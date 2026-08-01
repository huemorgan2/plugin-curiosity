# Phase 3 — execution summary

**Status: DONE.** The core diff stayed surgical — two files. All three acceptance criteria
verified: core pytest **15/15** (6 new phase-3 + 9 muted-message regression, in one run),
dojo walkthrough **5/5** headed, plugin-curiosity regression **9/9**.

## What was done

The plan's central question ("is repeat posting already allowed?") resolved to **yes** —
`post_muted_message` (luna/agent/muted.py) has no one-shot gate; each call persists its own
muted line (+ reaction reply on a moment) and emits `message.created`. Both the muted row
and the reply row already stamp `extra.source`. So per the plan's own preference, the code
change shrank to the two real gaps:

1. **`PluginContext.send_muted_message` gains `source: str | None = None`**
   (luna/plugins/context.py). Default unchanged — the plugin name — so every existing
   caller behaves identically; curiosity passes `source="curiosity"`. Docstring documents
   the repeatability contract and that the source string is a contract with the client.
2. **Client reflection badge** (ui/src/views/ChatPanel.tsx, Bubble): `source="curiosity"`
   renders a sky-blue bubble with a 💭 avatar and a `💭 Reflection` footer
   (`data-testid="reflection-badge"`), instead of the generic violet ⚡ "Auto sent from
   {source} run" automation badge. Every other source keeps the E12 generic badge; no
   plugin names special-cased beyond this one channel. UI rebuilt (`npm run build`).

Plugin side (plugin-curiosity 0.2.1): `POST /api/p/plugin-curiosity/reflect`
`{title, body, respond, conversation_id}` → `ctx.send_muted_message(source="curiosity")`.
`respond=true` (default) is a *moment* — the badged reply is Luna voicing the thought;
`respond=false` is *awareness* (line only, no badge, no turn). Phase 4's `share_thought`
adds cadence guardrails on top of this route's mechanism.

### Tests
- `tests/curiosity-phase3-reflection/test_reflection_source.py` (core, on `curiosity-dev`):
  two reflections in one session → 4 rows (2 muted + 2 assistant) all
  `extra.source="curiosity"`, 4 `message.created` events; ctx override forwards
  `"curiosity"` while a plain call still stamps the plugin name.
- 008.994 muted-message suite re-run green — no regression to E11 on-load posting or the
  respond/awareness semantics.
- Dojo `curiosity-phase3/walkthrough.mjs`, headed, 5/5: two reflect POSTs each produce a
  reaction reply; rows persist with the right source; the browser shows **2 reflection
  badges**; muted lines still render as collapsed `▸ REFLECTION` disclosure rows; zero
  generic automation badges on curiosity messages. Screenshots in
  `dojo/results/curiosity-phase3/walkthrough/`.

## What was encountered / learned

1. **The reply bubble is the badge carrier.** The muted line renders as a collapsed grey
   disclosure row (no badge); `extra.source` on the *assistant reply* row is what the badge
   keys off. So a "reflection" wants `channel="moment"` — an awareness-only post is
   invisible until expanded. Phase 4's share_thought should be a moment.
2. **The reaction turn defaults to zero tools** (`tools=[]` in post_muted_message). In the
   walkthrough, Luna's reflection said "let me read the mission page" but couldn't — the
   turn had no tools. Phase 4 must pass an explicit allowlist (wiki_* at minimum) when the
   reflection should be grounded in current wiki state.
3. **Conversation resolution**: explicit id → current-turn contextvar → most recent
   conversation. A headless/scheduled reflection with no explicit id lands in whatever
   conversation was most recently touched — fine for "ambient" but phases 4/5 should pass
   `conversation_id` deliberately when continuity matters.
4. Client live path and fetch path both map `source` (ChatPanel lines ~471/~2053), so the
   badge appears live via SSE `message.created` and after reload — no extra wiring.
5. Playwright: fixed sleeps after clicking a conversation lose to the "Loading
   conversation..." spinner; wait for a content testid instead. (First run failed 2 browser
   checks purely on this.)
6. `ui/dist` is untracked (build artifact) — rebuilding after any ChatPanel change is part
   of the deploy step, not the commit.

## Consider for the future

- **Phase 4 (`share_thought`)**: use the moment channel; pass a tool allowlist (wiki read
  tools) so the voiced thought can actually cite pages; keep `[[slug]]` links in the muted
  body so the wiki graph picks up reflection→page edges (phase-1 learning, still applies).
- **Phase 5 (dream)**: the morning thought is exactly one `/reflect`-style moment posted
  after quiet hours; the dream's consolidation turn itself should stay separate from the
  reflection post (consolidate first via fired turn, then one moment).
- The `source` string is now a **client contract**: only `"curiosity"` has a named badge.
  If a later phase wants sub-kinds (dream vs research reflection), differentiate in the
  title (`Reflection` / `Morning thought`), not with new source values, to keep the core
  generic-badge rule intact.
- The reflect route is owner-authed and generic — phase 6's onboarding can reuse it for the
  kickoff moment if the plugin-internal call path is awkward from onboarding code.
