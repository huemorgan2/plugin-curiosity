# Phase 9E — Ship 0.7.0 + tenant rollout

**Parent:** [../PLAN.md](../PLAN.md) §4 (9E) + §7 (ship-to-tenant note).
**Depends on:** 9D green twice.

---

## Steps

1. **Version bump to 0.7.0 in all three stamps** (in-code `PluginManifest` is
   authoritative; toml-only bumps make upgrades look like they never applied —
   memory + `test_manifest.py` guards).
2. Full unit suite green; commit plugin repo; push.
3. **Publish to marketplaces.com.ai** (always ship after push — memory; creds
   in workspace .env); verify published sha256 matches the local artifact.
4. **Upgrade e2e (marketplace artifact, not in-tree):** fresh Luna with 0.6.0
   installed + a mission set → runtime upgrade to 0.7.0 from the marketplace →
   on-load spec-drift repair observed: charter/loops/value mirrors seeded,
   phase defaults applied, weekly trigger intact — no mission_set required
   (8.2 learning 3: the upgrade path is what real owners take). Reuse the
   phase-8 `walkthrough-prod.mjs` pattern; production scheduler + tunnel leg
   only if the trigger surface changed (9A-9C add no new triggers — expected
   skip, decide at execution).
5. **Tenant rollout (the owner-felt fix):** upgrade the hosted tenant image to
   a core ≥0.33.001 (prompt.assemble hook) and install plugin-wiki +
   plugin-curiosity 0.7.0 on the observed tenant
   (vaselin-test-0-13-016-8-5-pluginsdk-9849753); scheduler relay already
   wired in production (memory). The 8.1 no-restart kickoff makes the install
   itself the first proactive moment. Coordinate the image upgrade with the
   luna-service owner (luna-service is read-only for us — memory).
6. **execution_summary.md** in the parent folder: what landed vs plan, live-QA
   learnings, deviations — same format as 8.1/8.2.
7. Cleanup: any scheduler test accounts deleted immediately (retry-ladder spam
   — memory); tunnels/processes killed; symlinks restored.

## Exit criteria
- 0.7.0 live on marketplaces.com.ai, sha-verified.
- Upgrade e2e green from the real artifact.
- Tenant runs 0.7.0 (or the blocker — image upgrade ownership — is explicitly
  handed off and tracked).
- execution_summary.md committed; workspace + plugin repos pushed.
