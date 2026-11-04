"""IV smiles: observed Combined IV by strike for the chosen expiries."""

import numpy as np
import streamlit as st

from iv_surface import visualization

from dashboard.settings import smile_key
from dashboard.state import widget_default


def smile_view(frame, snapshot_id, iv_source):
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
    if selected_expiries:
        st.plotly_chart(
            visualization.make_smile_figure(
                frame, selected_expiries=selected_expiries, iv_source=iv_source
            ),
            width="stretch",
        )
    else:
        st.info("Select an expiry to show its IV smile.")
    st.caption(
        f"Observed Combined {iv_source} IV · all strikes · gaps preserved · "
        "shading = bid–ask IV band"
    )
    with st.expander("Smile shading"):
        st.caption(
            "Shading is a bid–ask IV display band from our solver, blended with the "
            "line's Call/Put weights; it is not a tradable quote, and mark IV may sit "
            "outside it."
        )
