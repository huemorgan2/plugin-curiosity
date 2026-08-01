# Phase 11 — Implementation Plan

**Execution is phased — one folder per testable phase, each with its own
execution plan and (after running) an execution_summary.md. Learnings from
each phase adjust the next ones.**

| Phase | Folder | Ships |
|---|---|---|
| 01 | [phase01-first-contact](./phase01-first-contact/PLAN.md) | Fresh-Luna self-intro (core) + curiosity-led first interaction — **the most important phase** |
| 02 | [phase02-intake-confirm](./phase02-intake-confirm/PLAN.md) | Draft-first intake, confirm gate, kickoff split (M1) |
| 03 | [phase03-next-step-cards](./phase03-next-step-cards/PLAN.md) | NextStep cards + veto windows (M2) |
| 04 | [phase04-honest-horizons](./phase04-honest-horizons/PLAN.md) | Typed horizons, honest units (M3) |
| 05 | [phase05-surface](./phase05-surface/PLAN.md) | Missions surface rebuild + approve buttons (M4+M0a) |
| 06 | [phase06-chat-bridge](./phase06-chat-bridge/PLAN.md) | Composer prefill/focus bridge (M0b, luna core) |
| 07 | [phase07-automations](./phase07-automations/PLAN.md) | Automation lifecycle + catalog (M5) |
| 08 | [phase08-boundaries](./phase08-boundaries/PLAN.md) | goalseek Policy + incident protocol (M6) |
| 09 | [phase09-rhythm-metrics](./phase09-rhythm-metrics/PLAN.md) | Improvement rhythm + KPI funnel (M7) |

The sections below are the original milestone detail the phases execute.

Implements everything in this folder: the Luna Method ([method.md](./method.md)),
its mechanics ([considerations.md](./considerations.md) 11.001–11.007), and the
new surface ([mock.html](./mock.html)).

**Target versions:**

| Repo | From | To | Carries |
|---|---|---|---|
| plugin-curiosity | 0.12.0 | **0.13.0** | 11.001–11.006, surface, metrics |
| plugin-goalseek | 2.3.0 | **2.4.0** | 11.007 Policy object + enforcement |

The engine (wiki, dream, heartbeat, loops, value log, server-computed truth)
stays. Version stamps in all three places (in-code `PluginManifest` is
authoritative, plus pyproject + marketplace).

**Defaults adopted from the open questions** (change here if wrong):
deep kickoff proceeds after 12 h timeout with a note, not strict wait ·
next-step veto window at rung 1–2 = 2 h, paused during owner quiet hours ·
Hear→Reflect→Prove→Agree→Earn→Own is a **display mapping** over S0–S5, no
storage migration · intake flow lives in the base mission-gate prompt for now
(it only loads while missionless; skill-gate later if token cost bites).

---

## M0 — Buttons talk to the chat (first phase)

Investigated 2026-07-31. The pane is a **same-origin, unsandboxed iframe** with
the shell's bearer token (`Shell.tsx` `PluginIframe`) — no native-React plugin
system exists or is needed. Two levels:

**M0a — works today, zero core change (ship with M4):**
"Approve" / "Go ahead" buttons call
`POST /api/conversations/{id}/messages` with `{content, kind:"muted",
title, channel:"moment"}` — this is the documented iframe adapter
(`luna/agent/muted.py`), posts a badged line in the open chat and runs a
**real agent turn**, live via SSE. Button messages are written detailed
enough to be unambiguous, e.g.
`"I approve: start the inquiry-reply-drafts automation (sign-off request
2026-07-31). Go live."` — carries the object id so the agent needs no
guessing. Widget learns the conversation id via `GET /api/conversations`.

**M0b — "Change it" needs a tiny core bridge (luna repo, own plan in
luna/plans):** prefill + focus the composer from the iframe. ~40–60 lines,
3 frontend files, no backend change:
`ui/src/lib/pluginBridge.ts` (inbound `{type:'luna-chat',
action:'send'|'prefill'|'focus', text}` with origin/source guard) →
`Shell.tsx` `PluginIframe.onMsg` forwards + switches to chat →
`ChatPanel.tsx` effect: `setInput(text)` + textarea ref focus; `send()` gets
a `textOverride` arg (it closes over stale `input`). Tests extend
`pluginBridge.test.ts`. Until M0b lands, "Change it" falls back to a muted
message: "I want to change this step — asking the owner what to change."

**Button → message mapping (curiosity side)** — as shipped in 0.16.0
(phase05). Muted moment reaction turns are TOOL-FREE by default, so each
recording button names a `tools` allowlist (luna 063 added the HTTP pass-
through); talk-only buttons stay tool-free:
| Button | Muted moment content (SAY) | tools |
|---|---|---|
| Confirm (mission hero) | clicked "Confirm" on the mission statement (mission id) — record via mission_confirm | mission_confirm, current_state_set |
| Change it (mission hero) | clicked "Change it" — do not confirm; ask in chat what should change | — |
| Go ahead (queued card) | clicked "Go ahead" on step (id) — the click IS explicit approval; next_step_start with owner_ok true | next_step_start, current_state_set |
| Change it (queued card) | clicked "Change it" on step — do not start; ask what's different | — |
| Approve (setup plan) | clicked "Approve" (mission id) — record the approval, say what you'll do first | phase_advance, stage_set, current_state_set |

## M1 — Intake, confirm, kickoff split (11.001)

**models.py** — `MissionDraft` (verbatim text, created_at); `Mission` gains
`origin_statement`, `confirmed_at`.

**mission.py** — new tools:
- `mission_draft` — stores verbatim words instantly; fires nothing.
- `mission_confirm` — sets `confirmed_at`; the Reflect gate.
- `mission_set` extended: accepts `origin_statement`; still triggers kickoff.
Reaper: draft unanswered 24 h → next contact saves verbatim and proceeds
(convergent, list-before-create safe).

**prompts.py** — rewrite `MISSION_GATE_FLOW`: draft-first → one round, max 2–3
questions (non-inferable, plan-changing, each a small possibility lesson) →
next turn ALWAYS saves with reflect-back; any impatience → save now.
Rewrite `INSTALL_KICKOFF_CONTENT` from "give me a mission" to three concrete
before/after possibility examples.

**engine.py / kickoff** — split:
- Instant brief (~3 s): confirmed restatement + first-look + "3 things I could
  do for you", few calls, cents.
- Deep pass (today's ~20-call S0–S2): gated on `confirmed_at` or explicit "go",
  announced first via a NextStep card (M2); 12 h timeout-proceed with a note.
- Kickoff goal mandate: 3–5 milestones with honest horizons (M3), not 5–8
  dated goals.

**Tests:** rewrite `test_mission.py` / `test_mission_kickoff.py` /
`test_kickoff.py` expectations; new: draft-then-set flow, impatience path,
24 h reaper, deep-pass gating + timeout, confirm sets `confirmed_at`.
Dojo: missionless turn must produce draft + ≤3 questions, never a form-wall,
never save-then-interrogate.

## M2 — NextStep cards (11.002)

**models.py** — `NextStep`: `what`, `why`, `produces`, `cost_text`, `status ∈
{proposed, announced, running, done, redirected}`, `wait_until`, `value_ref`,
`plan_change_note`.

**New tools** (loops.py or new `next_steps.py`): `next_step_post`,
`next_step_start`, `next_step_done` (links value-log receipt — card is the
spend receipt).

**Gating (gating.py):** rung 1–2 → `proposed` + veto window (2 h default,
timeout-to-proceed with a note); rung 3+ → `announced`, no friction. Scheduled
runs (daily research, heartbeats, deep kickoff) post their card as step 0;
dream exempt from veto but posts what it did. Redirected card must carry
`plan_change_note` — no silent retry.

**Tests:** card lifecycle, veto/timeout, rung mapping, scheduled-run step 0,
redirect requires plan change. Dojo: "change it" mid-proposal actually changes
the plan visibly.

## M3 — Honest units (11.003)

**models.py** — `Goal` gains `horizon_kind ∈ {agent_minutes, awaiting_approval,
on_unlock, date, rhythm}` + `horizon_ref`; migration: existing free-text
`target_date` → `date` kind (data preserved).

**goals.py** — goalseek delegation maps `date`/`rhythm` through as today;
`on_unlock` goals surface blocked-on-loop, never overdue. `compute_pace` blame
attribution names the unlock + the 5-minute human cost; agent lanes date-free.

**prompts.py** — the three unit laws: no human-rhythm durations; waits phrased
by unlock + whose move; honest range, land inside it. `OWNER_WORDS` extended
(no "S3", no "sprint", no "ETA").

**Tests:** horizon typing, migration, delegation mapping, pace wording; prompt
tests for banned duration phrasing.

## M4 — Surface rebuild (11.004, mock.html is the spec)

**overview.py / routes.py** — `/missions/overview` serves the eight mock
blocks: mission-in-my-words (statement + reflect-back + confirmed chip +
collapsed intake Q&A) · where-we-are (server-derived 6-step mapping: saved /
confirmed / first value_log / S3 approval / setup-vs-work; S-codes never
serialized) · now-and-next (NextStep store) · waiting-on-you (existing
`needs_from_you`, unlock+human_cost as headline, "everything else keeps
moving") · what-I-run-for-you (M5's Automation catalog) · what-happens-when
(goals grouped by horizon kind) · what-you-got (value_log + minutes tally) ·
my-rules strip (goalseek `policy_list` + checked/exceptions counters; hidden
until policies exist).

**Progressive disclosure:** every section renders only when its data exists —
day one = mission + journey + now & next.

Abilities ladder, gap board, heartbeat history, JD blocks → Operational tab
unchanged; JD one click away. Strict ux_guidelines grammar; widget uses the
mock's CSS tokens.

**Tests:** overview payload per lifecycle stage (day-one vs earning vs
operating), no-jargon serialization test. Verify on a real running Luna
(cookie auth, widget token) — not just unit tests.

## M5 — Autonomy dial + automation loop (11.005 + 11.006)

**11.005:** render `rung`/`risk_ceiling` as plain words in where-we-are
("I propose, you approve" → "I act on approved playbooks" → "I act and
report" + "revoke anytime"). Failure protocol: visible error → affected area
drops one rung, said out loud, correction shown — wire through
`feedback_note`/`feedback_act`; never defend the output.

**11.006 models.py** — `Automation`: `what`, `state ∈ {building,
awaiting_your_signoff, hypercare, running, paused, retired}`, `scope`,
`target` (owner-unit SLO), `signoff_at` (approval or explicit waiver),
`clean_runs`, `value_ref`s, override/ignore counters.

**New tools** (`automations.py`): `automation_register`,
`automation_signoff_request` (N real inputs + would-have outputs),
`automation_pause` (the kill switch — required before leaving `building`),
`automation_state`. Go-live gate checked in code: no kill switch, no
measurable target, no failure detection → cannot leave `building`.

**Hypercare:** second-pass self-check + daily one-line digest; exit on
criteria only (`clean_runs ≥ N` + one full weekly cycle + zero corrections);
correction resets counter; auto-promote announced with the numbers.
**Adoption alarm:** overrides/ignores page Luna like an error — fix or
propose retiring; shelfware never silent.

**Tests:** lifecycle state machine, go-live gate refusal, hypercare exit +
counter reset, waiver recording, alarm trigger. Tool-name grep across plugins
before naming (global namespace).

## M6 — goalseek 2.4.0: Policy object (11.007)

In **plugin-goalseek**, enforced at the tool-execution layer, never prompt
discipline:

- `Policy` model exactly per considerations 11.007: `title`, `plain_text`,
  machine rule (`action_class`, `channels`, `window` with
  `tz_source: recipient|owner`, `limits`, `default: deny`,
  `fail_mode: closed`), `scope`, `origin`, `status`, `test_ref`,
  `confirmed_at`.
- Tools: `policy_propose` (Luna) / `policy_confirm` / `policy_suspend`
  (owner-action only) / `policy_list`. Deny events surfaced, never silent.
- Enforcement hook wraps action execution: unknown timezone → refuse
  (fail-closed); novel action class → default deny.
- Seed set proposed at the Agree stage (quiet hours, spend cap,
  phone-needs-approval) — boundaries exist before any incident.
- Regression test per policy (`test_ref`): the quiet-hours dry-run attempting
  a midnight call must be denied.

**Curiosity side (0.13.0):** incident protocol in prompts (kill-switch first ·
self-report before discovery · owner-approved customer recovery · one-page
blameless postmortem to wiki · fixes land as policy diffs + tests · announced
freeze with exit criteria · earn-back as small-slice proposal); postmortem
law: advice-only action items invalid. "My rules" strip reads goalseek
`policy_list` (degrade gracefully if goalseek absent).

**Tests (goalseek):** deny/allow matrix, fail-closed tz, owner-only confirm,
suspend, deny-event surfacing. Dojo: midnight-call scenario end to end.

## M7 — Improvement rhythm + metrics

**review.py** — weekly note = 5 lines: ran / cost-vs-value in owner units /
"No issues" when true / max **one** micro-proposal with `predicted` stated
before and `actual` after. Monthly: promised-vs-delivered vs Agree numbers,
savings, top 1–3 opportunities each anchored to a stored owner quote, one
decision ask, downsells included. Hard prompt rule: recovery and proposals
never share a turn.

**telemetry.py** — the funnel: time-to-confirmed-mission · time-to-first-win ·
card veto/redirect rate · step 3→5 climb · expectation hit rate · boundary
exceptions (target 0) · time-to-self-report · hypercare exit rate/time ·
override rate · proposal acceptance · prediction accuracy. All
server-computed, no self-reporting.

---

## Sequencing & shippability

M0b (luna core bridge, small, own plan) can start immediately in parallel.
M1 → M2 → M3 → M4 (+M0a buttons) → M5 → M6 → M7, each independently
shippable; M1+M4 alone
transform the felt experience. M6 (goalseek) can ship any time earlier if a
real incident demands it. If 0.13.0 grows too big in review, cut at
M1–M4 = 0.13.0, M5–M7 = 0.14.0.

## Verification & ship checklist (every release)

1. Full pytest suite green (curiosity ~30 test files; goalseek suite).
2. Dojo runs on QA Luna (:8766, turns via API, approve pending approval cards
   via API): missionless intake · veto/redirect · midnight-call incident ·
   day-one overview.
3. Verify on a real running Luna — widget renders, cookie auth, no stale
   routes; sync `~/.luna/managed_plugins` or confirm not overridden.
4. Bump all three version stamps; `gh auth switch` to huemorgan2 before push;
   after push, publish to marketplaces.com.ai (creds in workspace .env).
5. Production spot-check via CDP browser (:9222): upgrade route +
   `/api/plugins` JSON.

## Out of scope

S0–S5 storage migration (display mapping only) · Operational tab changes ·
any luna-service change (read-only; if the enforcement hook needs a core
extension point, write a recommendation, don't touch it).
