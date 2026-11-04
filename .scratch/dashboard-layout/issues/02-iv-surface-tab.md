# 02: One IV surface tab with a Heatmap | 3D view

**What to build:** The IV section shows three tabs: IV surface, IV smiles, ATM term structure. The IV surface tab has View (Heatmap | 3D, Heatmap first), Moneyness range and, in Heatmap view only, Heatmap values, all as segmented controls beside the chart, with one visible-range caption above it. Only the chosen chart is built; the 3D view keeps its responsive wide/compact pair. The moneyness range leaves the sidebar. Heatmap values keeps its value while hidden in 3D, and the IV view settings including View survive a run where the IV charts cannot be drawn. Save analysis stores `surface_view`; reopening restores it, and a file without it opens on Heatmap with no format or calculation version change.

Prototype reference: variant B on branch `prototype/dashboard-layout` (commit 89cdca2). Do not merge it. See `../spec.md`.

**Blocked by:** 01

**Status:** resolved

- [x] Tab labels are exactly IV surface, IV smiles, ATM term structure.
- [x] View defaults to Heatmap; switching to 3D shows the 3D chart and hides Heatmap values; switching back shows the earlier Heatmap values choice.
- [x] The chart count reflects only the chosen surface view.
- [x] The 3D mesh values equal the heatmap's Surface values for the same range (checked across two runs).
- [x] Save then Reopen restores View; a saved file without `surface_view` opens on Heatmap; an invalid value is rejected.
- [x] The surface view's CSS lives with the surface view, not in the page file.
- [x] Lint and tests pass; the dashboard has been opened and both views checked.

## Comments

- 2026-11-04: Resolved on the `dashboard-layout` integration branch; code-review fixes landed at e7a8adc.
