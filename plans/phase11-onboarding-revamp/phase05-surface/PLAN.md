# Phase 05 — The surface (11.004 / M4 + M0a buttons)

Rebuild the Missions tab per [../mock.html](../mock.html). Journey, not
dashboard. Progressive disclosure: sections render only when their data exists
— day one = mission + journey + now & next.

## Changes

- **overview.py:** payload for the 8 blocks (mission-in-my-words + intake Q&A
  · where-we-are 6-step display mapping over S0–S5, S-codes never serialized ·
  now & next from NextStep · waiting-on-you · what-I-run-for-you (phase07,
  renders empty-hidden until then) · what-happens-when by horizon kind ·
  what-you-got + minutes tally · my-rules strip (phase08, hidden until
  policies exist)).
- **ui/app.js + static:** render mock 1:1 (ux_guidelines tokens, eyebrow
  grammar). Abilities/gap board/heartbeats/JD stay on Operational tab; JD one
  click away.
- **M0a buttons:** "Go ahead"/"Approve"/"Confirm" POST
  `/api/conversations/{id}/messages` `{kind:"muted", channel:"moment"}` with
  object-id-bearing text; conversation id via `GET /api/conversations`;
  "Change it" fallback = muted ask (until phase06 bridge).
- **11.005 dial:** rung rendered as plain words + "revoke anytime"; visible
  error → rung drop said out loud (wire `feedback_note`/`feedback_act`).

## Testable units

| # | Unit | Test |
|---|---|---|
| 1 | Payload per lifecycle | unit: day-one payload has exactly 3 sections; earning-stage has cards+waiting; operating adds catalog/rules |
| 2 | No jargon | unit: serialized payload contains no S-codes/rung numbers/banned words |
| 3 | Step derivation | unit: saved/confirmed/first-win/S3/setup-vs-work → correct step; edge: confirmed-but-no-value |
| 4 | Buttons | integration on real Luna: click Go-ahead → muted moment turn arrives in open chat with object id; agent acts on it |
| 5 | Rung words + drop | unit: dial strings; feedback error → drop + sentence |
| 6 | Visual | headless-Chrome screenshot vs mock; ux_guidelines check |

## Regression gate

Full suite; **real-Luna verification mandatory** (cookie auth, widget token,
stale-route check; sync `~/.luna/managed_plugins`). Dojo: button-driven
approve flow end to end.

## Version

plugin-curiosity 0.16.0.

## Exit

`execution_summary.md`; button copy that the agent misread gets fixed here
and the mapping table in ../PLAN.md updated.
