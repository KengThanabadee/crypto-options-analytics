# 03: Log moneyness axes on the 3D surface, Heatmap and IV smiles

**What to build:** Every chart with a moneyness axis (3D surface, Heatmap, IV smiles) draws K/S on a log axis titled "K / S (log scale)", with tick values taken from a fixed K/S ladder (for example 0.25, 0.33, 0.5, 0.67, 0.8, 1, 1.25, 1.5, 2, 3) that falls inside the plotted range. Data arrays, hover text and saved values stay in K/S. The Heatmap keeps equal-height expiry rows; the smile axis still fits the selected observations. The AGENTS.md moneyness contract gains one sentence saying charts with a moneyness axis draw K/S on a log axis, and the dashboard guide describes the log axes. See `../spec.md` (Moneyness stays K/S, Charts).

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] The 3D, Heatmap and smile figures have a log moneyness axis titled "K / S (log scale)".
- [ ] Their tick values are K/S ladder values inside the plotted range, and the labels read as K/S.
- [ ] Data arrays still hold K/S; hover still reports K/S to four decimals and the USD strike.
- [ ] K/S 0.5 and 2.0 sit at equal distances from 1 on the axis.
- [ ] Lint and tests pass; the dashboard has been opened and all three charts checked in dark and light.
