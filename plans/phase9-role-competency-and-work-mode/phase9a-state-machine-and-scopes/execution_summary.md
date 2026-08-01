# Phase 9A — Execution summary

**Status: complete.** Unit suite 84/84 (11 new scope tests). Live-verified on a
fresh dev Luna (:8001, `luna_fresh9a`) with a naive-owner persona.

## What was built

- `models.py`: Mission gained `agent_phase` (setup|work), `phase_entered_at`,
  `setup_stage` (S0–S5). New tables `curiosity_scopes` (7 kinds, status both
  directions legal) and `curiosity_plan_changes` (append-only log).
  `apply_additive_migrations(conn)` ALTERs missing mission columns with
  DB-side defaults — `create(checkfirst=True)` alone never upgrades a 0.6.0 DB.
- `scopes.py` (~490 lines): `ScopeStore` (add/update/list/stage_set/phase_set/
  plan_change_add), `render_charter_page` ([[role-charter]] with
  `**Stage: Sx — phase: y**` marker line, scopes grouped by kind with
  ⬜🟡✅ marks + evidence, dated Plan-changes section), `ensure_charter_mirror`
  (upgrade seam), `register_tools`: `scope_set` / `scope_update` /
  `scope_list` / `stage_set` / `plan_change_note` (auto_approve) +
  `phase_advance` (gated).
- `phase_advance` handler enforces: no-scopes error, competency gate naming
  the first blocking scope, explicit `waive=[ids]` recorded per scope in
  Plan-changes, `to='setup'` always allowed with reason logged.
- Wiring: on_load runs the migration, registers tools, seeds the charter
  mirror for pre-9A missions.

## Live verification (naive persona, pottery-studio owner)

- Vague opener → agent proposed a mission, chartered 6–7 scopes across kinds
  unprompted, charter mirrored same-turn with stage marker.
- Owner pivot ("classes are full… it's the online shop that's dead") →
  `mission_refine` + `plan_change_note` + scope updates in one turn; the
  Plan-changes entry cites the owner's words. Realignment confirmed.
- Naive graduation pushes ("just run it yourself", "switch yourself over") →
  agent REFUSED twice, explaining it knew nothing yet — the talented-hire law
  transferred from tool descriptions alone, before any 9C prompt surgery.
- Info + explicit skip ("i don't care about the rest of the list, skip it") →
  `phase_advance(to=work, waive=[5 ids])`, graduation landed, five
  per-scope waiver entries logged with a reasoned justification each.
- Approval-card parking proven in BOTH directions after the policy fix:
  card parks the turn, phase frozen while parked, flips only on approve.

## Bugs found and fixed

1. **`policy="ask"` does not exist.** The core's dispatch gate knows
   `auto_approve | prompt_first_time_only | prompt_always | block`; an unknown
   string is silently ungated — first graduation fired with NO owner card.
   Fixed to `policy="prompt_always"`, `risk_level="medium"`. Rule: never
   invent a policy string; check `luna/plugins/base.py`.
2. **`routes.py` startup-hook call site starves the on-load work.** Under
   uvicorn the surviving `schedule_on_load_work` call is the one in
   `routes.register_routes`'s startup hook — it still passed only
   (ctx, store, reflections), so charter/loop mirror seeding silently never
   ran even though `on_load` passed the stores. Any future param added to
   `schedule_on_load_work` MUST be added at BOTH call sites.
3. **Approvals API path**: `/api/approvals` returns the SPA (HTML, 200).
   The real API is `GET /api/p/plugin-approvals/?status=pending`,
   `POST /api/p/plugin-approvals/{id}/approve`.

## Deviations from plan

- Added `curiosity_plan_changes` as its own table (plan implied charter-page
  text only) — append-only integrity and clean rendering.
- Onboarding-vs-mission tension (8.1B known): with a vague opener the agent
  ran the onboarding checklist first; mission landed one turn late. Not a 9A
  defect; 9D persona script should tolerate a one-turn lag.

## Changes applied to future phases

- 9D: graduation leg must be scripted as info-then-insist (a correctly
  behaving agent refuses naive "just switch" pushes) and must approve the
  phase_advance card via `/api/p/plugin-approvals/`.
- 9D: expect `risk_level=medium` on the graduation card.
