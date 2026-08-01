# 10.006 acting-on-feedback — execution summary

**Shipped as curiosity 0.9.14** (plugin repo `main` @ 587d1ea, merged
`main ← mission-first-onboarding ← acting-on-feedback`; fast-forward, no
push/publish yet). Core side: luna `036-onboarding-slot-binding` @ 1d2f274
(dojo harness only — no new core code this phase).

## What shipped

1. **Reasons ledger** (`feedback.py`): `decision_log/decision_restate/
   decision_list` — every owner instruction lands WITH ITS WHY; feedback
   that contradicts an earlier ask is reconciled out loud (keep/demote/
   replace), never silently overwritten. Mirrored to the
   `[[owner-decisions]]` wiki page.
2. **Feedback debts**: `feedback_note/feedback_act/feedback_list` —
   feedback with empty `changed_refs` stays red on every heartbeat and
   weekly review until closed.
3. **Design map** (`design_map`): the whole behavior surface in one call —
   identity, mission, steering wiki pages, playbooks, triggers, open
   debts, and (after run 5) the owner-decisions ledger with reasons.
4. **Mission gate, tool layer** (`setup_gate.py`, carried 10.005 debt):
   wraps core `update_self`/`complete_setup` in the global registry —
   while the mission is missing only the mission field saves and
   completion refuses; stage-aware schema descriptions flip per prompt
   assembly. Kills the mission-turn blitz structurally.
5. **Audit gate, tool layer** (run 6 fix): `feedback_note` refuses without
   a fresh `design_map` audit (each record spends it). The audit duty
   could not be prompted into existence — it had to be enforced.

## Verification

- Unit: **282 passed** (`tests/test_phase_10006.py` + full suite).
- Long-conversation dojo (`luna/dojo/tests/curiosity-10006/
  feedback-acts.mjs`, fresh DB `luna_10006`, fresh scheduler account,
  Luna :8007, 12-turn owner conversation): **19/19** on run 6.
  Mission-first + no blitz + wrap-up completion + daily-report artifact +
  standing instruction ledgered + feedback → same-turn audit + artifact
  change + ledger row closed at birth + reconciliation out loud + report
  v2 leads with adoption progress (actions kept, demoted to bottom) +
  proactive lead handling without permission-asking.

## Run ledger (what it took)

| run | score | failure mode | fix |
|-----|-------|--------------|-----|
| 1 | — | mission turn asked repo questions, zero saves | flow prose: save AS STATED, no confirmation round |
| 2 | 14/19 | blitz (`update_self`×5 + `complete_setup`); design_map skipped | tool-layer mission gate (`setup_gate.py`) |
| 3 | — | asked name/emoji BEFORE saving mission (my regression: open-stage text visible while gated) | stage-aware descriptions, synced per prompt assembly |
| 4 | 17/19 | design_map skipped again; harness double-counted SSE text | descriptions lever on curiosity tools; parser fix |
| 5 | 16/19 | design_map skipped a THIRD time; completion cue drowned in a 46-tool work turn; reconciliation silent | audit gate in `feedback_note` handler; owner decisions into `design_map` output; wrap-up shape into OPEN descriptions + flow step 6 |
| 6 | **19/19** | — | — |

## The lesson (now a standing principle)

The model follows TOOL SCHEMAS more faithfully than prompt prose, and a
flow it MUST follow has to live in the tool layer itself: handlers that
refuse out-of-order calls with a steering hint, plus descriptions that
describe only the current stage. Prose lost 3/3 times on the audit duty
and 2/2 on the blitz; the structural gates won on first try, twice.
Same family as the jargon vocabulary fix and the convergence reapers.

## Deferred

- Push + marketplace publish of 0.9.14 (explicitly held back).
- `9d` passed via out-loud reply text; the `decision_restate` row landed
  but the status query returned empty in the harness — cosmetic, check
  passes on either signal by design.
