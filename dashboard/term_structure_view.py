"""ATM term structure: the ATM proxy IV across expiries."""

import streamlit as st

from options_analytics import visualization
from options_analytics.surface_transforms import atm_term_structure_frame


def term_structure_view(frame, iv_source):
    atm_frame = atm_term_structure_frame(frame)
    st.caption(
        f"Observed Combined {iv_source} IV nearest to spot within 2% · "
        "all expiries"
    )
    st.plotly_chart(
        visualization.make_atm_term_structure_figure(atm_frame, iv_source=iv_source),
        width="stretch",
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
            width="stretch",
        )
