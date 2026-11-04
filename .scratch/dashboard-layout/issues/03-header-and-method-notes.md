# 03: One-row header and a Method notes group in the sidebar

**What to build:** The header is one row: `Deribit BTC · <snapshot label>: <capture time> UTC · Index $<index>` on the left and Fetch latest on the right, still updating on the same run after a fetch. The IV section no longer prints its own "Index · IV source" line. The sidebar shows Saved analysis (Reopen, Save) first, then a Method notes heading with "Combined IV coverage · <source>" and "Deribit pricing".

See `../spec.md` (Solution; Implementation Decisions: Page layout, Captions and notes).

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] The header caption includes the index in USD for frozen, fetched and reopened snapshots.
- [ ] Fetch latest sits in the header row; a fetch or a failed fetch behaves as today.
- [ ] No separate index line appears in the IV section.
- [ ] The Method notes heading and its two expanders render below Save analysis in the sidebar, and the coverage expander names the selected IV source.
- [ ] Lint and tests pass; the dashboard has been opened and the header and sidebar checked.
