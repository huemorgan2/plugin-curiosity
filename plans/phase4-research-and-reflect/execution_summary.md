# Phase 4 — execution summary

**Status: DONE.** Dojo walkthrough 12/12 (run `mrbvlhp4`, 2026-07-08, daytime branch) after
14 runs of environment + harness debugging; every failure along the way was infrastructure
or test-harness, never the plugin code — the guardrails behaved correctly from run 7 onward.

## What was done

### plugin-scheduler 0.1.2 — `trigger_update`
- scheduler-service already supported `PATCH /accounts/{id}/triggers/{trigger_id}`
  (app/api/account.py) — only the plugin side was missing.
- Added `client.update_trigger()` and a 7th tool `trigger_update`
  (auto_approve, low risk; params: `id` + optional `name/schedule_expr/target/inputs/timezone`).
  Updates in place — same trigger id, fire history preserved, no delete/recreate churn.
- Manifest bumped (`tools = 7`), tests: PATCH branch in the FakeService +
  `test_update_in_place`. 26/26 green.

### plugin-curiosity 0.3.0 — research, comms, kickoff
- **`comms.py`** (was an empty phase-0 scaffold): `share_thought` tool with three guardrails —
  1. *grounding*: body must cite a wiki page (`[[slug]]`) or a URL, else rejected;
  2. *daily cap*: 1 routine thought/day (local-midnight accounting); kinds `kickoff`/`dream` exempt;
  3. *quiet hours* 21:00–08:00 local: thoughts queue instead of posting; queue drains on the
     next share call, on plugin load, or via `POST /api/p/plugin-curiosity/comms/drain`;
     drained routine thoughts consume the day's cap; excess stays queued.
  Posting = fire-and-forget `ctx.send_muted_message(channel="moment", source="curiosity",
  tools=[wiki reads + mission_get])` → badged 💭 Reflection bubble.
  New `Reflection` table (`curiosity_reflections`) is the queue + audit log.
- **`research.py`** (was empty scaffold):
  - *Kickoff*: `mission_set` → `spawn_kickoff` (create_task; contextvars pin the mission
    conversation) → 3s delay → muted moment with a research-scoped tool allowlist
    (web_search/fetch + wiki write tools; **no** share_thought — the badged reply IS the
    artifact; no playbook_* — they're chat_only). Artifact shape: **Brief / Quick win /
    Open questions**, cited.
  - *Daily research target* (`DAILY_RESEARCH_TARGET`): self-contained agent_prompt that
    re-reads the mission at fire time (mission_get), picks ONE gap, does web research,
    writes cited wiki content, uses share_thought only if genuinely notable, and records
    playbook ideas as open questions (playbook tools are chat_only).
- **`mission.py`**: `_sync_schedules` now maps existing triggers by name and PATCHes a stale
  target via `trigger_update` when available (tolerates older scheduler: create-only).
  The phase-2 placeholder research target migrates in place. `mission_refine` also re-syncs.
- Routes: `POST /comms/drain`, `GET /comms/reflections`, and `POST /comms/share` (owner
  route through the same `share()` core — added late in the phase because the agent
  rightly refuses to call share_thought with deliberately invalid input; deliberate-
  guardrail-violation tests must bypass the LLM, not persuade it).

## Test results
- plugin-curiosity 22/22 (9 comms + 6 research + prior), plugin-scheduler 26/26,
  scheduler-service 48/48, plugin-wiki 17/17, core muted/reflection regression 15/15.
- Dojo walkthrough `curiosity-phase4/walkthrough.mjs` (headed): **12/12** — mission
  adoption, in-place trigger update (same id, no dupes), kickoff muted line + badged
  artifact (brief/quick win/questions + URL), wiki open-questions growth, guardrail post +
  daily-cap block + grounding rejection, run-now fire `outcome=emitted`, 💭 badge and
  collapsed muted rows in the browser.

## What was encountered / learned

1. **Kickoff reaction turns take >8 minutes.** Real web research + wiki writes + artifact
   composition ran past the walkthrough's original 8-min poll; the reply landed (~1.7k chars,
   correctly `source="curiosity"`), just late. Poll extended to 16 min. Any dojo check that
   waits on a research-grade muted turn needs that budget.
2. **Never overlap heavy turns with chat checks.** While the kickoff turn was still running,
   the subsequent chat checks starved (empty replies, retries double-queued thoughts,
   postgres checkpoint sync hit 30s, transient 500s). The DB never crashed this time (unlike
   phase-2's concurrent-pytest incident) but I/O contention alone was enough to break checks.
   The walkthrough now blocks on kickoff completion before moving on.
3. **`GET /api/p/plugin-scheduler/fires` returns `{local, service}`, not `{fires}`** — local
   rows carry `fire_id` and plugin-side `outcome` (`emitted|deduped|failed`). The dojo check
   originally read a nonexistent `.fires` array, so it could never pass. Fixed; phase-5's
   dedupe check should assert `outcome=deduped` on a replayed fire via the same route.
4. **chatExpect markers must be explicit.** share_thought results don't echo the body, so
   "reply with the raw JSON verbatim" contained no run nonce and the reply matcher never hit.
   Prompts now demand a `RESULT-${RUN}:` prefix line. Rule: every dojo chat prompt must
   instruct a marker-bearing reply.
5. **Time-aware walkthroughs work.** Quiet-hours runs (local hour < 8) exercise queue +
   drain-refusal; daytime runs exercise post + cap. Both branches live in one script.
6. **page.goto needs retry.** Right after heavy turns the UI can take >30s to serve; goto
   is now 4×60s with backoff (both in newChatSend and the browser checks).
7. **luna-postgres (docker) crashes under load were an fsync problem, not a fluke.** A
   backend process exits (code 2) under heavy concurrent I/O, and crash recovery then
   re-fsyncs the entire data directory — 5+ minutes of "recovery mode" 500s on Docker for
   Mac's slow disk (observed fsync elapsed 298s). This killed two walkthrough runs (and
   phase-2's earlier one). Fix for the dev DB: `ALTER SYSTEM SET fsync=off;
   synchronous_commit=off; full_page_writes=off` + `pg_reload_conf()` — removes the I/O
   stalls that trigger the crash and makes any recovery near-instant. Dev-only setting; do
   NOT carry to production.
8. **Long runs cross the quiet-hours boundary.** `quiet` was computed once at script start;
   a run starting 07:40 reaches check 5 after 08:00 and asserts the wrong branch. The
   walkthrough now recomputes `isQuiet()` at check time; time-sensitive runs should also
   clear `curiosity_reflections` first for a deterministic cap/queue baseline.

9. **Dojo sends must deep-link, not click "New chat".** The button's `newConversation()`
   races the initial-load effect (`selectConversation(c[0])` reverts the selection), so
   typed prompts silently land in the previously open conversation. Fix: create the
   conversation via `POST /api/conversations` (body `{}` required — 422 without it) and
   `page.goto(BASE + '/chat/<id>')`; the URL route is trusted unconditionally (007.013-D).
   `chatExpect` then polls that conv id directly — no title matching.
10. **While the panel-global `streaming` flag is set, Enter queues instead of sending**
   (ChatPanel 008.9) — and a queued chip in a fresh conversation never delivers. A long
   moment turn outlives its visible reply, so wait for the idle composer placeholder
   ("Message Luna…") before typing.
11. **The agent treats terse harness prompts as prompt injection** ("fake reference ID",
   "manufactured urgency") and refuses — increasingly firmly on retries. Honest owner
   framing ("I'm your owner, running an automated guardrail test (dojo run X)") gets
   compliance for legitimate asks; but asking it to *deliberately misuse a tool*
   (uncited share_thought) is refused under every framing — "the guardrail is a contract
   I follow, not one I probe." Correct behavior; test such paths via owner routes.
12. **Environment kills more runs than code.** Beyond the fsync fix: two unrelated
   containers (cloud-cp-postgres 1274% CPU, sched-postgres 538%) starved the 8-CPU Docker
   VM until restarted (sched-postgres also got fsync=off); the Mac clamshell-slept on
   battery mid-run (ERR_NETWORK_IO_SUSPENDED, fire stuck at outcome=received); a reboot
   wiped the stack; and after a reboot the scheduler delivers a *catch-up* daily fire at
   Luna boot whose research turn can consume the daily reflection cap before the
   walkthrough's check — clear `curiosity_reflections` after any restart, and run
   `caffeinate -dims`.

## For the future

- **Phase 5 (dream):** the dream fires at 02:00 = quiet hours, so a share_thought from the
  dream turn queues naturally and drains after 08:00 — "morning thought" comes free from the
  phase-4 guardrails. Decide whether the dream should use kind="dream" (cap-exempt) via
  `comms.share(...)` internally rather than the routine-kind tool.
  `_sync_schedules` only runs on mission_set/mission_refine — consider a sync-on-load task
  (like `_drain_on_load`) so a plugin upgrade refreshes trigger targets for an existing mission.
- **Walkthrough budget:** a full phase-4-style run is ~35–45 min wall-clock (one kickoff turn,
  several chat turns, one fired research turn). Schedule accordingly; never run core pytest
  concurrently.
- Stale state accumulates across runs (queued reflections, open questions, missions) — checks
  must be growth-based (before/after within the run), never absolute.
