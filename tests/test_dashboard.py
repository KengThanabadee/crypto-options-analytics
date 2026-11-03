import json
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

import requests

from iv_surface import deribit, surface_builder, visualization


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
SNAPSHOT_PATH = APP_PATH.parent / "data/deribit_btc_options_snapshot.json"


def _app():
    return AppTest.from_file(str(APP_PATH), default_timeout=30).run()


def _chain():
    return deribit.parse_deribit_snapshot(deribit.load_deribit_snapshot(SNAPSHOT_PATH))


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("The dashboard must not use the network")

    monkeypatch.setattr(requests.sessions.Session, "request", fail)


def test_dashboard_opens_on_deribit_at_zero_rate_without_source_or_rate_inputs(monkeypatch):
    results = []
    build = surface_builder.build_combined_surface_from_chain

    def record(chain, r=0):
        result = build(chain, r=r)
        results.append((r, result))
        return result

    monkeypatch.setattr(surface_builder, "build_combined_surface_from_chain", record)
    app = _app()
    assert not app.exception
    assert not app.error
    assert not app.selectbox
    assert not app.number_input
    assert {r for r, _ in results} == {0}
    result = results[-1][1]
    counts = [int(metric.value.replace(",", "")) for metric in app.metric]
    assert sum(counts) == result.iv_surface.size
    assert counts[2] == np.isnan(result.iv_surface).sum()
    assert len(app.get("plotly_chart")) == 7
    assert app.sidebar.radio[0].value == "Core (0.8–1.2)"
    assert app.main.radio[0].value == "Surface"
    assert [tab.label for tab in app.tabs] == ["Heatmap", "3D surface", "IV smiles", "ATM term structure"]
    assert any(
        "270 observed · 168 interpolated · 66 blank" in caption.value
        for caption in app.caption
    )
    assert any("Deribit BTC · Frozen snapshot:" in caption.value for caption in app.caption)

    app.main.radio[0].set_value("Observed").run()
    assert not app.exception
    assert app.main.radio[0].value == "Observed"
    assert any(
        "270 observed · 0 interpolated · 234 blank" in caption.value
        for caption in app.caption
    )

    app.sidebar.radio[0].set_value("Extended (0.7–1.3)").run()
    assert not app.exception
    assert any(
        "326 observed · 213 interpolated · 133 blank" in caption.value
        for caption in app.caption
    )
    assert {r for r, _ in results} == {0}


def test_smile_selection_preserves_observations_and_other_views(monkeypatch):
    figures = {}
    for name in ["make_iv_heatmap", "make_iv_surface_figure", "make_smile_figure"]:
        build = getattr(visualization, name)

        def record(*args, _name=name, _build=build, **kwargs):
            figure = _build(*args, **kwargs)
            figures[_name] = figure
            return figure

        monkeypatch.setattr(visualization, name, record)

    chain = _chain()
    result = surface_builder.build_combined_surface_from_chain(chain)
    ordered_expiries = sorted(result.expiries)
    dates = chain.drop_duplicates("tau").set_index("tau")["expiry_dt"]
    app = _app()
    assert not app.exception
    assert [select.label for select in app.multiselect] == ["OI expiries"]
    assert [box.label for box in app.checkbox] == [
        dates[tau].strftime("%Y-%m-%d") for tau in ordered_expiries
    ]
    expected_defaults = [
        tau for tau in ordered_expiries
        if np.isfinite(result.iv_surface[result.expiries.index(tau)]).any()
    ][:3]
    assert [tau for tau, box in zip(ordered_expiries, app.checkbox) if box.value] == expected_defaults
    other_views = {
        name: figures[name].to_json()
        for name in ["make_iv_heatmap", "make_iv_surface_figure"]
    }

    selected = ordered_expiries[-1]
    for tau, box in zip(ordered_expiries, app.checkbox):
        box.set_value(tau == selected)
    app.run()
    assert not app.exception
    smile = figures["make_smile_figure"]
    assert len(smile.data) == 1
    trace = smile.data[0]
    row = result.expiries.index(selected)
    order = np.argsort(result.strikes)
    np.testing.assert_allclose(trace.y, result.iv_surface[row, order], equal_nan=True)
    np.testing.assert_allclose(trace.x, np.asarray(result.strikes)[order] / result.spot_price)
    assert np.isnan(trace.y).any()
    assert trace.connectgaps is False
    assert trace.name == dates[selected].strftime("%Y-%m-%d")
    np.testing.assert_array_equal(
        np.asarray(trace.customdata)[:, 1], result.source_grid[row, order]
    )
    for field in ["strike", "K / S", "IV", "source", "fullData.name"]:
        assert field in trace.hovertemplate
    for name, before in other_views.items():
        assert figures[name].to_json() == before

    app.sidebar.radio[0].set_value("Extended (0.7–1.3)").run()
    assert not app.exception
    assert figures["make_smile_figure"].to_json() == smile.to_json()
    assert [tau for tau, box in zip(ordered_expiries, app.checkbox) if box.value] == [selected]

    for box in app.checkbox:
        box.uncheck()
    app.run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == 6
    assert any("Select an expiry" in info.value for info in app.info)


@pytest.mark.parametrize("finite_count", [0, 1, 2, 4])
def test_smile_defaults_skip_expiries_without_finite_iv(monkeypatch, finite_count):
    build = surface_builder.build_combined_surface_from_chain
    expected = []
    ordered_expiries = []

    def sparse_result(chain, r=0):
        result = build(chain, r=r)
        ordered_expiries[:] = sorted(result.expiries)
        # Keep later expiries usable to catch default selection of blank early rows.
        chosen = sorted(result.expiries)[-finite_count:] if finite_count else []
        expected[:] = chosen[:3]
        for index, tau in enumerate(result.expiries):
            if tau not in chosen:
                result.iv_surface[index, :] = np.nan
        return result

    monkeypatch.setattr(surface_builder, "build_combined_surface_from_chain", sparse_result)
    app = _app()
    assert not app.exception
    assert [tau for tau, box in zip(ordered_expiries, app.checkbox) if box.value] == expected
    assert len(app.get("plotly_chart")) == (7 if finite_count else 6)


@pytest.mark.parametrize("case", ["file", "schema", "index", "quotes"])
def test_dashboard_input_errors_are_visible(monkeypatch, case):
    if case == "file":
        def load(path):
            raise OSError("missing file")
    else:
        raw = json.loads(SNAPSHOT_PATH.read_text())
        if case == "schema":
            raw["schema_version"] = -1
        elif case == "index":
            raw["requests"][2]["response"]["result"]["index_price"] = None
        else:
            for book in raw["requests"][1]["response"]["result"]:
                book["bid_price"] = None
                book["ask_price"] = None

        def load(path):
            return raw

    monkeypatch.setattr(deribit, "load_deribit_snapshot", load)
    app = _app()
    assert not app.exception
    assert len(app.error) == 1
    assert not app.get("plotly_chart")


def test_atm_uses_raw_all_expiries_independent_of_view_controls(monkeypatch):
    from iv_surface.surface_transforms import atm_term_structure_frame, surface_to_long_frame

    figures = []
    build_figure = visualization.make_atm_term_structure_figure

    def record(frame):
        figure = build_figure(frame)
        figures.append(figure)
        return figure

    monkeypatch.setattr(visualization, "make_atm_term_structure_figure", record)
    chain = _chain()
    result = surface_builder.build_combined_surface_from_chain(chain)
    expected = atm_term_structure_frame(surface_to_long_frame(
        result.iv_surface, result.expiries, result.strikes, result.spot_price,
    ))
    app = _app()
    assert not app.exception
    trace = figures[-1].data[0]
    np.testing.assert_allclose(trace.x, expected["tau"])
    np.testing.assert_allclose(trace.y, expected["iv"], equal_nan=True)
    np.testing.assert_allclose(
        np.asarray(trace.customdata)[:, :3].astype(float),
        expected[["strike", "moneyness", "atm_distance"]].to_numpy(), equal_nan=True,
    )
    assert list(np.asarray(trace.customdata)[:, 3]) == expected["selection_status"].tolist()
    assert trace.connectgaps is False
    assert len(trace.x) == len(result.expiries)
    before = figures[-1].to_json()
    for box in app.checkbox:
        box.uncheck()
    app.sidebar.radio[0].set_value("Extended (0.7–1.3)")
    app.main.radio[0].set_value("Observed").run()
    assert not app.exception
    assert figures[-1].to_json() == before


def test_atm_rejected_expiries_remain_gaps_and_have_visible_status(monkeypatch):
    build = surface_builder.build_combined_surface_from_chain

    def sparse_result(chain, r=0):
        result = build(chain, r=r)
        # Retain only a wing quote in one expiry; other expiries have no IV.
        result.iv_surface[:] = np.nan
        result.iv_surface[0, 0] = 0.5
        return result

    monkeypatch.setattr(surface_builder, "build_combined_surface_from_chain", sparse_result)
    app = _app()
    assert not app.exception
    details = app.dataframe[0].value
    assert details["iv"].isna().all()
    assert set(details["selection_status"]) == {"outside_bound", "no_finite_iv"}
    assert any("remain gaps" in item.value for item in app.info)


def test_all_views_follow_the_raw_deribit_chain(monkeypatch):
    from iv_surface.surface_transforms import atm_term_structure_frame, surface_to_long_frame

    figures = {}
    for name in ["make_iv_heatmap", "make_iv_surface_figure", "make_smile_figure", "make_atm_term_structure_figure"]:
        build = getattr(visualization, name)

        def record(frame, *args, _name=name, _build=build, **kwargs):
            figure = _build(frame, *args, **kwargs)
            figures[_name] = figure
            return figure

        monkeypatch.setattr(visualization, name, record)

    app = _app()
    assert not app.exception and not app.error
    assert len(app.get("plotly_chart")) == 7
    assert any("Deribit BTC · Frozen snapshot:" in caption.value for caption in app.caption)
    chain = _chain()
    result = surface_builder.build_combined_surface_from_chain(chain)
    dates = chain.drop_duplicates("tau").set_index("tau").expiry_dt
    frame = surface_to_long_frame(
        result.iv_surface, result.expiries, result.strikes, result.spot_price,
        expiry_datetimes=dates.reindex(result.expiries).tolist(), source_grid=result.source_grid,
    )
    expected_atm = atm_term_structure_frame(frame)
    np.testing.assert_allclose(figures["make_atm_term_structure_figure"].data[0].y,
                               expected_atm.iv, equal_nan=True)
    assert sum(int(metric.value.replace(",", "")) for metric in app.metric) == result.iv_surface.size
    for trace in figures["make_smile_figure"].data:
        tau = next(t for t in result.expiries if dates[t].strftime("%Y-%m-%d") == trace.name)
        np.testing.assert_allclose(trace.y, result.iv_surface[result.expiries.index(tau)], equal_nan=True)
    mesh = figures["make_iv_surface_figure"].data[0]
    np.testing.assert_allclose(mesh.z, figures["make_iv_heatmap"].data[0].z, equal_nan=True)
    atm_before = figures["make_atm_term_structure_figure"].to_json()
    for box in app.checkbox:
        box.uncheck()
    app.sidebar.radio[0].set_value("Extended (0.7–1.3)")
    app.main.radio[0].set_value("Observed").run()
    assert not app.exception
    assert figures["make_atm_term_structure_figure"].to_json() == atm_before


def _fetched_snapshot():
    """The frozen responses, captured one hour later with a different index."""
    raw = json.loads(SNAPSHOT_PATH.read_text())
    raw["capture_started_at_utc"] = "2026-10-15T16:18:12.000000Z"
    raw["captured_at_utc"] = "2026-10-15T16:18:14.000000Z"
    for request in raw["requests"]:
        request["received_at_utc"] = "2026-10-15T16:18:13.000000Z"
    raw["requests"][2]["response"]["result"]["index_price"] = 90000.0
    return raw


def _fetch_button(app):
    return next(button for button in app.button if button.label == "Fetch latest")


def test_fetch_latest_switches_the_whole_page_and_controls_do_not_fetch(monkeypatch):
    calls = []

    def fetch():
        calls.append(1)
        return _fetched_snapshot()

    monkeypatch.setattr(deribit, "fetch_deribit_snapshot", fetch)
    app = _app()
    assert not calls
    assert any("Frozen snapshot: 2026-10-15 15:18:14 UTC" in c.value for c in app.caption)

    _fetch_button(app).click().run()
    assert not app.exception and not app.error
    assert len(calls) == 1
    assert any("Fetched snapshot: 2026-10-15 16:18:14 UTC" in c.value for c in app.caption)
    assert not any("Frozen snapshot" in c.value for c in app.caption)
    assert any("$90,000.00" in m.value for m in app.markdown)

    app.sidebar.radio[0].set_value("Extended (0.7–1.3)").run()
    app.main.radio[0].set_value("Observed").run()
    app.checkbox[0].set_value(not app.checkbox[0].value).run()
    assert not app.exception
    assert len(calls) == 1
    assert any("Fetched snapshot: 2026-10-15 16:18:14 UTC" in c.value for c in app.caption)
    assert any("$90,000.00" in m.value for m in app.markdown)


@pytest.mark.parametrize("failure", ["network", "unusable"])
def test_failed_fetch_keeps_the_previous_snapshot_and_shows_the_error(monkeypatch, failure):
    def fetch():
        if failure == "network":
            raise deribit.DeribitFetchError("Deribit request failed: offline")
        raw = _fetched_snapshot()
        raw["requests"][2]["response"]["result"]["index_price"] = None
        return raw

    monkeypatch.setattr(deribit, "fetch_deribit_snapshot", fetch)
    app = _app()
    _fetch_button(app).click().run()
    assert not app.exception
    assert len(app.error) == 1
    if failure == "network":
        assert "offline" in app.error[0].value
    assert any("Frozen snapshot: 2026-10-15 15:18:14 UTC" in c.value for c in app.caption)
    assert any("$82,227.73" in m.value for m in app.markdown)
    assert len(app.get("plotly_chart")) == 7
