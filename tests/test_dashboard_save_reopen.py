"""Save and reopen through the dashboard (spec check 8)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
import streamlit
from streamlit.testing.v1 import AppTest

from iv_surface import iv_source, saved_analysis
from iv_surface.deribit import load_deribit_snapshot, parse_deribit_snapshot


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
SNAPSHOT_PATH = APP_PATH.parent / "data/deribit_btc_options_snapshot.json"


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("The dashboard must not use the network")

    monkeypatch.setattr(requests.sessions.Session, "request", fail)


@pytest.fixture
def saved_files(monkeypatch):
    """Record what the Save button would download."""
    saved = []

    def download_button(label, data, **kwargs):
        if label == "Save analysis":
            saved.append(data)
        return False

    monkeypatch.setattr(streamlit, "download_button", download_button)
    return saved


@pytest.fixture
def upload(monkeypatch):
    """Stand in for the browser upload; set ``upload.file`` to a file's bytes."""
    state = SimpleNamespace(file=None, count=0)

    def file_uploader(label, **kwargs):
        if state.file is None:
            return None
        return SimpleNamespace(
            name="analysis.json", file_id=f"upload-{state.count}",
            getvalue=lambda: state.file,
        )

    def put(data):
        state.count += 1
        state.file = data if isinstance(data, bytes) else data.encode()

    state.put = put
    monkeypatch.setattr(streamlit, "file_uploader", file_uploader)
    return state


def _app():
    return AppTest.from_file(str(APP_PATH), default_timeout=60).run()


def _charts(app):
    return [chart.proto.spec for chart in app.get("plotly_chart")]


def _segmented(app, label):
    (control,) = [c for c in app.segmented_control if c.label == label]
    return control


def _explore(app):
    """Move every analysis setting off its default."""
    chain = parse_deribit_snapshot(load_deribit_snapshot(SNAPSHOT_PATH))
    taus = sorted(chain["tau"].unique())
    app.multiselect[0].set_value([taus[1], taus[4]]).run()
    app.slider[0].set_value((60_000.0, 110_000.0)).run()
    _segmented(app, "Calls").set_value("Customer buys").run()
    _segmented(app, "Puts").set_value("Customer sells").run()
    _segmented(app, "GEX view").set_value("Gross").run()
    app.segmented_control(key="iv_source").set_value("Quote midpoint").run()
    app.radio(key="moneyness_range").set_value("Extended (0.7–1.3)").run()
    app.radio(key="heatmap_view").set_value("Observed").run()
    app.checkbox[0].set_value(False).run()
    app.checkbox[5].set_value(True).run()
    assert not app.exception and not app.error
    return app


def _settings_shown(app):
    return {
        "oi_expiries": app.multiselect[0].value,
        "strike_range": app.slider[0].value,
        "calls": _segmented(app, "Calls").value,
        "puts": _segmented(app, "Puts").value,
        "gex_view": _segmented(app, "GEX view").value,
        "iv_source": app.segmented_control(key="iv_source").value,
        "moneyness": app.radio(key="moneyness_range").value,
        "heatmap": app.radio(key="heatmap_view").value,
        "smiles": [box.value for box in app.checkbox],
    }


def test_reopening_a_saved_analysis_restores_every_setting_and_the_same_charts(
    saved_files, upload
):
    explored = _explore(_app())
    assert saved_files
    file = saved_files[-1]

    reopened = _app()
    assert _settings_shown(reopened) != _settings_shown(explored)
    upload.put(file)
    reopened.run()

    assert not reopened.exception and not reopened.error and not reopened.warning
    assert _settings_shown(reopened) == _settings_shown(explored)
    assert _charts(reopened) == _charts(explored)
    assert any("Reopened snapshot: 2026-10-15 15:18:14 UTC" in c.value
               for c in reopened.caption)
    assert not reopened.info or not any(
        "calculation version" in i.value for i in reopened.info
    )
    saved = json.loads(file)
    assert saved["calculation_version"] == saved_analysis.CALCULATION_VERSION
    assert saved["snapshot"] == load_deribit_snapshot(SNAPSHOT_PATH)


def test_a_different_calculation_version_shows_a_recompute_notice(saved_files, upload):
    app = _app()
    saved = json.loads(saved_files[-1])
    saved["calculation_version"] = saved_analysis.CALCULATION_VERSION + 1
    upload.put(json.dumps(saved))
    app.run()

    assert not app.exception and not app.error
    notices = [i.value for i in app.info if "calculation version" in i.value]
    assert len(notices) == 1
    assert f"version {saved['calculation_version']}" in notices[0]


def test_an_invalid_file_shows_an_error_and_keeps_the_current_analysis(
    saved_files, upload
):
    app = _explore(_app())
    before = (_settings_shown(app), _charts(app))
    saved = json.loads(saved_files[-1])
    saved["settings"]["iv_source"] = "Bybit"
    upload.put(json.dumps(saved))
    app.run()

    assert not app.exception
    assert len(app.error) == 1 and "Cannot open" in app.error[0].value
    assert (_settings_shown(app), _charts(app)) == before
    assert any("Frozen snapshot" in c.value for c in app.caption)


def _later_snapshot():
    raw = json.loads(SNAPSHOT_PATH.read_text())
    raw["capture_started_at_utc"] = "2026-10-15T16:18:12.000000Z"
    raw["captured_at_utc"] = "2026-10-15T16:18:14.000000Z"
    for request in raw["requests"]:
        request["received_at_utc"] = "2026-10-15T16:18:13.000000Z"
    raw["requests"][2]["response"]["result"]["index_price"] = 90000.0
    return raw


def test_reopening_another_snapshot_switches_the_page_and_controls_keep_working(upload):
    snapshot = _later_snapshot()
    chain = parse_deribit_snapshot(snapshot)
    expiries = sorted(chain["expiry_dt"].unique())
    file = saved_analysis.save_analysis(snapshot, {
        "oi_expiries": [expiries[2]],
        "strike_range": (70_000.0, 100_000.0),
        "signs": {"call": 1, "put": 1},
        "gex_view": "Net",
        "iv_source": "Exchange mark",
        "moneyness_range": (0.8, 1.2),
        "heatmap_values": "Surface",
        "smile_expiries": [expiries[3]],
    })
    app = _app()
    upload.put(file)
    app.run()

    assert not app.exception and not app.error and not app.warning
    assert any("Reopened snapshot: 2026-10-15 16:18:14 UTC" in c.value for c in app.caption)
    assert any("$90,000.00" in m.value for m in app.markdown)
    tau = float(chain.loc[chain["expiry_dt"] == expiries[2], "tau"].iloc[0])
    assert app.multiselect[0].value == [tau]
    assert app.slider[0].value == (70_000.0, 100_000.0)
    assert _segmented(app, "Puts").value == "Customer sells"
    assert [box.value for box in app.checkbox] == [i == 3 for i in range(len(expiries))]

    _segmented(app, "Puts").set_value("Customer buys").run()
    app.checkbox[0].set_value(True).run()
    assert not app.exception and not app.error
    assert _segmented(app, "Puts").value == "Customer buys"
    assert app.checkbox[0].value and app.checkbox[3].value
    assert app.slider[0].value == (70_000.0, 100_000.0)
    assert any("Reopened snapshot: 2026-10-15 16:18:14 UTC" in c.value for c in app.caption)


def test_a_failed_iv_build_keeps_the_iv_view_settings_and_saves_them(
    saved_files, monkeypatch
):
    build = iv_source.build_iv_source_surface

    def build_or_fail(chain, source, **kwargs):
        if source == "Quote midpoint":
            raise ValueError("no usable quotes")
        return build(chain, source, **kwargs)

    streamlit.cache_data.clear()
    monkeypatch.setattr(iv_source, "build_iv_source_surface", build_or_fail)
    app = _app()
    app.radio(key="moneyness_range").set_value("Extended (0.7–1.3)").run()
    app.radio(key="heatmap_view").set_value("Observed").run()
    app.checkbox[0].set_value(False).run()
    app.checkbox[5].set_value(True).run()
    chosen = json.loads(saved_files[-1])["settings"]
    shown = _settings_shown(app)

    app.segmented_control(key="iv_source").set_value("Quote midpoint").run()
    assert any("Cannot build IV" in error.value for error in app.error)
    _segmented(app, "GEX view").set_value("Gross").run()
    _segmented(app, "GEX view").set_value("Net").run()
    saved = json.loads(saved_files[-1])["settings"]
    assert saved == {**chosen, "iv_source": "Quote midpoint"}

    app.segmented_control(key="iv_source").set_value("Exchange mark").run()
    assert not app.exception and not app.error
    assert _settings_shown(app) == shown
    streamlit.cache_data.clear()


def test_an_empty_strike_range_keeps_the_gex_scenario_and_saves_it(saved_files):
    app = _app()
    _segmented(app, "Calls").set_value("Customer buys").run()
    _segmented(app, "GEX view").set_value("Gross").run()
    # 81,000 and 81,500 are adjacent listed strikes; nothing lies strictly between.
    app.slider[0].set_value((81_100.0, 81_400.0)).run()
    app.run()

    assert not app.exception and not app.error
    assert any("No strikes in this range" in info.value for info in app.info)
    assert _segmented(app, "Calls").value == "Customer buys"
    assert _segmented(app, "GEX view").value == "Gross"
    settings = json.loads(saved_files[-1])["settings"]
    assert settings["signs"] == {"call": -1, "put": -1}
    assert settings["gex_view"] == "Gross"
    assert settings["strike_range"] == [81_100.0, 81_400.0]
