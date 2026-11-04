from html import escape

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from options_analytics.chain import DAYS_PER_YEAR
from options_analytics.positioning import GEX_MODES, strikes_in_range


_LONG_FRAME_COLUMNS = {"tau", "strike", "iv", "moneyness"}
_ATM_FRAME_COLUMNS = {
    "tau",
    "strike",
    "iv",
    "moneyness",
    "atm_distance",
    "selection_status",
}


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame")

    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{name} is missing required columns: {missing}")


def _format_expiry_label(tau, expiry_datetime=pd.NaT) -> str:
    if pd.isna(expiry_datetime):
        return f"tau={tau:g}"

    timestamp = pd.Timestamp(expiry_datetime)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.strftime("%Y-%m-%d")


def _expiry_labels(frame: pd.DataFrame, taus) -> list[str]:
    labels = []
    has_metadata = "expiry_datetime" in frame.columns
    for tau in taus:
        expiry_datetime = pd.NaT
        if has_metadata:
            values = frame.loc[
                frame["tau"] == tau, "expiry_datetime"
            ].dropna()
            if not values.empty:
                expiry_datetime = values.iloc[0]
        labels.append(_format_expiry_label(tau, expiry_datetime))
    return labels


def _spaced_tau_ticks(taus, minimum_spacing_fraction=0.08):
    values = np.asarray(taus, dtype=float)
    if len(values) <= 2:
        return values

    spacing = (values.max() - values.min()) * minimum_spacing_fraction
    visible = [0]
    for index in range(1, len(values)):
        if values[index] - values[visible[-1]] >= spacing:
            visible.append(index)
    if visible[-1] != len(values) - 1:
        visible.append(len(values) - 1)
    return values[visible]


def _maturity_hover(frame, taus):
    """Format source expiry and frozen maturity consistently across charts."""
    return [
        f"Expiry (UTC): {label if not label.startswith('tau=') else 'Unavailable'}<br>"
        f"Time to expiry: {float(tau) * DAYS_PER_YEAR:.2f} days"
        for tau, label in zip(taus, _expiry_labels(frame, taus))
    ]


def _format_strike(strike):
    """USD with thousands separators, keeping fractional strikes: '$83,500.5'."""
    if not np.isfinite(float(strike)):
        return "Unavailable"
    whole, _, fraction = np.format_float_positional(float(strike), trim="-").partition(".")
    return f"${int(whole):,}" + (f".{fraction}" if fraction else "")


# Combined IV source codes in reader words; other values (interpolation
# methods) already read as text and pass through.
SOURCE_LABELS = {
    "call": "Call",
    "put": "Put",
    "near_atm_average": "Call–Put average",
    "near_atm_call_only": "Call only (no Put IV)",
    "near_atm_put_only": "Put only (no Call IV)",
    "call_fallback": "Call (no Put IV)",
    "put_fallback": "Put (no Call IV)",
    "missing": "No IV",
}


def _source_label(source):
    return SOURCE_LABELS.get(source, source)


def _iv_label(iv_source=None):
    """Name the IV source in hover, e.g. 'Exchange mark IV'."""
    return "IV" if iv_source is None else f"{escape(str(iv_source))} IV"


def _surface_hover_text(
    maturity, moneyness, strike, iv, *,
    source_label=None, source=None, value_type=None, iv_label="IV",
):
    parts = [maturity, f"K / S: {moneyness:.4f}", f"Strike: {_format_strike(strike)}"]
    if source_label is not None:
        parts.append(f"{source_label}: {escape(str(_source_label(source)))}")
    if value_type is not None:
        parts.append(f"Surface value: {escape(str(value_type))}")
    parts.append(f"{iv_label}: {iv:.2%}")
    return "<br>".join(parts)


def _heatmap_customdata(long_frame, iv_grid, strike_grid):
    customdata = strike_grid.to_numpy(dtype=float)
    strike_hover = "Strike: %{hovertext}<br>"
    source_hover = ""
    value_type_hover = ""

    has_source = (
        "source" in long_frame.columns or "interpolation_method" in long_frame.columns
    )
    has_value_type = "surface_value_type" in long_frame.columns
    if not has_source and not has_value_type:
        return customdata, strike_hover, source_hover, value_type_hover

    fields = [customdata]
    if has_source:
        display_source = (
            long_frame["source"].copy()
            if "source" in long_frame.columns
            else pd.Series("Observed IV", index=long_frame.index).mask(
                long_frame["surface_value_type"].eq("Missing"), "missing"
            )
        )
        if has_value_type and "interpolation_method" in long_frame.columns:
            display_source = display_source.mask(
                long_frame["surface_value_type"].eq("Interpolated"),
                long_frame["interpolation_method"],
            )
        source_grid = long_frame.assign(source=display_source.map(_source_label)).pivot(
            index="tau", columns="moneyness", values="source"
        ).reindex(index=iv_grid.index, columns=iv_grid.columns)
        fields.append(source_grid.to_numpy())
    if has_value_type:
        value_type_grid = long_frame.pivot(
            index="tau", columns="moneyness", values="surface_value_type"
        ).reindex(index=iv_grid.index, columns=iv_grid.columns)
        fields.append(value_type_grid.to_numpy())

    combined = np.empty((*iv_grid.shape, len(fields)), dtype=object)
    for index, values in enumerate(fields):
        combined[:, :, index] = values

    customdata = combined
    next_index = 1
    if has_source:
        source_label = "Value source" if has_value_type else "IV from"
        source_hover = f"{source_label}: %{{customdata[{next_index}]}}<br>"
        next_index += 1
    if has_value_type:
        value_type_hover = f"Surface value: %{{customdata[{next_index}]}}<br>"
    return customdata, strike_hover, source_hover, value_type_hover


def make_iv_heatmap(
    long_frame: pd.DataFrame, *, equal_expiry_spacing: bool = False,
    iv_source=None,
) -> go.Figure:
    """Create a moneyness-by-expiry heatmap without filling IV itself."""
    _require_columns(long_frame, _LONG_FRAME_COLUMNS, "long_frame")

    iv_grid = (
        long_frame.pivot(index="tau", columns="moneyness", values="iv")
        .sort_index(axis=0)
        .sort_index(axis=1)
    )
    strike_grid = (
        long_frame.pivot(index="tau", columns="moneyness", values="strike")
        .reindex(index=iv_grid.index, columns=iv_grid.columns)
    )

    customdata, strike_hover, source_hover, value_type_hover = (
        _heatmap_customdata(long_frame, iv_grid, strike_grid)
    )
    expiry_labels = _expiry_labels(long_frame, iv_grid.index)
    y_values = expiry_labels if equal_expiry_spacing else iv_grid.index.to_numpy(
        dtype=float
    )
    maturity_text = np.repeat(
        np.asarray(_maturity_hover(long_frame, iv_grid.index), dtype=object)[:, None],
        len(iv_grid.columns), axis=1,
    )

    trace = go.Heatmap(
        x=iv_grid.columns.to_numpy(dtype=float),
        y=y_values,
        z=iv_grid.to_numpy(dtype=float),
        customdata=customdata,
        text=maturity_text,
        hovertext=np.asarray([
            [_format_strike(strike) for strike in row]
            for row in strike_grid.to_numpy(dtype=float)
        ], dtype=object),
        connectgaps=False,
        xgap=1,
        ygap=1,
        colorbar={
            "title": {"text": "IV", "side": "top"},
            "tickformat": ".0%",
            "thickness": 14,
            "xpad": 8,
        },
        hovertemplate=(
            "%{text}<br>"
            "K / S: %{x:.4f}<br>"
            + strike_hover
            + source_hover
            + value_type_hover
            + f"{_iv_label(iv_source)}: %{{z:.2%}}<extra></extra>"
        ),
        colorscale="Viridis",
    )
    figure = go.Figure(data=[trace])
    figure.update_layout(
        xaxis_title="K / S",
        yaxis_title="Expiry (UTC)" if equal_expiry_spacing else "tau (years)",
        plot_bgcolor="rgba(128, 128, 128, 0.18)",
        height=430,
        margin={"l": 12, "r": 12, "t": 24, "b": 12},
    )
    if equal_expiry_spacing:
        figure.update_yaxes(
            type="category",
            categoryorder="array",
            categoryarray=expiry_labels,
        )
    else:
        figure.update_yaxes(
            tickmode="array",
            tickvals=iv_grid.index.to_numpy(dtype=float),
            ticktext=expiry_labels,
        )
    return figure


def make_iv_surface_figure(
    long_frame: pd.DataFrame, *, compact_layout: bool = False, iv_source=None,
) -> go.Figure:
    """Create a 3D IV surface from the same rectangular frame as the heatmap."""
    _require_columns(long_frame, _LONG_FRAME_COLUMNS, "long_frame")

    iv_grid = (
        long_frame.pivot(index="tau", columns="moneyness", values="iv")
        .sort_index(axis=0)
        .sort_index(axis=1)
    )
    strike_grid = (
        long_frame.pivot(index="tau", columns="moneyness", values="strike")
        .reindex(index=iv_grid.index, columns=iv_grid.columns)
    )
    customdata, strike_hover, source_hover, value_type_hover = (
        _heatmap_customdata(long_frame, iv_grid, strike_grid)
    )
    visible_taus = _spaced_tau_ticks(
        iv_grid.index, minimum_spacing_fraction=0.30 if compact_layout else 0.18
    )
    maturity_text = _maturity_hover(long_frame, iv_grid.index)
    # Surface hover handles its native 2D text grid reliably. Keep customdata
    # for inspection, but avoid renderer-dependent compound-array indexing.
    hover_text = []
    for row_index, row in enumerate(customdata):
        text_row = []
        for column_index, cell in enumerate(row):
            values = cell if customdata.ndim == 3 else [cell]
            field = 1
            source_label = None
            source = None
            if source_hover:
                source_label = "Value source" if value_type_hover else "IV from"
                source = values[field]
                field += 1
            text_row.append(_surface_hover_text(
                maturity_text[row_index], iv_grid.columns[column_index],
                values[0], iv_grid.iloc[row_index, column_index],
                source_label=source_label, source=source,
                value_type=values[field] if value_type_hover else None,
                iv_label=_iv_label(iv_source),
            ))
        hover_text.append(text_row)
    trace = go.Surface(
        x=iv_grid.columns.to_numpy(dtype=float),
        y=iv_grid.index.to_numpy(dtype=float),
        z=iv_grid.to_numpy(dtype=float),
        customdata=customdata,
        # Plotly's text validator stringifies nested Python lists row-by-row;
        # a 2D object array retains the per-cell shape through serialization.
        text=np.asarray(hover_text, dtype=object),
        hoverlabel={"align": "left"},
        connectgaps=False,
        colorscale="Viridis",
        colorbar={
            "title": {"text": "IV", "side": "top"},
            "tickformat": ".0%",
            "len": 0.8,
            "thickness": 18,
            "x": 0.92 if compact_layout else 0.94,
            "y": 0.52,
        },
        lighting={
            "ambient": 0.78,
            "diffuse": 0.88,
            "specular": 0.16,
            "roughness": 0.82,
            "fresnel": 0.08,
        },
        lightposition={"x": 80, "y": -120, "z": 180},
        opacity=0.98,
        name="Interpolated surface",
        showlegend=False,
        # Native surface text lookup is row/column aware; hovertemplate's generic
        # array lookup can invert these indices, including for the text token.
        hoverinfo="text",
    )
    figure = go.Figure(data=[trace])
    observed_column = (
        "observed_iv" if "observed_iv" in long_frame.columns else "iv"
    )
    observed_values = long_frame[observed_column].to_numpy(dtype=float)
    observed = long_frame.loc[np.isfinite(observed_values)].copy()
    if not observed.empty:
        original_observed_iv = observed[observed_column].to_numpy(dtype=float)
        finite_surface = iv_grid.to_numpy(dtype=float)
        finite_surface = finite_surface[np.isfinite(finite_surface)]
        surface_span = np.ptp(finite_surface) if finite_surface.size else 0.0
        marker_lift = max(float(surface_span) * 0.006, 0.0005)
        observed_customdata = observed[
            ["strike", observed_column]
        ].to_numpy(dtype=float)
        if "source" in observed.columns:
            observed_customdata = observed[
                ["strike", "source", observed_column]
            ].to_numpy(dtype=object)
        observed_text = [
            _surface_hover_text(
                maturity, row.moneyness, row.strike, iv,
                source_label=(
                    "Value source" if value_type_hover else "IV from"
                ) if source_hover else None,
                source=getattr(row, "source", "Observed IV"),
                value_type="Observed" if value_type_hover else None,
                iv_label=_iv_label(iv_source),
            )
            for maturity, row, iv in zip(
                _maturity_hover(observed, observed["tau"]),
                observed.itertuples(index=False), original_observed_iv,
            )
        ]
        figure.add_trace(
            go.Scatter3d(
                x=observed["moneyness"].to_numpy(dtype=float),
                y=observed["tau"].to_numpy(dtype=float),
                z=original_observed_iv + marker_lift,
                customdata=observed_customdata,
                text=observed_text,
                hoverlabel={"align": "left"},
                mode="markers",
                name="Observed IV",
                marker={
                    "size": 3,
                    "color": "#F97316",
                    "opacity": 1,
                    "line": {
                        "color": "rgba(15, 23, 42, 0.85)",
                        "width": 0.4,
                    },
                },
                hoverinfo="text",
            )
        )
    axis_style = {
        "showbackground": False,
        "gridcolor": "rgba(148, 163, 184, 0.18)",
        "zeroline": False,
        "showspikes": False,
        # WebGL draws 3D axis text thinner than 2D axes; 13px keeps the
        # theme's grey tick colour readable on a light background.
        "tickfont": {"size": 13},
    }
    figure.update_layout(
        scene={
            # The scene stops short of the colorbar so the mesh can fill the
            # width; its axis labels are clipped at the scene's edges.
            "domain": {"x": [0, 0.9] if compact_layout else [0, 0.93]},
            "bgcolor": "rgba(0, 0, 0, 0)",
            "xaxis": {"title": {"text": "K / S", "font": {"size": 14}}, **axis_style},
            "yaxis": {
                "title": {
                    "text": "" if compact_layout else "Expiry (UTC)",
                    "font": {"size": 14},
                },
                "tickmode": "array",
                "tickvals": visible_taus,
                "ticktext": [
                    label.replace("-", "<br>", 1)
                    for label in _expiry_labels(long_frame, visible_taus)
                ],
                **axis_style,
            },
            "zaxis": {
                # The IV colorbar and percentage ticks identify this axis;
                # omitting the duplicate title avoids edge clipping on rotation.
                "title": "",
                "tickformat": ".0%",
                **axis_style,
            },
            # Lowering the look-at point lifts the box in the frame, so the
            # near corner's expiry ticks clear the bottom edge; moving it
            # along +x/-y shifts the box right, clear of the left edge.
            "camera": (
                {
                    "eye": {"x": 1.6, "y": 1.7, "z": 0.62},
                    "center": {"x": 0.15, "y": -0.15, "z": -0.45},
                }
                if compact_layout else {
                    "eye": {"x": 1.4, "y": 1.5, "z": 0.55},
                    "center": {"x": 0.05, "y": -0.05, "z": -0.45},
                }
            ),
            "aspectmode": "manual",
            "aspectratio": {"x": 2.0, "y": 1.2, "z": 0.72},
            "dragmode": "turntable",
        },
        autosize=True,
        height=340 if compact_layout else 500,
        margin={
            "l": 10 if compact_layout else 20,
            "r": 10 if compact_layout else 12,
            "t": 10,
            "b": 10,
        },
        paper_bgcolor="rgba(0, 0, 0, 0)",
        legend={
            "orientation": "h",
            "x": 0.02,
            "y": 0.98,
            "xanchor": "left",
            "yanchor": "top",
            "bgcolor": "rgba(0, 0, 0, 0)",
        },
        uirevision="iv-surface-camera-v20",
    )
    return figure


def _band_runs(low, high):
    """(start, stop) of each run of points where both band edges exist."""
    both = np.isfinite(low) & np.isfinite(high)
    runs, start = [], None
    for index in range(len(both) + 1):
        if index < len(both) and both[index]:
            if start is None:
                start = index
        elif start is not None:
            runs.append((start, index))
            start = None
    return runs


def _band_polygons(x, low, high):
    """One closed shape per run of two or more points with both band edges.

    Shapes are separated by None, so a point missing either edge is a gap.
    """
    xs, ys = [], []
    for start, stop in _band_runs(low, high):
        if stop - start < 2:
            continue
        run = slice(start, stop)
        xs.extend([*x[run], *x[run][::-1], None])
        ys.extend([*high[run], *low[run][::-1], None])
    return xs[:-1], ys[:-1]


def _band_bars(x, low, high):
    """Vertical low-to-high segments for points whose neighbours lack a band."""
    xs, ys = [], []
    for start, stop in _band_runs(low, high):
        if stop - start == 1:
            xs.extend([x[start], x[start], None])
            ys.extend([low[start], high[start], None])
    return xs[:-1], ys[:-1]


def _band_fill(color, alpha=0.18):
    red, green, blue = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({red}, {green}, {blue}, {alpha})"


def _add_band_trace(figure, x, low, high, color, name, legendgroup, showlegend):
    """Shade the bid-ask IV display band only where both edges exist.

    A run of one point has no width to shade, so it is drawn as a short
    vertical bar from the low to the high edge.
    """
    x = np.asarray(x, dtype=float)
    low = np.asarray(low, dtype=float)
    high = np.asarray(high, dtype=float)
    shape_x, shape_y = _band_polygons(x, low, high)
    figure.add_trace(go.Scatter(
        x=shape_x, y=shape_y, mode="lines", fill="toself",
        fillcolor=_band_fill(color),
        line=dict(width=0, color=color), connectgaps=False,
        hoverinfo="skip", legendgroup=legendgroup, showlegend=showlegend,
        name=name,
    ))
    bar_x, bar_y = _band_bars(x, low, high)
    if bar_x:
        figure.add_trace(go.Scatter(
            x=bar_x, y=bar_y, mode="lines",
            line=dict(width=6, color=_band_fill(color, 0.35)), connectgaps=False,
            hoverinfo="skip", legendgroup=legendgroup, showlegend=False,
            name=f"{name} · single points",
        ))


def make_smile_figure(
    long_frame: pd.DataFrame, selected_expiries=None, iv_source=None,
) -> go.Figure:
    """Create one IV smile trace per selected expiry.

    When the frame has band_low/band_high columns, each smile also gets a
    shaded bid-ask IV display band, drawn beneath its line.
    """
    _require_columns(long_frame, _LONG_FRAME_COLUMNS, "long_frame")

    selected = None if selected_expiries is None else set(selected_expiries)
    figure = go.Figure()
    observed_moneyness = []
    colors = [
        "#38BDF8", "#FB923C", "#C084FC", "#34D399", "#F472B6",
        "#FACC15", "#818CF8", "#2DD4BF", "#F87171", "#A3E635",
    ]
    for expiry_index, tau in enumerate(sorted(long_frame["tau"].dropna().unique())):
        if selected is not None and tau not in selected:
            continue
        smile = long_frame[long_frame["tau"] == tau].sort_values("moneyness")
        observed_moneyness.extend(
            smile.loc[np.isfinite(smile["iv"]), "moneyness"].to_numpy(dtype=float)
        )
        expiry_label = _expiry_labels(long_frame, [tau])[0]
        color = colors[expiry_index % len(colors)]
        customdata = smile["strike"].to_numpy(dtype=float)
        strike_hover = "Strike: %{hovertext}<br>"
        source_hover = ""
        band_hover = ""
        if "source" in smile.columns:
            customdata = np.column_stack([
                smile["strike"].to_numpy(dtype=object),
                smile["source"].map(_source_label).to_numpy(dtype=object),
            ])
            source_hover = "IV from: %{customdata[1]}<br>"
        if {"band_low", "band_high"} <= set(smile.columns):
            customdata = np.column_stack([
                customdata.reshape(len(smile), -1).astype(object),
                smile["band_low"].to_numpy(dtype=float),
                smile["band_high"].to_numpy(dtype=float),
            ])
            low_index = customdata.shape[1] - 2
            band_of = " of %{customdata[1]}" if source_hover else ""
            band_hover = (
                f"<br>bid–ask display band{band_of}: %{{customdata[{low_index}]:.2%}}"
                f" – %{{customdata[{low_index + 1}]:.2%}}"
            )
            _add_band_trace(
                figure, smile["moneyness"], smile["band_low"], smile["band_high"],
                color, name=f"{expiry_label} bid–ask IV (display band)",
                legendgroup=expiry_label, showlegend=False,
            )
        figure.add_trace(
            go.Scatter(
                x=smile["moneyness"].to_numpy(dtype=float),
                y=smile["iv"].to_numpy(dtype=float),
                customdata=customdata,
                text=[_maturity_hover(smile, [tau])[0]] * len(smile),
                hovertext=[_format_strike(strike) for strike in smile["strike"]],
                mode="lines+markers",
                line=dict(width=2, color=color),
                marker=dict(size=5),
                name=expiry_label,
                meta=tau,
                connectgaps=False,
                hovertemplate=(
                    "%{text}<br>"
                    "K / S: %{x:.4f}<br>"
                    + strike_hover
                    + source_hover
                    + f"{_iv_label(iv_source)}: %{{y:.2%}}"
                    + band_hover
                    + "<extra>%{fullData.name}</extra>"
                ),
            )
        )

    if observed_moneyness:
        lower, upper = min(observed_moneyness), max(observed_moneyness)
        padding = max((upper - lower) * 0.05, 0.01)
        x_range = [lower - padding, upper + padding]
    else:
        x_range = [0.8, 1.2]
    figure.add_vline(x=1.0, line_dash="dot", line_color="gray", line_width=1)
    figure.update_layout(
        xaxis_title="Moneyness (K / S)",
        yaxis_title="IV",
        height=430,
        margin=dict(l=12, r=12, t=65, b=12),
        legend=dict(orientation="h", x=0, y=1.02, xanchor="left", yanchor="bottom"),
        hovermode="closest",
    )
    figure.update_xaxes(range=x_range, tickformat=".2f", zeroline=False)
    figure.update_yaxes(tickformat=".0%", zeroline=False)
    return figure


def make_atm_term_structure_figure(
    atm_frame: pd.DataFrame, iv_source=None
) -> go.Figure:
    """Create an ATM-proxy term structure while preserving rejected expiries.

    When the frame has band_low/band_high columns, a shaded bid-ask IV
    display band is drawn beneath the line.
    """
    _require_columns(atm_frame, _ATM_FRAME_COLUMNS, "atm_frame")

    data = atm_frame.sort_values("tau")
    color = "#38BDF8"
    has_band = {"band_low", "band_high"} <= set(data.columns)
    columns = ["strike", "moneyness", "atm_distance", "selection_status"]
    band_hover = ""
    if has_band:
        columns += ["band_low", "band_high"]
        band_hover = (
            "<br>bid–ask display band: %{customdata[4]:.2%}"
            " – %{customdata[5]:.2%}"
        )
    customdata = data[columns].to_numpy()
    trace = go.Scatter(
        x=data["tau"].to_numpy(dtype=float),
        y=data["iv"].to_numpy(dtype=float),
        text=_maturity_hover(data, data["tau"]),
        hovertext=[_format_strike(strike) for strike in data["strike"]],
        customdata=customdata,
        mode="lines+markers",
        line=dict(width=2, color=color),
        name=f"ATM {_iv_label(iv_source)}",
        connectgaps=False,
        hovertemplate=(
            "%{text}<br>"
            f"{_iv_label(iv_source)}: %{{y:.2%}}<br>"
            "Strike: %{hovertext}<br>"
            "K / S: %{customdata[1]:.4f}<br>"
            "ATM distance: %{customdata[2]:.2%}<br>"
            "selection: %{customdata[3]}"
            + band_hover
            + "<extra></extra>"
        ),
    )
    figure = go.Figure()
    if has_band:
        _add_band_trace(
            figure, data["tau"], data["band_low"], data["band_high"], color,
            name="bid–ask IV (display band)", legendgroup="band", showlegend=True,
        )
    figure.add_trace(trace)
    figure.update_layout(
        height=430,
        margin=dict(l=12, r=12, t=48, b=12),
        legend=dict(orientation="h", x=0, y=1.02, xanchor="left", yanchor="bottom"),
        showlegend=has_band,
        xaxis_title=(
            "Expiry (UTC) · spaced by maturity"
            if "expiry_datetime" in data.columns else "tau (years)"
        ),
        yaxis_title="IV",
    )
    ticks = _spaced_tau_ticks(data["tau"], minimum_spacing_fraction=0.18)
    figure.update_xaxes(
        tickmode="array",
        tickvals=ticks,
        ticktext=_expiry_labels(data, ticks),
        automargin=True,
    )
    figure.update_yaxes(tickformat=".0%")
    return figure


def _strike_axis_range(shown: pd.DataFrame, strike_range) -> list[float]:
    """Strike axis for both panels: pad by half a strike step so end bars are whole."""
    low, high = strike_range
    strikes = shown["strike"].to_numpy(dtype=float)
    step = np.diff(strikes).min() if len(strikes) > 1 else (high - low) * 0.05
    return [low - step / 2, high + step / 2]


def _open_interest_bars(shown: pd.DataFrame, scope: str) -> list[go.Bar]:
    customdata = shown[["call_oi", "put_oi"]].to_numpy(dtype=float)
    hovertemplate = (
        "Strike: $%{x:,.0f}<br>"
        "Call OI: %{customdata[0]:,.1f} BTC<br>"
        "Put OI: %{customdata[1]:,.1f} BTC<br>"
        f"Expiries: {escape(scope)}<extra></extra>"
    )
    return [
        go.Bar(
            x=shown["strike"].to_numpy(dtype=float),
            y=shown[column].to_numpy(dtype=float),
            customdata=customdata,
            name=name,
            marker_color=color,
            hovertemplate=hovertemplate,
        )
        for name, column, color in [
            ("Call", "call_oi", "#60A5FA"), ("Put", "put_oi", "#FBBF24"),
        ]
    ]


_GEX_DETAIL_COLUMNS = ["call_gex", "put_gex", "call_oi", "put_oi", "contracts"]


def index_label(index_price: float) -> str:
    """The BTC index as every chart and caption shows it, e.g. 'Index $82,227.73'."""
    return f"Index ${index_price:,.2f}"


GROSS_GEX_COLOR = "#A78BFA"


def _gex_bar(shown: pd.DataFrame, scope: str, scenario: str, mode: str) -> go.Bar:
    values = shown[f"{mode.lower()}_gex"].to_numpy(dtype=float)
    details = shown[_GEX_DETAIL_COLUMNS].to_numpy(dtype=float)
    if mode == "Gross":
        # Each type has one sign, so its Gross share is the magnitude of its subtotal.
        details[:, :2] = np.abs(details[:, :2])
        colors = GROSS_GEX_COLOR
        scenario_line = ""
    else:
        colors = np.where(values >= 0, "#34D399", "#F87171")
        scenario_line = f"{scenario}<br>"
    hovertemplate = (
        "Strike: $%{x:,.0f}<br>"
        f"{mode} GEX: %{{y:$,.0f}} per 1% BTC move<br>"
        "Call GEX: %{customdata[0]:$,.0f}<br>"
        "Put GEX: %{customdata[1]:$,.0f}<br>"
        "Call OI: %{customdata[2]:,.1f} BTC<br>"
        "Put OI: %{customdata[3]:,.1f} BTC<br>"
        "Contracts: %{customdata[4]:,.0f}<br>"
        f"{scenario_line}"
        f"Expiries: {escape(scope)}<extra></extra>"
    )
    return go.Bar(
        x=shown["strike"].to_numpy(dtype=float),
        y=values,
        customdata=details,
        name=f"{mode} GEX",
        showlegend=False,
        marker_color=colors,
        hovertemplate=hovertemplate,
    )


# Incomplete/Insufficient markers sit in a strip near the top of the GEX panel
# on their own 0..1 axis, so they never read as a GEX value or a zero bar.
_STATUS_STRIP_Y = 0.94


def _incomplete_text(row, scope: str, mode: str) -> str:
    oi_share = (
        f"{row.oi_share:.1%} of strike OI computable"
        if np.isfinite(row.oi_share) else "Computable OI share unknown (OI missing)"
    )
    return (
        f"<b>Incomplete data</b><br>Strike: ${row.strike:,.0f}<br>"
        f"Partial {mode} GEX (computable contracts only): "
        f"${getattr(row, f'partial_{mode.lower()}_gex'):,.0f} "
        f"per 1% BTC move<br>"
        f"{row.usable} of {row.contracts} contracts usable<br>{oi_share}<br>"
        f"Reason: {escape(row.reason)}<br>Expiries: {escape(scope)}"
    )


def _insufficient_text(row, scope: str, mode: str) -> str:
    return (
        f"<b>Insufficient data</b><br>Strike: ${row.strike:,.0f}<br>"
        f"0 of {row.contracts} contracts usable<br>"
        f"Reason: {escape(row.reason)}<br>Expiries: {escape(scope)}"
    )


def _gex_status_markers(shown: pd.DataFrame, scope: str, mode: str) -> list[go.Scatter]:
    styles = [
        ("incomplete", "Incomplete data", "diamond-open", "#F59E0B", _incomplete_text),
        ("insufficient", "Insufficient data", "x-thin-open", "#9CA3AF", _insufficient_text),
    ]
    markers = []
    for status, name, symbol, color, describe in styles:
        rows = shown[shown["status"] == status]
        if rows.empty:
            continue
        markers.append(go.Scatter(
            x=rows["strike"].to_numpy(dtype=float),
            y=np.full(len(rows), _STATUS_STRIP_Y),
            xaxis="x2",
            yaxis="y3",
            legend="legend2",
            mode="markers",
            name=name,
            marker=dict(symbol=symbol, size=11, color=color, line=dict(width=2, color=color)),
            hovertext=[describe(row, scope, mode) for row in rows.itertuples()],
            hoverinfo="text",
        ))
    return markers


def _panel_title(name: str, text: str, yaxis) -> dict:
    """A left-aligned title just above a panel's plot area."""
    return dict(
        name=name, text=text, showarrow=False, font=dict(size=16), align="left",
        xref="paper", x=0, xanchor="left",
        yref="paper", y=yaxis.domain[1], yanchor="bottom", yshift=8,
    )


def make_positioning_figure(
    oi_table: pd.DataFrame, gex_table: pd.DataFrame, index_price: float,
    strike_range, scope: str, assumption: str, oi_share: float, mode: str = "Net",
) -> go.Figure:
    """Open interest (top) and gamma exposure (bottom) by strike in one figure.

    Both panels share one strike axis (``xaxis`` matches ``xaxis2``), so a
    strike sits at the same x in both and one zoom covers both.
    ``oi_table`` comes from ``open_interest_by_strike`` and ``gex_table`` from
    ``net_gex_by_strike``; ``strike_range`` only zooms the display. OI bars
    are Call and Put BTC. GEX bars are USD per 1% BTC move: ``mode`` picks
    ``net_gex`` (signed) or ``gross_gex`` (magnitudes), and the GEX title
    states ``assumption`` as a scenario, not observed dealer inventory. The
    panel titles are annotations named ``oi_title`` and ``gex_title``.
    Dragging selects a band of strikes (``dragmode="select"``, horizontal),
    which the dashboard turns into the strike range.
    """
    if mode not in GEX_MODES:
        raise ValueError(f"mode must be one of {GEX_MODES}, got {mode!r}")
    _require_columns(oi_table, {"strike", "call_oi", "put_oi"}, "oi_table")
    value_column = f"{mode.lower()}_gex"
    _require_columns(
        gex_table,
        {"strike", value_column, *_GEX_DETAIL_COLUMNS, "status",
         f"partial_{value_column}", "usable", "oi_share", "reason"},
        "gex_table",
    )
    oi_shown = strikes_in_range(oi_table, strike_range).sort_values("strike")
    gex_shown = strikes_in_range(gex_table, strike_range).sort_values("strike")
    scenario = f"Scenario: {escape(assumption)}"

    figure = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.16, row_heights=[0.45, 0.55],
    )
    for bar in _open_interest_bars(oi_shown, scope):
        figure.add_trace(bar, row=1, col=1)
    figure.add_trace(_gex_bar(gex_shown, scope, scenario, mode), row=2, col=1)
    markers = _gex_status_markers(gex_shown, scope, mode)
    figure.add_traces(markers)
    # One index line per panel; only the top one is labelled, inside the OI
    # panel so it stays clear of the panel titles.
    index_line = dict(x=index_price, col=1, line_dash="dash", line_color="gray", line_width=1)
    figure.add_vline(
        row=1, annotation_text=index_label(index_price), annotation_position="top right",
        annotation_yanchor="top", annotation_font_size=12, **index_line,
    )
    figure.add_vline(row=2, **index_line)

    share = "unknown share" if not np.isfinite(oi_share) else f"{oi_share:.0%}"
    complete = int((gex_table["status"] == "complete").sum())
    layout = figure.layout
    figure.add_annotation(_panel_title(
        "oi_title", f"Open interest · {escape(scope)}", layout.yaxis,
    ))
    figure.add_annotation(_panel_title(
        "gex_title",
        f"{mode} gamma exposure · {escape(scope)}<br><sup>"
        f"USD per 1% BTC move · Exchange mark IV · "
        f"{share} of OI computable · {complete} of {len(gex_table)} strikes "
        f"complete (every strike in {escape(scope)})"
        + (f"<br>{scenario}, not observed dealer inventory" if mode == "Net" else "")
        + "</sup>",
        layout.yaxis2,
    ))
    figure.update_layout(
        barmode="group",
        dragmode="select",
        selectdirection="h",
        height=900,
        margin=dict(l=12, r=12, t=45, b=12),
        legend=dict(orientation="h", x=1, y=1, xanchor="right", yanchor="bottom"),
        hovermode="closest",
        yaxis=dict(title="OI · BTC", rangemode="tozero"),
        yaxis2=dict(
            title=f"{mode} GEX · USD per 1% BTC move", zeroline=True, tickformat="$,.3s",
        ),
    )
    if markers:
        figure.update_layout(
            yaxis3=dict(
                overlaying="y2", anchor="x2", range=[0, 1], visible=False, fixedrange=True,
            ),
            legend2=dict(
                orientation="h", x=0.01, y=layout.yaxis2.domain[1] - 0.02,
                yanchor="top", bgcolor="rgba(0,0,0,0)",
            ),
        )
    figure.update_xaxes(
        range=_strike_axis_range(gex_shown, strike_range), tickformat=",.0f",
        showticklabels=True,
    )
    figure.update_xaxes(title="Strike · USD", row=2, col=1)
    return figure
