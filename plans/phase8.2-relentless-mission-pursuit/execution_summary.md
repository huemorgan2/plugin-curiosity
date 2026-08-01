# Phase 8.2 execution summary — relentless mission pursuit

**Shipped:** plugin-curiosity **0.6.0** (with 8.1, one artifact), commit
`9b9e302`, published to marketplaces.com.ai (sha-verified).

## What landed vs the plan

All six mechanisms:
- **A. Goal ledger** — `curiosity_goals` table, `goals.py` store +
  `goal_set` / `goal_update` / `goal_list` (auto_approve), kickoff step 5
  commits 2-3 goals, `DAILY_RESEARCH_TARGET` starts from `goal_list`,
  `[[mission-goals]]` wiki mirror written through on set/update.
- **B. Bias to action** — kickoff, daily share, weekly review all END with
  **Next move** ("say go and I'll do it" / "already scheduled"); mission
  fragment rewritten librarian → operator, both branches.
- **C. Capability-gap scan** — kickoff + weekly review run
  `marketplace_search` behind feature-detection; propose installs only,
  never install uninvited.
- **D. Weekly review** — `review.py` `WEEKLY_REVIEW_TARGET`;
  `curiosity-weekly-review` trigger (monday 09:30) added to
  `_sync_schedules` (idempotent, spec-drift repaired); comms `kind="review"`
  exempt from the routine daily cap; stalled-2+-weeks confrontation rule.
- **E. Louder daily presence** — "work quietly" removed; default flipped to a
  one-line goal-cited progress note; 1/day cap unchanged.
- **F. Outbound reach** — reach check (wa_status / connector_list_connected)
  in kickoff + weekly audit; unconnected → the review's single **I need** ask
  becomes a connect/install ask; connected-channel rails + guardrails
  (owner-only, quiet hours, no third parties).

## Verification

- Plugin suite 58 passing (ledger round-trip, wiki write-through, schedule
  sync incl. weekly, review cap exemption, prompt-content assertions).
- Local dojo walkthrough 9/9 (fresh Luna): mission adopted same-turn; kickoff
  artifact with **My goals** + **Next move**; 3 goals in the ledger;
  [[mission-goals]] mirrored; all three triggers registered with weekly
  "every monday at 09:30".
- Production e2e (`walkthrough-prod.mjs`): fresh Luna wired to the PRODUCTION
  scheduler (luna-scheduler.onrender.com, disposable account
  `curiosity-phase8-e2e`, cloudflared tunnel), real 0.6.0 artifact installed
  at runtime from marketplaces.com.ai; triggers verified on the production
  scheduler via the HMAC account API and the weekly review live-fired with
  run-now through the tunnel.

## Learnings

1. **Structural mechanisms survive; prompt-only ones need live proof.** The
   ledger, wiki mirror, and triggers (A, D) verified trivially. The
   prompt-only pieces (B, E) had to be proven behaviorally in the dojo — the
   artifact really ends with Next move, goals really get committed same-turn.
   Unit prompt-content assertions catch regressions but not compliance.
2. **Same-turn adoption is reliable.** mission_set fired in the very turn the
   owner stated the mission, every run — the 8.1 primacy work is what makes
   the mission statement land as an instruction rather than smalltalk.
3. **Trigger spec-drift repair earns its keep on upgrades** — on-load
   `_sync_schedules` reached the existing mission with the new weekly trigger
   without waiting for a mission_set (the exact upgrade path 0.5.x owners
   will take).
4. **Kickoff-artifact checks need generous timeouts** (10 min poll): the
   kickoff turn does real research + goal commits; dojo checks that poll the
   goal ledger and artifact text must not race it.
5. **Production scheduler hygiene:** enumerate accounts before creating;
   disposable e2e accounts must be deleted immediately after the run — an
   abandoned account's retry ladder (30 s → 1 h) spams a dead tunnel for
   ~2.7 h per fire.

## Deviations from plan

- Version 0.6.0 shipped once for 8.1+8.2 (plan assumed separate 0.5.0/0.6.0).
- 8.1 executed first, so Phase B's fragment surgery was rebased on the 8.1
  missionless text as the plan anticipated.
