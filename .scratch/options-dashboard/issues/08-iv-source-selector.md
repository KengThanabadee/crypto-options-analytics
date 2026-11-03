# 08: IV source selector

**What to build:** The IV charts start at Exchange mark IV and can switch to Quote midpoint IV from our solver, so the user can compare the exchange's IV with ours. Quote midpoint uses each contract's reported forward, `R = ln(F/X) / T`, so no rate is chosen. The smile keeps a bid–ask IV band in both modes.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] The selector changes only the IV charts, never GEX, and does not fetch.
- [ ] Both sources go through the Combined IV and ATM proxy rules in the README.
- [ ] A contract whose selected-source IV is unusable shows as missing; sources are never mixed.
- [ ] Repricing with Quote midpoint IV returns the midpoint within $0.01 per contract; unsolved midpoints count as missing (spec check 4).
- [ ] The smile's bid–ask band comes from solving bid and ask separately, blended in the 0.98–1.02 zone with the line's weights, and is labelled a display band.
- [ ] Hover shows the IV source with the value.
