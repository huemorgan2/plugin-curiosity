# Phase 9E — Ship 0.7.0 + tenant rollout: Execution Summary

**Status: DONE — 0.7.0 shipped, sha-verified, upgrade e2e 16/16 green from
marketplace artifacts (run 3, 2026-07-10). Tenant rollout handed off.**

## What landed vs plan

1. **Version bump** — all three stamps at 0.7.0 (`pyproject.toml`,
   `plugin_curiosity/__init__.py` PluginManifest, `luna-plugin.toml`);
   `test_manifest.py` guards agreement.
2. **Unit suite** — 93 passed (includes the two new 9D kickoff-retry tests).
   Plugin repo committed (`4c8b40d "0.7.0: role competency + work mode
   (phase 9)"`) and pushed — to a NEW public GitHub repo
   `huemorgan2/plugin-curiosity` (the repo had no remote; created to match the
   sibling plugin-mcp convention).
3. **Published to marketplaces.com.ai/mp/official** — sha256
   `483a40f0508cea61d0da6e79cabd8e78f362e777b2b0665480d3a0ad8bc1910a` matches
   the local artifact byte-for-byte in the live index.
4. **Upgrade e2e from real marketplace artifacts** — see below.
5. **Tenant rollout** — blocked on the hosted image (core ≥ 0.33.001);
   explicitly handed off: [tenant-rollout-handoff.md](tenant-rollout-handoff.md).
6. Production scheduler + tunnel leg: **skipped as planned** — 9A-9C changed
   no trigger surface (same three `curiosity-*` triggers, same fire targets
   resync on load), so there was nothing new for the production relay to carry.

## Upgrade e2e (step 4)

Harness: `luna/dojo/tests/curiosity-phase9/upgrade-e2e.mjs` — fresh Luna
(`luna_fresh9e`) booted WITHOUT in-tree plugin-curiosity, 16 checks:
install 0.6.0 → genuine pre-9A baseline → mission via chat → hot upgrade to
0.7.0 from the official marketplace → on-load spec-drift repair asserts.

**Run 3: 16/16 green.** The run ledger:

| Run | Result | What it taught |
|-----|--------|----------------|
| 1 | crashed at 6 | the official index only lists LATEST versions — `install {version: "0.6.0"}` fails at resolve even though the artifact zip is still served; also psql helper must tolerate missing relations pre-install |
| 2 | 15/16 | 0.6.0 pin-index worked; the ONLY fail was the install kickoff — "no target conversation": a brand-new owner with zero conversations gives the kickoff nowhere to post. Harness gap, not plugin: real owners install from the UI where one exists |
| 3 | **16/16** | conversation created BEFORE install → kickoff flag lands; whole arc green |

What the green run proves, end-to-end on shipped bytes (no in-tree code on
the path — the `luna/plugins/plugin_curiosity` symlink was moved aside):

- 0.6.0 installs from marketplace bytes and behaves as 0.6.0: pre-9A schema
  (no `agent_phase`/`setup_stage`), no kickoff-retry constants, install
  kickoff fires without a restart.
- A vague owner line ("i run a small pottery studio… thats your mission")
  becomes a real mission via `mission_set` in chat, and 0.6.0 registers the
  three recurring triggers.
- `POST /api/p/plugin-marketplace/upgrade` (version resolved from the live
  official index) hot-swaps to 0.7.0 with no restart.
- On-load spec-drift repair, exactly what an existing owner gets: additive
  migration adds the 9A columns with `setup/S0` defaults on the existing
  mission row; [[role-charter]], [[open-loops]], [[value-log]] mirrors seeded;
  schedule sync updated stale trigger targets in place (`created [], updated
  [daily-research, weekly-review]`) leaving exactly three triggers, no dupes;
  the mission row survives byte-identical — no `mission_set` required.
- The 9D kickoff-retry fix (`KICKOFF_ATTEMPTS`/`KICKOFF_RETRY_S`) is present
  in the installed 0.7.0 artifact — the fix travels in the shipped zip, not
  just the working tree.

## What we encountered

- **The official index only lists each plugin's LATEST version.** The 0.6.0
  artifact zip is still served, but `install {version: "0.6.0"}` fails at
  resolve ("not in index"). The e2e pins the baseline through a local
  one-plugin index (`http.server` on :8991) whose artifact is a sha-pinned
  byte mirror of the real marketplace 0.6.0 zip — install bytes are still the
  shipped artifact, and the UPGRADE leg (the path real owners take) runs
  against the real official index. If we ever want true pinned installs,
  the marketplace index needs per-version entries.
- **Booting Luna without the in-tree plugin**: `luna/plugins/plugin_curiosity`
  is a symlink into the workspace; the e2e moves it aside (and restores it
  after) so the loader only ever sees the managed marketplace install —
  otherwise the "fresh" 0.6.0 baseline would silently run 0.7.0 code.

- **The install kickoff needs a conversation to exist** ("no target
  conversation" in the log, flag never written). Harmless in real installs
  (the UI guarantees one) but any headless/scripted install flow that runs
  before the owner's first conversation silently skips the kickoff moment.
  Worth remembering for tenant provisioning: create the default conversation
  before installing plugins.

## Exit criteria

- [x] 0.7.0 live on marketplaces.com.ai, sha-verified.
- [x] Upgrade e2e green from the real artifact (16/16, run 3).
- [x] Tenant blocker explicitly handed off and tracked
      (tenant-rollout-handoff.md; owner: luna-service).
- [x] execution_summary.md committed; plugin repo pushed; luna repo pushed
      (workspace repo commit is local-only — its GitHub remote does not
      resolve for the authed account).
