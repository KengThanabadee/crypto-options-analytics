# 01: Remove the unused IV pipeline

**What to build:** The superseded IV path is gone: the price-grid surface builder, the IV interpolation helper, the 1D smile interpolator, the chain-to-surface wrappers with their input preparation and helpers, and the surface builder module once empty. Black-Scholes pricing and the IV solver stay; the Call/Put combine step moves into the IV source module. Deribit parsing checks that went through the old wrapper are rewritten through the IV source build. README entries for removed functions go.

See `../spec.md` (Removal of the unused IV pipeline).

**Blocked by:** None within this spec; the whole spec starts after `dashboard-layout` is done.

**Status:** ready-for-agent

- [ ] No removed function remains in code, tests or README.
- [ ] Deribit parsing assertions survive, now through the IV source build.
- [ ] Dashboard numbers and charts are unchanged; lint and tests pass.
