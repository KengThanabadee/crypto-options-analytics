# 03: Open interest by strike

**What to build:** The top of the dashboard shows an Open Interest bar chart by strike, Call and Put in BTC, with a current-price line at the index. It starts at All expiries and ±10% around the index, and the user can pick one or several expiries, adjust the strike range and reset it to Near spot. The IV charts below keep their own expiry controls.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] OI sums by strike separately for Call and Put over the selected expiries, in BTC.
- [ ] The chart shows its scope: All expiries or the selected dates.
- [ ] The default strike range is ±10% of the index, inclusive at the boundary (spec check 6); the range is a display zoom and never changes the calculation base.
- [ ] Reset returns the range to Near spot.
- [ ] A range with no strikes shows a "no strikes in this range" state that lets the user zoom out.
- [ ] Changing the OI expiry selection leaves the IV charts' expiry selection alone.
- [ ] Hover shows the strike, Call/Put OI with units and the expiry scope.
