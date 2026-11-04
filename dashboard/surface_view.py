"""IV surface tab: View, Moneyness range and Heatmap values above one chart."""

import streamlit as st

from iv_surface import visualization
from iv_surface.surface_transforms import (
    HEATMAP_VALUES,
    MONEYNESS_RANGES,
    SURFACE_VIEWS,
    interpolate_surface_2d,
    observed_surface_frame,
)

from dashboard.settings import HEATMAP_VALUES_KEY, MONEYNESS_RANGE_KEY, SURFACE_VIEW_KEY
from dashboard.state import widget_default


# The 3D chart is drawn twice, wide and compact; a container query on the
# tab width shows one of them.
_SURFACE_LAYOUT_CSS = """<style>
        .st-key-surface-responsive {container-type: inline-size;}
        .st-key-surface-narrow {display: none;}
        @container (max-width: 699px) {
            .st-key-surface-wide {display: none;}
            .st-key-surface-narrow {display: block;}
        }</style>"""


def surface_view(frame, iv_source):
    """The IV surface as a Heatmap or in 3D, over the chosen K / S range."""
    view_column, range_column, values_column = st.columns(3)
    with view_column:
        view = _choice(
            "View", SURFACE_VIEWS, SURFACE_VIEW_KEY,
            help="Two views of the same interpolated surface.",
        )
    with range_column:
        range_name = _choice(
            "Moneyness range", list(MONEYNESS_RANGES), MONEYNESS_RANGE_KEY,
            help="Applies to both views. IV smiles show all observed strikes.",
        )
    if view == "Heatmap":
        with values_column:
            heatmap_values = _choice(
                "Heatmap values", HEATMAP_VALUES, HEATMAP_VALUES_KEY,
                help=(
                    "Surface uses 2D total-variance interpolation. Observed "
                    "shows solved market IV without interpolation."
                ),
            )
    else:
        _keep_heatmap_values()

    moneyness = MONEYNESS_RANGES[range_name]
    surface_frame = interpolate_surface_2d(
        frame, min_moneyness=moneyness[0], max_moneyness=moneyness[1]
    )
    if view == "Heatmap":
        shown = (
            surface_frame if heatmap_values == "Surface"
            else observed_surface_frame(surface_frame)
        )
        st.caption(visible_range_summary(shown, moneyness))
        _heatmap_chart(shown, iv_source)
    else:
        st.caption(visible_range_summary(surface_frame, moneyness))
        st.caption("2D total-variance interpolation · observed IV overlaid as points.")
        _surface_3d_chart(surface_frame, iv_source)
    _interpolation_notes()


def _interpolation_notes():
    with st.expander("Surface interpolation"):
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


def visible_range_summary(frame, moneyness):
    counts = frame["surface_value_type"].value_counts()
    return (
        "Visible range: "
        f"{counts.get('Observed', 0):,} observed · "
        f"{counts.get('Interpolated', 0):,} interpolated · "
        f"{counts.get('Missing', 0):,} blank. "
        f"K / S: {moneyness[0]:.1f}–{moneyness[1]:.1f}."
    )


def _choice(label, options, key, help):
    """A required segmented control whose first option is the default."""
    default = options[0]
    return st.segmented_control(
        label,
        options,
        default=widget_default(key, default),
        required=True,
        key=key,
        help=help,
    ) or default


def _keep_heatmap_values():
    """Hold Heatmap values while 3D hides it; Streamlit drops undrawn widgets."""
    if HEATMAP_VALUES_KEY in st.session_state:
        st.session_state[HEATMAP_VALUES_KEY] = st.session_state[HEATMAP_VALUES_KEY]


def _heatmap_chart(heatmap_frame, iv_source):
    st.plotly_chart(
        visualization.make_iv_heatmap(
            heatmap_frame, equal_expiry_spacing=True, iv_source=iv_source
        ),
        width="stretch",
    )


def _surface_3d_chart(surface_frame, iv_source):
    """3D surface with observed IV as points, in a wide and a compact layout."""
    st.markdown(_SURFACE_LAYOUT_CSS, unsafe_allow_html=True)
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
                    width="stretch",
                    config={"modeBarButtonsToRemove": ["resetCameraDefault3d"]},
                )
    st.markdown(
        '<div aria-hidden="true" style="height: 32px"></div>',
        unsafe_allow_html=True,
    )
