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
    control = app.segmented_control(key="iv_source")
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

    def patched(chain, source, **kwargs):
        calls.append(source)
        return adjust(build(chain, source, **kwargs))

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
    assert len(app.get("plotly_chart")) == 4
    assert app.segmented_control(key="surface_view").value == "Heatmap"
    assert app.segmented_control(key="moneyness_range").value == "Core (0.8–1.2)"
    assert app.segmented_control(key="heatmap_view").value == "Surface"
    assert [tab.label for tab in app.tabs] == ["IV surface", "IV smiles", "ATM term structure"]
    assert any(
        "293 observed · 175 interpolated · 36 blank" in caption.value
        for caption in app.caption
    )
    assert any("Deribit BTC · Frozen snapshot:" in caption.value for caption in app.caption)

    app.segmented_control(key="heatmap_view").set_value("Observed").run()
    assert not app.exception
    assert app.segmented_control(key="heatmap_view").value == "Observed"
    assert any(
        "293 observed · 0 interpolated · 211 blank" in caption.value
        for caption in app.caption
    )

    app.segmented_control(key="moneyness_range").set_value("Extended (0.7–1.3)").run()
    assert not app.exception
    assert any(
        "355 observed · 0 interpolated · 317 blank" in caption.value
        for caption in app.caption
    )

    app.segmented_control(key="surface_view").set_value("3D").run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == 5
    assert not [c for c in app.segmented_control if c.key == "heatmap_view"]
    assert any(
        "355 observed · 248 interpolated · 69 blank" in caption.value
        for caption in app.caption
    )

    app.segmented_control(key="surface_view").set_value("Heatmap").run()
    assert not app.exception
    assert app.segmented_control(key="heatmap_view").value == "Observed"
    assert len(app.get("plotly_chart")) == 4
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
        for name in ["make_iv_heatmap"]
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
        np.asarray(trace.customdata)[:, 1],
        [visualization.SOURCE_LABELS[code] for code in result.source_grid[row, order]],
    )
    for field in ["Strike", "K / S", "IV", "IV from", "fullData.name"]:
        assert field in trace.hovertemplate
    for name, before in other_views.items():
        assert figures[name].to_json() == before

    app.segmented_control(key="moneyness_range").set_value("Extended (0.7–1.3)").run()
    assert not app.exception
    assert figures["make_smile_figure"].to_json() == smile.to_json()
    assert [tau for tau, box in zip(ordered_expiries, app.checkbox) if box.value] == [selected]

    for box in app.checkbox:
        box.uncheck()
    app.run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == 3
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
    assert len(app.get("plotly_chart")) == (4 if finite_count else 3)


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

    app.segmented_control(key="iv_source").set_value("Quote midpoint").run()
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
    app.segmented_control(key="moneyness_range").set_value("Extended (0.7–1.3)")
    app.segmented_control(key="heatmap_view").set_value("Observed").run()
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
    assert len(app.get("plotly_chart")) == 4
    assert "make_iv_surface_figure" not in figures
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
    heatmap = figures.pop("make_iv_heatmap")
    app.segmented_control(key="surface_view").set_value("3D").run()
    assert not app.exception
    assert "make_iv_heatmap" not in figures
    mesh = figures["make_iv_surface_figure"].data[0]
    np.testing.assert_allclose(mesh.z, heatmap.data[0].z, equal_nan=True)
    atm_before = figures["make_atm_term_structure_figure"].to_json()
    for box in app.checkbox:
        box.uncheck()
    app.segmented_control(key="moneyness_range").set_value("Extended (0.7–1.3)").run()
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
    assert any("16:18:14 UTC · Index $90,000.00" in c.value for c in app.caption)

    app.segmented_control(key="moneyness_range").set_value("Extended (0.7–1.3)").run()
    app.segmented_control(key="heatmap_view").set_value("Observed").run()
    app.checkbox[0].set_value(not app.checkbox[0].value).run()
    assert not app.exception
    assert len(calls) == 1
    assert any("16:18:14 UTC · Index $90,000.00" in c.value for c in app.caption)


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
    assert any(
        "Frozen snapshot: 2026-10-15 15:18:14 UTC · Index $82,227.73" in c.value
        for c in app.caption
    )
    assert len(app.error) == 1 and not _in_header(app, app.error[0])
    assert len(app.get("plotly_chart")) == 4


def test_a_fetched_snapshot_is_parsed_once(monkeypatch):
    fetched = _fetched_snapshot()
    monkeypatch.setattr(deribit, "fetch_deribit_snapshot", lambda: fetched)
    parsed = []
    parse = deribit.parse_deribit_snapshot

    def record(snapshot):
        parsed.append(snapshot["captured_at_utc"])
        return parse(snapshot)

    monkeypatch.setattr(deribit, "parse_deribit_snapshot", record)
    app = _app()
    _fetch_button(app).click().run()
    assert not app.exception and not app.error
    app.segmented_control(key="heatmap_view").set_value("Observed").run()
    assert not app.exception
    assert parsed.count(fetched["captured_at_utc"]) == 1


def test_bid_ask_band_iv_is_solved_once_per_snapshot_across_iv_sources(monkeypatch):
    solved = []
    solve = iv_source.solve_contract_iv

    def record(chain, price_column):
        solved.append(price_column)
        return solve(chain, price_column)

    monkeypatch.setattr(iv_source, "solve_contract_iv", record)
    app = _app()
    app.segmented_control(key="iv_source").set_value("Quote midpoint").run()
    app.segmented_control(key="iv_source").set_value("Exchange mark").run()
    assert not app.exception and not app.error
    assert sorted(solved) == ["ask_price", "bid_price", "mid_price"]


def _in_header(app, element):
    return any(node is element for column in app.columns[:2] for node in column)


def test_header_is_one_row_with_the_index_and_fetch_latest_on_the_right():
    app = _app()
    caption, fetch = app.columns[0], app.columns[1]
    assert [c.value for c in caption.caption] == [
        "Deribit BTC · Frozen snapshot: 2026-10-15 15:18:14 UTC · Index $82,227.73"
    ]
    assert [b.label for b in fetch.button] == ["Fetch latest"]


def test_an_unreadable_snapshot_shows_its_error_in_the_header_beside_fetch_latest(monkeypatch):
    def load(path):
        raise OSError("missing file")

    monkeypatch.setattr(deribit, "load_deribit_snapshot", load)
    app = _app()
    message, fetch = app.columns[0], app.columns[1]
    assert [e.value for e in message.error] == [
        "Cannot read the frozen Deribit snapshot. Check its file and schema."
    ]
    assert [b.label for b in fetch.button] == ["Fetch latest"]


def test_page_labels_the_index_once_and_names_the_counted_iv_source():
    app = _app()
    assert not any(c.value.startswith("Open interest ·") for c in app.caption)
    assert sum("Index $82,227.73" in c.value for c in app.caption) == 1
    assert not any("Index $" in m.value for m in app.markdown)
    assert not any("IV source:" in m.value for m in app.markdown)
    assert not any("spot:" in m.value.lower() for m in app.markdown)
    assert any(e.label == "Combined IV coverage · Exchange mark" for e in app.sidebar.expander)
    app.segmented_control(key="iv_source").set_value("Quote midpoint").run()
    assert any(e.label == "Combined IV coverage · Quote midpoint" for e in app.sidebar.expander)


def test_method_notes_sit_under_their_own_heading_below_save_analysis():
    app = _app()
    order = []
    for node in app.sidebar:
        if node.type == "subheader":
            order.append(node.value)
        elif node.type in ("download_button", "expander"):
            order.append(node.label)
    start = order.index("Saved analysis")
    assert order[start:start + 5] == [
        "Saved analysis",
        "Save analysis",
        "Method notes",
        "Combined IV coverage · Exchange mark",
        "Deribit pricing",
    ]


def test_smile_checkboxes_show_what_the_chart_draws_on_every_run(monkeypatch):
    # The popover mounts its checkboxes lazily, so the browser shows each
    # checkbox's sent default; it must match the value the chart uses.
    figures = _record_figures(monkeypatch, ["make_smile_figure"])
    app = _app()
    for _ in range(2):
        assert not app.exception
        drawn = {trace.meta for trace in _line_traces(figures["make_smile_figure"])}
        assert len(drawn) == 3
        assert sum(box.value for box in app.checkbox) == 3
        assert [box.proto.default for box in app.checkbox] == [box.value for box in app.checkbox]
        app.segmented_control(key="heatmap_view").set_value("Observed").run()


@pytest.mark.parametrize("view", ["Heatmap", "3D"])
@pytest.mark.parametrize("source", ["Exchange mark", "Quote midpoint"])
def test_no_chart_draws_across_missing_values(source, view):
    # Missing values stay gaps on screen: lines never bridge them, and a band
    # is only ever a closed shape, since "tonexty" joins two edges across gaps.
    app = _app()
    (control,) = [c for c in app.segmented_control if c.label == "IV source"]
    control.set_value(source).run()
    app.segmented_control(key="surface_view").set_value(view).run()
    assert not app.exception
    traces = [
        trace
        for chart in app.get("plotly_chart")
        for trace in json.loads(chart.proto.spec)["data"]
    ]
    assert traces
    for trace in traces:
        if trace.get("type", "scatter") in ("scatter", "heatmap", "surface"):
            assert trace.get("connectgaps") is False, trace.get("name")
        assert trace.get("fill") in (None, "none", "toself"), trace.get("name")


def _notes_after_chart(block, chart=0):
    """Caption, expander label and expander text between a chart and the next chart."""
    nodes = list(block)
    charts = [i for i, node in enumerate(nodes) if node.type == "plotly_chart"]
    chart %= len(charts)
    end = charts[chart + 1] if chart + 1 < len(charts) else len(nodes)
    after = nodes[charts[chart] + 1:end]
    caption = next(node for node in after if node.type == "caption")
    expander = next(node for node in after if node.type == "expander")
    text = " ".join(node.value for node in expander if node.type in ("caption", "markdown"))
    return caption.value, expander.label, text


def test_gex_chart_has_a_one_line_caption_and_the_method_in_an_expander():
    caption, title, text = _notes_after_chart(_app().main, chart=0)
    assert caption == "GEX = s × gamma × OI × index² × 1% · USD per 1% BTC move"
    assert title == "How GEX is calculated"
    assert text.startswith("GEX per contract = s × gamma × OI × index² × 1%")
    assert text.endswith("Neither is drawn as a bar.")


def _tab(app, label):
    return next(tab for tab in app.tabs if tab.label == label)


def test_smile_chart_has_a_one_line_caption_and_the_band_in_an_expander():
    caption, title, text = _notes_after_chart(_tab(_app(), "IV smiles"))
    assert caption == (
        "Observed Combined Exchange mark IV · all strikes · gaps preserved · "
        "shading = bid–ask IV band"
    )
    assert title == "Smile shading"
    assert text == (
        "Shading is a bid–ask IV display band from our solver, blended with the "
        "line's Call/Put weights; it is not a tradable quote, and mark IV may sit "
        "outside it."
    )


SURFACE_CAPTION = (
    "2D total-variance interpolation · observed IV unchanged · "
    "blank outside the observed range"
)


@pytest.mark.parametrize("view", ["Heatmap", "3D"])
def test_surface_chart_has_the_range_above_and_a_caption_and_interpolation_expander_below(view):
    app = _app()
    app.segmented_control(key="surface_view").set_value(view).run()
    tab = _tab(app, "IV surface")
    nodes = list(tab)
    first_chart = min(i for i, node in enumerate(nodes) if node.type == "plotly_chart")
    above = [node.value for node in nodes[:first_chart] if node.type == "caption"]
    assert len(above) == 1 and above[0].startswith("Visible range: ")

    caption, title, text = _notes_after_chart(tab, chart=-1)
    assert caption == SURFACE_CAPTION
    assert title == "Surface interpolation"
    expander = next(e for e in tab.expander if e.label == title)
    assert len(expander.caption) == 3 and not expander.markdown
    assert text.startswith("Convert observed IV to total variance (IV² × tau)")
    assert text.endswith("hover reports their original IV.")
    assert "Surface interpolation" not in [e.label for e in app.sidebar.expander]


def test_observed_heatmap_caption_says_nothing_is_interpolated():
    app = _app()
    app.segmented_control(key="heatmap_view").set_value("Observed").run()
    caption, _, _ = _notes_after_chart(_tab(app, "IV surface"), chart=-1)
    assert caption == (
        "Observed IV only · no interpolation · blank where no contract was solved"
    )
