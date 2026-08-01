# WS1 — Knowledge Architecture (the LLM Wiki)

> Deliverable for the **Luna Curiosity** initiative (Theme A / WS1).
> Answers research questions **A1–A6** with concrete, decisive recommendations,
> grounded in the actual codebase.
>
> Companion to [vision.md](../vision.md) §5 and [research_plan.md](../research_plan.md) §3 Theme A.

---

## 0. Grounding — what the codebase actually gives us

Everything below is anchored to real files. The relevant facts:

- **Memory is atomic facts, not pages.** `memory_facts` is a single table of short
  `text` strings + `embedding_json` + a JSONB `context` provenance blob, recalled by
  semantic cosine top-5.
  → [`luna/plugins/plugin_memory/__init__.py`](../../../luna/plugins/plugin_memory/__init__.py)
  (`MemoryRow`, `PgVectorMemoryProvider.recall`).
- **Recall is injected every turn**, top-5, keyed on the last user message, rendered as
  bullet lines under a "Relevant memories" header (`MEMORY_RECALL_LIMIT = 5`).
  → [`luna/luna/agent/system_prompt.py`](../../../luna/luna/agent/system_prompt.py)
  (`recall_context`, `_render_fact_line`, section 9 of `system_prompt_sections`).
- **Memory is global per Luna instance.** No `mission_id` / `agent_id` column today.
  `context.conversation_id` is captured but unused for scoping.
  → [`plugin_memory/context.py`](../../../luna/plugins/plugin_memory/context.py) (`MemoryContext`).
- **A plugin can own its own DB tables** and create them idempotently in `on_load`, expose
  agent tools (with `auto_approve`/`ask`/`prompt_always` policies), FastAPI routes, a
  sidebar iframe, and a one-time proactive "muted message".
  → [`plugin-interview`](../../../plugins/plugin-interview/) is the closest existing pattern:
  it owns `plugin_interview_*` tables ([`models.py`](../../../plugins/plugin-interview/plugin_interview/models.py)),
  renders **markdown briefs** ([`store.py:brief`](../../../plugins/plugin-interview/plugin_interview/store.py)),
  and delivers heavy methodology **as a tool result**, keeping only a one-paragraph
  capability note always-on in the prompt
  ([`prompts.py`](../../../plugins/plugin-interview/plugin_interview/prompts.py): `CAPABILITY_NOTE` vs `METHODOLOGY`).

That last pattern — **fat content in tool results, thin pointer in the always-on prompt** —
is the single most important precedent for A3 (context-budget control). We reuse it directly.

---

## A1 — New store beside memory, or a refactor/superset of memory?

### Recommendation: **A NEW STORE, cross-linked to memory. Do not refactor memory.**

The wiki is a **new plugin** (`plugin-wiki`) owning its own tables, sitting *beside*
`plugin-memory`, not replacing or subsuming it.

**Rationale**

1. **They are different data shapes with different access patterns.** `memory_facts`
   optimizes *fast associative recall of atoms* — top-5 cosine, injected every turn,
   cheap, lossy-by-design. The wiki optimizes *coherent long-form understanding* — whole
   pages, revised in place, cross-linked into a graph, read on demand. Forcing pages into
   the atomic-fact table (or vice-versa) degrades both. The vision states this explicitly
   (§5: "complementary, not competitors").

2. **Refactoring memory is high-risk, low-reward.** `plugin-memory` is `critical=True` and
   `system_app=True` ([`__init__.py`](../../../luna/plugins/plugin_memory/__init__.py) manifest),
   with a live pgvector HNSW index path, an auto-extraction event subscription, and a
   provider contract (`MemoryProvider`) other code depends on. Absorbing the wiki into it
   would couple a stable core service to an experimental feature and put curiosity's iteration
   speed behind memory's stability bar. A separate plugin can be built, shipped, and deleted
   cleanly (the interview plugin's own docstring: "Copying this folder enables it; deleting it
   removes it cleanly").

3. **The cross-feed gives us the superset benefit without the merge cost.** We do not need one
   physical store to get unified recall; we need the two stores to *reference each other*
   (A4). A wiki page can spawn atomic facts into `memory_facts`; those facts carry a
   `wiki_page_slug` in their existing JSONB `context` column — no schema change to memory
   required.

4. **Scoping diverges (A5).** The wiki is per-mission from day one; memory is global today.
   Baking per-mission scoping into the global memory table would be a migration we don't need
   to take on now. Keeping them separate lets the wiki be scoped while memory stays global.

**Rejected alternative:** *"memory as a superset — pages are just long facts."* Long free-text
in `memory_facts` breaks the top-5 recall model (one 2000-word page evicts five useful atoms),
has no revision/versioning story, and no title/link/citation structure. Dead on arrival.

---

## A2 — Storage shape: markdown files vs DB tables vs hybrid. Versioning/diffing.

### Recommendation: **DB tables (à la plugin-interview), markdown *in* a `body` column. Hybrid only for export.**

Store pages as **rows in plugin-owned tables**, where the page body is a **markdown string
column**. This is exactly how `plugin-interview` stores its content (`InterviewSession.domain_brief`,
`InterviewTopic.notes` are `Text` columns; the brief is *rendered* markdown, not a file).

**Why DB, not files on the plugin volume**

- **Consistency with the working precedent.** Every persistent plugin in-tree (memory,
  interview) uses SQLAlchemy tables created idempotently in `on_load`
  ([`plugin-interview/__init__.py`](../../../plugins/plugin-interview/plugin_interview/__init__.py):
  `for table in ALL_TABLES: await conn.run_sync(table.create, checkfirst=True)`). Files-on-volume
  is a *second* persistence mechanism with its own concurrency, backup, and multi-tenant
  isolation concerns — none of which the volume story on hosted Luna has solved.
- **Query needs.** We need to list pages by mission, resolve `[[slug]]` links, filter by
  `status`/`confidence`, and (A4) join facts → pages. That's relational work. Files force a
  full-directory scan + parse for every list/link resolution.
- **Embeddings live naturally next to the row** (mirroring `memory_facts.embedding_json`),
  which we need for the retrieval slice in A3.
- **Multi-tenant hosted Luna.** Rows inherit the per-instance Postgres isolation that already
  exists; volume files would need their own per-tenant pathing.

**Why markdown as the body format (not structured JSON blocks)**

Legibility is a first-class design principle (vision §8.3: "the human can *read Luna's mind*").
Markdown is what the human reads in the sidebar and what the agent writes/edits fluently.
`[[links]]`, headings, and citations all live as plain markdown conventions inside the body,
matching the memory index's existing `[[link]]` style noted in the vision.

**Versioning / diffing — recommendation:**

Keep a lightweight **append-only revision table**, not a git-style file history.

- `wiki_pages` holds the *current* version of each page (the fast read path).
- `wiki_page_revisions` holds prior `body` snapshots + a `summary` of the change and the
  `dream_run_id` / turn that produced it. One row per save.
- **Diffing is computed on read**, not stored — a route renders a unified diff between two
  revisions' `body` columns using Python's `difflib`. No need to persist diffs.
- This gives the "living page" story (vision §5: "revised as understanding deepens.
  Contradictions get resolved, not duplicated") plus an audit trail for the human, at trivial
  cost. It directly serves R5 (grounding/hallucination): a reviewer can see *when* and *why* a
  claim changed.

**Hybrid, but only for export:** offer a route (`GET …/pages/{slug}.md`) that streams the
current `body` as a `.md` file for the human to download or hand to another tool. Storage of
record stays in the DB.

---

## A3 — Getting wiki content into context without blowing the budget (R4)

This is the key risk. The vision is explicit (research_plan R4: "Long pages can't all live in
the prompt. Mitigation: TOC + on-demand fetch tool").

### Recommendation: **Three-tier injection — always-on capability note + auto-injected TOC/active-page pointer + on-demand `wiki_read` tool. Never inject full page bodies by default.**

This mirrors the interview plugin's proven split (`CAPABILITY_NOTE` always-on, `METHODOLOGY`
delivered only as a tool result) and extends it with a retrieval slice.

**Tier 1 — Always-on capability note (~40 tokens).** A single paragraph via the plugin's
`prompt_sections()` hook (the same mechanism interview uses:
[`__init__.py:prompt_sections`](../../../plugins/plugin-interview/plugin_interview/__init__.py)
returning `[CAPABILITY_NOTE]`). Tells the agent the wiki exists and how to open it. Fixed cost,
independent of wiki size.

**Tier 2 — Auto-injected, per-turn, budget-capped "wiki context block" (~200–400 tokens).**
Injected as one more `PromptSection` alongside the existing memory `recall_snippet` (section 9
of [`system_prompt_sections`](../../../luna/luna/agent/system_prompt.py)). It contains, for the
**active mission only**:

  - a generated **table of contents**: page titles + slugs + one-line summaries + `status`
    (`stub`/`draft`/`solid`) + `confidence`;
  - **plus** the 1–2 most **semantically relevant page summaries** to the last user message,
    retrieved the same way memory does its top-5 (cosine over a per-page `summary_embedding`).

  This is a *table of contents with a relevance-ranked spotlight* — enough for the agent to
  know what it already knows and decide what to open, never the full bodies. Hard token cap
  enforced by the plugin (truncate the TOC, drop lowest-priority pages first).

**Tier 3 — On-demand full read via `wiki_read(slug)` tool.** The agent pulls a full page body
into context *only when it decides it needs it*, exactly as interview delivers `METHODOLOGY` as
a tool result. A page can be large; it enters context once, for the turns that need it, then
ages out of the window naturally. `wiki_read` can also return a specific section (`#heading`)
to keep even single-page reads cheap.

**Why this shape**

- **Bounded and predictable.** Per-turn cost is Tier1 + Tier2, both hard-capped and independent
  of how big the wiki grows. Depth is pulled in by the agent's own judgement, tethered to a
  need — matching vision §8.2 ("prefer an early, shallow, legible pass").
- **Legible spend (vision §8.4).** Every `wiki_read` is a visible tool call — the human can see
  exactly which pages Luna consulted, a natural spend receipt.
- **It's the pattern that already works.** We are not inventing a mechanism; we are
  parameterizing the interview plugin's `CAPABILITY_NOTE`/`METHODOLOGY`/tool-result split with a
  memory-style retrieval slice.

**Explicitly rejected:** injecting full page bodies each turn (blows budget — the R4 failure
mode), or injecting *no* TOC (agent can't discover what it already knows and re-researches).

---

## A4 — How wiki and atomic memory cross-feed

Two directions, both cheap because they reuse existing columns.

### Pages → facts (wiki distills atoms for fast recall)

When Luna writes or substantially edits a page, she may emit a handful of **atomic facts** into
`memory_facts` via the existing `memory_remember` tool
([`plugin_memory/__init__.py:_remember_handler`](../../../luna/plugins/plugin_memory/__init__.py)).
Each such fact carries provenance in memory's existing JSONB `context` column:

```json
{ "source": "wiki", "trigger": "wiki_distilled",
  "wiki_page_slug": "funnel-map", "wiki_mission_id": "…" }
```

`MemoryContext` already has `extra="allow"`
([`context.py`](../../../luna/plugins/plugin_memory/context.py)), so `wiki_page_slug` needs **no
schema change to memory** — it just rides along in `context`. Result: the punchy conclusions from
a page ("second-session return predicts payment better than pageviews") surface in the every-turn
top-5 recall, while the *reasoning* stays in the page, fetched on demand.

The "dream" pass (WS2) is the natural place to run this distillation in batch, keeping it off the
hot conversational path.

### Facts → citations (atoms point back to the page that explains them)

Because those facts carry `wiki_page_slug`, memory's recall render can add a source pointer.
`recall_context` already renders a trailing clause per fact via `MemoryContext.to_human_phrase()`
([`system_prompt.py:_render_fact_line`](../../../luna/luna/agent/system_prompt.py)). We extend the
phrase renderer so a wiki-sourced fact reads:

> - "second-session return predicts payment better than pageviews" — from wiki page *Which Events Matter*

The agent can then `wiki_read("which-events-matter")` to get the full evidenced argument. This is
the "distinguish 'I read this' from 'I inferred this'" requirement (vision §5, R5): facts sourced
from a cited page are auditable; the citation is a live link to the page.

### The page's own citations

Independently, each page body carries inline **citations** (URLs, product-data references,
conversation refs) — see the schema in A6 (`citations` field). These are what make a claim
auditable *within* the wiki and are mandatory for any non-obvious claim (R5 mitigation:
"citations mandatory").

**Net:** one direction is a `memory_remember` call with `wiki_page_slug` in context; the other is
a render tweak in `_render_fact_line`. No new plumbing, no memory migration.

---

## A5 — Per-mission scoping vs today's global memory

### Recommendation: **Wiki is per-mission from day one (`mission_id` on every page). Memory stays global for now; bridge via context tags, not a memory migration.**

**Wiki: per-mission is non-negotiable.** The vision is unambiguous (§5: "Per-mission. Each
mission gets its own knowledge base, scoped and coherent"). A `Funnel Map` for the growth mission
must not bleed into a hiring mission's wiki. So every wiki row carries a `mission_id` FK, and
`wiki_list` / the Tier-2 TOC / retrieval are **always filtered to the active mission**.

**Memory: leave global; do not migrate it now.** `memory_facts` has no `mission_id` today and is a
`critical` system service. Adding mission scoping to memory is out of scope for WS1 and would be a
risky migration for little near-term gain — global facts like "the owner is on mobile mostly" are
*meant* to be cross-mission.

**How they interoperate without a memory migration:**

- Wiki-distilled facts (A4) already carry `wiki_mission_id` inside memory's JSONB `context`. That
  gives us **soft** mission scoping on the memory side for free: recall can *prefer* or *label*
  facts belonging to the active mission without a schema change or index change.
- If, later, we want *hard* per-mission memory filtering, the path is a lightweight `context ->>
  'wiki_mission_id'` filter in the recall query — additive, no column, no data migration. Note as
  a future option, not a v1 requirement.

**Where the mission object lives:** WS5 (Mission & Trust) owns the first-class `mission` object.
For WS1 we assume it exists and exposes a `mission_id` + a durable statement. The wiki plugin holds
the FK and, until WS5 lands, can own a minimal `wiki_missions` table (id, statement, created_at) so
the wiki is buildable/spikeable (SP1/SP4) without blocking on WS5. When WS5's mission object lands,
`wiki_pages.mission_id` re-points to it.

---

## A6 — Concrete page schema

### Field table

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | UUID | ✓ | PK, `default=uuid4` (mirrors `MemoryRow.id`). |
| `mission_id` | UUID (FK) | ✓ | Scopes the page. A5. |
| `slug` | str(128) | ✓ | Stable link target for `[[slug]]`. Unique per mission. |
| `title` | str(256) | ✓ | Human-readable, shown in TOC. |
| `summary` | str(512) | ✓ | One–two line abstract. Used in the Tier-2 TOC (A3) — never dump the body there. |
| `body` | Text (markdown) | ✓ | The page. Contains `[[links]]`, headings, inline citation markers. |
| `links` | JSONB (list[str]) | | Outbound `[[slug]]` targets, denormalized from `body` on save for fast graph queries. |
| `citations` | JSONB (list[obj]) | | `[{ "marker": "1", "kind": "url\|product_data\|conversation", "ref": "https://…", "note": "…" }]`. Mandatory for non-obvious claims (R5). |
| `confidence` | Float 0–1 | ✓ | Luna's own confidence in the page. Default 0.5. Surfaces low-confidence claims in dream (R5). |
| `status` | str(16) | ✓ | `stub` / `draft` / `solid` / `stale`. Drives TOC rendering + dream prioritization. |
| `open_questions` | JSONB (list[str]) | | What Luna still doesn't know — fuels reflections & the next research pass. |
| `source` | str(32) | ✓ | Provenance of the *page*: `agent_research` / `dream` / `user`. Mirrors `MemoryRow.source`. |
| `summary_embedding` | Text (JSON floats) | | Embedding of `title + summary` for the Tier-2 retrieval slice (A3). Same shape as `memory_facts.embedding_json`. |
| `created_at` | datetime tz | ✓ | `default=_utcnow`. |
| `updated_at` | datetime tz | ✓ | `default=_utcnow, onupdate=_utcnow` (exactly as `InterviewSession`). |

Revision history lives in a sibling table `wiki_page_revisions` (A2): `id`, `page_id` FK,
`body`, `summary` (change note), `confidence`, `created_by` (`dream`/`turn`), `created_at`.

### SQLAlchemy model sketch (consistent with plugin-interview `models.py`)

```python
# plugin_wiki/models.py  — mirrors plugins/plugin-interview/plugin_interview/models.py
from __future__ import annotations
import uuid as _uuid
from datetime import UTC, datetime
from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from luna_sdk import JSONB, UUID, declarative_base

Base = declarative_base()
def _utcnow() -> datetime: return datetime.now(UTC)


class WikiMission(Base):
    """Minimal stand-in until WS5's first-class mission lands; then FK re-points."""
    __tablename__ = "plugin_wiki_missions"
    id: Mapped[_uuid.UUID] = mapped_column(UUID(), primary_key=True, default=_uuid.uuid4)
    statement: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class WikiPage(Base):
    __tablename__ = "plugin_wiki_pages"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(), primary_key=True, default=_uuid.uuid4)
    mission_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(), ForeignKey("plugin_wiki_missions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    summary: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)               # markdown
    links: Mapped[list | None] = mapped_column(JSONB, nullable=True)                  # ["slug", ...]
    citations: Mapped[list | None] = mapped_column(JSONB, nullable=True)              # [{marker,kind,ref,note}]
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="stub", nullable=False)   # stub|draft|solid|stale
    open_questions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="agent_research", nullable=False)
    summary_embedding: Mapped[str | None] = mapped_column(Text, nullable=True)        # JSON floats, à la memory
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    __table_args__ = (Index("ix_plugin_wiki_pages_mission_slug", "mission_id", "slug", unique=True),)


class WikiPageRevision(Base):
    __tablename__ = "plugin_wiki_page_revisions"
    id: Mapped[_uuid.UUID] = mapped_column(UUID(), primary_key=True, default=_uuid.uuid4)
    page_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(), ForeignKey("plugin_wiki_pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    summary: Mapped[str] = mapped_column(String(512), default="", nullable=False)     # change note
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    created_by: Mapped[str] = mapped_column(String(16), default="turn", nullable=False)  # turn|dream|user
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


ALL_TABLES = (WikiMission.__table__, WikiPage.__table__, WikiPageRevision.__table__)
```

Tables are created idempotently in `on_load` exactly as interview does
(`for t in ALL_TABLES: await conn.run_sync(t.create, checkfirst=True)`), and the manifest
declares `db_tables=[t.name for t in ALL_TABLES]`.

### Equivalent markdown-frontmatter view (for export / the `.md` download route)

The same page rendered as a portable file — the on-disk shape only used for export (A2):

```markdown
---
slug: funnel-map
title: Funnel Map
mission_id: 5f1c…
status: draft
confidence: 0.6
source: agent_research
open_questions:
  - Is "company size" used downstream or can we drop it?
citations:
  - { marker: "1", kind: url, ref: "https://baymard.com/…", note: "mobile form-abandon stats" }
  - { marker: "2", kind: product_data, ref: "funnelfighters:funnel/checkout", note: "step-3 drop" }
updated: 2026-07-07T09:00:00Z
---

# Funnel Map

Our checkout funnel has four steps … The biggest drop is **mobile step 3** [2],
where the form asks for company size before the user has seen value [1].

See also [[which-events-matter]] and [[landing-page-principles]].
```

---

## Recommended data model (summary)

- **`plugin_wiki_pages`** — current version of each page (fast read path).
- **`plugin_wiki_page_revisions`** — append-only history for diffing/audit.
- **`plugin_wiki_missions`** — minimal mission stand-in until WS5 lands.
- **Cross-feed uses existing memory columns** — no `memory_facts` migration; wiki-sourced facts
  ride in memory's JSONB `context` with `wiki_page_slug` + `wiki_mission_id`.

---

## Tool surface the plugin exposes

Following the interview convention — thin handlers, persistence-only, most tools `auto_approve`
because they touch only the plugin's own tables (interview's tools.py notes exactly this). Names
match the vision/research_plan (`wiki_write_page`, `wiki_read`, `wiki_list`, `wiki_link`).

| Tool | Purpose | Policy | Injects into context? |
|---|---|---|---|
| `wiki_write_page(mission_id, slug, title, summary, body, citations?, status?, confidence?, open_questions?)` | Create a page (or stub). Denormalizes `[[links]]` from `body`, computes `summary_embedding`, writes a revision row. | `auto_approve` | No |
| `wiki_edit_page(slug, body?, summary?, status?, confidence?, add_citations?, open_questions?, change_note)` | Revise an existing page in place; snapshots prior body into revisions. `change_note` is required (legibility). | `auto_approve` | No |
| `wiki_read(slug, section?)` | **Pull a full page (or one `#section`) into context on demand.** The Tier-3 mechanism of A3. | `auto_approve` | Yes (tool result) |
| `wiki_list(mission_id?, status?)` | Return the TOC: titles + slugs + summaries + status + confidence. Cheap; no bodies. | `auto_approve` | Yes (compact) |
| `wiki_link(from_slug, to_slug, note?)` | Assert a `[[link]]` between pages (also auto-derived from body, but explicit linking lets the agent build the graph deliberately). | `auto_approve` | No |
| `wiki_search(mission_id, query, limit=3)` | Semantic search over `summary_embedding`; returns page summaries + slugs. Backs the Tier-2 retrieval slice; also callable directly. | `auto_approve` | Yes (compact) |
| `wiki_diff(slug, from_rev?, to_rev?)` | Render a unified diff between two revisions (for "what changed last night"). | `auto_approve` | Yes (small) |
| `wiki_delete_page(slug)` | Remove a page. Rare; destructive. | `ask` | No |

Not a tool, but part of the surface:
- **`prompt_sections()`** returns the Tier-1 capability note (always-on, ~40 tokens).
- **A per-turn injector** contributes the Tier-2 TOC/active-page block as a `PromptSection`
  beside memory's `recall_snippet` in
  [`system_prompt.py`](../../../luna/luna/agent/system_prompt.py).
- **FastAPI routes + a sidebar section** ("Wiki") render pages as readable markdown and expose
  the `.md` export and diff views — the "read Luna's mind" surface (vision §5), mirroring how
  interview ships a sidebar + `routes_module`.

---

## Worked example — the Growth mission wiki

Mission (from vision §6): *"Optimize the whole funnel for our products. Grow traffic that
converts to paying customers by optimizing campaign budgets, ads, landing pages, and the events
we track."*

Below are three pages as they'd exist after Luna's first day, using **only existing read-only
tools** ([`plugin-funnelfighters`](../../../plugins/plugin-funnelfighters/) for product data,
[`plugin-web-access`](../../../plugins/plugin-web-access/) for research) — no new integrations,
per the vision's "quick wins" constraint.

### Page 1 — `funnel-map` (status: draft, confidence: 0.6)

```markdown
# Funnel Map

Our funnel has four steps: **ad click → landing page → signup → checkout**.
Pulled live from funnelfighters [1].

- **Step 3 (mobile) is the biggest drop.** The checkout form asks for *company
  size* before the user has seen product value [1]. Cross-category benchmarks say
  asking qualifying questions pre-value is a top mobile-abandon cause [2].
- High-intent keywords currently route to the **generic homepage**, not a matched
  landing page — see [[landing-page-principles]].

**Open questions**
- Is "company size" used downstream (routing, pricing) or can we drop it?

**Citations**
[1] product_data — funnelfighters:funnel/checkout (step-3 drop = 41%)
[2] url — https://baymard.com/… (mobile form-abandonment)

See also [[which-events-matter]], [[landing-page-principles]].
```

### Page 2 — `which-events-matter` (status: draft, confidence: 0.55)

```markdown
# Which Events Matter

Most teams in our category track **pageviews and signups**. Those are weak
predictors of payment.

- The event that best predicts payment is **second-session return** [1] — a user
  who comes back within 72h converts far more often. We do **not** currently
  track this [2].
- Raw pageviews correlate with spend, not revenue; optimizing for them can *lower*
  paid conversion by rewarding cheap, low-intent traffic.

**Open questions**
- Do we have the analytics hooks to define a "second session" event today?

**Citations**
[1] url — https://…growth-benchmarks (return-visit → payment)
[2] product_data — funnelfighters:events (no return-session event configured)

See also [[funnel-map]].
```

This page is the source of a **distilled memory fact** (A4): `memory_remember("second-session
return predicts payment better than pageviews", context={"source":"wiki",
"wiki_page_slug":"which-events-matter", "wiki_mission_id":"…"})` — so the punchline reaches every
turn's top-5 recall while the argument stays here.

### Page 3 — `landing-page-principles` (status: stub → draft, confidence: 0.4)

```markdown
# Landing Page Principles

Working notes; low confidence, needs a second pass.

- **Message match:** the landing page headline should mirror the ad/keyword intent.
  Today high-intent keywords hit the generic homepage (see [[funnel-map]]) — a
  message-match miss.
- **Defer friction:** don't ask qualifying questions (e.g. company size) until
  after the value moment. Ties directly to the mobile step-3 drop in [[funnel-map]].

**Open questions**
- Which two live pages should I critique first — pricing or homepage?
- Do we have a page builder I could later draft changes in?

**Citations**
[1] url — https://…landing-page-message-match
```

These three pages cross-link into a small graph (`funnel-map ↔ which-events-matter ↔
landing-page-principles`), each cites its sources, each flags open questions — which become the
"two sharp questions" Luna shares (vision §6: *"is 'company size' actually used downstream, or
can we drop it?"*). The nightly **dream** (WS2) later raises confidence, resolves the open
questions, marks pages `solid`, and distills more facts into memory.

---

## Decisions this resolves (feeds research_plan §6)

- **A1 / Open Decision 1:** *New store beside memory, cross-linked.* Confirmed — new
  `plugin-wiki`, no memory refactor.
- **A2:** DB tables with markdown `body`; append-only revision table; diffs computed on read;
  files only for export.
- **A3 (R4):** Three-tier injection — always-on note + capped TOC/retrieval slice + on-demand
  `wiki_read`. Full bodies never auto-injected. Prove in **SP1**.
- **A4:** Cross-feed via existing memory JSONB `context` (`wiki_page_slug`) + a `_render_fact_line`
  citation tweak. No memory migration.
- **A5:** Wiki per-mission from day one (`mission_id` FK); memory stays global; soft mission
  scoping in memory rides in `context` if needed later.
- **A6:** Schema delivered as a table, a SQLAlchemy sketch (mirroring interview `models.py`), and
  a frontmatter export view.

**Open items handed onward:** the first-class `mission` object (WS5 — wiki uses a minimal
`wiki_missions` stand-in until then); the nightly dream that drives distillation + confidence
updates (WS2); whether wiki is its own plugin or folded into a larger curiosity plugin (WS3/C1 —
this doc assumes a dedicated `plugin-wiki` module, which can still ship inside one plugin package).
