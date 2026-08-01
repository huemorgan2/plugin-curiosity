# Phase 1 — Execution Summary

**Status: complete.** plugin-wiki 0.2.0 is live on the dev Luna: 5 tables, 9 agent tools,
tier-1/tier-2 prompt injection, a `WikiProvider` on the provider registry, read-only API
routes, and a sidebar pane. 17/17 unit tests green; 5/5 headed dojo checks green; R4
injection budget verified live.

## What was done

- **Models** (`plugin_wiki/models.py`): `wiki_pages` (slug-unique, title/summary/body),
  `wiki_revisions` (every write appends), `wiki_citations`, `wiki_open_questions`,
  `wiki_links` (slug→slug edges, `kind` = wikilink|citation). Idempotent create via
  `ctx.engine` on load.
- **Store** (`store.py`): upsert (verbatim body + revision row + wikilink re-parse), patch
  (find must occur exactly once), lexical search (title 3× > summary 2× > body 1×), toc
  (meta only, never bodies), citations, open-question lifecycle. `[[slug|alias]]` and
  `[[slug#anchor]]` both resolve to `slug`; citation edges survive body rewrites.
- **Tools** (9): `wiki_toc/read/search/write/patch/cite/ask/resolve_question/
  list_questions`, all `auto_approve` (plugin-owned tables only).
- **Injection** (`injection.py`): tier-1 capability note (~68 tokens) always present;
  tier-2 recency-ranked TOC under a 2400-char (~600-token) budget with an "…and N more"
  overflow line. Bodies never injected.
- **Provider**: `ctx.provider_registry.register("wiki", WikiProvider(store))` — resolved
  live from plugin-curiosity (`GET /api/p/plugin-curiosity/status` → `wiki_provider:
  "resolved"`).
- **Routes + pane**: `GET /api/p/plugin-wiki/pages[/{slug}]`, `/links`, `/questions`
  (authed); `/ui/` serves an unauthenticated HTML shell (token via localStorage /
  parent postMessage, marketplace-pane pattern) listed in the sidebar as "Wiki".

## Verification

- **Unit:** 17/17 (`tests/test_store.py`, `tests/test_injection.py`) on sqlite+aiosqlite
  with a stubbed `luna_sdk`.
- **Dojo** (`dojo/tests/curiosity-phase1/walkthrough.mjs`, headed, 5/5):
  1. real chat turn: `wiki_write` → `wiki_read` roundtrip, agent confirms marker;
  2. page persisted with verbatim body via plugin route;
  3. wikilink edge materialized (`from`/`to`/`kind` in `/links`);
  4. **tier-2 injection proven live** — a tool-free chat turn quoted the new page's slug
     from the wiki TOC section of its system prompt (no `tool` messages in the turn);
  5. Wiki sidebar pane (iframe) lists the new page.
- **R4 budget, live:** seeded 22 pages → context breakdown `plugins` section went
  **1494 → 2103 tokens (+609)**, matching the computed tier-2 estimate (2437 chars ≈ 609
  tokens) and the ~600-token target; tier-1 is 68 tokens. Seeds cleaned up after.

## What we encountered

1. **`prompt_sections()` receives no turn/query argument** (core seam), so tier-2 cannot
   be query-relevance-ranked from the plugin side. Tier-2 is **recency-ranked**
   (updated_at desc). If per-turn relevance ranking becomes necessary, that is a core
   seam change, not a plugin change. Noted for phase 3/4.
2. **The sidebar pane iframe loads without auth headers** — the `/ui/` HTML route must be
   unauthenticated; data fetches inside the pane carry the token from localStorage.
3. **Route order matters**: `/pages/{slug:path}` must be declared after `/pages`,
   `/links`, `/questions`.
4. **sqlite Uuid pk coercion**: `session.get(Model, str_uuid)` raises StatementError on
   sqlite — coerce with `uuid.UUID(str(...))` in the store, map ValueError →
   PageNotFound.
5. **Dojo iframe timing**: a fixed 3s wait misses the pane iframe; poll for the frame
   (up to 30s) then wait for content inside it.
6. The `/links` route returns `from`/`to` keys (not `from_page`/`to_page`) — walkthrough
   originally asserted the wrong keys.

## What we learned

- The injection design holds live: thin always-on tier-1 + budgeted tier-2 TOC gives the
  agent wiki awareness for ~680 tokens total on a 20+-page wiki, and a tool-free turn
  demonstrably *sees* it.
- Chat-turn tool use is reliable: the agent picked `wiki_write` and `wiki_read` unaided
  from tool descriptions on the first attempt.
- The store/provider split keeps plugin-curiosity fully decoupled — it consumes only the
  `WikiProvider` surface, never the tables.

## Consider for the future

- **Phase 3/4**: reflections should cite pages via `[[slug]]` so the wikilink parser
  builds the reflection→wiki graph for free.
- **Phase 4**: `wiki_search` is lexical only. If research quality suffers, consider
  embedding-based search via plugin-memory's provider — separate decision, new seam.
- **Phase 1.5**: the pane is deliberately minimal (list + detail). The graph view should
  read `/api/p/plugin-wiki/links` — the edge data is already shaped for it
  (`from`/`to`/`kind`).
- **Tier-2 ranking**: recency-only. A future `prompt_sections(turn)` core seam would
  enable query-relevance ranking; do not work around it plugin-side.
