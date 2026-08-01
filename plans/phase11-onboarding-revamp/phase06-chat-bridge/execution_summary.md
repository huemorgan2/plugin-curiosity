# Phase 06 — chat bridge — execution summary

**Shipped:** luna core 065 (chat bridge, pushed as 5bbaf53) ·
plugin-chat-ui 0.4.0 · plugin-curiosity 0.16.1 · tests: luna ui 109 +
tsc clean, chat-ui 20, curiosity 456 · real-Luna dojo 7/7 · screenshot
`dojo_chat_bridge.png`.

## What landed

- **luna 065 — `pluginBridge.ts` + Shell**: plugin iframes post
  `{type:'luna-chat', action:'send'|'prefill'|'focus'|'ping', text?}` to the
  parent (same-origin only). The shell validates via `parseChatMessage`
  (unknown actions/foreign types rejected, `text` capped at 4000, `send`
  without text rejected), **acks every valid message** with
  `{type:'luna-chat-ack', action}` back to `e.source`, and — except for
  `ping` — switches to the chat section and re-dispatches the message as a
  window CustomEvent `CHAT_BRIDGE_EVENT = 'luna-chat-bridge'`. The ack is
  the feature-detection contract: old cores never ack, so plugins fall back.
- **Both chat panels consume the same CustomEvent** — the plan's original
  file references were stale (no ChatPanel in core; product chat is
  plugin-chat-ui in luna-marketplaces). Making the shell dispatch a window
  event lets core's frozen BasicChat and the rich ChatPanel implement the
  same three verbs (`prefill` fills + focuses, `focus` focuses, `send`
  fires a real turn with the override text while the owner's half-typed
  draft survives).
- **chat-ui 0.4.0** — ChatPanel bridge listener + `focusRef` on the
  Composer; luna submodule bumped to 5bbaf53 so `@luna/lib/pluginBridge`
  resolves. Bridge `send` skips staged attachments and never clears the
  owner's draft.
- **curiosity 0.16.1** — talk-only Change-it buttons (mission + queued
  step) now `prefillChat('Change the mission: ')` / `` `Change this step:
  ${what} — ` `` when the bridge acked the startup ping; muted-moment
  fallback otherwise. Recording buttons (Confirm / Go ahead / Approve) are
  untouched — they keep muted moments + MOMENT_TOOLS allowlists (063).
  Philosophy pinned in tests: "Change it should end with the owner typing,
  not the agent talking."

## What the dojo taught us (the bugs tests couldn't catch)

1. **`document.querySelector('iframe')` is never "the plugin"** — the
   shell keeps a plugin-brain widget iframe mounted (bottom-left wheel), so
   the first iframe in the DOM is not the pane under test. Drivers must
   select by `src.includes('plugin-<id>')`. Two full dojo runs failed on
   this alone.
2. **Deep-linking `/p/plugin-curiosity` does not survive boot** — the
   always-mounted chat pane restores the last conversation and stomps the
   URL to `/chat/<id>` during hydration. The pane route is `/p/missions`,
   and the reliable path is clicking the sidebar nav like a user.
   (Candidate core bug — noted, not fixed here.)
3. **Headless iframes offscreen never execute their scripts** — without
   `Emulation.setDeviceMetricsOverride`, an 800x600 viewport left the pane
   iframe static (app.js never ran, no errors anywhere). Cost an hour of
   phantom debugging against a "broken render" that was just lazy loading.
4. **`/missions/overview` is slow enough to lose a race** — fixed sleeps
   (4–6 s) sometimes sampled the pane mid-"Loading missions…". Drivers
   must poll for the concrete element (`[data-change]`) before clicking.
5. **`load()` swallows render errors once DATA is set** — a real render
   crash would be invisible in the pane (catch only handles first paint).
   Worth a `console.error` in a future patch.

## Dojo (QA Luna, port 8767, DB luna_p05, headless Chrome + CDP)

7/7: sidebar nav click → queued card rendered (fixture `proposed`
next-step row; the step lifecycle itself was dojo-verified in phase05) →
`[data-change]` click inside the curiosity iframe → shell switched to
`/chat` → composer value `"Change this step: Set up the Friday publishing
pipeline — "` → composer focused. The prefill landing IS the ack proof:
without the ack the plugin would have posted a muted moment instead.
Fixture row deleted after the run.

## Feed-forward to later phases

- Dojo driver hygiene (iframe-by-src, viewport override, poll-not-sleep)
  applies to every UI dojo from phase07 on — `dojo_p06.py` is the template.
- plugin-set.toml in luna core still pins chat-ui 0.2.0 (stale since the
  064 ship too) — left deliberately; upgrades flow through the
  marketplace, not the pin.
- The bridge gives phase07+ a free "hand the owner the composer" verb for
  any card where the right outcome is the owner's voice, not agent talk.
