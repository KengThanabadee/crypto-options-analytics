> **Historical status — 2026-11-02:** the [accepted spec](../.scratch/options-dashboard/spec.md) takes precedence. The original pending/scope/acceptance text below is history, not the latest decision status. Under the reported-underlying assumption the gap in the frozen fixture narrows, but Bybit's full pricing convention is not established. Bybit is outside this Deribit dashboard increment, and source, price kind and input basis stay separate. The original results, numbers and scripts are preserved in full.

# Bybit midpoint IV versus exchange mark IV

Offline experiment only. Runtime/dashboard and pricing contracts are unchanged.

Snapshot: **2026-09-02T12:58:21.965864Z**, 660 individual BTC option contracts.
Current app default: spot Black–Scholes, r=0.00% continuously compounded, shared index S=76653.09446908, ACT/365.25, expiry at 08:00 UTC parsed from symbol.
The response server clock is 2026-09-02T12:58:21.870000+00:00, about 95.864 ms before local capture. The app uses local frozen capture time for tau, not the server clock or today's date.
No Combined or interpolated IV is used in the comparison. Each row retains its Call/Put identity.

## What is being compared

1. **Mid:** invert the arithmetic midpoint of usable bid/ask prices exactly as in the current app, then subtract Bybit markIv.
2. **Mark:** invert Bybit markPrice with the same spot/rate/tau/solver, then subtract markIv. This changes the price input only.
3. **Underlying diagnostic:** invert markPrice with reported underlyingPrice instead of index; keep r=0 and ACT/365.25. This is a labeled sensitivity experiment, not a changed app or a verified full exchange convention.
4. **Mid + assumed F, D=1:** invert midpoint with reported underlyingPrice treated as F in a Black-76 forward-price form, discount factor D=1. The existing bs_price(F,K,T,r=0) is algebraically equivalent in this case; no nonzero carry rate is applied again. Frozen ACT/365.25, quote units and ATM cohort stay unchanged.

IVs in raw Bybit fields are decimal: e.g. markIv=1.0608 means 106.08%. Gaps are volatility percentage points: 100*(our_decimal_IV - exchange_decimal_IV). Positive means ours is higher; 40% versus38% is+2 points, not+2% relative.
All snapshot symbols have the -USDT suffix. Prices are used in their stored quote units alongside strike/index, with no BTC-premium multiplication or stablecoin/USD FX conversion. The fixture does not contain a full instrument-spec response.

## Primary results (unweighted contract observations)

Near ATM is inclusive0.98<=K/S<=1.02, using app spot. Short expiry means remaining time<=7 actual days at capture.
The groups overlap. Different solve counts mean marginal statistics are not a paired causal decomposition.

| Group | Price inverted | Successful / usable / cohort | Median abs gap (pp) | P90 abs (pp) | P95 abs (pp) | Median signed (pp) |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| all | mid | 565/630/660 | 3.0485 | 16.2658 | 31.6881 | +1.3046 |
| all | mark | 603/660/660 | 1.3480 | 12.1587 | 24.7309 | +0.1204 |
| near_atm | mid | 90/90/90 | 0.6905 | 3.6923 | 4.7095 | -0.0006 |
| near_atm | mark | 90/90/90 | 0.4235 | 2.9049 | 4.5341 | +0.0067 |
| short_le7_days | mid | 147/164/182 | 1.3920 | 16.9608 | 52.6841 | +0.3299 |
| short_le7_days | mark | 172/182/182 | 0.2289 | 6.5331 | 26.5862 | +0.0603 |
| near_atm_short_le7_days | mid | 52/52/52 | 0.3779 | 1.9456 | 3.0807 | -0.0006 |
| near_atm_short_le7_days | mark | 52/52/52 | 0.2613 | 0.4439 | 0.4621 | +0.0067 |

## Coverage, sign bias and solver checks

| Profile | Input unusable | Solve failed | Positive gaps | Mean signed gap (pp) | Max repricing residual (quote units) |
| --- | ---: | ---: | ---: | ---: | ---: |
| mid | 30 | 65 | 67.4% | +5.9937 | 0.00016050 |
| mark | 0 | 57 | 55.1% | +3.8852 | 0.00016188 |
| underlying_diagnostic | 0 | 0 | 100.0% | +0.0118 | 0.00009339 |
| mid_underlying_D1_diagnostic | 30 | 32 | 68.1% | +3.0917 | 0.00012573 |

Signed bias should also be read by option type; pooled Call/Put signs can cancel.

| Side | Price | Comparable rows | Median signed (pp) | Positive gaps |
| --- | --- | ---: | ---: | ---: |
| call | mid | 313 | +4.1957 | 98.4% |
| call | mark | 330 | +2.2798 | 100.0% |
| put | mid | 252 | -1.0701 | 29.0% |
| put | mark | 273 | -1.0060 | 0.7% |

Failure reasons are saved per contract in CSV and reconciled in JSON. A below-bracket mark price means no IV solution within this model's current bracket at those inputs; it does not establish a bad exchange quote under its own inputs. No boundary-sigma returns occurred in this fixture. Successful direct midpoint inversions match the app's uncombined Call/Put grids.
The 565 rows where both primary inversions succeed are separately summarized in JSON. For each such row, (mid IV - markPrice-inverted IV) + (markPrice-inverted IV - exchange markIv) = total midpoint gap. Medians/P95 of those terms are not additive.

## Reported-underlying diagnostic

| Group | Successful / cohort | Median abs gap (pp) | P90 abs (pp) | P95 abs (pp) |
| --- | --- | ---: | ---: | ---: |
| all | 660/660 | 0.0100 | 0.0185 | 0.0233 |
| near_atm | 90/90 | 0.0060 | 0.0108 | 0.0115 |
| short_le7_days | 182/182 | 0.0103 | 0.0220 | 0.0274 |

On the same 603 contracts solved in both mark profiles, median absolute gap falls from 1.3480 to 0.0096 pp; P95 falls from 24.7309 to 0.0220 pp. Thus this reduction is not explained by comparing different surviving contract sets.

The same root finder fits exchange mark IV much more closely after changing only the underlying input. This is direct evidence that input basis contributes substantially in this saved batch. It does not prove Bybit's full pricing formula, discount rate, day count or timing. Reported underlyingPrice differs from index and is constant within each expiry; the current app does not use it. Remaining discrepancies are not assigned a definite cause.

## Added case: midpoint + assumed forward reference, D=1

The [Bybit ticker API](https://bybit-exchange.github.io/docs/v5/market/tickers) labels underlyingPrice only as Underlying price; the documentation checked here does not establish its construction as a forward or supply a discount curve. Therefore F=reported underlyingPrice and D=1 are explicit diagnostic assumptions, not a certified Bybit convention. The field is distinct from indexPrice and constant within each expiry in this fixture, which is supporting data context rather than proof.

```text
d1 = [ln(F/K) + 0.5*sigma^2*T] / (sigma*sqrt(T)); d2 = d1 - sigma*sqrt(T)
call = D * [F*N(d1) - K*N(d2)]
put  = D * [K*N(-d2) - F*N(-d1)]
D = 1; discount rate = 0; no additional carry rate
```

Midpoint is already in stored quote-price units, so it is not multiplied by F or index. A different discount factor would be a separate assumption; this experiment does not guess an unavailable rate.

| Group | Solved / usable / cohort | Median abs gap (pp) | P95 abs gap (pp) | Median signed (pp) |
| --- | --- | ---: | ---: | ---: |
| all | 598/630/660 | 0.6962 | 14.3351 | +0.2344 |
| near_atm | 90/90/90 | 0.1197 | 1.8844 | +0.0355 |

Paired comparison uses only the same contracts solved in both midpoint profiles; ATM still means K/index within2%.

| Paired group | Rows | Mid+index median abs (pp) | Mid+assumed F median abs (pp) | Mid+index P95 (pp) | Mid+assumed F P95 (pp) |
| --- | ---: | ---: | ---: | ---: | ---: |
| all | 565 | 3.0485 | 0.6621 | 31.6881 | 15.3125 |
| near_atm | 90 | 0.6905 | 0.1197 | 4.7095 | 1.8844 |

## Low-price numerical limitation

A small absolute repricing residual does not guarantee an equally small IV error in very low-vega wings. The following single-contract spot check uses an independent erfc-based price expression and tighter bisection; it does not replace the production solver or the primary app-matching results.

| Contract | Profile | Current solver IV (%) | Tight reference IV (%) | Solver minus reference (pp) |
| --- | --- | ---: | ---: | ---: |
| BTC-25SEP26-350000-C-USDT | mark | 119.561582 | 119.386652 | +0.174930 |
| BTC-25SEP26-350000-C-USDT | underlying_diagnostic | 119.379647 | 119.203489 | +0.176158 |

## Selected contract examples

Selection includes nearest strikes at short/long expiries, large gaps and failures; it is illustrative, not a random sample. An em dash is a missing/failed IV, not zero. Full precision, prices, inputs and selection reasons are in CSV/JSON.

| Contract | Days | K/index | Bybit mark IV (%) | Mid+index IV (%) | Mid+index gap (pp) | Mid+assumed F IV (%) | Mid+assumed F gap (pp) | MarkPrice+index IV (%) | Mark gap (pp) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BTC-3SEP26-76750-C-USDT | 0.79 | 1.0013 | 31.89 | 32.220 | 0.330 | 32.075 | 0.185 | 32.037 | 0.147 |
| BTC-3SEP26-76750-P-USDT | 0.79 | 1.0013 | 31.89 | 31.382 | -0.508 | 31.545 | -0.345 | 31.729 | -0.161 |
| BTC-25JUN27-76000-C-USDT | 295.79 | 0.9915 | 41.81 | 48.951 | 7.141 | 42.207 | 0.397 | 48.553 | 6.743 |
| BTC-25JUN27-76000-P-USDT | 295.79 | 0.9915 | 41.81 | 37.615 | -4.195 | 42.021 | 0.211 | 37.408 | -4.402 |
| BTC-25SEP26-20000-C-USDT | 22.79 | 0.2609 | 131.98 | 270.063 | 138.083 | 214.395 | 82.415 | 261.871 | 129.891 |
| BTC-26MAR27-110000-P-USDT | 204.79 | 1.4350 | 41.88 | 19.422 | -22.458 | 41.144 | -0.736 | 24.188 | -17.692 |
| BTC-26MAR27-10000-C-USDT | 204.79 | 0.1305 | 90.89 | 227.200 | 136.310 | 126.916 | 36.026 | 222.784 | 131.894 |
| BTC-25JUN27-110000-P-USDT | 295.79 | 1.4350 | 42.48 | 27.890 | -14.590 | 41.768 | -0.712 | 29.245 | -13.235 |
| BTC-11SEP26-86000-P-USDT | 8.79 | 1.1219 | 39.52 | — | — | 38.943 | -0.577 | — | — |
| BTC-25SEP26-130000-C-USDT | 22.79 | 1.6960 | 64.34 | — | — | — | — | 64.630 | 0.290 |

## Expiry breakdown

| Expiry UTC | Rows | Mid successes | Mid median abs (pp) | Mark successes | Mark median abs (pp) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-09-03T08:00:00+00:00 | 52 | 40 | 0.8134 | 48 | 0.1293 |
| 2026-09-04T08:00:00+00:00 | 88 | 65 | 2.9689 | 82 | 0.1960 |
| 2026-09-05T08:00:00+00:00 | 42 | 42 | 0.6650 | 42 | 0.3475 |
| 2026-09-11T08:00:00+00:00 | 62 | 56 | 2.1674 | 56 | 0.6386 |
| 2026-09-18T08:00:00+00:00 | 42 | 38 | 1.4144 | 38 | 0.8777 |
| 2026-09-25T08:00:00+00:00 | 108 | 81 | 3.1224 | 94 | 0.8202 |
| 2026-10-30T08:00:00+00:00 | 76 | 73 | 2.4110 | 73 | 2.0335 |
| 2026-12-25T08:00:00+00:00 | 66 | 57 | 3.8162 | 57 | 2.4521 |
| 2027-03-26T08:00:00+00:00 | 70 | 64 | 4.9281 | 64 | 3.7010 |
| 2027-06-25T08:00:00+00:00 | 54 | 49 | 4.7341 | 49 | 4.6420 |

## Interpretation and reproduction

With the current app inputs, the all-contract midpoint/mark-IV differences are material and tail-heavy; near-ATM differences are smaller. Replacing midpoint by markPrice narrows but does not remove the difference. Successful roots reprice their supplied prices closely, so a midpoint-versus-mark mismatch alone is not evidence of a broken root finder. The reported-underlying diagnostic supports an input/convention explanation, without certifying exchange parity or changing production behavior.

```sh
.venv/bin/python -B experiments/compare_bybit_mark_iv.py
```

Outputs: bybit_mark_iv_comparison.csv (all contracts), .json (settings, source hashes, all groups, paired rows and examples), and this .md report. Percentiles use NumPy linear interpolation and are unweighted. No live endpoint is called.

Sources: repository app.py rate default; fetcher.py parse_chain_snapshot/compute_tau; surface_builder.py build_combined_surface_from_chain (spot and uncombined Call/Put grids); solver.py solve_iv/bs_price; unchanged frozen Bybit snapshot. The [official ticker API](https://bybit-exchange.github.io/docs/v5/market/tickers) distinguishes bid/ask prices, markPrice, markIv, indexPrice and underlyingPrice; it is not evidence that our current inputs reproduce the exchange pricing convention.
