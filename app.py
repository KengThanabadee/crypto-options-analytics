"""Offline BTC volatility dashboard. Run with streamlit run app.py."""

from datetime import datetime
from pathlib import Path

import numpy as np
import streamlit as st

from iv_surface.deribit import (
    DeribitFetchError,
    fetch_deribit_snapshot,
    load_deribit_snapshot,
    parse_deribit_snapshot,
)
from iv_surface.iv_source import (
    DEFAULT_IV_SOURCE,
    IV_SOURCES,
    build_iv_source_surface,
    iv_source_long_frame,
)
from iv_surface.positioning import (
    assumption_label,
    computable_oi_share,
    expiry_scope_label,
    near_spot_range,
    net_gex_by_strike,
    open_interest_by_strike,
    strikes_in_range,
)
from iv_surface.surface_transforms import (
    atm_term_structure_frame,
    interpolate_surface_2d,
)
from iv_surface.visualization import (
    make_atm_term_structure_figure,
    make_gex_figure,
    make_iv_heatmap,
    make_iv_surface_figure,
    make_open_interest_figure,
    make_smile_figure,
)


DATA_PATH = Path(__file__).resolve().parent / "data"
SNAPSHOT_FILE = "deribit_btc_options_snapshot.json"
MONEYNESS_RANGES = {
    "Core (0.8–1.2)": (0.8, 1.2),
    "Extended (0.7–1.3)": (0.7, 1.3),
}


@st.cache_data(show_spinner="Building IV…", max_entries=8)
def _iv_source_surface(chain, iv_source):
    return build_iv_source_surface(chain, iv_source)


def iv_source_control():
    """IV source for the IV charts only; switching reuses the loaded snapshot."""
    return st.segmented_control(
        "IV source",
        IV_SOURCES,
        default=DEFAULT_IV_SOURCE,
        required=True,
        key="iv_source",
        help=(
            "Exchange mark is the mark IV Deribit reports. Quote midpoint is "
            "our solver's IV from each contract's bid/ask midpoint, priced "
            "with the contract's reported forward (R = ln(F / X) / T). "
            "Changes the IV charts only."
        ),
    ) or DEFAULT_IV_SOURCE


def open_interest_section(chain, snapshot_id):
    """OI by strike with its own expiry selection and strike zoom.

    Widget keys carry the snapshot id so a new snapshot starts at All
    expiries and its own Near spot range.
    """
    range_key = f"oi_strike_range_{snapshot_id}"
    st.subheader("Open interest")
    index_price = float(chain["index_price"].iloc[0])
    expiry_dates = chain.drop_duplicates("tau").set_index("tau")["expiry_dt"]
    selected = st.multiselect(
        "OI expiries",
        sorted(expiry_dates.index),
        format_func=lambda tau: f"{expiry_dates[tau]:%Y-%m-%d}",
        placeholder="All expiries",
        key=f"oi_expiries_{snapshot_id}",
        help="Leave empty for All expiries. The IV charts keep their own expiries.",
    )
    expiries = selected or None
    scope = expiry_scope_label(chain, expiries)
    table = open_interest_by_strike(chain, expiries)

    near_spot = near_spot_range(index_price)
    all_strikes = (
        float(np.floor(min(chain["strike"].min(), near_spot[0]) / 1000) * 1000),
        float(np.ceil(max(chain["strike"].max(), near_spot[1]) / 1000) * 1000),
    )
    if range_key not in st.session_state:
        st.session_state[range_key] = near_spot

    def set_range(strike_range):
        st.session_state[range_key] = strike_range

    range_column, reset_column = st.columns([5, 1], vertical_alignment="bottom")
    with range_column:
        strike_range = st.slider(
            "Strike range (USD)",
            min_value=all_strikes[0],
            max_value=all_strikes[1],
            step=500.0,
            format="$%.0f",
            key=range_key,
            help="Display zoom only. OI sums use every strike in the selected expiries.",
        )
    with reset_column:
        st.button("Near spot", on_click=set_range, args=(near_spot,),
                  help="Reset to ±10% around the index.")
    st.caption(
        f"Open interest · {scope} · Call and Put in BTC · "
        f"index ${index_price:,.2f}"
    )
    if strikes_in_range(table, strike_range).empty:
        st.info("No strikes in this range.")
        st.button("Zoom out to all strikes", on_click=set_range, args=(all_strikes,))
        return
    st.plotly_chart(
        make_open_interest_figure(
            table, index_price=index_price, strike_range=strike_range, scope=scope,
        ),
        use_container_width=True,
    )
    gamma_exposure_section(chain, expiries, scope, index_price, strike_range)


def gamma_exposure_section(chain, expiries, scope, index_price, strike_range):
    """Net GEX by strike below OI, sharing its expiries, strike zoom and index line."""
    st.plotly_chart(
        make_gex_figure(
            net_gex_by_strike(chain, expiries),
            index_price=index_price, strike_range=strike_range, scope=scope,
            assumption=assumption_label(),
            oi_share=computable_oi_share(chain, expiries),
        ),
        use_container_width=True,
    )
    st.caption(
        "GEX per contract = s × gamma × OI × index² × 1%, from Exchange mark IV "
        "with the index and every forward moving 1% together. s = +1 where the "
        "customer sells (dealer long gamma), −1 where the customer buys. "
        "Known zero OI adds zero. A strike where some contracts lack OI or mark IV "
        "shows Incomplete data; one where none are computable shows Insufficient "
        "data. Neither is drawn as a bar."
    )


def fetch_latest_snapshot():
    """Fetch only on the button; a failure keeps the current snapshot."""
    if not st.button("Fetch latest", help="Pull a new snapshot from Deribit's public API."):
        return
    try:
        with st.spinner("Fetching from Deribit…"):
            fetched = fetch_deribit_snapshot()
            parse_deribit_snapshot(fetched)
    except (DeribitFetchError, ValueError, TypeError, AttributeError) as exc:
        st.error(f"Fetch failed; still showing the previous snapshot. {exc}")
        return
    st.session_state["snapshot"] = fetched
    st.session_state["snapshot_label"] = "Fetched snapshot"


def main():
    st.set_page_config(page_title="BTC volatility", layout="wide")
    st.markdown(
        """<style>
        .stMainBlockContainer {padding-top: 2rem; padding-bottom: 1rem;}
        .st-key-surface-responsive {container-type: inline-size;}
        .st-key-surface-narrow {display: none;}
        @container (max-width: 699px) {
            .st-key-surface-wide {display: none;}
            .st-key-surface-narrow {display: block;}
        }
        </style>""",
        unsafe_allow_html=True,
    )
    st.title("BTC volatility")
    fetch_latest_snapshot()
    snapshot = st.session_state.get("snapshot")
    snapshot_label = st.session_state.get("snapshot_label", "Frozen snapshot")
    # Catch input errors at the loading boundary, not errors in chart rendering.
    try:
        if snapshot is None:
            snapshot = load_deribit_snapshot(DATA_PATH / SNAPSHOT_FILE)
        chain = parse_deribit_snapshot(snapshot)
    except (OSError, ValueError, TypeError, RuntimeError, AttributeError):
        st.error("Cannot read the frozen Deribit snapshot. Check its file and schema.")
        return

    captured_at = datetime.fromisoformat(
        snapshot["captured_at_utc"].replace("Z", "+00:00")
    )
    st.caption(f"Deribit BTC · {snapshot_label}: {captured_at:%Y-%m-%d %H:%M:%S} UTC")
    open_interest_section(chain, snapshot["captured_at_utc"])
    st.subheader("Implied volatility")
    iv_source = iv_source_control()
    try:
        result = _iv_source_surface(chain, iv_source)
    except ValueError:
        st.error(
            "Cannot build IV: the snapshot needs valid, unique contracts and "
            "usable bid/ask quotes."
        )
        return

    expiry_dates = chain.drop_duplicates("tau").set_index("tau")["expiry_dt"]
    frame = iv_source_long_frame(
        result, expiry_datetimes=expiry_dates.reindex(result.expiries).tolist()
    )
    st.write(
        f"Shared spot: **${result.spot_price:,.2f}** · "
        f"IV source: **{iv_source}**"
    )
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
    with st.sidebar.expander("Combined IV coverage"):
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
    if not np.isfinite(frame["iv"]).any():
        st.warning("No IV solves succeeded for this snapshot.")

    st.sidebar.subheader("Surface views")
    range_name = st.sidebar.radio(
        "Moneyness range",
        list(MONEYNESS_RANGES),
        horizontal=True,
        help=(
            "Applies to Heatmap and 3D surface. IV smiles show all observed strikes."
        ),
    )
    min_moneyness, max_moneyness = MONEYNESS_RANGES[range_name]
    surface_frame = interpolate_surface_2d(
        frame,
        min_moneyness=min_moneyness,
        max_moneyness=max_moneyness,
    )
    observed_frame = surface_frame.copy()
    observed_frame["iv"] = observed_frame["observed_iv"]
    observed_frame["surface_value_type"] = np.where(
        np.isfinite(observed_frame["observed_iv"]), "Observed", "Missing"
    )
    surface_counts = surface_frame["surface_value_type"].value_counts()
    surface_summary = (
        "Visible range: "
        f"{surface_counts.get('Observed', 0):,} observed · "
        f"{surface_counts.get('Interpolated', 0):,} interpolated · "
        f"{surface_counts.get('Missing', 0):,} blank. "
        f"K / S: {min_moneyness:.1f}–{max_moneyness:.1f}."
    )
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

    heatmap_tab, surface_tab, smile_tab, atm_tab = st.tabs(
        ["Heatmap", "3D surface", "IV smiles", "ATM term structure"]
    )
    with heatmap_tab:
        heatmap_view = st.radio(
            "Heatmap values",
            ["Surface", "Observed"],
            horizontal=True,
            help=(
                "Surface uses 2D total-variance interpolation. Observed "
                "shows solved market IV without interpolation."
            ),
        )
        heatmap_frame = (
            surface_frame if heatmap_view == "Surface" else observed_frame
        )
        heatmap_counts = heatmap_frame["surface_value_type"].value_counts()
        st.caption(
            "Visible range: "
            f"{heatmap_counts.get('Observed', 0):,} observed · "
            f"{heatmap_counts.get('Interpolated', 0):,} interpolated · "
            f"{heatmap_counts.get('Missing', 0):,} blank. "
            f"K / S: {min_moneyness:.1f}–{max_moneyness:.1f}."
        )
        st.plotly_chart(
            make_iv_heatmap(
                heatmap_frame, equal_expiry_spacing=True, iv_source=iv_source
            ),
            use_container_width=True,
        )
    with surface_tab:
        st.caption(surface_summary)
        st.caption("2D total-variance interpolation · observed IV overlaid as points.")
        with st.container(key="surface-responsive"):
            for compact, key in [(False, "surface-wide"), (True, "surface-narrow")]:
                with st.container(key=key):
                    st.plotly_chart(
                        make_iv_surface_figure(
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
    with smile_tab:
        expiry_labels = {
            row.tau: row.expiry_datetime.strftime("%Y-%m-%d")
            for row in frame[["tau", "expiry_datetime"]]
            .dropna()
            .drop_duplicates("tau")
            .itertuples(index=False)
        }
        available_expiries = sorted(frame["tau"].unique())
        finite_expiries = sorted(
            frame.loc[np.isfinite(frame["iv"]), "tau"].unique()
        )
        with st.popover("Select expiries"):
            st.caption("Expiry (UTC)")
            selected_expiries = [
                tau for tau in available_expiries
                if st.checkbox(
                    expiry_labels.get(tau, f"tau={tau:g}"),
                    value=tau in finite_expiries[:3],
                    key=f"smile_expiry_{snapshot['captured_at_utc']}_{tau}",
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
                make_smile_figure(
                    frame, selected_expiries=selected_expiries, iv_source=iv_source
                ),
                use_container_width=True,
            )
        else:
            st.info("Select an expiry to show its IV smile.")
    with atm_tab:
        atm_frame = atm_term_structure_frame(frame)
        st.caption(
            f"Observed Combined {iv_source} IV nearest to spot within 2% · "
            "all expiries"
        )
        st.plotly_chart(
            make_atm_term_structure_figure(atm_frame, iv_source=iv_source),
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


if __name__ == "__main__":
    main()
