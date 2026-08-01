# Phase 8 — Fix plugin-wiki upgrade failures

## Symptom

Updating plugin-wiki 0.3.0 → 0.3.1 from the marketplace UI fails and rolls back:

```
upgrade failed for plugin-wiki, rolled back: on_load failed for plugin-wiki:
Two implementations registered for provider 'wiki'.
Existing: WikiProvider, new: WikiProvider
```

## Root causes (two independent bugs)

### 1. Core: `unload_plugin` never unregisters providers

`luna/plugins/loader.py:unload_plugin` (008.999 "COMPLETE teardown") removes
routes, event subs, tools, skills, triggers, config sections, approval
renderers and the registry entry — but **not provider registrations**.
`ProviderRegistry.register` raises on a duplicate key. So for any
provider-registering plugin the upgrade sequence is:

1. `unload_plugin("plugin-wiki")` — provider `wiki` stays registered
2. swap code dirs, load new version
3. new `on_load` calls `provider_registry.register("wiki", ...)` → raises
4. installer rolls back to the old version

Every future upgrade of every provider plugin hits this.

### 2. plugin-wiki: version drift across its three version stamps

At HEAD: `luna-plugin.toml` says **0.3.1**, `PluginManifest` in `__init__.py`
says **0.3.0**, `pyproject.toml` says **0.1.0**. The marketplace reads the
toml (0.3.1), the loaded plugin reports the manifest (0.3.0) — hence the UI's
"installed v0.3.0 / available v0.3.1" even though the 0.3.1 artifact IS the
installed code. Even if bug #1 didn't exist, the update would "succeed" and
still show an update available forever.

## Fixes

### A. plugin-wiki 0.3.2 (ships now; works on Lunas running the current core)

- `on_load`: idempotent provider registration —
  `replace("wiki", ...)` when `has("wiki")`, else `register(...)`.
  With this, the NEW version's on_load tolerates the stale registration left
  by the old version, so 0.3.x → 0.3.2 upgrades succeed on unpatched cores.
- Align all three version stamps at 0.3.2; add `tests/test_manifest.py`
  (toml ⇄ manifest ⇄ pyproject agreement — same guard plugin-voice has) so
  drift can't recur.
- Test: calling `on_load` twice with a shared provider registry must not raise
  and must leave a working provider.

### B. luna core (correct fix; benefits every provider plugin)

- `ProviderRegistry.unregister(key)` (no-op if absent).
- `unload_plugin`: new teardown stage "providers" — if
  `lp.manifest.provider` is set, unregister it.
- Test: load → unload → load of a provider plugin re-registers cleanly.

### C. Verify + ship

- Both test suites green.
- Live QA Luna: install wiki artifact, upgrade over itself (exercise
  unload → load in-process) — no duplicate-provider error, version reports 0.3.2.
- Publish 0.3.2 to the marketplace the affected Luna actually uses:
  `https://luna-marketplaces.onrender.com/mp/official` ("Luna Official (dev)").
- Commit + push plugin-wiki (local repo) and luna core.

## Non-goals

- plugin-curiosity: consumes the provider via `provider_registry.get("wiki")`,
  registers nothing — unaffected.
- Migrating old installs' recorded versions — the 0.3.2 upgrade re-stamps.
