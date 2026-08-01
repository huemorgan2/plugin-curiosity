# Phase 07 — automation loop — execution summary

**Shipped:** plugin-curiosity 0.17.0 · tests: 488 (32 new) · real-Luna dojo
9/9 (QA 8767, incl. a live Gemini reaction turn recording the sign-off) ·
screenshot `dojo_automations.png`.

## What landed

- **`models.py` — `Automation`** (`curiosity_automations`, new table → no
  additive migration): mission-scoped standing job with the lifecycle state
  {building, awaiting_your_signoff, hypercare, running, paused, retired},
  the go-live trio (target / kill_switch / failure_detect), sign-off record
  (at / kind / note), hypercare counters (clean_runs, corrections,
  hypercare_since), and adoption counters (overrides, ignores).
- **`automations.py` — the state machine in the tool layer** (flows belong
  here; every illegal call refuses with a steering hint):
  - *Go-live gate in code*: `automation_signoff_request` refuses while
    kill_switch, target, or failure_detect is empty, and refuses without
    real `samples` text — an automation cannot leave `building` any other
    way.
  - *Sign-off before autonomy*: `automation_signoff` is the only door out
    of `awaiting_your_signoff`; a waiver is recorded distinctly
    (`signoff_kind='waived'`, owner-words note REQUIRED).
  - *Hypercare math*: `automation_run_report(ok=true)` counts a streak;
    promotion fires inside run_report only when `clean_runs ≥ 5` AND ≥ 7
    days since `hypercare_since` (pure `promotion_due()` — unit-testable to
    the day). Promotion returns an `announce` payload carrying the numbers
    and the kill switch — announced, never silent. `ok=false` REQUIRES a
    correction_note, resets the streak, and drops a *running* automation
    back to hypercare.
  - *Kill switch*: `automation_pause` from any live state;
    `automation_resume` re-enters hypercare (streak reset) — never straight
    to running; paused-before-signoff resumes to `building`.
  - *Adoption alarm*: `automation_adoption_event(override|ignore)`; at 3
    total the payload pages the agent — fix it or propose retiring.
    `automation_retire` needs `owner_ok=true` + the owner's words.
  - 9 tools, all `auto_approve/low`, ValueError → `{"error": ...}`,
    telemetry `changed/automation` on mutations.
- **Catalog + waiting**: `services_block()` renders "What I run for you"
  with plain words only — being built / waiting for your OK / extra watch /
  running / paused (css watch/ask/run pills, retired hidden; section hidden
  while empty). `journey._waiting` adds a real Approve button
  (`action='approve_automation'`) per awaiting_your_signoff automation;
  `app.js` sends the muted moment with
  `MOMENT_TOOLS.approveAutomation = ['automation_signoff',
  'current_state_set']`.
- **`overview.py`**: full `automations` list in the payload (ops tab) +
  services/automations into `build_journey`; best-effort read like every
  other block.
- **`prompts.py` — `AUTOMATION_LOOP_RULE`** on both phase branches: what
  counts as an automation, register-when-you-start-building, sample
  sign-off before any autonomous run, hypercare reporting + announced
  promotion, adoption honesty, pause-on-a-word. Prompt-budget test bumped
  (+~1.3k chars per branch) with the usual correctness-contract note.

## Dojo (QA Luna 8767, DB luna_p05, headless Chrome + CDP)

9/9 with three DB-fixture automations (one per visible state): services
section rendered all three with plain words and correct pill classes, zero
lifecycle enums anywhere in the rendered rows, Approve button carried the
right automation id, click → muted moment → **the live agent turn called
`automation_signoff`** → DB row landed `hypercare / approved / signoff_at
set / clean_runs 0` (~15 s after click). Fixtures deleted after the run.
The phase06 driver hygiene (iframe-by-src, viewport override,
poll-not-sleep, nav-click not deep-link) held with zero dojo failures —
first fully clean dojo of the project.

## Learnings → later phases

- **Clean-runs N: keep 5 runs / 7 days** — the dojo + unit math confirmed
  the two-condition gate (streak AND full weekly cycle) is what makes a
  daily automation take a real week and a weekly automation take ~5 weeks.
  Phase08 boundary/recovery policy defaults should reuse this same
  two-condition shape (count AND elapsed-time), not a bare counter.
- MOMENT_TOOLS + SAY worked unchanged for a brand-new button — the 063
  muted-moment pattern is now proven extensible without core changes; use
  it for any phase08/09 recording buttons.
- `promotion_due()` as a pure function (row + now) made the weekly-cycle
  edge exactly testable; keep policy predicates pure and out of handlers.
