from datetime import datetime
import json
import subprocess
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from options_analytics.surface_transforms import (
    atm_term_structure_frame,
    surface_to_long_frame,
)
from options_analytics.visualization import (
    make_iv_heatmap,
    make_iv_surface_figure,
    make_smile_figure,
    make_atm_term_structure_figure,
)


def _long_frame():
    return surface_to_long_frame(
        np.array([[0.20, np.nan], [0.25, 0.30]]),
        expiries=[0.5, 0.25],
        strikes=[110, 90],
        spot_price=100,
    )


def _with_filled_gap(frame, iv=0.40):
    """Mark the frame's one missing cell Interpolated at ``iv``, as a display frame."""
    frame = frame.copy()
    frame["observed_iv"] = frame["iv"]
    gap = frame["iv"].isna()
    frame["surface_value_type"] = np.where(gap, "Interpolated", "Observed")
    frame.loc[gap, "iv"] = iv
    frame["interpolation_method"] = pd.Series(None, index=frame.index, dtype=object)
    frame.loc[gap, "interpolation_method"] = "2D linear total variance"
    return frame


def test_surface_transforms_do_not_require_plotly():
    script = """
import importlib.abc
import sys

class BlockPlotly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "plotly" or fullname.startswith("plotly."):
            raise ImportError("plotly intentionally unavailable")
        return None

sys.meta_path.insert(0, BlockPlotly())
from options_analytics.surface_transforms import (
    atm_term_structure_frame,
    interpolate_surface_2d,
    surface_to_long_frame,
)

frame = surface_to_long_frame([[0.2]], [0.25], [100], 100)
interpolate_surface_2d(frame)
atm_term_structure_frame(frame)
"""
    subprocess.run([sys.executable, "-c", script], check=True)


def test_surface_to_long_frame_preserves_shape_order_and_nan():
    frame = _long_frame()

    assert len(frame) == 4
    assert {"tau", "strike", "iv", "spot_price", "moneyness"} <= set(
        frame.columns
    )
    assert frame[["tau", "strike"]].values.tolist() == [
        [0.5, 110.0],
        [0.5, 90.0],
        [0.25, 110.0],
        [0.25, 90.0],
    ]
    assert frame["moneyness"].tolist() == [1.1, 0.9, 1.1, 0.9]
    assert np.isnan(frame.loc[1, "iv"])


def test_surface_to_long_frame_rejects_bad_shape_and_spot_price():
    with pytest.raises(ValueError, match="shape"):
        surface_to_long_frame(np.ones((1, 2)), [0.25, 0.5], [90, 100], 100)

    for spot_price in [0, -1, np.nan, np.inf]:
        with pytest.raises(ValueError, match="spot_price"):
            surface_to_long_frame(np.ones((1, 1)), [0.25], [100], spot_price)


def test_source_grid_preserves_alignment_and_existing_output():
    args = ([[0.2, np.nan], [0.3, 0.4]], [0.5, 0.25], [110, 100], 100)
    metadata = ["2026-07-01", "2026-06-01"]
    baseline = surface_to_long_frame(*args, expiry_datetimes=metadata)
    frame = surface_to_long_frame(
        *args, expiry_datetimes=metadata,
        source_grid=[["call", "missing"], ["near_atm_put_only", "near_atm_average"]],
    )
    assert frame.source.tolist() == [
        "call", "missing", "near_atm_put_only", "near_atm_average"
    ]
    pd.testing.assert_frame_equal(frame.drop(columns="source"), baseline)
    assert "source" not in baseline.columns


@pytest.mark.parametrize("sources", ["call", ["call", "put"], [["call"], ["put"]]])
def test_source_grid_rejects_mismatched_shape(sources):
    with pytest.raises(ValueError, match="source_grid shape"):
        surface_to_long_frame([[0.2, 0.3]], [0.25], [90, 110], 100,
                              source_grid=sources)


def test_chart_sources_follow_sorted_cells_and_selected_expiry():
    frame = surface_to_long_frame(
        [[0.2, np.nan, 0.22], [0.3, 0.4, 0.35]],
        [0.5, 0.25], [110, 90, 100], 100,
        source_grid=[
            ["call", "missing", "near_atm_call_only"],
            ["near_atm_put_only", "put", "near_atm_average"],
        ],
    ).sample(frac=1, random_state=7)
    heatmap = make_iv_heatmap(frame).data[0]
    assert heatmap.customdata.tolist() == [
        [[90.0, "Put"], [100.0, "Call–Put average"], [110.0, "Put only (no Call IV)"]],
        [[90.0, "No IV"], [100.0, "Call only (no Put IV)"], [110.0, "Call"]],
    ]
    assert np.isnan(heatmap.z[1, 0])
    assert heatmap.z[0].tolist() == [0.4, 0.35, 0.3]
    smile = make_smile_figure(frame, selected_expiries=[0.5]).data[0]
    assert smile.customdata.tolist() == heatmap.customdata[1].tolist()
    assert np.isnan(smile.y[0])
    assert smile.y[1:].tolist() == [0.22, 0.2]
    for trace in [heatmap, smile]:
        assert "IV from: %{customdata[1]}" in trace.hovertemplate
        assert "Strike: %{hovertext}" in trace.hovertemplate
        assert trace.connectgaps is False
    for figure in [make_iv_heatmap(_long_frame()), make_smile_figure(_long_frame())]:
        assert all("IV from:" not in trace.hovertemplate for trace in figure.data)


def test_surface_to_long_frame_aligns_and_normalizes_expiry_datetimes():
    surface = np.array([[0.20], [0.25], [np.nan]])
    expiries = [0.5, 0.25, 0.125]
    without_metadata = surface_to_long_frame(surface, expiries, [100], 100)

    with_metadata = surface_to_long_frame(
        surface,
        expiries,
        [100],
        100,
        expiry_datetimes=[
            "2026-06-30T20:00:00-04:00",
            datetime(2026, 7, 2, 8),
            None,
        ],
    )

    assert str(with_metadata["expiry_datetime"].dtype) == "datetime64[ns, UTC]"
    assert with_metadata["expiry_datetime"].tolist() == [
        pd.Timestamp("2026-07-01T00:00:00Z"),
        pd.Timestamp("2026-07-02T08:00:00Z"),
        pd.NaT,
    ]
    assert "expiry_datetime" not in without_metadata.columns
    pd.testing.assert_frame_equal(
        with_metadata.drop(columns="expiry_datetime"),
        without_metadata,
    )


def test_surface_to_long_frame_rejects_invalid_expiry_datetimes():
    with pytest.raises(ValueError, match=r"expiry_datetimes.*len\(expiries\)"):
        surface_to_long_frame(
            np.ones((2, 1)),
            [0.25, 0.5],
            [100],
            100,
            expiry_datetimes=["2026-07-01"],
        )

    with pytest.raises(ValueError, match="expiry_datetimes.*valid"):
        surface_to_long_frame(
            np.ones((1, 1)),
            [0.25],
            [100],
            100,
            expiry_datetimes=["not-a-date"],
        )


def test_surface_to_long_frame_accepts_mixed_valid_datetime_formats():
    frame = surface_to_long_frame(
        np.ones((2, 1)),
        [0.25, 0.5],
        [100],
        100,
        expiry_datetimes=["2026-07-01", "2026-07-02T08:00:00Z"],
    )

    assert frame["expiry_datetime"].tolist() == [
        pd.Timestamp("2026-07-01T00:00:00Z"),
        pd.Timestamp("2026-07-02T08:00:00Z"),
    ]


def test_atm_term_structure_selects_nearest_and_accepts_bound():
    frame = pd.DataFrame(
        {
            "tau": [0.5, 0.25, 0.25],
            "strike": [102, 94, 102],
            "iv": [0.30, 0.24, 0.20],
            "moneyness": [1.02, 0.94, 1.02],
        }
    )

    result = atm_term_structure_frame(frame)

    assert result["tau"].tolist() == [0.25, 0.5]
    assert result["strike"].tolist() == [102.0, 102.0]
    assert result["selection_status"].tolist() == ["nearest", "nearest"]
    assert np.allclose(result["atm_distance"], [0.02, 0.02])


@pytest.mark.parametrize("right_moneyness", [1.02, 1.0200000000005])
def test_atm_term_structure_averages_exact_and_near_ties(right_moneyness):
    frame = pd.DataFrame(
        {
            "tau": [0.25, 0.25],
            "strike": [98, 102],
            "iv": [0.20, 0.24],
            "moneyness": [0.98, right_moneyness],
        }
    )

    result = atm_term_structure_frame(frame).iloc[0]

    assert result["selection_status"] == "symmetric_average"
    assert result["strike"] == 100
    assert result["iv"] == pytest.approx(0.22)
    assert result["moneyness"] == pytest.approx(
        (0.98 + right_moneyness) / 2
    )


def test_atm_term_structure_carries_the_band_and_averages_tied_edges():
    frame = pd.DataFrame(
        {
            "tau": [0.25, 0.25, 0.5, 0.5, 0.75],
            "strike": [98, 102, 98, 102, 120],
            "iv": [0.20, 0.24, 0.30, 0.34, 0.40],
            "moneyness": [0.98, 1.02, 0.98, 1.02, 1.20],
            "band_low": [0.18, 0.22, np.nan, 0.32, 0.38],
            "band_high": [0.22, 0.26, 0.32, 0.36, 0.42],
        }
    )

    result = atm_term_structure_frame(frame)

    assert result["band_low"].iloc[0] == pytest.approx(0.20)
    assert result["band_high"].iloc[0] == pytest.approx(0.24)
    # An edge missing on one averaged strike stays missing.
    assert np.isnan(result["band_low"].iloc[1])
    assert result["band_high"].iloc[1] == pytest.approx(0.34)
    # Outside the 2% bound the whole point, band included, is a gap.
    assert result.iloc[2][["band_low", "band_high"]].isna().all()


def test_atm_figure_shades_the_band_beneath_the_line_only_where_both_edges_exist():
    atm = pd.DataFrame(
        {
            "tau": [0.1, 0.2, 0.3, 0.4],
            "strike": [100.0] * 4,
            "iv": [0.50, 0.45, 0.42, 0.40],
            "moneyness": [1.0] * 4,
            "atm_distance": [0.0] * 4,
            "selection_status": ["nearest"] * 4,
            "band_low": [0.48, 0.43, np.nan, 0.38],
            "band_high": [0.52, 0.47, 0.44, 0.42],
        }
    )

    figure = make_atm_term_structure_figure(atm)

    band, bars, line = figure.data
    assert band.fill == "toself" and band.showlegend
    assert line.mode == "lines+markers"
    shapes = [sorted({x for x, _ in segment}) for segment in _band_segments(band)]
    assert shapes == [[0.1, 0.2]]
    assert _band_segments(bars) == [[(0.4, 0.38), (0.4, 0.42)]]
    assert "bid–ask display band" in line.hovertemplate


def test_atm_term_structure_carries_the_combined_iv_source():
    frame = pd.DataFrame(
        {
            "tau": [0.25, 0.25, 0.5, 0.5, 0.75],
            "strike": [98, 102, 99, 101, 120],
            "iv": [0.20, 0.24, 0.30, 0.34, 0.40],
            "moneyness": [0.98, 1.02, 0.99, 1.01, 1.20],
            "source": [
                "near_atm_average", "near_atm_call_only",
                "near_atm_average", "near_atm_average", "call",
            ],
        }
    )

    result = atm_term_structure_frame(frame)

    # Averaged strikes with different labels keep both; equal labels stay one.
    assert result["source"].tolist() == [
        "near_atm_average / near_atm_call_only", "near_atm_average", "missing",
    ]


def test_atm_hover_names_the_option_behind_the_line_and_band():
    atm = pd.DataFrame(
        {
            "tau": [0.1, 0.2],
            "strike": [100.0, 100.0],
            "iv": [0.50, 0.45],
            "moneyness": [1.0, 1.0],
            "atm_distance": [0.0, 0.0],
            "selection_status": ["nearest", "symmetric_average"],
            "band_low": [0.48, 0.43],
            "band_high": [0.52, 0.47],
            "source": ["near_atm_average", "near_atm_average / near_atm_put_only"],
        }
    )

    *_, line = make_atm_term_structure_figure(atm).data

    assert "IV from: %{customdata[4]}" in line.hovertemplate
    assert "bid–ask display band of %{customdata[4]}:" in line.hovertemplate
    assert [row[4] for row in line.customdata] == [
        "Call–Put average", "Call–Put average / Put only (no Call IV)",
    ]
    np.testing.assert_allclose(
        np.asarray(line.customdata)[:, 5:7].astype(float), [[.48, .52], [.43, .47]]
    )


def test_atm_figure_without_band_columns_has_only_the_line():
    atm = atm_term_structure_frame(pd.DataFrame(
        {"tau": [0.25], "strike": [100], "iv": [0.2], "moneyness": [1.0]}
    ))
    (line,) = make_atm_term_structure_figure(atm).data
    assert "display band" not in line.hovertemplate


def test_atm_term_structure_does_not_average_distinct_distances():
    frame = pd.DataFrame(
        {
            "tau": [0.25, 0.25],
            "strike": [98, 102],
            "iv": [0.20, 0.24],
            "moneyness": [0.98, 1.020000000002],
        }
    )

    result = atm_term_structure_frame(frame).iloc[0]

    assert result["selection_status"] == "nearest"
    assert result["strike"] == 98
    assert result["iv"] == 0.20


def test_atm_term_structure_preserves_outside_bound_and_no_finite_iv():
    frame = pd.DataFrame(
        {
            "tau": [0.25, 0.5],
            "strike": [120, 100],
            "iv": [0.30, np.nan],
            "moneyness": [1.20, 1.0],
        }
    )

    result = atm_term_structure_frame(frame)
    outside = result.iloc[0]
    missing = result.iloc[1]

    assert outside["selection_status"] == "outside_bound"
    assert np.isnan(outside[["strike", "iv", "moneyness"]].astype(float)).all()
    assert outside["atm_distance"] == pytest.approx(0.20)
    assert missing["selection_status"] == "no_finite_iv"
    assert np.isnan(
        missing[["strike", "iv", "moneyness", "atm_distance"]].astype(float)
    ).all()


def test_atm_term_structure_rejects_nearest_just_outside_default_two_percent():
    frame = pd.DataFrame(
        {
            "tau": [0.25],
            "strike": [102.0000000002],
            "iv": [0.20],
            "moneyness": [1.020000000002],
        }
    )

    result = atm_term_structure_frame(frame).iloc[0]

    assert result["selection_status"] == "outside_bound"
    assert result["atm_distance"] == pytest.approx(0.020000000002)
    assert np.isnan(result["iv"])


def test_atm_term_structure_preserves_expiry_metadata_for_rejected_rows():
    long_frame = pd.DataFrame(
        {
            "tau": [0.5, 0.25, 0.125],
            "strike": [120, 100, 100],
            "iv": [0.30, np.nan, 0.20],
            "moneyness": [1.20, 1.0, 1.0],
        }
    )
    with_metadata = long_frame.assign(
        expiry_datetime=pd.to_datetime(
            [
                "2026-07-01T08:00:00Z",
                "2026-06-01T08:00:00Z",
                "2026-05-01T08:00:00Z",
            ],
            utc=True,
        )
    )

    baseline = atm_term_structure_frame(long_frame)
    result = atm_term_structure_frame(with_metadata)

    pd.testing.assert_frame_equal(
        result.drop(columns="expiry_datetime"), baseline
    )
    assert result["expiry_datetime"].tolist() == [
        pd.Timestamp("2026-05-01T08:00:00Z"),
        pd.Timestamp("2026-06-01T08:00:00Z"),
        pd.Timestamp("2026-07-01T08:00:00Z"),
    ]
    assert result["selection_status"].tolist() == [
        "nearest",
        "no_finite_iv",
        "outside_bound",
    ]


@pytest.mark.parametrize("distance", [-0.01, np.nan, np.inf, -np.inf])
def test_atm_term_structure_rejects_invalid_distance_bound(distance):
    with pytest.raises(ValueError, match="finite and non-negative"):
        atm_term_structure_frame(_long_frame(), distance)


def test_make_iv_heatmap_sorts_grid_keeps_nan_and_strike_hover():
    figure = make_iv_heatmap(_long_frame())

    assert isinstance(figure, go.Figure)
    trace = figure.data[0]
    assert isinstance(trace, go.Heatmap)
    assert trace.x.tolist() == [0.9, 1.1]
    assert trace.y.tolist() == [0.25, 0.5]
    assert np.asarray(trace.z).shape == (2, 2)
    assert np.asarray(trace.z)[0].tolist() == [0.30, 0.25]
    assert np.isnan(np.asarray(trace.z)[1, 0])
    assert np.asarray(trace.z)[1, 1] == 0.20
    assert np.asarray(trace.customdata).tolist() == [[90.0, 110.0], [90.0, 110.0]]
    assert trace.connectgaps is False
    assert "Strike" in trace.hovertemplate
    assert figure.layout.xaxis.title.text == "K / S"
    assert figure.layout.yaxis.title.text == "tau (years)"


def test_surface_heatmap_uses_equal_expiry_rows_and_value_type_hover():
    frame = _with_filled_gap(
        surface_to_long_frame(
            [[0.30, np.nan, 0.50], [0.25, 0.35, 0.45]],
            [0.25, 0.5],
            [90, 100, 110],
            100,
            expiry_datetimes=["2026-06-01", "2026-09-01"],
            source_grid=[
                ["put", "missing", "call"],
                ["put", "near_atm_average", "call"],
            ],
        )
    )

    figure = make_iv_heatmap(frame, equal_expiry_spacing=True)
    trace = figure.data[0]
    assert list(trace.y) == ["2026-06-01", "2026-09-01"]
    assert figure.layout.yaxis.title.text == "Expiry (UTC)"
    assert figure.layout.yaxis.type == "category"
    assert list(figure.layout.yaxis.categoryarray) == [
        "2026-06-01", "2026-09-01"
    ]
    assert np.asarray(trace.z)[0].tolist() == pytest.approx([0.30, 0.40, 0.50])
    assert trace.customdata[0][1].tolist() == [
        100.0, "2D linear total variance", "Interpolated"
    ]
    assert "Surface value: %{customdata[2]}" in trace.hovertemplate
    assert "Value source: %{customdata[1]}" in trace.hovertemplate
    surface = make_iv_surface_figure(frame).data[0]
    assert surface.customdata.tolist() == trace.customdata.tolist()
    assert surface.hovertemplate is None
    assert surface.hoverinfo == "text"
    assert "Value source: 2D linear total variance" in surface.text[0][1]
    # Display provenance changes must not rewrite the original quote provenance.
    assert frame.loc[frame["surface_value_type"].eq("Interpolated"), "source"].tolist() == [
        "missing"
    ]
    assert trace.customdata[0][0].tolist() == [90.0, "Put", "Observed"]

    observed_frame = frame.copy()
    observed_frame["iv"] = observed_frame["observed_iv"]
    observed_frame["surface_value_type"] = np.where(
        np.isfinite(observed_frame["observed_iv"]), "Observed", "Missing"
    )
    observed_heatmap = make_iv_heatmap(observed_frame).data[0]
    assert observed_heatmap.customdata[0][1].tolist() == [
        100.0, "No IV", "Missing"
    ]


def test_3d_surface_uses_same_values_and_true_tau_axis_as_heatmap():
    frame = _with_filled_gap(
        surface_to_long_frame(
            [[0.30, np.nan, 0.50], [0.25, 0.35, 0.45]],
            [0.25, 0.5], [90, 100, 110], 100,
            expiry_datetimes=["2026-06-01", "2026-09-01"],
        )
    )
    heatmap = make_iv_heatmap(frame, equal_expiry_spacing=True).data[0]
    surface = make_iv_surface_figure(frame)
    compact = make_iv_surface_figure(frame, compact_layout=True)
    np.testing.assert_allclose(compact.data[0].z, surface.data[0].z, equal_nan=True)
    np.testing.assert_array_equal(compact.data[0].y, surface.data[0].y)
    np.testing.assert_array_equal(compact.data[0].text, surface.data[0].text)
    assert compact.layout.height < surface.layout.height
    trace = surface.data[0]
    observed = surface.data[1]

    assert isinstance(trace, go.Surface)
    assert isinstance(observed, go.Scatter3d)
    assert trace.y.tolist() == [0.25, 0.5]
    assert np.asarray(trace.z).tolist() == np.asarray(heatmap.z).tolist()
    assert trace.connectgaps is False
    assert list(surface.layout.scene.yaxis.ticktext) == [
        "2026<br>06-01", "2026<br>09-01"
    ]
    assert surface.layout.scene.aspectratio.to_plotly_json() == {
        "x": 2.0, "y": 1.2, "z": 0.72
    }
    assert compact.layout.scene.aspectratio == surface.layout.scene.aspectratio
    assert surface.layout.scene.dragmode == "turntable"
    assert surface.layout.height == 500
    assert compact.layout.height == 340
    assert surface.layout.scene.camera.eye.to_plotly_json() == {
        "x": 1.4, "y": 1.5, "z": 0.55
    }
    assert compact.layout.scene.camera.eye.to_plotly_json() == {
        "x": 1.6, "y": 1.7, "z": 0.62
    }
    assert surface.layout.scene.camera.center.to_plotly_json() == {
        "x": 0.05, "y": -0.05, "z": -0.45
    }
    assert compact.layout.scene.camera.center.to_plotly_json() == {
        "x": 0.15, "y": -0.15, "z": -0.45
    }
    assert surface.layout.scene.domain.x == (0, 0.93)
    assert compact.layout.scene.domain.x == (0, 0.9)
    assert (trace.colorbar.x, trace.colorbar.len) == (0.94, 0.8)
    assert (compact.data[0].colorbar.x, compact.data[0].colorbar.len) == (0.92, 0.8)
    assert (surface.layout.margin.t, surface.layout.margin.b) == (10, 10)
    assert (compact.layout.margin.l, compact.layout.margin.r) == (10, 10)
    assert surface.layout.uirevision == "iv-surface-camera-v20"
    assert trace.colorbar.thickness == 18
    assert trace.lighting.ambient == 0.78
    assert "Surface value: Interpolated" in trace.text[0][1]
    assert observed.name == "Observed IV"
    assert observed.z.tolist() != pytest.approx(
        [0.30, 0.50, 0.25, 0.35, 0.45]
    )
    assert np.asarray(observed.customdata)[:, 1].astype(float).tolist() == (
        pytest.approx([0.30, 0.50, 0.25, 0.35, 0.45])
    )
    assert np.all(
        np.asarray(observed.z, dtype=float)
        > np.asarray(observed.customdata)[:, 1].astype(float)
    )
    assert observed.marker.size == 3
    assert observed.marker.color == "#F97316"
    assert observed.hovertemplate is None
    assert observed.hoverinfo == "text"
    assert "Surface value: Observed" in observed.text[0]


def test_surface_hover_text_is_aligned_on_a_nonsquare_grid():
    frame = surface_to_long_frame(
        [[.21, .22, .23, .24], [.31, .32, .33, .34]],
        [.5, .25], [110, 90, 100, 120], 100,
        source_grid=[["call", "put", "near_atm_average", "near_atm_call_only"],
                     ["call", "put", "near_atm_put_only", "call"]],
    ).sample(frac=1, random_state=4)
    trace = make_iv_surface_figure(frame).data[0]
    assert np.asarray(trace.text).shape == (2, 4)
    assert "Strike: $90<br>IV from: Put" in trace.text[0][0]
    assert "Strike: $120<br>IV from: Call" in trace.text[0][3]
    assert "Strike: $120<br>IV from: Call only (no Put IV)" in trace.text[1][3]
    assert "Time to expiry: 91.25 days" in trace.text[0][3]
    assert "IV: 34.00%" in trace.text[0][3]
    assert trace.hovertemplate is None
    assert trace.hoverinfo == "text"
    serialized = json.loads(trace.to_json())
    assert len(serialized["text"]) == 2
    assert len(serialized["text"][0]) == 4
    assert "Strike: $120" in serialized["text"][1][3]


def test_make_smile_figure_filters_and_sorts_without_changing_iv_values():
    figure = make_smile_figure(_long_frame(), selected_expiries=[0.5])

    assert isinstance(figure, go.Figure)
    assert len(figure.data) == 1
    trace = figure.data[0]
    assert trace.name == "tau=0.5"
    assert trace.x.tolist() == [0.9, 1.1]
    assert np.isnan(trace.y[0])
    assert trace.y[1] == 0.20
    assert trace.customdata.tolist() == [90.0, 110.0]
    assert trace.connectgaps is False
    assert figure.layout.yaxis.tickformat == ".0%"
    assert len(figure.layout.shapes) == 1
    assert figure.layout.shapes[0].x0 == 1.0
    assert figure.layout.shapes[0].x1 == 1.0


def test_make_smile_figure_orders_all_expiries_ascending():
    figure = make_smile_figure(_long_frame())

    assert [trace.name for trace in figure.data] == ["tau=0.25", "tau=0.5"]
    assert all(trace.connectgaps is False for trace in figure.data)


def test_smile_axis_fits_selected_observations_without_removing_gaps():
    frame = surface_to_long_frame(
        [[np.nan, .4, np.nan, .5, np.nan], [.6, np.nan, np.nan, np.nan, .7]],
        [.25, .5], [10, 90, 100, 110, 400], 100,
    )
    figure = make_smile_figure(frame, selected_expiries=[.25])
    assert list(figure.layout.xaxis.range) == pytest.approx([.89, 1.11])
    assert len(figure.data[0].x) == 5
    np.testing.assert_allclose(figure.data[0].y, frame.iloc[:5]["iv"], equal_nan=True)
    assert figure.data[0].connectgaps is False
    assert figure.layout.legend.orientation == "h"
    assert figure.layout.height == 430
    all_expiries = make_smile_figure(frame)
    selected_later = make_smile_figure(frame, selected_expiries=[.5])
    assert selected_later.data[0].line.color == all_expiries.data[1].line.color


@pytest.mark.parametrize("values", [[np.nan, np.nan], [.4, np.nan]])
def test_smile_axis_handles_missing_or_single_observation(values):
    frame = surface_to_long_frame([values], [.25], [100, 400], 100)
    figure = make_smile_figure(frame)
    expected = [.8, 1.2] if np.isnan(values).all() else [.99, 1.01]
    assert list(figure.layout.xaxis.range) == pytest.approx(expected)


def test_make_atm_term_structure_figure_keeps_gap_and_hover_fields():
    atm_frame = atm_term_structure_frame(
        pd.DataFrame(
            {
                "tau": [0.5, 0.25],
                "strike": [120, 100],
                "iv": [0.30, np.nan],
                "moneyness": [1.20, 1.0],
            }
        )
    )

    figure = make_atm_term_structure_figure(atm_frame)

    assert isinstance(figure, go.Figure)
    trace = figure.data[0]
    assert trace.x.tolist() == [0.25, 0.5]
    assert np.isnan(trace.y).all()
    assert trace.connectgaps is False
    assert np.asarray(trace.customdata).shape == (2, 4)
    assert "Time to expiry: 91.25 days" in trace.text[0]
    for label in ["IV", "Strike", "K / S", "ATM distance", "selection"]:
        assert label in trace.hovertemplate
    assert figure.layout.yaxis.tickformat == ".0%"


def test_figures_use_date_labels_and_tau_fallback_without_moving_coordinates():
    long_frame = surface_to_long_frame(
        np.array([[0.20, np.nan], [0.25, 0.30]]),
        expiries=[0.5, 0.25],
        strikes=[110, 90],
        spot_price=100,
        expiry_datetimes=["2026-07-01T08:00:00Z", None],
    )

    heatmap = make_iv_heatmap(long_frame)
    heatmap_trace = heatmap.data[0]
    assert heatmap_trace.y.tolist() == [0.25, 0.5]
    assert list(heatmap.layout.yaxis.tickvals) == [0.25, 0.5]
    assert list(heatmap.layout.yaxis.ticktext) == ["tau=0.25", "2026-07-01"]
    assert np.isnan(np.asarray(heatmap_trace.z)[1, 0])
    assert heatmap_trace.connectgaps is False

    smiles = make_smile_figure(long_frame)
    assert [trace.name for trace in smiles.data] == [
        "tau=0.25",
        "2026-07-01",
    ]
    assert [trace.meta for trace in smiles.data] == [0.25, 0.5]
    assert all("Time to expiry" in trace.text[0] for trace in smiles.data)
    assert all(trace.connectgaps is False for trace in smiles.data)

    selected = make_smile_figure(long_frame, selected_expiries=[0.5])
    assert len(selected.data) == 1
    assert selected.data[0].name == "2026-07-01"
    assert selected.data[0].x.tolist() == [0.9, 1.1]
    assert np.isnan(selected.data[0].y[0])
    assert selected.data[0].y[1] == 0.20

    atm = make_atm_term_structure_figure(atm_term_structure_frame(long_frame))
    atm_trace = atm.data[0]
    assert atm_trace.x.tolist() == [0.25, 0.5]
    assert list(atm.layout.xaxis.tickvals) == [0.25, 0.5]
    assert list(atm.layout.xaxis.ticktext) == ["tau=0.25", "2026-07-01"]
    assert np.isnan(atm_trace.y).all()
    assert atm_trace.connectgaps is False


def test_all_views_share_source_expiry_and_frozen_maturity_hover():
    frame = surface_to_long_frame(
        [[.21, .22, np.nan], [.31, .32, .33]],
        [.5, .25], [90, 100, 110], 100,
        expiry_datetimes=['2027-03-26T01:00:00-07:00', None],
    ).sample(frac=1, random_state=7)
    expected = [
        'Expiry (UTC): Unavailable<br>Time to expiry: 91.25 days',
        'Expiry (UTC): 2027-03-26<br>Time to expiry: 182.50 days',
    ]
    for categorical in [False, True]:
        trace = make_iv_heatmap(frame, equal_expiry_spacing=categorical).data[0]
        assert np.asarray(trace.text).shape == (2, 3)
        assert trace.text[:, 0].tolist() == expected
        assert '%{text}' in trace.hovertemplate
    surface = make_iv_surface_figure(frame)
    for index, maturity in enumerate(expected):
        assert all(text.startswith(maturity + '<br>') for text in surface.data[0].text[index])
    points = frame.loc[np.isfinite(frame['iv'])]
    assert all(
        text.startswith(expected[int(tau == .5)] + '<br>')
        for text, tau in zip(surface.data[1].text, points['tau'])
    )
    for trace, maturity in zip(make_smile_figure(frame).data, expected):
        assert list(trace.text) == [maturity] * 3
    atm = make_atm_term_structure_figure(atm_term_structure_frame(frame)).data[0]
    assert list(atm.text) == expected
    assert list(atm.x) == [.25, .5]


def test_surface_mesh_and_observed_markers_share_identical_hover_for_same_quote():
    frame = _with_filled_gap(surface_to_long_frame(
        [[.30, np.nan, .50], [.25, .35, .45]],
        [.25, .5], [90, 100, 110], 100,
        expiry_datetimes=['2026-06-01', '2026-09-01'],
        source_grid=[['put', 'missing', 'call'], ['put', 'near_atm_average', 'call']],
    )).sample(frac=1, random_state=6)
    surface, markers = make_iv_surface_figure(frame).data
    taus, moneyness = list(surface.y), list(surface.x)
    for x, tau, text, lifted_iv, custom in zip(
        markers.x, markers.y, markers.text, markers.z, markers.customdata,
    ):
        assert text == surface.text[taus.index(tau)][moneyness.index(x)]
        assert f'IV: {float(custom[2]):.2%}' in text
        assert lifted_iv > float(custom[2])
    assert 'Surface value: Interpolated' in surface.text[0][1]
    assert 'Value source: 2D linear total variance' in surface.text[0][1]


@pytest.mark.parametrize("with_source", [False, True])
def test_all_chart_strike_labels_preserve_fractions_and_numeric_data(with_source):
    frame = surface_to_long_frame(
        [[.20, .21], [np.nan, .22]], [.25, .5], [82000, 82000.25], 82000,
        source_grid=(
            [["near_atm_average", "call"], ["missing", "call"]]
            if with_source else None
        ),
    ).sample(frac=1, random_state=9)
    original = frame.copy(deep=True)
    labels = ["$82,000", "$82,000.25"]
    heatmap = make_iv_heatmap(frame).data[0]
    assert np.asarray(heatmap.hovertext).tolist() == [labels, labels]
    assert json.loads(heatmap.to_json())["hovertext"] == [labels, labels]
    strikes = np.asarray(heatmap.customdata)
    if with_source:
        strikes = strikes[:, :, 0]
    np.testing.assert_array_equal(strikes.astype(float), [[82000, 82000.25]] * 2)
    assert "Strike: %{hovertext}" in heatmap.hovertemplate
    for trace in make_smile_figure(frame).data:
        assert list(trace.hovertext) == labels
        assert "Strike: %{hovertext}" in trace.hovertemplate
        numeric = np.asarray(trace.customdata)
        if with_source:
            numeric = numeric[:, 0]
        np.testing.assert_array_equal(numeric.astype(float), [82000, 82000.25])
    surface, markers = make_iv_surface_figure(frame).data
    for row in surface.text:
        for label, text in zip(labels, row):
            assert f"Strike: {label}<br>" in text
    for custom, text in zip(markers.customdata, markers.text):
        label = labels[int(float(custom[0]) == 82000.25)]
        assert f"Strike: {label}<br>" in text
    atm_frame = atm_term_structure_frame(frame)
    atm = make_atm_term_structure_figure(atm_frame).data[0]
    assert list(atm.hovertext) == labels
    assert "Strike: %{hovertext}" in atm.hovertemplate
    np.testing.assert_array_equal(np.asarray(atm.customdata)[:, 0].astype(float),
                                  [82000, 82000.25])
    assert np.isnan(heatmap.z[1, 0])
    pd.testing.assert_frame_equal(frame, original)


def test_iv_hovers_use_reader_words():
    frame = surface_to_long_frame(
        [[.21, .22, .23], [.31, .32, .33]],
        [.5, .25], [81_000, 82_000, 83_500.5], 82_000,
        source_grid=[["put", "near_atm_average", "near_atm_call_only"],
                     ["near_atm_put_only", "near_atm_call_only", "missing"]],
        expiry_datetimes=["2027-03-26T08:00:00Z", "2026-12-25T08:00:00Z"],
    )
    smile = make_smile_figure(frame, selected_expiries=[.25]).data[0]
    assert list(smile.hovertext) == ["$81,000", "$82,000", "$83,500.5"]
    assert "Strike: %{hovertext}" in smile.hovertemplate
    assert smile.customdata[:, 1].tolist() == [
        "Put only (no Call IV)", "Call only (no Put IV)", "No IV",
    ]
    assert smile.text[0] == "Expiry (UTC): 2026-12-25<br>Time to expiry: 91.25 days"
    heatmap = make_iv_heatmap(frame).data[0]
    assert heatmap.customdata[1, :, 1].tolist() == [
        "Put", "Call–Put average", "Call only (no Put IV)",
    ]
    surface = make_iv_surface_figure(frame).data[0]
    texts = " ".join(np.asarray(surface.text).reshape(-1))
    for code in ["near_atm", "fallback", "tau"]:
        assert code not in texts
    assert "Strike: $83,500.5" in texts
    atm = make_atm_term_structure_figure(atm_term_structure_frame(frame)).data[0]
    assert "tau" not in " ".join(atm.text)


def _band_segments(trace):
    """Split a band polygon trace into its closed shapes at the gaps."""
    segments, current = [], []
    for x, y in zip(trace.x, trace.y):
        if x is None or y is None or not np.isfinite(x) or not np.isfinite(y):
            if current:
                segments.append(current)
            current = []
        else:
            current.append((x, y))
    if current:
        segments.append(current)
    return segments


def test_smile_band_shades_only_strikes_with_both_edges():
    # Ask edges at every strike; bid edges missing at 1.0 and 1.3 (the 2026-10-16 case).
    frame = surface_to_long_frame(
        [[.50, .45, .40, .42, .44]], [.25], [90, 100, 110, 120, 130], 100,
    ).assign(
        band_low=[.48, np.nan, .38, .40, np.nan],
        band_high=[.52, .47, .42, .44, .46],
    )
    figure = make_smile_figure(frame)
    band, bars = [trace for trace in figure.data if trace.mode != "lines+markers"]
    assert band.fill == "toself"
    shapes = [sorted({x for x, _ in segment}) for segment in _band_segments(band)]
    assert shapes == [[pytest.approx(1.1), pytest.approx(1.2)]]
    upper_and_lower = sorted(y for _, y in _band_segments(band)[0])
    assert upper_and_lower == pytest.approx([.38, .40, .42, .44])
    # 0.9 has both edges but no neighbour with them: a bar, not a zero-width shape.
    assert _band_segments(bars) == [
        [(pytest.approx(0.9), .48), (pytest.approx(0.9), .52)]
    ]
    assert bars.fill != "toself" and bars.legendgroup == band.legendgroup
