# Phase 9A — Agent-phase state machine + role scopes (structural core)

**Parent:** [../PLAN.md](../PLAN.md) — mechanisms A (state machine) and B's
structural spine (scopes + charter mirror). No prompt behavior changes here;
this step is pure structure and is independently testable.

**Depends on:** plugin-curiosity 0.6.0 (goal ledger, wiki mirrors, schedules).
**Blocks:** 9B (loops reference scopes), 9C (prompts branch on phase/stage).

---

## Deliverables

1. **Phase state** — `setup | work` + `entered_at` + setup-arc stage marker
   (`S0..S5`, the furthest *ratified* stage).
   - Storage: columns on the existing mission row (one active mission — no new
     table needed): `agent_phase` (default `"setup"`), `phase_entered_at`,
     `setup_stage` (default `"S0"`).
   - Migration: additive columns, defaults applied to existing missions on
     upgrade (spec-drift-safe like `_sync_schedules`).
2. **`curiosity_scopes` table** — id, mission_id, kind, name, why, status
   (`missing|in_progress|competent`), evidence, updated_at.
   - Kinds (enum, validated): `knowledge`, `people`, `communication_paths`,
     `tools_data_access`, `workflow_approval`, `playbooks`,
     `routines_feedback`.
3. **Tools** (auto_approve — self-bookkeeping, own tables only):
   - `scope_set(kind, name, why)` → creates `missing`.
   - `scope_update(id, status?, evidence?, why?)` — **both status directions
     legal** (`competent → in_progress` is the refix-backward path).
   - `scope_list()` → all scopes with status, for prompt targets.
   - `stage_set(stage)` → advances/regresses the setup-stage marker.
   - `phase_advance(to)` → **approval-gated (NOT auto_approve)**: `to="work"`
     enforces the competency gate (reject if any scope not `competent` unless
     `waive=[ids]` explicitly passed — waivers recorded in the charter);
     `to="setup"` always allowed (regression path).
4. **`[[role-charter]]` wiki mirror** — seeded by `_seed_wiki_stubs`; written
   through on every scope/stage/phase change (same pattern as
   `[[mission-goals]]`). Layout: stage marker line on top → role statement →
   scopes grouped by kind with status/evidence → **Plan changes** section
   (dated, append-only: added/dropped/reopened + the learning that caused it).
5. **`charter_log(entry)` helper** (internal, called by tools; also exposed as
   auto_approve tool `plan_change_note`) — appends a dated Plan-changes entry.

## Implementation steps

1. models.py: mission columns + `Scope` table + migration-on-load guard.
2. `scopes.py`: store + the five tools; write-through renderer for
   `[[role-charter]]` (reuse goals-mirror rendering helpers).
3. Wire into `__init__.py` on_load: register tools, seed charter stub when a
   mission exists and the page is absent (upgrade path).
4. `phase_advance` approval policy: register with `ask` policy (the owner
   click IS the graduation approval — no new core surface).

## Tests (extend the existing suite)

- Scope round-trip per kind; invalid kind rejected.
- `competent → in_progress` regression legal; evidence preserved.
- Gate: `phase_advance(to="work")` rejected with non-competent scopes; allowed
  with all competent; allowed with explicit waivers, waiver text lands in the
  charter; `to="setup"` always allowed.
- Stage marker: `stage_set` renders at the top of `[[role-charter]]`.
- Plan-changes: `plan_change_note` appends dated entries, order preserved.
- Upgrade path: existing 0.6.0-shaped mission row gets defaults + charter stub
  seeded on load (no mission_set required) — mirrors 8.2's spec-drift lesson.
- Mirror write-through on every mutation (assert page body content).

## Exit criteria (testable, no LLM in the loop)

- All new unit tests green; existing 58 stay green.
- On a dev Luna: `scope_set`/`scope_update`/`stage_set` from chat round-trip
  and `[[role-charter]]` reflects each change within the same turn;
  `phase_advance` produces an approval card and does nothing until approved
  (approval gates park turns — dojo/API approval, per memory).

## Non-goals here
Prompt content (9C), loops/asks (9B), any behavioral/dojo assertions (9D).
