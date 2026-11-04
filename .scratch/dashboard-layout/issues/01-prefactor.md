# 01: Prefactor the dashboard with no visible change

**What to build:** The page looks and behaves exactly as today, but the code is ready for the layout changes. Dashboard tests find the moneyness range and heatmap values controls by key, not by position. Saved-setting names, widget keys and conversions live in one settings table that both Save and Reopen use, and the customer-side mapping lives there instead of in the positioning section. The IV section delegates each tab to its own view module (surface, smiles, term structure). The observed-only surface frame is a plain function in the surface transforms module. The page passes the IV section an explicit sidebar container for its method notes, so sidebar placement no longer depends on call order. The sidebar keeps today's order for now.

See `../spec.md` (Implementation Decisions: Page layout, IV section, Saved settings).

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] No test looks up the moneyness range or heatmap values control by position.
- [ ] Save and Reopen both read widget keys and conversions from one settings table; the settings code imports nothing from a page section.
- [ ] Surface, smile and term structure views are separate modules called from the IV section; the page file only lays out.
- [ ] The observed-only frame function has its own plain test without Streamlit.
- [ ] The page, every chart and every number are unchanged; lint and the full test suite pass.
