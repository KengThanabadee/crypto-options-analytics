"""Offline convention evidence; this does not change dashboard pricing.

Run: .venv/bin/python -B experiments/check_deribit_iv_convention.py
Uses the checked-in fixture and the repository's own IV solver. Writes only
deribit_iv_convention_check.json alongside this script. No network calls.
"""

from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from scipy.special import ndtr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from iv_surface.solver import bs_price, solve_iv


def inverse_price_btc(forward, strike, tau, sigma, flag):
    """Independent normalized-forward expression, not solver.bs_price()."""
    d1 = (math.log(forward / strike) + .5 * sigma**2 * tau) / (sigma * math.sqrt(tau))
    d2 = d1 - sigma * math.sqrt(tau)
    if flag == "call":
        return float(ndtr(d1) - strike / forward * ndtr(d2))
    if flag == "put":
        return float(strike / forward * ndtr(-d2) - ndtr(-d1))
    raise ValueError("Invalid option type")


def stats(values):
    values = np.asarray(values, dtype=float)
    if not len(values):
        return {"count": 0}
    return {
        "count": len(values),
        "median_signed": float(np.median(values)),
        "p95_absolute": float(np.percentile(abs(values), 95)),
        "maximum_absolute": float(abs(values).max()),
    }


def synthetic_checks():
    price_errors, iv_errors = [], []
    for index in (20000., 100000.):
        for forward_ratio in (.9, 1., 1.1):
            forward = index * forward_ratio
            for tau in (.01, .5, 1.):
                rate = math.log(forward / index) / tau
                for strike_ratio in (.9, 1., 1.1):
                    strike = forward * strike_ratio
                    for sigma in (.3, .7):
                        for flag in ("call", "put"):
                            price = inverse_price_btc(forward, strike, tau, sigma, flag)
                            price_errors.append(
                                bs_price(index, strike, tau, rate, sigma, flag) / index - price
                            )
                            recovered = solve_iv(price * index, index, strike, tau, rate, flag)
                            iv_errors.append(recovered - sigma)
    assert max(abs(x) for x in price_errors) < 1e-12
    assert max(abs(x) for x in iv_errors) < 1e-4
    return {"formula_error_btc": stats(price_errors), "iv_error_decimal": stats(iv_errors)}


def fixture_checks():
    source = ROOT / "data/deribit_btc_options_snapshot.json"
    raw = source.read_bytes()
    snapshot = json.loads(raw)
    results = {
        item["endpoint"].split("/")[-1]: item["response"]["result"]
        for item in snapshot["requests"]
    }
    instruments = {row["instrument_name"]: row for row in results["get_instruments"]}
    index = results["get_index_price"]["index_price"]
    captured = datetime.fromisoformat(snapshot["captured_at_utc"].replace("Z", "+00:00"))
    forward_sets, expiry_dates = defaultdict(set), {}
    rates, measures, counts, fields = [], defaultdict(list), Counter(), Counter()
    outliers = []
    books = results["get_book_summary_by_currency"]
    for book in books:
        instrument = instruments[book["instrument_name"]]
        strike, flag = instrument["strike"], instrument["option_type"]
        expiry_ms = instrument["expiration_timestamp"]
        seconds = expiry_ms / 1000 - captured.timestamp()
        tau = seconds / (365 * 86400)
        forward = book["underlying_price"]
        assert tau > 0 and forward > 0
        rate = math.log(forward / index) / tau
        rates.append(rate)
        forward_sets[expiry_ms].add(forward)
        expiry_dates[expiry_ms] = instrument["instrument_name"].split("-")[1]
        for field in ("open_interest", "volume", "volume_usd", "greeks", "best_bid_amount", "best_ask_amount"):
            fields[field] += book.get(field) is not None
        bid, ask = book.get("bid_price"), book.get("ask_price")
        valid_pair = bid is not None and ask is not None and 0 < bid <= ask
        prices = {key: book.get(key) for key in ("bid_price", "ask_price", "mark_price")}
        prices["mid_price"] = (bid + ask) / 2 if valid_pair else None
        for field, price in prices.items():
            if price is None or price <= 0:
                counts[field + "_missing_or_nonpositive"] += 1
                continue
            try:
                iv = solve_iv(price * index, index, strike, tau, rate, flag)
            except ValueError:
                counts[field + "_solve_failed"] += 1
                continue
            predicted = inverse_price_btc(forward, strike, tau, iv, flag)
            measures[field + "_repricing_error_usd"].append((predicted - price) * index)
            if field == "mark_price":
                difference = (iv - book["mark_iv"] / 100) * 100
                measures["mark_iv_difference_percentage_points"].append(difference)
                outliers.append({"symbol": book["instrument_name"], "iv_difference_percentage_points": difference})
            if field == "mid_price":
                try:
                    old_iv = solve_iv(price * index, index, strike, seconds / (365.25 * 86400), 0, flag)
                except ValueError:
                    counts["old_zero_rate_mid_solve_failed_among_new_successes"] += 1
                else:
                    measures["mid_change_vs_old_zero_rate_percentage_points"].append((iv - old_iv) * 100)
    for field in ("bid_price", "ask_price", "mark_price", "mid_price"):
        assert max(abs(x) for x in measures[field + "_repricing_error_usd"]) < .001
    return {
        "source": str(source.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "captured_at_utc": snapshot["captured_at_utc"],
        "index_price_usd": index,
        "instrument_rows": len(instruments),
        "summary_rows": len(books),
        "day_count_proposed": "ACT/365 fixed; capture end is frozen analysis time",
        "forward_policy_under_test": "original per-contract underlying_price; no averaging",
        "api_interest_rate_values": sorted({row.get("interest_rate") for row in books}),
        "inferred_rate_range_decimal": [min(rates), max(rates)],
        "forward_by_expiry": [
            {"expiry_label": expiry_dates[e], "unique_forward_count": len(fs), "minimum": min(fs), "maximum": max(fs)}
            for e, fs in sorted(forward_sets.items())
        ],
        "nonnull_summary_fields": dict(fields),
        "missing_or_failed": dict(counts),
        "metrics": {name: stats(values) for name, values in measures.items()},
        "largest_mark_iv_differences": sorted(outliers, key=lambda x: abs(x["iv_difference_percentage_points"]), reverse=True)[:5],
        "limitations": [
            "This is convention research, not a changed runtime or exchange parity certification.",
            "Mark is compared with mark; midpoint changes are compared only on mutually solved rows.",
            "Independently solved bid/ask diagnostics are not a validated executable spread or Combined-IV band.",
            "Reasons for real mark-price/mark-IV discrepancies have not been established.",
        ],
    }


if __name__ == "__main__":
    evidence = {"synthetic": synthetic_checks(), "fixture": fixture_checks()}
    destination = Path(__file__).with_name("deribit_iv_convention_check.json")
    destination.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n")
    print(json.dumps(evidence, indent=2, allow_nan=False))
