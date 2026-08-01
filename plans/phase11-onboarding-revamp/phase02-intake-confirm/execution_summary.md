# Phase 02 — intake & confirm: execution summary

**Status: shipped.** Curiosity 0.13.0 (plugin-only phase — no luna core change).

## What changed

### A. Verbatim intake (MissionDraft)
- `models.py`: new `MissionDraft` table (verbatim, created_at); `Mission` gains
  `origin_statement` + `confirmed_at` (additive migration; columns asserted in
  `test_scopes.py`).
- New tool `mission_draft(verbatim=...)` — captures the owner's words EXACTLY on
  the turn they state a mission, before any reply text. Oldest draft wins;
  `mission_set` consumes every draft and auto-fills `origin_statement` from the
  oldest when the model doesn't pass one (explicit origin wins).
- 24 h draft reaper (`reap_stale_draft`): a dead conversation must not orphan the
  owner's words — the draft promotes VERBATIM through the FULL `mission_set` tool
  handler (identity write-through, wiki bind + stubs, schedules, brief). Runs
  from on-load work and per-turn fire-and-forget; concurrent calls converge.

### B. The confirm gate + kickoff split
- `mission_set` no longer fires the deep S0→S2 pass. It spawns an INSTANT BRIEF
  (fast first-look moment, `BRIEF_TOOLS` scoped) and the deep pass waits for
  `mission_confirm` — or proceeds by default after 12 h with a no-guilt timeout
  note ("you never replied … proceeding by default").
- Once-per-mission guard: in-process `_deep_claims` set + persisted Flag
  `deep_kickoff_started:<mission_id>` ("started"/"grandfathered"). Grandfather
  guard: a pre-split mission past S0 (or in work phase) NEVER re-fires the deep
  pass on upgrade.
- Confirm-gate surfaces (agent confirm line, owner-pane "waiting for your yes" +
  needs_from_you entry) show ONLY at the gate — same S0 condition as the
  janitor (`setup_stage in (None,"S0") and agent_phase != "work"`), in BOTH
  `prompt_fragment` and `overview.py`.

### C. One-round intake flow (MISSION_GATE_FLOW rewrite)
- Fixed turn shapes: mission words → `mission_draft` FIRST, then ONE round of AT
  MOST 2-3 plan-changing questions; the owner's NEXT message ALWAYS ends intake
  (`mission_set` + `update_self`, never a second round); IMPATIENCE OVERRIDES
  EVERYTHING.
- Kickoff milestones mandate: 3-5 milestones with readiness colors replaces the
  dated-goal batch.

### D. Live-QA-found fix: the `load_tools` hop (the phase's big catch)
Luna core 046 tool-grouping defers `mission_set` behind
`load_tools(group="curiosity")` (static partition in `luna/agent/tool_groups.py`),
while the new `mission_draft`/`mission_confirm` are unassigned → fail-open
visible. Dojo run 1 attempt 1: the agent called `mission_draft` fine, then on the
save turn called `load_tools` + `mission_set` in the same turn — the tool schema
set is fixed for the whole model run, so `mission_set` hit an unknown tool
(EMPTY tool result, no row, no error anywhere), and the continuation turn
drifted to the naming flow. Fix: all four gate surfaces (MISSION_GATE_FLOW,
gate state block, missionless fragment, `mission_draft` steering result) now
teach the hop — load the group in the SAME turn as `mission_draft`, never call
`mission_set` in the turn that loaded it. Regression test added.

## Test results

- Curiosity suite: **365/365 pass** (29 new in `test_intake_confirm.py` + 7
  legacy spec updates + the load_tools-hop regression test).
- Prompt-budget tests caught a real bug pre-QA: the confirm line inflated the
  work-phase fragment — a grandfathered unconfirmed mission would have shown
  "waiting for your yes" forever. Fixed with the at-gate condition (§B).
- Live dojo run 1 (happy path, gemini-flash, fresh Luna on 8767): **16/16** —
  intro asks for the mission; draft VERBATIM; one round (3 questions);
  `mission_set` on the next message with origin auto-filled + drafts consumed;
  brief posted with `confirmed_at` NULL and deep flag unset; "sounds right - go"
  → `mission_confirm` stamped, deep kickoff fired exactly once.
- Live dojo run 2 (silent-owner paths, backdate + restart choreography), two
  attempts covering all 13 behaviors between them:
  - Attempt 1: draft planted, owner silent; 25 h backdate + restart → reaper
    promoted VERBATIM (statement == origin == the owner's exact words), drafts
    consumed, wiki stubs seeded, mission UNCONFIRMED, deep pass held; 13 h
    backdate + restart → timeout-proceed fired the deep pass with the no-guilt
    timeout note, flag=started; another restart did NOT re-fire. Only miss: the
    harness killed the server before the fire-and-forget brief landed (§learning
    3) — a wait bug, not a product bug.
  - Attempt 2 (proper waits): the agent preloaded the curiosity group on the
    greeting turn and saved DIRECTLY on the mission-words turn — sharpened
    statement with origin_statement auto-filled VERBATIM via draft consumption
    (the turn's message rows died with an aborted stream; the DB side effects
    persisted). Instant brief posted and answered ("What I heard…"); mission
    stayed unconfirmed; timeout-proceed + exactly-once + no-refire all held.

## Learnings → adjust later phases

1. **Core tool-grouping is part of every flow design now.** Any "the agent MUST
   call X on turn N" contract must check X against `tool_groups.py`'s partition:
   deferred tools need the load hop taught in the steering, or the flow silently
   dies with an empty tool result (no error, no log). Phases 03/05/07/08 add
   tools — either keep flow-critical ones out of the deferred partition (core
   change, phase 06 candidate) or teach the hop the way phase 02 does.
2. **An unknown-tool call returns an EMPTY tool result** — no error text, no log
   line. When a dojo run shows a tool "called" in the SSE names but no DB row,
   suspect visibility before suspecting the handler.
3. **Muted moments need generous QA waits**: fire-and-forget briefs ride
   KICKOFF_RETRY_S=90 s retries; on-load work starts at boot+15 s. Restart-based
   QA choreography must poll for rows (up to minutes), not sleep 20 s — run 2
   attempt 1's single "failure" was the harness killing the server mid-brief.
4. **Gemini-flash struggles with the long deep-kickoff turn** ("Exceeded maximum
   output retries"): the moment posts and flags converge correctly, but the S0→S2
   artifact quality needs a real reasoning model. Production runs on Anthropic
   keys are fine; don't judge kickoff content quality from gemini QA runs.
5. **SSE reply text arrives twice** (deltas + final message) — QA scripts must
   dedupe before counting anything in reply text.
6. Question quality at the gate was good across runs (platform / knowledge base /
   escalation rules — all plan-changing); the 2-3 cap held. Phase 03's next-step
   cards can trust intake output shape.
