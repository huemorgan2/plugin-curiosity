# 10.001 — The job model: data, contracts, discovery loop, overview v2

**Ships:** plugin-curiosity **0.9.0**. Model + API only — the pane is untouched
(10.002 rebuilds it); everything here is additive and backward-compatible so
0.9.0 is safe to ship alone.

**Parent:** [../PLAN.md](../PLAN.md) §2 (2A–2E) + §5. Read the parent first;
this file adds execution detail only.

---

## 1. Data (additive migration, `models.py`)

- `curiosity_abilities`: id, mission_id, title, why, sort_order,
  status (`building|ready|degraded`), created_at, updated_at.
- `curiosity_ability_tasks`: id, ability_id, title, status
  (`done|in_progress|missing|blocked`), note, evidence_ref, sort_order,
  updated_at.
- `curiosity_scopes.ability_id` — nullable FK (migration leaves NULL).
- `curiosity_goals` + `expected_result`, `readiness` (`green|amber|red`),
  `readiness_note` (all nullable).
- `curiosity_plan_changes.kind` — `refine | role_pivot` (existing rows →
  `refine`).
- `curiosity_missions` + `role_version` (default 1), `wiki_id` (nullable —
  bound when multi-wiki ships).
- Migration idempotent (existing `_ensure_columns` pattern); no destructive
  change anywhere.

## 2. Tools (auto-approve, mirroring scope tools in `scopes.py` style)

- `ability_upsert(title, why, tasks=[...])` — create/update one ability with
  its task list; slugged natural key on (mission_id, title) so re-derivation
  converges instead of duplicating (concurrent-turn rule: design for
  convergence, a reaper/upsert beats list-before-create).
- `ability_task_set(ability, task, status, note?, evidence_ref?)`.
- `ability_list()` — returns abilities with **server-computed** percents
  (done=1, in_progress=0.5) + overall setup % (unweighted mean). Agents never
  do arithmetic; agents have no clock — all ages server-side.
- `goal_update` gains the three new fields; `role pivot` path:
  `plan_change(kind='role_pivot', …)` bumps `role_version` in the same
  transaction.

## 3. Contracts (`prompts.py`, single-sourced consts — copies drift)

New consts, each interpolated into kickoff / heartbeat / dream / review /
system-prompt surfaces exactly once:

- `JOB_DESCRIPTION_SHAPE` — [[job-description]] must contain the four headed
  blocks: `## How I will accomplish this mission` (3–6 one-line bullets),
  `## After onboarding` (opens with the agent-picked horizon, then numbered
  observable behaviors), `## In 30 days` (numbered expectations),
  `## Working assumptions` (one line each: assumption + how it gets checked).
- `ABILITY_CONTRACT` — decompose the role into 3–7 "Ability to …" items, each
  with 2–6 concrete subtasks; every scope belongs to an ability; new gaps
  land as subtasks (or a new ability + plan change); heartbeat re-scores
  every fire via `ability_task_set`.
- `VALUE_QUESTION_CADENCE` — every proactive share ends with at most ONE
  question, the highest-leverage uncertainty; verify yourself before asking
  (site/data/wiki first — the owner may not know); questionnaires banned.
- `MATERIALITY_RULE` — within-ability learning → revise + `refine` plan
  change, no owner action; role-shape learning → role pivot: post "what I
  discovered → what changes → what I need from you", `role_pivot` change,
  loop for owner input, re-ratify the changed artifact only. Includes the
  two canonical illustrations (FF 5–10 hands-on → ~100 self-signups/day;
  website → e-commerce) phrased mission-agnostically.
- `NO_BLAME` — pivots are the learning process of both agent and human;
  never apologize, show the discovery and the improved plan.
- `FDE_DOCTRINE` extension to `PHASE_ONE_DOCTRINE` — learn the JOB itself
  (how the role is done well in the world), suggest how things should work
  (the owner ratifies a *design*), set yourself up.

Surface updates: kickoff re-ordered (restate → research the ROLE → JD v1 →
abilities v1 → scopes under abilities → dated goals w/ readiness → post for
ratification → author heartbeat — all in the kickoff turn, draft-labeled);
`HEARTBEAT_CONTRACT` + re-score clause (abilities AND assumptions);
ratification covers JD; weekly review audits JD/readiness shape drift.
Upgrade nudge: on first 0.9.0 load with an active mission and zero
abilities → one-shot muted nudge to derive abilities from the existing
scope ledger next heartbeat.

## 4. Overview v2 (`overview.py`, `routes.py`)

- `job_description`: parsed 4-block structure (headers + bullets only,
  `shape_ok:false` + raw on malformed) + `role_version` + latest role-shape
  change one-liner.
- `abilities[]` with percents + tasks; `setup_percent` = ability mean
  (falls back to the 9.002 stage-weighted % while abilities are empty —
  upgrade window).
- Goals carry the three new fields; pivots appear in `needs_from_you`.
- All 9.002 fields preserved verbatim (the old pane keeps working; 10.002's
  NOC needs them).

## 5. Verify

- **Unit** (extend existing suites): % math incl. 0.5 and empty sets;
  upsert convergence (double-derive → no dupes); role_version bump txn;
  JD parser (good / missing block / malformed); contract-presence
  (prompt-primacy pattern: every surface carries its consts); migration
  idempotence; stage-% fallback.
- **Local dojo** (fresh Luna + local scheduler, NON-funnel mission, dumb-user
  style): kickoff turn → JD page exists with 4 blocks; ability_list ≥3 with
  percents; goals dated, next 2–3 carry readiness; overview v2 contract;
  heartbeat fire re-scores ≥1 task; **discovery leg** — plant a fact
  breaking a working assumption → pivot posted, role_version=2, ONE question
  only, no apology framing; upgrade leg — 0.8.1 data → 0.9.0 load → nudge →
  abilities appear. Approve pending approval cards via API (gates park
  turns).
- Bump **all three version stamps** (in-code manifest authoritative), push
  (`gh auth switch` to huemorgan2 first), publish 0.9.0 to
  marketplaces.com.ai, write `execution_summary.md`.
