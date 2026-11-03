import json
from pathlib import Path

import numpy as np
import pytest
import requests
from streamlit.testing.v1 import AppTest

from iv_surface import deribit, visualization
from iv_surface.positioning import near_spot_range, net_gex_by_strike


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
    for name in ["make_open_interest_figure", "make_gex_figure"]:
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


def test_gex_sits_below_oi_with_default_assumption_and_near_spot_zoom(figures, chain):
    app = _app()
    assert not app.exception and not app.error
    oi, gex = _chart_json(app, 0), _chart_json(app, 1)
    assert oi["layout"]["yaxis"]["title"]["text"] == "OI · BTC"
    assert "Net gamma exposure" in gex["layout"]["title"]["text"]

    figure = figures["make_gex_figure"]
    title = figure.layout.title.text
    assert "Call+ / Put− (Calls customer sells, Puts customer buys)" in title
    assert "Exchange mark IV" in title and "100% of OI computable" in title
    low, high = near_spot_range(chain["index_price"].iloc[0])
    expected = net_gex_by_strike(chain)
    expected = expected[(expected.strike >= low) & (expected.strike <= high)]
    assert list(figure.data[0].x) == expected["strike"].tolist()
    np.testing.assert_allclose(list(figure.data[0].y), expected["net_gex"])
    assert list(figure.layout.xaxis.range) == list(
        figures["make_open_interest_figure"].layout.xaxis.range
    )


def test_gex_follows_the_oi_expiries_and_strike_zoom(figures, chain):
    app = _app()
    taus = sorted(chain["tau"].unique())
    chosen = [taus[1], taus[4]]
    app.multiselect[0].set_value(chosen).run()
    app.slider[0].set_value((60_000.0, 110_000.0)).run()
    assert not app.exception

    figure = figures["make_gex_figure"]
    expected = net_gex_by_strike(chain, expiries=chosen)
    expected = expected[(expected.strike >= 60_000.0) & (expected.strike <= 110_000.0)]
    assert list(figure.data[0].x) == expected["strike"].tolist()
    np.testing.assert_allclose(list(figure.data[0].y), expected["net_gex"])
    assert list(figure.data[0].x) == list(figures["make_open_interest_figure"].data[0].x)
    assert list(figure.layout.xaxis.range) == list(
        figures["make_open_interest_figure"].layout.xaxis.range
    )
    assert "2026-10-17, 2026-10-23" in figure.layout.title.text
