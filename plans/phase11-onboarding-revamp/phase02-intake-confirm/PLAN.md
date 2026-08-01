# Phase 02 — Intake & confirm (11.001 / M1)

Draft-first intake, one bounded discovery round, reflect-back, confirmation
gate, kickoff split. Depends on phase01 (first-turn direction).

## Changes

- **models.py:** `MissionDraft` (verbatim, created_at); `Mission` +
  `origin_statement`, `confirmed_at`. Migration additive.
- **mission.py:** tools `mission_draft`, `mission_confirm`; `mission_set`
  accepts `origin_statement`. 24 h draft reaper (convergent, keeps oldest).
- **prompts.py:** MISSION_GATE_FLOW rewrite — draft instantly → max 2–3
  questions in ONE round (non-inferable, plan-changing, possibility lesson)
  → next turn ALWAYS saves with reflect-back → impatience saves now.
- **engine.py:** kickoff split — instant brief (~3 s: restatement,
  first-look, "3 things I could do for you"); deep pass gated on
  `confirmed_at` / "go" / 12 h timeout-proceed with a note. Kickoff goal
  mandate → 3–5 milestones (dated-goal mandate removed; typed horizons in
  phase04).

## Testable units

| # | Unit | Test |
|---|---|---|
| 1 | Draft never loses words | unit: draft stored verbatim on first turn; set uses sharpened + origin |
| 2 | One-round cap | prompt test + dojo: second question round impossible; impatience → immediate save |
| 3 | Reaper | unit: 24 h stale draft → saved verbatim on next contact; concurrent-safe |
| 4 | Confirm gate | unit: `confirmed_at` unset until `mission_confirm`; overview shows "waiting for your yes" |
| 5 | Kickoff split | unit: instant brief fires ≤ handful of calls; deep pass blocked pre-confirm, runs on confirm/go/timeout; announced first |
| 6 | Live flow | dojo: full missionless→confirmed→brief→deep run; approve pending approval cards via API |

## Regression gate

`test_mission*.py`, `test_kickoff.py`, `test_prompt_primacy.py`,
`test_phase_10001-6` updated-and-green; full suite green; dojo unit 6 twice.

## Version

plugin-curiosity 0.13.0 (schema addition). All three stamps.

## Exit

`execution_summary.md`: shipped, tests, learnings (esp. question quality and
timeout defaults) → adjust phase03 veto windows if intake showed different
owner patience than assumed.
