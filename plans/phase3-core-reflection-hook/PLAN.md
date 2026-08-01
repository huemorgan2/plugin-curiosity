# Phase 3 — core reflection hook (the one luna change)

**Goal:** give `luna` core the single small primitive v1 needs — a supported way for a plugin
to post a **repeated, badged reflection** into the conversation, tagged `source="curiosity"`.
Everything else in v1 is plugin-side; this is the net core change.

**Depends on:** Phase 0 (dev Luna). Independent of 1–2; sequence here so phase 4 can use it.
**Spike:** none.

---

## Scope

**In:** extend the existing E11 muted-message path so `source="curiosity"` is a first-class,
**repeatable** message source (today E11 is effectively one-shot on load; `source="playbook"`
is the working badge precedent). Badge rendering in the client.

**Out:** push/email/WhatsApp (still SSE in-conversation only); cadence/noise logic (that's
comms.py in phase 4, plugin-side); autonomy/policy gating (deferred).

---

## The change (kept minimal)

Today: `post_muted_message` → persists `MessageRow(extra={source,...})` + emits
`message.created`; accepts `source` and `respond`; `source="playbook"` already badges.

v1 need: a plugin can call this **repeatedly** (not just once on load) with
`source="curiosity"`, and the client renders a distinct, low-noise "reflection" badge. Confirm
whether the existing path already permits repeat calls; if it does, the core change is only the
**client badge** + documenting the contract. If it's gated to one-shot, lift that gate for the
curiosity source.

> Net for v1: *one small change* — a supported, repeatable, badged reflection message with
> `source="curiosity"`. No change for mission/kickoff/cross-feed (those reuse existing paths).
> Autonomy gating deferred.

---

## Steps

1. Trace `post_muted_message` / E11 in `luna` core; determine if repeat posting is already
   allowed.
2. Add/confirm `source="curiosity"` handling alongside `source="playbook"`.
3. Add the client-side reflection badge (copy the playbook badge rendering).
4. Expose a thin helper on `ctx` (or confirm the existing one) so the plugin calls it without
   touching internals.

## Acceptance criteria

- [ ] A plugin can post two reflections in one session; both persist with
      `extra.source="curiosity"` and emit `message.created`.
- [ ] Each renders with the distinct reflection badge, visually separable from normal replies
      and from playbook messages.
- [ ] No regression to the on-load E11 muted message or to `source="playbook"`.

## Notes / risks

- This is the **only** change inside `luna` core for v1 — keep the diff surgical and reuse the
  playbook precedent rather than inventing a new channel.
- If repeat posting already works, prefer *documenting the contract* over changing code.

> **Phase-1 learnings:** have reflections cite wiki pages as `[[slug]]` in the message body —
> the wiki store's link parser then builds the reflection→wiki graph for free (and phase 1.5's
> graph view can show it). Also note the core seam limit found in phase 1:
> `prompt_sections()` receives no turn/query argument, so any "reflect on what's relevant
> right now" behavior must come from the agent's own tool calls (wiki_search/wiki_toc), not
> from smarter injection. A second core fix already landed this cycle: opt-in pooled DB
> engine (`LUNA_DB_POOL=1`) — dev-env only, but it is technically a second core diff.

> **Phase-1.5 learnings:** any reflection turn that writes the wiki via the store tools
> automatically live-animates the open graph pane — `WikiStore.on_change` emits
> `wiki.updated` on the core EventBus, bridged to SSE at `/api/events?topics=wiki.*`. No
> extra UI work needed in this phase; just never bypass the store with raw SQL.

> **Phase-2 learnings:**
> - Chat turns run *inside* the `POST /messages` SSE response (client disconnect cancels the
>   turn; a `prompt_always`-gated tool call blocks the turn with zero persisted messages).
>   Muted/reflection messages are a different path — but the dojo test for "two reflections
>   in one session" must not rely on chat markers if any gated tool is in play; poll
>   `/api/conversations/{id}/messages` for `extra.source="curiosity"` rows instead.
> - Dojo pattern to reuse from `dojo/tests/curiosity-phase2/walkthrough.mjs`: conversation
>   title = first 60 chars of the opening message, so every send needs a run-unique nonce
>   prefix (`[#xxxx]`) to pin the right conversation; verify the send landed within ~45s or
>   re-send.
> - Luna core work goes on the `curiosity-dev` branch (established phase 2), never `main`.
