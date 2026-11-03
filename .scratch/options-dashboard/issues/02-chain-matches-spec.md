# 02: Deribit chain follows the spec conventions

**What to build:** The Deribit chain the dashboard reads uses a 365-day year, carries each contract's open interest and reported forward, and leaves out contracts that have settled. The project contract says Exchange mark is the default IV source and the gamma input, and Quote midpoint is the comparison source.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Time to expiry uses a 365-day year everywhere, including the maturity axes (spec check 5).
- [ ] Each contract carries open interest in BTC and its reported forward; missing OI stays missing, never zero.
- [ ] Contracts with time to expiry at or below zero at the capture end time are left out; every contract still before expiry is kept.
- [ ] The book summary's `estimated_delivery_price` is kept as raw data only; the index from the index request stays the one spot for conversions and moneyness.
- [ ] AGENTS.md and README state the IV source contract above.
- [ ] Existing IV charts still render from the snapshot.
