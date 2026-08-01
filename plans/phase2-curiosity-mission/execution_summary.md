# Phase 2 — execution summary

**Status: DONE.** plugin-curiosity 0.2.0 ships the mission model + action rails; all five
acceptance criteria verified live in a headed browser (**7/7 dojo checks**), plus
plugin-curiosity pytest **9/9** and plugin-wiki regression **17/17**. No core changes.

One deliberate deviation from the plan: the tools are named **`mission_set` / `mission_refine`
/ `mission_get`**, not `set_mission`/`refine_mission`/`get_mission` — see learning #1; the
plan's name is permanently approval-gated on every Luna. Table is namespaced
`curiosity_missions` (plugin-owned tables carry the plugin prefix, per phase-0/1 convention).

## What was done

### plugin-curiosity (`plugin_curiosity/mission.py`, `models.py`, 0.2.0)
- `curiosity_missions` table: `id, statement, autonomy_rung (1–4), risk_ceiling, active,
  created_at, updated_at`. `MissionStore.set` deactivates all active rows before inserting —
  exactly one active mission, enforced in the store, unit-tested.
- Tools (all `auto_approve`, `timeout_seconds=120` on the two writers):
  - `mission_set(statement, rung=1, risk_ceiling=...)` — persists the row, write-through to
    `Identity.mission` via `config_registry.get("identity").writer(...)`, seeds the wiki
    mission hub + domain stubs via `provider_registry.get("wiki")`, registers the recurring
    schedules on plugin-scheduler.
  - `mission_refine(statement | rung | risk_ceiling)` — updates row + identity, re-syncs
    schedules; raises a clean error if no active mission (`use mission_set first`).
  - `mission_get()` — active mission + rung + ceiling.
- Schedules (`MISSION_SCHEDULES`): `curiosity-daily-research` and `curiosity-nightly-dream`,
  `action_type="agent_prompt"` with placeholder targets (phases 4/5 fill the real prompts).
  Registration is idempotent (checks `trigger_list` first) and wrapped in `_retry_tool` —
  3 attempts, 3s/6s backoff — because scheduler tool handlers return `{"error": str(exc)}`
  and the 10s scheduler-client timeout trips transiently under concurrent-turn load.
- Prompt fragment teaches the agent: the mission is native priority, the wiki is hers to
  fill, playbook_propose/playbook_run is the encouraged action path, side effects stay
  approval-gated at the current rung.
- GET `/api/p/plugin-curiosity/mission` route for inspection/UI.

### Tests
- pytest **9/9** (`tests/test_mission.py` + conftest fakes for tool_registry /
  provider_registry / config_registry seams): single-active-row, write-through payloads,
  wiki seeding, schedule idempotency + retry, refine-without-mission error, degraded modes
  (no wiki / no scheduler installed → tool still succeeds, reports what was skipped).
- plugin-wiki **17/17** regression (curiosity consumes WikiProvider).
- Dojo walkthrough (`luna/dojo/tests/curiosity-phase2/walkthrough.mjs`), headed, **7/7**:
  1. real chat turn adopts the mission via `mission_set`;
  2. structured row persists (statement + rung 2 + active) via the plugin route;
  3. `curiosity-daily-research` + `curiosity-nightly-dream` present in scheduler `triggers`;
  4. wiki hub (`mission`) carries the statement, domain stub exists;
  5. **write-through proof**: a tool-free turn quotes the mission codename from its system
     prompt (no `role='tool'` messages in the turn);
  6. `playbook_run` on a fresh playbook returns `needs_approval` (autonomy gate) and the
     agent stops — actions are rails-ready but gated;
  7. a direct `update_setting` request surfaces as a **pending approval** (observed via the
     approvals API — the turn blocks on the gate, so no chat marker is possible), then
     rejected for cleanup.
  Evidence: `dojo/results/curiosity-phase2/walkthrough/` (screenshots + checks.json).

## What was encountered / learned

1. **Reserved tool names: core's alembic `0008_approvals.py` seeds policy rows** for
   `set_mission`, `set_persona`, `update_self`, `mcp_add_server`, `mcp_remove_server`,
   `memory_forget` → `prompt_always` ("self-modification: always prompt"). Policy resolution
   is cache → exact DB row → wildcard → `ToolDef.effective_policy()`, so a **DB row beats the
   plugin's `policy="auto_approve"`** — a plugin tool named `set_mission` is permanently
   gated on every Luna, including fresh installs. Renamed to `mission_*` (also matches the
   `wiki_*`/`trigger_*`/`playbook_*` convention). **Check the 0008 seed list before naming
   any plugin tool.**
2. **Turns run *inside* the `POST /messages` SSE response** (plugin_api/app.py): client
   disconnect cancels the turn (`CancelledError`), and a **gated tool call blocks the turn
   with zero persisted messages** until approve/reject. Two consequences for walkthroughs:
   never navigate away while a turn you care about is in flight, and test `prompt_always`
   gates via the approvals API, not chat markers.
3. **Conversation title = first 60 chars of the opening message.** Any two walkthrough runs
   (or retry attempts) using the same prompt produce identical titles, so title-pinning
   matched a *stale* conversation from a previous run — check 1 false-passed against old
   data, then the script's navigation cancelled the real in-flight `mission_set` turn
   (learning #2 compounding). Fix: every send gets a fresh nonce prefix (`[#xxxx]`),
   independent of the run codename so the write-through check can't be answered by echoing
   the user message; plus a 45s send-verification bail that re-sends.
4. **Scheduler client timeout under load:** standalone `trigger_*` calls take ~0.14s, but
   during concurrent agent turns the 10s HMAC-client timeout trips transiently (episodic
   loop congestion; first-token latency up to ~2.5min was observed). `str()` of a bare httpx
   timeout is `""`, so failures surfaced as `{"error": ""}`. Handled with `_retry_tool` +
   `timeout_seconds=120` on the mission writers (default tool timeout is 30s — `mission_set`
   once died at exactly 30s mid-scheduler-retry).
5. **`playbook_run` autonomy gate is a tool *result*** (`needs_approval` +
   `current_autonomy: agent_must_confirm`), not a pending-approval row — the agent keeps
   control and can relay it. Distinct from the `prompt_always` gate, which blocks. Both rails
   verified.
6. **luna-postgres (docker) crashed into recovery mode** mid-run (backend exit 2 / signal 13
   → "database system is in recovery mode" → API 500s), self-recovered in ~2min; disk and
   memory were fine. Transient console 500s during page loads in later runs likely echo this.
   Worth watching; not caused by the plugin.
7. PlaybookDef YAML wants `name` + steps[].`kind` (not `type`) — agents self-corrected after
   one validation error each time; acceptable friction.

## Consider for the future

- **Phase 4/5 fill the placeholder trigger targets** (`agent_prompt` text for the daily
  research pass and the nightly dream). Update targets via `trigger_update`-style re-sync in
  `_sync_schedules` rather than delete/recreate, to preserve trigger history.
- Fired (scheduled) turns are muted and `chat_only` tools are unavailable in them —
  phase-4/5 prompts must not ask the fired turn to `playbook_propose` (phase-0 constraint,
  re-confirmed). Authoring happens in chat; fired turns run existing playbooks.
- Walkthrough helpers (`chatExpect` with nonce prefixes + conversation pinning + approvals-API
  polling) are the reusable pattern for every remaining phase's dojo test; copy from
  `curiosity-phase2/walkthrough.mjs`.
- Any future plugin tool name must be checked against the 0008 reserved list (and, generally,
  against existing DB policy rows: `GET /api/p/plugin-approvals/policy`).
- Autonomy lift (rung 4 auto / rung 5) remains a policy flip (`PolicyResolver.upsert` /
  `playbook_set_autonomy`), as designed — no code change needed later; phase 6 should
  demonstrate the flip explicitly on a fresh Luna.
- Episodic loop congestion (2.5min first token, asyncpg graceful-close timeouts) is a real
  platform issue that phase 5's nightly dream will hit if dreams overlap chat turns —
  phase-5 plan updated to schedule dreams in dead hours and keep dream turns short.
