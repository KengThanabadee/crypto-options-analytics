# 03: Rename the package and distribution

**What to build:** The distribution is `crypto-options-analytics` with a description naming a Deribit options dashboard with OI, GEX and IV, and the package is `options_analytics`. Every import, patch target, script, experiment, README and AGENTS.md reference follows. The saved-file format id, versions, saved file name, page title and dashboard UI package name stay.

See `../spec.md` (Package and distribution).

**Blocked by:** 01, 02

**Status:** resolved

- [x] No reference to the old package or distribution name remains outside git history and finished plans.
- [x] Saved files from before the rename still open.
- [x] Lint and tests pass; the dashboard opens and shows the same numbers.

## Comments

- 2026-11-04: Resolved on the `crypto-options-analytics` integration branch; code-review fixes landed at 9452a3d.
