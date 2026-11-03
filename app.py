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
    solve_bid_ask_iv,
)
from iv_surface.positioning import (
    DEFAULT_SIGNS,
    GEX_MODES,
    assumption_label,
    computable_oi_share,
    expiry_scope_label,
    near_spot_range,
    net_gex_by_strike,
    open_interest_by_strike,
    strike_zoom_bounds,
    strikes_in_range,
)
from iv_surface.saved_analysis import open_analysis, save_analysis
from iv_surface.surface_transforms import (
    HEATMAP_VALUES,
    MONEYNESS_RANGES,
    atm_term_structure_frame,
    interpolate_surface_2d,
)
from iv_surface.visualization import (
    make_atm_term_structure_figure,
    make_iv_heatmap,
    make_iv_surface_figure,
    make_positioning_figure,
    make_smile_figure,
)


DATA_PATH = Path(__file__).resolve().parent / "data"
SNAPSHOT_FILE = "deribit_btc_options_snapshot.json"


@st.cache_data(show_spinner="Solving bid/ask IV…", max_entries=4)
def _bid_ask_iv(chain):
    return solve_bid_ask_iv(chain)


@st.cache_data(show_spinner="Building IV…", max_entries=8)
def _iv_source_surface(chain, iv_source):
    return build_iv_source_surface(chain, iv_source, bid_ask_iv=_bid_ask_iv(chain))


def iv_source_control():
    """IV source for the IV charts only; switching reuses the loaded snapshot."""
    return st.segmented_control(
        "IV source",
        IV_SOURCES,
        default=_default_unless_set("iv_source", DEFAULT_IV_SOURCE),
        required=True,
        key="iv_source",
        help=(
            "Exchange mark is the mark IV Deribit reports. Quote midpoint is "
            "our solver's IV from each contract's bid/ask midpoint, priced "
            "with the contract's reported forward (R = ln(F / X) / T). "
            "Changes the IV charts only."
        ),
    ) or DEFAULT_IV_SOURCE


def positioning_section(chain, snapshot_id):
    """OI and GEX by strike in one figure, sharing expiries, strike zoom and axis.

    Widget keys carry the snapshot id so a new snapshot starts at All
    expiries, its own Near spot range and the default GEX scenario. Every
    control renders before the chart, so an empty range keeps their values.
    """
    range_key = f"oi_strike_range_{snapshot_id}"
    st.subheader("Open interest and gamma exposure")
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
    oi_table = open_interest_by_strike(chain, expiries)

    near_spot = near_spot_range(index_price)
    all_strikes = strike_zoom_bounds(chain)
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
            format="$%,.0f",
            key=range_key,
            help="Display zoom only. OI and GEX use every strike in the selected expiries.",
        )
    with reset_column:
        st.button("Near spot", on_click=set_range, args=(near_spot,),
                  help="Reset to ±10% around the index.")
    signs, mode = gex_scenario_controls(snapshot_id)
    st.caption(
        f"Open interest · {scope} · Call and Put in BTC · "
        f"index ${index_price:,.2f}"
    )
    if strikes_in_range(oi_table, strike_range).empty:
        st.info("No strikes in this range.")
        st.button("Zoom out to all strikes", on_click=set_range, args=(all_strikes,))
        return
    gex_table = net_gex_by_strike(chain, expiries, signs=signs)
    st.plotly_chart(
        make_positioning_figure(
            oi_table, gex_table, index_price=index_price, strike_range=strike_range,
            scope=scope, assumption=assumption_label(signs),
            oi_share=computable_oi_share(gex_table), mode=mode,
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


CUSTOMER_SIDES = {"Customer sells": 1, "Customer buys": -1}
SIDE_OF_SIGN = {sign: side for side, sign in CUSTOMER_SIDES.items()}


def gex_scenario_controls(snapshot_id):
    """Customer side per option type and Net/Gross; a new snapshot starts at the defaults."""
    defaults = {flag: SIDE_OF_SIGN[sign] for flag, sign in DEFAULT_SIGNS.items()}
    columns = st.columns(3)
    signs = {}
    for column, flag in zip(columns, ("call", "put")):
        with column:
            side = st.segmented_control(
                f"{flag.capitalize()}s",
                list(CUSTOMER_SIDES),
                default=_default_unless_set(f"gex_{flag}_side_{snapshot_id}", defaults[flag]),
                required=True,
                key=f"gex_{flag}_side_{snapshot_id}",
                help=(
                    f"Scenario for every {flag} in the analysed set, with the dealer "
                    "as counterparty: customer sells → dealer long gamma (+); "
                    "customer buys → dealer short gamma (−)."
                ),
            ) or defaults[flag]
        signs[flag] = CUSTOMER_SIDES[side]
    with columns[2]:
        mode = st.segmented_control(
            "GEX view",
            GEX_MODES,
            default=_default_unless_set(f"gex_mode_{snapshot_id}", "Net"),
            required=True,
            key=f"gex_mode_{snapshot_id}",
            help="Net lets Calls and Puts cancel. Gross adds magnitudes and ignores the scenario.",
        ) or "Net"
    return signs, mode


def _default_unless_set(key, default):
    """A widget default, or None once its value is set in session state.

    Reopening sets widget values through session state; passing a default too
    would make Streamlit warn about the conflict.
    """
    return None if key in st.session_state else default


def _smile_key(snapshot_id, tau):
    return f"smile_expiry_{snapshot_id}_{tau}"


def _expiry_taus(chain):
    return chain.drop_duplicates("expiry_dt").set_index("expiry_dt")["tau"]


def current_settings(chain, snapshot_id):
    """The analysis settings as the widgets hold them, with defaults for unshown ones."""
    state = st.session_state
    taus = _expiry_taus(chain)
    expiry_of = {tau: expiry for expiry, tau in taus.items()}
    signs = {
        flag: CUSTOMER_SIDES[
            state.get(f"gex_{flag}_side_{snapshot_id}") or SIDE_OF_SIGN[DEFAULT_SIGNS[flag]]
        ]
        for flag in ("call", "put")
    }
    return {
        "oi_expiries": [expiry_of[tau] for tau in state.get(f"oi_expiries_{snapshot_id}") or []],
        "strike_range": state.get(
            f"oi_strike_range_{snapshot_id}",
            near_spot_range(float(chain["index_price"].iloc[0])),
        ),
        "signs": signs,
        "gex_view": state.get(f"gex_mode_{snapshot_id}") or "Net",
        "iv_source": state.get("iv_source") or DEFAULT_IV_SOURCE,
        "moneyness_range": MONEYNESS_RANGES[
            state.get("moneyness_range", next(iter(MONEYNESS_RANGES)))
        ],
        "heatmap_values": state.get("heatmap_view", HEATMAP_VALUES[0]),
        "smile_expiries": [
            expiry for expiry, tau in taus.items()
            if state.get(_smile_key(snapshot_id, tau), False)
        ],
    }


def keep_iv_view_settings(chain, snapshot_id):
    """Hold the IV view settings on a run that cannot draw the IV charts.

    Streamlit drops a widget's value on any run that does not draw it.
    Writing each value back as session state keeps the user's moneyness range,
    heatmap values and smile expiries for Save and for when the charts return.
    """
    state = st.session_state
    smile_keys = [_smile_key(snapshot_id, tau) for tau in _expiry_taus(chain)]
    for key in ["moneyness_range", "heatmap_view", *smile_keys]:
        if key in state:
            state[key] = state[key]


def save_analysis_control(slot, snapshot, chain):
    """Download the raw snapshot with the current settings as one file."""
    captured_at = snapshot["captured_at_utc"]
    stamp = captured_at[:19].replace(":", "").replace("-", "")
    with slot:
        st.download_button(
            "Save analysis",
            data=save_analysis(snapshot, current_settings(chain, captured_at)),
            file_name=f"deribit-btc-analysis-{stamp}Z.json",
            mime="application/json",
            on_click="ignore",
            help="One file with the raw snapshot and every setting; no computed numbers.",
        )


def reopen_saved_analysis():
    """Reopen a saved file once per upload; an invalid file keeps the current analysis."""
    uploaded = st.file_uploader(
        "Reopen analysis", type=["json"], key="saved_analysis_file",
        help="Recomputes every number from the saved raw snapshot.",
    )
    if uploaded is None or st.session_state.get("reopened_file_id") == uploaded.file_id:
        return
    st.session_state["reopened_file_id"] = uploaded.file_id
    try:
        saved = open_analysis(uploaded.getvalue())
    except ValueError as exc:
        st.error(f"Cannot open {uploaded.name}; still showing the current analysis. {exc}")
        return
    snapshot_id = saved.snapshot["captured_at_utc"]
    taus = _expiry_taus(saved.chain)
    settings = saved.settings
    range_name = {value: name for name, value in MONEYNESS_RANGES.items()}
    widget_values = {
        f"oi_expiries_{snapshot_id}": [float(taus[e]) for e in settings["oi_expiries"]],
        f"oi_strike_range_{snapshot_id}": settings["strike_range"],
        f"gex_call_side_{snapshot_id}": SIDE_OF_SIGN[settings["signs"]["call"]],
        f"gex_put_side_{snapshot_id}": SIDE_OF_SIGN[settings["signs"]["put"]],
        f"gex_mode_{snapshot_id}": settings["gex_view"],
        "iv_source": settings["iv_source"],
        "moneyness_range": range_name[settings["moneyness_range"]],
        "heatmap_view": settings["heatmap_values"],
    }
    smiles = set(settings["smile_expiries"])
    for expiry, tau in taus.items():
        widget_values[_smile_key(snapshot_id, tau)] = expiry in smiles
    st.session_state.update(widget_values)
    _use_snapshot(saved.snapshot, saved.chain, "Reopened snapshot")
    if saved.version_differs:
        st.session_state["reopen_notice"] = saved.version_notice()
    else:
        st.session_state.pop("reopen_notice", None)


def fetch_latest_snapshot():
    """Fetch only on the button; a failure keeps the current snapshot."""
    if not st.button("Fetch latest", help="Pull a new snapshot from Deribit's public API."):
        return
    try:
        with st.spinner("Fetching from Deribit…"):
            fetched = fetch_deribit_snapshot()
            chain = parse_deribit_snapshot(fetched)
    except (DeribitFetchError, ValueError, TypeError, AttributeError) as exc:
        st.error(f"Fetch failed; still showing the previous snapshot. {exc}")
        return
    _use_snapshot(fetched, chain, "Fetched snapshot")
    st.session_state.pop("reopen_notice", None)


def _use_snapshot(snapshot, chain, label):
    """Switch the page to a snapshot, keeping its parsed chain for every rerun."""
    st.session_state["snapshot"] = snapshot
    st.session_state["chain"] = chain
    st.session_state["snapshot_label"] = label


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
    with st.sidebar:
        st.subheader("Saved analysis")
        reopen_saved_analysis()
        save_slot = st.container()
    snapshot = st.session_state.get("snapshot")
    chain = st.session_state.get("chain")
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
    if "reopen_notice" in st.session_state:
        st.info(st.session_state["reopen_notice"])
    positioning_section(chain, snapshot["captured_at_utc"])
    st.subheader("Implied volatility")
    iv_source = iv_source_control()
    try:
        result = _iv_source_surface(chain, iv_source)
    except ValueError:
        st.error(
            "Cannot build IV: the snapshot needs valid, unique contracts and "
            "usable bid/ask quotes."
        )
        keep_iv_view_settings(chain, snapshot["captured_at_utc"])
        save_analysis_control(save_slot, snapshot, chain)
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
        key="moneyness_range",
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
            HEATMAP_VALUES,
            horizontal=True,
            key="heatmap_view",
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
                    value=_default_unless_set(
                        _smile_key(snapshot["captured_at_utc"], tau),
                        tau in finite_expiries[:3],
                    ) or False,
                    key=_smile_key(snapshot["captured_at_utc"], tau),
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
    save_analysis_control(save_slot, snapshot, chain)


if __name__ == "__main__":
    main()
