# Phase 03 — Next-step cards (11.002 / M2)

No spend the human couldn't have seen coming. Every self-directed run opens
with a card.

## Changes

- **models.py:** `NextStep` — what/why/produces/cost_text/status
  {proposed,announced,running,done,redirected}/wait_until/value_ref/
  plan_change_note.
- **next_steps.py (new):** `next_step_post` / `next_step_start` /
  `next_step_done` (links value-log receipt).
- **gating.py:** rung 1–2 → proposed + 2 h veto window, timeout-to-proceed
  with a note; rung 3+ → announced. Veto clock pauses in owner quiet hours.
- **loops/research/engine:** scheduled runs (daily research, heartbeats,
  deep kickoff) post card as step 0; dream exempt from veto, posts what it did.
- Redirect requires `plan_change_note`; silent retry is a test failure.

## Testable units

| # | Unit | Test |
|---|---|---|
| 1 | Card lifecycle | unit: proposed→running→done links receipt; announced path for rung 3+ |
| 2 | Veto/timeout | unit: "go" starts now; silence starts at wait_until with note; "change it" → redirected + plan_change_note required |
| 3 | Scheduled step 0 | unit: research/heartbeat/deep-kickoff runs create a card before spending; dream posts after |
| 4 | Rung mapping | unit: rung transitions flip proposed/announced correctly |
| 5 | Live veto | dojo: propose → owner "change it" → visibly different plan; propose → silence → timeout start with note |

## Regression gate

Full suite green (esp. `test_loops.py`, `test_research.py`, heartbeat/slot
tests). Dojo unit 5. Verify cards on real Luna overview payload.

## Version

plugin-curiosity 0.14.0.

## Exit

`execution_summary.md`; learnings on veto-rate (too many vetoes = bad
proposals; zero = rubber stamp) recalibrate phase05 card rendering copy.
