# Phase 1.5 — deep wiki UI & knowledge graph

**Goal:** the wiki's payoff surface — a full reading/editing panel plus an Obsidian-style
knowledge-graph view that makes "what Luna understands" visible. This is the legibility pillar
of the vision, made literal.

**Depends on:** Phase 1 (store + `wiki_links` edges already accumulating). **Spike:** none —
this is a frontend build, de-risked by copying `plugin-playbooks`.

> **Phase-1 learnings (verified live):** the sidebar section + iframe pane already exist —
> phase 1 shipped a minimal vanilla-JS list/detail pane at `/api/p/plugin-wiki/ui/`. This
> phase REPLACES that pane with the React build; keep the same route so the manifest entry
> is untouched. Two verified constraints: (a) the Shell iframes `/ui/` with **no auth
> header** — the HTML route must stay unauthenticated, data fetches use the token from
> localStorage/postMessage; (b) `/api/p/plugin-wiki/links` already returns edges as
> `{from, to, kind}` (kind = wikilink|citation) — the `/graph` route just reshapes this
> plus `pages` into React Flow's `{nodes, edges}`.

**Off the critical path.** The curiosity loop (phases 2–6) works without this. It's sequenced
here so it *can* be built early for demo value, but phases 2–6 do not block on it — phase 1's
vanilla-JS list is enough for functional validation.

---

## Scope

**In:** a `wiki-src/` React + Vite app served as a sidebar-section iframe; deep page view
(rendered markdown, revisions, citations, open questions, TOC, search); a React Flow graph of
pages and their links; live re-render on agent edits.

**Out:** any backend/tool changes (phase 1 owns the store and already materializes
`wiki_links`); mission/research/dream behavior.

---

## Mechanism (grounded — copy `plugin-playbooks`)

Luna core ships **no shared graph component**; each plugin brings its own. Verified paths:

- **Register a sidebar section** in the manifest:
  `SidebarSection(id="wiki", label="Wiki", icon="book-open", sort_order=50)`
  (`luna/luna/plugins/base.py`). Core reads `GET /api/ui/plugins`; Shell renders the nav item.
- **Serve a self-contained iframe** at `/api/p/plugin-wiki/ui/` via a `serve_ui` /
  `serve_ui/{path}` FastAPI route (pattern from `plugin-interview/routes.py:52`). Shell mounts
  it in `PluginIframe` (`luna/ui/src/views/Shell.tsx:413`) and passes an auth token via
  `postMessage` (`{type:'luna-auth', token}`); the iframe calls back with
  `Authorization: Bearer <token>`.
- **Build**: a `wiki-src/` React app with `@xyflow/react`, `vite build` → baked into
  `plugin_wiki/ui/dist`, served with versioned asset URLs (exactly `plugin-playbooks`'
  `ui-src/` → dist flow).

## The graph

- **Data route:** `GET /api/p/plugin-wiki/graph` → `{ nodes: [{id, label, mission_id, kind}],
  edges: [{source, target, kind}] }` — React Flow's native shape. Nodes = `wiki_pages` rows;
  edges = `wiki_links` (page→page) + `wiki_citations` (page→source, distinct kind);
  `mission_id` drives cluster/color.
- **Rendering:** custom node component modeled on `plugin-playbooks`' `StepNode.tsx` — title,
  summary on hover, click → open the deep page view. `buildGraph` in
  `plugin-playbooks/ui-src/src/playbooks/layout.ts` is the reference for shaping/laying out.
- **Live updates:** reuse the playbooks pattern — when research or the dream patches a page,
  emit a `luna:wiki-patch` custom event so the graph re-lays-out and the changed node glows
  (`node-arriving` CSS). This is the "watch her understanding take shape" moment.

## Deep page view

Rendered markdown `body`, revision history (`wiki_revisions`), citations list
(`wiki_citations`), inline open questions (`wiki_open_questions`), TOC nav, and search — all
over the read routes phase 1 already exposes. Editing stays agent-driven for v1 (human editing
is a later add); the panel is read-first with the graph as the entry point.

---

## Steps

1. Scaffold `wiki-src/` (React + Vite + `@xyflow/react`); wire the manifest sidebar section and
   the `serve_ui` routes; confirm the empty iframe loads authenticated.
2. Add `GET /api/p/plugin-wiki/graph`; render nodes/edges with a custom node component; click →
   deep page view.
3. Build the deep page view (markdown, revisions, citations, questions, TOC, search).
4. Wire `luna:wiki-patch` live updates so agent edits animate into the graph.
5. Verify on a real running Luna with a 20+ page wiki.

## Acceptance criteria

- [ ] "Wiki" sidebar section loads a plugin iframe, authenticated via `postMessage`.
- [ ] The graph renders one node per page and edges from `[[slug]]` links + citations; clicking
      a node opens its page.
- [ ] Deep page view shows rendered markdown, revision history, citations, and open questions.
- [ ] An agent edit (research/dream patch) live-updates the graph without a manual refresh.
- [ ] Verified on a **real running Luna**, not just a dev build.

## Notes / risks

- Real frontend work (a Vite bundle) — heavier than the rest of the plugin. Keeping it off the
  critical path means a slip here never delays the phase-6 vision validation.
- No new backend: if `wiki_links` from phase 1 is missing edges, fix the parser there, not here.
