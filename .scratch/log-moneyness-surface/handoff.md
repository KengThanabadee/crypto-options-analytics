# Handoff: log-moneyness and a wider IV surface

**Status:** grilled 2026-11-07; the spec is `spec.md` beside this file.

## Decisions (grilling, 2026-11-04 to 11-07)

1. Every chart with a moneyness axis (3D, Heatmap, IV smiles) places K/S on
   a log axis. Data, hover, saved files and tick labels stay K/S; the axis
   title is "K / S (log scale)". AGENTS.md gains a sentence on the log axis.
2. The fill stays 2D linear total variance on K/S, with two changes, both
   from one principle: choosing a range is only a view and never changes
   how the data relate.
   - **One surface, sliced per view.** Triangulate every observed point in
     the snapshot and fill the whole grid once; each moneyness range shows
     a slice of that surface. A cell has the same value in every range.
   - **Strike–time scale** (anisotropy): a fixed 1 year of tau = 8 K/S
     units, replacing the per-range min/max normalization.
   No fitted surface is planned; the surface is for viewing.
   Leave-one-out MAE (Exchange mark): Core 0.93 → 0.26, Wide 0.51 → 0.24,
   All listed 0.30 → 0.25 vol pt; it plateaus from 8 upward. Today's
   per-range rescaling gives an effective rate of about 0.4 in Core and 1.6
   in Wide (strike span ÷ tau span), so a cell's fill depends on the range
   viewed.
3. Moneyness ranges: Core (0.8–1.2), Wide (0.5–2.0, the default) and All
   listed (bounds from the snapshot's listed strikes). Extended is removed.
4. Saved files: no migration for old files (still in development);
   `CALCULATION_VERSION` goes to 4 because filled values change.
5. Re-run `scripts/snapshot_coverage.py` for every range before the spec
   states blank or filled counts.

Terms are in `GLOSSARY.md` (Moneyness, Log-moneyness, Moneyness range).
Explainer of the fill (Core, per-range squeeze version):
https://claude.ai/artifact/Gd7pjGVr8oNbdP2g3vm6Mg

Written 2026-11-04 at the end of the session that finished the
`dashboard-layout` and `crypto-options-analytics` specs (both resolved in
`.scratch/`). Repo, folder and package were just renamed; main is at 1a04b8c.

## What Keng wants

The 3D IV surface (and possibly the whole IV section) should show more of the
listed strikes and read like the surfaces in textbooks and other products.

- Keng showed reference surfaces and asked why ours is not a smooth
  "mountain". He pointed out that references use **plain T** (not √T) on the
  maturity axis and **log-moneyness** on the strike axis.
- From four prototype panels he picked **C: K/S 0.5–2.0 drawn on ln(K/S)**.
  His words, roughly: "I like C; it doesn't look bad at all, even without any
  fitting."
- He then asked whether we can widen it to show everything. Answer given: an
  "All listed" range (≈ K/S 0.2–3.1) is possible as an optional range, but it
  leaves more cells blank (see facts below).
- He confirmed the current 3D orientation (short expiries at the back) is
  right; that is settled.

## Facts already checked (frozen snapshot, index $82,227.73)

Re-run `scripts/snapshot_coverage.py --range LOW HIGH` before restating any of
these, as AGENTS.md asks.

- Far wings are two-sided and solvable; spreads are 3–20%, about 67% only
  beyond K/S 3. The earlier claim that "far wings have few prices" was wrong.
- The real limit is listing: expiries of 1–8 days (except Oct 30) list only
  K/S ≈ 0.85–1.2; Dec 2026 to Sep 2027 list ≈ 0.25–3.0.
- Blank surface cells: Core 0.8–1.2 is 7%, Extended 0.7–1.3 10%, 0.5–2.0 20%,
  full listed range 24%. Blanks are outside the convex hull of observed
  points; the 2D interpolation never extrapolates.

## What it touches (decisions for the grilling)

- AGENTS.md contract: "Moneyness is spot-based `K / S`". Drawing on ln(K/S)
  changes the axis, and maybe the stored moneyness or only its display.
- Scope: 3D only, or heatmap, smiles and the moneyness range control too.
- Range options: replace Core/Extended, add 0.5–2.0, add "All listed".
- Axis ticks: ln(K/S) values, or K/S labels placed on a log scale.
- Interpolation stays 2D linear on total variance in K/S; whether to
  interpolate in ln(K/S) instead changes the numbers (name it if so).
- Saved files store the moneyness range; a new range value needs the saved
  format to accept it.

## Prototype

`prototype/wide_surface.py` (throwaway, imports updated after the rename)
writes an HTML page with panels A (Core), B (0.5–2.0 on K/S) and C (0.5–2.0
on ln(K/S)):

```bash
.venv/bin/python .scratch/log-moneyness-surface/prototype/wide_surface.py /tmp/wide.html
```

`prototype/panel0–3.png` are the images Keng saw: A, B, C and D (full listed
range ≈ 0.2–3.1 on ln(K/S)).
