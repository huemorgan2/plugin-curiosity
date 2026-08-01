# Luna Curiosity — Research Results (Synthesis)

Six workstreams, executed and grounded in the actual `luna` / `luna-service` / `plugins`
code. This is the index and the convergence: what we found, what it means, and the
recommended v1 build. Read the numbered files for depth.

| # | Deliverable | Question answered |
|---|-------------|-------------------|
| [00](./00-prior-art.md) | Prior art | Karpathy's LLM wiki, Generative Agents / Reflexion / MemGPT / Voyager, Letta sleep-time compute, proactive-UX budgets |
| [01](./01-wiki-knowledge-architecture.md) | Wiki / knowledge architecture | New store vs memory; page schema; context-budget strategy; cross-feed |
| [02](./02-scheduling-and-ambient.md) | Scheduling & ambient | Where the clock lives (the half-built external scheduler); the dream cadence |
| [03](./03-curiosity-plugin-design.md) | Curiosity plugin | One plugin or many; tool surface; routines vs agent-driven; file skeleton |
| [04](./04-comms-and-pacing.md) | Communication & pacing | Unprompted reflections; thought format; noise control; quick-wins; spend transparency |
| [05](./05-mission-and-trust.md) | Mission & trust | The mission object; the autonomy ladder mapped onto real policy machinery |

Companion context: [../vision.md](../vision.md) · [../research_plan.md](../research_plan.md)

---

## 1. The Findings That Change the Build

Five grounded discoveries do most of the de-risking. Each one turned a vision assumption
into a concrete, cheaper path.

1. **The mission already exists — extend, don't invent.** Core's `Identity` row already
   carries a `mission` string that renders at system-prompt slot #4 via `mission_block()`.
   Curiosity's structured mission (its own plugin table) **write-throughs** its statement
   into that field, so the agent "owns the goal" at native priority with zero core change.
   (WS5)

2. **`risk_level` is inert; only `policy` gates approvals — and tiers are unenforced.** The
   `low/medium/high` risk labels don't actually gate anything today; the `auto_approve /
   ask / prompt_always` **policy** is the real lever, and `Account.plan` is never checked.
   Consequence: the autonomy ladder must be driven by the mission writing `approval_policy`
   rows (via `PolicyResolver.upsert`), and **v1 (rungs 1–3) needs no tier entitlement at
   all.** (WS5)

3. **`plugin-interview` is the master template — copy it, don't design from scratch.** It
   already proves every pattern Curiosity needs: plugin-owned DB tables (E4), **markdown
   stored in a `body` column**, a *thin* always-on capability note with heavy detail
   delivered as a **tool result** (this is what keeps the wiki from blowing the token
   budget, R4), a one-shot proactive **muted message** on load (E11), and sidebar UI. WS1,
   WS3, WS4, and WS5 all independently landed on it. (multiple)

4. **The scheduler is half-built, not missing.** The delivery half is done (signed fire +
   machine-wake + retry, the `TriggerSource` registry); the clock half is specified but
   unbuilt (Plan 023: table, cron/NL parser, ticker, registration API). Curiosity is a
   **consumer** of the fire event and can develop against the OSS **`local` mode** without
   the control plane. This downgrades the plan's biggest risk (R1). (WS2)

5. **Outbound is SSE-only — but the proactive primitive already exists.** There's no push
   or email today; reflections land as in-conversation messages. The E11 muted-message path
   (`post_muted_message` → persists a `MessageRow(extra={source,...})` + emits
   `message.created`) already accepts `source` and `respond`, and `source="playbook"`
   badging is a working precedent. A repeated reflection is a new `source="curiosity"`
   badge — **near-zero core change.** (WS4)

Plus the conceptual anchor from prior art: Karpathy's wiki is **compile-time synthesis**
(knowledge accumulates into authored pages) vs RAG's **query-time** re-discovery — which is
exactly why the wiki is a *new store*, not a dressed-up memory recall. (WS6)

---

## 2. Converged Architecture

A single new plugin, **`plugin-curiosity`**, modeled on `plugin-interview`, with four
internal seams (Python modules) over one DB:

```
                         plugin-curiosity
   ┌───────────────────────────────────────────────────────────┐
   │ mission.py   set_mission / refine_mission / get_mission     │  ← write-through to Identity.mission
   │              + autonomy rung + risk_ceiling (drives policy)  │     (WS5)
   │ wiki.py      wiki_write/patch/read/toc/search/list_qs        │  ← new per-mission store, markdown in body
   │              pages · revisions · citations · open-questions  │     3-tier context injection (WS1)
   │ research.py  research_topic  ── wraps ──▶ plugin-web-access  │  ← reuse, never reimplement (WS3)
   │ dream.py     nightly consolidate → wiki edits → 1 thought    │  ← fired by scheduler (WS2)
   │ comms.py     share_thought → source="curiosity" badged msg   │  ← reflections + cadence/noise (WS4)
   └───────────────────────────────────────────────────────────┘
        ▲ on-load: E11 muted message kicks off curiosity (quick-win-first)
        │
   scheduler (Plan 023, external mode) ── signed /fire ──▶ dream.py     memory (unchanged; top-5 recall)
   or in-plugin croniter (local mode, dev)                              ▲ cross-fed via memory_remember
                                                                        │  tagged wiki_page_slug/mission_id
                                                              wiki pages distil atomic facts ┘
```

- **Wiki ≠ memory.** Memory stays exactly as-is (atomic facts, top-5 semantic recall). The
  wiki is a separate per-mission store. They cross-feed: pages distil facts via the existing
  `memory_remember` tool (tagged in memory's `extra="allow"` JSONB `context`); facts can
  cite their source page. No memory migration. (WS1)
- **Context budget (R4) solved by the interview pattern:** always-on ~40-token capability
  note; per-turn TOC + relevance-ranked page *summaries* beside memory's recall snippet;
  full page bodies only via an on-demand `wiki_read` tool result. Full bodies are never
  auto-injected. (WS1)
- **All v1 tools are `auto_approve` / low-risk** because they touch only the plugin's own
  tables and read-only web access — nothing executes against the outside world. (WS3)

---

## 3. The One Cross-Workstream Tension (resolved)

**How is the "dream" implemented?** WS2 leaned toward wrapping it as a `plugin-playbooks`
workflow (legible in the canvas, resumable). WS3 argued for **in-plugin linear Python**
(the v1 dream is a fixed linear routine; a hard playbooks dependency adds cross-plugin
coupling for no v1 payoff).

**Resolution — in-plugin Python for v1.** The dream is a short fixed sequence (list pages
touched → summarize new research → patch pages → draft one thought → enqueue delivery); it
does not need branch/loop/wait durability yet. Keep it in `dream.py`, fired by the scheduler
via `POST /api/p/plugin-curiosity/dream` (idempotent, so scheduler retries are safe).
Preserve the legibility WS2 wanted **without** the coupling by making the dream always emit a
**spend receipt + the thought it produced** (WS4's cost line) — the user sees what the
nightly run did and cost, just not as a react-flow diagram. Revisit playbook-wrapping only
if/when the dream grows conditional structure. Reuse playbooks *conceptually* (context
economy, trigger-registry shape), not as a dependency.

---

## 4. Recommended v1 Scope

**Rungs 1–3 only** (Observe & learn → Reflect & advise → Draft & recommend). **No external
write execution.** **Single active mission.** This is the deliberate cut across all
workstreams, and it's cheap: it needs no tier entitlement (finding #2) and no risky tools.

Build order (each step is small and mostly copies `plugin-interview`):

1. **Plugin skeleton + mission** — `plugin-curiosity` scaffold; `mission` table;
   `set_mission` (write-through to `Identity.mission`); E11 on-load kickoff muted message.
   *→ delivers the "she gets a mission and gets curious" moment immediately.*
2. **Wiki store (Spike SP1)** — tables + `wiki_write/patch/read/toc`; 3-tier injection.
   *Retires R4.*
3. **Research** — `research_topic` wrapping `plugin-web-access`.
4. **Reflection + quick-win (Spike SP3)** — `share_thought` → `source="curiosity"` badged
   in-conversation message; the "Mission Kickoff" quick-win artifact (brief + wiki stubs +
   one insight + cost line). *Retires the outbound-channel unknown.*
5. **Dream (Spike SP2)** — `dream.py` on **local-mode** cron; consolidates pages, drafts one
   thought. *Retires R1 without any control-plane work.*
6. **Growth dry run (Spike SP4)** — point it all at the vision's growth mission using the
   **read-only** `plugin-funnelfighters` `ff_*` tools + web-access. *Proves the whole loop,
   zero new integrations.*

Guardrails that ship with v1: ≤1 routine reflection/day, 21:00–08:00 quiet hours, batching,
mandatory per-session **spend receipt**, optional user allowance (default ~$3/week) checked
before each background session. (WS4)

---

## 5. Open Decisions for Roy

Most of the plan's original open questions are now answered by the research. These remain
genuine calls for you:

1. **Scheduler roadmap.** Mechanism is decided (consume Plan 023's fire; dev on local mode).
   The call: is Curiosity a strong enough first consumer to **pull the clock-half of Plan
   023 forward**, and is building **local mode** in the plugin acceptable for dev meanwhile?
   (luna-service is read-only for us — needs owner buy-in.)
2. **Dream implementation.** Confirm **in-plugin Python for v1** (§3) over a playbook wrap.
3. **v1 scope.** Confirm **rungs 1–3, single active mission, no external writes.**
4. **Spend model.** Confirm the **per-session receipt + optional weekly allowance** concept
   and the default figure.
5. **Outbound channel.** Confirm **in-conversation badged reflections for v1**, with an
   email digest as a fast-follow and WhatsApp reserved for urgent.

Largely settled by the research (flag if you disagree): **wiki as a new store** (not a memory
refactor); **one plugin** (not four); **extend the existing `Identity.mission`** rather than
add a mission concept to core.

---

## 6. Status vs. the Research Plan's Success Criteria

The §8 criteria of [../research_plan.md](../research_plan.md) are met at the *design* level:
knowledge architecture recommended (WS1), clock mechanism named and de-risked (WS2), outbound
reflection path identified (WS4), full loop specified against zero-new-integration tools
(WS3+all). What remains is **execution of the four spikes** (SP1–SP4) to convert design into
a working v1, plus Roy's decisions in §5.
