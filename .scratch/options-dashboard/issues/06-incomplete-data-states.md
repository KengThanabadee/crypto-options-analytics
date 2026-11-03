# 06: Incomplete and Insufficient data in GEX

**What to build:** A strike whose GEX cannot be fully computed never looks like a complete bar or a zero. Partly computable strikes show an Incomplete data marker; strikes with nothing computable show Insufficient data with the reason. OI still shows for those strikes.

**Blocked by:** 04

**Status:** resolved

- [x] Each strike is assessed over all Call/Put contracts in the selected expiries: all computable gives a normal bar (a true zero included), some gives Incomplete data, none gives Insufficient data.
- [x] Incomplete details show the labelled partial subtotal in the current Net/Gross mode, usable/total contract counts, the computable OI share when the OI base is complete, and the reason.
- [x] Known zero OI contributes zero even without IV; missing OI is not zero; midpoint or interpolated IV is never filled in.
- [x] Removing one contract's input gives Incomplete data and removing all gives Insufficient data, neither shown as a zero bar (spec check 7).
- [x] Analysis-set coverage is labelled with its scope (every strike in the selected expiries).

## Comments

- 2026-11-03: Resolved on the `options-dashboard` integration branch at 70863a7; code-review fixes landed at 0365271.
