# Phase 0 — Foundations & Scaffold

**Goal:** de-risk the one unverified assumption, stand up a dev Luna **with the real scheduler
and playbooks wired in**, and lay down two empty, loadable plugins so every later phase has a
place to write code.

**Depends on:** nothing. **Spike:** none.

---

## Grounded reality this phase builds on

- **The scheduler exists and is deployable** — `luna-scheduler` ships `scheduler-service`
  (FastAPI + Postgres, cron/NL expression engine, 15s ticker, HMAC-signed delivery with
  backoff, Render blueprint) and `plugin-scheduler` (tools `trigger_create` / `trigger_list` /
  `trigger_pause` / `trigger_resume` / `trigger_run_now` / `trigger_delete`, plus a `/fire`
  ingress that verifies HMAC and dedupes on `fire_id`). A fire runs either an **`agent_prompt`**
  (`ctx.send_muted_message(respond=True, tools=all)` → full agent turn) or a **`playbook`**
  (`playbook_run`). **Not yet deployed** (`scheduler_service_url` empty). → **We do not build a
  clock or an asyncio loop.** Curiosity registers schedules via `trigger_create`.
- **Playbooks exist** — `plugin-playbooks` lets the agent author (`playbook_propose`,
  `playbook_get_definition`, `playbook_edit`) and run playbooks whose `tool_call` steps invoke
  any registered tool (email, messaging, APIs), gated by approval policy. → **Actioning rides
  existing rails.**
- **The provider seam** (`ProviderRegistry`) is the one thing still to confirm for plugins.

---

## Scope

**In:** the provider-seam confirmation; a dev Luna running `plugin-scheduler` +
`plugin-playbooks` + a local `scheduler-service`; two scaffolded plugin repos that load cleanly.

**Out:** any wiki/curiosity behavior — that starts in phase 1.

---

## Deliverables

1. **Provider-seam decision.** Confirm whether a *plugin* can register a provider into
   `ProviderRegistry` and another plugin can fetch it via `ctx` (inspect
   `luna/luna/providers/registry.py` and how `plugin_memory` registers). If yes → `plugin-wiki`
   exposes `WikiProvider` there; if no → `plugin-curiosity` imports `plugin_wiki`'s service
   module directly (safe, shared DB). Record the choice in `NOTES.md`.
2. **Dev Luna** with: `plugin-web-access`, `plugin-funnelfighters` (read-only growth tools),
   `plugin-interview` (reference), **`plugin-playbooks`**, **`plugin-scheduler`**.
3. **A running `scheduler-service`** — stand it up locally (Postgres + `uvicorn app.main:app`)
   and point an account's `fire_url` at the dev Luna's `/api/p/plugin-scheduler/fire`; confirm
   `trigger_create` → ticker → delivery → `/fire` → an `agent_prompt` turn end to end. This is
   the dev clock; no in-plugin loop.
4. **`plugin-wiki` scaffold** — `luna-plugin.toml` + `wiki/__init__.py` that loads and
   registers nothing yet; empty `models.py`, `provider.py`, `injection.py`, `routes.py`.
5. **`plugin-curiosity` scaffold** — same, with empty `mission.py`, `research.py`, `dream.py`,
   `comms.py`.

---

## Steps

1. Copy `template/` → `plugins/plugin-wiki/` (package `wiki`) and `plugins/plugin-curiosity/`
   (package `curiosity`); confirm both load, toggle, and list.
2. Install `plugin-scheduler` + `plugin-playbooks` on the dev Luna; run `scheduler-service`
   locally; register a throwaway `trigger_create(... action_type="agent_prompt" ...)` and watch
   it fire a real agent turn. This proves the whole wake→turn path before any curiosity code.
3. Read `plugin_memory` + `ProviderRegistry`; record the provider path in `NOTES.md`.
4. Copy `plugin-interview`'s idempotent table-creation pattern into both `on_load`s (no tables
   yet — just the harness).

---

## Acceptance criteria

- [ ] Both new plugins load on the dev Luna, toggle on/off, and show in the plugin list.
- [ ] A `trigger_create` on the local `scheduler-service` fires an `agent_prompt` turn on the
      dev Luna, end to end (this retires the ambient-clock risk before phase 5).
- [ ] `plugin-playbooks` is installed and the agent can `playbook_propose` a trivial playbook.
- [ ] `NOTES.md` records the `WikiProvider` mechanism, grounded in the actual registry code.
- [ ] `git init` + first commit in each new plugin repo.

## Notes / risks

- The dev clock is the **real** `scheduler-service` run locally — not a stand-in. This means
  phases 5–7 exercise the production path from day one; phase 7 becomes deploy + config, not a
  rebuild.
- Do not add tools yet — a clean-loading scaffold plus a proven fire path is the whole point.
