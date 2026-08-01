# Phase 9.001 — Self-Setup, Holistically: the qualification doctrine + the heartbeat

**Target:** plugin-curiosity **0.7.1** (all three version stamps).
**Status: PLANNED — not started.**
**Vision anchor:** vision.md §8 Phase One + "She schedules her own drive"
(owner direction, 2026-07-10).
**Sibling track (luna core):** `luna/plans/028-phase9.1-fixes` — detached
turns, durable approval resume, history-delivery guard. 028 makes turns
*survive*; 9.001 makes the agent *drive itself*. Neither blocks the other.

---

## The owner's framing (this is the spec)

> I want two phases like we talked. **Am I qualified to do this job? If not,
> what do I need** — what tools, what connections to people, to systems, what
> plugins, tools, services? Then: **do I have the data, context, knowledge —
> and do I know what success looks like?** What are my job expectations, what
> will make me successful? Have the agent **relentlessly pursue this
> mission-job setup for itself** until it has all it needs to execute the
> mission — its job. This is phase one.
>
> I want to see that we are **holistically** driving the agent to self-setup —
> that it *knows* it, and that it also *knows to tell it to the user*. At this
> point I feel we've done a patchwork. (owner, 2026-07-10)

## The audit that motivated this plan (2026-07-10, all prompt surfaces read)

The bones are right, the frame is missing. What exists: the seven scope kinds
(knowledge, people, communication_paths, tools_data_access,
workflow_approval, playbooks, routines_feedback) ARE the qualification
inventory; the talented-hire law, loop discipline, phase branching, and the
owner-gated graduation are all real and single-sourced (prompts.py, 9C).

What the audit found — the patchwork, concretely:

1. **The qualification question is never asked.** Every surface is a numbered
   procedure (loop patrol → goal advance → scope_update → …). Nowhere does
   the agent carry the unifying self-question — *am I qualified for this job
   yet? what's still missing?* It executes setup steps without knowing what
   setup IS. Procedures without the frame is exactly "patchwork".
2. **"What does success look like" has no home.** `[[mission-metrics]]` is
   seeded at mission_set and then ORPHANED — no prompt ever drives filling
   it, ratifying it, or reading it. Job expectations / success definition
   appear in no prompt surface at all. Goals are dated deliverables, not a
   ratified definition of success.
3. **S3 is a ghost stage.** SETUP_STAGES = S0–S5; the kickoff defines S0–S2,
   the weekly review obliquely references S4 (workflow validation) and S5
   (feedback signals) — S3 is defined NOWHERE. No prompt tells the agent what
   it is or how to get there. Also: nothing forces S2 (charter posted) →
   ratification → S3+; a mission can sit un-ratified forever (observed on
   RayLa: charter overdue with no forcing function).
4. **The agent never explains the two-phase model to the owner.** The kickoff
   artifact and weekly setup report show charter/goals/scoreboard (good), but
   no surface says "tell the owner: I am in setup; my job right now is
   qualifying myself; here is my gap list; when it converges I graduate."
   The install kickoff and the missionless fragment never mention phases.
5. **Nothing is relentless.** Fixed daily/nightly/weekly cadence; an agent
   mid-setup waits up to 24h between self-driven actions.

## Design stance

One doctrine, stated once, injected everywhere; agency over machinery (the
agent authors its own drive; the framework teaches, notices, and floors).

---

## 9.001A — The Phase-One doctrine (one frame, every surface)

**Change:** a new single-source const in `prompts.py` — the owner's two
questions, verbatim in spirit:

```
PHASE_ONE_DOCTRINE:
  You are in phase one of two: SETUP — qualifying yourself for this job.
  Your driving questions, always, in this order:
  (1) Am I qualified to do this job? If not, what exactly do I need — which
      tools, which connections to people, to systems, which plugins,
      services, access?
  (2) Do I have the data, the context, the knowledge? And do I know what
      success looks like — what are my job expectations, what will make me
      successful in the owner's eyes?
  Pursue the answers relentlessly until you have everything you need to
  execute the job — that is what this phase IS. Every action you take in
  setup should close a named gap from (1) or (2). And keep the owner in the
  picture: they must always be able to see which phase you are in, what
  you're still missing, and how close you are to qualified.
```

Injected into: the setup posture in `prompt_fragment` (mission.py — replaces
the bare talented-hire line as the *opening* of the posture; the law stays as
the HOW), the mission kickoff (research.py S0 header), the daily setup
branch, the weekly setup branch, and the heartbeat contract (9.001C). Work
phase gets the one-line mirror: "phase two: WORK — you qualified; now execute
with mastery and keep improving the toolkit."

**Exit test:** grep-level — no setup surface lacks the doctrine; dojo-level —
ask a mid-setup agent "what are you doing right now and why?" cold, and the
answer names the phase, the two questions, and its current gap list.

## 9.001B — Success definition: a ratified artifact, not an orphaned stub

**Change:** `[[mission-metrics]]` becomes `[[success-criteria]]` (or the stub
is repurposed — migration renames in place): *what success looks like, the
job expectations, what will make me successful* — written by the agent in S0
from the mission + sharpened by asking the owner ONE plan-changing question
about expectations if unclear, then **ratified with the charter**. The weekly
setup report scores against it ("am I becoming the agent this page
describes?"). The kickoff artifact gains a **"What success looks like"**
section. Goals must trace to it (a goal that serves no success criterion is
scope creep — flag it).

## 9.001C — The setup heartbeat (self-scheduled, relentless, convergent)

As previously planned, now carrying the doctrine as its prompt core:

- At mission birth the agent creates its **own** recurring heartbeat trigger.
  The self-authored prompt must center the two doctrine questions — *am I
  qualified yet? what's still missing? do I know what success looks like?* —
  NOT a task-list check ("finish the tasks" is too narrow a way to think
  about setting yourself up).
- **Relentless during setup:** hours, not days (guidance 2–4h waking hours;
  agent picks). No frequency cap in setup.
- **Mandatory convergence criterion, stated inside the trigger prompt:**
  converged = N consecutive fires (suggest 5) where the gap list produced no
  new entries and nothing wobbled through real execution — the role *feels*
  solid. Each fire ends with a one-line verdict: qualified-gap-count,
  what stabilized, what wobbled.
- **Graduation is the agent's own call to propose** (existing phase_advance
  gate, owner approves), and on graduation the agent itself demotes the
  heartbeat to maintenance cadence. Relentlessness is phase-scoped by
  design — nowhere to run away to.
- Not a fourth fixed MISSION_SCHEDULES entry — that would be the rigid
  framework loop the owner rejected. The fixed three stay.

## 9.001D — No open work without a scheduled next touch

Charter norm + phase prompts: whenever the agent creates a plan, a task
list, or promises a future step — it schedules its own follow-up at creation
time (trigger or loop with next_nudge_at). Waiting for a fixed trigger or
the owner's memory is not a plan.

## 9.001E — Repair the ladder: S3 defined or deleted, ratification forced

- Give S3 a real meaning consistent with review.py's S4/S5:
  **S3 = charter + success-criteria RATIFIED by the owner** (S2 = posted,
  S3 = ratified, S4 = workflow validation run, S5 = feedback signals live).
  Define all six stages in ONE place in prompts.py, referenced by kickoff,
  daily, weekly — no stage may exist only in an enum.
- **Forcing function for ratification:** an un-ratified charter past ~3 days
  becomes the setup branch's top priority ask (and the heartbeat names it as
  gap #1) — a mission can no longer sit at S2 forever (RayLa's exact drift).

## 9.001F — The owner always knows (legibility)

- Install kickoff + missionless fragment: one plain-words sentence on the
  two-phase model ("give me a mission and I first make myself qualified for
  it — you'll see exactly what I'm missing — then I run it as my job").
- Kickoff artifact: add "What success looks like" + "Where I am: setup,
  stage Sx — what's still between me and qualified".
- Weekly setup report: scoreboard opens with the phase line and the
  qualification gap count, scores against [[success-criteria]].

## 9.001G — The safety net (notice, don't override)

- On-load: mission in setup + no heartbeat → muted nudge to create one.
- Weekly review audit: heartbeat exists? convergence criterion present in
  its prompt? verdict lines appearing? success-criteria ratified? cadence
  still earning its cost post-graduation? Any miss becomes the review's ONE
  ask. The net reminds; it never silently creates.

## 9.001H — Tests

- **Unit:** doctrine const present in every setup surface; stage definitions
  single-sourced; on-load nudge fires exactly when (mission ∧ setup ∧ no
  heartbeat); metrics→success-criteria migration idempotent.
- **Dojo (dumb-user):** vague mission from a confused owner, then the owner
  goes SILENT. Green =
  1. kickoff artifact contains success-criteria + phase line;
  2. agent creates its own heartbeat (doctrine questions + convergence
     criterion in the prompt) unprompted;
  3. heartbeat fires advance the gap list with zero owner input;
  4. un-ratified charter surfaces as top ask by day 3;
  5. a `tasks_set` plan gets a self-scheduled follow-up;
  6. heartbeat deleted behind the agent's back → flagged and recreated;
  7. cold question "what are you doing and why?" → phase, questions, gaps;
  8. converged streak → graduation proposed → cadence self-demoted.
- The RayLa turn-death scenario stays a 028 dojo test (core-side).

## 9.001I — Ship

Three stamps → 0.7.1, suite green, dojo green, commit, push, publish to
marketplaces.com.ai, execution_summary.md. Standard.

---

## Evidence still owed (carried from the incident)

RayLa runs core **v0.33.004** (owner screenshot) — modern core, full
history-rebuild machinery — so the fresh-chat amnesia is a LIVE bug. 028
phase F must read the incident rows from RayLa's own DB; verified NOT on
this machine's postgres (local 5433 hosts a different agent). Open question
to owner: where does RayLa run?

## Relationship to other phases

- **Phase 9.1 (planned, separate):** single mission source — remove
  `identity.mission`; unaffected.
- **Core 028:** reliability track (turns that survive) + task-driver floor
  under this behavior layer.

## Exit criteria

- [ ] One doctrine, single-sourced, present on every setup surface; the
      agent can state it cold (dojo-proven).
- [ ] Success-criteria artifact exists, is ratified with the charter, and
      the weekly scores against it.
- [ ] Every setup stage S0–S5 is defined in exactly one place; ratification
      has a forcing function.
- [ ] Agent-created heartbeat with convergence criterion, no owner
      prompting; setup advances with a silent owner; graduation self-demotes
      the cadence.
- [ ] Owner-legibility: phase + gap list visible in kickoff, weekly, and on
      cold questioning.
- [ ] Safety net detects missing/malformed heartbeat and un-ratified
      success-criteria; never auto-creates.
- [ ] 0.7.1 shipped (three stamps, marketplace, sha-verified),
      execution_summary.md written.
