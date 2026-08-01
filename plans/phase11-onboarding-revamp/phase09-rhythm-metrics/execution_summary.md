# Phase 09 — rhythm & metrics: execution summary

Shipped: plugin-curiosity 0.19.0. No goalseek or luna-core changes.

## What landed

**Proposal ledger (11.008/M7)**
- `curiosity_proposals` table + `proposals.py` ProposalStore: open → decide
  (accepted/declined) → close (done/dropped). ONE open proposal at a time —
  the cap lives in the tool layer with steering hints that name the open one;
  reopen by same title (case-insensitive) converges instead of erroring;
  a decline is terminal; closing requires `actual` ("The prediction was
  public; the result is too."); `done` requires a prior accepted decision.
- Tools `proposal_open` / `proposal_decide` / `proposal_close` /
  `proposal_list` (all auto_approve). `prediction_hit()` scores a closed bet
  inside a ±30% band; None when either side is missing or predicted is 0
  (prose-only predictions stay honest, never fabricated into a score).
- `_verdict()`: the store formats the closed bet's verdict sentence
  ("predicted X, actual Y — the prediction held (within ±30%)") and returns
  it from `proposal_close` and as `last_closed.verdict` in `proposal_list` —
  the weekly note quotes it verbatim instead of re-deriving it.

**Weekly-note bet gate (tool layer — added mid-dojo, see learnings)**
- `ProposalStore.weekly_note_gap(body)`: a work-phase weekly review note
  refuses to post unless a proposal is open or one closed within 7 days;
  when a bet closed this week the note must carry the verdict words, and the
  refusal hands the exact sentence to quote. Incident escape: a body saying
  "recovery first" passes without a bet. Wired into `comms.share()` for
  `kind='review'` + the work-phase title only; setup notes untouched.

**Server-computed KPI funnel**
- `telemetry.compute_metrics` (pure) + `gather_metrics` (DB): 18 KPIs —
  funnel head (time to confirmed mission / first win / setup→work), card
  discipline (closed, redirect rate), expectation hit rate, boundary
  exceptions (live cross-plugin probe of goalseek `policy_list` via the tool
  registry — None when goalseek is absent, zeros-dict when installed but
  empty), hypercare entry/exit, automation override/ignore TOTALS (no run
  denominator exists — no fabricated rates), proposal acceptance rate,
  prediction accuracy. None always means "no data", never zero.
- Tool `metrics_snapshot` (auto_approve; description mandates quoting
  verbatim — "never compute or estimate a metric yourself") and route
  `GET /api/p/plugin-curiosity/metrics`.

**Rhythm prompts**
- Weekly WORK branch rewritten as FIVE headed lines: **Ran** / **Cost vs
  value** (owner units, metrics_snapshot + [[value-log]] only) / **Health**
  ("'No issues' ONLY when literally true") / **Proposal** (one bet, verdict
  leads when one closed; "a normal week ALWAYS places its bet") / **Next
  move**. Success criteria scored on the wiki page, not in the note.
- `MONTHLY_REVIEW_TARGET`: promised-vs-delivered value ledger — CARD FIRST,
  gather-never-guess, opportunities each anchored to an owner quote or
  receipt ("no anchor stays off the list", downsells first-class), exactly
  ONE one-word-answerable decision; incident months list no new bets; setup
  months report "setup progress vs promise". Scheduled
  "on the 1st of every month at 09:45" (exact scheduler grammar) as
  `curiosity-monthly-review` in MISSION_SCHEDULES.

## Verification

- Unit: 531 passed (13 proposal tests, 12 metrics tests, monthly/weekly
  target shape tests, 3 bet-gate tests, budget guards updated with 0.19.0
  rationale).
- Live (QA Luna 8767, luna_p05, Gemini): GET /metrics returned real KPIs
  including the live goalseek boundary probe ({active:3, checks:2,
  exceptions:2} — phase-08's midnight-deny counters), proving the
  cross-plugin registry probe against a real toolset.
- Dojo (muted-turn driver, 9/9): weekly turn 1 → 5-head note lands in
  `curiosity_reflections` AND exactly one proposal row with a prediction
  (the gate forced `proposal_open` before the note posted — rows 5 s apart);
  owner-decision turn → decide(accepted) + close(actual_minutes=25);
  weekly turn 2 → the note LEADS its Proposal line with the quoted verdict
  ("predicted saves setup time by 10%, actual … 25 minutes"); /metrics
  reported proposals_decided=1, acceptance 1.0. An earlier gate-less run
  also verified the scored path: predicted_minutes=30 vs actual 25 →
  prediction_accuracy 1.0.
- Mission restored to setup/S2 (phase_entered_at NULL), dojo rows cleaned.
- Not live-verified: the monthly trigger creation (QA has no
  scheduler-service connected — unit-verified only, same mechanics as the
  weekly trigger which runs in production).

## Learnings (fed forward)

1. **Prose lost twice; the tool layer won first try — again.** Runs 1–2:
   Gemini wrote "No proposal this week; currently focusing on…" on a normal
   week, straight past an explicit "ALWAYS places its bet" prompt line. The
   `weekly_note_gap` gate (refuse + steering hint) fixed it in one run —
   turn 1 opened a real bet 5 seconds before the note posted. Same doctrine
   as phase-03/07: a note the model must not post is a note the tool must
   refuse.
2. **Give the model the words, not just the data.** Run 3: given raw
   `last_closed` fields, the model wrote "No proposals closed this week"
   over a bet it closed minutes earlier. Server-formatting the verdict
   sentence and demanding its words in the note fixed it — vocabulary fix
   over prompt ban, applied to numbers.
3. **First muted turn after a QA restart is often inert** (zero tool calls,
   inline answer) and the flake recurs randomly (~1 in 3 turns). Dojo
   drivers now retry a turn whose DB probe shows nothing happened — the
   production analogue is the next scheduled fire. Worth watching whether
   production Anthropic-model tenants show the same; not a plugin defect.
4. **Prose-only predictions are common** — the model often omits
   `predicted_minutes` (run 5: "saves setup time by 10%"). `prediction_hit`
   returning None keeps accuracy honest; if Roy wants more scored bets, the
   proposal_open description could push harder for minutes, at the cost of
   fabricated numbers. Left as-is deliberately.

## Feed-forward to phase 10+

- The incident ledger is still a fixture (`incidents=None`) —
  time_to_self_report stays None until an incident table exists; wire it
  when the incident protocol gets its own storage.
- automation overrides/ignores stay TOTALS until a run counter exists;
  never invent a denominator.
- The "1.0.0-adoption" re-stamp remains a decision to take with Roy.
