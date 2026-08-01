# Phase 6 — onboarding & validation (the finish line)

**Goal:** the payoff. A **fresh Luna** with `plugin-wiki` + `plugin-curiosity` installed,
handed a mission on first run, behaves exactly as the [vision](../../vision.md) describes —
and we prove it on a **real running Luna**, not just unit tests.

**Depends on:** Phases 1–5. **Spike:** **SP4** (growth-mission dry run, end-to-end).

---

## Scope

**In:** the first-run onboarding change (mission-first flow); a clean install of both plugins
on a fresh Luna; the full-loop validation against the vision's growth mission using only
**read-only** reused tools.

**Out:** production scheduler (phase 7); rung-4+ autonomy; external writes.

---

## The onboarding change

Make **mission-first** the fresh-Luna experience: on first run with curiosity installed, Luna
asks for (or receives) a mission *before* anything else, then immediately kicks off curiosity —
the E11 muted kickoff message + the phase-4 Mission Kickoff quick-win artifact. This inverts
the usual "configure tools first" flow into "mission → curiosity → shared understanding →
trust → setup," which is the core inversion of the vision.

## Validation — the growth mission, zero new integrations

Point the whole loop at the vision's funnel/growth mission using **read-only**
`plugin-funnelfighters` (`ff_*`) tools + `plugin-web-access`. No new integrations.

Walk the vision's emotional arc and check each beat actually happens:
1. Fresh Luna, given "grow signups," **owns the mission** (renders in system prompt).
2. Same day: a **quick-win** Mission Kickoff artifact — brief, seeded cited wiki, one concrete
   insight, open questions.
3. Over days: she **researches**, the **wiki grows** with cited pages, she shares **≤1
   grounded reflection/day** within quiet hours.
4. Nightly **dream** consolidates pages and delivers **one morning thought** — fired by the
   real `luna-scheduler` (run locally in dev), waking the machine, not an in-plugin loop.
5. Reflections trend from observations → advice → a **draft recommendation** (rung 3). She also
   **authors a playbook** for a repeatable action; running its side-effecting step surfaces an
   **approval card** rather than executing silently (rung 4 = execute-with-approval; the rails
   are proven, the ceiling stays approval-gated).
6. The human's picture of "what Luna understands" is legible via the wiki sidebar.

**Verify on a real running Luna** (per project rule) — the loop must be exercised live, since
unit tests have previously missed cookie-auth, widget-token, and stale-route bugs.

---

## Steps

1. Implement the first-run mission-first onboarding + kickoff wiring.
2. Fresh-install both plugins on a clean dev Luna; confirm clean load + enable.
3. SP4: run the growth mission for several simulated days; capture the artifacts at each arc
   beat (kickoff, daily reflections, wiki growth, morning thoughts, a rung-3 draft).
4. Write a short **validation report** in this folder mapping each vision beat → observed
   behavior (pass/fail + evidence).
5. File any gaps as follow-ups; fix blockers before declaring v1 done.

## Acceptance criteria

- [ ] A fresh Luna + both plugins, given a mission, produces a same-day quick-win artifact with
      no manual tool setup.
- [ ] Multi-day run shows: growing cited wiki, ≤1/day grounded reflections in quiet hours,
      nightly consolidation, one morning thought/day, escalation to a rung-3 draft recommendation.
- [ ] The nightly dream fires via `luna-scheduler` (waking the machine), not a plugin loop.
- [ ] The agent authors a playbook and its side-effecting step is **approval-gated** (card
      shown, not silently executed) — actioning rails proven without crossing the v1 ceiling.
- [ ] No **unattended** external writes occur; any action requires approval.
- [ ] Validation report exists, mapping every vision beat to observed evidence, exercised on a
      **real running Luna**.

## Notes / risks

- This phase is the definition of done for v1 — the vision, demonstrated end-to-end.
- Keep the mission growth-focused so reused read-only tools suffice for *research*. Actions are
  exercised via one approval-gated playbook to prove the rails; unattended execution (rung 4
  auto / rung 5) stays a deliberate post-v1 policy flip, not scope creep here.

> **Phase-1.5 learnings:** the wiki graph pane uses a deterministic two-ring layout that gets
> crowded past ~50 pages. If the onboarding/vision run seeds a large wiki, that's the moment
> to switch GraphView to a force layout (elkjs/d3-force) — don't do it preemptively, the
> deterministic layout keeps dojo checks stable.

> **Phase-4 learnings:**
> - Beat 2 (same-day quick win) is already wired: `mission_set` fire-and-forgets the kickoff
>   moment (muted line + badged artifact with Brief / Quick win / Open questions in the same
>   conversation). Onboarding only needs to get a mission adopted — the rest cascades.
> - The kickoff reaction turn takes **8–16 minutes** of real research; the onboarding UX and
>   the validation script must both treat it as eventually-arriving, not same-minute. Don't
>   run other chat turns against the dev box while it's in flight (I/O contention starves
>   them).
> - Beat 3's "≤1 grounded reflection/day" is enforced by phase-4 guardrails (grounding regex,
>   ROUTINE_DAILY_CAP=1, quiet-hours queue + drain); the multi-day arc can assert via
>   `GET /api/p/plugin-curiosity/comms/reflections` (growth-based, state accumulates).
> - Multi-day arc chat prompts must instruct marker-bearing replies (`RESULT-${RUN}: ...`);
>   raw tool JSON doesn't contain the run nonce.

> **Phase-5 learnings:**
> - **`luna serve` loads plugins in a throwaway bootstrap loop** (`asyncio.run` in cli.py),
>   then uvicorn runs a NEW loop — any task a plugin creates in `on_load` silently dies with
>   the bootstrap loop (no exception, no log). If onboarding needs on-load work (first-run
>   detection, kickoff nudge), use curiosity's pattern: register a startup hook in
>   `register_routes` via `app.router.on_startup.append(...)` + a loop-identity guard so the
>   on_load call (runtime-install path) and the hook (serve path) never double-schedule. The
>   app object has **no `add_event_handler`** — and an exception inside `register_routes`
>   kills ALL of that plugin's routes for the boot (`plugin.routes_failed` in the log).
> - Fresh-install step 2 must therefore check the serve log for `routes ok` (not just clean
>   import) for every plugin, and verify sync-on-load actually ran (trigger targets current).
> - **Empty-day dream no-op must be validated here**: on the fresh Luna, before any research
>   has touched the wiki that day, `run-now` the dream trigger and expect the "quiet night —
>   nothing to consolidate" path: no new `wiki_revisions` rows, no reflection row, outcome
>   still `emitted: agent_prompt`. (Phase 5 validated the busy-day path live; the empty-day
>   branch is unit-tested only.)
> - The dream turn is prompt-capped (~10 tool calls) and ran fast in phase 5, but budget the
>   same 16 min as research turns when polling `outcome=emitted` — it lands only AFTER the
>   full turn.
> - Beat 4 assertions, proven in phase 5 and reusable: exactly-one morning thought =
>   `routine_posted_today == 1` + one `Morning thought` row in `curiosity_reflections`;
>   consolidation = `wiki_revisions` count growth; dedupe = signed replay of a seen `fire_id`
>   (HMAC-SHA256 over `${ts}.${raw}`, headers `x-sched-timestamp`/`x-sched-signature`) →
>   `{ok, deduped:true}` and still one local fire row. See
>   `dojo/tests/curiosity-phase5/walkthrough.mjs`.
> - Multi-day simulation shortcut: `DELETE FROM curiosity_reflections` resets the daily cap,
>   so several "days" of the arc can run in one real day; each dream run-now then posts its
>   morning thought immediately (daytime) instead of queuing to 08:00.

> **Phase-2 learnings:**
> - The fresh-install validation matters doubly here: core's alembic `0008_approvals.py`
>   seeds `prompt_always` rows for reserved names (`set_mission`, `set_persona`, ...) on
>   **every fresh Luna** — that's exactly why the tools are `mission_set`/`mission_refine`/
>   `mission_get`. On the clean install, confirm via
>   `GET /api/p/plugin-approvals/policy/silent-catalog` that all `mission_*` tools resolve
>   `auto_approve` before running the arc.
> - Beat 5's approval-card proof has two distinct gates, both verified in phase 2: the
>   playbook autonomy gate (`playbook_run` → `needs_approval` tool result, agent relays it)
>   and the `prompt_always` tool gate (turn **blocks**, zero persisted messages — observe via
>   the approvals API and approve/reject there). Script the validation to use the right
>   observation channel per gate.
> - Reuse the phase-2 walkthrough helpers (nonce-prefixed prompts so conversation titles are
>   run-unique, send-verification, approvals-API polling) for the multi-day arc script.
