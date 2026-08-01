# WS3 — Curiosity Plugin Architecture

> Deliverable for Themes C & D of the Luna Curiosity research plan. Grounded in the
> real plugin system (`docs/PLUGIN-ARCHITECTURE.md`, `template/`, `plugin-interview`,
> `plugin-web-access`, `plugin-playbooks`). Decisions are decisive; open items are
> flagged and handed to the owning workstream.
>
> **Scope boundary:** the recurring clock (nightly dream, weekly digest) is **WS2's**
> job. This document designs only *the plugin's side of that interface* — the route the
> scheduler POSTs to and the payload it sends. Wherever a clock is implied, the text
> says **"fired by the scheduler — see WS2."**
>
> The wiki *page schema* is **WS1's** job. This document lists the wiki tools and their
> boundaries but defers the column-level schema to WS1.

---

## C1 — One plugin or several?

**Recommendation: ONE plugin, `plugin-curiosity`, with four clean internal seams.**

The vision names four capability clusters — wiki-store, research-loop, dreamer,
proactive-comms. The temptation is one plugin each. Resist it. They are not
independently useful, they share one hard dependency (the **mission** and its **wiki**),
and they must load in a known order against the same DB. Splitting them turns internal
function calls into cross-plugin event contracts and `depends_on` chains for no reuse
benefit — none of the four has a consumer outside curiosity.

`plugin-interview` is the proof of the right size: it owns tables, a sidebar UI, agent
tools, and a proactive on-load message *in one package* and stays legible. Curiosity is
interview's bigger sibling (mission instead of a one-off goal; a living wiki instead of a
frozen brief; recurring dreams instead of a single completion). Keep it one package.

### The four seams (internal modules, not plugins)

| Seam | Module | Owns | Depends on |
|---|---|---|---|
| **Mission** | `mission.py` + `models.py` | The `mission` row: statement, scope, current autonomy rung, cadence prefs. The spine everything hangs off. | — |
| **Wiki store** | `wiki.py` + `models.py` | Per-mission pages: create/read/patch/link/list/TOC. Storage shape **deferred to WS1**. | mission |
| **Research loop** | `research.py` | `research_topic` — orchestrates web-access search/fetch into wiki writes + citations. | wiki, `plugin-web-access` |
| **Dream / consolidate** | `dream.py` + `routes.py` | The consolidation pass (raw notes → distilled thoughts, contradiction resolution, open-question surfacing). Invoked by the **scheduler route** (WS2). | wiki, mission |
| **Proactive comms** | `comms.py` | On-load kickoff muted message + `share_thought`. Outbound *cadence* mechanism is **WS4**. | mission |

**Why not lean on `plugin-playbooks` as the dream engine?** It is a genuine candidate
(the research plan floats it), but two things argue against making it a *hard dependency*
of v1:

1. **Coupling & load order.** Depending on `plugin-playbooks` means curiosity can't
   install without it, and the dream logic becomes YAML-in-a-DB-row rather than plain
   Python the plugin ships and version-controls. For a v1 whose dream pass is a *fixed*
   routine (see C2), a small deterministic Python function in `dream.py` is simpler,
   testable in the plugin's own suite, and has no cross-plugin failure surface.
2. **The clock is WS2's anyway.** Playbooks' value is *trigger binding* + *decomposition
   UI*. The trigger side is exactly what WS2 owns; the decomposition side is overkill for
   one linear consolidation pass. Reuse playbooks *conceptually* (the runner's
   context-economy discipline — iterate per page, never dump the whole wiki into one
   call), not as a dependency.

**Verdict:** one plugin, dream implemented in-plugin, playbooks kept as an *optional
future* offload once the dream routine wants branching/approval steps.

---

## C2 — Deterministic routines vs agent-driven reasoning

The vision explicitly wants both ("predictable rhythms + reactive spikes"). The split
follows one test: **is the control flow fixed, or does the outcome depend on
open-ended judgment?** Fixed flow → routine (Python, playbook-shaped, scheduler-fired).
Open-ended → agent-driven (a tool the agent calls when it decides to).

| Behavior | Bucket | Where it lives | Notes |
|---|---|---|---|
| **On-load mission kickoff** | Routine (trigger) → agent | `comms.py` fires a **muted message**; the *content* is agent-driven | Deterministic *that* it fires; the agent authors the brief. Mirrors `plugin-interview._greet_install_once`. |
| **Nightly dream / consolidation** | **Deterministic routine** | `dream.py`, **fired by the scheduler — see WS2** | Fixed pipeline: for-each dirty page → summarize → resolve contradictions → write distilled thoughts → flag low-confidence claims → list open questions. Linear, no branching. Per-page iteration (context economy, per playbooks discipline). |
| **Weekly digest** | **Deterministic routine** | `dream.py` (digest mode), **fired by the scheduler — see WS2** | Same shape, wider window; emits one `share_thought`. |
| **Reactive news spike** | Routine trigger → agent | scheduler/bus event → agent turn | *That* it fires is a trigger (WS2/connectors); *what to do about the news* is agent judgment. |
| **`research_topic`** | **Agent-driven** | `research.py` tool | The agent decides depth, breadth, when to stop, what's worth a page. A routine can *call* it, but the reasoning is the agent's. |
| **`set_mission` / refine scope** | Agent-driven | `mission.py` tool | Restating the mission "in her own words" is judgment. |
| **`wiki_*` writes** | Agent-driven | `wiki.py` tools | The agent decides page structure, links, what's fact vs inference. |
| **`share_thought`** | Agent-driven | `comms.py` tool | The agent decides it has something worth saying. Cadence *caps* are WS4's deterministic guardrail around it. |
| **Autonomy-rung advance** | Deterministic guardrail | `mission.py` | Rung is a stored field; tool policies read it. Advancing is a human action (WS5), not agent self-promotion. |

**The pattern:** *triggers and guardrails are deterministic; the thinking inside them is
the agent's.* The dream is the one fully-deterministic pass — and even it delegates the
per-page "distill this" step to a model call (an `llm_step`-equivalent), it just doesn't
delegate the *control flow*.

---

## C3 — The tool surface

All handlers are `async def` returning a JSON-serializable `dict`, registered via
`ctx.tool_registry.register("plugin-curiosity", ToolDef(...), handler)`. Policies follow
the architecture rule of thumb and the vision's autonomy ladder: **rungs 1–3 are all
read/write-to-own-tables/output-only, so everything below is `auto_approve` / `low`.**
Nothing here executes a change in the outside world — that's rung 4+, out of v1 scope.

Wiki page-schema fields (marked ⟶WS1) are named illustratively; WS1 owns their final form.

### Mission management

| Tool | Description | Params | Policy | Risk |
|---|---|---|---|---|
| `set_mission` | Create or replace the durable mission statement + scope. Restates what Luna is here to accomplish; everything (wiki, dreams, thoughts) scopes to it. | `statement:str` (required), `scope:str?`, `title:str?` | `auto_approve` | `low` |
| `get_mission` | Return the current mission: statement, scope, autonomy rung, cadence prefs, linked-wiki summary (page count + TOC). | — | `auto_approve` | `low` |
| `refine_mission` | Patch scope / title after learning more (append or narrow) without wiping the statement. | `scope:str?`, `title:str?`, `add_open_questions:list[str]?` | `auto_approve` | `low` |

*One active mission per Luna in v1* (matches today's global memory scoping in §1.1 of the
research plan). Multi-mission is a WS5/F3 open question; the schema carries a
`mission_id` FK from day one so it's a data migration, not a rewrite.

### Wiki (schema detail ⟶ WS1)

| Tool | Description | Params | Policy | Risk |
|---|---|---|---|---|
| `wiki_write_page` | Create or overwrite a page (title, body, `[[links]]`, citations). ⟶WS1 for the full field set (confidence, last-updated, open-questions). | `title:str` (req), `body:str` (req), `links:list[str]?`, `citations:list[str]?`, `confidence:str?` | `auto_approve` | `low` |
| `wiki_patch_page` | Revise part of an existing page (append a section, update a claim) without rewriting the whole thing — keeps the page living, not duplicated. | `title:str` (req), `patch:str` (req), `citations:list[str]?` | `auto_approve` | `low` |
| `wiki_read` | Read one page's full body by title (or slug). The on-demand fetch that keeps the wiki out of the always-on prompt (mitigates R4). | `title:str` (req) | `auto_approve` | `low` |
| `wiki_toc` | Return the table of contents: page titles + one-line summaries + link graph. The cheap index the agent scans before deciding what to `wiki_read`. | — | `auto_approve` | `low` |
| `wiki_search` | Semantic/keyword search across pages; returns matching snippets + page titles. Bridges to atomic memory (A4 cross-feed ⟶WS1). | `query:str` (req), `k:int?` | `auto_approve` | `low` |
| `wiki_list_open_questions` | List unresolved open questions across pages (what Luna still doesn't know) — feeds the dream and the next research pass. | — | `auto_approve` | `low` |

`wiki_write_page` / `wiki_patch_page` are **write** tools but write **only to the
plugin's own tables** (like every `interview_*` tool), so `auto_approve`/`low` is honest —
this is exactly the `plugin-interview` precedent (its `tools.py` docstring: *"Writes touch
only plugin tables, so all tools use the default auto_approve policy — no approval prompts
on the loop."*).

### Research

| Tool | Description | Params | Policy | Risk |
|---|---|---|---|---|
| `research_topic` | Investigate a topic end-to-end: search the live web, fetch the best sources, and write/patch wiki page(s) with cited findings. Wraps `plugin-web-access` (`web_search`/`web_fetch`) — does not reimplement HTTP. | `topic:str` (req), `depth:str?` (`quick`\|`deep`, default `quick`), `into_page:str?` | `auto_approve` | `low` |

`depth:quick` honors design principle #2 (quick-win before deep-dive): a shallow, visible
pass by default; `deep` is opt-in. The tool *calls* web-access tools rather than importing
its client — plugins can invoke other registered tools via the runtime, keeping web-access
the single owner of search/fetch/SSRF-posture (see C4).

### Reflection / sharing

| Tool | Description | Params | Policy | Risk |
|---|---|---|---|---|
| `share_thought` | Send the human one short, high-signal reflection: headline + 1–3 findings + one sharp question, with wiki-page citations. The proactive outbound surface. | `headline:str` (req), `findings:list[str]` (req), `question:str?`, `cites:list[str]?` | `auto_approve` | `low` |

**Cadence/noise control (batching, quiet hours, frequency caps — D3/R3) is WS4's
mechanism, not a tool arg.** `share_thought` *enqueues* a reflection; WS4 owns whether it
sends now, batches, or defers. The plugin exposes the *content contract* (headline /
findings / question / cites — D2); WS4 owns the *delivery channel and rate limiting*. In
v1, if WS4's mechanism isn't ready, `share_thought` falls back to `ctx.send_muted_message`
(the one channel that exists today), documented as a stopgap.

### Dream / consolidation trigger

`dream` is **not an agent tool** — the agent never decides to dream. It is a
**scheduler-invoked route** (WS2 owns the clock). See "Scheduler interface" below. There
is, however, one agent-facing companion:

| Tool | Description | Params | Policy | Risk |
|---|---|---|---|---|
| `list_recent_thoughts` | Read the distilled thoughts the last dream produced (so a live chat can reference "what I figured out overnight"). Doubles as a spend receipt (principle #4). | `since:str?`, `limit:int?` | `auto_approve` | `low` |

**Tool count for the manifest `[requires] tools`: 12.**

---

## C4 — Reuse map

| Source | Reuse verbatim | Adapt / pattern-copy | Build new |
|---|---|---|---|
| **`plugin-web-access`** | `web_search`, `web_fetch`, `http_request` — the entire research substrate. `research_topic` **calls these registered tools**, never reimplements HTTP/search. Web-access stays the sole owner of provider keys (Tavily/Google via its `CredentialSlot`s) and internet posture. | — | Only the *orchestration* in `research.py` (search → pick sources → fetch → distill → `wiki_write_page` with citations). |
| **`plugin-interview`** | — | **Pattern-copy heavily** — it's the reference: (1) `on_load` idempotent table creation via `ctx.engine.begin()` + `ALL_TABLES`; (2) `store.py` pure-persistence + `_INSTALL_GREETED_KEY` one-time-flag pattern → reuse for the one-time **mission kickoff**; (3) `routes.py` sidebar-iframe serving (`/ui/` + path-traversal guard); (4) `prompts.py` thin `CAPABILITY_NOTE` via `prompt_sections()` + full methodology delivered as a **tool result**, not a fat system block; (5) tool-result "next_step" nudges that steer the agent's loop. | The mission/wiki tables and the wiki-specific store logic. |
| **`plugin-playbooks`** | — | **Concept only, no dependency.** Borrow its context-economy discipline (iterate per page, never dump the whole wiki into one model call — its authoring skill hammers this) and its `TriggerSourceRegistry` interface *shape* as the model for how WS2's scheduler will reach the plugin. | `dream.py` as plain Python, not YAML. |
| **`plugin-funnelfighters`** | Its read-only funnel/ads/landing-page tools — the growth-mission proving ground (SP4) needs **zero new integration**; `research_topic` and the agent use funnelfighters' tools alongside web-access. | — | — |
| **`plugin-memory`** (core) | — | Cross-feed only (A4, ⟶WS1): wiki pages spawn atomic facts; facts cite wiki pages. The interface is memory's own tools; curiosity doesn't touch its tables. | — |

**Net-new code is small:** mission + wiki tables/store, the `research_topic` orchestrator,
the `dream` consolidation function, the `share_thought` contract, and the sidebar UI.
Everything else is web-access (as-is) + interview (as-pattern).

---

## File skeleton — `plugin-curiosity`

Package dir `plugin_curiosity/` (snake_case), plugin name `plugin-curiosity` (kebab).
Structure mirrors `plugin-interview` plus a `routes.py` scheduler endpoint.

```
plugins/plugin-curiosity/
  plugin_curiosity/
    __init__.py            # LunaPlugin subclass — on_load, prompt_sections, kickoff
    luna-plugin.toml       # data manifest (mirrors PluginManifest)
    models.py              # SQLAlchemy tables (mission, wiki_page, thought, meta)
    state.py               # module-level singletons (store handle) — no asyncio clock
    mission.py             # mission tools + logic
    wiki.py                # wiki tools + store methods (schema detail ⟶ WS1)
    research.py            # research_topic — orchestrates plugin-web-access tools
    dream.py               # deterministic consolidation pass (scheduler-invoked)
    comms.py               # kickoff muted message + share_thought + list_recent_thoughts
    prompts.py             # thin CAPABILITY_NOTE + research/dream methodology (tool-result text)
    store.py               # pure persistence, shared by tools + routes (interview pattern)
    routes.py              # sidebar UI + POST /dream (the WS2 scheduler entrypoint)
    assets/icon.png
    ui/                    # sidebar iframe: mission header, wiki browser, thoughts feed
      index.html  app.js  style.css
  tests/
    conftest.py  test_manifest.py  test_kickoff.py  test_dream.py
  pyproject.toml
  LICENSE  README.md
```

### `luna-plugin.toml` (keys)

```toml
name = "plugin-curiosity"
shown_name = "Curiosity"
icon = "compass"
version = "0.1.0"
description = "Give Luna a mission; she teaches herself, builds a wiki, dreams, and shares."
entry = "plugin_curiosity"
sdk_version = "0"
license = "MIT"
category = "global"
db_tables = ["plugin_curiosity_missions", "plugin_curiosity_wiki_pages",
             "plugin_curiosity_thoughts", "plugin_curiosity_meta"]
routes_module = "routes"
tags = ["curiosity", "mission", "wiki", "research", "proactive"]
# NOTE: depends_on omitted deliberately. plugin-web-access is a RUNTIME reuse
# (research_topic calls its registered tools if present) but not a hard load-order
# dependency — curiosity degrades gracefully to "seed from own knowledge" if absent,
# exactly like interview's methodology says.
readme = """..."""

[requires]
tools = 12
tables = 4

[[tools]]  # ...one block per tool in C3, each with policy + risk_level...
```

### `__init__.py` (structure — grounded in interview + web-access)

```python
from __future__ import annotations
import asyncio, logging
from typing import Any
from luna_sdk import LunaPlugin, PluginContext, PluginManifest, SidebarSection

from .models import ALL_TABLES
from .prompts import CAPABILITY_NOTE
from .store import CuriosityStore
from .mission import register_mission_tools
from .wiki import register_wiki_tools
from .research import register_research_tools
from .comms import register_comms_tools, kickoff_once

log = logging.getLogger("plugin-curiosity")

class CuriosityPlugin(LunaPlugin):
    manifest = PluginManifest(
        name="plugin-curiosity", shown_name="Curiosity", icon="compass",
        image="assets/icon.png", version="0.1.0",
        description="Give Luna a mission; she teaches herself, builds a wiki, dreams, and shares.",
        category="global", license="MIT",
        db_tables=[t.name for t in ALL_TABLES],
        routes_module="routes",
        sidebar_sections=[SidebarSection(id="curiosity", label="Curiosity",
                                         icon="compass", sort_order=20)],
    )

    def __init__(self) -> None:
        self._store: CuriosityStore | None = None

    async def on_load(self, ctx: PluginContext) -> None:
        # 1. idempotent table creation (interview pattern)
        async with ctx.engine.begin() as conn:
            for table in ALL_TABLES:
                await conn.run_sync(table.create, checkfirst=True)
        self._store = CuriosityStore(ctx.db_session_factory)

        # 2. register the 12 tools across the four seams
        register_mission_tools(ctx, self._store)
        register_wiki_tools(ctx, self._store)
        register_research_tools(ctx, self._store)   # calls plugin-web-access tools
        register_comms_tools(ctx, self._store)

        # 3. one-time proactive kickoff (see below) — best-effort, never blocks load
        self._schedule_kickoff(ctx)
        log.info("plugin-curiosity loaded (tools=12, tables=%d)", len(ALL_TABLES))

    async def prompt_sections(self) -> list[Any]:
        # thin always-on note; full research/dream methodology arrives as tool results
        return [CAPABILITY_NOTE]

    def _schedule_kickoff(self, ctx: PluginContext) -> None:
        async def _run() -> None:
            try:
                await kickoff_once(ctx, self._store)
            except Exception:
                log.debug("curiosity.kickoff_failed", exc_info=True)
        try:
            asyncio.get_running_loop().create_task(_run())  # noqa: RUF006
        except RuntimeError:
            pass
```

### `models.py` (shape — full wiki_page columns ⟶ WS1)

```python
# Base = declarative_base()  (from luna_sdk import declarative_base, JSONB, UUID)
# plugin_curiosity_missions : id, statement, scope, title, autonomy_rung(int, default 1),
#                             cadence_prefs(JSONB), status, created_at, updated_at
# plugin_curiosity_wiki_pages: id, mission_id(FK), slug, title, body(Text),
#                             links(JSONB), citations(JSONB), confidence, open_questions(JSONB),
#                             dirty(bool -> feeds the dream), updated_at   # columns ⟶ WS1
# plugin_curiosity_thoughts : id, mission_id(FK), headline, findings(JSONB), question,
#                             cites(JSONB), source('dream'|'share'), created_at
# plugin_curiosity_meta     : key(PK), value   # one-time flags — kickoff_done, etc.
# ALL_TABLES = (Mission.__table__, WikiPage.__table__, Thought.__table__, Meta.__table__)
```

### `state.py`

```python
# Module-level store handle so routes.py and tools share one instance.
# DELIBERATELY NO asyncio background clock here — the recurring dream is fired
# by the scheduler (WS2) via routes.POST /dream, not an in-process timer.
# (Rationale: hosted Lunas suspend when idle; an in-process asyncio task dies with
#  the throwaway boot loop — see plugin-playbooks' comment on startup hooks. WS2 owns
#  the survive-suspend story.)
store: "CuriosityStore | None" = None
```

### `routes.py` — the WS2 scheduler interface (plugin side only)

```python
def register_routes(app, ctx):
    from luna_sdk import get_current_user
    store = CuriosityStore(ctx.db_session_factory)
    router = APIRouter(prefix="/api/p/plugin-curiosity", tags=["curiosity"])

    # --- Scheduler entrypoint (WS2 owns the clock that calls this) -------------
    @router.post("/dream")
    async def run_dream(payload: DreamRequest, user=Depends(get_current_user)):
        # payload: { mission_id: str, mode: "nightly"|"weekly", window_hours?: int }
        # Runs the DETERMINISTIC consolidation pass in dream.py:
        #   for each dirty page -> distill -> resolve contradictions -> write thought
        #   -> clear dirty -> collect open questions -> enqueue one share_thought
        # Returns: { thoughts_written: int, pages_touched: int, open_questions: int }
        return await dream.run(store, ctx, mission_id=payload.mission_id, mode=payload.mode)

    # --- Read APIs for the sidebar iframe (interview routes.py pattern) --------
    @router.get("/mission")            async def mission(...): ...
    @router.get("/wiki")               async def wiki_toc(...): ...
    @router.get("/wiki/{slug}")        async def wiki_page(...): ...
    @router.get("/thoughts")           async def thoughts(...): ...

    # --- Sidebar UI (verbatim interview pattern: /ui/ + traversal guard) -------
    @router.get("/ui/")                async def ui_root(): ...
    @router.get("/ui/{path:path}")     async def ui(path: str): ...
    app.include_router(router)
```

**Scheduler contract (hand to WS2):**
- **Endpoint:** `POST /api/p/plugin-curiosity/dream`, auth-gated by `get_current_user`.
- **Request payload:** `{ "mission_id": str, "mode": "nightly" | "weekly", "window_hours"?: int }`.
- **Response:** `{ "thoughts_written": int, "pages_touched": int, "open_questions": int }`.
- **Cadence, retry, wake-from-suspend, and *which* Luna to wake are WS2's** — the plugin
  only guarantees the pass is idempotent (re-running over already-clean pages is a no-op)
  so a retrying scheduler is safe.
- Alternatively WS2 may bind via `TriggerSourceRegistry` and emit a bus event
  (`curiosity.dream.tick`) that a subscriber in `on_load` handles — the plugin can expose
  *either* shape; the route is the simpler v1 default.

---

## On-load kickoff — the proactive muted message

**The behavior:** a fresh Luna that already has a mission should, on load, proactively get
curious rather than sit idle — the vision's "the very next thing that should happen is Luna
getting interested."

**The mechanism** is the confirmed `ctx.send_muted_message(title, note, respond=True)`
one-time pattern — used identically by `plugin-interview`, `plugin-giphy`, and
`plugin-whatsapp`. A muted message injects a prompt to the agent (invisible framing;
`respond=True` makes the agent produce a real turn). It is **one-time and idempotent** via
a persisted `meta` flag, so it never re-fires or blocks load.

```python
# comms.py
_KICKOFF_KEY = "kickoff_done"

async def kickoff_once(ctx, store) -> bool:
    send = getattr(ctx, "send_muted_message", None)
    if send is None or store is None:
        return False
    if await store.meta_get(_KICKOFF_KEY):          # idempotent
        return False
    mission = await store.active_mission()
    if mission is None:
        return False        # no mission yet -> leave flag unset, retry on a later load
    note = (
        f"You have a mission: \"{mission.statement}\". Before anything else, GET CURIOUS.\n"
        "Do a QUICK first pass (principle: quick-win before deep-dive):\n"
        "1. Restate the mission in your own words and confirm scope with ONE or TWO "
        "crisp questions — not a questionnaire.\n"
        "2. Create 3-5 wiki STUB pages for the sub-domains this mission touches "
        "(wiki_write_page).\n"
        "3. Run ONE shallow research_topic pass and drop a SINGLE sharp early insight "
        "via share_thought — so the human feels signal fast.\n"
        "Keep it short and legible. Depth is opt-in later; the nightly dream will "
        "deepen it. Do NOT dump tokens into a long silent deep dive."
    )
    result = await send("Mission received — get curious", note, respond=True)
    if isinstance(result, dict) and result.get("error"):
        return False        # no conversation open yet -> retry later (interview pattern)
    await store.meta_set(_KICKOFF_KEY, "1")
    return True
```

**Two firing points, both handled by the same idempotent function:**

1. **Mission set while running.** `set_mission` calls `kickoff_once` after persisting — so
   giving Luna a mission mid-session immediately triggers curiosity.
2. **Fresh load with a pre-existing mission.** `on_load` schedules `kickoff_once` as a
   best-effort background task (never blocks boot). If no conversation is open yet, the
   flag stays unset and it retries on the next load — exactly interview's
   `_greet_install_once` behavior (its comment: *"If no conversation exists yet … the flag
   is left unset so the greeting is retried on a later load"*).

This keeps *that Luna gets curious* deterministic (a routine, C2) while the *brief she
writes* is fully agent-driven — the intended split.

---

## Open items handed to other workstreams

- **WS1 (wiki):** final `wiki_page` column schema (confidence, versioning/diffing,
  open-questions), context-injection strategy (TOC + on-demand `wiki_read` is assumed
  here to mitigate R4), and the wiki↔memory cross-feed (`wiki_search` is the seam).
- **WS2 (scheduling):** the clock behind `POST /dream`; cadence list; wake-from-suspend;
  which Luna/mission to fire. Plugin side is fully specified above.
- **WS4 (comms & pacing):** the durable outbound channel + cadence/quiet-hours/frequency
  caps behind `share_thought`. Plugin exposes the content contract; WS4 owns delivery.
- **WS5 (mission & trust):** multi-mission scoping and how the human advances the
  `autonomy_rung` field (which then gates rung-4+ write-tool policies). v1 ships rung 1–3
  only, all `auto_approve`/`low`.
