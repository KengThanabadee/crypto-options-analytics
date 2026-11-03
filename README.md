# implied-vol-surface

A small personal quant library for learning and building implied-volatility tooling from first principles.

`implied-vol-surface` provides Black-Scholes pricing helpers, implied-volatility root finding, surface construction, interpolation, and a Deribit BTC option-chain input.

The implied-volatility root-finding logic is implemented without `scipy.optimize`.

## Status

This is an early local package in a personal quant-library ecosystem. It is useful for experiments and for feeding downstream projects, but it is not production trading infrastructure and is not financial advice.

The repository also ships a BTC options dashboard (`app.py`) built on the
library. It shows three sections for one Deribit snapshot, top to bottom:

1. **Open interest** by strike, in BTC.
2. **Gamma exposure (GEX)** by strike, in USD per 1% BTC move, under a stated
   customer/dealer assumption.
3. **Implied volatility**: heatmap, 3D surface, smiles and ATM term structure,
   from either of two [IV sources](#iv-sources).

See the [Dashboard preview](#dashboard-preview) for images and
[Offline dashboard](#offline-dashboard) for every control.

### IV sources

- **Exchange mark** is the `mark_iv` Deribit reports. It is the default IV
  source and the gamma input.
- **Quote midpoint** is this repository's solver IV from usable bid/ask
  midpoints. It is the comparison source.

The IV charts open on Exchange mark and an **IV source** selector switches
them to Quote midpoint. The selector changes only the IV charts and reuses the
loaded snapshot. Both sources follow the same Combined IV and ATM proxy rules;
a contract whose selected-source IV is unusable is missing, never filled from
the other source. Hover names the IV source beside each IV value.

Quote midpoint IV uses Deribit's inverse-option convention: the index `X` is
spot and each contract's reported forward `F` sets `R = ln(F / X) / T`, so no
rate is chosen. A solved IV must reprice the USD midpoint within $0.01, or it
counts as missing.

The smile shades a **bid–ask IV display band** in both modes: our solver
inverts bid and ask separately with the same forward rate, and the band blends
them with the line's Call/Put weights (bid with bid and ask with ask in the
`0.98–1.02` zone). It is a display band, not a tradable quote, and mark IV may
sit outside it.

## What It Does

- Prices European calls and puts with Black-Scholes.
- Solves implied volatility with Newton-Raphson and bisection fallback.
- Builds a 2D IV surface from a grid of option prices.
- Interpolates IV inside an expiry/strike grid with bilinear interpolation.
- Adapts frozen Deribit BTC inverse-option snapshots to a chain DataFrame with USD premiums, using the captured BTC/USD index and keeping market quotes separate from exchange mark values.
- Converts usable option-chain mid prices into the expiry/strike grid used by the surface builder.
- Combines aligned Call and Put surfaces with a spot-based, auditable selection rule.

## Dashboard preview

These images are screenshots of the running dashboard on the checked-in
Deribit BTC snapshot captured on **2026-10-15 at 15:18:14 UTC** (index
$82,227.73), at the page defaults: All expiries, Near spot strike range,
Call+ / Put−, Net, Exchange mark IV and the Core moneyness range.
`scripts/capture_readme_images.py` retakes them from a dashboard started on
that snapshot. Open the [offline dashboard](#offline-dashboard) to explore the
charts and their tooltips interactively.

### Open interest and gamma exposure

![Open interest by strike in BTC with Call and Put bars, above Net gamma exposure by strike in USD per 1% BTC move under the Call+ / Put− scenario, in one chart with a shared strike axis and a dashed index line.](docs/images/oi-gex.jpg)

**Open interest** is in BTC: each Deribit BTC option contract is one BTC, so
the bars are contract counts summed over the selected expiries, Calls and Puts
side by side. The dashed line marks the index.

**GEX** is in **USD per 1% BTC move**: roughly how many USD of BTC a dealer
would buy or sell to stay hedged if the index moved 1%, with every forward
moving with it. Each contract adds `s × gamma × OI × index² × 1%`, with gamma
from Exchange mark IV (see [`net_gex_by_strike`](#net_gex_by_strikechain-expiriesnone-signsnone)).

Deribit does not publish who holds each side, so the sign `s` comes from an
**assumption** you choose per option type. **Customer sells** means the dealer
bought the option and is long gamma (`s = +1`, a positive bar); **Customer
buys** means the dealer is short gamma (`s = −1`, a negative bar). The default
Call+ / Put− reads: customers sell calls and buy puts. The chart title states
the assumption as a scenario, not observed dealer inventory.

- **Net** (default) adds the signed contributions, so Calls and Puts at a
  strike can cancel. It depends on the assumption.
- **Gross** adds their magnitudes. It shows how much gamma sits at a strike
  and does not change with the assumption; it is always at least the size of
  Net.

A strike is drawn as a bar only when every contract in it has OI and mark IV.
When only some do, the strike shows an **Incomplete data** marker with the
partial subtotal, the usable/total contract count and what is missing; when
none do, it shows **Insufficient data**. Neither is drawn as a zero bar. The
title counts complete strikes; on this snapshot all 91 strikes are complete.

### Combined IV heatmap

![Implied volatility section with the IV source selector on Exchange mark, above the Combined IV heatmap across moneyness and UTC expiry.](docs/images/heatmap.jpg)

The **IV source** selector at the top of the section switches every IV chart
between **Exchange mark** (Deribit's `mark_iv`, the default and the GEX input)
and **Quote midpoint** (this repository's solver on bid/ask midpoints); see
[IV sources](#iv-sources). It never changes OI or GEX.

Color shows IV across spot moneyness (`K / S`) and expiry. This is Surface mode
in the Core range (`0.8–1.2`): observed values are preserved, supported gaps are
filled by 2D total-variance interpolation, and unsupported cells remain blank.
Expiry rows have equal height and are ordered by maturity.

### 3D surface

The same interpolated values are shown in 3D, with numerical time to expiry
controlling maturity spacing. Orange points show the original observed Combined
IV; the surface is an interpolated display rather than an arbitrage-free fit.

![3D Combined IV surface with observed values overlaid as orange points.](docs/images/surface.jpg)

### IV smiles

Compare observed Combined IV across strikes for selected expiries. The example
uses the first three usable expiries; each curve retains its missing-value gaps
and does not use the surface interpolation. The shaded area is the bid–ask IV
display band; it is wide where quotes are wide, as on the one-day expiry.

![Observed IV smile curves with bid–ask display bands for the first three usable Deribit expiries.](docs/images/iv-smiles.jpg)

### ATM term structure

Compare observed near-ATM IV across all expiries. Each expiry uses the nearest
finite Combined IV within 2% of spot, averaging equally near strikes. Dates are
spaced by numerical maturity; expiries without an eligible proxy remain gaps.

![ATM IV term structure across UTC expiry dates, spaced by maturity.](docs/images/atm-term-structure.jpg)

## Module Boundaries

- `iv_surface.deribit` validates frozen BTC inverse-option snapshots and adapts
  their metadata, BTC quotes and index to the canonical option-chain DataFrame.
- `iv_surface.chain` holds the shared parsing helpers: time to expiry, number
  parsing, bid/ask mid price and UTC timestamps.
- `iv_surface.surface_builder` converts that canonical chain into option-price
  grids and side-specific or Combined IV surfaces.
- `iv_surface.solver` owns Black-Scholes pricing, IV root finding, grid solving,
  and interpolation.
- `iv_surface.surface_transforms` reshapes IV surfaces and selects the bounded
  ATM proxy without requiring Plotly.
- `iv_surface.positioning` sums open interest and net gamma exposure by
  strike and holds the Near spot strike range, without requiring Plotly.
- `iv_surface.visualization` constructs Plotly figures from prepared frames.

## Core Data Shape

IV surface arrays use expiry rows and strike columns:

```text
iv_surface.shape == (len(expiries), len(strikes))
iv_surface[i, j] == IV at expiries[i], strikes[j]
```

Example layout:

```text
              K=90   K=100   K=110
T=0.10        0.18    0.20    0.22
T=0.25        0.19    0.21    0.23
T=0.50        0.20    0.22    0.24
```

Accordingly, the surface APIs take `expiries` before `strikes`, and interpolation uses `target_T` and `target_K`.

## Installation

Install locally in editable mode:

```bash
pip install -e .
```

For development dependencies:

```bash
pip install -e ".[dev]"
```

## Offline dashboard

From the repository root:

```bash
pip install -e ".[dashboard]"
python -m streamlit run app.py
```

Streamlit prints a local URL (by default `http://localhost:8501`); open it in a
browser. A typical session:

1. **Fetch latest** to pull a fresh Deribit snapshot, or keep the checked-in
   one to work offline.
2. **Explore** the three sections: pick OI expiries and a strike range, set
   the Calls/Puts assumption and Net/Gross for GEX, then switch the IV source
   and IV views below.
3. **Save analysis** in the sidebar to download one JSON file with the raw
   snapshot and every setting.
4. **Reopen analysis** with that file later: the page returns to the same
   snapshot and settings and recomputes the same numbers.

The dashboard opens on the checked-in Deribit BTC snapshot and runs offline;
the header shows the capture time. **Fetch latest** pulls a new snapshot from
Deribit's public API and the whole page switches to it, with its capture time.
A failed fetch keeps the current snapshot and shows the error. Only that button
fetches; every other control reuses the current snapshot.

**Save analysis** in the sidebar downloads one JSON file with the raw snapshot
(every API response with its capture times) and the settings: OI/GEX expiries,
strike range, Call/Put customer sides, Net/Gross, IV source, moneyness range,
heatmap values and smile expiries. **Reopen analysis** loads such a file,
restores every setting and recomputes every number from the raw snapshot; the
header then reads "Reopened snapshot". A file saved with a different
calculation version opens with a short recompute notice. An invalid file shows
an error and keeps the current analysis.

The top of the page, **Open interest and gamma exposure**, is one chart with
two panels that share a strike axis: a strike sits at the same x in both, and
a drag-zoom in either panel zooms both. The controls sit above the chart. The
top panel shows Open Interest by strike: Call and Put bars in BTC, summed over
the selected expiries, with a dashed line at the index. It starts
at All expiries; the OI expiry selection is separate from the IV charts'
expiries. The strike range starts at Near spot, ±10% around the index with
both ends included, and **Near spot** resets it. The range is a display zoom
only. A range with no listed strikes shows "No strikes in this range" with a
button that zooms out to every strike; the GEX controls keep their values.
Hover shows the strike, Call and Put OI in BTC and the expiry scope.

The bottom panel shows gamma exposure (GEX) by strike, with the same expiry
selection, strike range and index line. Bars are in USD per 1%
BTC move, computed from Exchange mark IV. Two controls, **Calls** and
**Puts**, each set Customer sells or Customer buys, with the dealer as
counterparty: customer sells gives the dealer positive gamma, customer buys
negative. One choice per option type covers every strike and expiry. A new
snapshot starts at Call+ / Put− (Calls customer sells, Puts customer buys).
**GEX view** switches between **Net** (the default; signed contributions,
so Calls and Puts can cancel) and **Gross** (the sum of contribution
magnitudes, unaffected by the assumption). Flipping a control recomputes the
signs from the loaded snapshot without fetching; OI, IV and gamma
magnitudes stay the same. The panel title names the source, unit, the share of OI
whose GEX is computable and how many strikes are complete, both over every
strike in the selected expiries, and the active assumption as a scenario, not
observed dealer inventory. Hover shows Net or Gross GEX, the Call and Put
subtotals (magnitudes in Gross), Call and Put OI, the contract count, the
scenario and the expiry scope. A strike where only some contracts are
computable shows an Incomplete data marker instead of a bar, with the labelled
partial subtotal in the selected Net/Gross view, usable/total contracts, the
computable OI share (when all OI is known) and the reason; a strike with none
shows Insufficient data and the reason. Markers sit in a strip near the top of
the GEX panel, away from zero.

Below it, the dashboard shows a Combined IV heatmap, 3D surface, IV smiles, and ATM term
structure. IV smiles use original observed
values across all strikes, with an independent expiry checklist. The ATM view
uses every expiry and selects the nearest finite Combined IV within 2% of spot,
averaging equally near strikes. Expiries without an eligible proxy remain gaps;
selection details show their status. Numerical maturity (`tau`) controls spacing.
All chart tooltips show source expiry dates in UTC, time to expiry in days
(`tau × 365`), and `tau` in years, using the frozen snapshot time. The 3D
view switches to a compact layout when its available width is below 700px.

The default `0.80 <= K / S <= 1.20` surface fills missing
grid cells with 2D piecewise-linear total-variance interpolation. It converts
observed IV to `w = IV² × tau`, interpolates across spot moneyness and numerical
`tau`, then converts back with `IV = sqrt(w / tau)`. Both axes are scaled to
their observed min/max ranges before triangulation. Support uses only original
finite observations inside the selected display range; observed values stay
unchanged and cells outside their convex hull remain missing. The Heatmap can switch back to unfilled
Observed values, and both charts can switch to an extended
`0.70 <= K / S <= 1.30` range. Hover distinguishes Observed, Interpolated, and
Missing cells, with `2D linear total variance` as the interpolated value source.
`interpolate_surface_2d()` in `surface_transforms.py` performs this operation
independently of the UI and retains original IV in `observed_iv`, quote
provenance in `source`, and the display method in `interpolation_method`.
Fewer than three non-collinear observations leave missing cells unfilled.
This fills the existing grid rather than adding dense display points.

### Deribit input

`data/deribit_btc_options_snapshot.json` preserves the raw responses from
[`public/get_instruments`](https://docs.deribit.com/api-reference/market-data/public-get_instruments),
[`public/get_book_summary_by_currency`](https://docs.deribit.com/api-reference/market-data/public-get_book_summary_by_currency),
and [`public/get_index_price`](https://docs.deribit.com/api-reference/market-data/public-get_index_price).
The version-1 envelope records `exchange: deribit`, `currency: BTC`, `base_url`,
UTC capture start/end and a `requests` list containing each endpoint, parameters,
UTC receive time and unchanged JSON-RPC response. The requests are sequential,
so the envelope records a capture interval rather than an atomic exchange snapshot.
Recurring historical collection belongs to the separate collector project.

The adapter accepts BTC inverse options with one-BTC contract size. Instrument
metadata supplies strike, option type and expiration timestamp. It retains
instruments with missing books as missing quotes and rejects ambiguous identities
or unsupported currencies. A valid mid requires positive, finite, uncrossed
bid and ask; mark and exchange-provided mid values never fill absent quotes.

[BTC inverse-option premiums are quoted in BTC](https://support.deribit.com/hc/en-us/articles/31424939096093-Inverse-Options).
The adapter multiplies bid/ask premiums by the captured BTC/USD index to obtain
USD per BTC, retaining BTC fields as `bid_price_btc`, `ask_price_btc`,
`mid_price_btc` and `mark_price_btc`. That same index is the shared spot.
Source expiry timestamps and the frozen capture end determine `tau` on a
365-day year, matching Deribit. Contracts whose `tau` is zero or below at the
capture end have settled and are left out; every contract still before expiry
is kept, however close. `mark_iv` is normalized from percent to decimal.

Each contract also carries `open_interest` in BTC and its reported forward
`underlying_price`; a missing value stays `NaN`, never zero. The book
summary's `estimated_delivery_price` is kept as raw data only: the index from
`get_index_price` stays the one spot for USD conversion and moneyness.

Quote midpoint IV uses this repository's Black-Scholes solver at each
contract's forward-implied rate (see [IV sources](#iv-sources)), so it need
not equal Exchange mark IV.

## Quick Example

```python
import numpy as np

from iv_surface.solver import bs_price, build_surface, interpolate_iv

spot_price = 100
r = 0.03
sigma = 0.20

expiries = [0.10, 0.25, 0.50]
strikes = [90, 100, 110]

option_price_grid = np.array([
    [bs_price(spot_price, K, T, r, sigma, "call") for K in strikes]
    for T in expiries
])

iv_surface = build_surface(
    option_price_grid, spot_price, expiries, strikes, r, flag="call"
)
iv = interpolate_iv(iv_surface, expiries, strikes, target_T=0.18, target_K=97)

print(iv_surface)
print(iv)
```

## API

### `bs_price(spot_price, K, T, r, sigma, flag, t=0)`

Returns the Black-Scholes price for a European call or put.

### `solve_iv(option_price, spot_price, K, T, r, flag, sigma_low=1e-6, sigma_high=10.0)`

Returns implied volatility for a single option price. Raises `ValueError` for invalid inputs, expired options, or prices outside the bracket implied by the sigma bounds.

### `build_surface(option_price_grid, spot_price, expiries, strikes, r=0, flag="call")`

Returns a 2D NumPy array of implied volatilities with shape `(n_expiries, n_strikes)`. Cells that cannot be solved are filled with `NaN`.

### `interpolate_iv(iv_surface, expiries, strikes, target_T, target_K)`

Returns bilinearly interpolated IV at the target `(T, K)`. Raises `ValueError` if the target point is outside the grid or if the grid is not valid.

### `load_deribit_snapshot(path)` and `parse_deribit_snapshot(snapshot)`

`load_deribit_snapshot` reads and validates a frozen Deribit snapshot offline.
`parse_deribit_snapshot` returns a tidy pandas DataFrame with strike, flag, USD
and BTC bid/ask prices, mid price, mark price, mark IV, index price, open
interest (BTC), reported forward (`underlying_price`),
`estimated_delivery_price`, expiry and time to expiry. Settled contracts are
left out.

### `fetch_deribit_snapshot(session=None)`

Captures a new snapshot from Deribit's public API in the same version-1
envelope as the frozen file: the three requests in order, each with its UTC
receive time and unchanged JSON-RPC response. The capture starts just before
the first request and ends at the last response. Each request has a 15 s
timeout. Network, HTTP, JSON-RPC and validation failures raise
`DeribitFetchError`.

`mid_price` is computed only from valid positive bid/ask quotes. If the bid/ask quote is not usable, `mid_price` is `NaN` and `quote_source` is `"none"`; the adapter does not fall back to `mark_price`.

### `prepare_surface_inputs(chain, flag="call")`

Filters a parsed option-chain DataFrame to usable bid/ask mid prices and returns `option_price_grid`, `spot_price`, `expiries`, and `strikes` for `build_surface`.

`spot_price` is the median `index_price` across usable rows. If usable rows have different `index_price` values, a warning is emitted.

### `build_surface_from_chain(chain, flag="call", r=0)`

Convenience wrapper for `prepare_surface_inputs()` followed by
`build_surface()`. The chain comes from a parsed snapshot.

Returns the IV surface together with the option price grid, spot price, expiries, and strikes. Missing usable quotes remain `NaN` in the price grid and IV surface.

### `build_iv_source_surface(chain, iv_source, bid_ask_iv=None)`

In `iv_surface/iv_source.py`. `iv_source` is `"Exchange mark"` or
`"Quote midpoint"`. Returns the Combined IV surface (`iv_surface`,
`source_grid`, the side surfaces `call_iv_surface` and `put_iv_surface`) for
that source only, plus the bid–ask display band as `band_low` and `band_high`,
with `spot_price`, `expiries` and `strikes`. The band does not depend on the
source: pass `bid_ask_iv=solve_bid_ask_iv(chain)` to solve each contract's
bid and ask IV once and reuse them for both sources. `contract_iv(chain, iv_source)`
returns the per-contract IV, and `iv_source_long_frame(result,
expiry_datetimes=None)` returns the chart frame with `band_low`, `band_high`
and `iv_source` columns. The figure builders take an optional `iv_source` to
name it in hover.

### `build_combined_surface_from_chain(chain, r=0)`

Builds aligned Call and Put surfaces with one shared median `spot_price`, then
returns one Combined IV per expiry/strike together with the separate Call/Put
inputs and IVs. Selection is spot-based:

- below `K / S = 0.98`, prefer Put IV;
- from `0.98` through `1.02`, average same-strike Call/Put IV when both solve;
- above `K / S = 1.02`, prefer Call IV.

If the preferred side is unavailable, the other side may be used with an
explicit value in `source_grid`; if neither side solves, the Combined IV stays
`NaN`. Within the near-ATM band, the blend is the arithmetic mean of separately
solved Call and Put IVs at the same expiry and strike when both are available.

### `open_interest_by_strike(chain, expiries=None)`

Returns `strike`, `call_oi` and `put_oi` (BTC) summed over the given `tau`
values, or over All expiries when `expiries` is `None`. A strike with no
contract of one type has zero OI for that type; a contract with missing OI
makes that strike's sum `NaN`, never zero. `near_spot_range(index_price)`
returns the ±10% default range and `strikes_in_range(table, strike_range)`
keeps rows inside it, both ends included.

### `net_gex_by_strike(chain, expiries=None, signs=None)`

Each contract contributes `s × gamma × OI × X² × 0.01` USD per 1% BTC move,
where `X` is the index, OI is in BTC and `s` is `+1` where the customer sells
(dealer long gamma) and `−1` where the customer buys. `signs` maps `call` and
`put` to `s`; the default `DEFAULT_SIGNS` is Call+ / Put−. Returns `strike`,
`net_gex`, `gross_gex`, `call_gex`, `put_gex`, `call_oi`, `put_oi` and
`contracts`, plus `status`, `partial_net_gex`, `partial_gross_gex`, `usable`,
`oi_share` and `reason` from `strike_coverage(rows, values)`. `gross_gex` sums
`abs(contribution)` and does not depend on `signs`. A contract with known zero
OI contributes zero even without IV; missing OI or mark IV leaves it
non-computable, with no midpoint or interpolated IV filled in. `status` is
`complete` (every contract computable, `net_gex`/`gross_gex` are the sums, a
true zero included), `incomplete` (some: both `NaN`, the `partial_*` columns
sum the computable contracts) or `insufficient` (none: all `NaN`). `oi_share`
is the strike's computable OI share, `NaN` unless every OI is known; `reason`
counts the missing inputs by type, e.g. `1 Put: no mark IV`. `strike_coverage`
takes the values to add: signed contributions for Net, magnitudes for Gross.
`gex_contributions(chain, signs)`
returns the per-contract rows and `computable_oi_share(gex_table)` the share
of OI with a computable contribution, from a `net_gex_by_strike` table.

`contract_gamma(strike, tau, mark_iv, forward, index_price)` is the spot gamma
of the contract's USD value per USD of index move, with the index and every
forward moving together: `phi(d1) / (X × sigma × sqrt(T))`, with `d1` from
undiscounted Black-76 on the contract's reported forward and its own `mark_iv`
and `tau`. Deribit's ticker gamma is per USD of the forward; multiply ours by
`X / F` to compare. `tests/test_gex.py` checks this against a one-time ticker
capture in `data/deribit_btc_gamma_check_*.json`
(`experiments/capture_deribit_ticker_gamma.py`).

### `save_analysis(snapshot, settings)` and `open_analysis(raw)`

`save_analysis` returns the saved-analysis JSON text:
`{"format": "btc-options-analysis", "format_version": 1,
"calculation_version": N, "snapshot": {...}, "settings": {...}}`. It stores
no computed numbers. Settings are `oi_expiries` and `smile_expiries` (expiry
datetimes, saved as UTC `YYYY-MM-DDTHH:MM:SSZ`; empty OI expiries means All
expiries), `strike_range` and `moneyness_range` as `(low, high)`, `signs`
(`call`/`put` → ±1), `gex_view` (`Net`/`Gross`), `iv_source` and
`heatmap_values` (`Surface`/`Observed`). `open_analysis` validates the file,
the snapshot and every setting against that snapshot and raises `ValueError`
on any problem. Its `SavedAnalysis` result has `snapshot`, `settings`,
`calculation_version`, `version_differs` and the parsed `chain`. `CALCULATION_VERSION` goes up
whenever a change alters a number computed from the same snapshot and
settings.

## Assumptions And Limitations

- Uses Black-Scholes European option assumptions.
- Time to expiry is measured in years of 365 days.
- No dividend yield parameter yet.
- IV solving requires `T > 0`; implied volatility is undefined at expiry.
- `build_surface` fills failed IV solves with `NaN`.
- Quote midpoint IV surfaces are built from usable bid/ask mid prices; Exchange mark IV (`mark_iv`) is the default IV source.
- The ATM term-structure proxy accepts only the nearest finite IV within 2% of
  spot; equally near listed strikes are averaged.
- Interpolation requires at least two strictly increasing expiries and strikes.
- Interpolation is in-grid only; no extrapolation.
- The surface is a raw interpolated grid, not an arbitrage-free fitted surface.

## Tests

```bash
pytest
```

Tests run offline on the frozen Deribit snapshot in `data/`.
