"""IV surface: moneyness range, Heatmap and 3D surface of the interpolated IV."""

import streamlit as st

from iv_surface import visualization
from iv_surface.surface_transforms import (
    HEATMAP_VALUES,
    MONEYNESS_RANGES,
    observed_surface_frame,
)

from dashboard.settings import HEATMAP_VALUES_KEY, MONEYNESS_RANGE_KEY


# The 3D chart is drawn twice, wide and compact; a container query on the
# page width shows one of them.
SURFACE_LAYOUT_CSS = """
        .st-key-surface-responsive {container-type: inline-size;}
        .st-key-surface-narrow {display: none;}
        @container (max-width: 699px) {
            .st-key-surface-wide {display: none;}
            .st-key-surface-narrow {display: block;}
        }"""


def moneyness_range_control():
    """The chosen K / S range as (low, high)."""
    range_name = st.radio(
        "Moneyness range",
        list(MONEYNESS_RANGES),
        horizontal=True,
        key=MONEYNESS_RANGE_KEY,
        help=(
            "Applies to Heatmap and 3D surface. IV smiles show all observed strikes."
        ),
    )
    return MONEYNESS_RANGES[range_name]


def interpolation_notes():
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


def heatmap_view(surface_frame, moneyness, iv_source):
    """Heatmap of the interpolated surface, or of observed IV only."""
    heatmap_values = st.radio(
        "Heatmap values",
        HEATMAP_VALUES,
        horizontal=True,
        key=HEATMAP_VALUES_KEY,
        help=(
            "Surface uses 2D total-variance interpolation. Observed "
            "shows solved market IV without interpolation."
        ),
    )
    heatmap_frame = (
        surface_frame if heatmap_values == "Surface"
        else observed_surface_frame(surface_frame)
    )
    st.caption(visible_range_summary(heatmap_frame, moneyness))
    st.plotly_chart(
        visualization.make_iv_heatmap(
            heatmap_frame, equal_expiry_spacing=True, iv_source=iv_source
        ),
        width="stretch",
    )


def surface_3d_view(surface_frame, moneyness, iv_source):
    """3D surface with observed IV as points, in a wide and a compact layout."""
    st.caption(visible_range_summary(surface_frame, moneyness))
    st.caption("2D total-variance interpolation · observed IV overlaid as points.")
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
