# 10.003 Execution Summary — Companion upgrades (wiki + scheduler) + curiosity adoption

**Shipped (three artifacts, each on its own terms):**

| Artifact | Version | Commit | Distribution |
|---|---|---|---|
| plugin-wiki | **0.7.0** | `99a475b` (local only — repo has no git remote) | published marketplaces.com.ai/mp/official |
| plugin-scheduler (+ scheduler-service on Render) | **0.3.0** | already live from earlier ship | published; prod service redeployed |
| plugin-curiosity | **0.9.2** | `a098cad`, pushed huemorgan2 | published marketplaces.com.ai/mp/official |

## What was built

- **plugin-wiki 0.7.0** — provider extraction API: `get_section(page, header, wiki=?)` (parsed bullets/numbered items) and `get_table(page, header, wiki=?)` (header row + rows), markdown-only, no LLM; page **revisions** (`wiki_write(..., reason=...)` recorded per write, `revisions(page, wiki=?)` newest-first). All additive; generic wiki features, nothing curiosity-specific.
- **plugin-scheduler 0.3.0** — `trigger_create(..., unique_name=...)` server-side upsert (advisory-lock, update-in-place on name collision within the account) kills the duplicate-cadence TOCTOU in code, not prompt discipline; **provenance** columns `created_by` + free-text `purpose`, both returned by `trigger_list`. Service + plugin shipped together.
- **plugin-curiosity 0.9.2** — the adoption patch, all feature-detected (`inspect.signature`), all fallbacks kept forever:
  - **Mission-bound wikis**: `mission_set` creates a named wiki per mission (slug from the statement), stores `Mission.wiki_id`; every wiki surface goes through `wikibind.wiki_kwargs()`, which re-checks the *current* provider each call. Re-mission archives; without multi-wiki the old global-namespace behavior is unchanged.
  - **Provider-first readers**: JD/success-criteria parsing via `get_section`/`get_table` when the provider has them; the bespoke parser stays as the fallback.
  - **JD stamp from real revisions**: `{count, latest}` from `revisions()` when present, else role_version join.
  - **Schedule provenance**: `unique_name`/`purpose`/`created_by` passed on CREATE only when the tool supports them; the 0.8.1 reaper stays as defense in depth.
  - **Owner-words rule**: no `S\d` stage codes on owner surfaces (the 10.002 jargon-leak fix — `overview.py` next-up title from label word; heartbeat prompt owner-visible-words rule).
  - **Degrade hardening (found by the downgrade leg, see below)**: wiki scaffolding is best-effort — per-slug try/except in `_seed_wiki_stubs`, whole-op guard in `ensure_success_criteria_page`; a broken/old wiki plugin can never abort mission adoption.

## Verification record

| Pass | Scope | Result |
|---|---|---|
| unit | `pytest plugins/plugin-curiosity` (incl. 21 new phase-10.003 tests, 2 for the degrade fix with a poisoned-slug provider) | **208 passed** |
| `companions-e2e.mjs` | local :8001, curiosity 0.9.2 + wiki 0.7.0 + scheduler 0.3.0 in-tree: adoption creates+binds a wiki, shelf reads scoped, JD stamp from revisions, two concurrent adoption turns → exactly one heartbeat via upsert, reaper log empty | **23/23** |
| `companions-downgrade.mjs` | :8003, curiosity **0.9.2** against **old** wiki 0.3.2 + scheduler 0.2.2 on a multi-wiki DB — the feature-detect contract | **13/13** (after the fix below; first run 12/13) |
| `companions-prod.mjs` (+ `-part2.mjs`) | fresh Luna :8002, empty-ish managed dir carrying the 0.9.1 artifact, **prod** Render scheduler, disposable HMAC account `curiosity-10003-e2e` | **15/15** (part 1 checks 1–8, part 2 checks 8r–15) |

**Prod e2e highlights** (real marketplace artifacts end to end):
- Baseline 0.9.1-only → runtime `POST /install` wiki 0.7.0 + scheduler 0.3.0 → `POST /upgrade` curiosity 0.9.1 → 0.9.2 (staged swap, sha256 verified) → relaunch → all three live.
- Ceramics-studio mission adopted from chat, bound to its own wiki; scoped stubs verified in-DB (`wiki_pages` joined through `wikis.slug` — `wiki_id` is a UUID FK, the mission stores the slug).
- Prod triggers carry provenance: `purpose` + `created_by=plugin-curiosity` on the three research schedules (`created_by=plugin-scheduler` on the heartbeat, since the agent authored it through the tool).
- JD parsed via the extraction API with revisions `{count: 2}`.
- Heartbeat race: HMAC-deleted the trigger server-side, fired two concurrent turns → **exactly 1** heartbeat row, purpose "my setup drive — closes qualification gaps". The reaper's raced-duplicates path is now unreachable, as planned.

Artifacts: `luna/dojo/results/curiosity-phase10/{companions-e2e,companions-downgrade,companions-prod}/checks.json` + overview/trigger snapshots.

## Defect found and fixed (the downgrade leg earned its keep)

First downgrade run failed check 11: `mission_set` died with `sqlalchemy.exc.MultipleResultsFound` — the old wiki plugin (0.3.2) does slug-only `.scalar_one_or_none()` lookups, and on a DB that already has multiple wikis a duplicated slug matches two rows. Curiosity's wiki *scaffolding* (success-criteria page, stub seeding) was letting that exception propagate out of mission adoption.

Fix in 0.9.2 (commit `a098cad`): scaffolding is best-effort — per-slug guards in `_seed_wiki_stubs` (returns `seeded [...], skipped [...] (wiki degraded)`), whole-op guard in `ensure_success_criteria_page` (`skipped: <err>`); on-load paths were already guarded. Two unit tests with a poisoned-slug provider pin the contract; check 11 now asserts no `tool.error`, no page loss, and the skip logged.

Notable resilience data point: even *before* the fix, the agent self-recovered in-chat — when `mission_set` errored it fell back to `mission_refine` + `update_self` and completed adoption. Logged for the phase-11 feedback doc.

## Cleanup

Disposable prod scheduler account `curiosity-10003-e2e` deleted (prod back to exactly the two protected `vaselin-test-*` accounts). Lunas on :8002/:8003 killed; DBs `luna_prod10003`, `luna_down10003` dropped; in-tree plugin symlinks restored.
