# Luna Curiosity — Execution Plans

Per-phase execution plans. Each phase is a shippable increment with its own folder. Build in
order; phases 1–6 run on a **dev Luna** running the real `luna-scheduler` locally, and end with
a fresh Luna behaving as the [vision](../vision.md) describes. Phase 7 deploys that scheduler to
production (gated on luna-service owners).

**Foundations we build on (already exist — we do not rebuild them):**
- **`luna-scheduler`** (`scheduler-service` + `plugin-scheduler`) — the ambient clock. Curiosity
  registers cadence via `trigger_create`; fires run an `agent_prompt` turn or a `playbook`, and
  the relay **wakes a sleeping machine**. → No asyncio loop of our own.
- **`plugin-playbooks`** — the action rails. The agent authors/refines playbooks
  (`playbook_propose`/`playbook_edit`) whose `tool_call` steps take real actions (email, APIs),
  gated by approval policy. → Self-improving *and* actioning on one substrate.

Context: [../high-level-plan.md](../high-level-plan.md) · [../vision.md](../vision.md) ·
[../results/](../results/)

| Phase | Folder | Goal | Spike |
|-------|--------|------|-------|
| 0 | [phase0-foundations-and-scaffold](./phase0-foundations-and-scaffold/PLAN.md) | Confirm the provider seam; dev Luna; scaffold both plugin repos | — |
| 1 | [phase1-plugin-wiki](./phase1-plugin-wiki/PLAN.md) | The knowledge substrate: `wiki_*` tools, 3-tier injection, `WikiProvider`, `wiki_links` edges | SP1 |
| 1.5 | [phase1.5-wiki-ui-and-graph](./phase1.5-wiki-ui-and-graph/PLAN.md) | Deep wiki UI + React Flow knowledge graph (off critical path) | — |
| 2 | [phase2-curiosity-mission](./phase2-curiosity-mission/PLAN.md) | Mission object + write-through + **the action rails** (scheduler + playbook authoring/triggering) | — |
| 3 | [phase3-core-reflection-hook](./phase3-core-reflection-hook/PLAN.md) | `luna` core: repeated `source="curiosity"` badged message | — |
| 4 | [phase4-research-and-reflect](./phase4-research-and-reflect/PLAN.md) | Research via `ctx.agent.run_turn` (kickoff + scheduled); `share_thought`; quick-win kickoff | SP3 |
| 5 | [phase5-dream-nightly](./phase5-dream-nightly/PLAN.md) | The nightly dream as a scheduled `agent_prompt` on real `luna-scheduler` — no asyncio | SP2 |
| 6 | [phase6-onboarding-and-validation](./phase6-onboarding-and-validation/PLAN.md) | First-run onboarding; fresh-Luna install; validate the vision end-to-end | SP4 |
| 7 | [phase7-production-scheduler](./phase7-production-scheduler/PLAN.md) | Deploy `luna-scheduler`, wire luna-service config, verify wake-on-sleep | — |

**The finish line (phase 6):** a fresh Luna with `plugin-wiki` + `plugin-curiosity` installed,
given a mission, teaches herself, builds a wiki, dreams, and proactively reflects — exactly as
the vision says — validated on a real running Luna.
