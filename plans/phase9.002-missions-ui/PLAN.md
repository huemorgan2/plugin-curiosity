# Phase 9.002 — Missions: a mission-control pane for curiosity

**Goal:** a left-pane UI area ("Missions") that makes the agent's inner
workings legible — what the mission is, where the agent is in its cycle,
what it's doing, what it needs, and how well it's doing. Plus: curiosity
becomes formally dependent on plugin-wiki and plugin-scheduler — without
them it does not run.

**Version:** plugin-curiosity 0.8.0 (new UI surface + dependency gate).

---

## 1. How the pane plugs in (mechanism, already exists in core)

No Luna-core changes needed. The shell already supports plugin-owned panes:

- Manifest declares `sidebar_sections=[SidebarSection(id="missions",
  label="Missions", icon="target", sort_order=…)]` (`base.py:196`).
- `plugin-webui` serves the registry (`GET /api/ui/plugins`); the shell
  renders our pane as a themed iframe at `/api/p/plugin-curiosity/ui/`
  (`Shell.tsx:495`), with the postMessage theme/auth bridge.
- Curiosity already has `routes_module` — we add `GET /ui/` (static,
  self-contained HTML/JS served from `plugin_curiosity/ui/`, the
  plugin-marketplace pattern) and the JSON endpoints below.

Marketplace plugins can't compile into core's Vite bundle, so the pane is a
**single self-contained static app** (no build step, no CDN deps) — same
delivery as plugin-marketplace's pane.

## 2. Hard dependency: wiki + scheduler or don't run

Today wiki is a soft `capabilities=["wiki"]` edge and scheduler is entirely
undeclared; every module feature-detects and degrades. 9.002 flips this:
curiosity's whole model (knowledge lives in wiki pages, drive lives in
triggers) is meaningless without them.

**Why hard, not soft:** the pane's whole value is showing wiki + scheduler
data (knowledge pages, triggers, fires) inside curiosity's UI. If they can
be absent, every pane panel and every prompt surface needs a degraded
branch — permanent complexity for a configuration that should never exist.
Depending on them lets the pane treat wiki pages and trigger schedules as
first-class, always-present data.

- **Manifest:** `depends_on=["plugin-wiki", "plugin-scheduler"]` in the
  PluginManifest + `luna-plugin.toml`. The loader enforces presence for
  in-tree loads (`loader.py:1092`); for managed/marketplace installs it
  does not raise — so:
- **Runtime gate (the real guard):** `on_load` checks
  `provider_registry.get("wiki")` and `tool_registry.get("trigger_create")`.
  If either is missing → curiosity goes **inert**: registers NO tools, NO
  moments, NO triggers, and sets a `dependency_blocked` flag.
- **The USER knows (UI):** the pane still loads and shows a
  dependency-blocked screen — which dependency is missing, why curiosity
  needs it (one line each: "wiki is where I keep everything I learn",
  "scheduler is what lets me act on my own"), and install deep-links to
  the marketplace pane.
- **The AGENT knows:** while blocked, curiosity registers exactly one
  prompt fragment: "Curiosity is installed but PAUSED — it requires
  plugin-wiki (my knowledge store) and plugin-scheduler (my own drive).
  Missing: <list>. If the owner asks about missions or growth work, say
  so and point them at the marketplace." Plus a one-time muted message on
  first blocked load. The agent can EXPLAIN its own paused state, same
  legibility bar as the two-phase model.
- Feature-detection branches inside modules stay (defense in depth) but are
  no longer reachable in normal operation.
- Optional core follow-up (separate luna plan, not in 9.002): marketplace
  install flow surfacing `depends_on` as "also installs X, Y".

## 3. The data the pane shows — and where each piece comes from

One aggregate endpoint: `GET /api/p/plugin-curiosity/missions/overview`
(plus `GET /missions/{id}` for history detail). Server-side JSON assembled
from plugin-owned tables + wiki provider + scheduler tools. Nothing in the
UI parses agent prose except page excerpts.

| Pane element | Source |
|---|---|
| Missions list (active first, history below) | `curiosity_missions` (all rows; `active` flag; statement, phase, stage, autonomy rung, risk ceiling, created_at) |
| Phase-of-cycle dial (setup → work) | `agent_phase`, `phase_entered_at`; server-computed phase age |
| Setup completion % + "what setup entails" checklist | stage ladder S0–S5 (single-sourced `SETUP_STAGE_DEFS`) rendered as a checklist with the CURRENT stage highlighted; % = stage weight + scope ledger ratio (`competent / total` from `curiosity_scopes`) |
| Gap board ("am I qualified?") | `curiosity_scopes` by status: missing / in_progress / competent, each with kind, why, evidence |
| Progress & tasks | `curiosity_goals` (statement, why, target_date, status, progress_note) — this IS the task view; goals link to criteria |
| Wiki knowledge summary | fixed page set via wiki provider: `mission` (hub), `role-charter`, `success-criteria`, `mission-domain`, `mission-goals`, `open-loops`, `value-log`, `mission-open-questions`, `setup-heartbeat` — card per page: title, age_days, excerpt, deep-link to the wiki pane |
| Recent actions log | merged timeline: `curiosity_reflections` (kickoff/routine/dream posts), `curiosity_plan_changes`, `curiosity_value_log`, loop transitions — newest first, kind-tagged |
| Future plans | goals with target dates + `curiosity_loops.next_nudge_at` + upcoming trigger fires (trigger_list → name, cadence, next fire) — one "what happens next" timeline |
| Heartbeat pulse | trigger_list: `curiosity-setup-heartbeat` present/cadence; latest verdict line from [[setup-heartbeat]]; streak (see §5) |
| What I need from you | open `curiosity_loops` where kind=ask/waiting_on + the ratification CTA when stage=S2 (button deep-links into chat with a prefilled ratification prompt) |
| Contentment gauge (§5) | server-computed + agent-reported |
| NOC role wall (§6) | success-criteria (structured, see §6) scored by weekly review + value-log evidence |

## 4. Mission-control layout (the cool part)

Dark "mission control" dashboard, three zones:

```
┌────────────────────────────────────────────────────────────┐
│  MISSION: grow the ceramics studio        ● SETUP  S2/S5   │
│  phase dial   setup ▓▓▓▓▓░░ 64%   day 3   rung 2  risk low │
├──────────────┬───────────────────────────┬─────────────────┤
│ SETUP ENTAILS│  GAP BOARD                │ HEARTBEAT       │
│ ☑ S0 adopted │  missing(3) in-prog(5)    │ ♥ every 3h      │
│ ☑ S1 charter │  competent(2)             │ streak 2/5      │
│ ▶ S2 ratify… │  [scope cards]            │ last: no wobble │
│ ☐ S3 …       │                           │ next fire 14:00 │
├──────────────┴──────────────┬────────────┴─────────────────┤
│ NEEDS FROM YOU (2)          │  CONTENTMENT  ◐ steady       │
│ ▸ ratify charter  [review]  │  pace: on-track (S2, day 3)  │
│ ▸ instagram access [answer] │  blocked-on-owner: 1         │
├─────────────────────────────┴──────────────────────────────┤
│ ACTIVITY  ── log ──────────────  NEXT ── plans ──────────  │
│ 10:02 heartbeat: streak 2     │  today  heartbeat ×4       │
│ 09:00 daily research: …       │  mon    weekly review      │
│ yst   value: shipped hashtag… │  jul 14 goal: 20 listings  │
└─────────────────────────────────────────────────────────────┘
```

In WORK phase the top band swaps: stage ladder → **NOC role wall**
(§6), heartbeat panel shows the demoted maintenance cadence.

Additional surfaces considered and IN:
- **Wiki knowledge shelf** — the 9-page card row (age-tinted: fresh/stale).
- **Mission history** — past missions collapsed at the bottom, with their
  final value-log tallies (what the agent accomplished before re-missioning).
- **Autonomy + risk chips** — rung 1-4 and risk ceiling, always visible;
  legibility = trust.
- **Open questions to owner** — from [[mission-open-questions]] loops,
  each with an "answer in chat" deep-link.

**Live, not polled.** Core already ships a generic plugin-iframe live
bridge (`ui/src/lib/pluginBridge.ts`): a plugin emits
`ui.plugin.event {plugin, event, payload}` on the bus → global SSE →
postMessage into our iframe (buffered until `luna-ui-ready`, FIFO,
replayed in order). Curiosity emits on: heartbeat fire recorded, stage
change, goal update, loop opened/closed, value logged, phase advance.
The pane updates in real time — the heartbeat dot literally pulses when
a fire lands. A slow poll (60s) stays as fallback/initial load.

Considered and OUT (for now): editing anything from the pane (read-only
v1 — the chat is the control channel; one exception: the ratify/answer
deep-links); charts of value over time (needs more history to be
meaningful).

## 4.5 Design language — it must look like Luna, and explain itself

Luna's visual identity (from `ui/src/index.css`): **Inter**, dark-first
ink neutrals (`ink-900/950` surfaces, soft `rgba(255,255,255,.06)`
borders), the **luna violet** family (`#8b5cf6`) as accent, and the
signature violet→pink→rose gradient reserved for hero text. The
marketplace pane already proves the pattern in plain CSS (`--bg #0b0e14`,
`--accent #7c6cff`); we ship the same token set so the pane is
indistinguishable from core UI.

Mission-control on top of that, disciplined:
- **One hero element:** the mission statement in the gradient. Everything
  else is quiet ink + one accent — a control room, not a dashboard-vendor
  demo. Status lights (`ok #3ad29f`, amber `#f5a524`, red) are the ONLY
  saturated non-violet colors, so state reads at a glance.
- **Motion = meaning only:** the heartbeat dot pulses once per real fire
  (live bridge event); numbers tick when they change; nothing else moves.
- **Self-explanatory, three layers:** (1) every panel has a plain-words
  subtitle ("Gaps — what I still need before I'm qualified"); (2) every
  metric has a hover/tap popover saying HOW it's computed ("streak =
  consecutive heartbeat fires with no new gaps; at 5 I propose
  graduating"); (3) empty states teach the model — a fresh install shows
  the two-phase story and "state a mission in chat to begin" instead of
  blank boxes. A first-open one-time strip explains setup → work in one
  sentence with a "how curiosity works" expander.
- **Density with hierarchy:** NOC walls fail when everything shouts.
  Type scale 12/14/15 + one 20px hero; panels breathe (16-18px padding,
  1px borders, no card shadows) — matching the marketplace pane's rhythm.

## 5. Contentment + pace (honest, not vibes)

Two-part metric, deliberately split so we never fake an emotion:

- **Pace (server-computed):** stage_age_days vs the forcing thresholds
  (S2 ratification at 3d), open-loop nudge debt (loops past
  next_nudge_at), heartbeat regularity (fires vs expected cadence).
  Bands: `ahead / on-track / dragging / stalled`.
- **Contentment (agent-reported, structured):** new tool
  `heartbeat_report(streak:int, gaps_open:int, wobbles:int, morale:str,
  note:str)` — the `HEARTBEAT_CONTRACT` gains one line: every fire ENDS
  with a heartbeat_report call (in addition to the [[setup-heartbeat]]
  verdict prose). Stored in `curiosity_flags` (latest) + appended to a
  small `curiosity_heartbeats` table (history → the streak is now data,
  not prose-parsing). The gauge shows morale + the agent's own one-line
  note ("waiting on instagram access, otherwise converging").
- **Morale vocabulary comes from the agent's personality**, not a
  hardcoded enum. The identity service (`luna/identity/service.py`,
  `PERSONALITY_FIELDS`: persona, tone, verbosity, formality, use_emoji,
  proactive) is read LIVE at the two places that need it: (a) prompt
  assembly — the heartbeat contract asks for morale "in your own voice,
  one or two words, consistent with your persona"; (b) overview render —
  the pane shows the agent's words verbatim, with a server-computed
  sentiment band behind them (positive/neutral/strained/blocked) so the
  gauge color is stable even as the vocabulary is personal. Verified:
  Luna has NO settings-change event bus today — but since nothing is
  cached, a personality change is picked up on the next prompt assembly
  and the next pane refresh with zero event plumbing. If a
  config-changed moment ever lands in core, we subscribe then.

This also upgrades convergence from prose to data: graduation proposals can
cite the real streak, and the weekly review audits report-vs-page drift.

## 6. Role wall — the NOC-style accomplishment view (work phase)

Once setup completes (phase=work), the pane's hero band becomes a
**NOC wall** — the role rendered as monitored systems, like a network
operations center: a grid of status tiles, one per success criterion,
each with a status light, last-checked stamp, and an evidence counter.

- **Tile = criterion.** Light: green `on-track` / amber `at-risk` /
  red `missed` / blue `met`. Sub-line: target + latest weekly verdict.
  Badge: value-log evidence count. Click → the criterion's history
  (weekly verdicts across time, linked evidence entries).
- **Wall header:** uptime-style counters — days in work phase, fires
  delivered vs expected (heartbeat regularity as "system health"),
  open incidents (= red tiles + stalled goals), value shipped this week.
- **Incident strip:** anything red/stalled surfaces as an incident row
  with the agent's own next action (from the goal's progress_note) —
  the wall never shows a problem without showing who owns the response.

To make tiles renderable, [[success-criteria]] gets a structured section:
kickoff drafts criteria as a markdown table (`criterion | measure |
target | horizon`) — the contract already forces the page; 9.002 forces
the SHAPE (prompt-level, like the heartbeat contract). The weekly review
appends one structured scores line per criterion (`on-track / at-risk /
met / missed` + evidence link into [[value-log]]). The pane parses only
these two structured blocks; everything else on the page stays free prose.

## 7. Work plan

- **A. Dependency gate** — manifest `depends_on`, toml mirror, on_load
  inert-mode + muted message + `dependency_blocked` flag, pane blocked
  screen. Unit tests: inert when wiki missing / scheduler missing;
  normal when both present.
- **B. Overview API** — `/missions/overview` + `/missions/{id}`;
  timeline merge, wiki page summaries (provider read + age_days),
  trigger snapshot, pace computation. Unit tests against fake registries.
- **C. Heartbeat telemetry** — `curiosity_heartbeats` table (additive),
  `heartbeat_report` tool (auto-approve), contract line, weekly-review
  drift audit. Unit tests: report round-trip, streak math, contract text.
- **D. Pane v1** — sidebar section + static app: mission header, phase
  dial, setup checklist + %, gap board, goals, needs-from-you,
  activity/next timelines, wiki shelf, contentment gauge, history.
  Luna token CSS (§4.5), live bridge events + 60s fallback poll,
  microcopy/popover/empty-state layer.
- **E. NOC role wall** — success-criteria structured-shape prompt forcing,
  weekly scores block, work-phase hero band (tiles + incident strip).
- **F. Verify** — unit suite; local dojo (extend the 9.001 walkthrough:
  after S2, fetch overview + assert pane data-contract: %, checklist,
  heartbeat pulse, needs-from-you carries the ratification ask; then
  delete a dependency and assert inert mode); production e2e (new agent,
  marketplace artifact, pane served, overview live against the
  production scheduler); ship 0.8.0.

Rough order A → C → B → D → E → F; B depends on C's table.

## 8. Decisions (resolved with owner, 2026-07-10)

1. **NOC style confirmed** — the work-phase view is the §6 role wall
   (status tiles, incident strip, uptime counters), not an OKR table.
2. **Missions = one active + history.** "The store" = `MissionStore`
   (`mission.py`), the plugin's DB layer for `curiosity_missions`: it
   keeps every mission ever set as a row but enforces exactly one
   `active=True` at a time (setting a new mission deactivates the old
   row, nothing is deleted). The pane shows the active mission as the
   dashboard + past missions as a history shelf with their final value
   tallies. Concurrent missions: out of scope for 9.002.
3. **Dependency gate: inert + visible everywhere.** Manifest
   `depends_on`, pane blocked-screen for the user, prompt fragment so
   the AGENT knows and can explain its paused state (§2). Rationale:
   the pane relies on wiki + scheduler data as first-class.
4. **Contentment vocabulary from personality** — read live from the
   identity service at prompt assembly + overview render; no event bus
   exists in core (verified) and none is needed since nothing is cached;
   a personality change lands within one pane poll (§5).
5. **Pane tech: plain hand-written JS** (see §1 — marketplace plugins
   can't join core's compiled bundle, so the pane ships as static files;
   plain JS means no build tooling in the plugin repo).
