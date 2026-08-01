# Phase 06 — Chat bridge (M0b, luna core)

"Change it" prefills + focuses the composer from the plugin iframe. Small,
frontend-only; runs in parallel with any phase after 05.

## Changes (luna repo — own plan `luna/plans/038-plugin-chat-bridge/`)

- **ui/src/lib/pluginBridge.ts:** inbound half — accept `{type:'luna-chat',
  action:'send'|'prefill'|'focus', text}`, origin+source guarded, re-dispatch
  as CustomEvent.
- **ui/src/views/Shell.tsx:** `PluginIframe.onMsg` forwards; `setSection('chat')`
  on send/focus when not split.
- **ui/src/views/ChatPanel.tsx:** effect listener; `send(textOverride?)`
  (closure-stale fix); `Composer` textarea ref + focus.
- **plugin-curiosity ui:** "Change it" switches from muted fallback to
  `luna-chat prefill` ("Change this step: {what} — "), feature-detected
  (works on old cores via fallback).

## Testable units

| # | Unit | Test |
|---|---|---|
| 1 | Bridge protocol | `pluginBridge.test.ts` extended: valid/foreign-origin/foreign-source/malformed messages |
| 2 | Send path | vitest: send with textOverride bypasses stale input |
| 3 | Prefill+focus | vitest (or component test): input set, textarea focused, section switched |
| 4 | Feature detect | curiosity unit: old core → muted fallback |
| 5 | Live | real Luna: click Change-it → composer focused with prefix, user types, agent gets it |

## Regression gate

Full `luna/ui` vitest suite; existing bridge tests untouched-green; curiosity
suite green.

## Version

luna core minor (own plan); plugin-curiosity 0.16.1.

## Exit

`execution_summary.md` here + `luna/plans/038/execution_summary.md`.
