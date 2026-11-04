# 04: One-line captions with expanders under the charts

**What to build:** Under the GEX chart a one-line caption gives the formula and unit, with "How GEX is calculated" in an expander below. Under the IV smile chart a one-line caption says what the line and shading are, with the bid–ask band explanation in an expander. Under the IV surface chart, the surface interpolation explanation sits in a "Surface interpolation" expander and leaves the sidebar. The ATM term structure tab is unchanged.

See `../spec.md` (Captions and notes) for the exact caption wording.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] Each of the three charts has its one-line caption and an expander holding today's full text.
- [ ] The sidebar no longer holds the surface interpolation note.
- [ ] Lint and tests pass; the dashboard has been opened and each expander checked.
