from html import escape

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from iv_surface.chain import DAYS_PER_YEAR
from iv_surface.positioning import strikes_in_range


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
        f"Time to expiry: {float(tau) * DAYS_PER_YEAR:.2f} days<br>"
        f"tau: {float(tau):.4f} years"
        for tau, label in zip(taus, _expiry_labels(frame, taus))
    ]


def _format_strike(strike):
    """Keep fractional strikes while omitting unnecessary trailing zeros."""
    return np.format_float_positional(float(strike), trim="-")


def _iv_label(iv_source=None):
    """Name the IV source in hover, e.g. 'Exchange mark IV'."""
    return "IV" if iv_source is None else f"{escape(str(iv_source))} IV"


def _surface_hover_text(
    maturity, moneyness, strike, iv, *,
    source_label=None, source=None, value_type=None, iv_label="IV",
):
    parts = [maturity, f"K / S: {moneyness:.4f}", f"strike: {_format_strike(strike)}"]
    if source_label is not None:
        parts.append(f"{source_label}: {escape(str(source))}")
    if value_type is not None:
        parts.append(f"Surface value: {escape(str(value_type))}")
    parts.append(f"{iv_label}: {iv:.2%}")
    return "<br>".join(parts)


def _heatmap_customdata(long_frame, iv_grid, strike_grid):
    customdata = strike_grid.to_numpy(dtype=float)
    strike_hover = "strike: %{hovertext}<br>"
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
        if has_value_type:
            display_source = display_source.mask(
                long_frame["surface_value_type"].eq("Interpolated"),
                long_frame["interpolation_method"]
                if "interpolation_method" in long_frame.columns
                else "1D interpolation within expiry",
            )
        source_grid = long_frame.assign(source=display_source).pivot(
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
    strike_hover = "strike: %{hovertext}<br>"
    next_index = 1
    if has_source:
        source_label = "Value source" if has_value_type else "Combined source"
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
                source_label = "Value source" if value_type_hover else "Combined source"
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
            "len": 0.72,
            "thickness": 18,
            "x": 1.02,
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
                    "Value source" if value_type_hover else "Combined source"
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
        "tickfont": {"size": 11},
    }
    figure.update_layout(
        scene={
            "domain": {"x": [0, 1]},
            "bgcolor": "rgba(0, 0, 0, 0)",
            "xaxis": {"title": {"text": "K / S", "font": {"size": 12}}, **axis_style},
            "yaxis": {
                "title": {
                    "text": "" if compact_layout else "Expiry (UTC)",
                    "font": {"size": 12},
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
            "camera": {
                "eye": (
                    {"x": 2.7, "y": 2.7, "z": 0.796}
                    if compact_layout else {"x": 1.9, "y": 1.9, "z": 0.56}
                ),
                "center": {"x": 0, "y": 0, "z": -0.06},
            },
            "aspectmode": "manual",
            "aspectratio": {"x": 1.7, "y": 1.2, "z": 0.72},
            "dragmode": "turntable",
        },
        autosize=True,
        height=430 if compact_layout else 640,
        margin={
            "l": 40 if compact_layout else 20,
            "r": 20 if compact_layout else 12,
            "t": 24,
            "b": 24,
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
        uirevision="iv-surface-camera-v18",
    )
    return figure


def _add_band_traces(figure, smile, expiry_label, color):
    """Shade the bid-ask IV display band; gaps stay open (no connectgaps)."""
    x = smile["moneyness"].to_numpy(dtype=float)
    fill = f"rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, 0.18)"
    common = dict(
        x=x, mode="lines", line=dict(width=0, color=color), connectgaps=False,
        hoverinfo="skip", legendgroup=expiry_label, showlegend=False,
    )
    figure.add_trace(go.Scatter(
        y=smile["band_high"].to_numpy(dtype=float),
        name=f"{expiry_label} bid–ask IV (display band)", **common,
    ))
    figure.add_trace(go.Scatter(
        y=smile["band_low"].to_numpy(dtype=float), fill="tonexty", fillcolor=fill,
        name=f"{expiry_label} bid–ask IV (display band)", **common,
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
        strike_hover = "strike: %{hovertext}<br>"
        source_hover = ""
        band_hover = ""
        if "source" in smile.columns:
            customdata = smile[["strike", "source"]].to_numpy(dtype=object)
            source_hover = "source: %{customdata[1]}<br>"
        if {"band_low", "band_high"} <= set(smile.columns):
            customdata = np.column_stack([
                customdata.reshape(len(smile), -1).astype(object),
                smile["band_low"].to_numpy(dtype=float),
                smile["band_high"].to_numpy(dtype=float),
            ])
            low_index = customdata.shape[1] - 2
            band_hover = (
                f"<br>bid–ask display band: %{{customdata[{low_index}]:.2%}}"
                f" – %{{customdata[{low_index + 1}]:.2%}}"
            )
            _add_band_traces(figure, smile, expiry_label, color)
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
    """Create an ATM-proxy term structure while preserving rejected expiries."""
    _require_columns(atm_frame, _ATM_FRAME_COLUMNS, "atm_frame")

    data = atm_frame.sort_values("tau")
    customdata = data[
        ["strike", "moneyness", "atm_distance", "selection_status"]
    ].to_numpy()
    trace = go.Scatter(
        x=data["tau"].to_numpy(dtype=float),
        y=data["iv"].to_numpy(dtype=float),
        text=_maturity_hover(data, data["tau"]),
        hovertext=[_format_strike(strike) for strike in data["strike"]],
        customdata=customdata,
        mode="lines+markers",
        connectgaps=False,
        hovertemplate=(
            "%{text}<br>"
            f"{_iv_label(iv_source)}: %{{y:.2%}}<br>"
            "strike: %{hovertext}<br>"
            "K / S: %{customdata[1]:.4f}<br>"
            "ATM distance: %{customdata[2]:.2%}<br>"
            "selection: %{customdata[3]}<extra></extra>"
        ),
    )
    figure = go.Figure(data=[trace])
    figure.update_layout(
        height=430,
        margin=dict(l=12, r=12, t=24, b=12),
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


def make_open_interest_figure(
    oi_table: pd.DataFrame, index_price: float, strike_range, scope: str
) -> go.Figure:
    """Create Call and Put open interest bars (BTC) by strike.

    ``oi_table`` is the full table from ``open_interest_by_strike``;
    ``strike_range`` only zooms the display.
    """
    _require_columns(oi_table, {"strike", "call_oi", "put_oi"}, "oi_table")
    shown = strikes_in_range(oi_table, strike_range).sort_values("strike")
    customdata = shown[["call_oi", "put_oi"]].to_numpy(dtype=float)
    hovertemplate = (
        "Strike: $%{x:,.0f}<br>"
        "Call OI: %{customdata[0]:,.1f} BTC<br>"
        "Put OI: %{customdata[1]:,.1f} BTC<br>"
        f"Expiries: {escape(scope)}<extra></extra>"
    )
    figure = go.Figure()
    for name, column, color in [
        ("Call", "call_oi", "#60A5FA"), ("Put", "put_oi", "#FBBF24"),
    ]:
        figure.add_trace(go.Bar(
            x=shown["strike"].to_numpy(dtype=float),
            y=shown[column].to_numpy(dtype=float),
            customdata=customdata,
            name=name,
            marker_color=color,
            hovertemplate=hovertemplate,
        ))
    figure.add_vline(
        x=index_price, line_dash="dash", line_color="gray", line_width=1,
        annotation_text=f"Index ${index_price:,.0f}",
        annotation_position="top",
    )
    figure.update_layout(
        title=f"Open interest · {escape(scope)}",
        barmode="group",
        height=430,
        margin=dict(l=12, r=12, t=65, b=12),
        legend=dict(orientation="h", x=1, y=1.02, xanchor="right", yanchor="bottom"),
        xaxis_title="Strike · USD",
        yaxis_title="OI · BTC",
        hovermode="closest",
    )
    figure.update_xaxes(range=_strike_axis_range(shown, strike_range), tickformat=",.0f")
    figure.update_yaxes(rangemode="tozero")
    return figure


def _strike_axis_range(shown: pd.DataFrame, strike_range) -> list[float]:
    """Shared OI/GEX strike axis: pad by half a strike step so end bars are whole."""
    low, high = strike_range
    strikes = shown["strike"].to_numpy(dtype=float)
    step = np.diff(strikes).min() if len(strikes) > 1 else (high - low) * 0.05
    return [low - step / 2, high + step / 2]


GEX_MODES = ("Net", "Gross")


# Incomplete/Insufficient markers sit in a strip near the top of the plot on
# their own 0..1 axis, so they never read as a GEX value or a zero bar.
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


def _add_gex_status_markers(figure: go.Figure, shown: pd.DataFrame, scope: str, mode: str):
    styles = [
        ("incomplete", "Incomplete data", "diamond-open", "#F59E0B", _incomplete_text),
        ("insufficient", "Insufficient data", "x-thin-open", "#9CA3AF", _insufficient_text),
    ]
    added = False
    for status, name, symbol, color, describe in styles:
        rows = shown[shown["status"] == status]
        if rows.empty:
            continue
        added = True
        figure.add_trace(go.Scatter(
            x=rows["strike"].to_numpy(dtype=float),
            y=np.full(len(rows), _STATUS_STRIP_Y),
            yaxis="y2",
            mode="markers",
            name=name,
            marker=dict(symbol=symbol, size=11, color=color, line=dict(width=2, color=color)),
            hovertext=[describe(row, scope, mode) for row in rows.itertuples()],
            hoverinfo="text",
            showlegend=True,
        ))
    if added:
        figure.update_layout(
            yaxis2=dict(overlaying="y", range=[0, 1], visible=False, fixedrange=True),
            legend=dict(orientation="h", x=0.01, y=0.86, bgcolor="rgba(0,0,0,0)"),
        )


def make_gex_figure(
    gex_table: pd.DataFrame, index_price: float, strike_range, scope: str,
    assumption: str, oi_share: float, mode: str = "Net",
) -> go.Figure:
    """Create Net or Gross GEX bars by strike in USD per 1% BTC move.

    ``gex_table`` is the full table from ``net_gex_by_strike``; ``strike_range``
    only zooms the display and the strike axis matches the OI figure's.
    ``mode`` picks ``net_gex`` (signed) or ``gross_gex`` (magnitudes). The
    title states ``assumption`` as a scenario, not observed dealer inventory.
    """
    if mode not in GEX_MODES:
        raise ValueError(f"mode must be one of {GEX_MODES}, got {mode!r}")
    detail_columns = ["call_gex", "put_gex", "call_oi", "put_oi", "contracts"]
    value_column = f"{mode.lower()}_gex"
    _require_columns(
        gex_table,
        {"strike", value_column, *detail_columns, "status", f"partial_{value_column}",
         "usable", "oi_share", "reason"},
        "gex_table",
    )
    shown = strikes_in_range(gex_table, strike_range).sort_values("strike")
    values = shown[value_column].to_numpy(dtype=float)
    details = shown[detail_columns].to_numpy(dtype=float)
    if mode == "Gross":
        # Each type has one sign, so its Gross share is the magnitude of its subtotal.
        details[:, :2] = np.abs(details[:, :2])
        colors = "#60A5FA"
    else:
        colors = np.where(values >= 0, "#34D399", "#F87171")
    share = "unknown share" if not np.isfinite(oi_share) else f"{oi_share:.0%}"
    scenario = f"Scenario: {escape(assumption)}"
    hovertemplate = (
        "Strike: $%{x:,.0f}<br>"
        f"{mode} GEX: %{{y:$,.0f}} per 1% BTC move<br>"
        "Call GEX: %{customdata[0]:$,.0f}<br>"
        "Put GEX: %{customdata[1]:$,.0f}<br>"
        "Call OI: %{customdata[2]:,.1f} BTC<br>"
        "Put OI: %{customdata[3]:,.1f} BTC<br>"
        "Contracts: %{customdata[4]:,.0f}<br>"
        f"{scenario}<br>"
        f"Expiries: {escape(scope)}<extra></extra>"
    )
    figure = go.Figure(go.Bar(
        x=shown["strike"].to_numpy(dtype=float),
        y=values,
        customdata=details,
        name=f"{mode} GEX",
        showlegend=False,
        marker_color=colors,
        hovertemplate=hovertemplate,
    ))
    _add_gex_status_markers(figure, shown, scope, mode)
    figure.add_vline(
        x=index_price, line_dash="dash", line_color="gray", line_width=1,
        annotation_text=f"Index ${index_price:,.0f}",
        annotation_position="top",
    )
    complete = int((gex_table["status"] == "complete").sum())
    figure.update_layout(
        title=(
            f"{mode} gamma exposure · {escape(scope)}<br><sup>"
            f"USD per 1% BTC move · Exchange mark IV · "
            f"{share} of OI computable · {complete} of {len(gex_table)} strikes "
            f"complete (every strike in {escape(scope)})<br>"
            f"{scenario}, not observed dealer inventory</sup>"
        ),
        height=450,
        margin=dict(l=12, r=12, t=100, b=12),
        showlegend=len(figure.data) > 1,
        xaxis_title="Strike · USD",
        yaxis_title=f"{mode} GEX · USD per 1% BTC move",
        hovermode="closest",
    )
    figure.update_xaxes(range=_strike_axis_range(shown, strike_range), tickformat=",.0f")
    figure.update_yaxes(zeroline=True, tickformat="$,.3s")
    return figure
