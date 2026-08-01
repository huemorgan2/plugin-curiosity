# Phase 14 — Plan, ask, then act: numbered setup plans + the owner's OK gate

**Incident** (2026-08-01, Roy): once the mission sets, the agent "goes on a
tangent and thinks it knows how to set itself up" — it builds its whole
scaffolding on its own judgment, without researching what Luna can actually
do and without asking. Roy's requirements, verbatim distilled:

1. A **planning mode** after the mission lands: research all plugins and all
   Luna capabilities, then SUGGEST a plan — written in the wiki, for the
   owner to review.
2. A **job description**, also in the wiki, also owner-reviewed (it comes
   first, with/before the plan).
3. The plan carries **all the technical details**; the agent then tries to
   accomplish them, and **always** — success or failure — writes an
   execution-summary artifact named `<plan-name>-execution-summary`.
4. Every amendment, improvement, or retry is **another numbered plan**:
   `001-name`, `002-name`, … with matching numbered execution summaries.
   Everything transparent.
5. **The core issue: between each execution the agent asks the owner. In no
   way does it run before the owner says OK.** Silence is never a yes.

## Root cause

`mission_confirm` releases ONE deep-kickoff turn (`research._KICKOFF_CONTENT`)
whose numbered checklist orders the agent to research AND build all its
scaffolding — job description, abilities, scopes across seven kinds, goals,
its own heartbeat trigger, `stage_set('S2')` — in a single un-reviewed turn.
Approval is requested only retroactively (step 12's closing line asks the
owner to approve what was already built). There is no capability-research
step (the agent never enumerates what plugins/tools it actually has — it
guesses), no reviewable plan artifact, no numbered history, and no gate of
any kind between "the agent decided" and "the agent did". Phase11 doctrine:
prose-only mandates lose; gates win in the tool layer — the plan/execute
boundary must be a tool-layer gate.

## Design

### 1. `planning.py` — the numbered plan ledger (new module + table)

Table `curiosity_setup_plans` (additive): id, mission_id, `seq` (1, 2, 3 →
rendered `001`, `002`…), `name` (kebab), `slug`
(`setup-plans/{seq:03d}-{name}`), `status`
(`draft → approved → executing → done|failed`; a draft replaced before
approval becomes `superseded`), `objective`, `decision_note` (the owner's OK
words, verbatim), `outcome_note`, `summary_slug` (`<slug>-execution-summary`),
timestamps (`created/approved/started/closed/updated`).

`PlanStore` + five auto-approve tools, gates in the handlers:

- `setup_plan_open(name, objective)` — allocates the next number. Refuses
  while a plan is approved/executing ("finish the live plan first"); a
  still-draft predecessor is auto-superseded (that IS the amendment path).
  Returns the slug + steering: write the FULL technical plan there, then put
  it on the owner's desk — nothing in it runs until their OK.
- `setup_plan_approve(owner_words)` — records the owner's explicit OK on the
  current draft. Description + handler enforce: only on a plain OK in the
  owner's latest message, never on silence or the agent's own judgment;
  `owner_words` required; **refuses if the plan wiki page does not exist**
  (the owner cannot approve a plan they cannot read). On success it spawns
  the execution pass (once per plan — flag `plan_exec_started:<plan_id>`).
- `setup_plan_start()` — top of the execution turn; refuses unless the
  current plan is `approved`. This is the hard gate: scaffolding tools stay
  refused until a plan is `executing` (see §4).
- `setup_plan_close(outcome, note)` — refuses unless `executing`; **refuses
  until the execution-summary wiki page exists at `summary_slug`** — every
  execution, success or failure, leaves the artifact. Steering on close:
  anything left undone → open the NEXT numbered plan as a draft and ask;
  never execute it before the OK.
- `setup_plan_list()` — the transparent ledger.

Wiki mirror `[[setup-plans]]` (like the loops/goals mirrors): one line per
plan — `001 — name · status · [[slug]] · [[summary]]` — refreshed on every
ledger change. `setup-plans` joins `mission._STUB_SLUGS` and
`overview.WIKI_SHELF`.

### 2. The kickoff split (research.py)

**The deep pass becomes the PLANNING pass** (same spawn plumbing, flag, and
janitor — content and tool allowlist change):

- Keeps: restate sharper, research the ROLE, draft `[[job-description]]` v1,
  `[[success-criteria]]` (steps 1–4 — these are exactly the review
  artifacts Roy wants).
- New step — **capability research**: `get_plugin_status` (every installed
  plugin + its tools), `marketplace_search`, `wa_status` /
  `connector_list_connected`; findings land in the plan ("what I have /
  what I'm missing"), never guessed.
- New step — `setup_plan_open` → `wiki_write` the numbered plan page per
  `PLAN_SHAPE`: `## Objective`, `## What I researched` (role +
  capabilities, cited), `## Technical steps` (numbered; the exact abilities,
  scopes, goals + horizons, heartbeat trigger, installs/access it will
  create), `## What could fail`, `## What I need from you`.
- The reply artifact is now **Mission plan**: brief + findings + pointers to
  `[[job-description]]` and the plan page, closing with: nothing runs until
  your OK; say ok/go and I execute exactly this plan — or tell me what to
  change and I write plan 002.
- **Tool allowlist is the muted-turn gate**: `scope_set`, `scope_update`,
  `stage_set`, `ability_upsert`, `ability_task_set`, `goal_set`,
  `trigger_create`, `value_log_add`, `loop_open` leave `KICKOFF_TOOLS`;
  `get_plugin_status`, `setup_plan_open`, `setup_plan_list` join. The
  planning turn physically cannot scaffold.

**New EXECUTION pass** (`run_plan_execution` / `spawn_plan_execution_once`,
same claim+flag+card+retry plumbing as the deep pass, spawned ONLY by
`setup_plan_approve` — and by the janitor for an approved-but-never-spawned
plan after a process death):

1. `setup_plan_start()` first (refused → the turn stops).
2. `wiki_read` the plan; execute its technical steps EXACTLY — the ladder,
   scopes, goals with honest horizons, the heartbeat (born HERE now),
   `stage_set('S2')` at the end. Small in-flight adjustments are noted;
   anything that changes the plan's shape stops the run.
3. **ALWAYS** `wiki_write` the summary at `<slug>-execution-summary`
   (`EXEC_SUMMARY_SHAPE`: `## What ran`, `## What worked`,
   `## What failed or was skipped`, `## Next`), success or failure.
4. `setup_plan_close(outcome=…)`, then a short owner-facing reply; any
   follow-up work = a new draft plan + an ask, never a silent retry.

### 3. Prompt contracts (prompts.py, mission.py)

- New `PLAN_LEDGER_RULE` — the doctrine, injected into the setup posture
  right after `FDE_DOCTRINE` and into both pass contents: setup runs on
  numbered plans; nothing scaffolds on your own judgment; owner's explicit
  OK before every execution; every execution leaves a numbered summary;
  every amendment is a new number; between executions you ASK.
- New `PLAN_SHAPE` + `EXEC_SUMMARY_SHAPE` (structure contracts, single-
  sourced).
- `HEARTBEAT_CONTRACT`: "born ONLY in your kickoff" → "born ONLY in your
  plan-execution turn (or a recreate nudge)".
- `prompt_fragment` gains a plan-state line (piped from `prompt_sections`
  like the phase13 draft): plan NNN is DRAFT — on the owner's desk, nothing
  executes until their OK / APPROVED — execution starting / EXECUTING /
  no plan yet — your next setup move is `setup_plan_open`.
- The heartbeat-missing nudge (`maybe_nudge_heartbeat`) additionally
  requires `setup_stage` past S0 — before the first execution there is
  legitimately no heartbeat.

### 4. The tool-layer scaffolding gate (interactive turns)

Muted turns are gated by allowlists; chat turns have every tool. So the
creation tools gate themselves: `scope_set`, `stage_set` (scopes.py),
`ability_upsert` (abilities.py), `goal_set` (goals.py) accept an optional
async `plan_gate` (wired only by `_activate`; module tests unaffected).
Gate logic (`planning.execution_gate`): missionless, work-phase, or past-S0
missions → open (grandfather: existing missions keep working); an S0 setup
mission → open ONLY while the current plan is `executing`; otherwise refuse
with the ledger steering. Updates (`scope_update`, `ability_task_set`,
`goal_update`) stay open — refining what an approved execution built is not
a new execution.

## Out of scope (documented)

- Gating the daily-research SETUP branch harder: its create-calls are now
  refused by §4 pre-approval; the prompt text is left as-is this phase.
- A stuck `executing` plan (process death mid-run) auto-recovery — the
  ledger shows it honestly; a janitor for it can be a later phase.
- Owner-side UI for one-click plan approval (chat "ok" is the contract).

## Testable units

1. PlanStore numbering (001, 002 after close, amendment supersedes draft),
   status transitions, refusals (open-while-live, approve-without-page,
   close-without-summary, start-without-approve).
2. `setup_plan_approve` spawns the execution pass exactly once per plan
   (claim + flag, mirroring the deep-kickoff tests).
3. Planning-pass content: no scaffolding tool in `KICKOFF_TOOLS`;
   `get_plugin_status`/`setup_plan_open` present; content orders the plan
   page + review ask, never `scope_set`/`goal_set`/heartbeat creation.
4. Execution-pass content: starts with `setup_plan_start`, always writes the
   summary, closes the plan; `PLAN_EXEC_TOOLS` carries the scaffolding set.
5. `execution_gate`: refuses `scope_set`/`goal_set`/`ability_upsert`/
   `stage_set` for an S0 setup mission with no executing plan; opens during
   `executing`; grandfathers past-S0 and work-phase missions; missionless
   defers to existing gates.
6. Fragment plan-state lines per status; `PLAN_LEDGER_RULE` present in the
   setup posture; heartbeat nudge suppressed pre-execution.

## Regression gate

Full pytest suite green (research/kickoff/prompt suites updated where they
asserted the one-shot S0→S2 content).

## Version

plugin-curiosity **0.23.0** (additive table `curiosity_setup_plans`; no
destructive migration). All three stamps.

## Exit

`execution_summary.md`; commit + tag + push; package + publish 0.23.0 to
marketplaces.com.ai.
