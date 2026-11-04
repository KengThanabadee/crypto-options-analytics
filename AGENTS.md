# Repository Guidance

`README.md` is the current reference for the dashboard's behaviour and data
inputs; signatures live in docstrings. Read it before changing analytics,
inputs or the dashboard.

## Plans

- Resolved specs and finished plans in `.agents/history/` hold past rationale;
  read one only for why a feature works as it does.

## Project Contracts

- Quantitative transforms and figure construction import nothing from
  Streamlit.
- Page sections live in `dashboard/`; `app.py` lays them out. They call
  `options_analytics` functions through their module (`visualization.make_*`,
  `deribit.*`, `iv_source.*`), since dashboard tests patch them there.
- IV root finding stays in `options_analytics/solver.py` (own Newton-Raphson with
  bisection fallback).
- Public argument names: `option_price`, `spot_price`, `iv_surface`. Surfaces
  are expiry rows by strike columns; arguments take `expiries` before
  `strikes`.
- IV sources: Exchange mark (Deribit `mark_iv`) is the default IV source and
  the gamma input. Quote midpoint (our solver's IV from usable bid/ask mids)
  is the comparison source.
- Spot is the index from the snapshot's `get_index_price` request; it drives
  USD conversion and moneyness. `estimated_delivery_price` is raw data only.
- Time to expiry uses a 365-day year (`DAYS_PER_YEAR` in
  `options_analytics/chain.py`). Contracts settled at the capture end are left out.
- Missing quotes and failed solves stay `NaN`; Plotly traces use
  `connectgaps=False`; interpolation is a separate explicit operation.
- Moneyness is spot-based `K / S`. Numerical `tau` drives calculations, expiry
  ordering and maturity axes; expiry datetimes come from source metadata.
- Combined IV and the ATM proxy follow the rules in `README.md`.
- When a change picks a convention, tolerance or default that affects the
  numbers, name it and say why in the summary.
- The project is Deribit only: snapshots go through `options_analytics/deribit.py`,
  with shared parsing helpers in `options_analytics/chain.py`.
- `experiments/` holds research scripts and their results. Runtime behaviour
  is accepted through `tests/`.

## Validation

Run `.venv/bin/python -m ruff check .` and `.venv/bin/python -m pytest`; CI
runs both. Tests run offline on the frozen Deribit snapshot in `data/`, in
parallel; add `-n0` to debug one test.
From a worktree, use the main checkout's interpreter:
`"$(git rev-parse --git-common-dir)/../.venv/bin/python" -m pytest`.
Launch the dashboard with `.venv/bin/python -m streamlit run app.py`.
A change to a chart or the page is done once you have opened the dashboard
and looked at every chart it touches in dark and light;
`scripts/capture_readme_images.py` screenshots them.
Before stating a fact about strike coverage or quote quality, run
`scripts/snapshot_coverage.py`.

## Agent skills

### Issue tracker

Issues are local markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
