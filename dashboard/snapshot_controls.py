"""Fetch latest, Save analysis and Reopen analysis: how a snapshot reaches the page."""

import streamlit as st

from iv_surface import deribit
from iv_surface.saved_analysis import open_analysis, save_analysis

from dashboard.settings import settings_from_widgets, widgets_from_settings
from dashboard.state import set_widget_values, use_snapshot


def save_analysis_control(slot, snapshot, chain):
    """Download the raw snapshot with the current settings as one file."""
    captured_at = snapshot["captured_at_utc"]
    stamp = captured_at[:19].replace(":", "").replace("-", "")
    with slot:
        st.download_button(
            "Save analysis",
            data=save_analysis(
                snapshot, settings_from_widgets(st.session_state, chain, captured_at)
            ),
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
    set_widget_values(widgets_from_settings(saved.settings, saved.chain, snapshot_id))
    use_snapshot(saved.snapshot, saved.chain, "Reopened snapshot")
    if saved.version_differs:
        st.session_state["reopen_notice"] = saved.version_notice()
    else:
        st.session_state.pop("reopen_notice", None)


def fetch_latest_snapshot(button_slot):
    """Fetch only on the button in ``button_slot``; a failure keeps the current snapshot.

    The spinner and any error show at full width below the slot.
    """
    if not button_slot.button(
        "Fetch latest", help="Pull a new snapshot from Deribit's public API."
    ):
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
