"""Open interest and GEX by strike, sharing expiries, strike zoom and axis."""

import streamlit as st

from iv_surface import visualization
from iv_surface.positioning import (
    DEFAULT_SIGNS,
    GEX_MODES,
    assumption_label,
    computable_oi_share,
    expiry_scope_label,
    near_spot_range,
    net_gex_by_strike,
    open_interest_by_strike,
    STRIKE_RANGE_STEP,
    strike_range_from_selection,
    strike_zoom_bounds,
    strikes_in_range,
)

from dashboard.state import widget_default


POSITIONING_CHART_KEY = "positioning_chart"
CUSTOMER_SIDES = {"Customer sells": 1, "Customer buys": -1}
SIDE_OF_SIGN = {sign: side for side, sign in CUSTOMER_SIDES.items()}


def positioning_section(chain, snapshot_id):
    """OI and GEX by strike in one figure, sharing expiries, strike zoom and axis.

    The expiry and strike range keys carry the snapshot id, so a new snapshot
    starts at All expiries and its own Near spot range; the GEX scenario and
    view carry over. Every control renders before the chart, so an empty
    range keeps their values.
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

    def zoom_to_dragged_strikes():
        # Streamlit redraws a changed figure from scratch, so a drag on the
        # chart sets the strike range, which every rerun keeps.
        selection = st.session_state[POSITIONING_CHART_KEY].selection
        dragged = strike_range_from_selection(selection.box, all_strikes)
        if dragged is not None:
            set_range(dragged)

    range_column, reset_column = st.columns([5, 1], vertical_alignment="bottom")
    with range_column:
        strike_range = st.slider(
            "Strike range (USD)",
            min_value=all_strikes[0],
            max_value=all_strikes[1],
            step=STRIKE_RANGE_STEP,
            format="$%,.0f",
            key=range_key,
            help=(
                "Display zoom only; drag across the chart to zoom too. OI and GEX "
                "use every strike in the selected expiries."
            ),
        )
    with reset_column:
        st.button("Near spot", on_click=set_range, args=(near_spot,),
                  help="Reset to ±10% around the index.")
    signs, mode = gex_scenario_controls()
    if strikes_in_range(oi_table, strike_range).empty:
        st.info("No strikes in this range.")
        st.button("Zoom out to all strikes", on_click=set_range, args=(all_strikes,))
        return
    gex_table = net_gex_by_strike(chain, expiries, signs=signs)
    st.plotly_chart(
        visualization.make_positioning_figure(
            oi_table, gex_table, index_price=index_price, strike_range=strike_range,
            scope=scope, assumption=assumption_label(signs),
            oi_share=computable_oi_share(gex_table), mode=mode,
        ),
        use_container_width=True,
        key=POSITIONING_CHART_KEY,
        on_select=zoom_to_dragged_strikes,
        selection_mode="box",
        config={"modeBarButtonsToRemove": [
            "zoom2d", "pan2d", "zoomIn2d", "zoomOut2d", "autoScale2d", "resetScale2d",
        ]},
    )
    st.caption(
        "GEX per contract = s × gamma × OI × index² × 1%, from Exchange mark IV "
        "with the index and every forward moving 1% together. s = +1 where the "
        "customer sells (dealer long gamma), −1 where the customer buys. "
        "Known zero OI adds zero. A strike where some contracts lack OI or mark IV "
        "shows Incomplete data; one where none are computable shows Insufficient "
        "data. Neither is drawn as a bar."
    )


def gex_scenario_controls():
    """Customer side per option type and Net/Gross; a new snapshot keeps them."""
    defaults = {flag: SIDE_OF_SIGN[sign] for flag, sign in DEFAULT_SIGNS.items()}
    columns = st.columns(3)
    signs = {}
    for column, flag in zip(columns, ("call", "put")):
        with column:
            side = st.segmented_control(
                f"{flag.capitalize()}s",
                list(CUSTOMER_SIDES),
                default=widget_default(f"gex_{flag}_side", defaults[flag]),
                required=True,
                key=f"gex_{flag}_side",
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
            default=widget_default("gex_mode", "Net"),
            required=True,
            key="gex_mode",
            help="Net lets Calls and Puts cancel. Gross adds magnitudes and ignores the scenario.",
        ) or "Net"
    return signs, mode
