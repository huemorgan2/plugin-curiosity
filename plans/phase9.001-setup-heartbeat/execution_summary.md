# Phase 9.001 execution summary — self-scheduled setup heartbeat

**Shipped:** plugin-curiosity **0.7.1**, commit `60f2ccc`, pushed to
`huemorgan2/plugin-curiosity`, published to marketplaces.com.ai official
(sha256 `f29f4be3…d86e56a`, index-verified).

## What landed vs the plan

All surfaces, single-sourced in `prompts.py`:

- **A. Phase-one doctrine** — `PHASE_ONE_DOCTRINE` ("Am I qualified to do
  this job? … do I know what success looks like") interpolated into kickoff,
  weekly review, and the setup mission fragment; the daily carries a
  condensed line ("you are QUALIFYING yourself…") by char budget. Work phase
  gets `PHASE_TWO_LINE` instead — the doctrine is setup-scoped by design.
- **B. Agent-authored heartbeat** — canonical name
  `curiosity-setup-heartbeat`; the AGENT creates it (kickoff step 9 /
  adoption turn), authoring its own target. `HEARTBEAT_CONTRACT` mandates:
  state re-derivation (mission_get, scope_list, goal_list, loop_list), an
  explicit convergence criterion (converged = 5 consecutive clean fires →
  propose graduation, self-demote cadence), and a one-line verdict appended
  to [[setup-heartbeat]] per fire.
- **C. Safety net that reminds, never creates** — on-load
  `maybe_nudge_heartbeat`: setup phase + heartbeat missing → muted "Setup
  heartbeat missing" nudge, 1/day flag (failed send does not burn the flag);
  `heartbeat_exists` is tristate (scheduler absent → None → no nudge). Daily
  recreates by name; weekly audits.
- **D. Success criteria** — `[[success-criteria]]` replaces the
  mission-metrics stub in `_STUB_SLUGS`; `ensure_success_criteria_page`
  upgrade-seeds it (legacy real content carried, stubs not).
- **E. Stage clock + forcing** — `stage_entered_at` (additive migration),
  server-computed `stage_age_days` (agents have no clock);
  `RATIFICATION_FORCING` at S2 age ≥ 3d; `NEXT_TOUCH_RULE` on setup surfaces.
- **F. Owner legibility** — kickoff artifact carries **What success looks
  like**, **Where I am** (phase line), and an explicit ratification ask; the
  agent can SAY the two-phase model cold.

## Verification

- **Unit suite 106 passed** (13 new in `test_phase_one.py`: doctrine
  placement, ladder single-sourcing, heartbeat contract + tristate, nudge
  truth table, stage clock, success-page seeding/carry-over).
- **Local dojo 18/18** (`setup-heartbeat-e2e.mjs`, fresh Luna, naive owner
  "potter" / ceramics studio, own scheduler-service): mission adopted
  same-turn; S2 + [[success-criteria]] (1685 chars) + legible artifact;
  exactly ONE agent-authored heartbeat with convergence in the target; cold
  probe named the phase and its gaps; heartbeat deleted behind the agent's
  back on the scheduler's own DB + restart → muted nudge posted → the agent
  recreated exactly one trigger.
- **Production e2e 16/16** (`setup-heartbeat-prod.mjs`, NEW agent — owner
  "marina", hand-dyed-yarn Etsy shop, not RayLa): fresh Luna booted WITHOUT
  in-tree curiosity; real 0.7.1 artifact installed at runtime from
  marketplaces.com.ai; install kickoff landed without restart; heartbeat
  created on the PRODUCTION scheduler (luna-scheduler.onrender.com, exactly
  one); run-now fire delivered through the cloudflared tunnel (http=200) and
  the heartbeat turn wrote a real [[setup-heartbeat]] verdict ("10 scopes
  chartered … Streak: 0. First fire — baseline established"). Disposable
  account `curiosity-9001-e2e` deleted after the run.

## Bug found and fixed mid-verification

**Duplicate heartbeat (dojo run 2):** two `curiosity-setup-heartbeat` rows,
4 minutes apart — the adoption chat turn created one (the contract rides the
setup fragment) and the kickoff background turn created another (step 9 said
"Create NOW" unconditionally). Fix: `HEARTBEAT_CONTRACT` now mandates
"EXACTLY ONE may exist: before any trigger_create, call trigger_list…", and
kickoff step 9 became "Ensure … trigger_list first". Run 3 held at exactly
one through adoption, kickoff, deletion-recovery, and a production fire.

## Learnings

1. **Two surfaces carrying the same 'create' instruction will both fire.**
   Any prompt-driven create needs an idempotency clause on the surface
   itself (list-before-create), not just a canonical name.
2. **The convergence criterion survives into agent-authored artifacts** —
   the agent's own trigger target and its [[setup-heartbeat]] page both
   restated "5 consecutive" unprompted; single-sourcing the contract works.
3. **Deleting on the scheduler's own DB is the honest safety-net test** —
   the plugin's trigger cache never sees it, so recovery genuinely proves
   the on-load path (nudge → agent recreates), not cache repair.
4. **Same-day reruns of nudge tests need a fresh DB** — the 1/day flag is
   date-keyed; a partial reset leaves the nudge throttled and the run
   unfalsifiable.
5. **Harness kills must target LISTEN sockets only** — `lsof -ti :port`
   matches the test's own client sockets and kills the runner mid-leg;
   `-sTCP:LISTEN` is required in every restart script.

## Deviations from plan

- None functional. One extra unit assertion group (dedupe clause) and the
  kickoff step-9 rewording were added beyond the plan as the run-2 fix.
