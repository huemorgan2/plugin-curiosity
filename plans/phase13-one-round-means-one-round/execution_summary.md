# Phase 13 — execution summary

**Shipped: plugin-curiosity 0.22.0** (2026-08-01). Incident response: the
marketplace agent `vaselin-shiran-personal-trainer` asked its discovery
questions, called `mission_draft` again on the owner's silence-adjacent next
turn, read the idempotent result's "ask your questions in this same reply"
steering as an unmet order, and asked a reworded superset of the same
questions — two consecutive "Mission draft" bubbles, five questions for a
two-question budget. Four root causes, all closed in the tool/prompt layer.
(Planned as 0.21.0; that number was claimed mid-execution by the published
NOC-removal release, so phase13 ships as 0.22.0.)

## What changed

1. **The repeat `mission_draft` call now refuses** (`mission.py`).
   `MissionStore.draft()` reports pre-existence (`already_existed`,
   computed — oldest-wins unchanged, nothing stored). The tool handler
   turns a repeat call into `{already_drafted: true, ...}` whose `next`
   says the round is **SPENT**: do NOT ask, do NOT repeat or expand
   questions already written; if the owner engaged the thread, save NOW
   with `mission_set`. The first-call steering now tolerates questions
   written before the call ("send that reply AS IS — never repeat, reword,
   or expand a question round") — this kills the text+call → result
   re-orders → ask-again loop at its source.

2. **Prompt assembly is draft-aware** (`mission.py`, `__init__.py`). With a
   captured draft and no mission, every surface flips from ask-stage to
   save-only: `prompt_fragment(..., draft=...)` renders a SPENT/save-only
   fragment carrying the owner's verbatim words; new
   `MISSION_GATE_FLOW_DRAFTED` and the drafted `_mission_gate_state_block`
   variant replace the capture/ask vocabulary ("never call `mission_draft`
   again"); `rewrite_onboarding_addendum(..., has_draft=...)` picks the
   drafted flow. Impatience-overrides, DETOUR, the `load_tools` hop, and
   the action rails all survive both variants.

3. **Hosted-core shape handled** (`__init__.py::_occupy_prompt`). Production
   cores emit the onboarding addendum as `source="plugin-onboarding"` —
   nothing ever feeds the `core.onboarding` slot, so curiosity's rewrite
   never fired and the drive-slot swap parked the fragment early, where it
   loses to the checklist's recency (025 QA). Missionless on that shape now
   takes the validated legacy reorder placement (fragment immediately AFTER
   the addendum) instead of swapping; mission-present still swaps. The
   proper fix — luna-core routing the addendum through `core.onboarding`
   (or adding `plugin-onboarding` to CLAIMABLE_SOURCES) — is documented in
   PLAN.md as the out-of-scope core companion change.

4. **Setup-gate vocabulary joins the draft-first contract**
   (`setup_gate.py`). `UPDATE_SELF_DESC_GATED` and both locked-error hints
   still spoke the pre-11.001 "save AS STATED — no confirmation round"
   contract, ordering the opposite of the intake flow. They now speak
   draft-first: capture verbatim → at most ONE bounded round *and only if
   it was not already asked* → save on the next ON-TOPIC message — "never
   a fresh question round".

## Verification

Full suite: **548 passed** (`pytest -q`). New/updated coverage:
- `tests/test_phase13_one_round.py` (new, 15 tests): store pre-existence
  flags and `draft_get` shape; repeat tool-call refusal (first call says
  "AS IS"/"never repeat", repeat says SPENT/"Do NOT ask"/`mission_set`,
  server state unchanged); drafted vs ask variants of the fragment, state
  block, addendum rewrite, and gate flow; `prompt_sections` through the
  real store emits the drafted fragment; gated descriptions/errors carry
  the draft-first wording and have lost "AS STATED"/"no confirmation
  round".
- `tests/test_slot_occupancy.py`: hosted missionless reorders instead of
  swapping (drive untouched, foreign addendum never rewritten); hosted
  mission-present still swaps; claimed core with a draft renders the
  drafted stage.
- `tests/test_phase_10006.py`: the gated-description assertion updated
  from the removed "AS STATED"/"no confirmation round" wording to the
  draft-first contract.

## Follow-up (out of scope, documented in PLAN.md)

luna-core: route the onboarding addendum through the `core.onboarding`
slot (or extend CLAIMABLE_SOURCES with `plugin-onboarding`) so claim-based
rewriting works on hosted cores; needs a core release + image rebuild.
Until then the reorder path above is the production behavior.
