# 10.006 — acting on feedback: criticism must change the machine

## Problem

Owner feedback on Luna's behavior produces empathy, not change. Real case:
owner said the daily report is bad and why; Luna acknowledged perfectly and
never touched the playbook that produces the report. The feedback evaporated
— next report identical.

North star dialogue:

> **user:** your report is shit
> **luna:** not happy to hear that — what's not working for you?
> **user:** i don't care what you do, i care about our progress getting
> people to adopt.
> **luna:** ok — *edits the report playbook to lead with adoption progress,
> logs the decision, replies with what changed.* No "should I?".

Three gaps behind it:

1. **No feedback turn contract.** Nothing tells the agent that criticism of
   her output/behavior means: find the artifact that produced it and change
   it in that turn. (Same lesson as 10.005: a fixed turn shape is what holds;
   rhetoric doesn't.)
2. **She can't see her own design.** "Look at all the prompts" has no
   handle — her behavior is spread across identity fields, persona, mission,
   job-description, playbooks, triggers, heartbeat contract. There is no
   inventory to audit.
3. **No memory of WHY things are the way they are.** Setup answers and owner
   instructions are stored as values, never with reasons. So when new
   feedback contradicts an old instruction, she can't say "you also asked me
   to list my exact actions — I'll keep that, but move it to the bottom."

Plus a standing rule: **proactive by default** — when there is a way forward
that isn't blocked on the owner, take it; don't ask.

## What exists (verified in code)

- Playbooks: `playbook_get_definition` → `playbook_edit` (full-YAML rewrite,
  versioned snapshots). No prompt says *when* to edit one. The daily report
  is scheduler-driven, not cron-in-playbook.
- Curiosity self-revision machinery is discovery-driven only:
  `plan_change_note(kind='role_pivot')`, materiality rule, weekly review
  scoring against `[[success-criteria]]`. Nothing triggers on criticism.
- Identity: core `update_self` fields incl. `persona`, `instructions`,
  `proactive`; every change already writes a Version row (before/after,
  reason) — the reason is just never asked for or surfaced.
- Wiki: `[[role-charter]]` has a Plan-changes log; `[[job-description]]` has
  Working assumptions. No page records owner instructions with rationale.

## Design

### A. `[[owner-decisions]]` — the reasons ledger (structural)

One wiki page, one row per owner instruction/decision:
`date | what the owner asked | why (their words) | where it now lives
(playbook X / persona / report format / …)`.

- Seeded at setup: every setup answer (mission, decision_authority, "tell me
  exactly what your actions are", …) lands here with the owner's phrasing.
- Every `update_self`, `mission_set`, `plan_change_note`, and feedback fix
  (C) appends a row. Prompt duty + heartbeat check that edits which touched
  behavior artifacts have a ledger row.
- On contradictory feedback the agent must read this page and reconcile OUT
  LOUD: keep, demote, or replace the old instruction — and say which.

### B. Design inventory — "all the prompts" gets a handle

A `design_map` tool (curiosity) returning the live behavior surface:
identity + personality fields (with current values), mission/job-description/
success-criteria/role-charter slugs, playbooks (name, version, autonomy,
when_to_use), triggers incl. heartbeat, report/renderer settings. Cheap:
reads existing stores. This is what the agent audits when feedback arrives —
no guessing where behavior comes from.

### C. Feedback turn contract (prompt, fixed shape like 10.005)

When the owner criticizes her behavior/output, the turn has a FIXED shape:

1. One clarifying question ONLY if the complaint is genuinely ambiguous —
   at most one, never as a stall.
2. `design_map` → identify every artifact implicated (playbook, persona,
   report format, trigger, job-description section).
3. Read `[[owner-decisions]]`; if the feedback contradicts an earlier
   instruction, reconcile explicitly (keep-but-demote / replace) and say so.
4. CHANGE the artifacts in that same turn: `playbook_edit`,
   `update_self(persona/instructions/...)`, `mission_refine`, wiki edits —
   whatever the audit implicated. Acknowledging without an edit is
   acting-vs-claiming (TRUTH_CORE language, same as 10.005 step 2).
5. Append the feedback + what changed to `[[owner-decisions]]`; reply with
   the diff in owner words ("report now leads with adoption progress;
   your action-list stays, at the bottom").

### D. Structural backstop (prompt invariants need code reapers)

Prompts alone won't hold (three dojo iterations in 10.005 proved it). Add
`feedback_note` (curiosity tool): records owner feedback with required
`changed_refs` (playbook name+version / identity field / wiki slug). The
setup/work heartbeat and weekly review surface any feedback_note with empty
`changed_refs` as a red item: "owner feedback from <date> not yet acted on."
So even when the model dodges in-turn, the loop drags it back.

### E. Proactivity rule

One prompt line in the curiosity fragment + honor core `proactive` field:
"If a step forward exists that doesn't need the owner, take it and report —
asking permission for a reversible step is a failure." Aligns with the
existing one-ask discipline (asks must ride on value_refs).

## Out of scope

- Core/luna changes: none needed (identity Version rows already exist).
- Cron triggers in playbooks (separate phase 014 item).
- Automatic sentiment detection — the contract keys on the owner addressing
  her behavior/output, not on tone classifiers.

## Verification

- Unit: design_map contents; feedback_note requires changed_refs; heartbeat
  flags unactioned feedback; owner-decisions append helpers.
- Dojo (`curiosity-10006/feedback-acts.mjs`), agent past setup with a
  daily-report playbook + seeded `[[owner-decisions]]` (incl. "tell me
  exactly what your actions are"):
  1. "your report is shit" → ≤1 clarifying question, no stall.
  2. "i care about adoption progress" → SAME turn: `playbook_edit` ran
     (version bumped), report leads with adoption progress, old
     exact-actions instruction demoted to bottom NOT deleted, reply states
     the reconciliation, `[[owner-decisions]]` gained a row.
  3. Next fired report reflects the change (regenerate and diff).
  4. Negative: unactioned feedback_note turns the next heartbeat/review red.

## Ship

curiosity 0.9.14 (after 0.9.12/0.9.13 land and rebase), plan-first per
convention; dojo gate before commit, as in 10.005.
