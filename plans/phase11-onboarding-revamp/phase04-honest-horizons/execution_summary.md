# Phase 04 — Honest horizons: execution summary

plugin-curiosity **0.15.0** (schema bump). Status: SHIPPED — 426 unit tests
green, dojo unit 6 live run 7/7.

## What shipped

- **Typed horizons on Goal** (`models.py`): `horizon_kind` in
  {agent_minutes, awaiting_approval, on_unlock, date, rhythm} + free-text
  `horizon_ref`, both additive columns in `_ADDITIVE_COLUMNS` with an
  idempotent backfill: pre-0.15 rows with a `target_date` become kind
  `date` (`WHERE target_date != '' AND horizon_kind = ''`).
- **Validation + rendering** (`goals.py`): `_norm_horizon` — kind `date`
  demands a real ISO date (steering ValueError otherwise, "never guess a
  date") and mirrors into legacy `target_date` so the pane timeline keeps
  working; a bare ISO `target_date` derives kind `date`; bare free-form
  text stays untyped (backward compat). `_horizon_phrase` renders each kind
  in owner words — "about 45 minutes of my work once I start", "waiting on
  your approval: X (~5 min of your time)", "starts when this unlocks: X",
  "target: DATE", "rhythm: weekly". Blocked kinds never render "overdue".
- **Delegation** (`goals.py` / `engine.py`): goal-seek knows exactly one
  time unit — a real date deadline. Kind `date` maps to `deadline`; every
  other kind rides the provenance note + the pointer snapshot, which
  `list_mission_goals` overlays onto engine reads. A bad date is a steering
  error with NO engine open. `to_curiosity_dict` maps an engine deadline
  back to kind `date`.
- **Pace blame** (`telemetry.py` / `overview.py`): `compute_pace` takes
  `blocked_horizons`; a blocked goal never worsens the band — it adds a
  reason naming the unlock and its ~5-minute human cost ("'X' waits on
  mailbox access — about 5 minutes of your time unlocks it").
- **Prompt law** (`prompts.py` + every surface): new `HONEST_HORIZONS`
  constant — bans human-rhythm duration promises ('3-5 days', 'in about a
  week'), phrases waits by unlock + whose move, real dates only when a
  real-world event carries them, typed horizons mandated on goal_set /
  goal_update, blocked ≠ late. Rides both prompt_fragment phase branches,
  kickoff, daily, weekly. OWNER_WORDS extended with the WHEN vocabulary.
  Kickoff milestone mandate now emits typed horizons; daily target
  confronts overdue only for kind `date` and confronts the BLOCKER (never
  the goal) for on_unlock/awaiting_approval; weekly Timeline reports each
  goal by its honest horizon.

## Test results

- Full suite: **426 passed** (39 prior + new `test_horizons.py` ~30 tests +
  `TestHorizonDelegation` in test_goals_delegation.py). All 5 offline
  testable units from PLAN.md covered; existing test_goals / test_engine /
  test_migration / phase-9002/10001 suites pass unmodified.
- Prompt budgets raised (test_prompts.py) with the 0.15.0 comment —
  HONEST_HORIZONS (~1.1k chars) rides every surface as a correctness
  contract.

## Dojo unit 6 (live, gemini, port 8767) — 7/7 PASS

Fresh QA Luna, fresh DB, curiosity 0.15.0 in the managed dir. Mission:
grow newsletter to 500 subscribers, explicitly no external deadline.

- H1 mission set + confirmed (rung 1). Kickoff card ran to `done`.
- H2 kickoff created 4 goals, **all 4 typed** — 2 `on_unlock`,
  2 `agent_minutes`, **0 dated**:
  - "Initial 3 distribution experiments launched" — on_unlock: waiting on
    job description approval
  - "Reach 500 active engaged newsletter subscribers" — on_unlock:
    successful distribution campaign scaling
  - "Audience persona profile & 10 top channels mapped" — agent_minutes: 30
  - "Landing page opt-in copy & lead magnet drafted" — agent_minutes: 45
- H3 zero `date` horizons → zero guessable dates (vacuously clean).
- H4 "when will X be done?" → *"waiting on your approval of my job
  description (about 2 minutes of your time) … about 60 to 90 minutes of
  my work"* — no banned duration, names the unlock, whose move it is, and
  the agent-minutes. Exactly the target wording.
- H5 mission-level "when will we hit 500?" (strongest temptation to guess)
  → names the unlock (performance data from the first experiments) and
  refuses to estimate before real conversion data. No guessed duration.

## Learnings → future phases

- **Horizon distribution (phase05 "What happens when" lane feed): in a
  mission with no real-world deadline, 0/4 kickoff goals are dated** —
  the lane must lead with on_unlock/awaiting_approval (whose-move framing)
  and agent-minutes; a date column is the rare case, not the spine.
- Live QA on gemini: the old google-generativeai sync SDK can hang forever
  mid-`generate_content`, freezing the turn server-side (turn stays active,
  every later message 202-queues). QA-temp fix: `request_options=
  {"timeout": 120}` in luna's gemini provider (reverted after the run) +
  driver retry treats a toolless hop-timeout/empty turn as dead. A real
  luna fix (planned change, luna/plans) is worth filing if gemini QA
  continues past phase05.
- LUNA_MANAGED_DIR must point AT managed_plugins itself (re-learned; cost
  one dojo run).
- Stale-card reaper (phase03 delta) deliberately deferred to phase07.
- UI horizon rendering deferred to phase05 surface rebuild: kind `date`
  mirrors into `target_date` so the existing pane timeline stays correct;
  non-date horizons intentionally land in the undated bucket until the new
  surface renders them first-class.
- HONEST_HORIZONS quotes its banned phrases as negative examples — the
  banned-phrase tests strip the law's own text (and OWNER_WORDS) from each
  surface before scanning (`_without_law`). Any future law that quotes its
  own anti-patterns needs the same treatment.
