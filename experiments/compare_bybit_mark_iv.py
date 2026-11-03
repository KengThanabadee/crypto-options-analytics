"""Bounded offline comparison: current app midpoint IV versus Bybit mark IV.

Run: .venv/bin/python -B experiments/compare_bybit_mark_iv.py
Writes bybit_mark_iv_comparison.csv/.json/.md here. No network or runtime edits.
"""

import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from iv_surface.fetcher import load_chain_snapshot, parse_chain_snapshot
from iv_surface.solver import bs_price, solve_iv
from iv_surface.surface_builder import build_combined_surface_from_chain

OUTPUT = Path(__file__).with_name("bybit_mark_iv_comparison")
PROFILES = {
    "mid": ("mid_price", "app_spot_price"),
    "mark": ("mark_price", "app_spot_price"),
    "underlying_diagnostic": ("mark_price", "underlying_price"),
    "mid_underlying_D1_diagnostic": ("mid_price", "underlying_price"),
}


def app_default_rate():
    tree = ast.parse((ROOT / "app.py").read_text())
    label = "Risk-free rate (% p.a., continuously compounded)"
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "number_input" and node.args
                and isinstance(node.args[0], ast.Constant) and node.args[0].value == label):
            return float(ast.literal_eval(next(k.value for k in node.keywords if k.arg == "value"))) / 100
    raise AssertionError("Current app rate default could not be identified")


def describe(values):
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a)]
    if not len(a):
        return {"count": 0}
    return {
        "count": len(a),
        "median_absolute_pp": float(np.median(abs(a))),
        "p90_absolute_pp": float(np.percentile(abs(a), 90)),
        "p95_absolute_pp": float(np.percentile(abs(a), 95)),
        "max_absolute_pp": float(abs(a).max()),
        "median_signed_pp": float(np.median(a)),
        "mean_signed_pp": float(np.mean(a)),
        "positive_gap_fraction": float(np.mean(a > 0)),
        "negative_gap_fraction": float(np.mean(a < 0)),
    }


def invert(price, spot, row, rate, eligible):
    if not eligible:
        return np.nan, "input_unusable", np.nan
    try:
        value = solve_iv(price, spot, row.strike, row.tau, rate, row.flag)
    except ValueError:
        low = bs_price(spot, row.strike, row.tau, rate, 1e-6, row.flag)
        high = bs_price(spot, row.strike, row.tau, rate, 10., row.flag)
        status = "below_solver_price_bracket" if price < low else "above_solver_price_bracket" if price > high else "solve_failed"
        return np.nan, status, np.nan
    residual = bs_price(spot, row.strike, row.tau, rate, value, row.flag) - price
    assert abs(residual) < .001, "Inspect price residual before interpreting IV differences"
    return value, "ok", residual


def tight_zero_rate_reference(price, spot, strike, tau, flag):
    """Independent erfc-price bisection for one low-price numerical spot check."""
    def price_at(sigma):
        d1 = (math.log(spot / strike) + .5 * sigma**2 * tau) / (sigma * math.sqrt(tau))
        d2 = d1 - sigma * math.sqrt(tau)
        cdf = lambda x: .5 * math.erfc(-x / math.sqrt(2))
        return spot * cdf(d1) - strike * cdf(d2) if flag == "call" else strike * cdf(-d2) - spot * cdf(-d1)
    low, high = 1e-6, 10.
    assert price_at(low) <= price <= price_at(high)
    for _ in range(80):
        middle = (low + high) / 2
        if price_at(middle) < price:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def comparison(frame, profile):
    col = profile + "_gap_pp"
    return {
        "cohort_rows": len(frame),
        "usable_price_rows": int(frame[profile + "_input_usable"].sum()),
        "solve_success_rows": int(frame[profile + "_iv"].notna().sum()),
        "solve_failed_rows": int((frame[profile + "_input_usable"] & frame[profile + "_iv"].isna()).sum()),
        "input_unusable_rows": int((~frame[profile + "_input_usable"]).sum()),
        "comparable_rows": int(frame[col].notna().sum()),
        "statuses": dict(Counter(frame[profile + "_status"])),
        "gaps": describe(frame[col]),
        "maximum_absolute_repricing_residual_quote_units": (
            float(frame[profile + "_price_residual"].abs().max())
            if frame[profile + "_price_residual"].notna().any() else None
        ),
        "sigma_boundary_returns": int(frame[profile + "_iv"].isin([1e-6, 10.]).sum()),
    }


def sample_indices(frame):
    chosen = {}

    def take(candidates, label):
        for index in candidates.index:
            if index not in chosen:
                chosen[index] = label
                return

    for edge, ascending in (("short", True), ("long", False)):
        for flag in ("call", "put"):
            candidates = frame[frame.flag.eq(flag)].copy()
            candidates["atm_distance"] = abs(candidates.moneyness - 1)
            take(candidates.sort_values(["tau", "atm_distance", "symbol"], ascending=[ascending, True, True]), edge + " expiry nearest strike")
    for profile in ("mid", "mark"):
        for flag in ("call", "put"):
            candidates = frame[frame.flag.eq(flag) & frame[profile + "_gap_pp"].notna()].copy()
            candidates["abs_gap"] = abs(candidates[profile + "_gap_pp"])
            take(candidates.sort_values(["abs_gap", "symbol"], ascending=[False, True]), "large " + profile + " gap")
    take(frame[frame.mark_input_usable & frame.mark_iv.isna()].sort_values("symbol"), "default mark inversion failed")
    take(frame[~frame.mid_input_usable].sort_values("symbol"), "missing two-sided midpoint")
    samples = frame.loc[list(chosen)].copy()
    samples["selection_reason"] = list(chosen.values())
    return samples


def number(value, digits=3):
    return f"{value:.{digits}f}" if pd.notna(value) else "—"


def render_report(info, frame, samples):
    lines = [
        "# Bybit midpoint IV versus exchange mark IV",
        "",
        "Offline experiment only. Runtime/dashboard and pricing contracts are unchanged.",
        "",
        f"Snapshot: **{info['captured_at_utc']}**, {len(frame)} individual BTC option contracts.",
        f"Current app default: spot Black–Scholes, r={info['rate_decimal'] * 100:.2f}% continuously compounded, "
        f"shared index S={info['app_spot_price']:.8f}, ACT/365.25, expiry at 08:00 UTC parsed from symbol.",
        f"The response server clock is {info['response_time_utc']}, about {info['capture_minus_response_ms']:.3f} ms before local capture. "
        "The app uses local frozen capture time for tau, not the server clock or today's date.",
        "No Combined or interpolated IV is used in the comparison. Each row retains its Call/Put identity.",
        "",
        "## What is being compared",
        "",
        "1. **Mid:** invert the arithmetic midpoint of usable bid/ask prices exactly as in the current app, then subtract Bybit markIv.",
        "2. **Mark:** invert Bybit markPrice with the same spot/rate/tau/solver, then subtract markIv. This changes the price input only.",
        "3. **Underlying diagnostic:** invert markPrice with reported underlyingPrice instead of index; keep r=0 and ACT/365.25. "
        "This is a labeled sensitivity experiment, not a changed app or a verified full exchange convention.",
        "4. **Mid + assumed F, D=1:** invert midpoint with reported underlyingPrice treated as F in a Black-76 forward-price form, "
        "discount factor D=1. The existing bs_price(F,K,T,r=0) is algebraically equivalent in this case; "
        "no nonzero carry rate is applied again. Frozen ACT/365.25, quote units and ATM cohort stay unchanged.",
        "",
        "IVs in raw Bybit fields are decimal: e.g. markIv=1.0608 means 106.08%. Gaps are volatility percentage points: "
        "100*(our_decimal_IV - exchange_decimal_IV). Positive means ours is higher; 40% versus38% is+2 points, not+2% relative.",
        "All snapshot symbols have the -USDT suffix. Prices are used in their stored quote units alongside strike/index, "
        "with no BTC-premium multiplication or stablecoin/USD FX conversion. The fixture does not contain a full instrument-spec response.",
        "",
        "## Primary results (unweighted contract observations)",
        "",
        "Near ATM is inclusive0.98<=K/S<=1.02, using app spot. Short expiry means remaining time<=7 actual days at capture.",
        "The groups overlap. Different solve counts mean marginal statistics are not a paired causal decomposition.",
        "",
        "| Group | Price inverted | Successful / usable / cohort | Median abs gap (pp) | P90 abs (pp) | P95 abs (pp) | Median signed (pp) |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for group in ("all", "near_atm", "short_le7_days", "near_atm_short_le7_days"):
        for profile in ("mid", "mark"):
            item = info["groups"][group][profile]
            g = item["gaps"]
            lines.append(f"| {group} | {profile} | {item['solve_success_rows']}/{item['usable_price_rows']}/{item['cohort_rows']} "
                         f"| {g['median_absolute_pp']:.4f} | {g['p90_absolute_pp']:.4f} | {g['p95_absolute_pp']:.4f} | {g['median_signed_pp']:+.4f} |")
    lines.extend([
        "", "## Coverage, sign bias and solver checks", "",
        "| Profile | Input unusable | Solve failed | Positive gaps | Mean signed gap (pp) | Max repricing residual (quote units) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for profile in PROFILES:
        item = info["groups"]["all"][profile]
        lines.append(f"| {profile} | {item['input_unusable_rows']} | {item['solve_failed_rows']} | {item['gaps']['positive_gap_fraction']:.1%} "
                     f"| {item['gaps']['mean_signed_pp']:+.4f} | {item['maximum_absolute_repricing_residual_quote_units']:.8f} |")
    lines.extend([
        "", "Signed bias should also be read by option type; pooled Call/Put signs can cancel.", "",
        "| Side | Price | Comparable rows | Median signed (pp) | Positive gaps |",
        "| --- | --- | ---: | ---: | ---: |",
    ])
    for flag in ("call", "put"):
        for profile in ("mid", "mark"):
            g = info["groups"][flag][profile]["gaps"]
            lines.append(f"| {flag} | {profile} | {g['count']} | {g['median_signed_pp']:+.4f} | {g['positive_gap_fraction']:.1%} |")
    paired = info["paired_default_successes"]
    lines.extend([
        "",
        "Failure reasons are saved per contract in CSV and reconciled in JSON. A below-bracket mark price means no IV solution "
        "within this model's current bracket at those inputs; it does not establish a bad exchange quote under its own inputs. "
        "No boundary-sigma returns occurred in this fixture. Successful direct midpoint inversions match the app's uncombined Call/Put grids.",
        f"The {paired['rows']} rows where both primary inversions succeed are separately summarized in JSON. "
        "For each such row, (mid IV - markPrice-inverted IV) + (markPrice-inverted IV - exchange markIv) = total midpoint gap. "
        "Medians/P95 of those terms are not additive.",
        "", "## Reported-underlying diagnostic", "",
        "| Group | Successful / cohort | Median abs gap (pp) | P90 abs (pp) | P95 abs (pp) |",
        "| --- | --- | ---: | ---: | ---: |",
    ])
    for group in ("all", "near_atm", "short_le7_days"):
        item = info["groups"][group]["underlying_diagnostic"]
        g = item["gaps"]
        lines.append(f"| {group} | {item['solve_success_rows']}/{item['cohort_rows']} | {g['median_absolute_pp']:.4f} | {g['p90_absolute_pp']:.4f} | {g['p95_absolute_pp']:.4f} |")
    common = info["paired_mark_diagnostic_successes"]
    lines.extend([
        "",
        f"On the same {common['rows']} contracts solved in both mark profiles, median absolute gap falls from "
        f"{common['default_mark_gap']['median_absolute_pp']:.4f} to {common['underlying_diagnostic_gap']['median_absolute_pp']:.4f} pp; "
        f"P95 falls from {common['default_mark_gap']['p95_absolute_pp']:.4f} to {common['underlying_diagnostic_gap']['p95_absolute_pp']:.4f} pp. "
        "Thus this reduction is not explained by comparing different surviving contract sets.",
    ])
    lines.extend([
        "",
        "The same root finder fits exchange mark IV much more closely after changing only the underlying input. "
        "This is direct evidence that input basis contributes substantially in this saved batch. It does not prove Bybit's full "
        "pricing formula, discount rate, day count or timing. Reported underlyingPrice differs from index and is constant within each expiry; "
        "the current app does not use it. Remaining discrepancies are not assigned a definite cause.",
        "", "## Added case: midpoint + assumed forward reference, D=1", "",
        "The [Bybit ticker API](https://bybit-exchange.github.io/docs/v5/market/tickers) labels underlyingPrice only as Underlying price; "
        "the documentation checked here does not establish its construction as a forward or supply a discount curve. "
        "Therefore F=reported underlyingPrice and D=1 are explicit diagnostic assumptions, not a certified Bybit convention. "
        "The field is distinct from indexPrice and constant within each expiry in this fixture, which is supporting data context rather than proof.",
        "",
        "```text",
        "d1 = [ln(F/K) + 0.5*sigma^2*T] / (sigma*sqrt(T)); d2 = d1 - sigma*sqrt(T)",
        "call = D * [F*N(d1) - K*N(d2)]",
        "put  = D * [K*N(-d2) - F*N(-d1)]",
        "D = 1; discount rate = 0; no additional carry rate",
        "```",
        "",
        "Midpoint is already in stored quote-price units, so it is not multiplied by F or index. "
        "A different discount factor would be a separate assumption; this experiment does not guess an unavailable rate.",
        "",
        "| Group | Solved / usable / cohort | Median abs gap (pp) | P95 abs gap (pp) | Median signed (pp) |",
        "| --- | --- | ---: | ---: | ---: |",
    ])
    for group in ("all", "near_atm"):
        item = info['groups'][group]['mid_underlying_D1_diagnostic']
        g = item['gaps']
        lines.append(f"| {group} | {item['solve_success_rows']}/{item['usable_price_rows']}/{item['cohort_rows']} "
                     f"| {g['median_absolute_pp']:.4f} | {g['p95_absolute_pp']:.4f} | {g['median_signed_pp']:+.4f} |")
    lines.extend([
        "", "Paired comparison uses only the same contracts solved in both midpoint profiles; ATM still means K/index within2%.", "",
        "| Paired group | Rows | Mid+index median abs (pp) | Mid+assumed F median abs (pp) | Mid+index P95 (pp) | Mid+assumed F P95 (pp) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for group, item in info['paired_mid_underlying_D1_successes'].items():
        a, b = item['default_mid_gap'], item['mid_assumed_forward_D1_gap']
        lines.append(f"| {group} | {item['rows']} | {a['median_absolute_pp']:.4f} | {b['median_absolute_pp']:.4f} "
                     f"| {a['p95_absolute_pp']:.4f} | {b['p95_absolute_pp']:.4f} |")
    lines.extend([
        "", "## Low-price numerical limitation", "",
        "A small absolute repricing residual does not guarantee an equally small IV error in very low-vega wings. "
        "The following single-contract spot check uses an independent erfc-based price expression and tighter bisection; "
        "it does not replace the production solver or the primary app-matching results.",
        "",
        "| Contract | Profile | Current solver IV (%) | Tight reference IV (%) | Solver minus reference (pp) |",
        "| --- | --- | ---: | ---: | ---: |",
    ])
    for item in info["low_price_reference_check"]:
        lines.append(f"| {item['symbol']} | {item['profile']} | {100*item['current_solver_iv']:.6f} | "
                     f"{100*item['tight_reference_iv']:.6f} | {item['solver_minus_reference_pp']:+.6f} |")
    lines.extend([
        "", "## Selected contract examples", "",
        "Selection includes nearest strikes at short/long expiries, large gaps and failures; it is illustrative, not a random sample. "
        "An em dash is a missing/failed IV, not zero. Full precision, prices, inputs and selection reasons are in CSV/JSON.",
        "",
        "| Contract | Days | K/index | Bybit mark IV (%) | Mid+index IV (%) | Mid+index gap (pp) | Mid+assumed F IV (%) | Mid+assumed F gap (pp) | MarkPrice+index IV (%) | Mark gap (pp) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in samples.itertuples():
        lines.append(f"| {row.symbol} | {row.days_to_expiry:.2f} | {row.moneyness:.4f} | {100*row.exchange_mark_iv:.2f} "
                     f"| {number(100*row.mid_iv)} | {number(row.mid_gap_pp)} | {number(100*row.mid_underlying_D1_diagnostic_iv)} "
                     f"| {number(row.mid_underlying_D1_diagnostic_gap_pp)} | {number(100*row.mark_iv)} | {number(row.mark_gap_pp)} |")
    lines.extend([
        "", "## Expiry breakdown", "",
        "| Expiry UTC | Rows | Mid successes | Mid median abs (pp) | Mark successes | Mark median abs (pp) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for expiry, entry in info["by_expiry"].items():
        mid, mark = entry["mid"], entry["mark"]
        lines.append(f"| {expiry} | {mid['cohort_rows']} | {mid['solve_success_rows']} | {mid['gaps']['median_absolute_pp']:.4f} "
                     f"| {mark['solve_success_rows']} | {mark['gaps']['median_absolute_pp']:.4f} |")
    lines.extend([
        "", "## Interpretation and reproduction", "",
        "With the current app inputs, the all-contract midpoint/mark-IV differences are material and tail-heavy; near-ATM differences are smaller. "
        "Replacing midpoint by markPrice narrows but does not remove the difference. Successful roots reprice their supplied prices closely, "
        "so a midpoint-versus-mark mismatch alone is not evidence of a broken root finder. The reported-underlying diagnostic supports an "
        "input/convention explanation, without certifying exchange parity or changing production behavior.",
        "",
        "```sh", ".venv/bin/python -B experiments/compare_bybit_mark_iv.py", "```", "",
        "Outputs: bybit_mark_iv_comparison.csv (all contracts), .json (settings, source hashes, all groups, paired rows and examples), "
        "and this .md report. Percentiles use NumPy linear interpolation and are unweighted. No live endpoint is called.",
        "",
        "Sources: repository app.py rate default; fetcher.py parse_chain_snapshot/compute_tau; surface_builder.py build_combined_surface_from_chain "
        "(spot and uncombined Call/Put grids); solver.py solve_iv/bs_price; unchanged frozen Bybit snapshot. "
        "The [official ticker API](https://bybit-exchange.github.io/docs/v5/market/tickers) distinguishes bid/ask prices, markPrice, markIv, "
        "indexPrice and underlyingPrice; it is not evidence that our current inputs reproduce the exchange pricing convention.",
        "",
    ])
    return "\n".join(lines)


def main():
    source = ROOT / "data/bybit_btc_options_snapshot.json"
    snapshot = load_chain_snapshot(source)
    chain = parse_chain_snapshot(snapshot)
    rate = app_default_rate()
    assert rate == 0., "App default changed; review this fixed comparison before rerunning"
    result = build_combined_surface_from_chain(chain, r=rate)
    frame = chain.rename(columns={"mark_iv": "exchange_mark_iv"}).copy()
    frame["app_spot_price"] = result.spot_price
    frame["days_to_expiry"] = frame.tau * 365.25
    frame["moneyness"] = frame.strike / result.spot_price
    frame["underlying_minus_index_pct"] = 100 * (frame.underlying_price / result.spot_price - 1)
    frame["expiry_utc"] = frame.expiry_dt.map(lambda value: value.isoformat())
    frame["raw_settle_suffix"] = frame.symbol.str.split("-").str[-1]
    assert not frame.duplicated(["flag", "tau", "strike"]).any()
    assert frame.raw_settle_suffix.eq("USDT").all()
    assert frame.index_price.nunique() == 1
    assert frame.exchange_mark_iv.gt(0).all()
    base_valid = frame.flag.isin(["call", "put"]) & frame.tau.gt(0) & frame.strike.gt(0) & frame.index_price.gt(0)
    for profile, (price_col, spot_col) in PROFILES.items():
        valid = base_valid & np.isfinite(frame[price_col]) & frame[price_col].gt(0) & np.isfinite(frame[spot_col]) & frame[spot_col].gt(0)
        if price_col == "mid_price":
            valid &= frame.quote_source.eq("mid")
        frame[profile + "_input_usable"] = valid
        solved = [invert(getattr(row, price_col), getattr(row, spot_col), row, rate, bool(valid.loc[row.Index])) for row in frame.itertuples()]
        frame[[profile + "_iv", profile + "_status", profile + "_price_residual"]] = pd.DataFrame(solved, index=frame.index)
        frame[profile + "_gap_pp"] = 100 * (frame[profile + "_iv"] - frame.exchange_mark_iv)
    # Match the exact app-side grids, never the Combined result.
    ei = {value: i for i, value in enumerate(result.expiries)}
    ki = {value: i for i, value in enumerate(result.strikes)}
    for row in frame.itertuples():
        grid = result.call_iv_surface if row.flag == "call" else result.put_iv_surface
        expected = grid[ei[row.tau], ki[row.strike]]
        np.testing.assert_allclose(row.mid_iv, expected, rtol=0, atol=1e-12, equal_nan=True)
    frame["mid_minus_mark_inversion_pp"] = 100 * (frame.mid_iv - frame.mark_iv)
    paired = frame[frame.mid_iv.notna() & frame.mark_iv.notna()]
    mark_paired = frame[frame.mark_iv.notna() & frame.underlying_diagnostic_iv.notna()]
    np.testing.assert_allclose(paired.mid_gap_pp, paired.mid_minus_mark_inversion_pp + paired.mark_gap_pp, atol=1e-12)
    groups = {
        "all": frame,
        "near_atm": frame[frame.moneyness.between(.98, 1.02, inclusive="both")],
        "short_le7_days": frame[frame.days_to_expiry.le(7)],
        "near_atm_short_le7_days": frame[frame.moneyness.between(.98, 1.02, inclusive="both") & frame.days_to_expiry.le(7)],
        "call": frame[frame.flag.eq("call")],
        "put": frame[frame.flag.eq("put")],
    }
    paired_mid_forward = {}
    for name in ('all', 'near_atm'):
        subset = groups[name]
        common = subset[subset.mid_iv.notna() & subset.mid_underlying_D1_diagnostic_iv.notna()]
        paired_mid_forward[name] = {
            'rows': len(common),
            'default_mid_gap': describe(common.mid_gap_pp),
            'mid_assumed_forward_D1_gap': describe(common.mid_underlying_D1_diagnostic_gap_pp),
        }
    samples = sample_indices(frame)
    wing = frame.loc[frame.symbol.eq("BTC-25SEP26-350000-C-USDT")].iloc[0]
    reference_checks = []
    for profile in ("mark", "underlying_diagnostic"):
        spot = float(wing[PROFILES[profile][1]])
        reference = tight_zero_rate_reference(wing.mark_price, spot, wing.strike, wing.tau, wing.flag)
        reference_checks.append({"symbol": wing.symbol, "profile": profile, "price_quote_units": wing.mark_price,
                                 "current_solver_iv": float(wing[profile + "_iv"]), "tight_reference_iv": reference,
                                 "solver_minus_reference_pp": float(100 * (wing[profile + "_iv"] - reference))})
    metadata = {
        "source": str(source.relative_to(ROOT)),
        "captured_at_utc": snapshot["captured_at_utc"],
        "response_time_epoch_ms": snapshot["response"].get("time"),
        "response_time_utc": datetime.fromtimestamp(snapshot["response"]["time"] / 1000, timezone.utc).isoformat(),
        "capture_minus_response_ms": datetime.fromisoformat(snapshot["captured_at_utc"].replace("Z", "+00:00")).timestamp() * 1000 - snapshot["response"]["time"],
        "rate_decimal": rate,
        "app_spot_price": result.spot_price,
        "model": "spot Black-Scholes; q=0; shared index; frozen ACT/365.25",
        "price_unit_policy": "Stored USDT-suffixed quote units, no FX conversion; no BTC conversion",
        "iv_unit": "decimal; gap_pp = 100*(computed - exchange_mark_iv)",
        "solver_sigma_bounds_decimal": [1e-6, 10.],
        "raw_iv_ranges": {name: [float(chain[name].min()), float(chain[name].max())] for name in ("bid_iv", "ask_iv", "mark_iv")},
        "profiles": {key: {"price": price, "underlying": spot, "rate_decimal": rate, "day_count": 365.25, "runtime_change": False} for key, (price, spot) in PROFILES.items()},
        "mid_underlying_D1_assumptions": {
            "formula": "Black-76 forward-price form; bs_price(F,K,T,0) is equivalent only with D=1 here",
            "F": "reported underlyingPrice; forward identification is an explicit diagnostic assumption",
            "discount_factor": 1.0, "discount_rate_decimal": 0.0, "additional_carry_rate": None,
            "field_meaning_evidence": "Official ticker API calls this Underlying price; no complete forward construction or discount curve established",
            "price_conversion": "none; stored quote units, not BTC premium",
        },
        "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, ROOT / "app.py", ROOT / "iv_surface/fetcher.py", ROOT / "iv_surface/solver.py", ROOT / "iv_surface/surface_builder.py")},
        "groups": {key: {profile: comparison(subset, profile) for profile in PROFILES} for key, subset in groups.items()},
        "by_expiry": {key: {profile: comparison(subset, profile) for profile in PROFILES} for key, subset in frame.groupby("expiry_utc", sort=True)},
        "paired_default_successes": {"rows": len(paired), "mid_minus_mark_inversion_pp": describe(paired.mid_minus_mark_inversion_pp), "mark_minus_exchange_pp": describe(paired.mark_gap_pp), "total_mid_minus_exchange_pp": describe(paired.mid_gap_pp)},
        "paired_mark_diagnostic_successes": {"rows": len(mark_paired), "default_mark_gap": describe(mark_paired.mark_gap_pp), "underlying_diagnostic_gap": describe(mark_paired.underlying_diagnostic_gap_pp)},
        "paired_mid_underlying_D1_successes": paired_mid_forward,
        "input_audit_by_expiry": {key: {"rows": len(subset), "reported_underlying_unique": subset.underlying_price.nunique(), "reported_underlying_min": float(subset.underlying_price.min()), "reported_underlying_max": float(subset.underlying_price.max()), "days_to_expiry": float(subset.days_to_expiry.iloc[0])} for key, subset in frame.groupby("expiry_utc", sort=True)},
        "low_price_reference_check": reference_checks,
        "examples": json.loads(samples.drop(columns=["expiry_dt"]).to_json(orient="records")),
    }
    frame.drop(columns=["expiry_dt"]).to_csv(OUTPUT.with_suffix(".csv"), index=False, float_format="%.12g")
    OUTPUT.with_suffix(".json").write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n")
    OUTPUT.with_suffix(".md").write_text(render_report(metadata, frame, samples))
    print(json.dumps({"rate_decimal": rate, "app_spot_price": result.spot_price,
                      "all": {key: {"solved": value['solve_success_rows'], "usable": value['usable_price_rows'],
                                    "median_absolute_pp": value['gaps']['median_absolute_pp'],
                                    "p95_absolute_pp": value['gaps']['p95_absolute_pp']}
                              for key, value in metadata['groups']['all'].items()}, "paired_rows": len(paired)}, indent=2))


if __name__ == "__main__":
    main()
