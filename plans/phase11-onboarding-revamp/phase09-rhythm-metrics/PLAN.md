# Phase 09 — Improvement rhythm & metrics (M7)

The proactive side: weekly/monthly rhythm with predictions, and the adoption
funnel as server-computed KPIs.

## Changes

- **review.py:** weekly note = 5 lines (ran / cost-vs-value owner units /
  "No issues" when true / max ONE micro-proposal with `predicted` before,
  `actual` after). Monthly: promised-vs-delivered vs Agree numbers, savings,
  top 1–3 opportunities each anchored to a stored owner quote, one decision
  ask, downsells included. Prompt law: recovery and proposals never share a
  turn.
- **telemetry.py:** time-to-confirmed-mission · time-to-first-win · card
  veto/redirect rate · step 3→5 climb · expectation hit rate · boundary
  exceptions · time-to-self-report · hypercare exit rate/time · override
  rate · proposal acceptance · prediction accuracy. All server-computed.

## Testable units

| # | Unit | Test |
|---|---|---|
| 1 | Weekly format | unit: 5-line cap, one-proposal cap, "No issues" honesty (only when true) |
| 2 | Prediction log | unit: proposal stores predicted; completion stores actual; accuracy computed |
| 3 | Monthly anchor | unit: each opportunity carries value_ref to owner quote; downsell path |
| 4 | Never-share-turn | prompt test + dojo: incident week → proposal deferred to next note |
| 5 | Metrics | unit: each KPI from fixtures; no self-reported numbers |
| 6 | Live rhythm | dojo: simulated week → note arrives correct; accept proposal → next note reports actual |

## Regression gate

Full suite (`test_review.py` rewritten); dojo unit 6; real-Luna weekly note.

## Version

plugin-curiosity 0.19.0 → then re-stamp **1.0.0-adoption** decision with Roy.

## Exit

`execution_summary.md` + a phase11 closing summary rolling up all phase
learnings and the metric baselines.
