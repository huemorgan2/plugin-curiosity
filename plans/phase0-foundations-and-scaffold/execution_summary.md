# Phase 0 — Execution Summary

**Status: complete.** Dev Luna runs 0.31.002 with both scaffold plugins loading, the local
scheduler-service delivers signed fires end-to-end into real agent turns, and the provider
seam is proven live. One core fix (opt-in DB pooling) was required to make the dev
environment stable enough to test against.

## What was done

- **Dev Luna brought to prod parity.** Dev checkout was 0.25.001, predating the 009.x SDK
  exports (`EventBus`, `message_source`, `TriggerSourceRegistry`) that plugin-playbooks
  needs. Fast-forwarded to prod HEAD `c5b9fd3` (0.31.002), migrated alembic 0015→0016,
  rebuilt the UI (`pnpm-workspace.yaml` needed `allowBuilds: esbuild: true`), re-synced deps
  with `uv sync --group dev`.
- **Scaffold plugins created and loading.** `plugins/plugin-wiki` (manifest
  `provider="wiki"`) and `plugins/plugin-curiosity` (manifest `capabilities=["wiki"]`),
  standalone repos symlinked into `luna/plugins/` as `plugin_wiki`/`plugin_curiosity`. Both
  visible in `/api/plugins`, toggleable, orderable by the provider-aware loader.
- **Local scheduler-service stood up** on :8123 (sched-postgres :5436, account `dev-luna`,
  HMAC secret in `luna/.env` as `LUNA_SCHEDULER_*`). plugin-scheduler `/status` reports
  connected.
- **Fire path proven end-to-end:** `trigger_create` → run-now → signed delivery (HMAC
  verified, fire_id deduped, 200) → muted message (`kind='muted'`, `source=plugin-scheduler`)
  → real agent turn → assistant reply `PHASE0-SCHED-OK` tagged with the source. Trigger
  `23bd7933` retained as evidence; `scripts/../scratchpad/sched_e2e.py` is the account-API
  client used.
- **Dojo walkthrough authored** at `dojo/tests/curiosity-phase0/walkthrough.mjs` (headed
  Playwright): plugin visibility, UI toggle off/on, scheduler status, and a real chat turn
  that authors a playbook via `playbook_propose`.
- **Provider seam decided and proven:** `ctx.provider_registry.register("wiki", impl)` in
  plugin-wiki's `on_load`; resolved from plugin-curiosity's ctx (live check:
  `GET /api/p/plugin-curiosity/status` → `{"wiki_provider": "resolved"}`).

## What we encountered (and fixed)

1. **`EventBus` import failure** killed plugin-playbooks on 0.25.001 → fast-forward (above).
2. **Signup closed on a single-user instance** — dojo auth now mints an owner JWT directly
   via `luna.auth.jwt.create_token(user_id)` and passes it as `TOKEN` env.
3. **`playbook_propose` is `chat_only=True`** — scheduled/muted fire turns do NOT get it.
   Discovered when a fired agent_prompt turn replied "tool not available". Playbook
   authoring must happen in real chat turns (or the tooling policy must be explicitly
   relaxed). **Phase 2/5 plans updated.**
4. **Dev postgres (Docker on macOS) collapses under connection churn.** Luna core uses
   `NullPool` (one fresh asyncpg connect per operation). Under a UI boot burst plus
   concurrent test suites, connects took 6–8s, some were reset mid-handshake
   (`ConnectionResetError`), postgres hit auth timeouts, and once a backend crashed into
   recovery mode (checkpoint fsync took 40s — the docker VM disk is the bottleneck). Fixed
   with an **opt-in pooled engine in core** (`luna/data/__init__.py`): `LUNA_DB_POOL=1` →
   `pool_size=10, max_overflow=20, pool_pre_ping, pool_recycle=1800`. Default stays
   NullPool (pooled connections are event-loop-bound; only single-loop `luna serve` should
   opt in). With the pool warm, a 10-request burst went from 6.9s+resets to 1.7s all-200.
5. **False-positive dojo check:** polling `body.innerText` for a marker phrase matches the
   *user's own* message. The walkthrough now polls the messages API for an **assistant**
   message, and uses the correct playbooks route (`/api/p/plugin-playbooks/playbooks`).
6. **Two pytest suites ran concurrently against the same dockerized postgres** (an orphan
   from a prior session) and, combined with browser tests, produced the crash in (4).
   Serialize heavy DB consumers on this machine.
7. **The core unit suite deletes `ui/dist`** (a vite-build proof test), so every UI route
   500s afterwards (`index.html does not exist`). Rebuild with `cd ui && pnpm build` after
   any full suite run, before browser tests.
8. **Settings sidebar nav caused a locator false positive** — plugin-wiki's `SidebarSection`
   adds a "Wiki" nav item, so a bare `span:text("Wiki")` matches before the plugin list
   loads. Walkthrough locators are now scoped to plugin cards (`div.rounded-xl span`), and
   the UI shows auto-derived `shown_name` ("Curiosity"), never the raw plugin name.
9. **LLM-network flakes kill chat turns mid-flight** (Anthropic ConnectTimeout; one
   `playbook_propose` 30s tool timeout). The walkthrough now retries the chat message once
   when the tail of the conversation shows an error reply, and uses a run-unique playbook
   name so reruns stay idempotent.

## Final verification

- Core unit suite on prod HEAD: **1360 passed, 56 failed — all 56 pre-existing upstream**
  (reproduced on pristine core with the pool patch reverted; e.g. stale
  `test_manifest_toml_present_and_consistent` expects plugin-files' old 6-tool set). Not
  regressions from the pool fix or the new plugins.
- Dojo walkthrough `curiosity-phase0`: **8/8 checks green, headed browser** — plugin
  visibility, UI toggle off/on (API-polled), scheduler connected, real chat turn authored
  and persisted a playbook via `playbook_propose`.

## What we learned

- The plugin seam surface (`provider_registry`, `db_tables` + `luna-plugin.toml`,
  `routes_module`, `prompt_sections`, muted messages) is sufficient for phases 1–5 without
  further core changes — except `prompt_sections()` taking no turn argument (see phase-1
  summary once written: tier-2 wiki injection can't be query-relevance-ranked from the
  plugin side).
- Scheduled fires produce full agent turns with tool access (minus `chat_only` tools) —
  the substrate phases 4–5 need is real.
- Test invocation on this Google-Drive path: `uv run pytest` fails to spawn (space in
  shebang path); use `uv run python -m pytest`.

## Consider for the future

- **Phase 2:** playbook authoring rails must run in chat context, or grant curiosity its
  own authoring path through the playbooks plugin API rather than the chat_only tool.
- **Phase 5 (nightly dream):** fires arrive as muted agent turns — fine for wiki writes
  (wiki tools are not chat_only), but never plan a fired turn that needs a chat_only tool.
- **Dev-env hygiene:** keep `LUNA_DB_POOL=1` in dev `.env`; serialize dojo runs and full
  test suites; the docker VM needs ~no other load during browser walkthroughs.
- **Upstreaming:** the pooled-engine flag and the dojo walkthrough pattern (owner-JWT auth,
  assistant-message polling) are worth carrying to prod luna.
