# Phase 9C — Prompt surgery: the setup arc + phase-aware surfaces

**Parent:** [../PLAN.md](../PLAN.md) — mechanisms B (setup arc S0–S5 as an
explicit algorithm), D (timelines/taper), E (people map), F (playbooks +
phase-branched weekly), and the prompt half of G. Testable via prompt-content
assertions; behavioral proof is 9D.

**Depends on:** 9A (phase/stage state to branch on), 9B (loop/ask/value tools
to cite). **Blocks:** 9D.

**Method note (8.1 learning):** an explicit numbered algorithm beats prose —
the model executes checklists faithfully. Every surface below is written as a
numbered procedure, and each rule appears on exactly ONE surface (no drift
between copies). Shared lines (the talented-hire law, the canonical ask shape)
live in one Python const, interpolated everywhere they're needed.

---

## Surfaces and must-contain content

### 1. Kickoff (`research.py` `_KICKOFF_CONTENT`) — setup branch
Numbered S0→S2 procedure:
- S0: restate the mission sharper than the owner said it; 2-3 non-obvious
  observations from immediate (shallow) research; ONLY plan-changing
  questions, each opened as a loop with its unblock stated; explicit line:
  "zero access asks in this turn."
- S1: inventory tools/plugins/data reachable NOW (`scope_set` per finding);
  first value pass on those alone; the AdWords-style example verbatim as the
  canonical pattern; **timebox: shallow redirectable passes, stub/summary
  depth — no deep corpus until the charter is ratified.**
- S2 close: full charter — role statement, scopes (all seven kinds incl.
  workflow/approval points), dated goal timeline (5-8 goals covering every
  scope, shown as a timeline not a list), ordered access plan by
  unlock-per-human-cost — ending "this is my complete understanding and my
  road to being great at it — push back now."

### 2. Daily (`research.py` `DAILY_RESEARCH_TARGET`) — phase-branched
- Setup branch: step 0 loop patrol (9B splice, kept); overdue-goal
  confrontation (past target_date → replan/escalate/drop TODAY, with reason);
  continue small S1-style value passes; S3 one-ask-at-a-time canonical shape:
  *"I did [value] with what I have — with [grant] I can additionally
  [unlock]"*; grant-payoff rule (use every grant visibly by the NEXT daily
  fire); event-driven replan rule ("if today's learning changes the plan,
  change the plan today, not at the weekly") + anti-pattern: "a plan that
  never changes after week 1 means you stopped learning."
- Work branch: loop patrol; execute/advance validated playbooks through the
  agreed approval points; rolling goals (2-3 active, refill as they close);
  one-line goal-cited progress note (8.2 E kept).

### 3. Weekly (`review.py`) — two phase-branched targets
- Setup: **"Setup report — road to competency"** — scope scoreboard
  (status+evidence per scope); timeline on-time/late; loops chased/closed;
  **Value delivered vs asks made**; **Plan changes** block (added/dropped/
  reopened + causing learning; may be "none"); single I-need ask; S4
  (workflow validation run) and S5 (feedback-signal wiring) progress;
  graduation proposal iff gate passes, citing per-scope feedback signals.
- Work: **"Work report — week in review"** — what was done (runs/outputs/
  goal movement); insights; concrete improvement suggestions for tools/
  playbooks/methods (a diff, a cadence change, a plugin); **Next move**.
- Both end value-first-ask-last; `kind="review"` cap exemption unchanged.

### 4. Mission fragment (`mission.py` `prompt_fragment`) — phase-aware
- Setup branch: operator text + the talented-hire law in two lines + the
  small-increments corollary in one line.
- Work branch: mastery/improvement posture ("the routine is yours; every week
  leave the toolkit better than you found it").
- Missionless branch untouched (8.1 owns that seam).

### 5. Cross-cutting instructions (single-source consts)
- Canonical ask shape; value-first-ask-last ordering + "never open with a
  requirement"; every question/promise becomes a loop in the same turn;
  people-map upkeep (`[[people]]`: who/why/path/needed; missing path → goal +
  owner-intro ask) — E; playbook author→validate→competent bar + S4 workflow
  validation run — F; all playbook/marketplace/channel references behind
  feature-detection language (absent tools degrade gracefully).

## Implementation steps

1. Extract shared consts (law, ask shape, ordering rule) into `prompts.py`.
2. Rewrite the four surfaces with branch selection reading 9A state.
3. Trim for budget: each surface's new material ≤ ~10 lines over 0.6.0
   (parent-plan risk: prompt bloat; branching halves active text).

## Tests (prompt-content assertions, per branch)

- Law phrases + ask shape present exactly once per assembled surface.
- S0 "zero access asks"; S1 timebox language; S2 "push back now".
- Replan rule + never-changes anti-pattern in daily-setup only.
- Taper (rolling goals) language in work branch only; big-batch (5-8) in
  kickoff only.
- Titles: setup/work weekly titles exact (dojo matches on `m.title`).
- Anti-patterns absent: "work quietly", open-with-a-requirement.
- Branch selection: fragment/daily/weekly render setup text when
  `agent_phase=setup`, work text when `work` (parametrized).

## Exit criteria
- Prompt assertion suite green; total prompt-fragment growth measured and
  within budget; a dev-Luna smoke turn shows the kickoff following S0 shape
  (full behavioral proof deferred to 9D).

## Non-goals here
New tables/tools (done in 9A/9B), dojo automation (9D), version bump (9E).
