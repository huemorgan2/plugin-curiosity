# Phase 6 — Validation Report: the vision arc on a real running Luna

> Status: COMPLETE — walkthrough run 14: **13/13 checks**, post-run probes **2/2**.
> Evidence: `dojo/results/curiosity-phase6/run14/` (checks.json + 8 screenshots).

**Setup:** genuinely fresh Luna (`luna_fresh` DB created empty, redis db1 flushed, own
scheduler-service account `fresh-luna`, scratch managed dir with read-only
funnelfighters/playbooks/web_access), `:8001`, headed Playwright walkthrough
`dojo/tests/curiosity-phase6/walkthrough.mjs`. Owner signup → single chat flow, no manual
tool setup. Run 6 ran with web_search unconfigured (validated the degradation path:
visible error → gateway probe → `request_credential` vault card); run 14 configures the
Tavily key so the research day is real. The walkthrough plays an attentive owner: it
approves pending onboarding approval cards via the approvals API — identity writes are
approval-gated and park the turn until the owner decides (see gaps). Evidence dir:
`dojo/results/curiosity-phase6/run14/`.

## Vision beats → observed behavior

### Beat 1 — fresh Luna owns the mission
- **Claim:** given "grow signups," Luna owns the mission (renders in system prompt).
- **Observed (run 14, checks 0–2b, all PASS):** from a provably empty state
  (mission=null, pages=0, onboarding incomplete), the unprompted greeting asked
  "what kind of work do you want me to own for you" before any name/emoji talk
  (missionIdx=161, nameIdx=-1). The owner's one-line answer produced a live
  curiosity mission the same turn: "Grow signups for FunnelFighters, a SaaS
  product — research the funnel, activation and retention…" — and the bridge
  saved the identical statement as identity. No nudges needed.
- Mission-first inversion: the first-run greeting itself asks for a mission before
  name/emoji (checks 1/1b), and `mission_set` is called in the same turn the owner states
  it (check 2), with the onboarding bridge saving it as identity too (check 2b).

### Beat 2 — same-day quick win
- **Claim:** kickoff artifact (brief, seeded cited wiki, concrete insight, open questions)
  the same day, no manual tool setup.
- **Observed (run 14, checks 3/3b, PASS):** a 1,908-char kickoff brief landed in the
  onboarding conversation the same day (muted fire + assistant reply), and the wiki
  seeded from zero to 4 pages with 5 open questions — before setup was even complete.
- Degradation path (run 6, web_search unconfigured): kickoff degrades gracefully —
  visible error → gateway probe → `request_credential` secure vault form in chat →
  artifact from model knowledge. Run 7 (key configured) exercises the real research path.

### Beat 3 — research days: wiki grows, ≤1 grounded reflection/day
- **Claim:** she researches, the wiki grows with cited pages, ≤1 reflection/day in quiet
  hours.
- **Observed (run 14, 6-pre daily-research beat):** run-now on the real trigger produced
  a genuine Tavily-backed research turn — revisions 6→8 on the (aged) wiki, and
  `wiki_citations` holds 6 rows with real source URLs (firstpagesage.com,
  productfruits.com, emailtooltester.com, …). Cap/grounding rails (ROUTINE_DAILY_CAP=1,
  grounding regex, quiet-hours queue) are phase-4 unit+dojo-proven.

### Beat 4 — nightly dream via the real scheduler
- **Claim:** dream consolidates pages and delivers one morning thought, fired by the real
  `luna-scheduler`, not an in-plugin loop.
- **Observed (run 14, checks 5/6/6b, PASS):** both recurring triggers registered on the
  fresh scheduler account (research daily 09:00, dream daily 02:00); run-now fire →
  `emitted: agent_prompt` + real assistant turn + consolidation revisions 8→10 +
  exactly one "Morning thought" reflection.
- Empty-day branch **(run 14, check 7, PASS):** with every trace of "today" hidden
  (pages/revisions backdated, reflections cleared, fire parked in a quiet
  conversation), the dream declined in exactly the designed words: "Every page has
  `age_days >= 1` — … Quiet night — nothing to consolidate." Zero revisions, zero
  thoughts. Getting here took four root-cause rounds (see execution summary): the
  decisive fix was product, not test — wiki_toc now returns a server-computed
  `age_days` because the model has no clock and cannot judge recency from raw ISO
  timestamps.

### Beat 5 — escalation to rung-3 draft + actioning rails
- **Claim:** reflections trend to a draft recommendation (rung 3); she authors a playbook
  and its side-effecting step surfaces an approval card, never executing silently.
- **Observed:** playbook gate — run 14 check 8 PASS: `growth-digest` playbook authored
  in chat; its side-effecting `playbook_run` produced a pending approval row and the
  agent's own reply says a confirmation card goes to the owner — zero silent
  executions across every run and retry of this validation (runs 2–14).
- Rung-3 draft recommendation — probe B PASS: asked to escalate, she shared a grounded
  routine reflection "Draft Recommendation: Prioritize First-Session Activation |
  Based on [[mission-domain]] and [[competitors]]…" (reflections 0→1, grounding
  regex satisfied). Screenshot: `B-draft-recommendation.png`.

### Beat 6 — legible understanding (wiki sidebar)
- **Claim:** the human can see "what Luna understands" via the wiki sidebar.
- **Observed:** probe A PASS — the wiki sidebar renders the live mission wiki (11
  nodes rendered for the 5 DB pages: seeded + researched + dream-consolidated).
  Screenshot: `A-wiki-sidebar.png`.

## Acceptance criteria

| Criterion | Status | Evidence |
|---|---|---|
| Fresh Luna + mission → same-day quick-win artifact, no manual setup | **PASS** | run 14 checks 1–3b |
| Growing cited wiki, ≤1/day reflections, nightly consolidation, morning thought, rung-3 draft | **PASS** | run 14 checks 3b/6/6b + probe B; 6 real-URL citations |
| Dream fires via luna-scheduler (not a plugin loop) | **PASS** | run 14 checks 5/6, fires API run-now → `emitted: agent_prompt` |
| Playbook side-effecting step approval-gated | **PASS** | run 14 check 8 |
| No unattended external writes | **PASS** | playbook gate held every run and retry (runs 2–14: pending rows accumulated, zero executions) |
| Validation report on a real running Luna | this document | — |

## Gaps / follow-ups filed

- **A turn parked on approval cards is indistinguishable from a dead turn.** Identity
  writes (`update_self` etc.) block the agent turn on the approval await — no TTL, no
  composer/status hint that Luna is *waiting* rather than *thinking*. With an attentive
  owner this is invisible (cards get clicked in seconds); an owner who walks away
  strands the turn, and any page navigation then cancels it. Product follow-ups:
  (a) surface "waiting for your approval" in the chat UI while a turn is parked;
  (b) consider a TTL that resolves stale cards to a rejection the model can react to.
  (`approval-gates-park-turns` memory; cost runs 2–6 of this validation.)
- plugin-scheduler records `outcome: "emitted: agent_prompt"` even when the fired turn
  dies — dead turn looks like a healthy no-op. Folded into phase-7 scope (PLAN.md).
- Chat turns are SSE-scoped: closing the tab cancels an in-flight turn. Post-v1: detach
  turn execution from the SSE request scope. (`luna-turns-die-with-sse` memory.)
- Onboarding addendum stays active on scheduler-fired turns if the owner abandons setup
  mid-flow — works, but consider suppressing it on fired turns post-v1.
- Approval-card dedup for retried playbook steps (pending rows accumulate on retries).
