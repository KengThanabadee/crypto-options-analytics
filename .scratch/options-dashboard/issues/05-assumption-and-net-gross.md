# 05: Customer-side assumption and Net / Gross

**What to build:** The user sets Call and Put each to customer buys or customer sells, and toggles Net / Gross. Flipping an assumption changes only the signs of GEX; the active assumption is always shown with the chart.

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] A new analysis starts at Call+ / Put− and Net.
- [ ] Customer buys gives the dealer negative gamma (`s = −1`); customer sells gives positive gamma (`s = +1`); one choice per option type applies to every strike and expiry in the analysed set.
- [ ] Gross is `sum(abs(contribution))` over the same contracts, units and computability rule as Net, and is at least the magnitude of Net per strike.
- [ ] Flipping an assumption leaves OI, prices, IV, gamma magnitudes and Gross unchanged and does not fetch (spec check 3).
- [ ] The chart states the active assumption as a scenario, not observed dealer inventory.
