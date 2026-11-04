# Dashboard layout: one IV surface view, controls beside their charts

**Status:** ready-for-agent

Accepted 2026-11-04 after a grilling session and a layout prototype. Tickets
go in `issues/` beside this file. The prototype lives on the local branch
`prototype/dashboard-layout` (commit 89cdca2, variants A–D via `?variant=`);
variant B won.

## Problem Statement

Keng uses the dashboard to read positioning (OI and GEX) and then volatility
pricing for one Deribit BTC snapshot. The page works, but it reads as
cluttered and loosely organised:

- The Heatmap and the 3D surface are separate tabs, although they show the
  same interpolated values for the same moneyness range and share every
  control but one.
- The Moneyness range control sits in the sidebar, far from the two charts it
  changes.
- The IV method notes (Combined IV coverage, Deribit pricing) render directly
  under the Save analysis button, so they look like part of save and reopen.
- Long methodology paragraphs sit under the GEX chart and the IV smile chart.
- The Fetch latest button sits above the snapshot caption, and the index price
  appears in the IV section as a separate line that repeats the IV source
  selector.
- The 3D surface leaves a lot of empty space above and below the mesh, and it
  is built twice on every run.
- Screenshots taken for the README come out in the light theme, while Keng
  uses the dashboard in dark mode.

The code mirrors this: one IV module builds the source control, the cached
build, sidebar notes, sidebar controls, interpolation and four tabs. Widget
keys are spelled out separately in each section, in the saved-settings reader
and in the reopen path. Where a sidebar element appears depends on which
section happens to call it first.

## Solution

The page keeps its order: OI and GEX on top, then implied volatility. Within
that:

- A one-row header shows `Deribit BTC · <snapshot label>: <capture time> UTC ·
  Index $<index>` on the left and **Fetch latest** on the right.
- The IV section has three tabs: **IV surface**, **IV smiles** and **ATM term
  structure**.
- The IV surface tab has a **View** control (Heatmap | 3D, Heatmap first), the
  **Moneyness range** control and, in Heatmap view only, the **Heatmap values**
  control (Surface | Observed). One visible-range caption sits above the
  chart. Only the chosen chart is built.
- Under the GEX, IV surface and IV smile charts sits a one-line caption, with
  the full explanation in an expander below it.
- The sidebar holds **Saved analysis** (Reopen, Save) and, under its own
  **Method notes** heading, the Combined IV coverage and Deribit pricing
  notes.
- The 3D surface fills its frame with less empty space.
- Save analysis also stores the chosen View.
- The app keeps following the viewer's system theme, with Streamlit's own
  System / Light / Dark switch in the ⋮ menu. README screenshots are always
  taken in dark mode.

## User Stories

1. As a market explorer, I want the snapshot capture time, its label and the index price on one line at the top, so that I see what I am looking at before any chart.
2. As a market explorer, I want Fetch latest at the right end of that line, so that it is where I look for a page-level action and does not push the caption down.
3. As a market explorer, I want the index price shown once in the header, so that the IV section does not repeat it on a separate line.
4. As a market explorer, I want the header to read "Fetched snapshot" or "Reopened snapshot" as it does today, so that I still know where the data came from.
5. As a market explorer, I want OI and GEX to stay above the IV charts, so that I read positioning first and then volatility pricing.
6. As a market explorer, I want the Heatmap and the 3D surface in one IV surface tab, so that I treat them as two views of the same surface.
7. As a market explorer, I want a View control that switches between Heatmap and 3D, so that I can change the view without changing tabs.
8. As a market explorer, I want the IV surface tab to open on the Heatmap, so that the first view is quick to load and easy to read cell by cell.
9. As a market explorer, I want the Moneyness range control next to the View control, so that I change the range where I see its effect.
10. As a market explorer, I want the Moneyness range to keep applying to both the Heatmap and the 3D view, so that switching view keeps the same range.
11. As a market explorer, I want the Heatmap values control (Surface | Observed) shown only in Heatmap view, so that I do not see a control that does nothing in 3D.
12. As a market explorer, I want my Heatmap values choice kept while I look at 3D, so that switching back to Heatmap shows what I had.
13. As a market explorer, I want one visible-range caption (observed, interpolated, blank, K/S range) above whichever chart is shown, so that I know how much of the view is real data.
14. As a market explorer, I want only the chosen surface chart built, so that the page responds faster.
15. As a market explorer, I want the 3D surface to fill its frame without large empty bands, so that the mesh is large enough to read.
16. As a market explorer, I want the 3D surface to keep its compact layout on narrow screens, so that it stays readable on a phone or a narrow window.
17. As a market explorer, I want the three IV tabs to be IV surface, IV smiles and ATM term structure, so that the tab row is shorter and each tab is a distinct question.
18. As a market explorer, I want a one-line caption under the GEX chart giving the formula and unit, so that I can read the chart without a paragraph in the way.
19. As a market explorer, I want an expander under the GEX chart with the full GEX method, so that I can check the assumptions when I need to.
20. As a market explorer, I want a one-line caption under the IV smile chart saying what the line and the shading are, so that I can read the chart at a glance.
21. As a market explorer, I want an expander under the IV smile chart explaining the bid–ask display band, so that I do not mistake the shading for a tradable quote.
22. As a market explorer, I want the surface interpolation method in an expander under the IV surface chart, so that the explanation sits next to the values it explains.
23. As a market explorer, I want the sidebar to show Saved analysis first and the IV method notes under their own Method notes heading, so that the notes do not look like part of save and reopen.
24. As a market explorer, I want the Combined IV coverage note to keep naming the selected IV source, so that I know which source the counts describe.
25. As a market explorer, I want Save analysis to store the View I chose, so that reopening the file shows the same view.
26. As a market explorer, I want a file saved before this change to open on the Heatmap view, so that my older saved analyses still open.
27. As a market explorer, I want reopening to keep restoring the moneyness range, the heatmap values and every other setting as it does today, so that nothing I saved is lost.
28. As a market explorer, I want the IV view settings, including the View, kept when the IV charts cannot be drawn, so that they return when the charts do.
29. As a market explorer, I want the dashboard to follow my system's light or dark setting and keep the ⋮ menu's theme switch, so that it opens dark on my machine and I can still change it.
30. As a market explorer, I want the README images captured in dark mode, so that they look like the dashboard I use.
31. As a market explorer, I want every number on the page unchanged by this rework, so that the layout change does not alter any analysis.
32. As a maintainer, I want each saved setting's widget key defined in one place, so that adding a setting does not mean editing three lists.
33. As a maintainer, I want each IV view (surface, smiles, term structure) in its own module, so that each one can be read and changed on its own.
34. As a maintainer, I want the page file to only lay out the header, sidebar and sections, so that the page structure is visible in one short file.
35. As a maintainer, I want the observed-only surface frame built by a plain function outside the dashboard, so that it is tested without Streamlit.
36. As a maintainer, I want sidebar placement decided explicitly by the page layout, so that it no longer depends on which section calls the sidebar first.
37. As a maintainer, I want dashboard tests to find controls by key rather than by position, so that moving a control does not break unrelated tests.
38. As a résumé reader, I want the README dashboard section and images to match the new layout, so that what I read is what the app shows.

## Implementation Decisions

**Page layout**

- The page file only lays out: page config, title, the header row, the sidebar
  (Saved analysis, then a Method notes container), the positioning section, the
  IV section, and the Save analysis control filled last into its sidebar slot.
- The IV section writes its method notes into a sidebar container the page
  passes in, instead of writing to the sidebar directly.
- The header row is two columns: snapshot caption with the index on the left,
  Fetch latest on the right. Fetch latest still runs before the snapshot is
  read, so a fetch updates the caption on the same run.
- Index price for the header comes from the parsed chain's index column, the
  same value the positioning section uses.

**IV section**

- The IV section keeps the IV source control and the cached builds, builds the
  shared long frame, writes the method notes, and lays out the three tabs. Each
  tab calls its own view module: surface view, smile view, term structure view.
- The surface view owns the View, Moneyness range and Heatmap values controls,
  the visible-range caption, the chosen chart, the interpolation expander, and
  the CSS that switches the 3D chart between its wide and compact layouts.
- Controls are segmented controls, matching IV source and the GEX controls.
  Widget keys stay `moneyness_range` and `heatmap_view`; the new View control
  uses `surface_view`. Choices are Heatmap and 3D, with Heatmap the default.
- When the 3D view is shown, the Heatmap values control is not drawn, and its
  session value is written back to itself so Streamlit keeps it (the same
  technique the IV section already uses when the IV build fails). That
  keep-settings path also covers `surface_view`.
- In 3D view the chart uses the interpolated surface with observed points, as
  today; Heatmap values does not apply to it.
- The observed-only frame (IV replaced by observed IV, value type Observed or
  Missing) becomes a function in the surface transforms module.
- The responsive wide/compact 3D pair stays (it fixed narrow-width layout in an
  earlier browser review), but it is built only when the 3D view is chosen.

**Captions and notes**

- GEX: caption "GEX = s × gamma × OI × index² × 1% · USD per 1% BTC move";
  expander "How GEX is calculated" holds today's full text.
- IV smiles: caption "Observed Combined <source> IV · all strikes · gaps
  preserved · shading = bid–ask IV band"; expander holds today's band text.
- IV surface: expander "Surface interpolation" holds today's interpolation text.
- Sidebar Method notes: "Combined IV coverage · <source>" (metrics and rule
  text as today) and "Deribit pricing".
- The ATM term structure tab keeps its caption, gap notice and "ATM selection
  details" expander unchanged.

**Saved settings**

- A settings module holds the table of saved-setting names, their widget keys
  (some keyed by snapshot id) and the conversions both ways. Save reads the
  current settings from it; Reopen turns saved settings into widget values
  from it. The customer-side label/sign mapping moves there, so the settings
  code no longer imports from a page section.
- The saved file gains an optional `surface_view` setting (Heatmap or 3D).
  Reading a file without it gives Heatmap. `FORMAT_VERSION` and
  `CALCULATION_VERSION` stay at 1: the setting changes no number, and older
  files stay valid.

**3D surface sizing**

- The 3D figure's camera, aspect ratio, height and margins are retuned so the
  mesh fills the frame at the standard 1400 px capture width and in the
  compact layout. The exact values are chosen by looking at the rendered chart.
  The camera `uirevision` string changes so browsers pick up the new camera.

**Theme and README images**

- No theme is set in Streamlit config. The app follows the viewer's system
  theme, and the ⋮ menu keeps its System / Light / Dark switch. Setting a base
  theme in config removes that switch, which was checked on Streamlit 1.64.
- The README capture script asks the browser for the dark colour scheme
  before loading the page. It drops the separate surface screenshot step for
  the old 3D tab and instead switches the View control to 3D.

## Testing Decisions

A good test drives the page the way a user would (open it, set a control,
reopen a file) and checks what is shown: tab labels, control values, captions,
chart counts and figure data. It does not check which helper was called or
how modules are split.

- **Page level (main seam).** Streamlit `AppTest` on the whole page, as in the
  existing dashboard tests. It covers the three tab labels, finding View,
  Moneyness range and Heatmap values by key, Heatmap values hidden in 3D and
  its value kept, the header caption including the index, the expanders under
  the GEX, surface and smile charts, the Method notes heading, the chart count
  for each View, and that Save then Reopen restores the View.
- Existing tests that find controls by position (the first sidebar radio, the
  first main radio) switch to lookups by key first, before any control moves.
- The check that the 3D mesh values equal the heatmap values on one run
  becomes two runs, one per View, comparing the recorded figures.
- **Saved analysis.** The save and open tests cover the optional
  `surface_view`, a file without it opening as Heatmap, and an invalid value
  being rejected.
- **Surface transforms.** A plain test for the observed-only frame function,
  next to the existing surface interpolation tests.
- **3D figure.** The existing 3D figure test updates its expected height and
  aspect values and keeps checking that the compact layout is shorter.
- The README images, the dark capture and the 3D framing are checked by
  opening the dashboard and looking at every chart this spec touches, as
  AGENTS.md requires.

## Out of Scope

- Renaming the project, repository, folder or package, rewriting the README
  as dashboard-first, and removing the unused IV pipeline: covered by the
  `crypto-options-analytics` spec.
- ETH or any second underlying.
- New analytics, new charts or any change to computed numbers.
- Showing IV smiles and ATM term structure side by side.
- Pinning a theme in Streamlit config.

## Further Notes

- The prototype's variant code was written under prototype constraints and is
  not to be merged; it is reference only.
- The settings table, the per-view modules and the observed-only transform are
  prefactoring. They land first, with no visible change, so the visible
  changes land on a cleaner base.
