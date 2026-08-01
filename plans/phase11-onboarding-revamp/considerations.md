# Key Considerations — Mechanics in plugin-curiosity

Not the strategy — that lives in [ideas.md](./ideas.md). This file maps the
revamp onto today's mechanisms (0.12.0): which tools, gates, prompts, and surface
pieces change. Planning only; nothing here is committed.
The engine (wiki, dream, heartbeat, loops, value log, server-computed truth) stays.
What changes is the opening, the units, and the surface.

---

## 11.001 — Intake & confirm (Law 1)

**Today:** `MISSION_GATE_FLOW` bans both the confirmation round and any question
before save; kickoff fires ~3 s after `mission_set`; the reflect-back ("Brief")
arrives later, buried in the 11-section artifact.

**Decision (Roy, 2026-07-30): a quick conversation happens BEFORE `mission_set`.**
The old save-first ban existed because agents interrogated instead of saving.
The fix is a *hard-bounded* intake with a safety net, not no intake:

1. **Capture instantly, don't set.** The moment the owner states a mission, the
   agent calls `mission_draft` — a new lightweight tool that stores the verbatim
   words + timestamp. Nothing else fires (no wiki, no schedules, no kickoff).
   The mission can never be lost mid-conversation.
2. **One round of discovery — hard cap.** Same reply: at most **2–3 questions**,
   each (a) non-inferable, (b) plan-changing, (c) a small possibility lesson
   ("do you know which event predicts payment?"). One round only — the next
   agent turn ALWAYS saves. Any impatience signal ("just go", a repeat of the
   mission) → save immediately, verbatim. Draft unanswered for 24 h → next
   contact saves verbatim and proceeds. Relentless stays relentless.
3. **Reflect back, then set.** The closing turn states the job back sharper —
   "here's the problem as I understand it" — and calls `mission_set` with the
   sharpened statement plus `origin_statement` (the verbatim words) in the same
   turn. If the owner's answers already confirmed the reflect-back,
   `confirmed_at` is set at once; otherwise the pane shows "waiting for your
   yes" until a `mission_confirm` call. Confirmation is step 2's exit condition
   in the adoption arc. The name question moves to after the owner confirms.
4. **Kickoff splits in two.**
   - *Instant brief* (still ~3 s after save): shallow — the confirmed
     restatement, what I'd look at first, **"3 things I could do for you"**
     grounded in the intake answers. A few tool calls, cents, ~2 min. This is
     the Prove-step opener and the possibility education in one.
   - *Deep pass* (today's ~20-call S0–S2 kickoff): gated on the owner’s confirmation **or**
     an explicit "go" — announced first via a next-step card (11.002). No more
     20 unpreviewed tool calls.
5. `INSTALL_KICKOFF_CONTENT` ("Curiosity awakened") rewritten from "give me a
   mission" to possibility-teaching: three concrete before/after examples of what
   a mission unlocks.

## 11.002 — Next-step cards (Law 2)

**Today:** overview has a `next_up` field, but self-directed runs (daily 09:00
research, nightly dream, 2–4 h heartbeats, kickoff deep pass) spend without a
preview. The slot-machine feeling lives here.

**New object: `NextStep`** — `what` (one line), `why` (one line, tied to the
confirmed mission), `produces` (the artifact), `cost_text` ("~10 min · read-only
on your analytics"), `status` (`proposed | announced | running | done |
redirected`), `wait_until` (veto window), `value_ref` on completion.

- Tools: `next_step_post`, `next_step_start`, `next_step_done` (links the value-log
  receipt — the card is also the spend receipt).
- **Veto policy rides the existing `rung`:** rung 1–2 → *proposed*: wait for "go"
  with a timeout-to-proceed ("no answer? I start in 2 h and leave a note");
  rung 3+ → *announced*: card posts as the run starts, no friction. The rule that
  never expires: no spend the human couldn't have seen coming.
- Scheduled runs open by posting their card (the daily research prompt's step 0);
  the dream is exempt from veto (it's consolidation, near-zero cost) but still
  posts what it did.
- Pane: the **Now & next** section renders running + proposed cards; chat "go
  ahead" / "change it" resolves them. Loop-guard: a redirected card must change
  the plan visibly (`plan_change_note`), never retry silently.

## 11.003 — Expectations in honest units (Law 3)

**Today:** `Goal.target_date` is free-text; **kickoff mandates 5–8 dated goals on
day one** — maximal anchoring at the moment of least knowledge. The JD template
mandates "in about a week" / "in 30 days" prose horizons. Meanwhile loops already
carry `unlock` + `human_cost` — the honest machinery half-exists.

1. **Typed horizons on goals:** `horizon_kind ∈ {agent_minutes, awaiting_approval,
   on_unlock, date, rhythm}` + `horizon_ref` (the loop id for `on_unlock`, the
   trigger for `rhythm`). `date` is legal **only** where a date is real (external
   deadline, weekly review). Goalseek delegation maps `date`/`rhythm` through as
   today; unlock-goals surface as blocked-on-loop, not overdue.
2. **Kickoff mandate rewritten:** 3–5 milestones, each with an honest horizon —
   not 5–8 dated goals. Early passes small and redirectable (the original vision
   already says this; the goal mandate contradicted it).
3. **Prompt laws** (in `prompts.py`, owner-words enforced):
   - Never state a duration a human work-rhythm generated; agent-minutes are
     stated as true minutes, with the evidence of depth attached (sources, steps).
   - A wait caused by a missing grant is *always* phrased by its unlock, never as
     days: "ready once I have Ads access", plus whose move it is.
   - Under-promise: give the honest range, land inside it.
4. **Pace/nudges get blame attribution:** `compute_pace` reasons already say
   "waiting 5 days for you to approve" — extend to name the unlock and the
   5-minute human cost, and keep the agent's own lanes date-free.

## 11.004 — The surface: journey, not dashboard

**Today:** Missions pane = hero + needs strip + JD + setup ring + abilities +
goals timeline; ops tab adds heartbeats, gap board, activity, shelf. Verdict:
"lots of params, lots of text, very little clarity."

Rebuild the Missions tab as six sections (see [mock.html](./mock.html)), all
served by `/missions/overview` with modest additions:

| Mock section | Data source |
|---|---|
| 1 · Your mission — in my words | `mission.statement` (owner's words) + reflected restatement + `confirmed_at` chip + collapsed intake Q&A |
| 2 · Where we are (Hear→Reflect→Prove→Agree→Earn→Own) | derived server-side: mission saved / confirmed / first `value_log` entry / S3 approval / setup vs work phase. S-codes never shown; step names join `OWNER_WORDS` |
| 3 · Now & next | `NextStep` store (11.002) |
| 4 · Waiting on you | `needs_from_you` — already carries `unlock` + `human_cost`; render them as the headline, add "everything else keeps moving" |
| 5 · What happens when | goals with typed horizons (11.003), grouped by horizon kind — agent-minutes lane, your-unlock lane, real dates lane |
| 6 · What you got so far | `value_log` + the "your minutes spent vs mine" tally |

Everything else — abilities ladder, gap board, heartbeat history, JD blocks,
revision stamps — moves entirely to the Operational tab (unchanged) or behind
expands. The JD stays one click away ("read my full job description"), not a
front-page panel. Strict [ux_guidelines](../../../../vision/ux_guidelines.md)
grammar throughout.

## 11.005 — Visible autonomy dial + failure protocol

- `rung` and `risk_ceiling` exist on the mission row but the human never sees
  them. Render as plain words in section 2: "I propose, you approve" → "I act on
  approved playbooks" → "I act and report", with "revoke anytime."
- **Failure protocol (Dietvorst/Parasuraman):** on a visible error, the agent
  drops the affected area one rung, says so, and shows the correction —
  `feedback_note` + `feedback_act` already model this; wire the rung drop and the
  owner-facing sentence. Never defend the output.

## 11.006 — The automation loop (build → sign-off → hypercare → run)

Implements [ideas.md](./ideas.md) §4. Every automation Luna operates becomes a
first-class object with a lifecycle state the owner can see:

- **Registry entry:** `Automation` — `what` (plain words), `state ∈ {building,
  awaiting_your_signoff, hypercare, running, paused, retired}`, `scope`
  (channels/systems it may touch), `target` (its SLO in owner units: "drafts
  within 10 min, error-free"), `value_ref`s. Rendered as the catalog — "what I
  run for you" — a new block in the Missions surface (extends 11.004 §6).
- **Sample sign-off** (the UAT gate): `automation_signoff_request` posts N real
  inputs + the outputs Luna *would have* produced; the owner approves in chat.
  `signoff_at` is the autonomy license — no autonomous execution before it.
  Impatient owners can say "just run it": recorded as an explicit waiver, same
  field.
- **Hypercare state:** entered at go-live. Elevated scrutiny: second-pass
  self-check on every output, daily one-line digest, tight thresholds. Exit on
  criteria, never calendar: `clean_runs ≥ N` + one full weekly cycle + zero
  owner corrections in the window → auto-promote to `running`, announced with
  the numbers. A correction resets the counter, silently staying in hypercare.
- **Go-live gate:** an automation may not leave `building` unless it has a
  kill switch (pause tool), a measurable target, and detection for its own
  failures (operate-readiness — checked in code, not prose).
- **Adoption alarm:** overrides/ignored-output telemetry per automation; an
  automation the owner keeps overriding pages Luna the way an error would —
  fix or propose retiring it. Shelfware never accumulates silently.

## 11.007 — Boundaries, recovery, and the improvement rhythm

Implements [ideas.md](./ideas.md) §5–6. The mechanics Roy's midnight-call
example needs:

**Boundary policies — new first-class object in plugin-goalseek** (enforced at
the tool-execution layer, not by prompt discipline — a rule an LLM must obey
must not depend on the LLM remembering it):

- `Policy` — `title` + `plain_text` (the sentence the owner reads), `rule`
  (machine-checkable): `action_class` (outbound_contact / spend / delete …),
  `channels`, `window` (start, end, `tz_source: recipient | owner`), `limits`
  (per-day counts, spend caps), `default: deny`, `fail_mode: closed` (timezone
  unknown → action refused), `scope`, `origin` (incident_ref or "set at
  agree"), `status ∈ {proposed, confirmed, active, suspended}`, `test_ref`,
  `confirmed_at`.
- Tools: `policy_propose` (Luna), `policy_confirm` / `policy_suspend` (owner
  action only), `policy_list`. Deny events are **surfaced, never silent** — a
  denied action posts what was blocked and by which boundary.
- The worked example as data: title "Quiet hours"; plain_text "I never contact
  your customers outside 9:00–19:00 their local time, on any channel. If I
  can't tell their timezone, I don't contact them. Phone calls always need
  your approval first."; rule: outbound_contact, all channels, window
  09:00–19:00 tz_source=recipient, phone → approval_required always,
  fail_mode=closed; origin: incident 2026-07-29-midnight-call; test: a dry-run
  that attempts the midnight call and must be denied.
- Surface: a "Your boundaries" block (Missions pane, plain sentences +
  "since {date}, {n} actions checked, 0 exceptions"). Default boundary set is
  proposed at the Agree stage — quiet hours, spend cap, phone approval — so
  most boundaries exist *before* any incident.

**Incident protocol** (competence-failure playbook, in prompts + tools):
kill-switch first · owner told before they find out (time-to-self-report is a
tracked metric) · owner-approved recovery of the end customer · one-page
blameless postmortem to the wiki (impact, cause, detection gap,
prevent/detect/limit fixes) · fixes land as policy diffs + tests, not
promises · freeze: rung drops for the affected class, `standard set only` for
N days with exit criteria, announced · earn-back: weekly evidence line, then
`policy_propose`/rung-restore as a small-slice proposal, never assumed.
Postmortem quality law: an action item that is advice ("be more careful") is
invalid — every recurrence-class item must reference a policy or a detection.

**Improvement rhythm** (the proactive side, extends the weekly review):
- Weekly note (5 lines): ran / cost vs value in owner units / "no issues"
  when true / **one** micro-proposal max — `predicted` benefit+cost stated
  before, `actual` reported after (the prediction log is how the owner sees
  learning).
- Monthly: promised-vs-delivered against Agree-stage numbers, savings to
  date, top 1–3 ranked opportunities each anchored to a stored owner quote
  (`value_ref`), **one decision ask**, downsells included.
- Hard rule in prompts: recovery messages and proposals never share a turn.

## Metrics (the adoption funnel becomes the KPI)

Server-computable, no self-reporting: time-to-confirmed-mission ·
time-to-first-win (first `value_log` entry) · % of next-step cards vetoed or
redirected (predictability health — high veto rate = bad proposals, zero = rubber
stamp) · step 3→5 climb rate · expectation hit rate (done inside stated range).
Operate metrics (11.006/11.007): boundary exceptions (target 0) ·
time-to-self-report on incidents · hypercare exit rate and time · override/
ignore rate per automation (shelfware alarm) · weekly-proposal acceptance rate ·
prediction accuracy (predicted vs actual on improvements).

## Open questions for Roy

1. Should the deep kickoff wait for the owner's confirmation strictly, or proceed after a
   timeout (e.g. 12 h) with a note? (Draft answer: timeout-proceed — relentless,
   but announced.)
2. Next-step veto window default at rung 1 — 2 hours? Longer during quiet hours?
3. Do Hear/Reflect/Prove/Agree/Earn/Own become the *stored* stage model (replacing
   S0–S5), or a display mapping over it? (Draft: display mapping first — no
   migration, jargon stays internal; revisit after the surface ships.)
4. Does the intake conversation get a skill (progressive disclosure) or live in
   the base mission-gate prompt? Token cost of 11.001 in every missionless turn.

## Suggested sequencing

11.004 mock → agree on surface → 11.001 (intake/confirm) → 11.002 (cards) →
11.003 (horizons) → 11.004 build → 11.005 → 11.006 (automation loop) →
11.007 (boundaries/recovery — the goalseek policy object can ship earlier if a
real incident demands it). Each independently shippable; 11.001+11.004 alone
already transform the felt experience.
