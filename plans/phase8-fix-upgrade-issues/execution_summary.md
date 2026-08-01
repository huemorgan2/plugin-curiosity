# Phase 8 — Fix plugin upgrade issues — Execution Summary

Date: 2026-07-08. Trigger: "Couldn't update plugin-wiki … Two implementations
registered for provider 'wiki'" on hosted tenant AND localhost; plugin-curiosity
also showed a perpetual "update available" badge.

## Root causes (two independent bugs)

1. **Core teardown gap.** `unload_plugin` (008.999 "complete teardown") removed
   routes, event subs, tools, skills, triggers, config sections — but never the
   provider registration. `ProviderRegistry.register` raises on a duplicate key,
   so the NEW version's `on_load` blew up and the installer rolled the upgrade
   back. Affected every provider-registering plugin on every upgrade.
2. **Version drift.** plugin-wiki stamped 0.3.0 (manifest) / 0.3.1 (toml) /
   0.1.0 (pyproject); plugin-curiosity 0.4.2 (manifest) / 0.4.3 (toml). The
   loaded plugin reports the manifest version, the marketplace reads the toml →
   the "update available" badge never clears even after a successful upgrade.

## Fixes shipped

### luna core (commit 3838e12, pushed to huemorgan/luna curiosity-dev)
- `luna/providers/registry.py`: `ProviderRegistry.unregister(key)` (no-op if absent).
- `luna/plugins/loader.py`: new `("providers", …)` teardown stage — unregisters
  the key declared in `manifest.provider` via `_unregister_provider`.
- `tests/008.999-fix-plugin-upgrade/`: conftest fixture grew a `provider` spec;
  `test_provider_swaps_on_upgrade` proves install → upgrade → delete swaps the
  registration cleanly. **Fails on the unfixed core, passes now (verified both
  ways by stashing the fix).** Suite: 11 passed; broader
  `-k "provider or loader or unload or upgrade or install"`: 180 passed.

### plugin-wiki 0.3.2 (commit 25bd3f3, local repo — no remote exists)
- `on_load` is now upgrade-safe on UNPATCHED cores too: if a stale "wiki"
  registration survives teardown, it calls `replace()` instead of `register()`.
  This is why localhost/hosted (old core) upgrades work without a core update.
- Versions aligned 0.3.2 across toml/manifest/pyproject.
- `tests/test_manifest.py`: version agreement + provider declared + on_load
  idempotency under a stale registration. Suite: 20 passed.

### plugin-curiosity 0.4.4 (commit 878edb8, local repo)
- No provider registered (consumer only) — NOT hit by bug 1; its badge was pure
  version drift (bug 2). Aligned all stamps at 0.4.4 (skipped 0.4.3: the
  marketplace already had a 0.4.3 artifact whose manifest said 0.4.2, so
  upgrading to it would not have cleared the badge).
- `tests/test_manifest.py`: version agreement + asserts curiosity never
  declares a provider. Suite: 29 passed.

## Live verification (QA Luna, patched core, port 8123)
- Isolated `LUNA_MANAGED_DIR`, local static file:// marketplace with wiki
  0.3.1 + 0.3.2. `POST /api/p/plugin-marketplace/upgrade` over the LIVE loaded
  plugin — the exact call that failed for the user — returned `ok: true`;
  ran it twice (in-tree→managed, managed→managed); wiki routes served 200 after
  each. `~/.luna/managed_plugins/plugin_wiki` rsynced to 0.3.2 (stale-override rule).

## Published (Render dev marketplace — the one the user's Lunas install from)
- https://luna-marketplaces.onrender.com/mp/official: plugin-wiki **0.3.2**,
  plugin-curiosity **0.4.4** (index verified).

## What the user should see
- Marketplace "Update" on plugin-wiki (→0.3.2) and plugin-curiosity (→0.4.4)
  now succeeds on hosted tenants and localhost WITHOUT a core update, and the
  badges clear afterward.
- Lunas running the patched core additionally get correct provider teardown
  for all future provider plugins.

## Notes
- plugin-wiki and plugin-curiosity git repos have no remotes; commits are local.
- `luna/plugins/plugin_wiki|plugin_curiosity` seen mid-session were dev links
  created by the running QA server, not tracked files.
