# Phase 9B — Open-loops ledger + ask economics + value log (durability engine)

**Parent:** [../PLAN.md](../PLAN.md) — mechanisms C (open loops) and G (ask
economics + value log). Pure structure + one prompt hook (loop patrol step 0);
independently testable without any LLM behavior.

**Depends on:** 9A (loops may reference scopes; charter Plan-changes helper).
**Blocks:** 9C (prompts cite loop/ask/value tools), 9D.

---

## Deliverables

1. **`curiosity_loops` table** — id, mission_id, kind
   (`question|promise|waiting_on|handoff|ask`), statement, who
   (`owner|self|<person>`), opened_at, next_nudge_at, nudge_count, status
   (`open|answered|closed|abandoned`), resolution, and the ask-economics
   fields: `unlock` (required for kind=ask), `human_cost`, `value_ref` (FK →
   value_log, required for kind=ask).
2. **`curiosity_value_log` table** — id, mission_id, statement, evidence
   (wiki slug / artifact link — required), delivered_at, linked_ask_id
   (nullable).
3. **Tools** (auto_approve unless noted):
   - `loop_open(kind, statement, who, unlock?, human_cost?, value_ref?)`
   - `loop_close(id, status, resolution)` — `abandoned` REQUIRES a resolution
     (the stated reason the owner sees).
   - `loop_list(status?)`
   - `value_log_add(statement, evidence, linked_ask_id?)`
4. **Enforcement inside `loop_open` (the law's teeth — errors steer the model
   mid-turn, message text matters):**
   - kind=ask and an ask already open → reject: "One ask at a time — close
     loop #N first (the I-need slot is single)."
   - kind=ask and no value_log entry newer than the last CLOSED ask → reject:
     "Deliver value first, then ask — log the win with value_log_add and ride
     it."
   - kind=ask and missing `unlock` or `value_ref` → reject naming the missing
     field.
5. **Nudge ladder** — `next_nudge_at` computed at open (+2d), advanced on each
   nudge (+5d, then weekly); `nudge_count` increments; ladder pure-function so
   it is unit-testable without time mocking (takes `now` as arg).
6. **Wiki mirrors** — `[[open-loops]]` (open + recently closed, with
   waiting-since and nudge count) and `[[value-log]]` (receipts, newest
   first); seeded by `_seed_wiki_stubs`; write-through on every mutation.
7. **Daily-trigger prompt hook** — `DAILY_RESEARCH_TARGET` gains **step 0,
   loop patrol** (text only; full prompt rework is 9C): list loops past
   `next_nudge_at` → act on each BEFORE new research (re-ask rephrased naming
   the blocked goal / try connected channel / propose a default / close with
   explicit assumption); **unused-grant check**: an answered ask whose grant
   has no value_log payoff yet must be used and shown TODAY.

## Implementation steps

1. models.py: both tables (+ additive migration guard).
2. `loops.py`: store, ladder function, four tools, enforcement rules,
   mirror renderers; Plan-changes note (9A helper) on ask drop ("no longer
   needed because …").
3. `research.py`: splice step 0 into `DAILY_RESEARCH_TARGET`.
4. on_load: register tools; seed mirrors on upgrade like 9A.

## Tests

- Loop round-trip per kind; abandoned-without-reason rejected.
- Ladder: open→+2d, first nudge→+5d, then weekly; pure-function cases.
- **Second concurrent ask rejected with the steering message.**
- **Ask with no fresh value_log rejected; accepted after `value_log_add`;
  the "newer than last closed ask" boundary exact** (S1's value-before-ask,
  structurally).
- `unlock`/`value_ref` required for asks; not required for other kinds.
- Mirrors write through; `[[value-log]]` shows evidence refs verbatim.
- `DAILY_RESEARCH_TARGET` contains patrol step 0 + unused-grant text.
- Upgrade path: 0.6.0 mission gets both mirror stubs on load.

## Exit criteria

- Unit suite green (existing + new).
- Dev Luna: open a question loop in chat → `[[open-loops]]` updated same
  turn; attempt two asks → second visibly rejected and the agent's reply
  reflects the steering message; `value_log_add` then ask → accepted.

## Non-goals here
Full prompt surgery (9C), behavioral verification (9D), any core changes.
