# Phase 1.5 — execution summary

**Status: DONE.** Wiki React UI + knowledge graph shipped as plugin-wiki 0.3.0; all acceptance
criteria verified live in a headed browser (6/6 dojo checks), including SSE-driven live graph
updates from a real agent chat turn.

## What was done

### Backend (plugin-wiki, no core changes)
- `store.py`: `WikiStore.on_change` async callback, fired after every committed mutation
  (`write` / `patch` / `cite` / `ask` / `resolve`), exception-swallowing, called *outside* the
  session context (safe: `expire_on_commit=False`).
- `__init__.py`: wires `on_change` → `ctx.events.emit("wiki.updated", {action, slug})`.
- `routes.py` additions:
  - `GET /search?q=` (store's lexical search),
  - `GET /graph` — React Flow shape `{nodes, edges}`; wikilink targets without pages become
    `kind=stub` nodes, citation URLs `kind=source`,
  - `GET /pages/{slug:path}/revisions` (declared BEFORE the greedy `/pages/{slug:path}`),
  - `/ui/` + `/ui/{path:path}` now serve the built React app from `plugin_wiki/ui` with
    no-cache headers and `?v=<version>` cache-busting; the phase-1 vanilla pane remains as a
    fallback when no build exists (dev safety net).

### Frontend (`wiki-src/`, React + Vite, pattern copied from plugin-playbooks/ui-src)
- Stack: React 19, @xyflow/react 12, react-markdown + remark-gfm, tailwind v4, vite 7.
  Build → `plugin_wiki/ui` (`base: './'` so assets resolve under `/api/p/plugin-wiki/ui/`).
- `lib/auth.ts` — playbooks iframe auth bridge verbatim (postMessage `luna-auth`, localStorage
  fallback). `lib/api.ts` derives the API base from `location.pathname` so any reverse-proxy
  prefix survives; 401 → invalidate + one retry.
- `lib/events.ts` — native `EventSource` on `/api/events?topics=wiki.*` (endpoint is public;
  named event `wiki.updated` arrives un-namespaced). No fetch-event-source needed.
- `GraphView.tsx` — custom React Flow node (page/stub/source styling, testids
  `wiki-node-<slug>`), deterministic two-ring radial layout (pages inner, stubs/sources outer;
  fine at wiki scale — tens of pages), wikilink edges animated purple, node click → page view,
  source click → open URL; just-updated node gets a `node-updated` glow.
- `PageView.tsx` — rendered markdown with `[[slug]]` preprocessed to in-app links (`#wiki:`
  pseudo-protocol intercepted in the `<a>` renderer), open questions, citations, revision
  history.
- `App.tsx` — graph/page view switch, debounced `/search` dropdown, SSE subscription that
  refetches the graph + open page and glows the touched slug.

### Dojo walkthrough (`luna/dojo/tests/curiosity-phase1.5/walkthrough.mjs`)
6/6 headed checks green:
1. Wiki sidebar loads the React app in the plugin iframe,
2. graph renders page nodes + edges (baseline pages honored),
3. node click opens deep page view (markdown body + History),
4. search dropdown returns results,
5. a real chat turn (`wiki_write` in a second tab) succeeds,
6. **the already-open graph shows the new node without any refresh** (SSE live update — the
   "watch her understanding take shape" acceptance criterion).

### Tests
- plugin-wiki pytest: **17/17** (unchanged surface; version-sync rerun).
- phase-1 dojo walkthrough regression: **5/5** — its pane check now exercises the React UI
  (node label text matches).
- Luna core suite NOT rerun this phase: zero core-code changes (only a new walkthrough file
  under `dojo/tests/`); phase-1's verdict (1360 pass / 56 pre-existing failures) stands.
- plugin-curiosity: no tests exist yet (phase-0 scaffold; phase 2 adds them). Found and fixed
  an unterminated string in its `pyproject.toml` `description` that made pytest ERROR on
  collection.

## What was encountered / learned

1. **`luna-plugin.toml` is flat, not `[plugin]`-tabled.** The versioned-index rewrite read
   `toml["plugin"]["version"]` and silently fell back to `?v=0`. Symptom was subtle (stale-cache
   risk, not breakage). Lesson: exercise the fallback path — the `except Exception` hid it;
   caught only by eyeballing the served HTML.
2. **The SSE bridge is public and event names pass un-namespaced** (`ScopedEventBus.emit`
   delegates verbatim; `/api/events?topics=` globs the raw name). So the iframe needs no token
   for live updates — native `EventSource` suffices, no fetchEventSource/auth-header dance.
3. **Graph nodes carry `id`, not `slug`** — first walkthrough run failed its click check by
   reading `.slug` off a `/graph` node. API shape discipline: the graph route deliberately
   speaks React Flow, not store, vocabulary.
4. **Playwright `addInitScript` applies to every frame**, so the `localStorage('luna.token')`
   fallback authenticates the iframe app in dojo runs even before the Shell's postMessage.
5. Manifest version now lives in three places (`luna-plugin.toml`, `PluginManifest`,
   `wiki-src/package.json`) — sync manually on bump; the first two are the ones that matter.
6. Vite bundle is 564 kB minified (React Flow dominates). Acceptable for a lazy-loaded
   sidebar iframe; code-splitting is a later nicety.

## Consider for the future

- **Phases 3–5 (reflection, research, dream) get live visibility for free**: any mutation via
  WikiStore emits `wiki.updated` → the open graph animates. Dream/research turns should write
  through the store (they do — via the same tools), never raw SQL, or the pane goes stale.
- The two-ring layout will get crowded past ~50 pages; if phase-6 onboarding seeds a large
  wiki, consider elkjs or d3-force then. Not before — deterministic layout keeps dojo checks
  stable.
- `wiki.updated` currently carries `{action, slug}` only. If a future phase needs diffs in the
  UI (e.g. dream-report highlights), extend the payload there rather than refetching.
- The `luna:wiki-patch` custom-event name in the original plan was superseded by the core
  EventBus + SSE bridge — cleaner (no plugin-to-plugin JS coupling) and already load-tested by
  approvals. Plans for later phases should reference `wiki.updated` SSE, not DOM events.

## Verification evidence

- dojo: `dojo/results/curiosity-phase1.5/walkthrough/` (5 screenshots + checks.json, 6/6).
- Live-update proof: `05-live-update.png` shows node `phase15-live-<run>` present in a pane
  that was never reloaded after the chat turn in a separate tab.
- Served HTML shows `assets/index-*.js?v=0.3.0` (cache-buster fixed and live).
