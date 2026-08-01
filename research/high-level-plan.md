# Luna Curiosity — High-Level Implementation Plan

How we turn the [vision](./vision.md) into a shipped v1: what gets built, **where** (which
repo/folder), what changes in `luna` vs `luna-service`, and how it all works at runtime.

Grounded in the research in [results/](./results/) — read [results/README.md](./results/README.md)
first for the findings this plan assumes.

---

## 1. What We're Building

A fresh Luna, given a mission, teaches herself the domain: she researches the web, writes a
per-mission **knowledge wiki**, **dreams** nightly to consolidate learning into clear
thoughts, and **proactively reflects** to her human — earning the trust to eventually act.
v1 ships **rungs 1–3** of the autonomy ladder (Observe & learn → Reflect & advise → Draft &
recommend): **no external write execution.**

The work lands on **four surfaces** (two plugins — see §3 for why the wiki is split out):

| Surface | Role | Change size | Who owns it |
|---------|------|-------------|-------------|
| **`plugin-wiki`** (new) | Knowledge substrate: pages, `wiki_*` tools, context injection, `WikiProvider` | **Medium** | Us (new standalone repo) |
| **`plugin-curiosity`** (new) | The behavior: mission, dream, reflections; consumes the wiki | **Medium–large** | Us (new standalone repo) |
| **`luna` core** | Expose small hooks the plugins ride | **Small, surgical** | Us (editable working dir) |
| **`luna-service`** | Finish the scheduler clock-half so the nightly dream fires in production | **Medium** | luna-service owners (**planning-only for us** — read-only) |

Plus **reuse, unchanged**: `plugin-web-access` (research is agent-mediated — the LLM calls
`web_search`), `plugin-funnelfighters` (the growth-mission's read-only tools),
`plugin-interview` (the pattern we copy), and core memory.

> **Why two plugins, not one.** The wiki is the one piece that is independently valuable — a
> knowledge substrate, a *peer of memory*, that interview/playbooks/a future researcher could
> also write to. Splitting is well-supported: plugin DBs share one database (isolation is by
> table-name convention), and Luna has a sanctioned cross-plugin service seam — the
> **`ProviderRegistry`**, which is how memory itself is exposed. `plugin-wiki` registers a
> `WikiProvider`; `plugin-curiosity` consumes it. Verified against the codebase (see §3.0).

---

## 2. Where The Code Lives (project setup)

Following the established convention (each plugin is a standalone repo under `plugins/`, e.g.
`github.com/huemorgan/plugin-<name>`), Curiosity is set up as **its own folder/project**:

```
luna-plugins/
├── research/luna-curiosity/        # ← research + this plan (stays here, not shipped)
│   ├── vision.md, research_plan.md, high-level-plan.md
│   └── results/                    # the six workstream deliverables
│
├── plugins/plugin-wiki/            # ← NEW standalone repo — the knowledge substrate
│   ├── luna-plugin.toml
│   ├── wiki/
│   │   ├── __init__.py             # on_load: register wiki_* tools + WikiProvider
│   │   ├── models.py               # pages, revisions, citations tables (E4)
│   │   ├── provider.py             # WikiProvider — typed service for other plugins
│   │   ├── injection.py            # 3-tier context injection
│   │   └── routes.py               # read API + sidebar UI
│   ├── interface/webui/
│   └── tests/
│
├── plugins/plugin-curiosity/       # ← NEW standalone repo — the behavior
│   ├── luna-plugin.toml
│   ├── curiosity/
│   │   ├── __init__.py             # on_load: mission/dream/comms; get WikiProvider
│   │   ├── mission.py  dream.py  comms.py
│   │   ├── models.py               # missions, thoughts tables (E4)
│   │   ├── routes.py               # /dream fire ingress; mission read API; UI
│   │   └── state.py                # clients; NO in-process clock in hosted mode
│   ├── interface/webui/
│   └── tests/
│
├── luna/                           # core — small surgical changes (see §4)
└── luna-service/                   # scheduler clock-half — spec handed to owners (see §5)
```

**Scaffold each from `template/`** (the plugin skeleton), then copy the proven bits from
`plugins/plugin-interview/`. The research artifacts stay in `research/luna-curiosity/` — they
document the "why," they aren't shipped.

> Recommendation: keep both plugins under `plugins/` as standalone git repos like the others
> (each is its own workspace folder root, so you "open it as its own project"). Either can
> live entirely outside `luna-plugins` too — a plugin only depends on `luna_sdk`, not on this
> monorepo.

---

## 3. Component A — the two plugins

### 3.0 The seam (verified against the codebase)

Splitting the wiki from the behavior is well-supported. Grounded findings:
- **Tools are agent-only** — there is no `ctx.tools.call()`. So "research" is **agent-mediated
  by nature**: the LLM calls `web_search` (web-access) and `wiki_write_page` (wiki) itself.
  There is no deterministic `research_topic` wrapper (an earlier design error — web-access
  cannot be invoked from Python).
- **Plugin DBs share one database**; isolation is table-name convention. Cross-plugin data
  access is technically first-class.
- **`ProviderRegistry`** (`luna/luna/providers/registry.py`) is the sanctioned cross-plugin
  *Python service* seam — memory itself is exposed this way. `plugin-wiki` registers a
  `WikiProvider`; `plugin-curiosity` gets it from `ctx.providers`. Fallback if plugin-level
  registration isn't exposed: import `plugin_wiki`'s service module directly (safe — one DB).

### 3.A `plugin-wiki` — the knowledge substrate

A reusable, per-scope knowledge base (the "LLM wiki"), a peer of memory.

- **Agent tools:** `wiki_write_page`, `wiki_patch_page`, `wiki_read`, `wiki_toc`,
  `wiki_search`, `wiki_list_open_questions`. Markdown in a `body` column; append-only
  revisions; pages carry citations, confidence, open-questions; scoped by an opaque `scope_id`
  (a mission id, but the wiki doesn't care whose).
- **Context budget (R4):** **three-tier injection** — thin always-on capability note →
  per-turn TOC + relevance-ranked page *summaries* beside memory's recall → full page body
  only via the `wiki_read` tool result. Bodies are never auto-injected.
- **`WikiProvider`:** a typed Python service (read/patch pages by scope) registered in
  `ProviderRegistry`, so curiosity's deterministic dream — and any other plugin — can use the
  wiki without going through the LLM.
- **Data:** `wiki_pages`, `wiki_page_revisions`, `wiki_citations`.

### 3.B `plugin-curiosity` — the behavior

The drive that uses the wiki. Modeled on `plugin-interview`.

- **`mission.py`** — the mission object. Tools: `set_mission`, `refine_mission`,
  `get_mission`. Owns the autonomy rung + `risk_ceiling`. **Write-throughs** the mission
  statement into core's existing `Identity.mission` so the agent "owns the goal" at native
  prompt priority.
- **`dream.py`** — the nightly consolidation, fired by the scheduler at an idempotent
  `POST /api/p/plugin-curiosity/dream`. Reads/patches pages via the **`WikiProvider`** (typed,
  deterministic) — list pages touched → summarize new research → patch pages → draft one
  thought → enqueue delivery. In-plugin Python for v1 (not a playbook — see
  [results/README §3](./results/README.md)).
- **`comms.py`** — `share_thought`: posts an unprompted reflection as a `source="curiosity"`
  badged message, with cadence + noise controls (≤1/day, quiet hours). *(Spend receipts
  deferred — see §9.)*
- **Research** is not a module here — it's the agent, driven by the mission + kickoff prompt,
  calling web-access + `wiki_*` tools directly.
- **Data:** `missions`, `thoughts`.

### Behavior at load (curiosity)
Fires a one-time E11 **muted message** the moment a mission exists — a **quick-win-first**
pass: restate the mission, stub the first wiki pages, surface one sharp insight.

### Tool policies
All v1 tools across both plugins are **`auto_approve` / low-risk** — they touch only the
plugins' own tables and read-only web access. Nothing executes against the outside world at
rungs 1–3.

---

## 4. Component B — `luna` core changes (small, surgical)

The research found core **already has** most of what we need, so changes are minimal:

| Need | Status in core today | Change |
|------|---------------------|--------|
| Agent "owns the goal" in system prompt | `Identity.mission` renders at prompt slot #4 via `mission_block()` | **None** — plugin write-throughs into it |
| One-time proactive kickoff | `ctx.send_muted_message()` (E11) exists | **None** — reuse |
| Repeated unprompted reflection | `post_muted_message` persists `MessageRow(extra={source})` + emits `message.created`; `source="playbook"` badging is a precedent | **Small** — allow a `source="curiosity"` badge + a supported path for the plugin to post a reflection message (not just on-load) |
| Autonomy ladder actually gates tools | **`risk_level` is inert; only `policy` gates**, via `approval_policy` rows / `PolicyResolver` | **Small (v1 optional)** — v1 stays read-only so no gating needed; for rungs 4–5 later, let the mission's `risk_ceiling` drive `PolicyResolver.upsert` |
| Wiki ↔ memory cross-feed | `memory_remember` tool + `MemoryContext(extra="allow")` JSONB | **None** — plugin tags facts with `wiki_page_slug`/`mission_id`; optional tiny tweak to `_render_fact_line` to show citations |

**Net for v1: one small change** — a supported way for the plugin to post a repeated,
badged reflection message. Everything else is reuse. (These are edits in the `luna/` working
dir, which is editable.)

---

## 5. Component C — `luna-service` changes (the scheduler; planning-only for us)

This is the part that makes ambient behavior work **in production**, and it's the long pole.
Hosted Lunas are ephemeral Fly machines that sleep, so the nightly dream **cannot** run on an
in-process timer — the clock must live on the always-on control plane. This is exactly
**Plan 023 (external scheduler)**, which is **half-built**:

- **Already done ✅ (the hard part):** signed fire delivery + **machine-wake** + retry +
  dead-letter (`cloud/relay/forwarder.py`), the `TriggerSource` registry, Standard-Webhooks
  signing.
- **To build 🚧 (the clock half):** `external_schedules` table, cron/NL expression engine
  (`cloud/scheduler/expr.py`), the ticker poll loop (`cloud/scheduler/ticker.py`), the
  registration API (`POST /api/scheduler/schedules`), and `SCHEDULER_MODE=external`
  provisioning.

**How Curiosity uses it:** the plugin **registers a schedule** ("dream nightly at 3am") and
**receives the fire** at `POST /api/p/plugin-curiosity/dream`. The control plane ticks →
wakes the machine → POSTs the signed fire → `dream.py` runs. Fire payload:
`{fire_id, schedule_id, action_type, target, inputs:{mission_id}, fired_at}`.

**Our path given luna-service is read-only for us:**
1. **Develop against `local` mode first** — an in-plugin `croniter` loop
   (`SCHEDULER_MODE=local`) on a dev Luna. The fire *interface is identical*, so nothing is
   thrown away. This unblocks the entire dream loop **without** touching luna-service.
2. **Hand owners a one-page spec** of what Curiosity needs from the fire contract
   (`inputs.mission_id` targeting, timezone handling) and make the case that Curiosity is the
   **first real consumer** justifying finishing Plan 023.

See [results/02-scheduling-and-ambient.md](./results/02-scheduling-and-ambient.md) for the
full interface.

---

## 6. Reused, Unchanged

- **`plugin-web-access`** — research substrate; the **agent** calls `web_search`/`web_fetch`
  (tools are agent-only — no programmatic wrapper).
- **`plugin-funnelfighters`** — read-only funnel/ads/landing-page tools; the growth mission's
  proving ground with **zero new integrations**.
- **`plugin-interview`** — the master pattern both new plugins copy (own tables, markdown body,
  thin prompt note + detail-as-tool-result, one-shot muted message, sidebar UI).
- **Core memory** — stays exactly as-is (atomic facts, top-5 recall). The wiki is a *separate*
  store; they cross-feed, no migration.

---

## 7. How It Works (end-to-end)

```
 (1) Human sets a mission ──▶ set_mission → write-through to Identity.mission
        │                          │
        ▼                          ▼
 (2) On-load muted message kicks off curiosity (quick-win-first):
        restate mission · stub wiki pages · one insight
        │
        ▼
 (3) Agent-driven research: the agent calls web_search (web-access) + wiki_write/patch_page
        (pages cite sources, carry confidence + open-questions)
        │                                          │ cross-feed
        │                                          ▼ memory_remember (tagged wiki_page/mission)
        ▼
 (4) NIGHTLY DREAM (scheduler-fired):
        control plane ticks → wakes machine → POST /dream
        dream.py: read/patch pages via WikiProvider → draft ONE thought
        │
        ▼
 (5) share_thought → source="curiosity" badged message to the human
        headline · 2-3 cited findings · one question · [Go deeper|Redirect|Stop]
        │
        ▼
 (6) Human steers (buttons / NL) → updates mission topic priorities
        │
        ▼ (after enough grounded understanding — interview-style coverage signal)
 (7) PROPOSE: a concrete, scoped, low-risk change list ("7 edits to this landing page")
        → paste into your agent, OR (rung 4+, later) grant a tool and Luna drafts for approval
```

Predictable rhythm (nightly dream, morning reflection) makes it feel alive; the quick-win
kickoff keeps early token use legible. (Spend receipts/allowance deferred — §9.)

---

## 8. Build Phases

Eight phases, each a shippable increment with its own folder + detailed plan under
[plans/](./plans/). Phases 1–6 run entirely on a **dev Luna** with `local` scheduler mode and
zero new integrations; phase 7 (the production clock) is owner-gated and lands after the
experience is already validated.

| Phase | Folder | Deliverable | Depends on | Spike |
|-------|--------|-------------|------------|-------|
| **0** | `phase0-foundations-and-scaffold` | Confirm `ProviderRegistry` plugin registration; dev Luna; scaffold both plugin repos from `template/` | — | — |
| **1** | `phase1-plugin-wiki` | wiki tables + `wiki_*` tools + 3-tier injection + `WikiProvider` | 0 | **SP1** |
| **2** | `phase2-curiosity-mission` | `plugin-curiosity` scaffold; `missions` table; `set_mission` write-through; consume `WikiProvider` | 1 | — |
| **3** | `phase3-core-reflection-hook` | `luna` core: `source="curiosity"` repeated badged-message path | 2 (parallel-ok) | — |
| **4** | `phase4-research-and-reflect` | Agent-mediated research; `share_thought`; the quick-win kickoff artifact | 2, 3 | **SP3** |
| **5** | `phase5-dream-nightly` | `dream.py` on `local`-mode `croniter`; consolidation → one thought; cadence/noise controls | 4 | **SP2** |
| **6** | `phase6-onboarding-and-validation` | First-run **onboarding** (fresh Luna → mission → curiosity kicks off); install both plugins on a fresh Luna; validate the vision on the growth mission; **verify on a real running Luna** | 5 | **SP4** |
| **7** | `phase7-production-scheduler` | luna-service finishes Plan 023 clock-half; plugin → `external` mode; verify wake + fire on hosted Luna | 6; **luna-service owners** | — |

Phases 1–6 prove the entire experience — ending in a fresh Luna behaving as the vision
describes. Phase 7 makes the ambient clock production-real and is gated on luna-service.

---

## 9. v1 Scope & Cut Lines

**In:** rungs 1–3 (learn → advise → recommend); single active mission; read-only tools only;
per-mission wiki; nightly dream + reflections.

**Out (later):** spend transparency (receipts/allowance) — not needed now; **design nothing
that blocks adding it** (a token counter around dream/research sessions is a later add-on);
rungs 4–5 (execute-with-approval, own) and the `risk_ceiling`→`PolicyResolver` gating they
need; multiple concurrent missions; reactive news-spike triggers (webhook, not cron);
email/WhatsApp reflection channels; playbook-wrapped dream. These map cleanly onto
luna-service's Pro/Power tiers when tiers become enforced (today `Account.plan` is unused).

---

## 10. Dependencies, Risks, Open Decisions

**Critical path / long pole:** luna-service Plan 023 clock-half (P5). Mitigated by building
everything else against `local` mode first — Curiosity is fully demonstrable without it.

**Top risks** (full list in [research_plan.md §7](./research_plan.md)): proactive messages
becoming noise (→ ≤1/day + quiet hours); wiki bloating context (→ 3-tier injection, proven by
SP1); confident-but-wrong worldview (→ mandatory citations, confidence flags, dream flags
low-confidence claims).

**Decisions — resolved:**
1. **Scheduler** — Roy owns completing Plan 023's clock-half; we build/develop against
   `local` mode meanwhile. ✅
2. **Dream home** — a **module inside `plugin-curiosity`** (not in the wiki substrate, not its
   own plugin; behaviors stay modules, substrates become plugins). ✅
3. **v1 scope** — rungs 1–3, single active mission, no external writes. ✅
4. **Spend transparency** — **deferred**; not needed now, design nothing that blocks adding a
   token counter later. ✅
5. **Reflection channel** — in-conversation `source="curiosity"` badged messages for v1. ✅

Settled by research: wiki as a separate substrate (`plugin-wiki`); wiki split from curiosity;
extend the existing `Identity.mission`.

---

*Next concrete step: Phase 0 — confirm the `ProviderRegistry` plugin hook and scaffold both
plugin repos from `template/`. Detailed per-phase plans live in [plans/](./plans/).*
