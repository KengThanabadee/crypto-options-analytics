from datetime import datetime, timezone

import numpy as np
import pytest

from iv_surface.chain import (
    _compute_mid_price,
    _parse_utc_timestamp,
    _to_float,
    compute_tau,
)


def test_to_float_returns_nan_for_bad_values():
    assert _to_float("123.45") == 123.45
    assert np.isnan(_to_float(None))
    assert np.isnan(_to_float("not-a-number"))
    assert np.isnan(_to_float(np.inf))


def test_compute_mid_price_uses_valid_bid_ask_only():
    assert _compute_mid_price(100, 110) == 105
    assert np.isnan(_compute_mid_price(0, 110))
    assert np.isnan(_compute_mid_price(100, 0))
    assert np.isnan(_compute_mid_price(110, 100))
    assert np.isnan(_compute_mid_price(np.nan, 110))


def test_compute_tau_clamps_expired_time_to_zero():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert compute_tau(now, now) == 0.0
    assert compute_tau(datetime(2025, 12, 31, tzinfo=timezone.utc), now) == 0.0


def test_compute_tau_one_year_is_365_days():
    now = datetime(2027, 1, 1, tzinfo=timezone.utc)
    expiry = datetime(2028, 1, 1, tzinfo=timezone.utc)  # 2027 has 365 days

    assert abs(compute_tau(expiry, now) - 1.0) < 1e-12


def test_parse_utc_timestamp_accepts_z_and_zero_offset():
    expected = datetime(2026, 10, 15, 8, 0, 1, tzinfo=timezone.utc)

    assert _parse_utc_timestamp("2026-10-15T08:00:01Z") == expected
    assert _parse_utc_timestamp("2026-10-15T08:00:01+00:00") == expected
    assert _parse_utc_timestamp("2026-10-15T08:00:01Z").tzinfo == timezone.utc


@pytest.mark.parametrize(
    "value",
    [None, 1760515201, "not a time", "2026-10-15T08:00:01", "2026-10-15T08:00:01+07:00"],
)
def test_parse_utc_timestamp_rejects_missing_naive_or_non_utc_values(value):
    with pytest.raises(ValueError):
        _parse_utc_timestamp(value)
