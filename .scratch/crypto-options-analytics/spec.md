# Crypto options analytics: the dashboard is the project

**Status:** ready-for-agent

Accepted 2026-11-04 after a grilling session. Tickets go in `issues/` beside
this file. Starts after the `dashboard-layout` spec is done.

## Problem Statement

The project started as `implied-vol-surface`, a small quant library
("Black-Scholes implied-volatility solving and simple IV surface
interpolation") with a dashboard on top. It is now a Deribit options dashboard
with open interest, gamma exposure and implied volatility, checkable numbers,
and fetch, save and reopen. The way it presents itself no longer matches what
it is:

- The repository, local folder and distribution are named
  `implied-vol-surface`, and the package is `iv_surface`. That package also
  holds OI, GEX, saved analyses and the Deribit fetch.
- The README introduces a library "for feeding downstream projects" and spends
  about 160 lines on function signatures. No other project on Keng's machine
  imports the package, and some documented functions are not used by the
  dashboard at all.
- An older IV pipeline remains in the code: building a surface from a price
  grid with one chosen rate, its chain wrappers, and two superseded
  interpolators. The dashboard replaced it with the IV source path (Exchange
  mark, or Quote midpoint at each contract's forward rate), but the old path
  was never removed and is exercised only by its own tests.
- Streamlit and Plotly are optional extras, so a plain install cannot run the
  project's main product.

ETH support is planned, so the new name must not tie the project to BTC.

## Solution

- The project is renamed `crypto-options-analytics`: GitHub repository, local
  folder and distribution name. The package becomes `options_analytics`. The
  dashboard UI package keeps its name.
- The README leads with the dashboard: what it shows, how to run it, how to
  read each chart and why the numbers can be checked. A short "How the code is
  organised" section replaces the function-by-function API reference.
- The unused IV pipeline is removed. The solver functions the Quote midpoint
  path relies on stay, and the Call/Put combine step moves next to its only
  user, the IV source module.
- Streamlit and Plotly become regular dependencies, so a plain editable install
  runs the dashboard.
- The rename happens last, done by Claude end to end, including the GitHub
  rename, the git remote, Claude's project memory folder and the local folder.

## User Stories

1. As a résumé reader, I want the repository name to say it is crypto options analytics, so that I know what it is before opening it.
2. As a résumé reader, I want the README to open with what the dashboard shows and a preview, so that I see the product first.
3. As a résumé reader, I want the README to say why the numbers can be trusted (gamma matched to Deribit, IV repriced within $0.01, GEX assumptions stated), so that I see the engineering behind the charts.
4. As a résumé reader, I want a short "How the code is organised" section, so that I can find my way around the code without a signature listing.
5. As a résumé reader, I want the README to stop describing a library for downstream projects, so that it does not claim something untrue.
6. As a new user, I want a plain editable install to bring everything the dashboard needs, so that I can run it without knowing about extras.
7. As a new user, I want the run command and the offline frozen snapshot explained near the top, so that I can open the dashboard in a minute.
8. As Keng, I want the old GitHub URL to keep working after the rename, so that links I have shared still land on the project.
9. As Keng, I want the local folder renamed to match, so that the folder name matches the project.
10. As Keng, I want Claude's memory for this project carried over to the new folder path, so that what I taught it still applies.
11. As Keng, I want the git remote updated to the new repository URL, so that pushes go to the right place.
12. As Keng, I want the project name to leave room for ETH, so that adding ETH later does not need another rename.
13. As a maintainer, I want the package named after what it does, so that OI, GEX and saving do not live in a package named after one chart.
14. As a maintainer, I want the unused IV pipeline removed with its tests, so that nobody mistakes it for the path the dashboard uses.
15. As a maintainer, I want the Deribit parsing checks that went through the old pipeline kept, rewritten through the IV source path, so that parsing stays covered.
16. As a maintainer, I want the Call/Put combine step to live in the IV source module, so that the surface builder module can be deleted.
17. As a maintainer, I want the solver kept as our own Newton-Raphson with bisection fallback, so that Quote midpoint and the bid–ask band still use our solver.
18. As a maintainer, I want CI to install the project with a plain editable install plus test tools, so that CI checks the install users get.
19. As a maintainer, I want the rule that calculations and figures run without Streamlit kept, so that the analytics stay testable without a UI.
20. As a maintainer, I want AGENTS.md updated for the new names and dependencies, so that agents follow the current layout.
21. As a maintainer, I want the experiment scripts updated to the new package name, so that they still run.
22. As a market explorer, I want every number, chart and saved-file format unchanged by the rename, so that my saved analyses still open and match.

## Implementation Decisions

**Removal of the unused IV pipeline**

- Removed: the price-grid surface builder, the IV interpolation helper and the
  1D smile interpolator; the chain-to-surface wrappers, their input
  preparation and their private helpers; the surface builder module once
  emptied.
- Kept: Black-Scholes pricing and the IV solver (Newton-Raphson with bisection
  fallback), and the Call/Put combine step with its source codes, which moves
  into the IV source module.
- Tests for removed functions go. Deribit parsing checks that went through the
  old chain wrapper are rewritten through the IV source build. Solver tests
  for the kept functions stay.
- This lands before the package rename so the rename touches fewer files.

**Package and distribution**

- Distribution name `crypto-options-analytics`; package `options_analytics`;
  the description names a Deribit options dashboard with OI, GEX and IV.
- Streamlit and Plotly move into the main dependencies. The dev extra keeps the
  test and lint tools. The extra named `dashboard` goes away.
- The rule stays that quantitative transforms and figure construction import
  nothing from Streamlit. AGENTS.md drops "Plotly and Streamlit stay in
  optional extras" and keeps the no-Streamlit rule.
- The package rename is one mechanical change across the package, the
  dashboard modules, the page file, tests, scripts, experiments, README and
  AGENTS.md. It is a single ticket: there are no outside importers, so no
  expand–contract shim is needed.
- These stay as they are: the saved-file format id `btc-options-analysis`,
  its versions, the saved file name pattern, the page title and the dashboard
  UI package name.

**README**

- Order: title and one-paragraph pitch; the dashboard preview images; running
  it (install, launch, offline frozen snapshot, Fetch latest); reading each
  section (OI and GEX, IV source, IV surface, IV smiles, ATM term structure);
  save and reopen; why the numbers can be checked; how the code is organised;
  assumptions and limitations; tests.
- "How the code is organised" lists each module in a line or two (Deribit
  snapshot and parsing, chain helpers, solver, IV source, surface transforms,
  positioning, saved analysis, figures, dashboard UI). Signatures are left to
  docstrings.
- Content that documents behaviour stays, reworded where it was library
  framing: Combined IV and ATM proxy rules, the IV source definitions, Deribit
  input details, GEX formula and assumption, and the saved file format.

**Rename outside the repository (last ticket, done by Claude)**

- Order:
  1. Commit everything in the repository that refers to the new names.
  2. Rename the GitHub repository to `crypto-options-analytics`; GitHub
     redirects the old URL.
  3. Point `origin` at the new URL and confirm it with a fetch.
  4. Copy Claude's project memory folder to the path derived from the new
     folder.
  5. Move the local folder.
  6. Recreate the virtual environment at the new path, since its scripts
     record absolute paths, and run lint and tests there.
- Moving the folder ends any Claude session working in the old path. It is the
  last step, and the summary says to open the next session in the new folder.

## Testing Decisions

A good test checks behaviour through the highest existing seam: the dashboard
page via `AppTest`, saved files via save and open, figures via their builders.
This spec adds no behaviour, so the existing suite is the evidence.

- The whole test suite and lint pass after each ticket, and the dashboard page
  tests show the same charts and numbers as before.
- Deribit parsing tests that used the removed wrapper are rewritten through
  the IV source build and keep their assertions on the parsed chain.
- CI installs with a plain editable install plus the dev tools. That proves
  the dashboard runs from the main dependencies.
- The outside rename is verified by the repository view showing the new name,
  the old URL redirecting, `origin` fetching from the new URL, and lint and
  tests passing in the moved folder.
- The rewritten README is checked by opening the dashboard and comparing each
  described control and chart to the page.

## Out of Scope

- ETH or any second underlying, an asset selector, and the title, saved-file
  and spec changes those bring: a future spec.
- Any change to computed numbers, charts or the saved-file format.
- The dashboard layout rework: the `dashboard-layout` spec.
- Publishing to PyPI.

## Further Notes

- No other project under Keng's Developer folder imports the package (checked
  2026-11-04), which is why the rename needs no compatibility shim.
- The old IV pipeline was superseded when Quote midpoint moved to each
  contract's forward rate and Exchange mark became the default IV source. Git
  history keeps it for reference.
