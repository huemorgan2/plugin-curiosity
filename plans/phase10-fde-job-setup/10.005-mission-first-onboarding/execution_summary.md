# 10.005 — mission-first onboarding: execution summary

**Goal:** a fresh agent has curiosity active with a mission ask right out of
the door.

## Shipped (on branches, not merged/pushed yet)

- **luna 0.34.019** — branch `036-onboarding-slot-binding` (luna repo):
  plugin_onboarding's live addendum section is stamped `core.onboarding`, so
  Tier-1 claims finally govern the real setup flow. Plan + summary in
  `luna/plans/036-onboarding-slot-binding/`.
- **plugin-curiosity 0.9.13** — branch `mission-first-onboarding` (curiosity
  repo, worktree): claims `core.onboarding` and REWRITES the setup flow —
  mission is the first question; the turn a mission lands has a fixed shape
  (`mission_set` + `update_self(field='mission')` before reply text); SETUP
  STATE block preserved verbatim; unknown addendum shapes fall back to the
  0.9.12-style prepend note. Install kickoff defers while setup is incomplete
  (empty identity table = setup not started) and stays armed for owners who
  finish setup missionless.

## Verification

- Curiosity unit suite: **241 passed** (new slot-rewrite + kickoff-deferral
  tests included).
- Luna suite: zero new failures vs clean main (stash-verified).
- Dojo `curiosity-10005/mission-first.mjs`, factory-fresh agent (fresh DB,
  seeded owner, setup=null, managed-dir 0.9.13 on 0.34.019): **7/7** —
  no kickoff during setup; mission asked before name/emoji; same-turn double
  save into curiosity store and identity; no mission re-ask afterwards.
  Prompt wording took 3 iterations (acknowledge-without-saving, then
  skip-the-saves); the fixed-turn-shape wording (a/b/c sequence) is what
  finally held.

## Queued for 0.9.14

The model blitzes the rest of the checklist in the mission turn (self-picked
name/persona, `complete_setup`) instead of one question per message. Identity
writes are approval-gated so the owner sees cards, but the wording brake
("the two calls are the WHOLE step") did not hold. Needs the same treatment
as the jargon fix: structural, not rhetorical.

## Merge path

1. Land the in-flight curiosity 0.9.12 (other session).
2. Rebase `mission-first-onboarding` onto it, keep version 0.9.13, re-run
   unit + dojo.
3. Merge luna `036-onboarding-slot-binding` (core-first gives full behavior;
   0.9.13 degrades gracefully on older cores).
4. Push (gh auth switch huemorgan2) + publish to marketplaces.com.ai.
