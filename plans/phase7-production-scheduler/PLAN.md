# Phase 7 — deploy & wire the scheduler (production ambient)

**Goal:** make the nightly dream and recurring research work on **hosted** Luna by putting the
already-built `luna-scheduler` into production. Because the clock, plugin, and luna-service
relay all **already exist**, this is **deploy + configure + verify** — not a build. The one
gate: populating luna-service config is owner-side (luna-service is read-only for us).

**Depends on:** Phases 2 & 5 (schedules registered and firing on the dev scheduler), Phase 6
(validated v1). **Spike:** none.

---

## What already exists (so this phase is small)

- `scheduler-service` — deployable via its Render blueprint (always-on, auto-provisions
  Postgres). Ticker + delivery + HMAC already built.
- `plugin-scheduler` — packaged (`luna-plugin.toml`), auto-provisions per agent via
  `/api/agent/scheduler/connect`.
- luna-service relay — `POST /api/webhooks/scheduler/{slug}/fire` already wired, wakes the Fly
  machine, forwards signed body. Admin + agent-self-service routes already present.

**Missing only:** the service isn't deployed, and luna-service's `scheduler_service_url` /
`scheduler_service_admin_key` are empty.

---

## Scope

**In:** deploy `scheduler-service`; populate luna-service config (owner); install
`plugin-scheduler` on hosted Luna; verify the end-to-end wake→fire→turn path in production.

**Out:** any new scheduler code. Any curiosity code change — the plugin is identical to dev.

---

## Steps

1. **Deploy `scheduler-service`** (Render blueprint): provision Postgres, set `ADMIN_KEY`,
   `TICK_INTERVAL_S`, `DELIVERY_*`, `MIN_INTERVAL_S`, `DEFAULT_DAILY_FIRE_CAP`; confirm
   `/health`.
2. **Owner wires luna-service** (read-only for us → hand off a precise config change, not a
   PR): set `CLOUD_SCHEDULER_SERVICE_URL` + `CLOUD_SCHEDULER_SERVICE_ADMIN_KEY`.
3. **Install `plugin-scheduler`** on hosted Luna; confirm it auto-provisions its account via
   `/api/agent/scheduler/connect` (secret + `fire_url` registered with the service).
4. **Re-point curiosity's schedules** — the same `trigger_create` calls from phase 2 now land
   on the production service; no code change.
5. **Verify end to end on a sleeping machine:** let the machine sleep, wait for a scheduled
   fire, confirm the relay wakes it and the dream/research turn runs; verify HMAC, dedupe, and
   `daily_fire_cap`.

## Acceptance criteria

- [ ] `scheduler-service` is deployed and healthy; luna-service config populated (owner
      confirmed).
- [ ] Hosted `plugin-scheduler` auto-provisions and shows the account in the service.
- [ ] A scheduled fire **wakes a sleeping hosted machine** and runs the dream turn, with valid
      HMAC verification.
- [ ] Retries dedupe on `fire_id`; no duplicate consolidation or morning thought.
- [ ] Hosted behavior matches the phase-6 validation on the growth mission.

## Notes / risks

- **luna-service is read-only for Claude** — step 2 is a documented handoff to owners, not code
  we write.
- Everything upstream already runs against a local `scheduler-service` (phase 0), so v1 does
  **not** block on this phase — it upgrades dev-ambient to hosted-ambient (works while asleep).
- After this phase, ambient behavior is fully unattended on hosted Luna. The remaining lever is
  the autonomy ceiling (rung 4 auto / rung 5), which is a policy flip on the phase-2 rails, not
  scheduler work.

> **Phase-4 learnings:** verification in step 5 should read
> `GET /api/p/plugin-scheduler/fires` → `.local` rows (`fire_id`,
> `outcome ∈ emitted|deduped|failed`; `.service` mirrors the service history) — there is no
> `.fires` key. `trigger_update` (plugin-scheduler 0.1.2) means re-pointing schedules in step
> 4 is an in-place PATCH preserving trigger ids and fire history — no delete/recreate churn
> on the production service either.

> **Phase-5 learnings:**
> - Step 4 (re-pointing schedules) is now **automatic**: plugin-curiosity 0.4.0's
>   sync-on-load creates missing triggers and PATCHes target/schedule drift on every boot
>   where a mission exists. Once hosted plugin-scheduler is provisioned against the
>   production service, the next Luna boot registers `curiosity-daily-research` +
>   `curiosity-nightly-dream` there — no manual `mission_set` needed. Verify via
>   `GET /api/p/plugin-scheduler/triggers` (dream: `expr_raw == "every day at 02:00"`,
>   target starts `[curiosity] Nightly dream`).
> - That sync runs via a **routes startup hook**, not on_load (`luna serve` disposes the
>   bootstrap loop that on_load runs in). If hosted Luna boots differently (Fly machine
>   wake), the same hook fires on every uvicorn startup — but confirm `routes ok` for
>   plugin-curiosity in the hosted log; a routes_failed there means no sync AND no owner
>   routes.
> - Step 5's dedupe check can replay a **signed** fire (HMAC-SHA256 over `${ts}.${raw}`,
>   headers `x-sched-timestamp`/`x-sched-signature`, minimal body `{"fire_id": ...}` so a
>   dedupe failure can't re-run a 10-min turn) — expect `{ok, deduped:true}` and one local
>   row. Working reference: `dojo/tests/curiosity-phase5/walkthrough.mjs` check 5.
> - `outcome` flips to `emitted: agent_prompt` only AFTER the full agent turn — on hosted
>   hardware budget up to 16 min before declaring a fire stuck. The 02:00 fire lands in
>   quiet hours: morning thought queues and drains after 08:00 (drain points: any
>   share_thought call, or plugin load on machine wake).

> **Phase-6 learnings:**
> - **The model has no clock — recency-dependent prompts need server-computed ages.**
>   Luna's system prompt injects no current date/time, so a fired turn cannot judge
>   "was this edited today?" from raw ISO timestamps (check 7 failed three ways on this
>   before the fix). plugin-wiki now returns `age_days` in page meta and the dream gate
>   is numeric ("every page age_days >= 1 → quiet night"). **Consider in this phase's
>   plugin-scheduler touch:** prepend the fire time to the emitted message ("A scheduled
>   trigger just fired at <iso local>") — cheap, and gives every scheduled routine a
>   clock anchor without a core change.
> - **`outcome: "emitted: agent_prompt"` is recorded even when the fired agent turn dies**
>   (observed twice in phase-6 runs: transient Anthropic `ConnectTimeout` killed the turn,
>   fire row still said `emitted`). A dead fired turn is indistinguishable from a healthy
>   no-op by outcome alone. **Add to this phase's scope (small plugin-scheduler change):**
>   catch turn exceptions in the fire handler and record `outcome: "error: <ExcType>"` —
>   production monitoring depends on it, and phase 7 touches plugin-scheduler anyway.
>   Verification in step 5 must NOT trust outcome: require an assistant message after the
>   fire's injected user message (the phase-6 walkthrough's `fireTrigger` turned-flag
>   pattern is the working reference).
> - Chat turns are SSE-scoped (cancelled when the owner's tab closes) but scheduler fires
>   are background tasks — they survive. On hosted, a fire arriving while the owner has a
>   chat open injects into the most recent active conversation; harmless, noted post-v1.
> - Scheduler fires land in the most recent active conversation. During hosted onboarding
>   (owner installs, adopts mission, walks away mid-setup) the 02:00 fire lands in the
>   "Getting started" conversation with the setup addendum active — works, but consider
>   suppressing the onboarding addendum on fired turns post-v1.

> **Phase-2 learnings:** the scheduler HMAC client has a 10s timeout that trips transiently
> when the Luna event loop is congested (observed in dev under concurrent turns; curiosity
> wraps calls in `_retry_tool`, 3 attempts with backoff). In production, hosted latency adds
> to this — when verifying step 5, watch for `{"error": ""}`-shaped results (a bare httpx
> timeout str()s to empty) and confirm the retry path absorbs them.
