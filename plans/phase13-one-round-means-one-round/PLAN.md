# Phase 13 — One round means one round (intake idempotence + the onboarding stack)

Trigger: production incident (marketplace agent `vaselin-shiran-personal-trainer`,
2026-08-01, same conversation as phase12's). The owner stated the mission and
the agent asked its discovery questions TWICE — two consecutive assistant
messages, each ending in a `mission_draft` call, the second a reworded
superset of the first. Root causes, all shipped behavior in ≤0.20.0:

1. **`mission_draft` is silently idempotent.** A repeat call returns the
   existing draft with the SAME steering text — *"ask your ONE round of
   discovery questions … in this same reply"* — so the model that emitted its
   questions alongside the first call reads the tool result as an unmet
   order and asks again. The one-round cap is the one intake contract that
   stayed prose-only; phase11's closing doctrine ("flows belong in the tool
   layer — gates won first try, every time") never reached it.
2. **Prompt assembly is draft-blind.** The intake instruction lives in five
   places (gate flow, reduced state block, missionless drive fragment, tool
   schema, tool result) and none is conditioned on a draft existing —
   `prompt_sections` / `_occupy_prompt` / `rewrite_onboarding_addendum`
   never read the draft table. Every re-entry re-presents "capture + ask".
3. **On hosted cores the onboarding rewrite never fires — and the drive-slot
   swap makes it worse.** Production luna (0.55.000) emits the onboarding
   addendum as a plugin section stamped `plugin-onboarding`; no caller feeds
   the `core.onboarding` slot, so `_occupy_prompt`'s rewrite matches nothing
   and the PRISTINE one-question-at-a-time checklist survives in full. The
   claim path then swaps our fragment into `core.drive` — EARLY in the
   prompt — while the untouched checklist sits near the end, where the 025
   QA showed recency wins. Two contradictory interview motions, ours in the
   losing seat. (The hook contract forbids rewriting a foreign source —
   a violation reverts our whole diff — so the rewrite cannot simply also
   match `plugin-onboarding`.)
4. **The setup gate still speaks the pre-11.001 contract.**
   `UPDATE_SELF_DESC_GATED` / `_LOCKED_FIELD_ERROR` / `_LOCKED_COMPLETE_ERROR`
   order "mission_set the moment their message states the work … no
   confirmation round" — the exact opposite of the draft-first flow, live in
   the tool schemas the whole time.

## Changes

- **mission.py — `MissionStore.draft()` reports pre-existence.** The
  returned dict gains `already_existed` (False on create, True when the
  oldest-wins row was already there). Oldest-wins semantics unchanged.
- **mission.py — `mission_draft` repeat → tool-layer refusal.** `_draft`
  branches on `already_existed`: the repeat call returns
  `{"already_drafted": True, ...}` with steering that says the round is
  SPENT — never ask again; save on engagement, handle detours, send an
  already-written reply unchanged. The first-call `next` text drops the
  unconditional "ask your questions in this same reply" for wording that
  tolerates questions already emitted before the call ("if your reply
  already contains them, send it as is — never repeat or expand").
- **mission.py + __init__.py — draft-aware prompt assembly.** While
  missionless, `prompt_sections` fetches the draft; `prompt_fragment` gains
  a `draft` param — with a draft the missionless fragment flips from
  "capture + ask one round" to "words captured, round spent: next on-topic
  message saves with mission_set; impatience saves now; detours never save".
  Same flip inside the claimed-addendum path: `rewrite_onboarding_addendum`
  and `_mission_gate_state_block` gain `has_draft`, rendering a drafted
  stage (no capture step, no question round, `mission_set` + `update_self`
  as the only tools) instead of the ask stage.
- **__init__.py — hosted stacking fix.** `_occupy_prompt`: while missionless,
  if no `core.onboarding` section exists but a `plugin-onboarding` one does
  (hosted core shape), skip the drive-slot swap and fall through to the
  legacy `_reorder_prompt` placement — own sections moved to immediately
  AFTER the addendum, the exact recency strategy the 025 QA validated.
  Claim cores that do stamp `core.onboarding` keep the swap + in-place
  rewrite; mission-present behavior unchanged.
- **setup_gate.py — the gated vocabulary joins the draft-first contract.**
  `UPDATE_SELF_DESC_GATED`, `_LOCKED_FIELD_ERROR`, `_LOCKED_COMPLETE_ERROR`
  rewritten: capture with `mission_draft` if not yet captured, one bounded
  round may already be spent, save with `mission_set` + `update_self` on the
  next on-topic message — never a fresh question round, no "save AS STATED —
  no confirmation round" anywhere.

Out of scope, tracked for luna core (companion change, separate repo/deploy):
route `plugin_onboarding`'s addendum through the `core.onboarding` slot (or
add `plugin-onboarding` to `CLAIMABLE_SOURCES`) so the consented claim
curiosity already declares becomes real on hosted cores — then the reorder
fallback here becomes dead code and the rewrite path serves everywhere.

## Testable units

| # | Unit | Test |
|---|---|---|
| 1 | Repeat draft refuses | first `mission_draft` → no `already_drafted`, steering tolerates pre-written questions; second call → `already_drafted: True`, "round is spent" steering, draft unchanged, oldest still wins |
| 2 | Draft-aware fragment | `prompt_fragment(None, draft=...)` says round spent / save next, never "ask"; `prompt_fragment(None)` keeps the ask; drafted fragment still carries rails + load_tools note |
| 3 | Drafted addendum stage | `rewrite_onboarding_addendum(has_draft=True)` on a gate-stage addendum: no capture/ask instructions, tools line is `mission_set` + `update_self` only; `has_draft=False` unchanged from 0.20.0 |
| 4 | Hosted stacking | missionless + `plugin-onboarding` section + no `core.onboarding` → drive slot untouched, own section sits immediately after the addendum; with `core.onboarding` → swap + rewrite as today; mission present → swap only, both shapes |
| 5 | Gate vocabulary | gated update_self/complete_setup descriptions + locked errors carry draft-first wording; "no confirmation round" is gone |
| 6 | prompt_sections wiring | missionless with a stored draft → drafted fragment emitted (integration through the real store) |

## Regression gate

Full pytest suite green (intake/slot-occupancy/prompt suites updated where
they asserted the 0.20.0 shapes).

## Version

plugin-curiosity **0.22.0** (behavior change; no schema migration —
`already_existed` is computed, not stored). All three stamps (pyproject,
luna-plugin.toml, manifest). Originally planned as 0.21.0; that number was
claimed and published mid-execution by the NOC-removal release
(`0.21.0: remove the Operational dashboard`), and published versions are
immutable, so phase13 ships as 0.22.0.

## Exit

`execution_summary.md`; commit + tag + push plugin repo; package + publish
0.22.0 to marketplaces.com.ai.
