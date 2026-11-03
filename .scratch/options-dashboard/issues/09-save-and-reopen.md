# 09: Save and reopen an analysis

**What to build:** The user saves the current snapshot with every setting to one file and reopens it later to the same analysis. Reopening recomputes every number from the raw snapshot and shows a short notice when the file was saved with an older calculation version.

**Blocked by:** 05, 06, 07, 08

**Status:** resolved

- [x] The file holds the raw snapshot (every API response with its capture times) and the settings: OI/GEX expiry selection, strike range, Call/Put assumptions, Net/Gross, IV source and the existing IV chart controls.
- [x] The file records one calculation version and no computed numbers.
- [x] Reopening restores every setting and reproduces the same numbers (spec check 8).
- [x] A different saved calculation version shows a short recompute notice.
- [x] An invalid file shows an error and keeps the current analysis.

## Comments

- 2026-11-03: Resolved on the `options-dashboard` integration branch at 5989e43; code-review fixes landed at 0365271.
