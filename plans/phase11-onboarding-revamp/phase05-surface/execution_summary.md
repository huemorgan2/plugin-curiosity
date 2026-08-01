# Phase 05 — surface rebuild + M0a buttons — execution summary

**Shipped:** plugin-curiosity 0.16.0 · luna core 063 (muted-moment tools
allowlist) · 451 plugin tests green (+25) · real-Luna dojo 8/8 · screenshot
`dojo_missions_pane.png`.

## What landed

- **journey.py** — pure builder for the owner-facing journey payload: hero
  (statement, you-said, confirmed, intake fold), 6-step rail (Hear → Own,
  derived judgments, not stage echoes), now & next (running/queued cards,
  honest-unit costs, veto-window hint), waiting-on-you (Approve item),
  happens-when (unlocks-first, dimmed owner-choice row), wins (honest
  minutes both ways), dial words (rung → plain words + revoke sentence),
  rung-drop sentence with no digits. `sections` drives progressive
  disclosure — day one is exactly mission + journey + now & next.
- **Missions pane rebuilt** (`ui/`): 8 sections in mock order, late panels
  ship hidden; zero stage jargon (regex-pinned S0–S5 / rung / enum leak
  tests across every serialized stage). Machinery (JD living draft, ability
  ladder, agent status line) moved to the Operational tab (`ui/noc/`).
- **M0a buttons** — Confirm / Change it / Go ahead / Approve post muted
  moment messages (`kind=muted, channel=moment`) into the newest
  conversation, with per-button `tools` allowlists (see mapping table in
  ../PLAN.md).

## What the dojo taught us (the bugs tests couldn't catch)

1. **Muted moment turns are tool-free over HTTP.** The agent replied
   "Thanks for confirming!" and could not record anything — it hunted via
   `load_skill(mission-changes)` (which lacks mission_confirm) and gave up.
   The SDK path has had a `tools` allowlist since 027; the HTTP route never
   passed it. Fixed in luna plan 063 (SendMessageRequest.tools +
   pass-through; 7 core tests). Explicit allowlists reach skill-gated tools
   (046/phase03 contract), so `phase_advance` works for Approve.
2. **POST /messages holds its response until the turn ends** — and a
   first-run turn parks on the identity approval card only the owner can
   approve. A synchronous driver deadlocks: it waits on the POST while the
   turn waits on the approval. Drivers must POST from a thread and poll
   `/api/p/plugin-approvals/` (NOT `/api/approvals` — that's SPA HTML),
   approving as they go.
3. **Button copy must name the tool and the authority.** "Start this step
   now" produced talk with no action; `next_step_start` refuses inside the
   veto window without `owner_ok=true`. SAY.go now says the click IS the
   owner's explicit approval and names the tool + flag. SAY.confirm already
   named mission_confirm — that pattern generalizes.
4. **Gemini-flash agents defer mission_set** — turn 1 often only drafts
   (mission_draft) and finishes onboarding chatter. The overview may have
   no journey until a nudge. Real owners nudge naturally; drivers need the
   same tolerance.

## Dojo (QA Luna, port 8767, fresh DB, gemini-flash heads)

8/8: journey present · day-one sections exact · no jargon in the serialized
payload (live) · hero statement · dial words · Confirm → confirmed=true ·
queued card on desk · Go ahead → running=True, queue emptied. Screenshot of
the live pane matches the mock's section grammar (hero pill, rail states,
running card, Approve row, honest-units timeline, wins).

## Feed-forward to later phases

- Phase 06 (chat bridge): M0b "Change it" prefill still falls back to muted
  ask-in-chat; the bridge should carry composer prefill.
- Phase 07 (automations): `services` payload is a bare list until then;
  renderer already tolerates both shapes. Approve-to-go-live will ride the
  same MOMENT_TOOLS pattern.
- Phase 08 (boundaries): `rules` block reserved; renderer ships hidden.
- Any future pane button that must RECORD something needs a tools
  allowlist — muted turns stay tool-free by default, by design.
