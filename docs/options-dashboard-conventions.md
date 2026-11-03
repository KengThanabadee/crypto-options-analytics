# Options Dashboard — Convention research

> Historical status — 2026-11-02: a record of the original research. The agreements carried forward live in the [spec](../.scratch/options-dashboard/spec.md). Old proposals and questions do not reopen accepted scope; the Call/Put split IV view in section 3 was set aside on 2026-11-03.

Documents checked on 2026-11-01 to support discussing one topic at a time. Status: findings and proposals, not additional agreements. The actual agreements are in the [spec](../.scratch/options-dashboard/spec.md).

## How to discuss the remaining topics

Before asking Keng, prepare examples from real products with sources, and explain the purpose, benefits/tradeoffs and our proposal. Separate documented behaviour from proposals, and do not call a self-chosen default an industry convention. Ask one topic at a time where it affects use or interpretation; routine development details need not become per-button approval questions.

## 1. Strike range — Near spot accepted 2026-11-02

Keng chose to start near spot, as Fuelmaps does, rather than all strikes. Claude proposed this release's ±10% default with shared OI/GEX zoom. The details in use are in the [spec](../.scratch/options-dashboard/spec.md); the references below are kept as comparison history.

| Real example | Documented | Not yet confirmable |
| --- | --- | --- |
| [GammaFlip](https://gammaflip.io/methodology) | The app does not filter strikes or set a minimum OI; historical files are limited to ±25% of spot | Does not say which range the screen opens zoomed to. Keeping every strike does not mean every strike appears full-screen on first load |
| [MenthorQ Options Menu](https://menthorq.com/guide/options-menu/) | The Exposure chart zooms the strike range with a vertical bar, scroll/pinch, and shows a current-price marker; expiry selection is separate from the visible range | Does not state a default range as a percentage, or whether totals change with the viewport |
| [Fuelmaps](https://fuelmaps.io/options-analytics/) | Checked again 2026-11-02: OI states "within 15% of spot"; gamma has Near/±10%; the method says Near covers at least a one-day 2σ range | The text gives no complete Near formula. Near is not assumed to equal ±10% or to be a shared standard across sites |

Conclusion: products offer both wide views and near-price focus, with range controls. This set of documents gives no evidence that ±20% is a shared default.

- **All strikes:** shows concentration far from the price too, but a wide range can make bars near the current price hard to read.
- **Near spot:** levels near the price read clearly, but distant OI needs zooming out. A value such as ±20% is our design choice, not a calibrated range or industry standard.
- Minimum proposal: keep the full snapshot universe and selected expiries, treat the strike range as a shared OI/GEX display zoom, and offer a way back to All strikes. If summary totals are added later, state their calculation scope separately from the viewport.
- Proposal history: an agent proposed ±20% with All strikes, and Claude proposed All strikes with zoom. Keng then chose to start near spot as Fuelmaps does, so Near spot follows the current spec.

## 2. GEX when some constituent contracts are missing — accepted 2026-11-02

One strike can aggregate several expiries and both Call/Put, while some contracts lack IV/gamma. Keng confirmed showing an incomplete-data status instead of the aggregate bar, with the partial subtotal and coverage available in the details. The rules in use are in the [spec section on GEX with incomplete data](../.scratch/options-dashboard/spec.md). The sources below are the origin of the original research, not a convention shared by every product.

- [IBKR Option Columns](https://www.ibkrguides.com/traderworkstation/option-columns.htm) states that IV is not shown when the midpoint IV does not converge.
- [Cboe DataShop FAQ](https://datashop.cboe.com/faqs) states that, for Greeks, the offer is used when IV cannot be found from the mid. This is that product's method, not a proposal to change our midpoint basis.
- No convention for incomplete aggregated GEX bars was found in these sources.
- Agreement: a GEX bar shows a status when data for the contracts to sum is incomplete, with the partial subtotal, coverage and reasons viewable in the details, clearly labelled partial. Net/Gross use the same rule, and OI still shows as before.
- Checks: zero OI gives a zero contribution, not missing data; missing OI still counts as missing, and a partially computed total is not presented as the complete total, because Net can have the wrong sign.

## 3. Viewing IV split by Call/Put — to discuss later

Status as of 2026-11-02: an additional proposal, not a condition for closing the existing scope. Keng confirmed keeping the existing IV charts and adding the IV source selector per the spec. Verify Combined correctness and the origin of the bid–ask band during development.

- [Optionomics Volatility Skew](https://docs.optionomics.ai/analytics/volatility-skew/) shows Call IV and Put IV lines with an expiry selector; it does not confirm our Combined method or defaults.
- [IBKR Volatility Lab](https://ibkrguides.com/traderworkstation/volatility.htm) compares skew across expiries; it does not establish three expiries as the default.
- Minimum proposal to discuss: let the smile choose Combined / Calls / Puts to read quote differences. Extending the selector to the heatmap/3D is not implicitly approved.
- The bid–ask IV band must trace back to its source contracts. Where a Combined point averages Call/Put near ATM, there is no single tradable quote interval.

## What to keep and verify in development

Reading `app.py` shows an Observed/Surface heatmap toggle, a 3D view with observed markers, and a smile with expiry selection starting at the first three usable expiries; `iv_surface/surface_builder.py` already has Combined IV and the near-ATM average. These need not be re-asked part by part. Accepting the developed behaviour requires checking the source again at that time.

Computing bid/mid/ask separately, provenance, missingness, units, the same snapshot, and keeping display-interpolated IV out of per-contract gamma are correctness requirements, not extra preferences.

## Review trail

Later, the real tabs for GammaFlip, MenthorQ and Fuelmaps were opened and scrolled at Keng's request. Images and observations are in the [browser walkthrough](reference-reviews/browser-walkthrough/review.md). On the Fuelmaps options page loaded that time, Near was selected with ±10% available to toggle. This is UI evidence in addition to the earlier documents; it does not change the conclusion that no shared default is confirmed across products. Additional features found are inspiration and do not expand scope automatically.

Two Codex research tasks split strikes from the remaining topics, and Claude reviewed each report, checking consistency from the provided text without opening the web itself. Claude then opened and confirmed the GammaFlip, MenthorQ, Fuelmaps, IBKR Option Columns, Optionomics and Cboe FAQ pages, and applied the corrections on viewport/coverage, optional totals and not extending per-side surfaces automatically in this note.

The reasoning carried forward is summarised in this note and the [spec](../.scratch/options-dashboard/spec.md). The raw briefs, reviews and logs are archived locally in [docs/history](history/research-2026-11/README.md), which is kept out of git.
