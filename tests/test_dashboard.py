import json
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

import requests

from iv_surface import deribit, iv_source, visualization


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
SNAPSHOT_PATH = APP_PATH.parent / "data/deribit_btc_options_snapshot.json"


def _app():
    return AppTest.from_file(str(APP_PATH), default_timeout=30).run()


def _chain():
    return deribit.parse_deribit_snapshot(deribit.load_deribit_snapshot(SNAPSHOT_PATH))


@pytest.fixture(autouse=True)
def fresh_cache():
    import streamlit as st

    st.cache_data.clear()
    yield
    st.cache_data.clear()


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("The dashboard must not use the network")

    monkeypatch.setattr(requests.sessions.Session, "request", fail)


def _record_figures(monkeypatch, names):
    figures = {}
    for name in names:
        build = getattr(visualization, name)

        def record(*args, _name=name, _build=build, **kwargs):
            figure = _build(*args, **kwargs)
            figures[_name] = figure
            return figure

        monkeypatch.setattr(visualization, name, record)
    return figures


def _line_traces(figure):
    return [trace for trace in figure.data if trace.mode == "lines+markers"]


def test_iv_charts_open_on_exchange_mark_and_switch_to_quote_midpoint(monkeypatch):
    from iv_surface.iv_source import build_iv_source_surface
    from iv_surface.surface_transforms import atm_term_structure_frame, surface_to_long_frame

    figures = _record_figures(monkeypatch, [
        "make_iv_heatmap", "make_iv_surface_figure", "make_smile_figure",
        "make_atm_term_structure_figure",
    ])
    chain = _chain()
    app = _app()
    assert not app.exception and not app.error
    control = app.segmented_control[0]
    assert control.label == "IV source"
    assert control.value == "Exchange mark"
    assert list(control.options) == ["Exchange mark", "Quote midpoint"]

    for source in ["Exchange mark", "Quote midpoint"]:
        if source != control.value:
            control.set_value(source).run()
            assert not app.exception and not app.error
        expected = build_iv_source_surface(chain, source)
        atm = atm_term_structure_frame(surface_to_long_frame(
            expected.iv_surface, expected.expiries, expected.strikes, expected.spot_price,
        ))
        trace = figures["make_atm_term_structure_figure"].data[0]
        np.testing.assert_allclose(trace.y, atm["iv"], equal_nan=True)
        assert f"{source} IV" in trace.hovertemplate
        for line in _line_traces(figures["make_smile_figure"]):
            row = expected.expiries.index(line.meta)
            np.testing.assert_allclose(line.y, expected.iv_surface[row], equal_nan=True)
            assert f"{source} IV" in line.hovertemplate
            assert "display band" in line.hovertemplate
        assert f"{source} IV" in figures["make_iv_heatmap"].data[0].hovertemplate
        assert any("display band" in caption.value for caption in app.caption)


def _patch_iv_build(monkeypatch, adjust=lambda result: result):
    calls = []
    build = iv_source.build_iv_source_surface

    def patched(chain, source):
        calls.append(source)
        return adjust(build(chain, source))

    monkeypatch.setattr(iv_source, "build_iv_source_surface", patched)
    return calls


def _mark_result():
    return iv_source.build_iv_source_surface(_chain(), "Exchange mark")


def test_dashboard_opens_on_exchange_mark_without_rate_inputs(monkeypatch):
    results = []
    calls = _patch_iv_build(monkeypatch, lambda result: results.append(result) or result)
    app = _app()
    assert not app.exception
    assert not app.error
    assert not app.selectbox
    assert not app.number_input
    assert calls == ["Exchange mark"]
    result = results[-1]
    counts = [int(metric.value.replace(",", "")) for metric in app.metric]
    assert sum(counts) == result.iv_surface.size
    assert counts[2] == np.isnan(result.iv_surface).sum()
    assert len(app.get("plotly_chart")) == 5
    assert app.sidebar.radio[0].value == "Core (0.8–1.2)"
    assert app.main.radio[0].value == "Surface"
    assert [tab.label for tab in app.tabs] == ["Heatmap", "3D surface", "IV smiles", "ATM term structure"]
    assert any(
        "293 observed · 175 interpolated · 36 blank" in caption.value
        for caption in app.caption
    )
    assert any("Deribit BTC · Frozen snapshot:" in caption.value for caption in app.caption)

    app.main.radio[0].set_value("Observed").run()
    assert not app.exception
    assert app.main.radio[0].value == "Observed"
    assert any(
        "293 observed · 0 interpolated · 211 blank" in caption.value
        for caption in app.caption
    )

    app.sidebar.radio[0].set_value("Extended (0.7–1.3)").run()
    assert not app.exception
    assert any(
        "355 observed · 248 interpolated · 69 blank" in caption.value
        for caption in app.caption
    )
    # View controls reuse the cached Exchange mark surface.
    assert calls == ["Exchange mark"]


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
    result = _mark_result()
    ordered_expiries = sorted(result.expiries)
    dates = chain.drop_duplicates("tau").set_index("tau")["expiry_dt"]
    app = _app()
    assert not app.exception
    assert not app.multiselect
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
    assert len(_line_traces(smile)) == 1
    trace = _line_traces(smile)[0]
    row = result.expiries.index(selected)
    order = np.argsort(result.strikes)
    np.testing.assert_allclose(trace.y, result.iv_surface[row, order], equal_nan=True)
    np.testing.assert_allclose(trace.x, np.asarray(result.strikes)[order] / result.spot_price)
    assert np.isnan(trace.y).any()
    assert all(item.connectgaps is False for item in smile.data)
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
    assert len(app.get("plotly_chart")) == 4
    assert any("Select an expiry" in info.value for info in app.info)


@pytest.mark.parametrize("finite_count", [0, 1, 2, 4])
def test_smile_defaults_skip_expiries_without_finite_iv(monkeypatch, finite_count):
    expected = []
    ordered_expiries = []

    def sparse_result(result):
        ordered_expiries[:] = sorted(result.expiries)
        # Keep later expiries usable to catch default selection of blank early rows.
        chosen = sorted(result.expiries)[-finite_count:] if finite_count else []
        expected[:] = chosen[:3]
        for index, tau in enumerate(result.expiries):
            if tau not in chosen:
                result.iv_surface[index, :] = np.nan
        return result

    _patch_iv_build(monkeypatch, sparse_result)
    app = _app()
    assert not app.exception
    assert [tau for tau, box in zip(ordered_expiries, app.checkbox) if box.value] == expected
    assert len(app.get("plotly_chart")) == (5 if finite_count else 4)


@pytest.mark.parametrize("case", ["file", "schema", "index"])
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

        def load(path):
            return raw

    monkeypatch.setattr(deribit, "load_deribit_snapshot", load)
    app = _app()
    assert not app.exception
    assert len(app.error) == 1
    assert not app.get("plotly_chart")


def test_without_quotes_exchange_mark_still_charts_and_quote_midpoint_stays_missing(monkeypatch):
    raw = json.loads(SNAPSHOT_PATH.read_text())
    for book in raw["requests"][1]["response"]["result"]:
        book["bid_price"] = None
        book["ask_price"] = None
    monkeypatch.setattr(deribit, "load_deribit_snapshot", lambda path: raw)
    figures = _record_figures(monkeypatch, ["make_smile_figure"])

    app = _app()
    assert not app.exception and not app.error
    assert not app.warning
    line = _line_traces(figures["make_smile_figure"])[0]
    assert np.isfinite(line.y).any()

    app.segmented_control[0].set_value("Quote midpoint").run()
    assert not app.exception and not app.error
    assert any("No IV solves succeeded" in item.value for item in app.warning)
    counts = [int(metric.value.replace(",", "")) for metric in app.metric]
    assert counts[0] == counts[1] == 0


def test_atm_uses_raw_all_expiries_independent_of_view_controls(monkeypatch):
    from iv_surface.surface_transforms import atm_term_structure_frame, surface_to_long_frame

    figures = []
    build_figure = visualization.make_atm_term_structure_figure

    def record(frame, **kwargs):
        figure = build_figure(frame, **kwargs)
        figures.append(figure)
        return figure

    monkeypatch.setattr(visualization, "make_atm_term_structure_figure", record)
    result = _mark_result()
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
    def sparse_result(result):
        # Retain only a wing quote in one expiry; other expiries have no IV.
        result.iv_surface[:] = np.nan
        result.iv_surface[0, 0] = 0.5
        return result

    _patch_iv_build(monkeypatch, sparse_result)
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
    assert len(app.get("plotly_chart")) == 5
    assert any("Deribit BTC · Frozen snapshot:" in caption.value for caption in app.caption)
    chain = _chain()
    result = _mark_result()
    dates = chain.drop_duplicates("tau").set_index("tau").expiry_dt
    frame = surface_to_long_frame(
        result.iv_surface, result.expiries, result.strikes, result.spot_price,
        expiry_datetimes=dates.reindex(result.expiries).tolist(), source_grid=result.source_grid,
    )
    expected_atm = atm_term_structure_frame(frame)
    np.testing.assert_allclose(figures["make_atm_term_structure_figure"].data[0].y,
                               expected_atm.iv, equal_nan=True)
    assert sum(int(metric.value.replace(",", "")) for metric in app.metric) == result.iv_surface.size
    for trace in _line_traces(figures["make_smile_figure"]):
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
