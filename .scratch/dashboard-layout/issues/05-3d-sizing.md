# 05: 3D surface fills its frame

**What to build:** The 3D IV surface no longer leaves large empty bands around the mesh. Camera, aspect ratio, height and margins are retuned for the wide layout at the standard 1400 px capture width and for the compact layout; the camera revision string changes so browsers pick up the new camera. Values are chosen by looking at the rendered chart.

See `../spec.md` (3D surface sizing).

**Blocked by:** 02

**Status:** resolved

- [x] Screenshots of the 3D view, wide and compact, show the mesh filling the frame with axes and ticks unclipped.
- [x] The 3D figure test expects the new values and still checks the compact layout is shorter.
- [x] Lint and tests pass.

## Comments

- 2026-11-04: Resolved on the `dashboard-layout` integration branch; code-review fixes landed at e7a8adc.
