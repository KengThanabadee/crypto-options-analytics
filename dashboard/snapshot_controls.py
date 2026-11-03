"""Fetch latest, Save analysis and Reopen analysis: how a snapshot reaches the page."""

import streamlit as st

from iv_surface import deribit
from iv_surface.iv_source import DEFAULT_IV_SOURCE
from iv_surface.positioning import DEFAULT_SIGNS, near_spot_range
from iv_surface.saved_analysis import open_analysis, save_analysis
from iv_surface.surface_transforms import HEATMAP_VALUES, MONEYNESS_RANGES

from dashboard.positioning_section import CUSTOMER_SIDES, SIDE_OF_SIGN
from dashboard.state import expiry_taus, set_widget_values, smile_key, use_snapshot


def current_settings(chain, snapshot_id):
    """The analysis settings as the widgets hold them, with defaults for unshown ones."""
    state = st.session_state
    taus = expiry_taus(chain)
    expiry_of = {tau: expiry for expiry, tau in taus.items()}
    signs = {
        flag: CUSTOMER_SIDES[
            state.get(f"gex_{flag}_side") or SIDE_OF_SIGN[DEFAULT_SIGNS[flag]]
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
        "gex_view": state.get("gex_mode") or "Net",
        "iv_source": state.get("iv_source") or DEFAULT_IV_SOURCE,
        "moneyness_range": MONEYNESS_RANGES[
            state.get("moneyness_range", next(iter(MONEYNESS_RANGES)))
        ],
        "heatmap_values": state.get("heatmap_view", HEATMAP_VALUES[0]),
        "smile_expiries": [
            expiry for expiry, tau in taus.items()
            if state.get(smile_key(snapshot_id, tau), False)
        ],
    }


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
    taus = expiry_taus(saved.chain)
    settings = saved.settings
    range_name = {value: name for name, value in MONEYNESS_RANGES.items()}
    widget_values = {
        f"oi_expiries_{snapshot_id}": [float(taus[e]) for e in settings["oi_expiries"]],
        f"oi_strike_range_{snapshot_id}": settings["strike_range"],
        "gex_call_side": SIDE_OF_SIGN[settings["signs"]["call"]],
        "gex_put_side": SIDE_OF_SIGN[settings["signs"]["put"]],
        "gex_mode": settings["gex_view"],
        "iv_source": settings["iv_source"],
        "moneyness_range": range_name[settings["moneyness_range"]],
        "heatmap_view": settings["heatmap_values"],
    }
    smiles = set(settings["smile_expiries"])
    for expiry, tau in taus.items():
        widget_values[smile_key(snapshot_id, tau)] = expiry in smiles
    set_widget_values(widget_values)
    use_snapshot(saved.snapshot, saved.chain, "Reopened snapshot")
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
            fetched = deribit.fetch_deribit_snapshot()
            chain = deribit.parse_deribit_snapshot(fetched)
    except (deribit.DeribitFetchError, ValueError, TypeError, AttributeError) as exc:
        st.error(f"Fetch failed; still showing the previous snapshot. {exc}")
        return
    use_snapshot(fetched, chain, "Fetched snapshot")
    st.session_state.pop("reopen_notice", None)
