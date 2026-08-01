# Phase 5 — the nightly dream

**Goal:** while the human sleeps, Luna consolidates the day's raw learnings into clearer wiki
pages and surfaces **one** distilled thought in the morning. This is the "dream → clear
thoughts" pillar of the vision — and it now runs on the **real scheduler**, so it works even
when the machine is asleep.

**Depends on:** Phases 1, 2 (schedule registered), 4 (wiki + research + share_thought).
**Spike:** **SP2** (dream cadence/noise; consolidation quality).

---

## Scope

**In:** the nightly dream as a **scheduled `agent_prompt`** (or a curiosity-authored dream
**playbook**) fired by `luna-scheduler`; the consolidation routine the fired turn performs;
production of exactly one morning thought.

**Out:** deploying the scheduler to production (phase 7). No custom cron, no asyncio loop, no
custom idempotency — the scheduler owns all of that.

---

## Design (the dream is a schedule, not a loop)

Phase 2's `mission_set` already registered the cadence — the trigger is named
**`curiosity-nightly-dream`** (verified live in the phase-2 dojo run). Here we fill the
dream target via mission.py's idempotent `_sync_schedules` (update the target, don't
delete/recreate):

```
trigger_create(
  name="curiosity-nightly-dream",
  schedule_expr="every day at 02:00",
  action_type="agent_prompt",
  target=<dream instructions>,
  timezone=<owner tz>,
)
```

At 02:00 the scheduler's ticker enqueues a fire → the luna-service relay **wakes the Fly
machine** → `plugin-scheduler` `/fire` verifies HMAC, **dedupes on `fire_id`**, and runs
`send_muted_message(respond=True, tools=all)`. That agent turn executes the dream:

1. list wiki pages touched today,
2. summarize the day's new research/citations,
3. `wiki_patch` those pages into clearer, consolidated form (+ revision rows),
4. update/close open questions,
5. draft **one** morning thought via `share_thought`, queued to post after quiet hours (~08:00).

**Why an `agent_prompt` and not in-plugin Python:** the fired turn is already agentic and has
all wiki tools; the consolidation is a prompt, not a service. If the dream later grows
branch/loop structure, promote it to a curiosity-authored **playbook**
(`action_type="playbook"`) — the scheduler supports that target directly, and Luna can author
the playbook herself (phase 2 rails — but note: `playbook_propose` is `chat_only`, so the
authoring happens in a chat turn, never inside the fired dream itself). Either way:
**no asyncio, no bespoke endpoint.**

**Idempotency & retries are free** — `plugin-scheduler` records each `fire_id` in
`plugin_scheduler_fires` and returns `deduped:true` on repeats, so scheduler retries can't
double-dream. We add nothing.

**Dev vs prod:** in dev the same path runs against the locally-hosted `scheduler-service`
(phase 0). Production is just deploying that service (phase 7) — the plugin code is identical.

---

## Steps

1. SP2: write the dream instructions (the `agent_prompt` target) that perform the 5-step
   consolidation using `wiki_*` + `share_thought`; make them safe to run on an empty day
   (no-op gracefully).
2. Confirm phase 2's `curiosity-nightly-dream` trigger points at these instructions; fire it
   via `trigger_run_now` and watch the full wake→turn→consolidation path on the dev scheduler.
3. Tune noise: exactly one consolidated thought per dream, batched, relevance-gated, posted
   after quiet hours.
4. Multi-day dry run: confirm pages measurably improve and one grounded morning thought lands
   each day; confirm a duplicate `fire_id` is deduped.

## Acceptance criteria

- [ ] The `nightly-dream` schedule fires via `luna-scheduler`, waking the machine, and runs the
      consolidation turn — **no asyncio loop in our plugin**.
- [ ] After a dream, touched pages are consolidated (clearer summaries/bodies + revision rows)
      and open questions are updated.
- [ ] Exactly **one** morning thought is produced, posts after quiet hours, and cites wiki pages.
- [ ] A replayed `fire_id` is deduped by `plugin-scheduler` (no double consolidation).
- [ ] An empty-day dream is a graceful no-op.

## Notes / risks

- The dream inherits the scheduler's `daily_fire_cap` and `min_interval_s` floors — fine for
  once-nightly, but note them if cadence ever tightens.
- Keep the consolidation prompt tight; one over-long turn risks hitting MAX_TURNS mid-dream.

> **Phase-1.5 learnings:** dream consolidation writes emit `wiki.updated` (SSE
> `/api/events?topics=wiki.*`) — an open wiki pane animates the dream live, which makes a
> great demo of the "dream" happening (leave a pane open overnight in the dojo run). The
> event payload is `{action, slug}` only; if the morning thought wants to reference "what
> changed tonight", read `wiki_revisions` rather than extending the event.

> **Phase-2 learnings:**
> - Real platform load matters: under concurrent turns, first-token latency reached ~2.5min
>   and asyncpg graceful-close timeouts appeared (episodic loop congestion); luna-postgres
>   (docker) also crashed into recovery mode once, self-recovering in ~2min. The 02:00
>   dead-hours slot is right; additionally keep the dream turn short (learning already in
>   Notes) and make the consolidation prompt resilient to a failed/cancelled fire — the next
>   night's fire must be able to pick up where the last left off (wiki state is the ledger).
> - When testing with `trigger_run_now` in the dojo, the fired turn is muted — verify results
>   via wiki revisions and the plugin routes, not chat markers; reuse the phase-2 walkthrough
>   helpers (nonce-prefixed prompts, approvals-API polling) for any chat-side checks.

> **Phase-4 learnings:**
> - `trigger_update` now exists (plugin-scheduler 0.1.2) and `_sync_schedules` already
>   PATCHes a stale target in place when the listed target differs from the spec — filling
>   the dream target is one line in `MISSION_SCHEDULES` (point it at a `dream.DREAM_TARGET`
>   like phase 4 did with `research.DAILY_RESEARCH_TARGET`). But `_sync_schedules` only runs
>   on `mission_set`/`mission_refine` — add a **sync-on-load** task (mirror
>   `_drain_on_load`) so a plugin upgrade refreshes the trigger for an existing mission
>   without a chat turn.
> - The 02:00 fire lands in **quiet hours**, so a `share_thought` from the dream turn queues
>   automatically and drains after 08:00 — the "morning thought" behavior comes free from the
>   phase-4 guardrails. Decide kind: the `share_thought` **tool** hardcodes `kind="routine"`
>   (counts against the 1/day cap when drained); `comms.share(..., kind="dream")` is
>   cap-exempt. Recommendation: keep the tool routine and let the dream's thought BE the day's
>   one routine thought — that enforces "exactly one morning thought" for free.
> - Make the dream target **self-contained** like `DAILY_RESEARCH_TARGET` (re-read the
>   mission via `mission_get` at fire time; never bake mission text into the trigger).
> - Dojo: verify fire delivery via `GET /api/p/plugin-scheduler/fires` → **`.local`** rows
>   (`fire_id`, `outcome ∈ emitted|deduped|failed`) — there is no `.fires` key; the dedupe
>   acceptance check is a replayed fire showing `outcome=deduped`. Research-grade muted turns
>   take 8–16 min under load — budget polls accordingly, and never overlap chat checks with a
>   running heavy turn (I/O contention alone breaks them). Chat prompts must instruct a
>   marker-bearing reply (`RESULT-${RUN}: ...`) — raw tool JSON doesn't echo the run nonce.
> - All dojo checks must be growth-based (before/after within the run): queued reflections,
>   open questions, and missions accumulate across runs.

> **Phase-3 learnings:** the morning thought is one `source="curiosity"` **moment**
> (`ctx.send_muted_message(channel="moment", source="curiosity", tools=[wiki reads...])`) —
> the badged reply bubble is the thought; the reaction turn has no tools unless given an
> allowlist. Post it as a separate step after the consolidation turn, with an explicit
> `conversation_id` (the default is "most recent conversation"). Title it "Morning thought"
> — sub-kinds differentiate by title, not by new source values (the client badge contract
> names only `curiosity`).
