# Repository Guidance

`README.md` is the current reference for public behaviour, data inputs and the
API. Read it before changing analytics, inputs or the dashboard.

## Plans

- Before work on OI, GEX, the IV source selector, Fetch latest or save/reopen,
  read `.scratch/options-dashboard/spec.md`; its tickets go in `issues/` beside
  it.
- `.agents/history/` holds finished plans; read them only for past rationale.

## Project Contracts

- Quantitative transforms and figure construction work without Streamlit;
  Plotly and Streamlit stay in optional extras.
- IV root finding stays in `iv_surface/solver.py` (own Newton-Raphson with
  bisection fallback).
- Public argument names: `option_price`, `option_price_grid`, `spot_price`,
  `iv_surface`. Surfaces are expiry rows by strike columns; arguments take
  `expiries` before `strikes` and `target_T` before `target_K`.
- Market IV comes from usable bid/ask mids. Spot is the exchange index
  (Bybit `index_price`; Deribit captured BTC/USD index). Mark price and mark IV
  are comparison fields only.
- Missing quotes and failed solves stay `NaN`; Plotly traces use
  `connectgaps=False`; interpolation is a separate explicit operation.
- Moneyness is spot-based `K / S`. Numerical `tau` drives calculations, expiry
  ordering and maturity axes; expiry datetimes come from source metadata.
- Combined IV and the ATM proxy follow the rules in `README.md`.
- When a change picks a convention, tolerance or default that affects the
  numbers, name it and say why in the summary.
- New dashboard features use the Deribit adapter (`iv_surface/deribit.py`).
- `experiments/` holds research scripts and their results. Runtime behaviour
  is accepted through `tests/`.

## Validation

Run `.venv/bin/python -m pytest`. Tests run offline on the frozen snapshots in
`data/`; `scripts/check_bybit_chain.py` is a manual live diagnostic.
Launch the dashboard with `.venv/bin/python -m streamlit run app.py`.

## Agent skills

### Issue tracker

Issues are local markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
