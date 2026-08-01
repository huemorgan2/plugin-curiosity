# Phase 1 — plugin-wiki (the knowledge substrate)

**Goal:** a working Karpathy-style knowledge store Luna can read and author, injected into
context within budget. This is the substrate every later phase leans on.

**Depends on:** Phase 0. **Spike:** **SP1** (wiki store + 3-tier injection).

---

## Scope

**In:** wiki tables, the `wiki_*` tool surface, 3-tier context injection, the `WikiProvider`
seam, minimal sidebar/route for reading pages.

**Out:** who *writes* the wiki and when (that's research/dream, phases 4–5); missions
(phase 2). The wiki here is mission-agnostic and driven only by direct tool calls.

---

## Model (copy `plugin-interview`'s DB + body-column pattern)

Tables (all plugin-owned, idempotent create in `on_load`):
- `wiki_pages` — `id, mission_id (nullable now), slug, title, summary, body (markdown),
  updated_at`. Markdown lives in `body`, exactly like interview.
- `wiki_revisions` — append-only history: `page_id, body, note, created_at`.
- `wiki_citations` — `page_id, url, note` (populated later by research).
- `wiki_open_questions` — `page_id (nullable), question, status`.
- `wiki_links` — `from_page, to_page, kind` (materialized graph edges). Populated by parsing
  `[[slug]]` wikilinks out of `body` on every `wiki_write`/`wiki_patch`, so the agent authors
  the knowledge graph just by writing prose — no separate linking tool. Citations become a
  second edge kind (page → source); `mission_id` gives an optional cluster. **The graph *view*
  is deferred to phase 1.5** — this table exists now so edges accumulate from day one.

## Tools (all `auto_approve`, low-risk — touch only own tables)

- `wiki_toc` → titles + summaries (the map).
- `wiki_read(slug)` → full page body **as a tool result** (tier 3 — never auto-injected).
- `wiki_search(query)` → relevance-ranked page summaries.
- `wiki_write(slug, title, body)` / `wiki_patch(slug, edit)` → create/update + revision row +
  re-parse `[[slug]]` wikilinks into `wiki_links`.
- `wiki_list_questions` → open questions.

## 3-tier context injection (retires R4)

1. **Tier 1 — always on (~40 tokens):** a thin capability note ("You keep a wiki; N pages;
   use `wiki_toc`/`wiki_read`").
2. **Tier 2 — per turn:** TOC + relevance-ranked page **summaries** beside memory's existing
   top-5 recall snippet. Summaries only, budget-capped.
3. **Tier 3 — on demand:** full body via `wiki_read` tool result.

Full bodies are **never** auto-injected. Mirror how `plugin-interview` delivers heavy detail.

## WikiProvider (the seam decided in Phase 0)

Expose read/write helpers (`get_page`, `upsert_page`, `toc`, `search`) via the path Phase 0
confirmed (ProviderRegistry registration *or* importable service module). `plugin-curiosity`
consumes this in later phases — no direct table access across plugins.

---

## Steps

1. SP1: create tables; implement `wiki_write`/`wiki_read`/`wiki_toc`; confirm markdown
   round-trips and a revision row is written on each edit.
2. Implement `wiki_search` (reuse the memory embedding path if trivial; else title/summary
   lexical match — embeddings can come later).
3. Implement 3-tier injection; measure token cost of tiers 1–2 on a 20-page wiki.
4. Register `WikiProvider`; add a read-only `/api/p/plugin-wiki/pages` route + minimal sidebar
   list (copy interview's UI wiring).

## Acceptance criteria

- [ ] Agent can `wiki_write` a page and `wiki_read` it back verbatim; edit creates a revision.
- [ ] A `[[slug]]` in a page body materializes a `wiki_links` edge; editing the body updates
      the edge set (graph rendering itself is phase 1.5).
- [ ] Tier-1 note is always present; tier-2 injects TOC+summaries **only**; full body appears
      only after a `wiki_read` call.
- [ ] Measured tier-1+2 injection stays within an agreed token budget on a 20-page wiki
      (record the number — this is the R4 evidence).
- [ ] `WikiProvider` resolvable from another plugin's `ctx` on the dev Luna.
- [ ] Sidebar lists pages and opens a body.

## Notes / risks

- `mission_id` is nullable here so the wiki stands alone before phase 2 wires missions.
- Keep search dumb if embeddings add friction; ranking quality is a later optimization.
