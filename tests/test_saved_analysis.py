import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from options_analytics import saved_analysis
from options_analytics.deribit import load_deribit_snapshot, parse_deribit_snapshot
from options_analytics.iv_source import build_iv_source_surface
from options_analytics.positioning import net_gex_by_strike, open_interest_by_strike


SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "data/deribit_btc_options_snapshot.json"


@pytest.fixture
def snapshot():
    return load_deribit_snapshot(SNAPSHOT_PATH)


def _settings(chain):
    expiries = sorted(chain["expiry_dt"].unique())
    return {
        "oi_expiries": [expiries[1], expiries[4]],
        "strike_range": (60_000.0, 110_000.0),
        "signs": {"call": -1, "put": 1},
        "gex_view": "Gross",
        "iv_source": "Quote midpoint",
        "moneyness_range": "All listed",
        "heatmap_values": "Observed",
        "smile_expiries": [expiries[0], expiries[2], expiries[5]],
        "surface_view": "3D",
    }


def _expiry_taus(chain, expiries):
    by_expiry = chain.drop_duplicates("expiry_dt").set_index("expiry_dt")["tau"]
    return [float(by_expiry[pd.Timestamp(expiry)]) for expiry in expiries]


def test_reopen_restores_snapshot_settings_and_the_same_numbers(snapshot):
    chain = parse_deribit_snapshot(snapshot)
    settings = _settings(chain)

    reopened = saved_analysis.open_analysis(saved_analysis.save_analysis(snapshot, settings))

    assert reopened.snapshot == snapshot
    assert reopened.settings == settings
    assert reopened.calculation_version == saved_analysis.CALCULATION_VERSION
    assert not reopened.version_differs

    again = parse_deribit_snapshot(reopened.snapshot)
    pd.testing.assert_frame_equal(again, chain)
    taus, taus_again = (
        _expiry_taus(chain, settings["oi_expiries"]),
        _expiry_taus(again, reopened.settings["oi_expiries"]),
    )
    assert taus == taus_again
    pd.testing.assert_frame_equal(
        open_interest_by_strike(again, taus_again), open_interest_by_strike(chain, taus)
    )
    pd.testing.assert_frame_equal(
        net_gex_by_strike(again, taus_again, signs=reopened.settings["signs"]),
        net_gex_by_strike(chain, taus, signs=settings["signs"]),
    )
    before = build_iv_source_surface(chain, settings["iv_source"])
    after = build_iv_source_surface(again, reopened.settings["iv_source"])
    np.testing.assert_array_equal(after.iv_surface, before.iv_surface)
    np.testing.assert_array_equal(after.strikes, before.strikes)


def test_the_file_holds_raw_responses_settings_and_one_version_but_no_numbers(snapshot):
    chain = parse_deribit_snapshot(snapshot)
    saved = json.loads(saved_analysis.save_analysis(snapshot, _settings(chain)))

    assert set(saved) == {"format", "format_version", "calculation_version",
                          "snapshot", "settings"}
    assert saved["snapshot"] == snapshot
    assert [r["received_at_utc"] for r in saved["snapshot"]["requests"]]
    expiries = sorted(chain["expiry_dt"].unique())
    assert saved["settings"] == {
        "oi_expiries": [f"{expiries[1]:%Y-%m-%dT%H:%M:%SZ}",
                        f"{expiries[4]:%Y-%m-%dT%H:%M:%SZ}"],
        "strike_range": [60_000.0, 110_000.0],
        "signs": {"call": -1, "put": 1},
        "gex_view": "Gross",
        "iv_source": "Quote midpoint",
        "moneyness_range": "All listed",
        "heatmap_values": "Observed",
        "smile_expiries": [f"{expiries[i]:%Y-%m-%dT%H:%M:%SZ}" for i in (0, 2, 5)],
        "surface_view": "3D",
    }


def test_an_older_calculation_version_is_flagged(snapshot):
    chain = parse_deribit_snapshot(snapshot)
    saved = json.loads(saved_analysis.save_analysis(snapshot, _settings(chain)))
    saved["calculation_version"] = saved_analysis.CALCULATION_VERSION - 1 or 0

    reopened = saved_analysis.open_analysis(json.dumps(saved))

    assert reopened.version_differs
    assert reopened.calculation_version == saved["calculation_version"]
    assert str(saved["calculation_version"]) in reopened.version_notice()


@pytest.mark.parametrize("range_name", ["Core", "Wide", "All listed"])
def test_the_moneyness_range_is_saved_by_name(snapshot, range_name):
    chain = parse_deribit_snapshot(snapshot)
    settings = {**_settings(chain), "moneyness_range": range_name}
    raw = saved_analysis.save_analysis(snapshot, settings)

    assert json.loads(raw)["settings"]["moneyness_range"] == range_name
    assert saved_analysis.open_analysis(raw).settings["moneyness_range"] == range_name


def test_a_format_1_file_is_rejected_as_unsupported(snapshot):
    chain = parse_deribit_snapshot(snapshot)
    saved = json.loads(saved_analysis.save_analysis(snapshot, _settings(chain)))
    saved["format_version"] = 1
    saved["settings"]["moneyness_range"] = [0.8, 1.2]
    with pytest.raises(ValueError, match="Unsupported saved-analysis format version"):
        saved_analysis.open_analysis(json.dumps(saved))


def test_a_file_saved_without_a_surface_view_opens_on_heatmap(snapshot):
    chain = parse_deribit_snapshot(snapshot)
    saved = json.loads(saved_analysis.save_analysis(snapshot, _settings(chain)))
    del saved["settings"]["surface_view"]

    reopened = saved_analysis.open_analysis(json.dumps(saved))

    assert reopened.settings == {**_settings(chain), "surface_view": "Heatmap"}
    assert not reopened.version_differs


def _corrupt(snapshot, chain, change):
    saved = json.loads(saved_analysis.save_analysis(snapshot, _settings(chain)))
    change(saved)
    return json.dumps(saved)


@pytest.mark.parametrize("change", [
    lambda s: s.pop("snapshot"),
    lambda s: s.update(format="something else"),
    lambda s: s.update(format_version=1),
    lambda s: s.update(format_version=3),
    lambda s: s.update(calculation_version="1"),
    lambda s: s["snapshot"].update(schema_version=9),
    lambda s: s["settings"].pop("iv_source"),
    lambda s: s["settings"].update(iv_source="Bybit"),
    lambda s: s["settings"].update(gex_view="Both"),
    lambda s: s["settings"].update(signs={"call": 2, "put": -1}),
    lambda s: s["settings"].update(strike_range=[110_000, 60_000]),
    lambda s: s["settings"].update(strike_range=[1, 10_000_000]),
    lambda s: s["settings"].update(oi_expiries=["2030-01-01T08:00:00Z"]),
    lambda s: s["settings"].update(smile_expiries=["not a date"]),
    lambda s: s["settings"].update(moneyness_range=[0.5, 2.0]),
    lambda s: s["settings"].update(moneyness_range="Extended"),
    lambda s: s["settings"].update(heatmap_values="Both"),
    lambda s: s["settings"].update(surface_view="Contour"),
])
def test_invalid_files_raise_value_error(snapshot, change):
    chain = parse_deribit_snapshot(snapshot)
    with pytest.raises(ValueError):
        saved_analysis.open_analysis(_corrupt(snapshot, chain, change))


@pytest.mark.parametrize("raw", [b"\xff\xfe", b"not json", b"[]", "{}"])
def test_unreadable_files_raise_value_error(raw):
    with pytest.raises(ValueError):
        saved_analysis.open_analysis(raw)


@pytest.mark.parametrize("change", [
    lambda s: s["settings"].pop("iv_source"),
    lambda s: s["settings"].update(extra=1),
    lambda s: s.update(settings=[]),
])
def test_wrong_setting_names_name_the_required_and_optional_settings(snapshot, change):
    chain = parse_deribit_snapshot(snapshot)
    with pytest.raises(ValueError) as error:
        saved_analysis.open_analysis(_corrupt(snapshot, chain, change))
    assert str(error.value) == (
        "Saved settings must have oi_expiries, strike_range, signs, gex_view, "
        "iv_source, moneyness_range, heatmap_values and smile_expiries, and may "
        "have surface_view, with no other settings"
    )
