> **Historical status — 2026-11-02:** the [accepted spec](../.scratch/options-dashboard/spec.md) takes precedence. The original pending/scope/acceptance text below is history, not the latest decision status. The Deribit conventions and scope were later accepted per the spec. This experiment is research: it does not test the gamma/GEX convention at runtime. The original results, numbers and scripts are preserved in full.

# Deribit inverse-option IV: convention review checkpoint

Status: research and proposed acceptance, 2026-10-29. Dashboard/runtime behavior
has not changed. The three requested features are assigned work, not completed
or accepted implementation. This checkpoint precedes the public analytical
contract change required by AGENTS.md.

Scope update: Keng subsequently selected OI Heatmap, IV views and GEX Heatmap
as the dashboard's three main sections. That proposal was
later superseded by the accepted spec. The Part B table below records earlier
unselected alternatives; it is not the approved scope. A1's detailed convention
and the new plan still require review before runtime implementation.

## Reference and algebra

Deribit's [inverse-option specification](https://support.deribit.com/hc/en-us/articles/31424939096093-Inverse-Options)
defines index `X`, expiry forward `F`, `R = ln(F / X) / T`, and time in years on
a 365-day basis. USD display premiums use the index. The
[summary API](https://docs.deribit.com/api-reference/market-data/public-get_book_summary_by_currency)
provides `underlying_price` for IV, `underlying_index`, and a separate
`interest_rate` field. These sources were checked on 2026-10-29.

For the documented call formula, substitute `exp(-R*T) = X/F` and divide by X:

```text
d1 = [ln(F/K) + 0.5*sigma^2*T] / (sigma*sqrt(T))
d2 = d1 - sigma*sqrt(T)
call_BTC = N(d1) - (K/F)*N(d2)
put_BTC  = (K/F)*N(-d2) - N(-d1)
```

The existing repository solver can therefore invert a BTC premium `p` with
`solve_iv(p*X, X, K, T, ln(F/X)/T, flag)`. An equivalent call uses
`solve_iv(p*F, F, K, T, 0, flag)`. The latter's `p*F` is an algebraic solver
input, **not the displayed USD premium**. Multiplying by X and then using F
at zero rate would mix conventions. No independent user-guessed discount rate
is required for this documented inverse convention.

## Reproduce and evidence

```sh
.venv/bin/python -B experiments/check_deribit_iv_convention.py
```

The script uses no network, reads the checked-in snapshot, reuses the existing
root finder, and writes `deribit_iv_convention_check.json`. Its normalized
pricing expression is independent of `solver.bs_price()`.

- 216 synthetic Call/Put cases cover positive, zero and negative inferred
  rates. Maximum formula difference is 2.64e-16 BTC; maximum recovered IV error
  is 5.07e-5 in decimal volatility, within the current solver's tolerance scale.
- The real fixture has 936 instruments/summaries across 12 expiries. Every
  expiry has two or more distinct reported forward values (one has five).
  Averaging them would change the original per-contract inputs.
- All 936 API `interest_rate` values are zero, while rates derived from the
  reported F and shared index range from 0.05256 to 0.33992 annually. Do not
  assume the raw API field equals the rate inferred in the support formula.
- 900 rows have usable two-sided midpoint prices; the proposed convention
  solves 882, leaving 18 failures. Independent re-pricing of solved midpoints
  has maximum USD residual 0.000166. On the 752 midpoints solved by both this
  convention and the old zero-rate convention, the median signed IV change is
  -0.8685 percentage points. This comparison is not against exchange mark IV.
- Mark-price inversions solve 899 of 933 positive marks. Comparing those
  inversions with their own reported mark IV yields median signed difference
  0.00124 percentage points, P95 absolute difference 1.6084 points, and maximum
  35.0702 points. Therefore exact exchange mark-IV agreement is **not**
  established. Causes of individual discrepancies remain unverified; do not
  attribute them automatically to rounding, timing, or low vega.
- Independent bid/ask diagnostics in the JSON are per-contract solves. They
  are not a Combined-IV interval, a spread validation, or proof of execution.

## Proposed acceptance for implementation chunk A1

1. Deribit BTC inverse defaults to documented market-forward inputs: retain
   each contract's positive finite `underlying_price` and source identity,
   convert premium with the shared captured BTC/USD index, derive R, and
   expose the convention and inputs for inspection. No forward averaging,
   `interest_rate == 0` shortcut, or spot/manual-rate fallback.
2. Use frozen capture end as analysis time and ACT/365 for Deribit. Keep source
   expiry datetimes unchanged. Days shown in hover derive from the actual
   expiry-minus-analysis interval, not a globally assumed tau*365.25. Preserve
   Bybit's existing ACT/365.25 and user rate behavior.
3. Keep the repository's solver. Preserve invalid quotes, missing forward
   inputs and failed inversions as missing analytical values with a reason;
   no mark substitution. Test malformed inputs and verify aligned row/contract
   identity, including shuffled rows and differing forwards within one expiry.
4. Preserve spot K/S, existing Combined-IV selection/blend and bounded ATM
   proxy rules. Forward pricing does not silently redefine moneyness or ATM.
5. Mark-price/mark-IV comparisons use matching identities and price kinds;
   record residuals and failures explicitly. Synthetic formula/price recovery
   and source-specific regressions are mandatory. The frozen fixture's mark
   discrepancies must remain disclosed rather than hidden by a broad equality
   tolerance or fitted replacement forward.
6. README and UI identify the new Deribit convention. Old screenshots/counts
   describe the old implementation until refreshed. Reusable pricing remains
   independent of Streamlit. Stop for review after this chunk, before A2.

Items 1-2 are the concrete public-contract decisions to confirm at this
checkpoint: per-contract reported forward and Deribit ACT/365 at frozen capture
end. The assignment authorizes the direction; it is not evidence that these
previously unspecified decisions were accepted.

## Later assigned chunks

- A2: explicit Deribit fetch outside the UI; validate a complete replacement
  before changing session state. Retain the last good snapshot and label failed
  refresh. Tab/control changes do not fetch. Save/download and reopen preserve
  raw payload, capture times and reproducible pricing conventions. No collector
  collect-once, scheduler or VPS dependency.
- A3: invert bid, midpoint price and ask separately with the same per-contract
  pricing inputs. Mid IV is not the mean of bid/ask IV. Preserve missing sides,
  crossing/failure reasons and gap boundaries. Reuse the midpoint-selected
  Call/Put provenance; do not independently choose a different contract for
  each edge. For near-ATM blended points, proposed presentation is separate
  labeled Call and Put whiskers with the Combined-mid line; no synthetic
  executable blended spread. Confirm that presentation before implementation.

## Part B: proposals only

| Addition | Question answered | Existing raw fields / endpoint | Extra effort and stopping point |
| --- | --- | --- | --- |
| Filterable option-chain table | Which exact contract and quote produced the curve point? | Instruments: symbol, expiry, strike, call/put; summaries: bid/ask, mark, underlying_price. All already captured by the same three endpoints. Derived midpoint IV and provenance come from A1/A3. | Small after A1/A3. One expiry filter and searchable table, BTC/USD units and raw-versus-derived columns; no order entry or new endpoint. |
| OI and 24-hour volume distribution | Where are outstanding positions and recent trading concentrated across strikes/expiries? | Summary `open_interest`, `volume`, `volume_usd`, joined to instrument identity. All three fields non-null on 936/936 fixture summaries; not yet carried by the analytical parser. | Small to medium. One selectable OI/24h-volume view split by Call/Put, consistent units and totals that reconcile with included contracts. No inference of net positioning, directional flow or historical change from one snapshot. |
| Quote context in the chain/smile | Which apparent IV differences come with wide, one-sided or unusable quotes? | Summary bid/ask; derive absolute spread, spread/mid only for valid positive pairs, and quote/solve status. These prices exist now. Summary has no displayed quantities or depth. | Small when added to the table and A3 hover. Clear denominator/units and missingness; no separate liquidity score or claimed executable size. Depth/size would need an additional book endpoint and is deferred. |

The summary API documents 24-hour `volume` in base currency and option OI in
base currency units. Keep OI and volume separate; `volume_usd` must not be
silently labeled as option premium turnover. No Part B UI, repository rename,
new package, Greeks or historical feature has been selected or implemented.
