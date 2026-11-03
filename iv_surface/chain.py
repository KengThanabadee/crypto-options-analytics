"""Shared parsing helpers for option-chain snapshots."""

from datetime import datetime, timezone

import numpy as np


def _to_float(value):
    try:
        v = float(value)
        return v if np.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _compute_mid_price(bid_price, ask_price):
    if not np.isfinite(bid_price) or not np.isfinite(ask_price):
        return np.nan
    if bid_price <= 0 or ask_price <= 0:
        return np.nan
    if ask_price < bid_price:
        return np.nan
    return (bid_price + ask_price) / 2


def compute_tau(expiry_dt: datetime, now: datetime) -> float:
    """Time to expiry in years of 365.25 days; settled contracts clamp to 0."""
    diff = expiry_dt - now
    seconds = diff.total_seconds()
    return max(seconds / (365.25 * 24 * 3600), 0.0)


def _parse_utc_timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("captured_at_utc must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("captured_at_utc must be a valid ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("captured_at_utc must use UTC")
    return parsed.astimezone(timezone.utc)
