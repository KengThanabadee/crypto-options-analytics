# 01: Remove Bybit

**What to build:** The dashboard opens straight onto the frozen Deribit snapshot. Bybit leaves the app, the package, the frozen data, the tests, the live diagnostic script and the docs, so the project is Deribit only. Until ticket 08, Quote midpoint IV is solved at a zero rate, so the sidebar has no rate input.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] The dashboard has no Data source selector and no rate input; it shows the existing IV charts from the Deribit snapshot.
- [x] The Deribit adapter keeps working after the shared parsing helpers (time to expiry, number parsing, mid price, UTC timestamps) move out of the Bybit module.
- [x] Bybit fetching, the Bybit snapshot, its tests and the Bybit live diagnostic are gone.
- [x] README and AGENTS.md describe a Deribit-only project; the spot rule names only the Deribit captured BTC/USD index.
- [x] Experiment results stay as research records; experiment scripts that need Bybit code or data are removed, and each kept result notes that its script ran on the commit before this one.
- [x] The full test suite passes offline.

## Comments

- 2026-11-03: Resolved on the `options-dashboard` integration branch at bd28546; code-review fixes landed at 0365271.
