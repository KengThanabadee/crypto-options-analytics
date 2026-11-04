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

from dashboard.settings import (
    HEATMAP_VALUES_KEY,
    MONEYNESS_RANGE_KEY,
    SURFACE_VIEW_KEY,
    WIDGET_DEFAULTS,
)
from dashboard.state import keep_widget_values, widget_default


# The 3D chart is drawn twice, wide and compact; a container query on the
# tab width shows one of them.
_SURFACE_LAYOUT_CSS = """<style>
        .st-key-surface-responsive {container-type: inline-size;}
        .st-key-surface-narrow {display: none;}
        @container (max-width: 699px) {
            .st-key-surface-wide {display: none;}
            .st-key-surface-narrow {display: block;}
        }</style>"""


HEATMAP, VIEW_3D = SURFACE_VIEWS
SURFACE_VALUES, OBSERVED_VALUES = HEATMAP_VALUES
SURFACE_CAPTION = (
    "2D total-variance interpolation · observed IV unchanged · "
    "blank outside the observed range"
)
OBSERVED_CAPTION = (
    "Observed IV only · no interpolation · blank where no contract was solved"
)


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
    moneyness = MONEYNESS_RANGES[range_name]
    surface_frame = interpolate_surface_2d(
        frame, min_moneyness=moneyness[0], max_moneyness=moneyness[1]
    )

    if view == HEATMAP:
        with values_column:
            heatmap_values = _choice(
                "Heatmap values", HEATMAP_VALUES, HEATMAP_VALUES_KEY,
                help=(
                    "Surface uses 2D total-variance interpolation. Observed "
                    "shows solved market IV without interpolation."
                ),
            )
        observed_only = heatmap_values == OBSERVED_VALUES
        if observed_only:
            surface_frame = observed_surface_frame(surface_frame)
        st.caption(visible_range_summary(surface_frame, moneyness))
        _heatmap_chart(surface_frame, iv_source)
    else:
        observed_only = False
        keep_widget_values([HEATMAP_VALUES_KEY])
        st.caption(visible_range_summary(surface_frame, moneyness))
        _surface_3d_chart(surface_frame, iv_source)
    st.caption(OBSERVED_CAPTION if observed_only else SURFACE_CAPTION)
    _interpolation_notes()


def _interpolation_notes():
    with st.expander("Surface interpolation"):
        st.caption(
            "Convert observed IV to total variance (IV² × tau), linearly "
            "interpolate it between observations, then convert back to IV. "
            "K / S and tau are each scaled to their observed range for "
            "triangulation. Original IV points stay unchanged."
        )
        st.caption(
            "The existing grid is filled only inside the convex hull of "
            "observations in the selected range. A cell can be filled across "
            "expiries, but cells outside that boundary stay blank. "
            "A denser grid would add display points, not market observations."
        )
        st.caption(
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
    """A required segmented control, defaulting to the setting's default."""
    default = WIDGET_DEFAULTS[key]
    return st.segmented_control(
        label,
        options,
        default=widget_default(key, default),
        required=True,
        key=key,
        help=help,
    ) or default


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
