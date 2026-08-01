# Phase 9B — Loops, Asks, Value Log: Execution Summary

**Status: DONE** (structural layer live-verified on QA Luna :8001; behavioral gaps deferred to 9C by design). Suite: 84/84 at 9B close (91 after 9C additions).

## What was built

- `plugin_curiosity/loops.py` (new): `LoopStore` over `ctx.db_session_factory`; kinds `question|promise|waiting_on|handoff|ask`, statuses open/closed/abandoned.
- Pure nudge ladder `next_nudge(now, count)`: +2d, +5d, then weekly — unit-testable with no clock dependency.
- **Ask economics enforced in the store, not the prompt**:
  - one open ask at a time ("One ask at a time — close loop {id} first");
  - an ask requires `unlock` and `value_ref` (a value-log id);
  - the referenced value must be NEWER than the last closed ask's `closed_at` — `<=` rejects ("Deliver value first, then ask — the referenced value predates your last ask"). Boundary tested to the microsecond.
- `curiosity_value_log`: evidence required ("value needs evidence"); `linked_ask_id` ties grant payoffs back to asks.
- Wiki write-through mirrors: `[[open-loops]]` (kind marks ❓🤝⏳📤🙏, "open since", unlocks line, "Recently closed" tail) and `[[value-log]]`; best-effort — degrades to "not mirrored" without the wiki provider.
- `ensure_loop_mirrors` upgrade seam: seeds both pages on load for a pre-9B mission; idempotent ("already present").
- 5 tools, all `auto_approve`: `loop_open`, `loop_close` (abandon REQUIRES a resolution), `loop_nudge` (open loops only), `loop_list`, `value_log_add`. Errors returned as steering messages, never raised.
- Daily trigger target gained "0. LOOP PATROL" + UNUSED-GRANT CHECK (moved/kept in 9C's rewrite).
- `tests/test_loops.py`: 15 tests covering all of the above.

## Live verification (QA Luna :8001, DB luna_fresh9a)

- `loop_list` reached naturally in chat when a naive user asked "what are you waiting on from me?" — agent enumerated open loops without being told the tool name.
- Daily trigger target updated IN PLACE on plugin reload (schedule sync-on-load drift update worked; no mission_set needed).
- Mirrors seeded on upgrade load: log line "loop mirrors seed on load: ok", both wiki pages present.

## Errors encountered and fixes

1. **Loop mirrors never seeded on load.** `routes.py`'s `app.router.on_startup` hook — the call site that SURVIVES under uvicorn (the `on_load` call dies with the bootstrap loop) — passed only `(ctx, store, reflections)`, so the new stores were silently `None`. **Rule reaffirmed: any new `schedule_on_load_work` parameter must be added at BOTH call sites.** Fixed and comment left at the hook.
2. **`plugin_scheduler_fires` has no `status` column** — driver assertions must poll the `messages` table instead.
3. Driver `psql` count polling returned empty strings (quoting), making the wait a no-op — the fired turn completed after sampling; verified manually. Drivers now cast with `int(x or 0)`.

## Behavioral gaps observed (deliberately NOT fixed in 9B)

The fired daily turn: opened no loops for its own promises, logged no value, ended on homework for the owner. T2 vague answers went to `memory_remember` instead of scope evidence. These are prompt-surface problems — 9B is the enforcement rails; 9C is the behavior. Carried into 9C as: LOOP_DISCIPLINE line on the daily, `value_log_add` steps on every surface, "never end on homework", work-phase charter upkeep in the fragment.

## Changes to future phases

- 9C: absorbed the behavioral-gap list above (done).
- 9D: walkthrough must assert loops/value rows appear from a FIRED turn, not just from chat.
- 9E: no changes.
