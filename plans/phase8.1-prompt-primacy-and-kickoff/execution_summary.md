# Phase 8.1 execution summary — prompt primacy + install kickoff

**Shipped:** plugin-curiosity **0.6.0** (8.1 + 8.2 shipped together, one
version instead of the planned 0.5.0), commit `9b9e302`, published to
marketplaces.com.ai (sha-verified). Core side: luna 0.33.001 (`06c7f11`,
plan 025 — see its execution_summary.md).

## What landed vs the plan

- **Phase A (core hook)** — executed as luna plan 025.
- **Phase B (primacy consumer)** — `_reorder_prompt` at priority 60,
  feature-detected via `getattr(ctx, "hooks", None)`. **Deviation from plan:**
  the plan said move BEFORE the onboarding addendum; shipped behavior moves
  the curiosity section to immediately AFTER it (see learning 1). Missionless
  only; with a mission set, order untouched; no onboarding section → no-op.
- **Phase C (install kickoff)** — `install_kickoff_sent` flag row; kickoff
  sent from `schedule_on_load_work` when missionless + flag unset +
  `send_muted_message` present. Flag burns only after a DELIVERED send;
  mission-present installs burn it as `"skipped: mission present"`. Two
  hardening pieces the plan didn't anticipate: an in-process claim
  (`_kickoff_claimed`, atomic check-and-set) and drain→sleep→send ordering
  (see learnings 3-4).
- **Phase D (verify + ship)** — dojo `curiosity-phase8/walkthrough.mjs` 9/9
  on a fresh Luna (3 runs, 3 live bugs found and fixed), then a production
  e2e (`walkthrough-prod.mjs`): fresh Luna without curiosity in-tree, runtime
  install of the real 0.6.0 artifact from marketplaces.com.ai, kickoff landing
  WITHOUT restart, triggers on the PRODUCTION scheduler
  (luna-scheduler.onrender.com) through a cloudflared tunnel.
- Tests: 58 passing in the plugin suite, including new
  `test_prompt_primacy.py` (v2, after-onboarding semantics) and kickoff
  concurrency/claim-release tests.

## Learnings (each found live, not by unit tests)

1. **Primacy is not "earlier".** The onboarding addendum is a
   plugin-onboarding `prompt_sections()` section near the END of the prompt.
   QA run 1: fragment moved before core.personality → the greeting still ran
   the checklist (missionIdx way after nameIdx). At the end of a long prompt
   recency wins, so the override must sit immediately AFTER the section it
   contradicts — and say so explicitly ("this OVERRIDES its ordering ... your
   very FIRST question is the mission"). Run 3 result: missionIdx=628,
   nameIdx=-1 — the checklist deferred entirely.
2. **An explicit algorithm beats generic prose.** ONBOARDING_FLOW's "pick the
   next REQUIRED missing item" is a checklist the model executes faithfully;
   beating it required position + explicit override language. Persuasive
   framing alone (0.4.3 lesson) and position alone (run 1) both lost.
3. **on_load work runs twice per boot under `luna serve`** — once on a
   throwaway bootstrap loop, once on the serving loop. The two runs
   interleaved inside the send-then-flag window and posted the kickoff twice.
   Fix: module-level claim with no await between check and set; released only
   on failed send so a later load retries.
4. **A cancelled task can half-complete a side effect.** Run 2: the
   bootstrap-loop task won the claim, inserted the muted message, and was
   cancelled mid-send at loop teardown — moment posted, no reaction, no flag.
   Fix: sleep BEFORE the send (`SYNC_ON_LOAD_DELAY_S`), so the doomed task is
   cancelled harmlessly in the sleep and only the serving-loop task reaches
   the send. General rule: in on-load tasks, put the delay before the side
   effects, not after.
5. **The messages API flattens `extra.*` to top-level fields** (`title`,
   `kind`, `source`); `m.extra` is null in payloads. Dojo matchers must read
   `m.title`.
6. **The no-restart path matters and works.** On a runtime marketplace
   install the serving loop is already up and a conversation exists — the
   kickoff lands ~15 s after install with no restart. This is the actual
   hosted-tenant UX, and only the production e2e exercised it.

## Deviations from plan

- Version 0.6.0 (combined with 8.2), not 0.5.0.
- Reorder direction: after-the-addendum, not before (learning 1).
- Fallback "before the personality block" dropped — with no onboarding
  section, appended-at-end already has maximal recency; moving it is
  counterproductive.
