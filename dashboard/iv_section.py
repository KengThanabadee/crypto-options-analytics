"""Implied volatility: IV source, method notes and the three IV chart tabs.

Each tab is drawn by its own view module: surface, smiles, term structure.
"""

import numpy as np
import streamlit as st

from options_analytics import iv_source as iv_sources
from options_analytics.iv_source import IV_SOURCES, iv_source_long_frame

from dashboard import smile_view, surface_view, term_structure_view
from dashboard.settings import (
    HEATMAP_VALUES_KEY,
    IV_SOURCE_KEY,
    MONEYNESS_RANGE_KEY,
    SURFACE_VIEW_KEY,
    WIDGET_DEFAULTS,
    expiry_taus,
    smile_key,
)
from dashboard.state import keep_widget_values, widget_default


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
    default = WIDGET_DEFAULTS[IV_SOURCE_KEY]
    return st.segmented_control(
        "IV source",
        IV_SOURCES,
        default=widget_default(IV_SOURCE_KEY, default),
        required=True,
        key=IV_SOURCE_KEY,
        help=(
            "Exchange mark is the mark IV Deribit reports. Quote midpoint is "
            "our solver's IV from each contract's bid/ask midpoint, priced "
            "with the contract's reported forward (R = ln(F / X) / T). "
            "Changes the IV charts only."
        ),
    ) or default


def keep_iv_view_settings(chain, snapshot_id):
    """Hold the IV view settings on a run that cannot draw the IV charts.

    Keeps the user's surface view, moneyness range, heatmap values and smile
    expiries for Save and for when the charts return.
    """
    smile_keys = [smile_key(snapshot_id, tau) for tau in expiry_taus(chain)]
    keep_widget_values(
        [SURFACE_VIEW_KEY, MONEYNESS_RANGE_KEY, HEATMAP_VALUES_KEY, *smile_keys]
    )


def iv_section(chain, snapshot_id, sidebar):
    """IV charts from the selected IV source; a failed IV build keeps the IV settings.

    Method notes go into ``sidebar``, a container the page places in its
    sidebar.
    """
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
    with sidebar:
        _iv_method_notes(frame, iv_source)
    if not np.isfinite(frame["iv"]).any():
        st.warning("No IV solves succeeded for this snapshot.")

    surface_tab, smile_tab, atm_tab = st.tabs(
        ["IV surface", "IV smiles", "ATM term structure"]
    )
    with surface_tab:
        surface_view.surface_view(frame, iv_source)
    with smile_tab:
        smile_view.smile_view(frame, snapshot_id, iv_source)
    with atm_tab:
        term_structure_view.term_structure_view(frame, iv_source)


def _iv_method_notes(frame, iv_source):
    source = frame["source"]
    counts = (
        int(source.isin(["call", "put", "near_atm_average"]).sum()),
        int(source.isin(["near_atm_call_only", "near_atm_put_only"]).sum()),
        int(source.eq("missing").sum()),
    )
    st.subheader("Method notes")
    with st.expander(f"Combined IV coverage · {iv_source}"):
        for label, count in zip(
            ["Out of the money / averaged", "One-sided near spot", "Missing"], counts
        ):
            st.metric(label, f"{count:,}")
        st.caption(f"All {len(frame):,} expiry × strike grid cells.")
        st.caption(
            "Within 2% of spot, average same-strike Call and Put IV when both "
            "are available, else use the one that is. Outside that band, use "
            "only the out-of-the-money side, Put below spot and Call above; "
            "without it the cell stays missing."
        )
    with st.expander("Deribit pricing"):
        st.caption(
            "BTC bid/ask premiums are converted to USD using the snapshot's "
            "BTC/USD index X. Quote midpoint IV and the bid–ask band use our "
            "Black-Scholes solver with each contract's reported forward F, so "
            "R = ln(F / X) / T and no rate is chosen. A solve must reprice "
            "within $0.01 or it is missing, and a midpoint IV counts only when "
            "the bid and ask both solve too. Exchange mark IV is Deribit's own."
        )
