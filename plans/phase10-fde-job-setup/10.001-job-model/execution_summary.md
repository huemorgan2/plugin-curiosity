# 10.001 — Job model: execution summary

**Shipped:** plugin-curiosity **0.9.0** (three stamps: `PluginManifest`,
`pyproject.toml`, `luna-plugin.toml`). Unit suite **175 passed**. Local dojo
`luna/dojo/tests/curiosity-phase10/job-model-e2e.mjs`: **28/28** (see
§Dojo).

## What 0.9.0 adds

- **The job, not just a charter.** Kickoff now drafts `[[job-description]]`
  as a LIVING DRAFT with four headed blocks — *How I will accomplish this
  mission*, *After onboarding*, *In 30 days*, *Working assumptions* — and
  closes with an explicit ratification ask covering job description, charter
  and success criteria together.
- **Qualification ability ladder.** New `curiosity_abilities` +
  `curiosity_ability_tasks` tables and an `AbilityStore`; four new tools
  (`ability_upsert`, `ability_task_set`, `ability_list`,
  `plan_change_note`), all auto-approve. Percents are SERVER-computed
  (done=1, in_progress=0.5, missing/blocked=0); agents never do arithmetic.
  Upserts converge on natural keys (mission_id + slug) — concurrent turns
  cannot duplicate the ladder.
- **Goal readiness.** Goals carry `expected_result` +
  green/amber/red `readiness` + `readiness_note`; the render page prints
  them (🟢 green — …, expected result: …).
- **Plan-change kinds.** `plan_change_note(kind='refine'|'role_pivot')`;
  a pivot bumps `mission.role_version` in the same transaction. Materiality
  rule rides the daily/weekly prompts: details refine, discoveries that
  change what the JOB IS become pivot PROPOSALS — the owner decides,
  no blame framing.
- **Overview v2.** `/missions/overview` gains `setup_percent` (ability mean,
  stage fallback during upgrade window), `abilities`, `job_description`
  (parsed shape, `shape_ok`, `role_version`, latest pivot); pivots ≤14 days
  surface in `needs_from_you`; activity prefixes `ROLE PIVOT — `. All 9.002
  keys preserved; wiki shelf grows to 10 slots (job-description added).
- **Upgrade path.** Pre-0.9.0 missions (no abilities) get a ONE-SHOT muted
  nudge ("Your qualification ladder") on load telling the agent to re-derive
  the ladder from the charter + scope ledger — a re-derivation, not new work.
  Fresh missions never see it (kickoff creates abilities in the same turn).
- **Prompt single-sourcing.** FDE_DOCTRINE, JOB_DESCRIPTION_SHAPE,
  ABILITY_CONTRACT, VALUE_QUESTION_CADENCE, MATERIALITY_RULE, NO_BLAME,
  RATIFICATION_FORCING, SETUP_STAGE_DEFS, HEARTBEAT_CONTRACT are consts in
  `prompts.py`, interpolated into kickoff/daily/weekly/fragment surfaces;
  contract-presence tests enforce exactly-once inclusion. Prompt budgets
  re-measured and raised deliberately (kickoff <12000, setup fragment <9000,
  work fragment <2400 — work mode stays lean).
- **Migration hardening.** `_ADDITIVE_COLUMNS` now skips absent tables
  (fresh installs create them with full schema via checkfirst) and resolves
  `{UUID}` per dialect; returns "table.column" strings.

## Dojo (fresh Luna :8001, curiosity 0.9.0 in-tree, local scheduler :8123)

NON-funnel mission, dumb-user style: a Haifa pottery studio owner who
"doesn't know where to start" hands Luna the business. 27 checks in 5 legs:

- **A. Pre-mission contract** — overview v2 keys live pre-mission, 0.9.0
  stamped assets, gate open.
- **B. Kickoff → S2** — mission adopted from one casual message;
  `[[job-description]]` written with all four blocks (`shape_ok:true`);
  ladder of 5 abilities × 4 subtasks each, server percents; setup_percent =
  ability mean; 6 dated goals, 3 with readiness + expected_result; ratify
  CTA; 10-slot shelf; heartbeat trigger self-authored.
- **C. Heartbeat fire** — prompted tick lands a `curiosity_heartbeats` row
  AND re-scores the ladder (`ability_task_set` on the tick); triggers
  converge to exactly one on the account (report-path reaper).
- **D. Discovery/pivot** — owner reveals the business is actually a
  self-service members club (no teaching, no hired teachers):
  `plan_change kind='role_pivot'` posted with evidence, `role_version` 1→2,
  job description re-written on the new role, EXACTLY ONE owner-facing
  question, zero apology/blame framing; pivot surfaces in `needs_from_you`
  and as `ROLE PIVOT — ` activity.
- **E. Upgrade leg** — ladder + flag wiped to simulate 0.8.1 data, Luna
  restarted: one-shot "Your qualification ladder" nudge posts, flag set on
  delivery; owner says go → 5 abilities re-derived from existing knowledge
  (no research redo), overview back on the ability dial, pivot intact.

**Run history**

| run | result | notes |
|---|---|---|
| 1 | 26/27 | sole failure was a HARNESS bug: check 20 counted `?` in the raw SSE stream, which carries wiki/artifact text; the persisted chat messages of the pivot turn contain exactly ONE question. Also: `spsql` trigger counts were cross-account — the "2 triggers" were ours + a stale 9.002 account's; the exactly-one invariant held per account all along. |
| 2 | **28/28** | clean re-run after fixing check 20 (persisted-message question count), scoping trigger checks to the account (`SACC`), adding 17b (report-path convergence), fresh DB + fresh owner. Exactly one trigger authored this time (no kickoff race), one question on the pivot, 4-ability ladder re-derived on upgrade. |

**Live observations worth keeping**

- The kickoff arc produced the ladder, JD, goals-with-readiness and the
  ratification forcing in ONE turn (~6 min wall clock), on a mission far
  from the funnel domain the prompts were bred on.
- The pivot response was the doctrine verbatim: "That's a fundamentally
  different business — not a tweak", full artifact sweep (JD + charter +
  success criteria + goals + scopes re-pointed), one question, no apology.
- The upgrade nudge respected the "re-derivation, not new work" instruction:
  `ability_upsert` ×5 with zero research tool calls.

## Files

Implementation: `plugin_curiosity/abilities.py` (new), `models.py`,
`goals.py`, `scopes.py`, `mission.py`, `research.py`, `review.py`,
`prompts.py`, `overview.py`, `routes.py`, `__init__.py`.
Tests: `tests/test_phase_10001.py` (16 new), updates to
`test_phase_9002.py`, `test_research.py`, `test_scopes.py`,
`test_prompts.py`. Dojo: `luna/dojo/tests/curiosity-phase10/job-model-e2e.mjs`.
