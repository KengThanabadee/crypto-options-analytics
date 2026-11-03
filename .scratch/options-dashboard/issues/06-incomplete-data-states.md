# 06: Incomplete and Insufficient data in GEX

**What to build:** A strike whose GEX cannot be fully computed never looks like a complete bar or a zero. Partly computable strikes show an Incomplete data marker; strikes with nothing computable show Insufficient data with the reason. OI still shows for those strikes.

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] Each strike is assessed over all Call/Put contracts in the selected expiries: all computable gives a normal bar (a true zero included), some gives Incomplete data, none gives Insufficient data.
- [ ] Incomplete details show the labelled partial subtotal in the current Net/Gross mode, usable/total contract counts, the computable OI share when the OI base is complete, and the reason.
- [ ] Known zero OI contributes zero even without IV; missing OI is not zero; midpoint or interpolated IV is never filled in.
- [ ] Removing one contract's input gives Incomplete data and removing all gives Insufficient data, neither shown as a zero bar (spec check 7).
- [ ] Analysis-set coverage is labelled with its scope (every strike in the selected expiries).
