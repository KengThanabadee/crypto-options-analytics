from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from options_analytics.positioning import (
    expiry_scope_label,
    near_spot_range,
    open_interest_by_strike,
    strike_range_from_selection,
    strikes_in_range,
)


def _contract(flag, tau, strike, oi, day):
    return {
        "symbol": f"{flag}-{day}-{strike:.0f}", "flag": flag, "tau": tau,
        "strike": strike, "open_interest": oi,
        "expiry_dt": datetime(2026, 10, day, 8, tzinfo=timezone.utc),
        "mark_iv": 0.5, "underlying_price": 81_000.0, "index_price": 81_000.0,
    }


@pytest.fixture
def chain():
    return pd.DataFrame([
        _contract("call", 0.01, 80_000.0, 10.0, 16),
        _contract("put", 0.01, 80_000.0, 4.0, 16),
        _contract("call", 0.01, 90_000.0, 2.5, 16),
        _contract("call", 0.03, 80_000.0, 1.5, 23),
        _contract("put", 0.03, 70_000.0, 7.0, 23),
        _contract("put", 0.03, 90_000.0, 0.0, 23),
    ])


def test_open_interest_sums_calls_and_puts_by_strike_over_all_expiries(chain):
    table = open_interest_by_strike(chain)
    assert table["strike"].tolist() == [70_000.0, 80_000.0, 90_000.0]
    assert table["call_oi"].tolist() == [0.0, 11.5, 2.5]
    assert table["put_oi"].tolist() == [7.0, 4.0, 0.0]


def test_open_interest_sums_only_the_selected_expiries(chain):
    table = open_interest_by_strike(chain, expiries=[0.03])
    assert table["strike"].tolist() == [70_000.0, 80_000.0, 90_000.0]
    assert table["call_oi"].tolist() == [0.0, 1.5, 0.0]
    assert table["put_oi"].tolist() == [7.0, 0.0, 0.0]


def test_missing_open_interest_is_not_counted_as_zero(chain):
    chain.loc[0, "open_interest"] = np.nan
    table = open_interest_by_strike(chain).set_index("strike")
    assert np.isnan(table.loc[80_000.0, "call_oi"])
    assert table.loc[80_000.0, "put_oi"] == 4.0


def test_near_spot_range_includes_strikes_exactly_ten_percent_from_the_index():
    low, high = near_spot_range(80_000.0)
    assert (low, high) == pytest.approx((72_000.0, 88_000.0))
    table = pd.DataFrame({
        "strike": [71_999.0, 72_000.0, 80_000.0, 88_000.0, 88_001.0],
        "call_oi": 1.0, "put_oi": 1.0,
    })
    shown = strikes_in_range(table, (low, high))
    assert shown["strike"].tolist() == [72_000.0, 80_000.0, 88_000.0]


def test_strike_range_is_a_display_zoom_over_the_full_table(chain):
    full = open_interest_by_strike(chain)
    shown = strikes_in_range(full, (75_000.0, 85_000.0))
    assert shown["strike"].tolist() == [80_000.0]
    assert shown["call_oi"].tolist() == [11.5]
    assert open_interest_by_strike(chain).equals(full)
    assert strikes_in_range(full, (81_000.0, 85_000.0)).empty


def test_expiry_scope_names_all_expiries_or_the_selected_dates(chain):
    assert expiry_scope_label(chain, None) == "All expiries"
    assert expiry_scope_label(chain, [0.03, 0.01]) == "2026-10-16, 2026-10-23"


def test_open_interest_panel_shows_calls_and_puts_in_range_with_index_line(chain):
    from options_analytics.positioning import net_gex_by_strike
    from options_analytics.visualization import make_positioning_figure

    table = open_interest_by_strike(chain)
    figure = make_positioning_figure(
        table, net_gex_by_strike(chain), index_price=81_000.0,
        strike_range=(75_000.0, 95_000.0), scope="2026-10-16",
        assumption="Call+ / Put−", oi_share=1.0,
    )
    call, put = figure.data[:2]
    assert (call.type, call.name, put.type, put.name) == ("bar", "Call", "bar", "Put")
    assert list(call.x) == [80_000.0, 90_000.0]
    assert list(call.y) == [11.5, 2.5]
    assert list(put.y) == [4.0, 0.0]
    low, high = figure.layout.xaxis.range
    assert low <= 75_000.0 and high >= 95_000.0
    assert [shape.x0 for shape in figure.layout.shapes] == [81_000.0, 81_000.0]
    assert "BTC" in figure.layout.yaxis.title.text
    (title,) = [a.text for a in figure.layout.annotations if a.name == "oi_title"]
    assert "2026-10-16" in title
    for trace in (call, put):
        hover = trace.hovertemplate
        assert "Strike" in hover and "%{x" in hover
        assert "Call OI: %{customdata[0]" in hover and "Put OI: %{customdata[1]" in hover
        assert hover.count("BTC") == 2
        assert "2026-10-16" in hover
        np.testing.assert_array_equal(
            np.asarray(trace.customdata, dtype=float), [[11.5, 4.0], [2.5, 0.0]]
        )


@pytest.mark.parametrize("boxes, expected", [
    ([{"x": [80_400.5, 77_100.0], "y": [0, 1]}], (77_000.0, 80_500.0)),
    ([{"x": [60_000.0, 81_000.0]}], (70_000.0, 81_000.0)),
    ([{"x": [70_000.0, 74_000.0]}, {"x": [79_000.0, 83_000.0]}], (79_000.0, 83_000.0)),
    ([], None),
    ([{"x": [78_000.0, 78_000.0]}], None),
    ([{"x": [50_000.0, 60_000.0]}], None),
])
def test_a_dragged_strike_band_becomes_the_strike_range(boxes, expected):
    # The latest box wins, widened to whole $500 steps and clipped to the zoom
    # bounds; empty or outside bands are ignored.
    assert strike_range_from_selection(boxes, bounds=(70_000.0, 120_000.0)) == expected
