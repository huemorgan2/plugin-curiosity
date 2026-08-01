# Phase 7 — owner handoff: what's live, what's left

> Written 2026-07-08. luna-service is read-only for Claude, so the items under
> "Left for you" are documented here instead of committed anywhere.

## Already live (verified today)

- **scheduler-service is deployed and healthy**: https://luna-scheduler.onrender.com
  (`srv-d96jd35aeets73dfkki0`, Oregon, plan starter, autodeploys from
  `huemorgan/luna-scheduler-service` main — currently at `de025a8`, the 0.2.0
  bounded-runs release). `GET /health` → `{"status":"ok","db":true}`. Postgres:
  `luna-scheduler-db` (`dpg-d96j08vavr4c739jcu90-a`, basic-256mb, Oregon).
  `ADMIN_KEY` is set in the service's Render env vars (dashboard → luna-scheduler
  → Environment); it is not written down anywhere else.
- **luna-service appears already wired**: the production service has an account
  `vaselin-test-0-13-016-8-5-pluginsdk-9849753-2` with
  `fire_url = https://luna.com.ai/api/webhooks/scheduler/<slug>/fire`, created
  2026-07-07 18:23 UTC — i.e. a hosted Luna already auto-provisioned through the
  relay, which only works if `CLOUD_SCHEDULER_SERVICE_URL` and
  `CLOUD_SCHEDULER_SERVICE_ADMIN_KEY` are populated in luna-service.
- **End-to-end against the production service passed** (from a local Luna behind a
  cloudflared tunnel, account `curiosity-e2e`, deleted after the test):
  - curiosity 0.4.x sync-on-load re-registered `curiosity-daily-research` (09:00)
    and `curiosity-nightly-dream` (02:00) on the production service automatically
    after `manual-config` — plan step 4 needs no manual `trigger_create`.
  - run-now fire → delivered (1 attempt, HTTP 200) → HMAC verified → real agent
    turn; the nightly-dream fire ran the true dream prompt and the clock-free
    gate held ("Every page has `age_days >= 3` … Quiet night").
  - signed replay of the same `fire_id` → `{"ok":true,"deduped":true}`; tampered
    signature → 403; `daily_fire_cap` 200 on the account.
- **Plugins published to marketplaces.com.ai `mp/official`**:
  `plugin-scheduler 0.2.1`, `plugin-curiosity 0.4.2`, `plugin-wiki 0.3.1`.
  0.2.1 is new today: fired prompts now carry the fire time ("just fired at
  <iso> (UTC)" — the agent has no clock, this is its only "now" anchor), and a
  dead fired turn now records `outcome: "error: <ExcType>: …"` instead of
  masquerading as `emitted: agent_prompt`. Repo pushed
  (`huemorgan/luna-scheduler-plugin` `b5d2b11`).

## Left for you

1. **Confirm luna-service config** (2 min): `scheduler_service_url =
   https://luna-scheduler.onrender.com` and the admin key matching the Render
   env var. The existing relay account suggests this is already done.
2. **Install the stack on the real hosted Luna** from `mp/official`:
   plugin-scheduler 0.2.1, plugin-wiki 0.3.1, plugin-curiosity 0.4.2 (curiosity
   needs wiki + scheduler + web-access). On hosted, the scheduler settings tab's
   **Connect** button auto-provisions via `/api/agent/scheduler/connect`. Then
   state a mission (or reboot if one exists) — sync-on-load registers both
   triggers; check the settings tab shows them.
3. **The one unverifiable-from-here beat: sleeping-machine wake.** Let the hosted
   machine scale down overnight and confirm the 02:00 dream fire wakes it via the
   relay and a turn actually runs. Do not trust `outcome` alone —
   with plugin-scheduler **< 0.2.1** a dead turn still records
   `emitted: agent_prompt`; on 0.2.1 look for `error:` outcomes in the fires
   panel, or simply check an assistant message follows the fire's muted line.
4. **Merge luna core `curiosity-dev` into main** when ready — hosted error
   outcomes need `b29f857` (muted.py surfaces turn failure as `{"error": ...}`;
   without it 0.2.1 still can't tell a dead hosted turn from silence). The
   Render `luna` service (luna-kp8e.onrender.com) autodeploys from
   `novalystrix/luna` main, so the merge ships it there too. I did not touch
   that instance (it has live WhatsApp wiring).

## Notes

- The dev scheduler-service on :8123 and the dev `fresh-luna` account are
  untouched; the local QA Luna (`luna_fresh` DB, port 8001) was stopped after
  verification and its plugin config restored to the dev service.
- Backoff/dead-letter: delivery retries on `30,120,600,1800,3600,3600`; an
  unreachable fire_url goes dead after ~2.7h of attempts. That is why the test
  account was deleted rather than left pointing at an expired tunnel.
