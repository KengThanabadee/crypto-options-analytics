import numpy as np
import pandas as pd
import pytest

from options_analytics.surface_transforms import (
    interpolate_surface_2d,
    moneyness_range_slice,
    observed_surface_frame,
    surface_to_long_frame,
)


def _frame():
    frame = surface_to_long_frame(
        [[.3, np.nan, .5], [np.nan, np.nan, np.nan], [.4, np.nan, .6]],
        [.1, .2, .3], [90, 100, 110], 100,
        expiry_datetimes=["2026-06-01", "2026-07-01", "2026-08-01"],
        source_grid=[["put", "missing", "call"], ["missing"] * 3,
                     ["put", "missing", "call"]],
    )
    # Affine total variance has an exact, unambiguous interpolated value.
    finite = frame.iv.notna()
    frame.loc[finite, "iv"] = np.sqrt(
        (.02 + .01 * frame.loc[finite, "moneyness"]
         + .03 * frame.loc[finite, "tau"]) / frame.loc[finite, "tau"]
    )
    return frame


def test_total_variance_is_linear_across_both_axes_and_preserves_inputs():
    frame = _frame()
    original = frame.copy(deep=True)
    result = interpolate_surface_2d(frame)
    expected = np.sqrt((.02 + .01 * frame.moneyness + .03 * frame.tau) / frame.tau)
    np.testing.assert_allclose(result.iv, expected)
    np.testing.assert_array_equal(result.iv[frame.iv.notna()], frame.iv.dropna())
    pd.testing.assert_series_equal(result.observed_iv, frame.iv, check_names=False)
    assert (result.surface_value_type == "Observed").sum() == 4
    assert (result.surface_value_type == "Interpolated").sum() == 5
    assert result.loc[result.surface_value_type.eq("Interpolated"),
                      "interpolation_method"].eq("2D linear total variance").all()
    pd.testing.assert_series_equal(result.source, frame.source)
    pd.testing.assert_series_equal(result.expiry_datetime, frame.expiry_datetime)
    pd.testing.assert_frame_equal(frame, original)


def test_observed_frame_shows_only_observed_iv_and_leaves_the_surface_unchanged():
    surface = interpolate_surface_2d(_frame())
    original = surface.copy(deep=True)
    observed = observed_surface_frame(surface)
    expected = _frame().iv
    np.testing.assert_array_equal(observed.iv, expected)
    assert observed.loc[expected.notna(), "surface_value_type"].eq("Observed").all()
    assert observed.loc[expected.isna(), "surface_value_type"].eq("Missing").all()
    assert (observed.surface_value_type == "Missing").sum() == 5
    pd.testing.assert_frame_equal(
        observed.drop(columns=["iv", "surface_value_type"]),
        surface.drop(columns=["iv", "surface_value_type"]),
    )
    pd.testing.assert_frame_equal(surface, original)


def test_2d_preserves_duplicate_row_labels_and_shuffled_order():
    frame = _frame().sample(frac=1, random_state=4)
    frame.index = pd.Index([0, 1, 2] * 3, name="input_row")
    result = interpolate_surface_2d(frame)
    pd.testing.assert_index_equal(result.index, frame.index)
    pd.testing.assert_frame_equal(result[frame.columns.drop("iv")], frame.drop(columns="iv"))
    expected = np.sqrt((.02 + .01 * frame.moneyness + .03 * frame.tau) / frame.tau)
    np.testing.assert_allclose(result.iv, expected)


def test_2d_leaves_outside_convex_hull_missing():
    extra = pd.DataFrame({"tau": [.05, .4, .2, .2], "strike": [100, 100, 80, 120],
                          "moneyness": [1., 1., .8, 1.2], "iv": [np.nan] * 4})
    frame = pd.concat([_frame(), extra], ignore_index=True)
    result = interpolate_surface_2d(frame)
    assert result.iloc[-4:].iv.isna().all()
    assert result.iloc[-4:].surface_value_type.eq("Missing").all()


def _plane_frame(strikes):
    taus = [.1, .3]
    grid = np.full((2, len(strikes)), np.nan)
    frame = surface_to_long_frame(grid, taus, strikes, 100)
    frame["iv"] = np.sqrt(
        (.02 + .01 * frame.moneyness + .03 * frame.tau) / frame.tau
    )
    return frame


def test_range_slice_keeps_inclusive_bounds_and_the_cell_values():
    frame = _plane_frame([60, 70, 80, 90, 100, 110, 120, 130])
    frame.loc[frame.moneyness.isin([.8, 1.]), "iv"] = np.nan
    surface = interpolate_surface_2d(frame)
    core = moneyness_range_slice(surface, .8, 1.2)
    extended = moneyness_range_slice(surface, .7, 1.3)
    assert core.moneyness.between(.8, 1.2).all()
    assert sorted(core.moneyness.unique()) == pytest.approx([.8, .9, 1., 1.1, 1.2])
    assert len(extended) == 14
    pd.testing.assert_frame_equal(core, extended.loc[core.index])
    pd.testing.assert_frame_equal(core, surface.loc[core.index])


def test_gap_at_a_range_edge_is_filled_from_an_observation_outside_the_range():
    frame = _plane_frame([70, 80, 90, 100])
    frame.loc[frame.moneyness.eq(.8), "iv"] = np.nan
    core = moneyness_range_slice(interpolate_surface_2d(frame), .8, 1.2)
    edge = core[core.moneyness.eq(.8)]
    assert edge.surface_value_type.eq("Interpolated").all()
    np.testing.assert_allclose(
        edge.iv, np.sqrt((.02 + .01 * .8 + .03 * edge.tau) / edge.tau)
    )


@pytest.mark.parametrize("case", ["empty", "missing", "one", "collinear"])
def test_2d_insufficient_support_returns_observed_and_missing(case):
    frame = _frame()
    if case == "empty":
        frame = frame.iloc[:0]
    elif case == "missing":
        frame.iv = np.nan
    elif case == "one":
        frame.loc[frame.index[1:], "iv"] = np.nan
    else:
        frame = frame[frame.tau.eq(.1)]
    result = interpolate_surface_2d(frame)
    np.testing.assert_allclose(result.iv, frame.iv, equal_nan=True)
    assert not result.surface_value_type.eq("Interpolated").any()


def test_2d_uses_original_observations_when_called_on_display_frame():
    first = interpolate_surface_2d(_frame())
    first.loc[first.surface_value_type.eq("Interpolated"), "iv"] = 99.
    second = interpolate_surface_2d(first)
    expected = interpolate_surface_2d(_frame())
    pd.testing.assert_frame_equal(second, expected)


@pytest.mark.parametrize("bounds", [(1., 1.), (1.2, .8), (np.nan, 1.2), (.8, np.inf)])
def test_range_slice_rejects_bad_bounds(bounds):
    with pytest.raises(ValueError, match="moneyness bounds"):
        moneyness_range_slice(interpolate_surface_2d(_frame()), *bounds)


@pytest.mark.parametrize("column,value", [("tau", 0), ("tau", -1), ("tau", np.nan),
                                          ("moneyness", np.inf), ("moneyness", 0),
                                          ("iv", -.1)])
def test_2d_rejects_invalid_coordinates_and_negative_iv(column, value):
    frame = _frame()
    frame.loc[0, column] = value
    with pytest.raises(ValueError):
        interpolate_surface_2d(frame)


def test_2d_rejects_duplicate_cells_and_missing_columns():
    with pytest.raises(ValueError, match="unique tau and moneyness"):
        interpolate_surface_2d(pd.concat([_frame(), _frame().iloc[[0]]]))
    with pytest.raises(ValueError, match="missing required columns"):
        interpolate_surface_2d(_frame().drop(columns="tau"))


@pytest.mark.parametrize("with_source", [True, False])
def test_2d_shows_correct_method_in_both_figures(with_source):
    from options_analytics.visualization import make_iv_heatmap, make_iv_surface_figure

    frame = interpolate_surface_2d(_frame())
    if not with_source:
        frame = frame.drop(columns="source")
    heatmap = make_iv_heatmap(frame).data[0]
    surface = make_iv_surface_figure(frame)
    np.testing.assert_allclose(heatmap.z, surface.data[0].z)
    assert heatmap.customdata[1][1].tolist() == [
        100., "2D linear total variance", "Interpolated"
    ]
    assert surface.data[0].customdata.tolist() == heatmap.customdata.tolist()
    assert heatmap.customdata[0][0].tolist() == [
        90., "Put" if with_source else "Observed IV", "Observed"
    ]
    assert len(surface.data[1].x) == 4
    assert heatmap.connectgaps is False
    assert surface.data[0].connectgaps is False


def test_2d_gap_between_strikes_of_one_expiry_borrows_from_that_expiry():
    # Expiries a week apart: at 1 year of tau = 8 K/S units, the neighbouring
    # strikes 0.01 away are far closer than the neighbouring expiries.
    taus = [.04, .06, .08, 1.]
    strikes = [80, 99, 100, 101, 120]
    grid = np.full((4, 5), .3)
    grid[1] = .5
    grid[1, 2] = np.nan
    result = interpolate_surface_2d(surface_to_long_frame(grid, taus, strikes, 100))
    gap = result.tau.eq(.06) & result.moneyness.eq(1.)
    assert result.loc[gap, "surface_value_type"].item() == "Interpolated"
    assert result.loc[gap, "iv"].item() == pytest.approx(.5)
