"""Session state shared by the dashboard sections."""

import streamlit as st


_WRITTEN_KEYS = "_widget_keys_written_this_run"


def start_run():
    """Forget the widget values written on the previous run."""
    st.session_state.pop(_WRITTEN_KEYS, None)


def set_widget_values(values):
    """Set widget values through session state, e.g. on reopen or fetch."""
    st.session_state.update(values)
    st.session_state.setdefault(_WRITTEN_KEYS, set()).update(values)


def keep_widget_values(keys):
    """Hold the values of widgets not drawn on this run.

    Streamlit drops a widget's value on any run that does not draw it;
    writing the value back as session state keeps it.
    """
    state = st.session_state
    for key in keys:
        if key in state:
            state[key] = state[key]


def widget_default(key, default):
    """The default to send with a widget: the value it holds, else ``default``.

    The browser shows a widget's sent default whenever it mounts without its
    own state (a checkbox inside a closed popover), so the default must be the
    value the page uses. A value just set through session state already
    reaches the browser; passing it again as a default makes Streamlit warn,
    so those widgets get None.
    """
    if key in st.session_state.get(_WRITTEN_KEYS, ()):
        return None
    return st.session_state.get(key, default)


def use_snapshot(snapshot, chain, label):
    """Switch the page to a snapshot, keeping its parsed chain for every rerun."""
    st.session_state["snapshot"] = snapshot
    st.session_state["chain"] = chain
    st.session_state["snapshot_label"] = label
