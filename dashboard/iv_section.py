"""Implied volatility: IV source, sidebar notes and the four IV chart tabs."""

import numpy as np
import streamlit as st

from iv_surface import iv_source as iv_sources
from iv_surface import visualization
from iv_surface.iv_source import DEFAULT_IV_SOURCE, IV_SOURCES, iv_source_long_frame
from iv_surface.surface_transforms import (
    HEATMAP_VALUES,
    MONEYNESS_RANGES,
    atm_term_structure_frame,
    interpolate_surface_2d,
)

from dashboard.state import expiry_taus, smile_key, widget_default


@st.cache_data(show_spinner="Solving bid/ask IV…", max_entries=4)
def _bid_ask_iv(chain):
    return iv_sources.solve_bid_ask_iv(chain)


@st.cache_data(show_spinner="Building IV…", max_entries=8)
def _iv_source_surface(chain, iv_source):
    return iv_sources.build_iv_source_surface(
        chain, iv_source, bid_ask_iv=_bid_ask_iv(chain)
    )


def iv_source_control():
    """IV source for the IV charts only; switching reuses the loaded snapshot."""
    return st.segmented_control(
        "IV source",
        IV_SOURCES,
        default=widget_default("iv_source", DEFAULT_IV_SOURCE),
        required=True,
        key="iv_source",
        help=(
            "Exchange mark is the mark IV Deribit reports. Quote midpoint is "
            "our solver's IV from each contract's bid/ask midpoint, priced "
            "with the contract's reported forward (R = ln(F / X) / T). "
            "Changes the IV charts only."
        ),
    ) or DEFAULT_IV_SOURCE


def keep_iv_view_settings(chain, snapshot_id):
    """Hold the IV view settings on a run that cannot draw the IV charts.

    Streamlit drops a widget's value on any run that does not draw it.
    Writing each value back as session state keeps the user's moneyness range,
    heatmap values and smile expiries for Save and for when the charts return.
    """
    state = st.session_state
    smile_keys = [smile_key(snapshot_id, tau) for tau in expiry_taus(chain)]
    for key in ["moneyness_range", "heatmap_view", *smile_keys]:
        if key in state:
            state[key] = state[key]


def iv_section(chain, snapshot_id):
    """IV charts from the selected IV source; a failed IV build keeps the IV settings."""
    st.subheader("Implied volatility")
    iv_source = iv_source_control()
    try:
        result = _iv_source_surface(chain, iv_source)
    except ValueError:
        st.error(
            "Cannot build IV: the snapshot needs valid, unique contracts and "
            "usable bid/ask quotes."
        )
        keep_iv_view_settings(chain, snapshot_id)
        return

    expiry_dates = chain.drop_duplicates("tau").set_index("tau")["expiry_dt"]
    frame = iv_source_long_frame(
        result, expiry_datetimes=expiry_dates.reindex(result.expiries).tolist()
    )
    st.write(f"{visualization.index_label(result.spot_price)} · IV source: **{iv_source}**")
    _sidebar_iv_notes(frame, iv_source)
    if not np.isfinite(frame["iv"]).any():
        st.warning("No IV solves succeeded for this snapshot.")

    st.sidebar.subheader("Surface views")
    range_name = st.sidebar.radio(
        "Moneyness range",
        list(MONEYNESS_RANGES),
        horizontal=True,
        key="moneyness_range",
        help=(
            "Applies to Heatmap and 3D surface. IV smiles show all observed strikes."
        ),
    )
    moneyness = MONEYNESS_RANGES[range_name]
    surface_frame = interpolate_surface_2d(
        frame, min_moneyness=moneyness[0], max_moneyness=moneyness[1]
    )
    observed_frame = surface_frame.copy()
    observed_frame["iv"] = observed_frame["observed_iv"]
    observed_frame["surface_value_type"] = np.where(
        np.isfinite(observed_frame["observed_iv"]), "Observed", "Missing"
    )
    _sidebar_interpolation_notes()

    heatmap_tab, surface_tab, smile_tab, atm_tab = st.tabs(
        ["Heatmap", "3D surface", "IV smiles", "ATM term structure"]
    )
    with heatmap_tab:
        _heatmap_tab(surface_frame, observed_frame, moneyness, iv_source)
    with surface_tab:
        _surface_tab(surface_frame, moneyness, iv_source)
    with smile_tab:
        _smile_tab(frame, snapshot_id, iv_source)
    with atm_tab:
        _atm_tab(frame, iv_source)


def _visible_range_summary(frame, moneyness):
    counts = frame["surface_value_type"].value_counts()
    return (
        "Visible range: "
        f"{counts.get('Observed', 0):,} observed · "
        f"{counts.get('Interpolated', 0):,} interpolated · "
        f"{counts.get('Missing', 0):,} blank. "
        f"K / S: {moneyness[0]:.1f}–{moneyness[1]:.1f}."
    )


def _sidebar_iv_notes(frame, iv_source):
    source = frame["source"]
    counts = (
        int(source.isin(["call", "put", "near_atm_average"]).sum()),
        int(
            source.isin(
                [
                    "call_fallback",
                    "put_fallback",
                    "near_atm_call_only",
                    "near_atm_put_only",
                ]
            ).sum()
        ),
        int(source.eq("missing").sum()),
    )
    with st.sidebar.expander(f"Combined IV coverage · {iv_source}"):
        for label, count in zip(
            ["Preferred / averaged", "Fallback / one-sided", "Missing"], counts
        ):
            st.metric(label, f"{count:,}")
        st.caption(f"All {len(frame):,} expiry × strike grid cells.")
        st.caption(
            "Within 2% of spot, average same-strike Call and Put IV when both "
            "are available. Outside that band, prefer Put below spot and Call "
            "above spot."
        )
    with st.sidebar.expander("Deribit pricing"):
        st.caption(
            "BTC bid/ask premiums are converted to USD using the snapshot's "
            "BTC/USD index X. Quote midpoint IV and the bid–ask band use our "
            "Black-Scholes solver with each contract's reported forward F, so "
            "R = ln(F / X) / T and no rate is chosen. A solve must reprice "
            "within $0.01 or it is missing. Exchange mark IV is Deribit's own."
        )


def _sidebar_interpolation_notes():
    with st.sidebar.expander("Surface interpolation"):
        st.write(
            "Convert observed IV to total variance (IV² × tau), linearly "
            "interpolate it between observations, then convert back to IV. "
            "K / S and tau are each scaled to their observed range for "
            "triangulation. Original IV points stay unchanged."
        )
        st.write(
            "The existing grid is filled only inside the convex hull of "
            "observations in the selected range. A cell can be filled across "
            "expiries, but cells outside that boundary stay blank. "
            "A denser grid would add display points, not market observations."
        )
        st.write(
            "In 3D, observed markers are lifted slightly above the mesh for "
            "visibility; hover reports their original IV."
        )


def _heatmap_tab(surface_frame, observed_frame, moneyness, iv_source):
    heatmap_view = st.radio(
        "Heatmap values",
        HEATMAP_VALUES,
        horizontal=True,
        key="heatmap_view",
        help=(
            "Surface uses 2D total-variance interpolation. Observed "
            "shows solved market IV without interpolation."
        ),
    )
    heatmap_frame = surface_frame if heatmap_view == "Surface" else observed_frame
    st.caption(_visible_range_summary(heatmap_frame, moneyness))
    st.plotly_chart(
        visualization.make_iv_heatmap(
            heatmap_frame, equal_expiry_spacing=True, iv_source=iv_source
        ),
        use_container_width=True,
    )


def _surface_tab(surface_frame, moneyness, iv_source):
    st.caption(_visible_range_summary(surface_frame, moneyness))
    st.caption("2D total-variance interpolation · observed IV overlaid as points.")
    with st.container(key="surface-responsive"):
        for compact, key in [(False, "surface-wide"), (True, "surface-narrow")]:
            with st.container(key=key):
                st.plotly_chart(
                    visualization.make_iv_surface_figure(
                        surface_frame,
                        compact_layout=compact,
                        iv_source=iv_source,
                    ),
                    key=f"plot-{key}",
                    use_container_width=True,
                    config={"modeBarButtonsToRemove": ["resetCameraDefault3d"]},
                )
    st.markdown(
        '<div aria-hidden="true" style="height: 32px"></div>',
        unsafe_allow_html=True,
    )


def _smile_tab(frame, snapshot_id, iv_source):
    expiry_labels = {
        row.tau: row.expiry_datetime.strftime("%Y-%m-%d")
        for row in frame[["tau", "expiry_datetime"]]
        .dropna()
        .drop_duplicates("tau")
        .itertuples(index=False)
    }
    available_expiries = sorted(frame["tau"].unique())
    finite_expiries = sorted(frame.loc[np.isfinite(frame["iv"]), "tau"].unique())
    with st.popover("Select expiries"):
        st.caption("Expiry (UTC)")
        selected_expiries = [
            tau for tau in available_expiries
            if st.checkbox(
                expiry_labels.get(tau, f"tau={tau:g}"),
                value=widget_default(
                    smile_key(snapshot_id, tau),
                    tau in finite_expiries[:3],
                ) or False,
                key=smile_key(snapshot_id, tau),
            )
        ]
    st.caption(
        f"Observed Combined {iv_source} IV · all strikes · gaps preserved. "
        "Shading is a bid–ask IV display band from our solver, blended "
        "with the line's Call/Put weights; it is not a tradable quote, "
        "and mark IV may sit outside it."
    )
    if selected_expiries:
        st.plotly_chart(
            visualization.make_smile_figure(
                frame, selected_expiries=selected_expiries, iv_source=iv_source
            ),
            use_container_width=True,
        )
    else:
        st.info("Select an expiry to show its IV smile.")


def _atm_tab(frame, iv_source):
    atm_frame = atm_term_structure_frame(frame)
    st.caption(
        f"Observed Combined {iv_source} IV nearest to spot within 2% · "
        "all expiries"
    )
    st.plotly_chart(
        visualization.make_atm_term_structure_figure(atm_frame, iv_source=iv_source),
        use_container_width=True,
    )
    rejected_count = int(atm_frame["iv"].isna().sum())
    if rejected_count:
        st.info(
            f"{rejected_count} expiries have no usable ATM proxy and remain gaps. "
            "See selection details below."
        )
    with st.expander("ATM selection details"):
        st.caption(
            "Choose the nearest finite Combined IV within 2% of spot. "
            "Equally near strikes are averaged. Maturity spacing uses tau in years."
        )
        st.dataframe(
            atm_frame.rename(columns={"expiry_datetime": "Expiry (UTC)"}),
            hide_index=True,
            use_container_width=True,
        )
