# Log-moneyness axes and one IV surface for every range

**Status:** ready-for-agent

Accepted 2026-11-07 after a grilling session (decisions summarised in
`handoff.md` beside this file). Tickets go in `issues/` beside this file.

## Problem Statement

Keng wants the IV section to show more of the listed strikes and to read like
the volatility surfaces in textbooks and other products. Today it falls short
in three ways.

- The surface only offers **Core (0.8–1.2)** and **Extended (0.7–1.3)**
  moneyness ranges. December 2026 to September 2027 expiries list strikes from
  about K/S 0.25 to 3.0, and those wings are two-sided and solvable, but the
  dashboard never shows them. Extended adds little beyond Core.
- Every moneyness axis is linear in K/S. On a wide range the put wing (0.5–1)
  is squeezed into a third of the width and the call wing (1–2) takes two
  thirds, so the smile looks lopsided. Reference surfaces space strikes by
  log-moneyness, and Keng chose prototype panel C (K/S 0.5–2.0 drawn on
  ln(K/S)) as the look he wants.
- The fill depends on which range is being viewed. Interpolation uses only the
  observations inside the chosen range, and it rescales strike and time to
  that range's min/max before triangulating. The same cell can therefore get a
  different value in Core than in Wide, and Core's strike axis is stretched so
  far that gaps in short expiries borrow from neighbouring expiries. Choosing a
  range should only change the view, never how the data relate.

## Solution

- Every chart with a moneyness axis (3D surface, Heatmap, IV smiles) places
  K/S on a log axis. Tick labels, hover and data stay in K/S. The axis title is
  "K / S (log scale)".
- The **Moneyness range** choices become **Core (0.8–1.2)**, **Wide (0.5–2.0)**
  and **All listed**. Wide is the default. All listed spans every strike listed
  in the open snapshot. Extended is removed.
- The surface is built once per snapshot and IV source: every observed IV in
  the snapshot supports one 2D linear total-variance fill, and each range shows
  a slice of that surface. A cell has the same value in every range.
- The fill measures distance with a fixed **strike–time scale**: 1 year of
  `tau` counts as 8 K/S units, for every range and every snapshot.
- Filled values change, so the calculation version rises to 4. Saved files
  store the range by name.

Effect on the frozen snapshot (index $82,227.73), measured with a scratch
implementation of the new fill and the current `interpolate_surface_2d`:

| Range | Cells | Exchange mark blank: now → new | Quote midpoint blank: now → new |
|---|---|---|---|
| Core | 504 | 36 (7%) → 6 (1%) | 81 (16%) → 67 (13%) |
| Wide | 936 | 183 (20%) → 155 (17%) | 291 (31%) → 257 (27%) |
| All listed (K/S 0.243–3.040) | 1092 | 263 (24%) → 263 (24%) | 369 (34%) → 369 (34%) |

Leave-one-out refill error on Exchange mark (hide each observed IV, fill it
back): Core 0.93 → 0.26, Wide 0.51 → 0.24, All listed 0.30 → 0.25 vol pt.

## User Stories

1. As Keng, I want the 3D surface to space strikes by log-moneyness, so that it reads like the reference surfaces I compare against.
2. As Keng, I want the Heatmap on the same log spacing, so that the two views of the surface line up.
3. As Keng, I want the IV smiles on the same log spacing, so that one strike sits at the same place in every IV tab.
4. As a reader, I want tick labels in K/S (0.5, 0.8, 1, 1.25, 2), so that I read a strike's distance from spot without converting logs.
5. As a reader, I want the axis title to say "K / S (log scale)", so that I know the spacing is logarithmic.
6. As a reader, I want K/S 0.5 and 2.0 to sit at equal distances from 1, so that put and call wings get equal width.
7. As a reader, I want hover to keep showing K/S to four decimals and the USD strike, so that the numbers I read do not change.
8. As Keng, I want a Wide (0.5–2.0) range, so that I see the shape of the smile beyond the near-the-money strikes.
9. As Keng, I want Wide to be the default range, so that the page opens on the view I chose from the prototype.
10. As Keng, I want an All listed range, so that I can see every strike Deribit lists for the snapshot.
11. As Keng, I want All listed to follow the open snapshot's lowest and highest listed strikes, so that a new snapshot with wider listings is never cut off.
12. As Keng, I want Core (0.8–1.2) to stay, so that I can zoom to the strikes every expiry lists.
13. As Keng, I want Extended removed, so that the choices step clearly from narrow to wide.
14. As a reader, I want every expiry shown as a row in every range, so that no expiry disappears when I widen the view.
15. As a reader, I want cells outside an expiry's listed strikes to stay blank, so that the surface never invents values beyond the observations.
16. As Keng, I want a cell to have the same filled value in Core, Wide and All listed, so that changing the view never changes the data.
17. As Keng, I want the fill to use observations just outside the visible range, so that cells at the edge of Core are filled from their real neighbours.
18. As Keng, I want gaps to borrow from neighbouring strikes of the same expiry before other expiries, so that short-expiry gaps follow their own smile.
19. As Keng, I want the strike–time scale fixed at one value for every range and snapshot, so that the fill does not shift when expiries roll off.
20. As a reader, I want observed IV to stay exactly as solved, so that the fill only touches empty cells.
21. As a reader, I want the caption above the chart to count observed, interpolated and blank cells in the visible range, so that I know how much of what I see is filled.
22. As a reader, I want the Surface interpolation expander to explain the one-surface fill and the strike–time scale in plain words, so that I can tell how a filled cell got its value.
23. As a reader, I want the Observed heatmap mode to keep showing solved IV only, so that I can still see the raw data on the log axis.
24. As Keng, I want the range to apply to both the Heatmap and 3D views, as today, so that switching views keeps my zoom.
25. As Keng, I want a saved analysis to remember the range by name, so that All listed reopens as All listed for that file's snapshot.
26. As Keng, I want reopening an analysis saved before this change to show the recompute notice, so that I know filled values may differ.
27. As a résumé reader, I want the dashboard guide and README images to show the new axes and ranges, so that the documentation matches the page.
28. As a maintainer, I want the coverage script to count cells with the same fill as the dashboard, so that its blank counts match the caption.
29. As a maintainer, I want the AGENTS.md moneyness contract to mention the log axis, so that later changes keep it.

## Implementation Decisions

- **Moneyness stays K/S.** The long frame's `moneyness` column, hover, saved
  files and tick labels stay in K/S. Charts set their moneyness axis to a
  logarithmic type with K/S tick values; no column stores ln(K/S). The AGENTS.md
  contract "Moneyness is spot-based `K / S`" gains one sentence: charts with a
  moneyness axis draw K/S on a log axis.
- **One surface per snapshot and IV source.** The surface transform module's 2D
  fill takes the whole chart frame and fills every grid cell once, using every
  finite observed IV as support. Range bounds leave the fill and become a
  separate slicing step that keeps cells inside the inclusive bounds. The
  dashboard builds the surface once and slices it for the chosen range; the
  coverage script uses the same two steps.
- **Fill method is unchanged apart from the distance.** Total variance
  `w = IV² × tau` is interpolated piecewise-linearly on (K/S, `tau`) and
  converted back with `IV = sqrt(w / tau)`. Observed values, provenance columns,
  row order and index are preserved. Cells outside the convex hull of the
  observations stay blank; fewer than three non-collinear observations leave
  every gap blank.
- **Strike–time scale** (anisotropy): triangulation coordinates are
  (K/S, `tau` × 8), a named module constant meaning "1 year of tau = 8 K/S
  units". It replaces the per-range min/max normalisation. Why 8:
  leave-one-out error falls as the scale rises and stops improving from 8
  upward in all three ranges (Core 0.26, Wide 0.24, All listed 0.25 vol pt);
  8 is the smallest value on that plateau. At this scale K/S 0.01 apart counts
  as close as expiries about half a day apart, so gaps borrow from the same
  expiry first. The ruler stays linear in K/S (not ln K/S); both rulers
  refilled equally well (within 0.05 vol pt), and Keng preferred the look.
- **Moneyness ranges.** The surface choices become Core (0.8, 1.2), Wide
  (0.5, 2.0) and All listed. All listed has no fixed bounds: it resolves to the
  lowest and highest K/S of the snapshot's grid when the page is drawn. The
  visible-range caption prints the resolved bounds to two decimals. Wide is the
  widget default. Extended is removed.
- **Charts.** The 3D surface, Heatmap and IV smile figure builders put K/S on
  a log axis titled "K / S (log scale)", with tick values chosen from a fixed
  K/S ladder (for example 0.25, 0.33, 0.5, 0.67, 0.8, 1, 1.25, 1.5, 2, 3) that
  falls inside the plotted range, so ticks read as K/S at every range. The
  Heatmap keeps equal-height expiry rows; its cells keep their K/S centres on
  the log axis. The smile axis still fits the selected observations. Hover text
  is unchanged.
- **Saved analyses.** The `moneyness_range` setting stores the range name
  (`Core`, `Wide`, `All listed`) instead of a numeric pair, so All listed
  reopens against its own snapshot. The saved-file format version rises to 2;
  files from format 1 are rejected with the existing unsupported-format error.
  Nobody holds saved files yet, so there is no migration. The calculation
  version rises to 4 because filled values change.
- **Captions and notes.** The Surface interpolation expander describes one
  surface built from every observation, sliced by range, and the fixed
  strike–time scale; the one-line caption under the chart keeps its wording
  ("blank outside the observed range" stays true).
- **Documentation.** `docs/dashboard-guide.md` describes the log axes, the
  three ranges, the one-surface fill and the strike–time scale with its reason.
  README highlights and the images from `scripts/capture_readme_images.py`
  (heatmap, surface, smiles) are refreshed.
- **Coverage script.** Its surface cell counts use the new build-then-slice
  fill, and `--range` accepts the three range names besides numeric bounds.

## Testing Decisions

A good test checks external behaviour through the highest existing seam:
values of the surface frame, figure properties a reader sees, and the page and
saved files as Keng uses them. Three existing seams cover this spec; no new
seam is added.

- **Surface fill** (the surface transform functions, prior art in the surface
  interpolation tests):
  - a cell has the same value whichever range slices it;
  - a gap at the edge of a range is filled from an observation outside that
    range;
  - with observations in two expiries close in `tau`, a gap between two strikes
    of one expiry takes its value from that expiry (the fixed scale), where
    the old min/max scaling would have borrowed across expiries;
  - linear total variance is exact on a plane, observed values are unchanged,
    cells outside the hull stay blank, and invalid input raises the existing
    errors (the current cases, kept).
- **Figures** (figure builders, prior art in the visualization tests): the 3D,
  Heatmap and smile figures have a log moneyness axis titled
  "K / S (log scale)", K/S tick values inside the plotted range, and hover that
  still reports K/S and strike; data arrays still hold K/S.
- **Page and saved files** (Streamlit `AppTest` page tests and save/reopen
  tests): the range control offers Core, Wide and All listed with Wide
  selected; All listed's caption shows the snapshot's listed bounds; switching
  ranges keeps a cell's value; a saved file stores the range name and reopens
  to the same range and charts; a file with calculation version 3 shows the
  recompute notice; a format 1 file is rejected.
- The whole suite and ruff pass after each ticket. The dashboard is opened and
  every touched chart is checked in dark and light, as AGENTS.md requires.

## Out of Scope

- Fitting a parametric surface (SVI or similar), smoothing, or arbitrage
  checks. The surface stays a display of observed IV with a linear fill.
- Interpolating in ln(K/S), or storing ln(K/S) anywhere.
- Extrapolating beyond the observed convex hull.
- Changing the maturity axis: the 3D view already spaces expiries by `tau`, and
  the Heatmap keeps equal expiry rows.
- The open-interest and GEX strike range, which is a USD window and unrelated
  to the moneyness range.
- Migrating saved files from format 1.
- ETH or another underlying.

## Further Notes

- Prototype: `prototype/wide_surface.py` and `prototype/panel0–3.png` beside
  this file. Panel C (Wide on a log axis, old fill) is the look Keng chose.
- Explainer of the fill on the frozen snapshot, built during grilling (shows
  the old per-range scaling with a squeeze slider):
  https://claude.ai/artifact/Gd7pjGVr8oNbdP2g3vm6Mg
- Listing limits on the frozen snapshot (from `scripts/snapshot_coverage.py`):
  expiries of 1–8 days (except 30 Oct) list only about K/S 0.85–1.2; December
  2026 to September 2027 list about 0.25–3.0. Most blank cells in Wide and
  All listed are short expiries beyond their listed strikes.
- Terms used here are defined in `GLOSSARY.md`: Moneyness, Log-moneyness,
  Moneyness range.
