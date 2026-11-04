from pathlib import Path

import numpy as np
import pytest
import requests
from streamlit.testing.v1 import AppTest

from options_analytics import deribit, visualization
from options_analytics.positioning import near_spot_range, open_interest_by_strike
from conftest import smile_boxes, oi_expiries, set_oi_expiries


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
SNAPSHOT_PATH = APP_PATH.parent / "data/deribit_btc_options_snapshot.json"


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("The dashboard must not use the network")

    monkeypatch.setattr(requests.sessions.Session, "request", fail)


@pytest.fixture
def figures(monkeypatch):
    recorded = {}
    for name in ["make_positioning_figure", "make_smile_figure"]:
        build = getattr(visualization, name)

        def record(*args, _name=name, _build=build, **kwargs):
            figure = _build(*args, **kwargs)
            recorded[_name] = figure
            return figure

        monkeypatch.setattr(visualization, name, record)
    return recorded


@pytest.fixture
def chain():
    return deribit.parse_deribit_snapshot(deribit.load_deribit_snapshot(SNAPSHOT_PATH))


def _app():
    return AppTest.from_file(str(APP_PATH), default_timeout=30).run()


def _bars(figure):
    call, put = figure.data[:2]
    return dict(zip(call.x, call.y)), dict(zip(put.x, put.y))


def _oi_title(figure):
    (title,) = [a.text for a in figure.layout.annotations if a.name == "oi_title"]
    return title


def test_open_interest_opens_on_all_expiries_near_spot(figures, chain):
    app = _app()
    assert not app.exception and not app.error
    index_price = chain["index_price"].iloc[0]
    low, high = near_spot_range(index_price)
    assert oi_expiries(app) == []
    assert app.slider[0].value == pytest.approx((low, high))

    figure = figures["make_positioning_figure"]
    assert _oi_title(figure) == "Open interest · All expiries"
    calls, puts = _bars(figure)
    expected = open_interest_by_strike(chain)
    expected = expected[(expected.strike >= low) & (expected.strike <= high)]
    assert sorted(calls) == expected["strike"].tolist()
    np.testing.assert_allclose([calls[k] for k in expected.strike], expected.call_oi)
    np.testing.assert_allclose([puts[k] for k in expected.strike], expected.put_oi)
    assert [shape.x0 for shape in figure.layout.shapes] == [index_price, index_price]
    assert "All expiries" in figure.data[0].hovertemplate


def test_oi_expiry_selection_sums_only_those_expiries_and_leaves_iv_alone(figures, chain):
    app = _app()
    smile_before = figures["make_smile_figure"].to_json()
    checks_before = [box.value for box in smile_boxes(app)]
    taus = sorted(chain["tau"].unique())
    chosen = [taus[1], taus[4]]

    set_oi_expiries(app, chosen)
    assert not app.exception
    dates = [chain.loc[chain.tau == tau, "expiry_dt"].iloc[0].strftime("%Y-%m-%d")
             for tau in chosen]
    scope = ", ".join(dates)
    figure = figures["make_positioning_figure"]
    assert _oi_title(figure) == f"Open interest · {scope}"
    assert scope in figure.data[0].hovertemplate
    calls, puts = _bars(figure)
    subset = chain[chain.tau.isin(chosen)]
    for strike, value in calls.items():
        expected = subset.loc[(subset.strike == strike) & (subset.flag == "call"), "open_interest"].sum()
        assert value == pytest.approx(expected)
    for strike, value in puts.items():
        expected = subset.loc[(subset.strike == strike) & (subset.flag == "put"), "open_interest"].sum()
        assert value == pytest.approx(expected)

    assert [box.value for box in smile_boxes(app)] == checks_before
    assert figures["make_smile_figure"].to_json() == smile_before


def test_many_oi_expiries_keep_the_titles_short_and_list_every_date_on_hover(
    figures, chain
):
    app = _app()
    dates = chain.drop_duplicates("tau").sort_values("tau")
    chosen = dates["tau"].tolist()[:5]
    labels = [f"{d:%Y-%m-%d}" for d in dates["expiry_dt"][:5]]

    set_oi_expiries(app, chosen)
    assert not app.exception
    figure = figures["make_positioning_figure"]
    short = f"5 expiries · {labels[0]} to {labels[-1]}"
    assert _oi_title(figure) == f"Open interest · {short}"
    (gex_title,) = [a.text for a in figure.layout.annotations if a.name == "gex_title"]
    assert gex_title.startswith(f"Net gamma exposure · {short}<br>")
    assert f"every strike in {short})" in gex_title
    assert ", ".join(labels) in figure.data[0].hovertemplate

    set_oi_expiries(app, dates["tau"].tolist())
    assert _oi_title(figures["make_positioning_figure"]) == "Open interest · All expiries"


def test_strike_range_zooms_and_resets_to_near_spot(figures, chain):
    app = _app()
    near = near_spot_range(chain["index_price"].iloc[0])
    app.slider[0].set_value((60_000.0, 110_000.0)).run()
    assert not app.exception
    calls, _ = _bars(figures["make_positioning_figure"])
    assert min(calls) >= 60_000.0 and max(calls) <= 110_000.0
    assert min(calls) < near[0] and max(calls) > near[1]

    next(button for button in app.button if button.label == "Near spot").click().run()
    assert not app.exception
    assert app.slider[0].value == pytest.approx(near)


def test_strike_range_labels_read_as_thousands_separated_usd(chain):
    app = _app()
    slider = app.slider[0]
    # sprintf-js: "%,.0f" groups thousands, so 74,004.96 reads "$74,005".
    assert slider.proto.format == "$%,.0f"
    index_price = chain["index_price"].iloc[0]
    assert slider.value == (index_price * 0.9, index_price * 1.1)


def test_empty_strike_range_shows_a_state_that_zooms_out(figures, chain):
    app = _app()
    # 81,000 and 81,500 are adjacent listed strikes; nothing lies strictly between.
    app.slider[0].set_value((81_100.0, 81_400.0)).run()
    assert not app.exception
    assert any("No strikes in this range" in info.value for info in app.info)
    charts_with_oi_and_gex = len(_app().get("plotly_chart"))
    assert len(app.get("plotly_chart")) == charts_with_oi_and_gex - 1

    next(b for b in app.button if b.label == "Zoom out to all strikes").click().run()
    assert not app.exception
    assert not any("No strikes in this range" in info.value for info in app.info)
    low, high = app.slider[0].value
    assert low <= chain.strike.min() and high >= chain.strike.max()
    calls, _ = _bars(figures["make_positioning_figure"])
    assert sorted(calls) == sorted(chain.strike.unique())
