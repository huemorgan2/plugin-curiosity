# Phase 0 notes

## Provider-seam decision (deliverable 1)

**Decision: use `ctx.provider_registry` — plugin-wiki registers a `WikiProvider`,
plugin-curiosity fetches it. No direct cross-plugin imports.**

Grounded in the actual code (dev Luna, now at 0.31.002):

- `luna/providers/registry.py` — `ProviderRegistry.register(key, impl)` /
  `.replace(key, impl)` / `.get(key, type)`. Process-wide instance injected into
  every plugin as `ctx.provider_registry` (`luna/plugins/context.py`).
- Precedent: `plugin_files` registers the `"storage"` provider in its `on_load`
  and `plugin_browser` consumes it; the loader's capability-aware ordering
  (`order_plugin_paths`, boot.py 008.98) guarantees provider-before-consumer.
- Manifest wiring: `provider = "wiki"` on plugin-wiki, `capabilities = ["wiki"]`
  on plugin-curiosity → topological load order, verified in the previous session
  with both scaffolds loading in the right order.

So:

```python
# plugin-wiki on_load
ctx.provider_registry.register("wiki", WikiProvider(engine=ctx.engine))
# plugin-curiosity, anywhere with ctx
wiki = ctx.provider_registry.get("wiki")   # None-safe: degrade if wiki absent
```

Fallback (not needed): direct import of `plugin_wiki`'s service module. Rejected —
breaks managed-dir isolation and the marketplace packaging story.

## Dev-Luna environment (deliverable 2–3)

- Dev Luna: `luna-plugins/luna`, **fast-forwarded from 0.25.001 to 0.31.002**
  (prod HEAD `c5b9fd3`) because plugin-playbooks 0.2.2 imports `EventBus` +
  `message_source` from `luna_sdk`, which only exist from 009.001 on. The
  message-source tagging phase 3 depends on is also 009.00x. Alembic migrated
  0015 → 0016 (agent tasks table) cleanly on the dockerized `luna-postgres`
  (port 5433, db `luna_dev`).
- UI rebuilt (`pnpm install && pnpm run build` in `ui/`; had to set
  `allowBuilds.esbuild: true` in `ui/pnpm-workspace.yaml` — the committed file
  contained a placeholder).
- scheduler-service runs locally: `ADMIN_KEY=dev uvicorn app.main:app --port 8123`,
  DB = dockerized `sched-postgres` (port 5436, already existed).
- Account `dev-luna` created via admin API; `fire_url =
  http://localhost:8000/api/p/plugin-scheduler/fire`; plugin creds wired via
  `.env` (`LUNA_SCHEDULER_SERVICE_URL/ACCOUNT_ID/SECRET`); plugin `/status`
  reports `connected`.

## Fire path proof (acceptance)

`trigger_create` ("every day at 03:00" → cron `0 3 * * *`) → `run-now` →
delivery worker POSTs HMAC-signed fire → plugin `/fire` verifies + dedupes →
muted message (`kind=muted`, `source=plugin-scheduler`) → **real agent turn** →
assistant replied `PHASE0-SCHED-OK`, tagged `source=plugin-scheduler`.
Fire status `delivered`, attempts 1, response 200; outcome `emitted: agent_prompt`.
