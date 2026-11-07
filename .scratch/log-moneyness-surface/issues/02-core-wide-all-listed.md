# 02: Moneyness ranges Core, Wide and All listed

**What to build:** The Moneyness range control offers Core (0.8–1.2), Wide (0.5–2.0) and All listed, with Wide selected by default; Extended is gone. All listed resolves to the lowest and highest K/S of the open snapshot's grid, and the visible-range caption prints the resolved bounds to two decimals. A saved analysis stores the range by name, so All listed reopens against its own snapshot; the saved-file format version rises to 2 and format 1 files are rejected with the existing unsupported-format error. The coverage script's `--range` accepts the three names besides numeric bounds. The dashboard guide describes the three ranges. See `../spec.md` (Moneyness ranges, Saved analyses, Coverage script) and `GLOSSARY.md` (Moneyness range).

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] The control's options are exactly Core, Wide and All listed, with Wide selected on a fresh page.
- [ ] All listed's caption shows the frozen snapshot's listed bounds (about 0.24–3.04).
- [ ] Switching between ranges keeps a cell's value.
- [ ] Save then Reopen restores each range by name; an unknown name is rejected; a format 1 file is rejected.
- [ ] `snapshot_coverage.py --range Wide` and `--range "All listed"` work; numeric bounds still work.
- [ ] Lint and tests pass; the dashboard has been opened and all three ranges checked in both views, dark and light.
