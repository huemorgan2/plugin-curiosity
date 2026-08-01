# Phase 7 — execution summary

> Status: **COMPLETE (autonomous scope)** — production scheduler live and verified
> end to end; plugins shipped; the two owner-side steps are documented in
> [owner_handoff.md](owner_handoff.md). 2026-07-08.

## What was done

1. **Scoping found most of step 1 already done.** Render CLI was authenticated
   (workspace `tea-d5co7dbe5dus738p4sjg`); `luna-scheduler-db` and the
   `luna-scheduler` web service already existed (created 2026-07-07), the service
   live on the latest `main` (`de025a8`, 0.2.0) and healthy
   (`{"status":"ok","db":true}` at https://luna-scheduler.onrender.com/health).
   Better: the production service already held an account whose `fire_url` is the
   **luna.com.ai relay** — so luna-service's `CLOUD_SCHEDULER_SERVICE_*` config
   is evidently populated and a hosted Luna has already auto-provisioned through
   it. "Deploy + wire" collapsed to "verify + ship the plugin fix".

2. **The plugin-scheduler change the plan added (0.2.1)** — commit `b5d2b11`,
   pushed:
   - Dead fired turns no longer record `emitted: agent_prompt`. Outcomes now
     split: `emitted` / `emitted: agent_prompt (no reply)` / `error: <ExcType>: …`
     (type name first — a bare httpx timeout `str()`s to empty, the phase-2
     `{"error": ""}` shape).
   - The emitted prompt carries the service's `fired_at`: "A scheduled trigger
     just fired at <iso> (UTC)". The agent has no clock (phase-6 finding); this
     gives every scheduled routine a "now" anchor with no core change. The
     delivery payload already included `fired_at`, so no service change either.
   - Required one small **luna core** commit on `curiosity-dev` (`b29f857`):
     `post_muted_message` swallowed `run_turn` exceptions and returned only
     `responded=False` — the producer literally could not see the death. It now
     returns `{"error": "turn failed: <ExcType>: …"}` too (backward-compatible;
     callers already check `.get("error")`).
   - Tests: plugin 31/31 (4 new: fired_at in prompt, error outcome, silent-turn
     outcome, exc-type outcome), luna muted suites 23/23 untouched.

3. **Verified on a real running Luna before shipping** (rule): restarted the
   run-14 `luna_fresh` Luna on :8001, one-shot ping trigger → the muted line
   showed the UTC anchor and the agent echoed the timestamp back; outcome
   recorded correctly.

4. **End-to-end against the production service** — the plan's step 5, adapted to
   what's reachable from here (a laptop Luna is not publicly addressable, so a
   cloudflared quick tunnel stood in for the relay):
   - admin API: created `curiosity-e2e` account (fire_url = tunnel).
   - `manual-config` re-pointed the local plugin at
     https://luna-scheduler.onrender.com; **restart → curiosity sync-on-load
     registered both triggers on the production service automatically** (research
     09:00, dream 02:00) — plan step 4 confirmed to need zero manual calls.
   - ping fire: service `delivered` (1 attempt, HTTP 200) → HMAC verified →
     agent turn → reply `PROD-E2E-OK <fired_at>`.
   - **real nightly-dream fire**: full dream prompt ran and the clock-free gate
     held — "Every page has `age_days >= 3` … Quiet night — nothing to
     consolidate" (pages still backdated from phase-6 staging, so quiet-night was
     the correct branch). Hosted-path behavior matches phase-6 validation.
   - dedupe: signed replay of the same `fire_id` → `{"ok":true,"deduped":true}`;
     tampered signature → 403; cap present (200/day).
   - cleanup: local plugin restored to the dev scheduler, `curiosity-e2e`
     deleted from production (a dead tunnel would have generated daily
     retry/dead-letter noise), tunnel killed, QA Luna stopped.

5. **Shipped**: pushed `huemorgan/luna-scheduler-plugin` main; published to
   marketplaces.com.ai `mp/official`: **plugin-scheduler 0.2.1**,
   **plugin-curiosity 0.4.2**, **plugin-wiki 0.3.1** (the latter two were never
   on the marketplace; curiosity/wiki repos have no git remote, so publish was
   the shipping act). Index verified live.

## What was encountered

- Two "already in use" surprises (DB, then service name) — the deployment
  existed since yesterday. Lesson: enumerate before creating; Render's default
  service list hid the service until queried by name.
- The Render workspace also runs a **live hosted Luna** (`luna-kp8e.onrender.com`,
  novalystrix/luna, WhatsApp-wired). Deliberately not touched — it's a
  production-ish instance and not the plan's hosted target.
- `render` CLI v2 can't create services; the REST API with the CLI's stored key
  can. `DATABASE_URL` had to be set as a plain env var in
  `postgresql+asyncpg://` form — the app does no scheme normalization and
  Render's `fromDatabase` hands out `postgresql://`.
- The dead-turn root cause was one level deeper than the plan assumed: the
  plugin's exception handler was fine; it was `post_muted_message` in core that
  ate the exception. The plan's "small plugin-scheduler change" needed a
  two-line core change to be true at all.

## What was learned

- **Verify-before-create applies to infrastructure**: half this phase's plan was
  already done by the time it ran. Enumerating accounts on the production
  service was the single most informative call of the phase — it proved the
  luna-service wiring (the one step believed owner-blocked) was already live.
- **An error a caller can't see doesn't exist.** Same shape as phase-6's no-clock
  lesson: the fire outcome was "decidable" only if the layer below actually
  surfaced failure. When adding observability, walk the whole chain the signal
  must travel.
- A quick cloudflared tunnel turns "can't verify production delivery to a laptop"
  into a 30-second job; delete the service-side account afterwards or the retry
  scheduler punishes you for hours.

## For the future (post-v1 backlog, phase 7 was the last planned phase)

- Owner-side remainder (handoff doc): confirm luna-service config, install the
  three plugins on the real hosted agent, observe one sleeping-machine wake at
  02:00, and merge `curiosity-dev` (esp. `b29f857`) into `novalystrix/luna` main
  so hosted error outcomes work.
- Carried from phase 6, unchanged: approval-parked turns need a UI hint + TTL;
  SSE-scoped chat turns; onboarding addendum on fired turns; approval-card dedup.
- New: consider a scheduler-service admin alert (or plugin badge) when a fire
  ends `dead` or `error:` — the data is now recorded; nothing reads it yet.
- Autonomy ceiling (rung 4 auto / rung 5) remains a policy flip on the phase-2
  rails, untouched by this phase.
