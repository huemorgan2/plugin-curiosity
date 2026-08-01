# Phase 4 — research & reflect (the daytime loop)

**Goal:** Luna teaches herself — she researches the web, writes it into the wiki, and
proactively shares one grounded reflection. Plus the first-session **quick win** so the human
feels value before any opaque token-spend. This closes the awake half of the core loop.

**Depends on:** Phases 1 (wiki), 2 (mission + action rails), 3 (reflection hook). **Spike:**
**SP3** (reflection + quick-win kickoff).

---

## Scope

**In:** the immediate kickoff research (muted-message turn); the recurring research pass
(scheduler-fired); a thin `research.py` orchestrator; `share_thought`; the "Mission Kickoff"
quick-win artifact; comms cadence/noise guardrails.

**Out:** the nightly dream (phase 5). No unattended external writes (actions stay
approval-gated, per phase 2).

---

## How research is triggered (two paths, both real)

1. **Kickoff (immediate).** On `mission_set` (phase 2 renamed the tools to
   `mission_set`/`mission_refine`/`mission_get` — see phase-2 learnings below), the
   on-load / mission-set **muted message** (`respond=True`) runs an agent turn right then —
   no clock needed. This produces the quick-win artifact in the first session.
2. **Recurring (scheduler-fired).** The mission's `trigger_create(action_type="agent_prompt",
   schedule_expr="every day at 09:00", target=<research instructions>)` from phase 2 fires a
   daily research turn. The scheduler wakes the machine; `plugin-scheduler` runs the turn. **No
   asyncio loop.** For a repeatable multi-step routine, the target can instead be a
   curiosity-authored **playbook** (`action_type="playbook"`).

## Research is agent-mediated — via `ctx.agent.run_turn`, not a tool wrapper

Tools are agent-only (no `ctx.tools.call()`), but plugin code **can** launch a scoped agent
session: `ctx.agent.run_turn(prompt, tools=["web_search","wiki_write","wiki_patch", ...])`.
So `research.py` is a **thin orchestrator** — it composes the prompt from the mission + open
questions and calls `run_turn`; inside that one agentic turn the LLM loops `web_search` →
`wiki_write`/`wiki_patch` → `wiki_citations` until done. `research.py` drives the agent; it
does not call web tools directly. (This reinstates the module removed earlier, now on the
correct primitive.)

Research may also **spawn or refine a playbook** when it spots a repeatable task — e.g. a
weekly-competitor-scan playbook — using `playbook_propose` / `playbook_edit`.

> **Phase-0 constraint (verified live):** those two tools are `chat_only=True`, so a
> scheduler-FIRED research turn cannot author playbooks. Fired research should instead
> record the repeatable-task idea (wiki open question or mission note) and propose the
> playbook in the next real chat turn. Only chat-initiated research runs can author
> directly. Wiki/citation/search tools are unaffected in fired turns.

## comms.py — `share_thought`

- `share_thought(body)` → posts a `source="curiosity"` badged reflection via the Phase 3 hook.
- Guardrails: **≤1 routine reflection/day**, **21:00–08:00 quiet hours**, batching, relevance
  gate. A thought must cite a wiki page or a fresh finding — no ungrounded musing.

## The quick-win kickoff (SP3) — value before spend

On mission start, produce a **Mission Kickoff** artifact cheaply and visibly: a 3–5 line brief;
2–4 seeded wiki stub pages with a first pass of researched content; **one concrete insight or
quick win** grounded in a real source; the open questions she'll pursue next. Design it so a
cost line can slot in later without rework.

---

## Steps

1. SP3: write the curiosity prompt fragment that, given a mission + open questions, researches
   via `web_search` and records via `wiki_write`/`wiki_patch` + citations — used both by the
   kickoff muted message and the recurring `agent_prompt` target.
2. Implement `research.py` as a `run_turn` orchestrator; wire the recurring schedule's target
   to it (phase 2 registered the trigger; here we fill the prompt).
3. Implement `share_thought` + guardrails in `comms.py`.
4. Implement the Mission Kickoff artifact (brief + stub research + one insight + open questions).
5. Dry-run: set a mission → kickoff artifact appears same session → next day's scheduler fire
   adds cited wiki content and lands one grounded reflection.

## Acceptance criteria

- [ ] The kickoff produces a Mission Kickoff artifact in the first session (brief + seeded
      cited research + ≥1 concrete quick win + open questions).
- [ ] A scheduler `agent_prompt` fire runs a research turn that adds cited content to wiki pages
      via `run_turn` — **no asyncio loop, no research tool-wrapper**.
- [ ] `share_thought` posts a grounded, badged reflection; guardrails block a 2nd same-day
      routine reflection and respect quiet hours.
- [ ] When research identifies a repeatable action, the agent can `playbook_propose` a playbook
      for it (approval-gated actions).
- [ ] Every shared thought cites a wiki page or a fresh finding.

## Notes / risks

- One `run_turn` is one bounded agentic turn (multi-tool, capped by MAX_TURNS). Deep coverage =
  many scheduled turns over days, not one long session.
- Do not reintroduce a research tool-wrapper — orchestrate via `ctx.agent.run_turn`.
- **Phase-1 learnings:** `wiki_search` is lexical (term-count ranked) — fine to start; if
  research recall suffers, embedding search via plugin-memory's provider is a separate,
  later decision. Tier-2 wiki injection is recency-ranked (core's `prompt_sections()` has
  no turn argument), so research turns should locate context via `wiki_toc`/`wiki_search`
  rather than assuming the prompt carries the relevant pages.

> **Phase-2 learnings:**
> - Tools renamed: `mission_set`/`mission_refine`/`mission_get`. Root cause: core's alembic
>   `0008_approvals.py` seeds `prompt_always` policy rows for `set_mission`, `set_persona`,
>   `update_self`, `mcp_*`, `memory_forget`, and DB rows beat `ToolDef.policy`. **Check the
>   0008 seed list (and `GET /api/p/plugin-approvals/policy`) before naming `share_thought`
>   or any other new tool.**
> - Phase 2 registered the recurring trigger as **`curiosity-daily-research`** (not a generic
>   name) with a placeholder `agent_prompt` target. This phase fills the real prompt: update
>   the target via `_sync_schedules` in mission.py (idempotent re-sync), don't
>   delete/recreate the trigger.
> - Scheduler tool calls from plugin code must go through mission.py's `_retry_tool` pattern
>   (handlers return `{"error": str(exc)}`, empty string for bare timeouts; the 10s HMAC
>   client timeout trips transiently under concurrent-turn load). Any tool whose handler can
>   spend >30s (e.g. a kickoff that seeds wiki + schedules) needs an explicit
>   `timeout_seconds` on its ToolDef — the default 30s killed `mission_set` once.
> - `playbook_run` on an unapproved playbook returns `needs_approval` as a *tool result*
>   (agent keeps control); `prompt_always` tools *block* the turn with no persisted messages.
>   Design kickoff/research prompts accordingly, and dojo-test the blocking kind via the
>   approvals API, never chat markers.

> **Phase-3 learnings (reflection hook is live):**
> - `share_thought` should post a **moment** (`ctx.send_muted_message(..., channel="moment",
>   source="curiosity")`): the badge renders on the assistant *reply* bubble — an
>   awareness-only post is a collapsed grey line with no badge. plugin-curiosity 0.2.1
>   already exposes the mechanism at `POST /api/p/plugin-curiosity/reflect`; share_thought
>   wraps the same ctx call with the cadence/quiet-hours guardrails.
> - The reaction turn defaults to **zero tools** — pass an explicit allowlist (wiki read
>   tools at least) so the voiced thought can ground itself in current wiki state.
> - Pass `conversation_id` deliberately; the fallback is "most recently updated
>   conversation", which is nondeterministic under concurrent activity.
> - Keep `[[slug]]` links in the muted body so reflections join the wiki graph.
