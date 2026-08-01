# Phase 14 — execution summary

**Shipped: plugin-curiosity 0.23.0** (2026-08-01). Incident response: once
the mission set, the agent went on a tangent — it assumed it knew how to
set itself up and started scaffolding (scopes, goals, abilities, triggers)
without asking. Phase14 replaces "confirm → build" with "confirm → PLAN →
owner's OK → build": setup now runs on a numbered, wiki-visible plan
ledger, and in no path does execution start before the owner's explicit OK
lands in chat. Silence is never a yes. All gates live in the tool layer
(phase11 doctrine), not in prose.

## What changed

1. **The numbered plan ledger** (`planning.py`, new; `models.py`
   `SetupPlan` table). Plans are `001-name`, `002-name`, … per mission,
   each with wiki slug `setup-plans/NNN-name` and a paired
   `…-execution-summary` slug. Statuses: draft → approved → executing →
   done|failed; opening over an unapproved draft supersedes it (every
   amendment/retry is a NEW number, never an edit). Five tools:
   `setup_plan_open` (refused while a plan is approved/executing; steers
   to write the full technical plan and ask the owner), `setup_plan_approve`
   (records the owner's words VERBATIM; refused while the plan's wiki page
   is missing — "the owner cannot approve a plan they cannot read"; this is
   what spawns the execution pass), `setup_plan_start` (refused unless
   approved), `setup_plan_close` (refused until the execution-summary page
   exists — EVERY run, success or failure, leaves the artifact), and
   `setup_plan_list`. The whole ledger mirrors to the `setup-plans` wiki
   index on every transition, so the history stays transparent.

2. **The kickoff split** (`research.py`). The old one-shot deep S0→S2 pass
   became two muted turns. The PLANNING pass ("Mission planning") keeps the
   research: SHARPER restatement, role research, [[job-description]] v1,
   [[success-criteria]], then a real capability scan (`get_plugin_status`
   over EVERY installed plugin, marketplace/WhatsApp/connector reach) and
   `setup_plan_open` + the full technical plan on the wiki — ending in a
   Mission-plan artifact (Brief / What I found / My job description / What
   success looks like / The plan / What I need from you) that ASKS for the
   OK and STOPS. Its allowlist (`KICKOFF_TOOLS`) physically contains no
   scaffolding tools — scope_set/goal_set/ability_upsert/stage_set/
   trigger_create/setup_plan_approve are not in the belt. The EXECUTION
   pass ("Setup plan execution", `PLAN_EXEC_TOOLS`) opens with
   `setup_plan_start()` FIRST, executes exactly what the plan page says
   (ladder, scopes, goals, heartbeat born here as a plan step), ALWAYS
   writes the execution summary, closes the plan, and reports honestly —
   anything left becomes the next numbered plan behind a fresh OK.

3. **Owner's-OK spawn plumbing** (`research.py`). The execution pass is
   spawned only by `setup_plan_approve`, via
   `spawn_plan_execution_once(ctx, sf, mission, plan)` — the proven
   claim-set + persisted `plan_exec_started:<plan_id>` Flag + next-step
   card + retry-posting shape, at most once per plan. The janitor
   (`maybe_start_deep_kickoff`, on-load + per-turn) recovers an
   approved-but-unspawned plan after a process death; a confirmed mission
   with no plan still gets the planning pass; past-S0 missions stay
   grandfathered.

4. **The interactive-turn gate** (`planning.execution_gate`, wired by
   `_activate` into `scope_set`, `stage_set`, `ability_upsert`,
   `goal_set`). A chat turn on an S0 setup mission outside an executing
   plan gets a refusal ("setup runs on numbered plans — nothing scaffolds
   before the owner's OK") with the current ledger position in the hint.
   Updates stay open — refining what an approved execution built is not a
   new execution. Missionless turns, work-phase missions, and past-S0
   missions are never gated; a broken store probe fails open so tools
   never brick.

5. **Every chat turn knows the ledger position** (`mission.py`,
   `prompts.py`, `overview.py`). `PLAN_LEDGER_RULE` rides in the setup
   posture right behind the FDE stance; `prompt_fragment(..., plan=...)`
   renders the plan-state line per status (draft = "on the owner's desk,
   NOTHING executes until their explicit OK … Silence is never a yes";
   approved = don't re-open/re-approve/hand-execute; executing = exactly
   the plan + always the summary; confirmed-no-plan = demand the ledger).
   The wiki shelf gains `setup-plans` (11 entries); the heartbeat safety
   net stays silent at S0 — before the first plan execution the heartbeat
   is legitimately unborn, and nudging would order scaffolding outside the
   ledger.

## Verification

Full suite: **565 passed** (`pytest -q`; 548 pre-phase14).
- `tests/test_phase14_plan_ledger.py` (new, 15 tests): store numbering /
  supersede-on-amend / transition refusals (no owner words → no approval;
  draft can't start; live plan blocks the next number; close follows
  start); tools — open mirrors the ledger and steers to the owner, approve
  refuses without a readable plan page, approve spawns the execution pass
  exactly once (claim + flag, owner's words ride in the turn), close
  refuses until the summary page exists; the split — planning belt has
  research + setup_plan_open and NO scaffolding, execution belt has the
  scaffolding + the summary law; execution_gate refusals / opens-inside-
  an-executing-plan / grandfathering / missionless; scope_set + stage_set
  wired through the gate; fragment plan-state lines per status +
  PLAN_LEDGER_RULE in the setup posture only; janitor recovery of an
  approved-but-unspawned plan, idempotent across restarts.
- Updated to the split: `test_prompts.py` (planning-pass and
  execution-pass shape tests replace the one-shot arc test),
  `test_research.py` (new Mission-plan artifact markers),
  `test_review.py` (capability scan on the planning pass, goal commits on
  the execution pass), `test_phase_one.py`, `test_phase_9002.py` (shelf
  11; heartbeat born in the plan-execution turn), `test_phase_10001.py`
  (contracts split across the two passes), `test_horizons.py`,
  `test_intake_confirm.py`, `test_next_steps.py`.

## Follow-up

- 0.22.0 (phase13) and 0.23.0 are both unpublished to the marketplace if
  the publish classifier blocks again — the exact commands are in the
  handover note; publishing 0.23.0 alone suffices (it contains phase13).
- The dojo run for phase14 (live agent against the new ledger) is the next
  natural checkpoint: watch for the agent asking for the OK instead of
  assuming it, and for amendment requests becoming plan 002 rather than
  edits.
