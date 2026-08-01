# Phase 9.002 — Missions UI: execution summary

**Shipped:** plugin-curiosity **0.8.0** (`fc09410`) + **0.8.1** (`7526196`), both
pushed to `huemorgan2/plugin-curiosity` and published to
`marketplaces.com.ai/mp/official` (0.8.1 index sha256
`555bb9275a789e…789d`, verified against the local zip).

## What was built (0.8.0)

- **Missions pane** — `sidebar_sections=[SidebarSection(id="missions",
  label="Missions", icon="target", sort_order=45)]`; self-contained static
  app (`ui/index.html`, `app.js`, `style.css`) served from plugin routes at
  `/api/p/plugin-curiosity/ui/` with cache-busting `?v=<manifest.version>`
  stamps and the luna-ui-ready / luna-plugin-event live bridge.
- **Overview + drilldown API** — `GET /missions/overview` (auth'd): mission,
  setup ladder (stages/percent), gap board, goals, loops, value log, plan
  changes, heartbeats (latest+recent), pace (server-computed band+reasons),
  sentiment (deterministic band behind the agent's own morale words),
  needs_from_you (incl. the S2 ratify CTA), 9-slot wiki shelf, NOC wall,
  activity timeline. `GET /missions/{id}` full record; garbage ids 404.
- **Hard dependency gate** — manifest `depends_on=["plugin-wiki",
  "plugin-scheduler"]` + runtime gate (`missing_dependencies` probes
  provider:wiki / tool:trigger_create). Blocked → inert: no tools, no
  sends, advisory `dependency_blocked` flag, one-time muted "Curiosity is
  paused" notice, agent-facing PAUSED fragment; pane still serves a
  blocked screen. Serving-loop re-check after `SYNC_ON_LOAD_DELAY_S` is
  authoritative (load-order races).
- **Heartbeat telemetry** — `heartbeat_report(streak, gaps_open, wobbles,
  morale, note)` auto-approve tool ends every heartbeat fire; rows in
  `curiosity_heartbeats`; morale is personality-voiced verbatim, sentiment
  band computed from the numbers.

## 0.8.1 — the duplicate-heartbeat fix

Prod e2e run 1 (17/18) caught it: the mission-adoption chat turn and the
detached kickoff turn both obeyed list-before-create and still authored two
`curiosity-setup-heartbeat` triggers ~2 min apart (TOCTOU — prompt
discipline is probabilistic across concurrent turns).

Fix, two halves:

1. **Code reaper** `research.dedupe_heartbeats(ctx)` — raw-handler
   `trigger_list`/`trigger_delete` (bypasses trigger_delete's
   `prompt_always` approval policy, so cleanup never parks a turn),
   deletes extras keeping the OLDEST (its fire history carries the
   streak). Runs on load (after mission check) and after every
   `heartbeat_report`.
2. **Single-creator contract** — `HEARTBEAT_CONTRACT` now says the trigger
   is born ONLY in the kickoff (or a recreate nudge), never in an ordinary
   conversation turn; kickoff step 9 marks itself as THE creation moment.

The invariant is **convergence**, not exactly-once-at-creation: duplicates
can still appear under concurrent turns; they die at the next
heartbeat_report or restart. Verified live on production: after a restart
of the e2e Luna, the on-load reaper deleted the newer duplicate and kept
the oldest.

## Verification

- **Unit**: 159 passed (154 from 0.8.0 + 5 new: reaper keep-oldest /
  no-op / unknowable-without-scheduler, report-triggers-reaper,
  single-creator contract clauses).
- **Local dojo** (`luna/dojo/tests/curiosity-phase9/missions-ui-e2e.mjs`,
  24 checks, fresh Luna :8001 + local scheduler-service): pane registry +
  versioned assets + bridge, auth gate, pre-mission contract, adoption →
  S2, overview contract (checklist 50%, ratify CTA, 9-slot shelf, gap
  board, pace+sentiment), agent-authored heartbeat, prompted pulse-check →
  telemetry row + morale on the pane, drilldown + 404, and the
  dependency-gate leg (in-tree curiosity+scheduler parked, managed copy →
  blocked overview names plugin-scheduler, pane still served, one-time
  muted notice, agent explains the pause, gate reopens after restore).
  Result: **24/24** on 0.8.0; rerun on 0.8.1: **24/24**.
- **Production e2e** (`missions-ui-prod.mjs`, 19 checks, fresh Luna :8002,
  artifact installed at runtime from marketplaces.com.ai, production
  scheduler luna-scheduler.onrender.com through a cloudflared tunnel,
  disposable account `curiosity-9002-e2e`, disposable owner "sam"):
  baseline absent → runtime install 0.8.1 → pane advertised + served
  WITHOUT restart → adoption → S2 → overview contract → heartbeat authored
  on the prod scheduler → run-now fire delivered through the tunnel →
  heartbeat_report row → **triggers converge to exactly one (reaper,
  oldest kept)** → morale verbatim on the pane → drilldown + 404.
  Result: **19/19**. The race fired again in the final run (2 heartbeats
  authored) and the report-path reaper converged it live — both reaper
  paths are now proven on production.

## Run history (prod e2e)

| run | version | result | note |
|---|---|---|---|
| 1 | 0.8.0 | 17/18 | FAIL: two heartbeat triggers (the TOCTOU race) |
| 2 | 0.8.1 | 14/18 | test bugs (stale 0.8.0 literals, exactly-once asserted pre-reaper) + runner restarted the Luna mid-fire, killing the report turn; the restart proved the on-load reaper live (2→1, oldest kept) |
| 3 | 0.8.1 | aborted | killed by the runner prematurely (background tasks are not bound by the Bash timeout param — lesson recorded) |
| 4 | 0.8.1 | **19/19** | test restructured to the real contract: check 13 ≥1 authored, check 16 convergence to exactly one after the fire's report (race occurred: 2 authored → reaper kept oldest) |

## Cleanup

- prod scheduler account `curiosity-9002-e2e` deleted (admin key), tunnel
  killed, QA Lunas :8001/:8002 stopped, in-tree symlinks restored.
