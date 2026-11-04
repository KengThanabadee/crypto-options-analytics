"""Offline BTC volatility dashboard. Run with streamlit run app.py.

Each section of the page lives in ``dashboard/``; this file lays them out.
"""

from datetime import datetime
from pathlib import Path

import streamlit as st

from iv_surface import deribit, visualization

from dashboard.iv_section import iv_section
from dashboard.positioning_section import positioning_section
from dashboard.snapshot_controls import (
    fetch_latest_snapshot,
    reopen_saved_analysis,
    save_analysis_control,
)
from dashboard.state import start_run
from dashboard.surface_view import SURFACE_LAYOUT_CSS


DATA_PATH = Path(__file__).resolve().parent / "data"
SNAPSHOT_FILE = "deribit_btc_options_snapshot.json"


def main():
    st.set_page_config(page_title="BTC volatility", layout="wide")
    st.markdown(
        "<style>.stMainBlockContainer {padding-top: 2rem; padding-bottom: 1rem;}"
        f"{SURFACE_LAYOUT_CSS}</style>",
        unsafe_allow_html=True,
    )
    st.title("BTC volatility")
    start_run()
    header, fetch_column = st.columns([6, 1], vertical_alignment="center")
    # Fetch before the snapshot is read, so a fetch updates the header this run.
    fetch_latest_snapshot(fetch_column)
    with st.sidebar:
        st.subheader("Saved analysis")
        reopen_saved_analysis()
        save_slot = st.container()
        iv_notes_slot = st.container()
    snapshot = st.session_state.get("snapshot")
    chain = st.session_state.get("chain")
    snapshot_label = st.session_state.get("snapshot_label", "Frozen snapshot")
    # Catch input errors at the loading boundary, not errors in chart rendering.
    try:
        if snapshot is None:
            snapshot = deribit.load_deribit_snapshot(DATA_PATH / SNAPSHOT_FILE)
            chain = deribit.parse_deribit_snapshot(snapshot)
    except (OSError, ValueError, TypeError, RuntimeError, AttributeError):
        st.error("Cannot read the frozen Deribit snapshot. Check its file and schema.")
        return

    captured_at = datetime.fromisoformat(
        snapshot["captured_at_utc"].replace("Z", "+00:00")
    )
    index_price = float(chain["index_price"].iloc[0])
    header.caption(
        f"Deribit BTC · {snapshot_label}: {captured_at:%Y-%m-%d %H:%M:%S} UTC"
        f" · {visualization.index_label(index_price)}"
    )
    if "reopen_notice" in st.session_state:
        st.info(st.session_state["reopen_notice"])
    positioning_section(chain, snapshot["captured_at_utc"])
    iv_section(chain, snapshot["captured_at_utc"], sidebar=iv_notes_slot)
    save_analysis_control(save_slot, snapshot, chain)


if __name__ == "__main__":
    main()
