# 10.005 — Mission-first onboarding (curiosity out of the door)

## Goal
A fresh agent with curiosity installed asks for its MISSION as the very first
setup question — before name/emoji — and saves it to both the curiosity
mission store and the identity checklist in the same turn. No duplicate
mission asks (onboarding + install kickoff), no contradicting flows.

## Why now (034 layers)
Core 0.34.018 gave plugins Tier-1 prompt-slot claims (`prompt_overrides`).
Curiosity 0.9.7+ already claims `core.drive` + `core.onboarding` and prepends
MISSION_FIRST_NOTE to any `core.onboarding` section. **But in production the
claim binds to nothing**: plugin_onboarding's addendum enters the prompt via
`prompt_sections()` → `source="plugin-onboarding"`, and the legacy
`onboarding_addendum` param (the only thing stamped `core.onboarding`) is
always None. The prepend silently no-ops; the checklist still says name/emoji
first and step 5 tells the agent to invent the mission itself.

## Changes

### A. luna core 0.34.019 (plan: luna/plans/036-onboarding-slot-binding)
One-line alias in `system_prompt.py` plugin_sections loop: a section
contributed by `plugin-onboarding` gets `source="core.onboarding"` (the slot
the 034 design already lists in CLAIMABLE_SOURCES / SLOT_CLAIM_MEANING as
"your agent's onboarding flow"). Now the Tier-1 claim governs the live
addendum. Unit test included.

### B. curiosity 0.9.13 (branch mission-first-onboarding off 0.9.11)
1. **Onboarding-slot rewrite** (`_occupy_prompt`, claim path): while
   missionless AND the `core.onboarding` section carries the live
   `SETUP STATE (you are not fully set up yet)` marker, REPLACE the flow
   portion with curiosity's mission-first flow, preserving the live SETUP
   STATE block verbatim (split on the header marker). Marker absent →
   keep today's MISSION_FIRST_NOTE prepend as fallback.
2. **Unified mission step**: the rewritten flow's step 1 = ask the mission
   first; when it lands, call `mission_set` AND `update_self(field='mission')`
   in the same turn — one answer feeds both the curiosity engine and the
   setup checklist. Then resume the normal checklist (name, emoji, persona,
   `complete_setup`).
3. **Kickoff suppression during setup**: `maybe_send_install_kickoff` reads
   `identity.setup_completed` (raw SQL, table may not exist on odd cores →
   proceed as today). Setup incomplete → defer WITHOUT setting
   INSTALL_KICKOFF_FLAG: onboarding owns the mission ask; the kickoff stays
   armed for the post-setup missionless case and self-cancels
   ("skipped: mission present") once the mission exists.
4. Version stamps: `__init__.py` manifest (authoritative), `pyproject.toml`,
   `luna-plugin.toml`.

### Out of scope (recommendation only — luna-service is read-only)
Bake plugin-wiki/plugin-scheduler/plugin-curiosity into the image plugin-set
(luna-service/plugin-set.toml) so "out of the door" needs no install step.

## Verification gates (before commit — user-mandated)
1. Curiosity unit suite green (new tests: slot rewrite preserves SETUP STATE,
   fallback prepend, kickoff deferral on setup_completed=false).
2. Luna unit test for the source alias green.
3. **Dojo, fresh agent**: new DB on the patched core + curiosity 0.9.13
   installed → first agent question is the mission ask; owner answers →
   mission_set + update_self both persisted; checklist resumes (name next);
   no duplicate kickoff ask.

## Ship path
Commit on branches only. No push/publish: another session has uncommitted
0.9.12 work (skill gating) in the main checkout; merge order is theirs-first,
then this branch rebased as 0.9.13.
