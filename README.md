# crypto-options-analytics

A Streamlit dashboard for one Deribit BTC options snapshot: open interest and
gamma exposure (GEX) by strike, and implied volatility (IV) as a surface,
smiles and an ATM term structure. It opens offline on a checked-in snapshot,
pulls a fresh one on request, and saves an analysis as one file that reopens
to the same numbers. Every number is computed from the raw Deribit responses.
It is a research tool, not trading infrastructure, and not financial advice.

## Dashboard preview

These images are screenshots of the running dashboard on the checked-in
Deribit BTC snapshot captured on **2026-10-15 at 15:18:14 UTC** (index
$82,227.73), at the page defaults: All expiries, Near spot strike range,
Call+ / Put−, Net, Exchange mark IV and the Core moneyness range, in the dark
colour scheme. `scripts/capture_readme_images.py` retakes them from a
dashboard started on that snapshot.

### Open interest and gamma exposure

![Open interest by strike in BTC with Call and Put bars, above Net gamma exposure by strike in USD per 1% BTC move under the Call+ / Put− scenario, in one chart with a shared strike axis and a dashed index line.](docs/images/oi-gex.jpg)

### IV surface: Heatmap

![Implied volatility section with the IV source selector on Exchange mark, the IV surface, IV smiles and ATM term structure tabs, and the IV surface tab's View, Moneyness range and Heatmap values controls above the Combined IV heatmap across moneyness and UTC expiry.](docs/images/heatmap.jpg)

### IV surface: 3D

![IV surface tab with View on 3D: the 3D Combined IV surface with observed values overlaid as orange points.](docs/images/surface.jpg)

### IV smiles

![Observed IV smile curves with bid–ask display bands for the first three usable Deribit expiries.](docs/images/iv-smiles.jpg)

### ATM term structure

![ATM IV term structure across UTC expiry dates, spaced by maturity.](docs/images/atm-term-structure.jpg)

## Running it

Install in editable mode from the repository root; this brings Streamlit and
Plotly:

```bash
pip install -e .
python -m streamlit run app.py
```

Streamlit prints a local URL (by default `http://localhost:8501`); open it in a
browser. The page follows the browser's light or dark colour scheme;
Streamlit's ⋮ menu switches it.

The dashboard opens on the checked-in snapshot in `data/` and runs offline.
Under the title **BTC volatility**, one header row reads
`Deribit BTC · Frozen snapshot: <capture time> UTC · Index $<index>`, with
**Fetch latest** on the right.

**Fetch latest** pulls a new snapshot from Deribit's public API and the whole
page switches to it; the header then reads "Fetched snapshot" with its capture
time. Every setting carries over except the OI expiries, strike range and
smile expiries, which belong to the old snapshot and start at the new one's
defaults. A failed fetch keeps the current snapshot and shows the error. Only
that button fetches; every other control reuses the loaded snapshot.

The sidebar has two parts. **Saved analysis** holds Reopen analysis and Save
analysis (see [Save and reopen](#save-and-reopen)). **Method notes** holds two
expanders: **Combined IV coverage** counts the grid cells that are preferred
or averaged, fallback or one-sided, and missing for the selected IV source;
**Deribit pricing** states the USD conversion and the solver's forward rate.

## Reading each section

### Open interest and gamma exposure

The top of the page is one chart with two panels that share a strike axis: a
strike sits at the same x in both, and one zoom covers both. The controls sit
above the chart.

- **OI expiries** starts empty, which means All expiries. It is separate from
  the IV charts' expiries.
- **Strike range (USD)** starts at Near spot, ±10% around the index with both
  ends included, and **Near spot** resets it. Dragging across either panel
  sets the range to the dragged band, widened to whole $500 steps, so the
  zoom stays through every rerun and each panel's value axis fits the visible
  bars. The range is a display zoom only: OI and GEX use every strike in the
  selected expiries. A range with no listed strikes shows "No strikes in this
  range." with a **Zoom out to all strikes** button; the GEX controls keep
  their values.
- **Calls** and **Puts** each set Customer sells or Customer buys (see below).
- **GEX view** switches between **Net** and **Gross**.

**Open interest** (top panel) is in BTC: each Deribit BTC option contract is
one BTC, so the bars are contract counts summed over the selected expiries,
Calls and Puts side by side. A dashed line labelled with the index marks spot.
Hover shows the strike, Call and Put OI and the expiry scope.

**GEX** (bottom panel) is in **USD per 1% BTC move**: roughly how many USD of
BTC a dealer would buy or sell to stay hedged if the index moved 1%, with every
forward moving with it. Each contract adds

```text
s × gamma × OI × X² × 1%
```

where `X` is the index, OI is in BTC and gamma comes from Exchange mark IV. The
gamma is the spot gamma of the contract's USD value per USD of index move, with
the index and every forward moving together: `phi(d1) / (X × sigma × sqrt(T))`,
with `d1` from undiscounted Black-76 on the contract's reported forward and its
own `mark_iv` and `tau`. Deribit's ticker gamma is per USD of the forward;
multiplying ours by `X / F` gives Deribit's. A caption under the chart repeats
the formula and the **How GEX is calculated** expander explains it.

Deribit does not publish who holds each side, so the sign `s` is an
**assumption** you choose per option type, with the dealer as counterparty.
**Customer sells** means the dealer bought the option and is long gamma
(`s = +1`, a positive bar); **Customer buys** means the dealer is short gamma
(`s = −1`, a negative bar). One choice per option type covers every strike and
expiry. A new analysis starts at Call+ / Put− (customers sell calls and buy
puts), and Fetch latest keeps the current choice. Flipping a control
recomputes the signs from the loaded snapshot without fetching.

- **Net** (default) adds the signed contributions, so Calls and Puts at a
  strike can cancel. It depends on the assumption, and the title states it as
  a scenario, not observed dealer inventory.
- **Gross** adds the contribution magnitudes, drawn in their own colour. It
  shows how much gamma sits at a strike and does not change with the
  assumption, so its title and hover leave the scenario out; it is always at
  least the size of Net.

The panel title names the source, the unit, the share of OI whose GEX is
computable and how many strikes are complete, both over every strike in the
selected expiries, and the scenario (Net only). Hover shows Net or Gross GEX,
the Call and Put subtotals (magnitudes in Gross), Call and Put OI, the
contract count, the scenario (Net only) and the expiry scope.

A strike is drawn as a bar only when every contract in it is computable. A
contract with known zero OI adds zero even without IV; missing OI or mark IV
makes it non-computable, and no midpoint or interpolated IV fills in. When
only some contracts are computable, the strike shows an **Incomplete data**
marker with the partial subtotal in the selected view, the usable/total
contract count, the computable OI share (when all OI is known) and what is
missing (for example `1 Put: no mark IV`); when none are, it shows
**Insufficient data** and the reason. Markers sit in a strip near the top of
the panel, away from zero, and neither is drawn as a zero bar.

### IV source

The **IV source** selector at the top of **Implied volatility** switches every
IV chart between two sources:

- **Exchange mark** is the `mark_iv` Deribit reports. It is the default IV
  source and the gamma input.
- **Quote midpoint** is this repository's solver IV from usable bid/ask
  midpoints. It is the comparison source.

The selector changes only the IV charts, never OI or GEX, and reuses the
loaded snapshot. Both sources follow the same Combined IV and ATM proxy rules;
a contract whose selected-source IV is unusable is missing, never filled from
the other source. Hover names the IV source beside each IV value.

Quote midpoint IV uses Deribit's inverse-option convention: the index `X` is
spot and each contract's reported forward `F` sets `R = ln(F / X) / T`, so no
rate is chosen and the result need not equal Exchange mark IV. A solved IV must
reprice the USD midpoint within $0.01, or it counts as missing.

**Combined IV** puts Calls and Puts on one expiry × strike grid. Selection is
spot-based:

- below `K / S = 0.98`, prefer Put IV;
- from `0.98` through `1.02`, average the same-strike Call and Put IV when
  both are available;
- above `K / S = 1.02`, prefer Call IV.

If the preferred side is unavailable, the other side is used and labelled as a
fallback (or one-sided near ATM); if neither side has IV, the cell stays
missing. Tooltips say which side a value came from in plain words, for example
"Average of Call and Put" or "Call (no Put IV)".

Below the selector, three tabs hold the IV charts: **IV surface**, **IV
smiles** and **ATM term structure**. All IV tooltips show the expiry date in
UTC, time to expiry in days (`tau × 365`) at the snapshot time and the strike
in USD with thousands separators.

### IV surface

Three controls sit in a row above the chart:

- **View**: **Heatmap** (default) or **3D**.
- **Moneyness range**: **Core (0.8–1.2)** (default) or **Extended (0.7–1.3)**
  in `K / S`, for both views.
- **Heatmap values**: **Surface** (default) or **Observed**, shown only in the
  Heatmap view; it keeps its value while 3D is shown.

The Heatmap colours IV across spot moneyness (`K / S`) and expiry, with
expiry rows of equal height ordered by maturity. In Surface mode observed
values are preserved, supported gaps are filled by 2D total-variance
interpolation, and unsupported cells stay blank; Observed mode shows solved IV
only. The 3D view shows the same interpolated values with numerical time to
expiry spacing the maturities, and orange points mark the original observed
Combined IV (lifted slightly above the mesh for visibility; hover reports
their original IV). It switches to a compact layout when its width is below
700px.

A caption above the chart counts the observed, interpolated and blank cells in
the visible range; a one-line caption under it names the fill, and the
**Surface interpolation** expander explains it. Hover distinguishes Observed,
Interpolated and Missing cells, with `2D linear total variance` as the
interpolated value source.

The interpolation converts observed IV to total variance `w = IV² × tau`,
interpolates it piecewise-linearly across spot moneyness and numerical `tau`,
then converts back with `IV = sqrt(w / tau)`. Both axes are scaled to their
observed min/max before triangulation. Support uses only original finite
observations inside the selected range; observed values stay unchanged, cells
outside their convex hull stay missing, and fewer than three non-collinear
observations leave every gap unfilled. It fills the existing grid rather than
adding display points. The surface is a display, not an arbitrage-free fit.

### IV smiles

The smiles show observed Combined IV across all strikes for the chosen
expiries, keeping missing-value gaps and never using the surface
interpolation. **Select expiries** opens an expiry checklist, independent of
the OI expiries, that starts at the first three expiries with any IV.

The shaded area is a **bid–ask IV display band**, in both IV source modes: our
solver inverts bid and ask separately with the same forward rate, and the band
blends them with the line's Call/Put weights (bid with bid and ask with ask in
the `0.98–1.02` zone). It is drawn only where both edges exist, so it is wide
where quotes are wide. It is a display band, not a tradable quote, and mark IV
may sit outside it. The caption and the **Smile shading** expander sit under
the chart.

### ATM term structure

The ATM term structure shows near-ATM IV across every expiry. Each expiry uses
the nearest finite Combined IV within 2% of spot, averaging equally near
strikes; expiries without one stay gaps, and a note under the chart counts
them. Numerical maturity (`tau`) spaces the dates. The **ATM selection
details** expander lists every expiry's status.

## Save and reopen

**Save analysis** downloads `deribit-btc-analysis-<capture time>Z.json`: the
raw snapshot, with every API response and its capture times, and the settings.
It stores no computed numbers:

```text
{"format": "btc-options-analysis", "format_version": 1,
 "calculation_version": N, "snapshot": {...}, "settings": {...}}
```

The settings are:

- `oi_expiries` and `smile_expiries`: expiry datetimes saved as UTC
  `YYYY-MM-DDTHH:MM:SSZ`; empty OI expiries means All expiries;
- `strike_range` and `moneyness_range`: `(low, high)`;
- `signs`: `call` and `put` → `+1` (customer sells) or `−1` (customer buys);
- `gex_view` (`Net`/`Gross`), `iv_source`, `heatmap_values`
  (`Surface`/`Observed`) and `surface_view` (`Heatmap`/`3D`).

Saved files accept only the dashboard's own choices. A file without
`surface_view` opens as Heatmap.

**Reopen analysis** loads such a file, validates the snapshot and every
setting against it, restores every setting and recomputes every number from
the raw snapshot; the header then reads "Reopened snapshot". A file saved with
a different calculation version opens with a short recompute notice. An
invalid file shows an error and keeps the current analysis. The calculation
version goes up whenever a change alters a number computed from the same
snapshot and settings.

## Why the numbers can be checked

- **Raw input is kept.** `data/deribit_btc_options_snapshot.json` preserves
  the unchanged responses from
  [`public/get_instruments`](https://docs.deribit.com/api-reference/market-data/public-get_instruments),
  [`public/get_book_summary_by_currency`](https://docs.deribit.com/api-reference/market-data/public-get_book_summary_by_currency)
  and [`public/get_index_price`](https://docs.deribit.com/api-reference/market-data/public-get_index_price).
  Fetched snapshots and saved analyses use the same envelope, so any number
  can be recomputed from what Deribit sent.
- **Every step is visible.** USD conversion, time to expiry, IV solving
  (Newton-Raphson with bisection fallback), Combined IV, Black-76 gamma, GEX
  and the 2D surface fill (linear interpolation on total variance) are
  computed from the snapshot. Only Exchange mark IV is taken from Deribit as
  reported.
- **Missing stays missing.** Absent quotes, failed solves and unknown OI stay
  `NaN`, never zero or a substitute value; charts leave gaps
  (`connectgaps=False`) and label interpolated cells.
- **Solves are repriced.** A Quote midpoint IV counts only when it reprices
  the USD midpoint within $0.01.
- **Gamma is checked against Deribit.** `tests/test_gex.py` compares our gamma
  with a one-time capture of Deribit's ticker gamma in
  `data/deribit_btc_gamma_check_*.json`
  (`experiments/capture_deribit_ticker_gamma.py`).
- **Coverage is measurable.** `scripts/snapshot_coverage.py` prints, by
  `K / S` bucket and by expiry, how many contracts are listed, quoted and
  solved, and how many surface cells are observed, interpolated or blank.

### Deribit input

The snapshot envelope (version 1) records `exchange: deribit`, `currency: BTC`,
`base_url`, the UTC capture start and end, and a `requests` list with each
endpoint, its parameters, its UTC receive time and the unchanged JSON-RPC
response. The requests are sequential, so the envelope records a capture
interval rather than an atomic exchange snapshot. A fetch makes the three
requests in order with a 15 s timeout each; the capture starts just before the
first request and ends at the last response. Recurring historical collection
belongs to a separate collector project.

The parser accepts BTC inverse options with one-BTC contract size. Instrument
metadata supplies strike, option type and expiration timestamp. Instruments
with missing books are kept as missing quotes; ambiguous identities and
unsupported currencies are rejected.

[BTC inverse-option premiums are quoted in BTC](https://support.deribit.com/hc/en-us/articles/31424939096093-Inverse-Options).
Bid and ask premiums are multiplied by the captured BTC/USD index to give USD
per BTC; the BTC values stay as `bid_price_btc`, `ask_price_btc`,
`mid_price_btc` and `mark_price_btc`. That same index, from
`get_index_price`, is the one spot for USD conversion and moneyness; the book
summary's `estimated_delivery_price` is kept as raw data only.

A valid mid requires a positive, finite, uncrossed bid and ask; otherwise
`mid_price` is `NaN` and `quote_source` is `"none"`, and neither the mark
price nor the exchange's own mid fills it. `mark_iv` is converted from percent
to decimal. Each contract also carries `open_interest` in BTC and its reported
forward `underlying_price`; a missing value stays `NaN`, never zero.

Source expiry timestamps and the capture end set `tau` on a 365-day year,
matching Deribit. Contracts whose `tau` is zero or below at the capture end
have settled and are left out; every contract still before expiry is kept,
however close.

## How the code is organised

The calculations and figures live in the `options_analytics` package and
import nothing from Streamlit; the page lives in `app.py` and `dashboard/`.
Signatures and arguments are documented in docstrings.

- `options_analytics.deribit`: fetches, loads and validates Deribit snapshots
  and parses them into the option-chain DataFrame.
- `options_analytics.chain`: shared parsing helpers: time to expiry, number
  parsing, bid/ask mid and UTC timestamps.
- `options_analytics.solver`: Black-Scholes pricing and the IV root finder.
- `options_analytics.iv_source`: per-contract IV for each IV source, the
  Combined IV rule and the bid–ask band.
- `options_analytics.surface_transforms`: the chart frame, the 2D surface
  interpolation, the ATM proxy and the dashboard's surface choices.
- `options_analytics.positioning`: OI and GEX by strike, gamma, strike
  coverage and the Near spot range.
- `options_analytics.saved_analysis`: the saved file format, its validation
  and the calculation version.
- `options_analytics.visualization`: Plotly figures built from prepared
  frames.
- `dashboard/`: the page sections (snapshot controls, OI and GEX, the IV
  section and its three tabs) and the settings they save.

IV grids are expiry rows by strike columns:
`iv_surface[i, j]` is the IV at `expiries[i]` and `strikes[j]`.

## Assumptions and limitations

- Black-Scholes European option assumptions, with no dividend yield.
- Time to expiry uses a 365-day year; IV is undefined at expiry (`T > 0`).
- The GEX sign is a chosen customer/dealer assumption, not observed dealer
  inventory.
- The ATM proxy accepts only the nearest finite IV within 2% of spot; equally
  near listed strikes are averaged.
- Interpolation fills inside the observed range only; there is no
  extrapolation.
- The surface is an interpolated display grid, not an arbitrage-free fitted
  surface.
- Bitcoin only, from Deribit only.

## Tests

```bash
pip install -e ".[dev]"
python -m pytest
```

Tests run offline on the frozen Deribit snapshot in `data/`, in parallel.
