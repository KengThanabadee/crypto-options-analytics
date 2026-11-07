# 01: One IV surface for every range, with a fixed strike–time scale

**What to build:** The IV surface is filled once per snapshot and IV source from every observed IV, and the chosen moneyness range shows a slice of it, so a cell has the same value in every range. Distance in the fill uses a fixed strike–time scale of 1 year of `tau` = 8 K/S units instead of the per-range min/max rescaling. The Surface interpolation expander and the fill section of the dashboard guide describe the one-surface fill and the scale with its reason. The coverage script counts cells with the same build-then-slice fill. The calculation version rises to 4. Ranges stay Core and Extended in this ticket. See `../spec.md` (Implementation Decisions: one surface, fill method, strike–time scale).

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] The fill takes the whole chart frame and no range bounds; a separate slicing step keeps cells inside inclusive bounds.
- [ ] A cell has the same value in Core and Extended (surface test and page test).
- [ ] A gap at a range edge is filled from an observation outside that range.
- [ ] With two expiries close in `tau`, a gap between two strikes of one expiry takes its value from that expiry.
- [ ] Existing cases still hold: exact on a plane, observed values unchanged, blank outside the hull, existing errors on invalid input.
- [ ] The scale is a named module constant with a docstring or comment giving its meaning.
- [ ] Reopening a calculation version 3 file shows the recompute notice.
- [ ] `scripts/snapshot_coverage.py` reports Exchange mark blanks of 6 of 504 cells in Core on the frozen snapshot (spec table), or the change is explained.
- [ ] Lint and tests pass; the dashboard has been opened and the IV surface tab checked in both views, dark and light.
