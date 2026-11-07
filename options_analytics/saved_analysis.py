"""Save an analysis as one JSON file and reopen it from the raw snapshot.

The file holds the raw Deribit snapshot (every API response with its capture
times), the analysis settings and one calculation version. It holds no
computed numbers: reopening recomputes everything from the snapshot.
"""

from dataclasses import dataclass
import json
import math

import pandas as pd

from options_analytics.deribit import parse_deribit_snapshot
from options_analytics.iv_source import IV_SOURCES
from options_analytics.positioning import GEX_MODES, strike_zoom_bounds
from options_analytics.surface_transforms import HEATMAP_VALUES, MONEYNESS_RANGES, SURFACE_VIEWS


FILE_FORMAT = "btc-options-analysis"
FORMAT_VERSION = 1
# Raise when a change alters any number computed from the same snapshot and
# settings, so reopening an older file shows a recompute notice.
CALCULATION_VERSION = 4
SETTING_NAMES = (
    "oi_expiries", "strike_range", "signs", "gex_view", "iv_source",
    "moneyness_range", "heatmap_values", "smile_expiries", "surface_view",
)
# Settings added after format version 1, with the value a file without them opens on.
OPTIONAL_SETTINGS = {"surface_view": SURFACE_VIEWS[0]}
_EXPIRY_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True)
class SavedAnalysis:
    snapshot: dict
    settings: dict
    calculation_version: int
    chain: pd.DataFrame

    @property
    def version_differs(self) -> bool:
        return self.calculation_version != CALCULATION_VERSION

    def version_notice(self) -> str:
        return (
            f"Saved with calculation version {self.calculation_version}; "
            f"every number is recomputed with version {CALCULATION_VERSION}."
        )


def save_analysis(snapshot: dict, settings: dict) -> str:
    """Return the saved-analysis JSON for a raw snapshot and its settings.

    Settings: ``oi_expiries`` and ``smile_expiries`` are expiry datetimes
    (empty OI expiries means All expiries), ``strike_range`` and
    ``moneyness_range`` are (low, high), ``signs`` maps call/put to ±1,
    plus ``gex_view``, ``iv_source``, ``heatmap_values`` and ``surface_view``.
    """
    stored = {
        "oi_expiries": [_expiry_text(e) for e in settings["oi_expiries"]],
        "strike_range": [float(v) for v in settings["strike_range"]],
        "signs": {flag: int(settings["signs"][flag]) for flag in ("call", "put")},
        "gex_view": settings["gex_view"],
        "iv_source": settings["iv_source"],
        "moneyness_range": [float(v) for v in settings["moneyness_range"]],
        "heatmap_values": settings["heatmap_values"],
        "smile_expiries": [_expiry_text(e) for e in settings["smile_expiries"]],
        "surface_view": settings["surface_view"],
    }
    return json.dumps({
        "format": FILE_FORMAT,
        "format_version": FORMAT_VERSION,
        "calculation_version": CALCULATION_VERSION,
        "snapshot": snapshot,
        "settings": stored,
    }, ensure_ascii=False)


def open_analysis(raw) -> SavedAnalysis:
    """Read and validate a saved analysis; any problem raises ValueError."""
    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        saved = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("The file is not a saved analysis (unreadable JSON)") from exc
    if not isinstance(saved, dict) or saved.get("format") != FILE_FORMAT:
        raise ValueError("The file is not a saved analysis")
    if saved.get("format_version") != FORMAT_VERSION:
        raise ValueError("Unsupported saved-analysis format version")
    version = saved.get("calculation_version")
    if type(version) is not int:
        raise ValueError("Saved analysis needs an integer calculation version")
    snapshot = saved.get("snapshot")
    try:
        chain = parse_deribit_snapshot(snapshot)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"Saved snapshot is invalid: {exc}") from exc
    settings = _read_settings(saved.get("settings"), chain)
    return SavedAnalysis(
        snapshot=snapshot, settings=settings, calculation_version=version, chain=chain,
    )


def _expiry_text(expiry) -> str:
    return pd.Timestamp(expiry).tz_convert("UTC").strftime(_EXPIRY_FORMAT)


def _read_expiries(values, chain, name):
    listed = set(chain["expiry_dt"])
    if not isinstance(values, list):
        raise ValueError(f"Setting {name} must be a list of expiries")
    expiries = []
    for value in values:
        try:
            expiry = pd.Timestamp(value)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Setting {name} has an invalid expiry: {value!r}") from exc
        if not isinstance(value, str) or expiry.tzinfo is None or expiry not in listed:
            raise ValueError(f"Setting {name} names an expiry not in the snapshot: {value!r}")
        expiries.append(expiry)
    if len(set(expiries)) != len(expiries):
        raise ValueError(f"Setting {name} repeats an expiry")
    return expiries


def _read_pair(value, name):
    if (not isinstance(value, list) or len(value) != 2
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                       and math.isfinite(v) for v in value)
            or value[0] > value[1]):
        raise ValueError(f"Setting {name} must be a finite (low, high) pair")
    return (float(value[0]), float(value[1]))


def _read_choice(value, choices, name):
    if value not in choices:
        raise ValueError(f"Setting {name} must be one of {', '.join(choices)}")
    return value


def _names(names):
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0]


_REQUIRED_SETTINGS = [name for name in SETTING_NAMES if name not in OPTIONAL_SETTINGS]
_SETTING_NAMES_ERROR = (
    f"Saved settings must have {_names(_REQUIRED_SETTINGS)}, and may have "
    f"{_names(list(OPTIONAL_SETTINGS))}, with no other settings"
)


def _read_settings(stored, chain) -> dict:
    if isinstance(stored, dict):
        stored = {**OPTIONAL_SETTINGS, **stored}
    if not isinstance(stored, dict) or set(stored) != set(SETTING_NAMES):
        raise ValueError(_SETTING_NAMES_ERROR)
    strike_range = _read_pair(stored["strike_range"], "strike_range")
    low, high = strike_zoom_bounds(chain)
    if strike_range[0] < low or strike_range[1] > high:
        raise ValueError("Setting strike_range lies outside the snapshot's strikes")
    moneyness_range = _read_pair(stored["moneyness_range"], "moneyness_range")
    if moneyness_range not in MONEYNESS_RANGES.values():
        raise ValueError("Setting moneyness_range is not a dashboard range")
    signs = stored["signs"]
    if (not isinstance(signs, dict) or set(signs) != {"call", "put"}
            or any(type(s) is not int or s not in (1, -1) for s in signs.values())):
        raise ValueError("Setting signs must map call and put to +1 or -1")
    return {
        "oi_expiries": _read_expiries(stored["oi_expiries"], chain, "oi_expiries"),
        "strike_range": strike_range,
        "signs": {"call": signs["call"], "put": signs["put"]},
        "gex_view": _read_choice(stored["gex_view"], GEX_MODES, "gex_view"),
        "iv_source": _read_choice(stored["iv_source"], IV_SOURCES, "iv_source"),
        "moneyness_range": moneyness_range,
        "heatmap_values": _read_choice(
            stored["heatmap_values"], HEATMAP_VALUES, "heatmap_values"
        ),
        "smile_expiries": _read_expiries(stored["smile_expiries"], chain, "smile_expiries"),
        "surface_view": _read_choice(stored["surface_view"], SURFACE_VIEWS, "surface_view"),
    }
