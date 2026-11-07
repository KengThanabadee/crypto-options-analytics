import numpy as np
import pandas as pd
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import QhullError


# Moneyness ranges by name, with (low, high) K/S bounds; All listed has none
# and spans the snapshot's lowest to highest listed K/S.
ALL_LISTED = "All listed"
MONEYNESS_RANGES = {
    "Core": (0.8, 1.2),
    "Wide": (0.5, 2.0),
    ALL_LISTED: None,
}
DEFAULT_MONEYNESS_RANGE = "Wide"
# Strike–time scale of the 2D fill: 1 year of tau counts as 8 K/S units, for
# every range and snapshot. Leave-one-out refill error on the frozen snapshot
# stops improving from 8 upward; at 8, K/S 0.01 apart is as close as expiries
# about half a day apart, so gaps borrow from their own expiry first.
STRIKE_TIME_SCALE = 8.0
# IV chart view choices; the dashboard and saved analyses share them.
HEATMAP_VALUES = ("Surface", "Observed")
SURFACE_VIEWS = ("Heatmap", "3D")

_LONG_FRAME_COLUMNS = {"tau", "strike", "iv", "moneyness"}
_ATM_TOLERANCE = 1e-12
_SURFACE_VALUE_TYPES = {
    "observed": "Observed",
    "missing": "Missing",
}


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame")

    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{name} is missing required columns: {missing}")


def _normalize_expiry_datetimes(
    expiry_datetimes, expiry_count: int
) -> pd.Series | None:
    if expiry_datetimes is None:
        return None

    try:
        values = list(expiry_datetimes)
    except TypeError as exc:
        raise ValueError(
            "expiry_datetimes must contain len(expiries) values"
        ) from exc
    if len(values) != expiry_count:
        raise ValueError("expiry_datetimes must contain len(expiries) values")

    try:
        normalized = pd.to_datetime(
            values, utc=True, errors="raise", format="mixed"
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            "expiry_datetimes must contain valid datetime values"
        ) from exc
    return pd.Series(normalized, dtype="datetime64[ns, UTC]")


def surface_to_long_frame(
    iv_surface, expiries, strikes, spot_price, expiry_datetimes=None,
    source_grid=None,
) -> pd.DataFrame:
    """Convert an expiry-by-strike IV grid to chart-ready long-form data.

    Optional source_grid labels must align with iv_surface and are preserved
    unchanged in a source column, including labels for missing IV cells.
    """
    try:
        surface = np.asarray(iv_surface, dtype=float)
        expiry_values = np.asarray(list(expiries), dtype=float)
        strike_values = np.asarray(list(strikes), dtype=float)
        spot_value = float(spot_price)
    except (TypeError, ValueError) as exc:
        raise ValueError("surface inputs must be numeric") from exc

    expected_shape = (len(expiry_values), len(strike_values))
    if surface.ndim != 2 or surface.shape != expected_shape:
        raise ValueError(
            "iv_surface shape must equal (len(expiries), len(strikes))"
        )
    if not np.isfinite(spot_value) or spot_value <= 0:
        raise ValueError("spot_price must be finite and positive")

    expiry_datetime_values = _normalize_expiry_datetimes(
        expiry_datetimes, len(expiry_values)
    )
    tau = np.repeat(expiry_values, len(strike_values))
    strike = np.tile(strike_values, len(expiry_values))
    data = {"tau": tau}
    if expiry_datetime_values is not None:
        data["expiry_datetime"] = expiry_datetime_values.repeat(
            len(strike_values)
        ).reset_index(drop=True)
    data.update(
        {
            "strike": strike,
            "iv": surface.reshape(-1),
            "spot_price": spot_value,
            "moneyness": strike / spot_value,
        }
    )
    if source_grid is not None:
        sources = np.asarray(source_grid, dtype=object)
        if sources.shape != surface.shape:
            raise ValueError("source_grid shape must equal iv_surface shape")
        data["source"] = sources.reshape(-1)
    return pd.DataFrame(data)


def interpolate_surface_2d(long_frame: pd.DataFrame) -> pd.DataFrame:
    """Fill every missing cell of the frame by piecewise-linear total variance.

    One surface per snapshot and IV source: every original finite IV
    (observed_iv when present) supports the fill, whatever range is viewed;
    ``moneyness_range_slice`` then picks a range. Interpolate w = IV**2 * tau
    on (K/S, tau * STRIKE_TIME_SCALE), then recover IV = sqrt(w/tau).

    Observations, quote provenance, metadata, row order and index are preserved.
    Outside the observed convex hull, or without non-collinear 2D support,
    missing cells remain NaN. This operation creates no additional grid cells.
    """
    _require_columns(long_frame, _LONG_FRAME_COLUMNS, "long_frame")
    coordinates = long_frame[["moneyness", "tau"]].to_numpy(dtype=float)
    if not np.isfinite(coordinates).all() or (coordinates <= 0).any():
        raise ValueError("moneyness and tau must be finite and positive")
    if long_frame.duplicated(["tau", "moneyness"]).any():
        raise ValueError("long_frame must have unique tau and moneyness cells")

    frame = long_frame.copy()
    original_index = frame.index
    frame = frame.reset_index(drop=True)
    observed_column = "observed_iv" if "observed_iv" in frame else "iv"
    observed = frame[observed_column].to_numpy(dtype=float)
    finite = np.isfinite(observed)
    if (observed[finite] < 0).any():
        raise ValueError("observed IV must be non-negative")
    observed = np.where(finite, observed, np.nan)
    frame["observed_iv"] = observed
    frame["iv"] = observed
    frame["surface_value_type"] = np.where(
        finite, _SURFACE_VALUE_TYPES["observed"], _SURFACE_VALUE_TYPES["missing"]
    )
    frame["interpolation_method"] = pd.Series(None, index=frame.index, dtype=object)

    def finish():
        frame.index = original_index
        return frame

    if finite.sum() < 3 or finite.all():
        return finish()

    points = frame[["moneyness", "tau"]].to_numpy(dtype=float)
    scaled = points * [1.0, STRIKE_TIME_SCALE]
    support = scaled[finite]
    if np.linalg.matrix_rank(support - support[0]) < 2:
        return finish()
    total_variance = observed[finite] ** 2 * points[finite, 1]
    if not np.isfinite(total_variance).all():
        raise ValueError("observed total variance must be finite")
    try:
        interpolator = LinearNDInterpolator(support, total_variance)
    except QhullError:
        # Degenerate support cannot define a stable 2D triangulation.
        return finish()
    targets = np.flatnonzero(~finite)
    variance = interpolator(scaled[targets])
    supported = np.isfinite(variance) & (variance >= 0)
    targets = targets[supported]
    recovered = np.sqrt(variance[supported] / points[targets, 1])
    valid = np.isfinite(recovered)
    targets = targets[valid]
    frame.loc[targets, "iv"] = recovered[valid]
    frame.loc[targets, "surface_value_type"] = "Interpolated"
    frame.loc[targets, "interpolation_method"] = "2D linear total variance"
    return finish()


def moneyness_range_label(range_name: str) -> str:
    """The range's name with its fixed bounds, e.g. "Wide (0.5–2.0)"."""
    bounds = MONEYNESS_RANGES[range_name]
    if bounds is None:
        return range_name
    return f"{range_name} ({bounds[0]:.1f}–{bounds[1]:.1f})"


def resolve_moneyness_range(moneyness_range, frame: pd.DataFrame) -> tuple[float, float]:
    """The (low, high) K/S of a range name, or of a (low, high) pair.

    All listed spans the lowest to highest K/S of the frame's grid.
    """
    if isinstance(moneyness_range, str):
        if moneyness_range not in MONEYNESS_RANGES:
            raise ValueError(f"Unknown moneyness range: {moneyness_range!r}")
        moneyness_range = MONEYNESS_RANGES[moneyness_range]
    if moneyness_range is None:
        _require_columns(frame, {"moneyness"}, "frame")
        return float(frame["moneyness"].min()), float(frame["moneyness"].max())
    low, high = moneyness_range
    return float(low), float(high)


def moneyness_range_surface(
    long_frame: pd.DataFrame, moneyness_range
) -> tuple[pd.DataFrame, tuple[float, float]]:
    """The surface filled from every observation, sliced to a range.

    ``moneyness_range`` is a range name or a (low, high) pair; the resolved
    bounds are returned with the slice.
    """
    surface = interpolate_surface_2d(long_frame)
    bounds = resolve_moneyness_range(moneyness_range, surface)
    return moneyness_range_slice(surface, *bounds), bounds


def moneyness_range_slice(
    surface_frame: pd.DataFrame, min_moneyness: float, max_moneyness: float
) -> pd.DataFrame:
    """Keep the cells whose K/S lies inside the inclusive bounds, unchanged."""
    _require_columns(surface_frame, {"moneyness"}, "surface_frame")
    try:
        lower, upper = float(min_moneyness), float(max_moneyness)
    except (TypeError, ValueError) as exc:
        raise ValueError("moneyness bounds must be finite with min < max") from exc
    if not np.isfinite([lower, upper]).all() or lower >= upper:
        raise ValueError("moneyness bounds must be finite with min < max")
    return surface_frame[surface_frame.moneyness.between(lower, upper)].copy()


def observed_surface_frame(surface_frame: pd.DataFrame) -> pd.DataFrame:
    """Return a surface frame showing only observed IV, without interpolation.

    ``iv`` becomes ``observed_iv`` and each cell is Observed or Missing; every
    other column is kept. The input frame is not changed.
    """
    _require_columns(surface_frame, {"observed_iv"}, "surface_frame")
    frame = surface_frame.copy()
    frame["iv"] = frame["observed_iv"]
    frame["surface_value_type"] = np.where(
        np.isfinite(frame["observed_iv"]),
        _SURFACE_VALUE_TYPES["observed"],
        _SURFACE_VALUE_TYPES["missing"],
    )
    return frame


def atm_term_structure_frame(
    long_frame: pd.DataFrame, max_moneyness_distance: float = 0.02
) -> pd.DataFrame:
    """Select a bounded, transparent ATM proxy independently for each expiry.

    When the frame has band_low/band_high columns, the chosen strikes' band
    edges come along, averaged like IV; an edge missing on any averaged
    strike stays missing. A ``source`` column comes along too: the chosen
    strikes' Combined IV labels, joined with " / " when averaged strikes
    differ.
    """
    _require_columns(long_frame, _LONG_FRAME_COLUMNS, "long_frame")
    band_columns = [
        column for column in ("band_low", "band_high")
        if column in long_frame.columns
    ]
    no_band = {column: np.nan for column in band_columns}
    has_source = "source" in long_frame.columns
    if has_source:
        no_band["source"] = "missing"

    try:
        distance_bound = float(max_moneyness_distance)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "max_moneyness_distance must be finite and non-negative"
        ) from exc
    if not np.isfinite(distance_bound) or distance_bound < 0:
        raise ValueError("max_moneyness_distance must be finite and non-negative")

    has_expiry_metadata = "expiry_datetime" in long_frame.columns
    rows = []
    for tau, expiry_frame in long_frame.groupby("tau", sort=True, dropna=False):
        metadata = (
            {"expiry_datetime": expiry_frame["expiry_datetime"].iloc[0]}
            if has_expiry_metadata
            else {}
        )
        iv = expiry_frame["iv"].to_numpy(dtype=float)
        moneyness = expiry_frame["moneyness"].to_numpy(dtype=float)
        finite = np.isfinite(iv) & np.isfinite(moneyness)

        if not finite.any():
            rows.append(
                {
                    "tau": tau,
                    **metadata,
                    "strike": np.nan,
                    "iv": np.nan,
                    "moneyness": np.nan,
                    "atm_distance": np.nan,
                    "selection_status": "no_finite_iv",
                    **no_band,
                }
            )
            continue

        candidates = expiry_frame.loc[finite].copy()
        candidates["atm_distance"] = np.abs(candidates["moneyness"] - 1.0)
        minimum_distance = float(candidates["atm_distance"].min())
        within_bound = minimum_distance < distance_bound or np.isclose(
            minimum_distance,
            distance_bound,
            atol=_ATM_TOLERANCE,
            rtol=0,
        )

        if not within_bound:
            rows.append(
                {
                    "tau": tau,
                    **metadata,
                    "strike": np.nan,
                    "iv": np.nan,
                    "moneyness": np.nan,
                    "atm_distance": minimum_distance,
                    "selection_status": "outside_bound",
                    **no_band,
                }
            )
            continue

        tied = candidates[
            np.isclose(
                candidates["atm_distance"],
                minimum_distance,
                atol=_ATM_TOLERANCE,
                rtol=0,
            )
        ]
        rows.append(
            {
                "tau": tau,
                **metadata,
                "strike": float(tied["strike"].mean()),
                "iv": float(tied["iv"].mean()),
                "moneyness": float(tied["moneyness"].mean()),
                "atm_distance": minimum_distance,
                "selection_status": (
                    "symmetric_average" if len(tied) > 1 else "nearest"
                ),
                **{
                    column: float(tied[column].to_numpy(dtype=float).mean())
                    for column in band_columns
                },
                **(
                    {"source": " / ".join(dict.fromkeys(tied["source"]))}
                    if has_source else {}
                ),
            }
        )

    columns = ["tau"]
    if has_expiry_metadata:
        columns.append("expiry_datetime")
    columns.extend(
        [
            "strike",
            "iv",
            "moneyness",
            "atm_distance",
            "selection_status",
            *band_columns,
            *(["source"] if has_source else []),
        ]
    )
    return pd.DataFrame(rows, columns=columns)
