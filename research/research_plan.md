# Luna Curiosity — Research Plan

Companion to [vision.md](./vision.md). This document defines **how we investigate** what it
takes to make a fresh Luna curious — self-educating, wiki-building, reflective, and
proactive — and how that behavior gets built across the `luna` core, `luna-service`, and a
likely new **curiosity plugin**.

The goal of this phase is **not to build** but to answer the open questions well enough that
the build is de-risked and the architecture is settled. Output is a set of decisions, a
recommended architecture, and a small number of throwaway spikes that prove the risky parts.

---

## 0. How to Read This

- **§1 Current state** — what the codebase already gives us (grounded findings, so we don't
  re-litigate solved problems).
- **§2 Gaps** — what does not exist yet and therefore must be designed or built.
- **§3 Research questions** — the open questions, grouped by theme.
- **§4 Workstreams** — how we'll actually chase the answers, with deliverables.
- **§5 Spikes** — throwaway prototypes that retire the biggest risks fast.
- **§6 Open decisions** — the calls that need the human (Roy).
- **§7 Risks · §8 Success criteria · §9 Sequencing.**

---

## 1. Current State (Grounded Findings)

These come from reading the codebase; treat them as settled facts, not assumptions.

### 1.1 Memory
- Storage is a `memory_facts` table of **short atomic facts** with embeddings
  ([luna/plugins/plugin_memory/](../../luna/plugins/plugin_memory/)).
- Facts are created explicitly (`memory_remember` tool) and via **regex auto-extraction**
  on each user message (`extract.py`), tagged with provenance/context (`context.py`).
- Recall is **semantic top-5**, injected into the system prompt each turn via
  `recall_context()` in `luna/luna/agent/system_prompt.py`.
- Scope is **global per Luna instance** — no `mission_id`/`agent_id` scoping today, though
  `context.conversation_id` is captured and could support future scoping.
- **There is no wiki, knowledge base, or long-form document store.** Memory is atomic
  facts, not pages.

### 1.2 Scheduling / ambient behavior — **half-built** (updated)
- `luna-service` is a multi-tenant control plane (provisions Fly Machines, proxies chat,
  relays Composio webhooks with a retry outbox at `cloud/relay/forwarder.py`).
- An **external scheduler is designed and partially implemented** — Plan 023
  (`luna-service/plans/023-external-scheduler/PLAN.md`). Because hosted Lunas are ephemeral
  (scale-to-zero) machines that can't keep their own cron, the **clock lives on the
  control plane**: it ticks, **wakes** the tenant machine, and **fires** a plugin trigger.
- **The delivery half already exists** ✅: the `TriggerSource` registry
  (`luna/triggers/__init__.py`), the relay forwarder with auto-wake + retry + dead-letter,
  machine-wake (`cloud/api/proxy.py::_try_wake_agent`), and Standard-Webhooks signing.
- **The clock half is unbuilt** 🚧: no `external_schedules` table, no cron/NL expression
  engine (`cloud/scheduler/expr.py`), no ticker (`cloud/scheduler/ticker.py`), no
  registration API, no `external-scheduler` plugin. `plugin_playbooks` has a `cron` field
  stub that is hard-rejected until Phase 014 (`plugin_playbooks/definition.py:73`).
- A **`local` mode** (in-plugin `croniter` loop, `SCHEDULER_MODE=local`) is part of the OSS
  design — lets us develop cadences without the control plane.
- Implication: **"dream every night at 3am" has a designed home; we finish the clock half
  and develop against local mode meanwhile.** Full grounding + recommendation in
  [results/02-scheduling-and-ambient.md](./results/02-scheduling-and-ambient.md).

### 1.3 Plugin surface (what a curiosity plugin could use)
- A plugin is a `luna_sdk`-only package (`luna-plugin.toml` + `LunaPlugin.on_load(ctx)`).
- It can register: **tools** (with `auto_approve`/`ask`/`prompt_always` policies + risk
  levels), **skills**, **FastAPI routes**, **settings tabs & sidebar sections** (iframe
  UI), its own **DB tables** (SDK enabler E4), **vault secrets**, **triggers**
  (`TriggerSourceRegistry`), and **one-time "muted messages"** — a proactive prompt pushed
  to the agent on load (SDK enabler E11).
- Read-only conversation access via `ctx.conversations` / `ctx.current_conversation_id`
  (E6). Plugins **cannot** `import luna.*`.
- Directly reusable building blocks already exist:
  - [plugin-web-access](../../plugins/plugin-web-access/) — `web_search`, `web_fetch`,
    `http_request`. **The research substrate is done.**
  - [plugin-interview](../../plugins/plugin-interview/) — the closest pattern to what we
    want: owns DB tables, produces **markdown briefs**, and fires a proactive muted message
    on load. A strong template for wiki storage + proactive nudge.
  - [plugin-playbooks](../../plugins/plugin-playbooks/) — durable multi-step workflows +
    trigger binding. Candidate engine for the "dream" cadence.
  - [plugin-funnelfighters](../../plugins/plugin-funnelfighters/) — read-only funnel/ads/
    landing-page tools; makes the growth example runnable with **no new integration.**

---

## 2. Gaps (What Must Be Designed / Built)

| # | Gap | Why it matters |
|---|-----|----------------|
| G1 | No long-form, per-mission **knowledge store** (the wiki) | Core of the vision; memory is atomic-fact-shaped |
| G2 | No first-class **mission** object | Everything hangs off "the mission"; today it's implicit in chat |
| G3 | No **scheduler / ambient clock** owned by Luna | "Dream nightly," "weekly digest" have no home |
| G4 | No **proactive outbound messaging** beyond one-time muted messages | Luna must send reflections unprompted, repeatedly, with cadence control |
| G5 | No **"dream"/consolidation** routine | Turning raw notes into distilled thoughts + wiki edits |
| G6 | No **autonomy-ladder / trust** model surfaced to the user | Rungs 1–5 from the vision need a representation |
| G7 | No **spend-transparency** surface for background work | Users must see what tokens bought |

---

## 3. Research Questions

### Theme A — Knowledge representation (the wiki)
- **A1.** Wiki as a *new* document store beside `memory_facts`, or as a *superset/refactor*
  of memory? (Recommend leaning "new store, cross-linked to memory" — validate.)
- **A2.** Storage shape: markdown files on the plugin volume, DB table(s) à la
  plugin-interview, or a hybrid? How do pages get versioned and diffed?
- **A3.** How does the wiki get **into context** without blowing the token budget? Full
  pages? A retrieved slice? A generated table-of-contents + on-demand page fetch tool?
- **A4.** How do wiki and atomic memory **cross-feed** (pages → facts, facts → citations)?
- **A5.** Scoping: is the wiki per-mission from day one? How does that interact with the
  currently-global memory?
- **A6.** What is the concrete **page schema** (title, body, links, citations, confidence,
  last-updated, open-questions)?

### Theme B — Ambient behavior & the clock
- **B1.** ~~Where does the recurring trigger live?~~ **Resolved** (see
  [results/02](./results/02-scheduling-and-ambient.md)): consume the Plan 023 external
  scheduler's fire event; develop against `local` mode meanwhile. Curiosity does not build a
  clock. Remaining sub-question: whether we build local mode in the curiosity plugin for dev
  or wait for hosted external mode.
- **B2.** What cadences do we actually need (nightly dream, weekly digest, reactive news
  spike) and which are must-have for v1?
- **B3.** How does a scheduled trigger **invoke a Luna run** with the right mission context?
  (Ties to luna-service's future "wake + POST trigger event" design.)
- **B4.** Idle/suspend interaction: hosted Lunas suspend when idle — how does a background
  routine survive that? (This is why B1 can't be hand-waved.)

### Theme C — The curiosity plugin (architecture)
- **C1.** Is this **one plugin** or several (wiki store / research loop / dreamer /
  proactive-comms)? Where are the seams?
- **C2.** Which behaviors are **deterministic routines** (predictable, playbook-like) vs
  **agent-driven** (open-ended reasoning)? The vision wants both.
- **C3.** What tools does the plugin expose to the agent (e.g. `wiki_write_page`,
  `wiki_read`, `research_topic`, `share_thought`, `set_mission`)?
- **C4.** How does it reuse plugin-web-access and plugin-playbooks vs reimplement?

### Theme D — Communication & reflection
- **D1.** By what channel does Luna send an **unprompted** reflection? (Muted messages are
  one-time and on-load; we need repeated, scheduled outbound — likely a new mechanism in
  core or luna-service.)
- **D2.** What is the **format** of a shared thought (headline + findings + one question)?
- **D3.** Cadence & **noise control** — batching, quiet hours, per-user frequency caps.
- **D4.** How does the human **steer** curiosity (react to a thought, redirect, "go deeper
  on X," "stop researching Y")? Reflections should be a two-way surface.

### Theme E — Calls to action & pacing
- **E1.** Validate the **quick-win-first** intuition: early shallow-but-visible pass beats a
  long silent deep dive. Design the "first 10 minutes" artifact (mission brief + first wiki
  stub + one insight).
- **E2.** When does Luna escalate from *learning* to *proposing*? What signals "enough
  understanding"?
- **E3.** **Spend transparency:** how do we show what background tokens bought, so a
  multi-hour session is legible? Should there be a budget/allowance the user sets?
- **E4.** Depth control: does the user pick "quick tour" vs "deep dive," or does Luna
  default to shallow-then-offer-deep?

### Theme F — Mission & trust model
- **F1.** What is a **mission** object concretely (statement, scope, current rung, linked
  wiki, linked tools)? Where does it live?
- **F2.** How is the **autonomy ladder** (rungs 1–5) represented and advanced? Does climbing
  a rung map to unlocking tool policies?
- **F3.** How does mission scope interact with global memory and (future) per-mission wiki?

---

## 4. Workstreams

Each workstream produces a written deliverable in this folder.

- **WS1 — Knowledge architecture** (Theme A). Deliverable: `design/wiki.md` — recommended
  store, page schema, context-injection strategy, memory cross-feed, migration stance.
- **WS2 — Ambient & scheduling** (Theme B). Deliverable: `design/scheduling.md` — chosen
  clock mechanism with tradeoffs, cadence list, and the suspend-survival story. Coordinate
  with luna-service owners (read-only for us).
- **WS3 — Curiosity plugin design** (Themes C, D). Deliverable: `design/plugin.md` —
  plugin boundary, tool list, routines-vs-agent split, reuse map, and a file skeleton.
- **WS4 — Communication & pacing** (Themes D, E). Deliverable: `design/comms-and-pacing.md`
  — outbound-message mechanism, thought format, cadence/noise rules, quick-win spec, spend
  transparency.
- **WS5 — Mission & trust model** (Theme F). Deliverable: `design/mission-and-trust.md` —
  mission object, autonomy ladder representation, tool-policy mapping.
- **WS6 — Prior art scan.** Deliverable: `design/prior-art.md` — Karpathy's LLM-wiki notes,
  agent "reflection/dreaming" patterns (Generative Agents, Reflexion, memory-stream
  consolidation), and proactive-assistant UX. Feeds all other workstreams.

---

## 5. Spikes (Throwaway, Risk-Retiring)

Small prototypes to prove the risky parts before committing to architecture:

- **SP1 — Wiki round-trip.** A minimal plugin with `wiki_write_page` / `wiki_read` +
  markdown-on-volume storage. Prove pages persist, cross-link, and can be selectively
  pulled into context without blowing the budget. (Retires G1, A2, A3.)
- **SP2 — Nightly dream.** Wire one recurring trigger (via the cheapest viable mechanism
  from B1) that runs a consolidation pass over SP1's pages and writes distilled thoughts.
  Prove the clock fires and survives idle/suspend. (Retires G3, B1, B4.)
- **SP3 — Proactive reflection.** Have Luna send one unprompted, well-formatted reflection
  to the user on a schedule. Prove the outbound channel exists and is controllable.
  (Retires G4, D1.)
- **SP4 — Growth-mission dry run.** Point the above at the growth example using existing
  [plugin-funnelfighters](../../plugins/plugin-funnelfighters/) (read-only) + web-access.
  Prove the end-to-end feel: mission → wiki → dream → reflection → proposal, with **no new
  integrations.** (Retires the whole loop; validates E1's quick-win intuition.)

Spikes are deliberately disposable — their job is to produce *decisions*, not code we keep.

---

## 6. Open Decisions (need Roy)

1. **Wiki vs memory** (A1): new store beside memory, or refactor memory into it?
   *Leaning: new store, cross-linked. Confirm.*
2. **Scheduler priority** (B1 — mostly resolved): the mechanism is decided (consume Plan
   023's fire event; dev against `local` mode). The remaining call is roadmap: do we pull
   the hosted clock-half of Plan 023 forward with Curiosity as its first consumer, and is
   building `local` mode in the curiosity plugin acceptable for dev? (luna-service is
   read-only for us — needs owner buy-in.)
3. **One plugin or several** (C1).
4. **Quick-win vs deep-dive default** (E1/E4): confirm the "shallow first, offer depth"
   default and whether the user sets a token budget/allowance.
5. **Scope of v1**: which cadences and which autonomy rungs ship first. *Recommend: rungs
   1–3 only (observe/learn → reflect/advise → draft/recommend), no write execution.*

---

## 7. Risks

- **R1 — Ambient clock is half-built (downgraded).** No longer an unknown: the external
  scheduler is designed (Plan 023) with the hard delivery infra (wake + signed fire + retry)
  already done; the clock half (table, cron parser, ticker, registration API, plugin) is
  unbuilt but mechanical. Curiosity is a *consumer* of the fire event, and can develop
  against `local` mode without the control plane. Residual risk is scheduling/roadmap: the
  hosted half needs luna-service owner buy-in (read-only for us) to finish. See
  [results/02-scheduling-and-ambient.md](./results/02-scheduling-and-ambient.md).
- **R2 — Token spend feels opaque or runaway.** Background curiosity burns tokens with no
  user in the loop. Mitigation: quick-win-first, spend transparency, budgets (Theme E).
- **R3 — Proactive messaging becomes noise.** Kills trust faster than silence. Mitigation:
  batching, cadence caps, quiet hours (D3).
- **R4 — Wiki bloats context.** Long pages can't all live in the prompt. Mitigation: TOC +
  on-demand fetch tool (A3); prove in SP1.
- **R5 — Curiosity without grounding hallucinates a confident-but-wrong worldview.**
  Mitigation: citations mandatory; distinguish "read" from "inferred"; dream pass flags
  low-confidence claims.
- **R6 — Scope creep.** The vision is large. Mitigation: rungs 1–3 only for v1; the growth
  example on existing read-only tools as the single proving ground.

---

## 8. Success Criteria for This Research Phase

The phase is done when we can:
1. State a recommended **knowledge architecture** (wiki store + memory relationship) with a
   page schema and a context-injection strategy — validated by SP1.
2. Name the **clock mechanism** for ambient behavior and show it firing + surviving idle —
   validated by SP2.
3. Show one **unprompted, well-formed reflection** delivered on cadence — SP3.
4. Demonstrate the **full loop** on the growth mission with zero new integrations — SP4.
5. Hand Roy a crisp **decision list (§6) resolved**, a **v1 scope**, and a **plugin
   skeleton** ready to build.

---

## 9. Suggested Sequencing

```
WS6 prior-art  ─┐
WS1 wiki       ─┼─▶ SP1 wiki round-trip ─┐
WS2 scheduling ─┴─▶ SP2 nightly dream   ─┼─▶ SP4 growth dry run ─▶ decisions + v1 scope
WS4 comms      ────▶ SP3 proactive msg  ─┘
WS3 plugin design & WS5 mission/trust run alongside, folding in spike learnings.
```

Start with WS6 + WS1 + WS2 in parallel (they're independent reading/design), then the
spikes in dependency order, converging on SP4 as the integrated proof.

---

*See [vision.md](./vision.md) for the "why" and the target experience.*
