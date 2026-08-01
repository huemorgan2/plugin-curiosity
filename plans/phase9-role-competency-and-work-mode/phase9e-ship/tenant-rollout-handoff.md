# Tenant rollout handoff — plugin-curiosity 0.7.0

**To:** luna-service owner (luna-service is read-only for this track — we plan,
you apply).
**From:** phase 9E ship (2026-07-10).

## What is ready

- **plugin-curiosity 0.7.0** is live on `https://marketplaces.com.ai/mp/official`,
  sha256 `483a40f0508cea61d0da6e79cabd8e78f362e777b2b0665480d3a0ad8bc1910a`
  (byte-verified against the local artifact).
- Upgrade path is proven end-to-end from marketplace artifacts (not in-tree):
  0.6.0 install → mission → hot upgrade to 0.7.0 → on-load spec-drift repair
  (9A phase columns added with defaults, [[role-charter]]/[[open-loops]]/
  [[value-log]] mirrors seeded, weekly trigger intact, mission untouched).
  See `luna/dojo/tests/curiosity-phase9/upgrade-e2e.mjs` + results.
- Production scheduler relay is already wired (phase 8.2); 9A-9C added **no new
  triggers** — the trigger surface is unchanged (daily research, nightly dream,
  weekly review), so no scheduler-service work is needed for this rollout.

## What we need from you

1. **Upgrade the hosted tenant image to a core ≥ 0.33.001** (ships the
   `prompt.assemble` hook — 8.1B prompt primacy; 0.7.0 feature-detects it and
   degrades gracefully on older cores, but the owner-felt fix needs it).
2. On tenant `vaselin-test-0-13-016-8-5-pluginsdk-9849753`, install
   **plugin-wiki**, then **plugin-curiosity 0.7.0** from the official
   marketplace. Order matters: curiosity's wiki mirrors need the wiki provider.
3. Nothing else. No restart choreography — the 8.1 no-restart install kickoff
   makes the install itself the tenant's first proactive moment, and 0.7.0's
   kickoff turn now retries transient model-API failures (3×, 90s apart), so a
   flaky moment no longer strands a mission at S0.

## How to verify it took

- `plugins` table row for plugin-curiosity reads **0.7.0** (the in-code
  manifest is authoritative — a toml-only 0.7.0 with a 0.6.x manifest means the
  upgrade did NOT apply).
- Within ~1 minute of install the agent posts its install-kickoff moment and
  `curiosity_flags` has `install_kickoff_sent`.
- After a mission is set, the scheduler account for the tenant carries exactly
  three `curiosity-*` triggers.
