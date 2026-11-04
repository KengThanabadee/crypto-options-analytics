# 06: README dashboard section and dark screenshots

**What to build:** The README capture script asks the browser for the dark colour scheme and captures the IV surface tab in both views via the View control. Every README image is retaken from the real app, and the README text about the dashboard (sections, controls, sidebar, saved settings including `surface_view`) matches the new layout. No theme is set in Streamlit config.

See `../spec.md` (Theme and README images).

**Blocked by:** 02, 03, 04, 05

**Status:** resolved

- [x] All README images are dark and show the new layout.
- [x] README describes the three IV tabs, the View control, the header, Method notes and the saved `surface_view` setting.
- [x] Lint and tests pass; every chart was opened and looked at.

## Comments

- 2026-11-04: Resolved on the `dashboard-layout` integration branch; code-review fixes landed at e7a8adc.
