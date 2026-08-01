# Phase 5 — execution summary (dream nightly)

**Status: DONE.** plugin-curiosity 0.4.0: the nightly dream ships as a *schedule, not a loop* —
a `curiosity-nightly-dream` trigger (`agent_prompt`, "every day at 02:00") whose target prompt
IS the consolidation routine. Proven live on dev Luna + dojo walkthrough (results below).

## What was done

- **`dream.py`** — `DREAM_TARGET`, the fired routine (mirrors phase 4's
  `DAILY_RESEARCH_TARGET` pattern): re-read the mission (`mission_get`), find pages touched in
  the last day via `wiki_toc` `updated_at`, consolidate with `wiki_patch` (merge, prose-ify,
  [[link]], keep citations), tend the question ledger (`wiki_resolve_question` / `wiki_ask`),
  distill **one** "Morning thought" via `share_thought`, and no-op gracefully on a quiet day
  ("quiet night — nothing to consolidate"). Self-contained — no mission text baked in.
- **Quiet-hours choreography does the "morning thought" for free**: 02:00 is inside quiet
  hours (21:00–08:00), so the dream's `share_thought` *queues*; the queue drains after 08:00
  (any share_thought call, or plugin load). The tool is routine-kind, so the drained thought
  consumes `ROUTINE_DAILY_CAP=1` — "exactly one morning thought" is enforced structurally, not
  by prompt discipline.
- **`_sync_schedules` now patches drift** (`_spec_drift`): compares `target` and `expr_raw`
  against the spec and PATCHes only drifted fields via `trigger_update` — 0.3.0's placeholder
  dream trigger (03:30) upgraded in place, same trigger id, no delete/recreate churn.
- **Sync-on-load** (`schedule_on_load_work` in `__init__.py`): on every boot with an existing
  mission — drain overnight-queued thoughts, wait 15s (scheduler plugin may still be loading
  on runtime installs), re-sync schedules. This is how a plugin upgrade reaches an existing
  mission without waiting for a `mission_set`.
- Tests: `test_dream.py` (5 tests — target wiring, expr-drift patch, sync-on-load refresh /
  no-mission no-op / once-per-loop guard); conftest fakes extended with `expr_raw`.
- Dojo: `dojo/tests/curiosity-phase4/walkthrough.mjs` committed (closed phase 4);
  `dojo/tests/curiosity-phase5/walkthrough.mjs` written + run headed.

## What was encountered and learned

1. **`luna serve` runs plugin `on_load` in a throwaway bootstrap loop.** cli.py does
   `fastapi_app = asyncio.run(_bootstrap_then_dispose())`, then uvicorn starts a NEW event
   loop. Any task created during `on_load` dies with the disposed bootstrap loop — **no
   exception, no log, it just never runs**. Two restarts of "why didn't the sync fire?" led
   here. Consequence discovered along the way: **phase 4's `_drain_on_load` never actually
   worked under `luna serve`** (unit tests passed because tests run everything on one loop).
2. **The fix is the core's own idiom**: register a startup hook in `register_routes` via
   `app.router.on_startup.append(...)` — cli.py mounts `_reboot_mcp` exactly this way. The hook
   runs in uvicorn's serving loop. A module-level loop-identity guard
   (`_onload = {"loop": None, "task": None}`) makes on_load (runtime-install path, long-lived
   loop) + startup hook (serve path) safe to call in any combination — second call on the same
   loop is a no-op.
3. **`app.add_event_handler` does not exist on Luna's app object**, and the failure mode is
   nasty: the AttributeError inside `register_routes` produced `plugin.routes_failed` and
   killed **all** of plugin-curiosity's routes for that boot. Guard exotic host-app APIs with
   try/except; prefer `app.router.on_startup`.
4. **The event loop holds only weak refs to tasks** — an on-load task that sleeps 15s is
   GC-able mid-flight. Keep a strong reference (`_onload["task"]`). (This alone didn't fix the
   serve-path bug, but it's a real second bug.)
5. **`wiki_toc` rows carry `updated_at`** — the dream finds "today's touched pages" with zero
   plugin-wiki changes. Phase 5 needed no wiki schema work at all.
6. Sync-on-load proven live across three Luna restarts: dream trigger
   `60cd450e-6eb2-4e13-a9ca-7b3934a3e303` kept its id while target+expr were patched
   (placeholder/03:30 → real routine/02:00).

## Dojo walkthrough (headed, real Luna)

`dojo/tests/curiosity-phase5/walkthrough.mjs` — checks:
1. one dream trigger, real target, `every day at 02:00`, **same id across upgrades** (1b);
2. `run-now` → fire delivered, full consolidation turn completes (`outcome=emitted`, 16-min
   budget — outcome lands only AFTER the turn);
3. consolidation evidence: `wiki_revisions` count grew;
4. exactly one "Morning thought" through the guardrails (daytime run → posted immediately,
   `routine_posted_today == 1`; the 02:00 production path queues to the 08:00 drain instead —
   that leg is unit-tested + phase-4-proven live);
5. dedupe: HMAC-signed replay of the seen `fire_id` (minimal `{"fire_id"}` body so a dedupe
   failure can't re-run a 10-min turn) → `{ok, deduped:true}`, still one local fire row;
6. browser: dream muted line renders as a collapsed disclosure row; Morning thought carries
   the 💭 Reflection badge.

**Result: 8/8 PASS** (run 2). Evidence: fire `9b5991c6` → `emitted: agent_prompt`;
`wiki_revisions` 67→68 (run 1: 63→67 — the dream really merges/rewrites pages);
`routine_posted_today == 1`, single `posted|Morning thought` row; signed replay →
`{ok, deduped:true}`, one local row; browser shows the collapsed muted rows and the 💭
badge on the Morning thought reply. Run 1 was 7/8: the badge check ran as a single
snapshot, but the Morning thought's 💭 reply is a **separate agent turn** that lands
minutes after the dream turn's `outcome=emitted` — fixed by polling with page reloads
(5-min budget). That timing gap is itself a finding: `share_thought`'s moment post is
fire-and-forget, so "outcome=emitted" ≠ "all downstream turns visible."

Empty-day no-op ("quiet night") is prompt-designed + unit-asserted; live validation
deliberately deferred to phase 6's fresh-Luna run (this dev wiki is never empty anymore).

## For the future

- **Core recommendation (luna, not this plugin)**: the bootstrap-loop dispose is a trap every
  plugin with on-load background work will hit. Either run `load_all_plugins` inside the
  serving loop (uvicorn lifespan) or document `app.router.on_startup` as the supported hook.
  Worth a core issue; until then the curiosity pattern is the reference.
- Phase 6 must validate the empty-day dream no-op on the fresh Luna, and must check
  `routes ok` per plugin on the fresh install (a routes_failed is silent otherwise).
- Phase 7's "re-point schedules" step is now automatic (sync-on-load) — plan updated.
- Phase 6/7 PLAN.md files updated with these learnings (bootstrap loop, dedupe-replay
  technique, cap-reset trick for multi-day simulation, 16-min outcome budget).
