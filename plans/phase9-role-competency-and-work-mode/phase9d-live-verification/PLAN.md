# Phase 9D — Live behavioral verification (dojo walkthrough)

**Parent:** [../PLAN.md](../PLAN.md) §4 (9D) + acceptance criteria. Proves the
setup arc, ask economics, durability, replan/refix, and graduation on a real
running Luna — the 8.x lesson: unit tests catch regressions, not compliance;
every mechanism must be seen live (memory: verify plugins on a real Luna).

**Depends on:** 9A–9C. **Blocks:** 9E (no ship without this green).

---

## Harness

- `luna/dojo/tests/curiosity-phase9/walkthrough.mjs`, fresh dev Luna (fresh DB
  + redis namespace + managed dir, launch-script pattern from phase 8),
  local scheduler mode; results under `dojo/results/curiosity-phase9/`.
- Hardening carried over: generous polls (kickoff does real research — 10 min
  budget; 8.2 learning 4); match on `m.title` — `extra.*` flattens (8.1
  learning 5); nudge-once on silent turns (phase 6 ConnectTimeout lesson);
  approvals via API (approval gates park turns — memory).
- Time control: no wall-clock waits — time-warp by rewriting `next_nudge_at` /
  `target_date` in the DB, then fire triggers via the scheduler API run-now.
- *9C learnings:* reset must truncate `memory_facts` AND use a fresh
  conversation — a dead mission surviving in chat scrollback or memory makes
  the agent (correctly) refuse a second mission. A vague "can you take this
  on?" yields a sharper proposal + one confirming question, adopted on a
  shrug — send the shrug when no mission row appears after turn 1. Approvals
  list key is `requests`; approve body needs `{reason}`. Kickoff moments are
  stored as `role='user'` messages ("Your mission was just set…").

## Checks (in order, each PASS/FAIL logged)

1. **Kickoff shape (S0/S1/S2).** mission_set → kickoff artifact: charter +
   stage marker + 5-8 dated goals covering all scopes + loops opened for its
   own questions; **zero ask loops exist**; value/observations appear BEFORE
   any need-language (string-position assert).
2. **Small increments.** Pre-ratification wiki pages are stub/summary depth
   (size ceiling per page, spot-checked); no page exceeds the shallow-pass
   budget until the owner's ratification reply lands.
3. **First ask earned.** After a value pass, `value_log` has ≥1 row → agent's
   first ask loop exists with `unlock` + `value_ref`; the artifact ENDS (not
   opens) with it.
4. **Enforcement visible.** Scripted turn asks the agent to raise two more
   asks: second concurrent ask rejected (steering message surfaces in the
   turn); ask-without-fresh-value rejected likewise.
5. **Durability.** Leave a question loop unanswered; time-warp +2d; fire the
   daily trigger → the note re-asks it REPHRASED, naming the blocked goal;
   nudge_count incremented; `[[open-loops]]` updated.
6. **Grant → payoff.** Answer the ask (simulate the grant: enable the tool /
   post the owner reply); fire daily → artifact references the grant and
   `value_log` grew (grant-payoff rule).
7. **Replan forward + refix backward.** Owner reply: "we don't use X —
   everything runs through system Y" → same/next fire: Plan-changes gains a
   dated entry; the obsolete goal/ask dropped with reason; a new
   `tools_data_access` scope/goal for Y appears; one `competent` scope
   invalidated by the learning regresses to `in_progress` and the artifact
   states the correction plainly.
8. **Workflow validation (S4).** The workflow/approval scope reaches
   `competent` only after a validation run is recorded in the charter (drive
   one approval-path item through; approve via API).
9. **Graduation.** Force all scopes competent (tool calls) → weekly fire
   proposes graduation citing per-scope feedback signals (S5); approve the
   `phase_advance` card via API → phase flips to `work`.
   *9A learnings:* the card is `risk_level=medium`; approvals API is
   `GET /api/p/plugin-approvals/?status=pending` +
   `POST /api/p/plugin-approvals/{id}/approve` (NOT `/api/approvals`, which
   returns the SPA with status 200). A naive "just switch yourself over"
   push is REFUSED by a correctly behaving agent — to exercise the waiver
   path, script info-then-insist ("here are the basics… now skip the rest"),
   which yields `phase_advance(waive=[...])` and per-scope waiver entries in
   Plan-changes. Assert phase is FROZEN while the card is parked.
10. **Work mode.** Next weekly fire emits "Work report — week in review" with
    done/insights/improvement-suggestions/Next move; daily note is one-line
    goal-cited; rolling-goal refill observed after closing a goal.
11. **Hygiene.** 0 prompt.assemble violations/failures in server logs; no
    duplicate kickoff/moments (8.1 claim/sleep pattern still holding).

## Acceptance-criteria mapping
Checks 1-3 → criteria 1, 2, 9 · check 5 → 4, 5 · check 6 → 3 · check 7 → 8 ·
checks 8-10 → 6, 7 · wiki-only reconstruction (criterion 6): a final assert
reads ONLY the five wiki pages and answers the four owner questions
(become/when/needs/delivered) — no chat scrollback in that assert's inputs.

## Exit criteria
- All checks green on a fresh Luna, twice consecutively (flake guard).
- Live bugs found → fixed → full rerun (phase 8 ran 3 rounds; budget for it).
- Results + screenshots committed under dojo/results; walkthrough committed
  to luna main with a plan-025-style note if any core issue surfaces (luna
  changes need a plan — memory).

## Non-goals here
Production scheduler / marketplace-artifact e2e — that is 9E's ship gate,
reusing the phase-8 `walkthrough-prod.mjs` pattern only if 9E deems it needed.
