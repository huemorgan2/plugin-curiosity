# Phase 11 onboarding revamp — closing summary

All nine phases executed and shipped. Final versions: **plugin-curiosity
0.19.0**, **plugin-goalseek 2.4.0** (plus the phase-06 luna-core chat
bridge, its own plan in luna/plans). Every phase ran the full loop: plan →
code → unit suite green → dojo on a real QA Luna → execution summary →
publish to marketplaces.com.ai.

## What shipped, per phase

| Phase | Milestone | Shipped in |
|---|---|---|
| 01 first contact | fresh-Luna self-intro, curiosity-led first interaction | curiosity 0.12.x |
| 02 intake confirm | draft-first intake, confirm gate, kickoff split (M1) | curiosity 0.13.0 |
| 03 next-step cards | card-before-spend, veto windows, redirects (M2) | curiosity 0.14.0 |
| 04 honest horizons | typed goal horizons, honest time units (M3) | curiosity 0.15.0 |
| 05 surface | missions pane rebuild + approve buttons (M4+M0a) | curiosity 0.16.0 |
| 06 chat bridge | composer prefill/focus bridge (M0b) | luna core (plan 06x) |
| 07 automations | lifecycle: build → sample sign-off → hypercare → run (M5) | curiosity 0.17.0 |
| 08 boundaries | goalseek boundary gate + incident protocol (M6) | goalseek 2.4.0, curiosity 0.18.0 |
| 09 rhythm & metrics | proposal ledger + KPI funnel + weekly/monthly rhythm (M7) | curiosity 0.19.0 |

## Metric baselines (server-computed, first live snapshot)

`GET /api/p/plugin-curiosity/metrics` now answers the funnel the plan asked
for — 18 KPIs, all server-computed, None means "no data" and is said so.
QA snapshot at close (fresh mission, one dojo cycle): time_to_confirmed 0.0 h
(same-turn confirm), cards_closed 1, card_redirect_rate 0.0,
boundary_exceptions {active 3, checks 2, exceptions 2} (live goalseek probe),
proposals_decided 1, proposal_acceptance_rate 1.0, prediction_accuracy 1.0
(scored run: predicted 30 min vs actual 25). Production baselines start
accruing once tenants upgrade — the funnel reads history, so no backfill is
needed beyond what the tables already hold.

Not yet measurable (deliberate): time_to_self_report (no incident ledger
table yet — protocol is prompt+gate only), automation override/ignore RATES
(no run counter — totals only, no fabricated denominators).

## What the nine dojos taught (the doctrine that now holds the system)

1. **Flows belong in the tool layer.** Every behavioral contract that
   survived contact with a live model is enforced by a tool that refuses
   out-of-order calls with a steering hint — intake confirm (02), card
   before spend (03), sample sign-off before autonomy (07), boundary deny
   (08), the weekly note's bet + verdict (09). Prose-only mandates lost
   dojo runs in phases 02, 03, and 09; gates won first try, every time.
2. **Give the model the words.** Enum codes and server-formatted sentences
   (owner-words vocabulary map, boundary sentences quoted verbatim, the
   proposal verdict string) beat prompt bans on jargon or re-derivation.
3. **DB rows are the assertion; logs and SSE are garnish.** All nine dojo
   drivers converged on: drive muted turns via API, poll turn state, assert
   on postgres rows, retry inert turns (a scheduled fire's natural retry).
4. **Server-computed honesty everywhere**: counters bump inside the effects
   session (08), metrics never trust self-reports (09), horizons carry
   typed units instead of vibes (04), 'No issues' has a literal definition.
5. **Three version stamps, flat managed dir, marker-grep after sync,
   `env -u ANTHROPIC_API_KEY`, generous muted-turn waits** — the QA
   choreography that cost runs to learn is now encoded in the drivers.
6. **Gemini QA limits**: judge flow compliance on QA, judge artifact prose
   quality only on Anthropic-model tenants; ~1 in 3 muted turns is inert
   on QA and needs the retry pattern.

## Open items (decisions or later work — none block adoption)

- **"1.0.0-adoption" re-stamp** — Roy's call, explicitly not unilateral.
  Everything M0–M7 the plan scoped is shipped; a 1.0.0 stamp is naming,
  not code.
- **Production tenant upgrade + CDP spot-check** — 0.19.0 is live on
  marketplaces.com.ai; no :9222 Chrome session existed at close, so the
  production upgrade-route spot-check is pending the next session with one.
- **Incident ledger table** (feeds time_to_self_report), **automation run
  counter** (turns override totals into rates), **per-boundary metric
  rows** (08 feed-forward) — natural phase-10 candidates.
- Monthly review trigger is unit-verified only; QA has no scheduler-service
  connected. Mechanics are identical to the weekly trigger already firing
  in production.
