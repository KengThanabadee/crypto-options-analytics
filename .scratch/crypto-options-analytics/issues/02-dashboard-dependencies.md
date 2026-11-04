# 02: Streamlit and Plotly as main dependencies

**What to build:** A plain editable install brings everything the dashboard needs. Streamlit and Plotly move into the main dependencies, the `dashboard` extra goes, and the dev extra keeps test and lint tools. CI installs with a plain editable install plus dev tools. AGENTS.md drops the optional-extras rule and keeps the rule that calculations and figures import nothing from Streamlit. README install steps match.

See `../spec.md` (Package and distribution).

**Blocked by:** None within this spec.

**Status:** resolved

- [x] A fresh environment with a plain editable install runs the dashboard.
- [x] CI uses that install and passes.
- [x] AGENTS.md and README describe the new install.

## Comments

- 2026-11-04: Resolved on the `crypto-options-analytics` integration branch; code-review fixes landed at 9452a3d.
