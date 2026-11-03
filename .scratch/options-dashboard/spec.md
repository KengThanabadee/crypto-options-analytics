# Options Dashboard: OI, GEX and IV from one Deribit snapshot

**Status:** ready-for-agent

Accepted 2026-11-03. Tickets go in `issues/` beside this file.

## Problem Statement

Keng explores the Deribit BTC options market with the existing IV charts (heatmap/3D surface, smile, ATM term structure), which run on frozen fixtures. They cannot see where open interest sits, which price levels are most sensitive to dealer hedging, or how either relates to the volatility surface, and they cannot pull a fresh snapshot or keep an analysis to reopen later. The project should finish as a dashboard that can be demonstrated and put on a résumé, with numbers that can be checked.

## Solution

One page built on one Deribit BTC snapshot. **Fetch latest** pulls a new snapshot and shows its capture time. The top section is a pair of bar charts by strike, **Open Interest** and **Gamma Exposure**, sharing the strike axis, a current-price line, one expiry selection and one zoom. Below them sit the existing IV charts, which gain an **IV source** selector (Exchange mark / Quote midpoint). Signed GEX rests on a stated customer/dealer assumption the user can flip per option type. An analysis can be saved to a file and reopened, and reopening recomputes every number from the raw snapshot.

## User Stories

1. As a market explorer, I want to press Fetch latest, so that I analyse the market as it is now.
2. As a market explorer, I want to see the snapshot's capture time, so that I know how fresh the numbers are.
3. As a market explorer, I want a failed fetch to keep the previous snapshot and show the error, so that I never lose the analysis I was looking at.
4. As a market explorer, I want changing views, expiries, zoom or assumptions to reuse the current snapshot, so that the page stays fast and the numbers stay consistent.
5. As a market explorer, I want OI and GEX at the top of the page and IV below, so that I read positioning first and then volatility pricing.
6. As a market explorer, I want OI bars by strike split into Call and Put, in BTC, so that I see which price levels hold the most open positions.
7. As a market explorer, I want GEX bars on the same strike axis as OI, so that I can read positioning and hedging sensitivity side by side.
8. As a market explorer, I want a current-price line on both charts, so that I see how far concentrations sit from the price.
9. As a market explorer, I want the OI/GEX pair to start at All expiries, so that I first see the whole market.
10. As a market explorer, I want to select one or several expiries for the OI/GEX pair, so that I can focus on the maturities I care about.
11. As a market explorer, I want the pair to show whether it is on All expiries or which dates, so that I always know the scope.
12. As a market explorer, I want the OI/GEX expiry selection to leave the IV charts' expiries alone, so that each section keeps its own controls.
13. As a market explorer, I want the pair to start zoomed to ±10% around the BTC index, so that levels near the price are readable.
14. As a market explorer, I want to adjust the strike range and reset it to the Near spot default, so that I can look at distant strikes and come back.
15. As a market explorer, I want both charts to zoom together, so that the strikes stay aligned.
16. As a market explorer, I want a "no strikes in this range" state that lets me zoom out, so that an empty chart is never a mystery.
17. As a market explorer, I want a Call and a Put customer-side control (customer buys / customer sells), so that I can test how the hedging picture changes with the assumption.
18. As a market explorer, I want a new analysis to start at Call+ / Put−, so that signed GEX shows immediately under a common assumption.
19. As a market explorer, I want the active assumption always shown with the chart, so that I never mistake a scenario for observed dealer inventory.
20. As a market explorer, I want a Net / Gross toggle starting at Net, so that I can see both the signed total and how much exposure cancels.
21. As a market explorer, I want GEX in USD per 1% BTC move, shown with the computable OI share, so that the unit is clear and comparable.
22. As a market explorer, I want a strike with only some computable contributions to show an Incomplete data marker with the partial subtotal and coverage in the details, so that a partial sum never looks like a complete one.
23. As a market explorer, I want a strike with no computable contribution to show Insufficient data with the reason, so that I can tell missing data from a real zero.
24. As a market explorer, I want OI to show even when GEX cannot be computed, so that I keep the positioning information.
25. As a market explorer, I want the IV charts to start at Exchange mark IV and switch to Quote midpoint IV, so that I can compare the exchange's IV with our own solver's.
26. As a market explorer, I want the smile to keep the bid–ask IV band in both modes, so that I can judge quote quality.
27. As a market explorer, I want a contract whose selected-source IV is unusable to show as missing, so that the chart never silently mixes sources.
28. As a market explorer, I want hovering any chart to show the value, its unit and the point's details, so that I can inspect exact numbers.
29. As a market explorer, I want to save the snapshot with all my settings to one file, so that I can return to the same analysis later.
30. As a market explorer, I want reopening a file to restore every setting and recompute the numbers, so that I see the same analysis with the current code.
31. As a market explorer, I want a short notice when a reopened file was saved with an older calculation version, so that I know the numbers were recomputed.
32. As a reviewer of the project, I want the README to show images from the real app and explain the units and assumptions, so that I can understand the dashboard without running it.

## Implementation Decisions

### Snapshot and index

- One snapshot holds contract data, bid–ask prices, exchange mark IV, OI, each contract's reported forward and the index. It is a capture window over several API requests, not an atomic whole-market instant.
- The index `X` is the `index_price` from the snapshot's `get_index_price` request. It is the one index for `R`, USD premium conversion, moneyness, the current-price line and `X²` in GEX. The book summary's `estimated_delivery_price` (82,256.17 versus 82,227.73 in the 2026-10-15 snapshot) is stored as raw data only.
- Every contract with time to expiry `T > 0` at the capture end time is included, however close to expiry, because dealers keep hedging it until then. Contracts with `T ≤ 0` have settled and are left out.
- Fetching uses Deribit's public API directly; the Data Collector owns recurring historical capture and is not needed for this release.

### Conventions

- Deribit uses each contract's reported forward `F` and computes `R = ln(F/X) / T`, so the user does not choose a rate. Coin premiums convert to USD with `X`. Moneyness stays spot-based `K / S`.
- The whole app uses a 365-day year, matching Deribit: the IV charts, GEX and the existing Bybit charts, which move from 365.25. Beyond that day count, Bybit is unchanged.
- Contract identity stays separate by Call/Put, expiry and strike. IV source, the inverted price (mid or mark) and the input basis (index, reported underlying, assumed forward) stay separate fields.

### IV source

- **Exchange mark** is the `mark_iv` Deribit reports. **Quote midpoint** is our solver's IV from the bid–ask midpoint.
- The IV charts start at Exchange mark and can switch to Quote midpoint. The selector changes only the IV charts, never GEX, and does not fetch.
- Both sources go through the README's Combined IV and ATM proxy rules: Put IV below `K / S = 0.98`, Call IV above `1.02`, the average of the two in between. The smile shows Combined IV only.
- The smile's bid–ask IV band comes from our solver on bid and ask separately, in both modes. In the 0.98–1.02 zone it blends bid with bid and ask with ask, using the line's weights; it is a display band, not a tradable quote, and mark IV may sit outside it. Midpoint IV is not overlaid as dots.
- Quote data and exchange mark IV are stored separately with source, time and units. The 2026-10-15 snapshot has `mark_iv` for 936/936 contracts, and mark lies inside bid–ask for 885 of the 900 two-sided contracts.
- The first ticket updates the project contract in AGENTS.md and the README: Exchange mark is the default IV source and the gamma input, and Quote midpoint is the comparison source.

### Gamma and GEX

- GEX always uses Exchange mark IV, so all OI converts to GEX. The GEX chart label says so.
- Gamma is the spot gamma of the contract's USD value when BTC moves 1%, with the index and every forward moving 1% together. Gamma is computed per contract from that contract's own maturity and `mark_iv`, never from Combined or display-interpolated IV.
- Contribution = `s × gamma × OI × X² × 0.01`, with `s = −1` when the customer buys and `s = +1` when the customer sells. Unit: USD change in delta value per 1% BTC move, per the model. Verify units and numeraire against the gamma test before building the charts.
- Two controls, Call and Put, each set customer buys or customer sells, assuming the dealer is the counterparty: customer buys → dealer short → negative gamma; customer sells → dealer long → positive gamma. A new analysis starts at Call+ / Put− (Calls customer sells, Puts customer buys). One choice per option type applies to every strike and expiry in the analysed set; it is a scenario placing all OI on that side, with no per-strike or percentage controls.
- Flipping a control recomputes only the signs from the same snapshot. OI, prices, IV and gamma magnitudes stay the same.
- **Net** sums signed contributions by strike, so Calls and Puts can cancel. **Gross** is `sum(abs(contribution))`, unaffected by the assumption, with the same contracts, units and computability rule as Net. Net is the default.
- The system does not infer dealer positioning from the surface or OI.

### Expiries and strike range for OI/GEX

- Default All expiries (every unexpired expiry in the snapshot), selectable as one or several, shared by OI and GEX. OI sums by strike separately for Call and Put; GEX sums contract contributions by strike.
- Default strike range: ±10% around `X`, inclusive at the boundary, adjustable, with reset. Claude proposed the number and Keng did not specify it; it is not claimed to equal Fuelmaps' Near formula.
- The strike range is a display zoom. The full snapshot is kept and the calculation base does not change. Analysis-set coverage refers to every strike in the selected expiries, labelled with that scope; each bar's status refers to its own strike.

### Incomplete data

Each strike is assessed from all Call/Put contracts in the selected expiries:

| Data for the GEX sum | Main display |
| --- | --- |
| Every contribution computable | Normal Net/Gross bar, including a true zero |
| Some computable | **Incomplete data** marker instead of the bar |
| None computable | **Insufficient data** state with the reason |

- An incomplete strike's details show the labelled partial subtotal in the selected Net/Gross mode, usable/total contract counts, the computable OI share when the OI base is complete, and the reason.
- Known zero OI gives a zero contribution even without IV. Missing OI is not zero. Midpoint or interpolated IV is never filled in.

### Save and reopen

- A saved analysis is one file holding the raw snapshot (every API response with its capture times) and the analysis settings: OI/GEX expiry selection, strike range, Call/Put assumptions, Net/Gross mode, IV source and the existing IV chart controls.
- The file records one calculation version and no computed numbers. Reopening recomputes everything from the raw snapshot; a short notice appears when the saved version differs from the current one.

## Testing Decisions

- Tests check external behaviour at the highest seam: the pure functions that turn a snapshot plus settings into OI, GEX and IV tables, which run without Streamlit per AGENTS.md. Save/reopen and fetch failure are tested at the snapshot-loading seam.
- Tests run offline on frozen snapshots in `data/`, following the existing Deribit and surface-builder tests.
- Checks:
  1. **Gamma matches Deribit.** Our gamma from `mark_iv` matches Deribit's ticker gamma for a sample of contracts within a per-contract relative tolerance, after confirming and converting Deribit's basis (probably the forward). The ticker data is a new one-time capture stored as test data, since the dashboard fetch does not call the ticker endpoint.
  2. **One contract by hand.** A real contract's GEX contribution, computed step by step in the test, equals the app's value.
  3. **Bars add up.** Each strike's bar equals the sum of its contracts; Gross is at least the magnitude of Net; flipping an assumption changes only signs and leaves Gross unchanged.
  4. **Midpoint IV prices back.** Repricing with Quote midpoint IV returns the midpoint within $0.01 per contract; unsolved midpoints count as missing.
  5. **One day count.** Time to expiry uses 365 days for Deribit and Bybit.
  6. **Near spot boundary.** A strike exactly at ±10% of the index is included.
  7. **Incomplete data states.** Removing one contract's input gives Incomplete data; removing all gives Insufficient data; neither shows as a zero bar.
  8. **Save and reopen round trip.** Reopening restores every setting and reproduces the same numbers.
  9. **Failed fetch.** A simulated failure keeps the previous snapshot and shows the error.

## Out of Scope

- Bybit beyond the 365-day year.
- Historical comparison, a volume dashboard, an option-chain table, order-book depth and a broad terminal.
- Expiry summary or comparison, a skew metric, IV-implied range, candles, liquidation, flow and spot book.
- A Call/Put split IV view: set aside on 2026-11-03, since the Combined rule already uses the out-of-the-money side and the band shows quote quality.
- Per-strike or percentage dealer-share controls.
- BSAD versus ML/GARCH modelling.

Done when Fetch → explore the three sections → save → reopen works end to end, the checks above pass, charts carry units and explanations, and the README has images from the real app.

## Further Notes

- [Convention research](../../docs/options-dashboard-conventions.md): sources for Near spot, incomplete GEX and the set-aside Call/Put view.
- [Deribit IV convention experiment](../../experiments/deribit_iv_convention.md) and [Bybit mark IV comparison](../../experiments/bybit_mark_iv_comparison.md): research from 2026-10-29, not acceptance of runtime behaviour.
- [Layout sketch](../../docs/design/options-dashboard-layout-sketch.jpg): synthetic data, confirms OI/GEX above IV only.
- Vendor methods and UI (Fuelmaps, GammaFlip, MenthorQ) are inspiration, not validation of our numbers. Fuelmaps, checked 2026-11-02, has a Near/±10% toggle and states OI "within 15% of spot".
- Raw reviews, screenshots and the superseded first plan are kept on Keng's machine in `docs/reference-reviews/` and `docs/history/`.
