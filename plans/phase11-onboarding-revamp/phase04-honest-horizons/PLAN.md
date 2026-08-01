# Phase 04 — Honest horizons (11.003 / M3)

Time in honest units: agent-minutes, unlocks, real dates only when real.

## Changes

- **models.py:** `Goal` + `horizon_kind` {agent_minutes, awaiting_approval,
  on_unlock, date, rhythm} + `horizon_ref`; migration maps existing
  `target_date` → kind `date`.
- **goals.py:** delegation passes date/rhythm through; on_unlock surfaces
  blocked-on-loop, never overdue. `compute_pace` names the unlock + 5-min
  human cost; agent lanes date-free.
- **prompts.py:** unit laws (no human-rhythm durations; waits phrased by
  unlock + whose move; honest range). OWNER_WORDS extended.
- Kickoff milestone mandate emits typed horizons.

## Testable units

| # | Unit | Test |
|---|---|---|
| 1 | Typing + migration | unit: old rows readable, mapped to `date`; new kinds validate; `date` requires real-date source |
| 2 | Delegation | `test_goals_delegation.py` extended: kinds map to goalseek correctly |
| 3 | Never overdue on unlock | unit: on_unlock goal renders blocked-on-loop |
| 4 | Pace blame | unit: pace reason names unlock + human cost |
| 5 | Prompt law | prompt test: banned duration phrases absent from generated JD/kickoff templates |
| 6 | Live wording | dojo: ask "when will X be done" → answer in agent-minutes/unlock, never "3–5 days" |

## Regression gate

`test_goals*.py`, migration tests, full suite. Dojo unit 6.

## Version

plugin-curiosity 0.15.0 (schema).

## Exit

`execution_summary.md`; learned horizon distribution (how many goals are
truly dated?) feeds phase05 "What happens when" lane design.
