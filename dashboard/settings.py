"""Saved analysis settings: each one's widget keys and its conversions both ways.

Save reads the settings from the widgets with ``settings_from_widgets``;
Reopen turns saved settings back into widget values with
``widgets_from_settings``. Adding a saved setting means adding one row to
``SETTINGS`` (and its name to ``saved_analysis``).
"""

from dataclasses import dataclass
from typing import Callable

from iv_surface.iv_source import DEFAULT_IV_SOURCE
from iv_surface.positioning import DEFAULT_SIGNS, near_spot_range
from iv_surface.surface_transforms import HEATMAP_VALUES, MONEYNESS_RANGES, SURFACE_VIEWS


CUSTOMER_SIDES = {"Customer sells": 1, "Customer buys": -1}
SIDE_OF_SIGN = {sign: side for side, sign in CUSTOMER_SIDES.items()}

GEX_VIEW_KEY = "gex_mode"
IV_SOURCE_KEY = "iv_source"
MONEYNESS_RANGE_KEY = "moneyness_range"
HEATMAP_VALUES_KEY = "heatmap_view"
SURFACE_VIEW_KEY = "surface_view"


def oi_expiries_key(snapshot_id):
    return f"oi_expiries_{snapshot_id}"


def strike_range_key(snapshot_id):
    return f"oi_strike_range_{snapshot_id}"


def customer_side_key(flag):
    return f"gex_{flag}_side"


def smile_key(snapshot_id, tau):
    return f"smile_expiry_{snapshot_id}_{tau}"


def expiry_taus(chain):
    """Each expiry datetime in the chain with its tau."""
    return chain.drop_duplicates("expiry_dt").set_index("expiry_dt")["tau"]


@dataclass(frozen=True)
class SavedSetting:
    """One saved setting.

    ``read(state, chain, snapshot_id)`` gives the saved value from the widget
    state, with the page default for a widget not drawn yet;
    ``write(value, chain, snapshot_id)`` gives the widget values that show it.
    """

    name: str
    read: Callable
    write: Callable


def _single_key(name, key, default, to_saved=lambda v: v, to_widget=lambda v: v):
    """A setting held by one widget whose key does not depend on the snapshot."""
    return SavedSetting(
        name,
        read=lambda state, chain, snapshot_id: to_saved(default(state.get(key))),
        write=lambda value, chain, snapshot_id: {key: to_widget(value)},
    )


def _read_oi_expiries(state, chain, snapshot_id):
    expiry_of = {tau: expiry for expiry, tau in expiry_taus(chain).items()}
    return [expiry_of[tau] for tau in state.get(oi_expiries_key(snapshot_id)) or []]


def _write_oi_expiries(value, chain, snapshot_id):
    taus = expiry_taus(chain)
    return {oi_expiries_key(snapshot_id): [float(taus[e]) for e in value]}


def _read_strike_range(state, chain, snapshot_id):
    return state.get(
        strike_range_key(snapshot_id),
        near_spot_range(float(chain["index_price"].iloc[0])),
    )


def _read_signs(state, chain, snapshot_id):
    return {
        flag: CUSTOMER_SIDES[
            state.get(customer_side_key(flag)) or SIDE_OF_SIGN[DEFAULT_SIGNS[flag]]
        ]
        for flag in ("call", "put")
    }


def _write_signs(value, chain, snapshot_id):
    return {customer_side_key(flag): SIDE_OF_SIGN[value[flag]] for flag in ("call", "put")}


def _read_smile_expiries(state, chain, snapshot_id):
    return [
        expiry for expiry, tau in expiry_taus(chain).items()
        if state.get(smile_key(snapshot_id, tau), False)
    ]


def _write_smile_expiries(value, chain, snapshot_id):
    chosen = set(value)
    return {
        smile_key(snapshot_id, tau): expiry in chosen
        for expiry, tau in expiry_taus(chain).items()
    }


_RANGE_NAME = {value: name for name, value in MONEYNESS_RANGES.items()}

SETTINGS = (
    SavedSetting("oi_expiries", _read_oi_expiries, _write_oi_expiries),
    SavedSetting(
        "strike_range",
        _read_strike_range,
        lambda value, chain, snapshot_id: {strike_range_key(snapshot_id): value},
    ),
    SavedSetting("signs", _read_signs, _write_signs),
    _single_key("gex_view", GEX_VIEW_KEY, lambda v: v or "Net"),
    _single_key("iv_source", IV_SOURCE_KEY, lambda v: v or DEFAULT_IV_SOURCE),
    _single_key(
        "moneyness_range",
        MONEYNESS_RANGE_KEY,
        lambda v: next(iter(MONEYNESS_RANGES)) if v is None else v,
        to_saved=MONEYNESS_RANGES.__getitem__,
        to_widget=_RANGE_NAME.__getitem__,
    ),
    _single_key(
        "heatmap_values",
        HEATMAP_VALUES_KEY,
        lambda v: HEATMAP_VALUES[0] if v is None else v,
    ),
    SavedSetting("smile_expiries", _read_smile_expiries, _write_smile_expiries),
    _single_key("surface_view", SURFACE_VIEW_KEY, lambda v: v or SURFACE_VIEWS[0]),
)


def settings_from_widgets(state, chain, snapshot_id):
    """The saved settings as the widgets hold them, with defaults for unshown ones."""
    return {s.name: s.read(state, chain, snapshot_id) for s in SETTINGS}


def widgets_from_settings(settings, chain, snapshot_id):
    """The widget values that show saved settings for a snapshot."""
    values = {}
    for setting in SETTINGS:
        values.update(setting.write(settings[setting.name], chain, snapshot_id))
    return values
