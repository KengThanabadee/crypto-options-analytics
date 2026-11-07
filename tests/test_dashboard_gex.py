import json
from pathlib import Path

import numpy as np
import pytest
import requests
from streamlit.testing.v1 import AppTest

from options_analytics import deribit, positioning, visualization
from options_analytics.positioning import near_spot_range, net_gex_by_strike
from conftest import set_oi_expiries


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
    for name in ["make_positioning_figure"]:
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


def _chart_json(app, index):
    return json.loads(app.get("plotly_chart")[index].proto.spec)


def _gex_title(figure):
    (annotation,) = [a for a in figure.layout.annotations if a.name == "gex_title"]
    return annotation.text


def _gex_bars(figure):
    return figure.data[2]


def test_gex_sits_below_oi_with_default_assumption_and_near_spot_zoom(figures, chain):
    app = _app()
    assert not app.exception and not app.error
    chart = _chart_json(app, 0)
    assert chart["layout"]["yaxis"]["title"]["text"] == "OI · BTC"
    assert chart["layout"]["xaxis"]["matches"] == "x2"
    # The OI panel sits above the GEX panel.
    assert chart["layout"]["yaxis"]["domain"][0] > chart["layout"]["yaxis2"]["domain"][1]

    figure = figures["make_positioning_figure"]
    title = _gex_title(figure)
    assert title.startswith("Net gamma exposure")
    assert "Call+ / Put− (Calls customer sells, Puts customer buys)" in title
    assert "Exchange mark IV" in title and "100% of OI computable" in title
    low, high = near_spot_range(chain["index_price"].iloc[0])
    expected = net_gex_by_strike(chain)
    expected = expected[(expected.strike >= low) & (expected.strike <= high)]
    assert list(_gex_bars(figure).x) == expected["strike"].tolist()
    np.testing.assert_allclose(list(_gex_bars(figure).y), expected["net_gex"])


def test_gex_follows_the_oi_expiries_and_strike_zoom(figures, chain):
    app = _app()
    taus = sorted(chain["tau"].unique())
    chosen = [taus[1], taus[4]]
    set_oi_expiries(app, chosen)
    app.slider[0].set_value((60_000.0, 110_000.0)).run()
    assert not app.exception

    figure = figures["make_positioning_figure"]
    expected = net_gex_by_strike(chain, expiries=chosen)
    expected = expected[(expected.strike >= 60_000.0) & (expected.strike <= 110_000.0)]
    assert list(_gex_bars(figure).x) == expected["strike"].tolist()
    np.testing.assert_allclose(list(_gex_bars(figure).y), expected["net_gex"])
    assert list(_gex_bars(figure).x) == list(figure.data[0].x)
    assert "2026-10-17, 2026-10-23" in _gex_title(figure)


def _control(app, label):
    (control,) = [c for c in app.segmented_control if c.label == label]
    return control


def test_new_analysis_starts_at_call_plus_put_minus_and_net(figures):
    app = _app()
    assert _control(app, "Calls").value == "Customer sells"
    assert _control(app, "Puts").value == "Customer buys"
    assert _control(app, "GEX view").value == "Net"
    assert _gex_title(figures["make_positioning_figure"]).startswith("Net gamma exposure")


def test_flipping_an_assumption_changes_only_gex_signs_without_fetching(figures, chain):
    app = _app()
    oi_before = [trace.to_plotly_json() for trace in figures["make_positioning_figure"].data[:2]]
    _control(app, "Calls").set_value("Customer buys").run()
    assert not app.exception and not app.error

    figure = figures["make_positioning_figure"]
    low, high = near_spot_range(chain["index_price"].iloc[0])
    expected = net_gex_by_strike(chain, signs={"call": -1, "put": -1})
    expected = expected[(expected.strike >= low) & (expected.strike <= high)]
    np.testing.assert_allclose(list(_gex_bars(figure).y), expected["net_gex"])
    title = _gex_title(figure)
    assert "Scenario: Call− / Put− (Calls customer buys, Puts customer buys)" in title
    assert "not observed dealer inventory" in title
    oi_after = [trace.to_plotly_json() for trace in figure.data[:2]]
    assert json.dumps(oi_after, default=str) == json.dumps(oi_before, default=str)


def test_gross_view_ignores_the_assumption(figures, chain):
    app = _app()
    _control(app, "GEX view").set_value("Gross").run()
    gross = list(_gex_bars(figures["make_positioning_figure"]).y)
    low, high = near_spot_range(chain["index_price"].iloc[0])
    expected = net_gex_by_strike(chain)
    expected = expected[(expected.strike >= low) & (expected.strike <= high)]
    np.testing.assert_allclose(gross, expected["gross_gex"])

    _control(app, "Puts").set_value("Customer sells").run()
    figure = figures["make_positioning_figure"]
    assert list(_gex_bars(figure).y) == gross
    assert "Scenario" not in _gex_title(figure)


def _fetched_snapshot():
    """The frozen responses, captured one hour later with a different index."""
    raw = json.loads(SNAPSHOT_PATH.read_text())
    raw["capture_started_at_utc"] = "2026-10-15T16:18:12.000000Z"
    raw["captured_at_utc"] = "2026-10-15T16:18:14.000000Z"
    for request in raw["requests"]:
        request["received_at_utc"] = "2026-10-15T16:18:13.000000Z"
    raw["requests"][2]["response"]["result"]["index_price"] = 90000.0
    return raw


def test_fetch_latest_keeps_every_setting_that_still_applies(figures, monkeypatch):
    monkeypatch.setattr(deribit, "fetch_deribit_snapshot", _fetched_snapshot)
    app = _app()
    _control(app, "Calls").set_value("Customer buys").run()
    _control(app, "GEX view").set_value("Gross").run()
    _control(app, "IV source").set_value("Quote midpoint").run()
    app.segmented_control(key="moneyness_range").set_value("All listed").run()
    app.segmented_control(key="heatmap_view").set_value("Observed").run()

    next(b for b in app.button if b.label == "Fetch latest").click().run()
    assert not app.exception and not app.error
    assert any("Fetched snapshot" in c.value for c in app.caption)
    assert _control(app, "Calls").value == "Customer buys"
    assert _control(app, "Puts").value == "Customer buys"
    assert _control(app, "GEX view").value == "Gross"
    assert _control(app, "IV source").value == "Quote midpoint"
    assert app.segmented_control(key="moneyness_range").value == "All listed"
    assert app.segmented_control(key="heatmap_view").value == "Observed"
    assert _gex_title(figures["make_positioning_figure"]).startswith("Gross gamma exposure")
    # The strike range belongs to the old snapshot; the new one starts at its own Near spot.
    assert app.slider[0].value == near_spot_range(90000.0)


def _positioning_chart(app):
    (chart,) = [c for c in app.get("plotly_chart") if "gex_title" in c.proto.spec]
    return chart


def test_dragging_across_the_chart_sets_the_strike_range_that_reruns_keep(chain):
    # Streamlit redraws a changed figure from scratch, so the zoom lives in the
    # strike range: a horizontal drag box-selects strikes and reruns the page.
    app = _app()
    chart = _positioning_chart(app)
    layout = json.loads(chart.proto.spec)["layout"]
    assert layout["dragmode"] == "select" and layout["selectdirection"] == "h"
    assert list(chart.proto.selection_mode) == [1]  # BOX
    assert "zoom2d" in json.loads(chart.proto.config)["modeBarButtonsToRemove"]

    low, high = app.slider[0].value
    app.slider[0].set_value((low + 2_000, high - 2_000)).run()
    _control(app, "Calls").set_value("Customer buys").run()
    _control(app, "GEX view").set_value("Gross").run()
    assert not app.exception
    assert app.slider[0].value == (low + 2_000, high - 2_000)
    next(b for b in app.button if b.label == "Near spot").click().run()
    assert app.slider[0].value == pytest.approx((low, high))


def test_switching_iv_source_never_changes_gex(figures):
    app = _app()
    before = figures["make_positioning_figure"].to_json()
    _control(app, "IV source").set_value("Quote midpoint").run()
    assert not app.exception
    assert figures["make_positioning_figure"].to_json() == before


def test_one_rerun_computes_gex_contributions_once(monkeypatch):
    calls = []
    compute = positioning.gex_contributions

    def record(*args, **kwargs):
        calls.append(1)
        return compute(*args, **kwargs)

    monkeypatch.setattr(positioning, "gex_contributions", record)
    app = _app()
    assert not app.exception and len(calls) == 1
    _control(app, "Calls").set_value("Customer buys").run()
    assert not app.exception and len(calls) == 2
