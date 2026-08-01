# Phase 03 — next-step cards: execution summary

**Shipped:** plugin-curiosity 0.14.0 (2026-07-31/08-01). 394 unit tests green
(29 new in tests/test_next_steps.py), 3 live dojo runs on a fresh QA Luna
(gemini, port 8767).

## What was built

"No spend the owner couldn't have seen coming. Every self-directed run opens
with a card."

- **NextStep model** (`curiosity_next_steps` table, additive): what / why /
  produces / cost_text, status `proposed|announced|running|done|redirected`,
  wait_until, value_ref, plan_change_note, source
  `agent|daily|heartbeat|kickoff|dream|review`.
- **Three tools** — `next_step_post`, `next_step_start`, `next_step_done` —
  ungated + auto_approve by design (scheduled and muted turns must always
  reach them), registered directly via `ctx.tool_registry.register`.
- **Rung teeth**: rung 1-2 → `proposed` with a 2-**waking**-hour veto window
  (quiet hours 21:00–08:00 pause the clock — pure `veto_deadline()` fn);
  rung 3+ → `announced`. `scheduled=true` → announced regardless of rung (a
  routine fire rides an owner-visible schedule; a 2 h wait inside a
  once-a-day fire would kill the loop). `retro=true` → lands done (dream's
  after-the-fact receipt).
- **Flow gates in the tool layer** (not prose): `next_step_start` refuses
  inside an open window with a steering error naming the deadline and the
  `owner_ok` escape (explicit chat approval only); a timed-out start carries
  the no-guilt "window passed, proceeding by default" note.
  `next_step_done(outcome=redirected)` REQUIRES `plan_change_note` — the
  silent-retry loop is the failure mode this phase exists to kill.
- **Scheduled fires card up**: daily research target opens with CARD FIRST
  (before LOOP PATROL), weekly review's common prep opens with its card,
  heartbeat contract gained clause (a0), kickoff closes its card as step 13,
  dream posts retro-only. The deep kickoff's card is posted **plugin-side**
  in `spawn_deep_kickoff_once` (`record_scheduled_step`) — deterministic,
  not dependent on the model remembering.
- **Surfaces**: overview payload carries `next_step` + `next_steps_recent`,
  a `needs_from_you` veto CTA while a proposed window is open ("About to: …
  reply in chat to redirect"), activity entries, and `mission_detail` history.
  `NEXT_STEP_CARD_RULE` rides both phase branches of the prompt fragment.

## Test results

- **Unit**: 394 passed (`uv run … pytest tests/ -q`). New coverage: rung
  mapping, waking-hours deadline math (20:30→next-day 09:30, 02:00→10:00),
  post/start/done lifecycle, veto refusal + owner_ok bypass + timeout note,
  value receipt linking (foreign value_ref rejected), redirect note gate,
  newest-open resolution, kickoff plugin-side card, overview/CTA/detail,
  prompt wiring (CARD FIRST before "0. LOOP PATROL" preserved).
- **Live dojo** (3 runs, fresh DB each): every behavior observed on a real
  Luna — organic card posting (incl. in the confirm turn, unstarted and
  respecting its window), kickoff card self-posts + self-closes,
  owner redirect → `redirected` + plan_change_note + replacement card,
  backdated window + neutral check-in → timeout-to-proceed start + close,
  overview CTA present while proposed, and the waking-hours pause verified
  live (cards posted 23:06 local got 10:00-next-morning deadlines).

## Learnings (feed forward)

1. **Veto-rate copy learning for phase05**: organic card-first compliance
   varies by turn shape. When the owner says "decide your own next move —
   don't wait for me", the model treats it as `owner_ok` license and starts
   immediately (defensible; the rule's own semantics). When the turn is a
   scheduled fire or post-confirm kickoff, compliance was strong. The
   phase05 pane copy should present the card as "what she's about to do"
   with redirect affordance, NOT as an approval gate — live behavior shows
   the window is mostly consumed by silence.
2. **Cards orphan when turns die** (503 spikes killed a kickoff turn
   mid-flight, leaving its card `running` forever). Newest-open resolution
   means a stale card never blocks new ones, but a reaper (close open cards
   older than ~24 h as `done` with a note) belongs in a later phase —
   prompt invariants need code reapers.
3. **Dojo driver**: turns are server-owned (028) — the SSE is only a viewer;
   a driver must poll `GET /api/conversations/{id}/turn` until idle before
   posting the next message (a busy conversation 202-queues posts) and
   before reading ground truth. SSE keepalives defeat httpx read timeouts —
   wall-clock-cap every hop. Gemini 503 spikes need retry-with-backoff, and
   the concurrent deep-kickoff turn competes for the model — wait for its
   card to settle before driving the next chat turn.
4. **The third version stamp** (`plugin_curiosity/luna-plugin.toml`) hides
   inside the package dir — 4 of 9 first-run test failures were the stamp.
   The three-stamp check tests earn their keep every phase.
5. **SQLite returns naive datetimes** from `DateTime(timezone=True)` columns
   under aiosqlite — any stored-deadline comparison must normalize tzinfo
   before comparing (postgres is unaffected). `telemetry.emit_ui_event` is a
   coroutine — must be awaited (loops.py is the reference pattern).

## Plan deltas for later phases

- Phase 05 (surface): veto CTA copy per learning 1; consider an explicit
  "go ahead now" button that maps to `next_step_start(owner_ok=true)` and a
  "redirect" affordance that pre-fills chat.
- Phase 04/07: add the stale-card reaper alongside honest horizons /
  automation loop work.
