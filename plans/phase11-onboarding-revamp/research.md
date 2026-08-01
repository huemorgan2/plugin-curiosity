# Onboarding Research — How Humans Adopt an Agent

What we're trying to understand: adoption is not a technology problem. Each person
prices the risk alone — *it'll cost a lot, take a lot of my time, and never work* —
and they can't ask for what they can't imagine. This file collects the evidence
behind the revamp, then diagnoses where curiosity stands today against it.

---

## 1. Why people don't adopt

- **They judge on perception formed before real use.** The Technology Acceptance
  Model (Davis 1989): adoption = perceived usefulness × perceived ease. A user who
  can't imagine what the agent does *for their job* scores it useless regardless of
  capability. ([MIS Quarterly](https://misq.umn.edu/misq/article/13/3/319/191/Perceived-Usefulness-Perceived-Ease-of-Use-and))
- **The fear has a structure.** Rogers' Diffusion of Innovations: adoption speed
  hangs on *trialability* (can I try it cheaply and reversibly?) and *observability*
  (can I see results?). "Costs a lot / takes long / never works" is exactly low
  trialability + low observability.
- **People don't know what's possible — measurably.** HCI research shows users'
  mental models of AI capability are systematically misaligned with actual
  capability, and that misalignment — not capability — determines reliance.
  LLMs *look* walk-up-and-use, but users can't discover what to ask for.
  Microsoft's first human-AI guideline is literally "make clear what the system
  can do." ([IUI 2026 review](https://dl.acm.org/doi/10.1145/3742413.3789223))
- **One visible mistake is catastrophically expensive.** Algorithm aversion
  (Dietvorst, Simmons & Massey 2015): people abandon an algorithm after seeing the
  *same* error they'd forgive a human — even when it still outperforms. The 2018
  follow-up: letting people *slightly modify* the algorithm's output made them
  dramatically more willing to use it. **Control, even token control, cures
  aversion.** ([paper](https://marketing.wharton.upenn.edu/wp-content/uploads/2016/10/Dietvorst-Simmons-Massey-2014.pdf), [follow-up](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2466040))
- **Satisfaction is relative to expectation, not to output.** Expectation
  disconfirmation (Oliver 1980; Bhattacherjee 2001): continued use is driven by
  performance *versus what was promised*. Overpromising is a churn mechanism, not
  a sales tactic. ([ECT](https://en.wikipedia.org/wiki/Expectation_confirmation_theory))

**Design consequences:** teach possibility by concrete example on *their* case, not
a feature list; make the first steps tiny, cheap, reversible, visible; give an
edit/redirect affordance on everything; treat every stated expectation as a
contract we must land inside.

## 2. Hearing them out first

- **Reflective listening is the trust move, with outcome evidence.** Motivational
  interviewing (OARS): a higher ratio of *reflections* to questions predicts better
  outcomes; reflecting back builds the working alliance and lowers resistance.
  ([SAMHSA TIP 35](https://www.ncbi.nlm.nih.gov/books/NBK571068/))
- **Questions beat pitches — in 35,000 sales calls.** SPIN Selling (Rackham):
  top performers walk the buyer Situation → Problem → Implication → Need-payoff.
  Asking the right questions *is* the demonstration of competence; pitching first
  loses. ([summary](https://blog.hubspot.com/sales/spin-selling-the-ultimate-guide))
- **Interview for the job, not the features.** Jobs-to-be-done: dig for the
  progress the person is trying to make and the circumstance of the struggle. A
  mission is a JTBD statement — it deserves a JTBD interview.
- **Question count has a sweet spot.** One well-chosen clarifying question cut
  agent error rates ~27% in one study; but users complain far more about agents
  *acting on wrong assumptions* than about being asked. Never ask what you can
  discover yourself. ([active questioning](https://medium.com/@milesk_33/when-agents-learn-to-ask-active-questioning-in-agentic-ai-f9088e249cf7))

**Design consequences:** the first session is a short discovery interview — 2–3
sharp, non-inferable questions, each one teaching what's possible; then a
reflection back ("here's the problem as I understand it — did I get it right?")
that the human confirms. The reflection is not overhead; per the MI evidence it IS
the trust-building step.

## 3. Predictability before autonomy

- **Trust develops in a fixed order.** Muir (from Rempel): *predictability* ("I can
  anticipate what it will do") → *dependability* → *faith*. You cannot skip to
  faith. ([replication](https://www.tandfonline.com/doi/abs/10.1080/00140139.2021.1909752))
- **Trust must be calibrated, and process transparency calibrates it.** Lee & See
  (2004): trust rests on performance, *process*, and purpose; seeing how it works
  is what lets a human predict, and predict is what lets them delegate.
  ([paper](https://journals.sagepub.com/doi/10.1518/hfes.46.1.50_30392))
- **Showing the work increases perceived value.** Buell & Norton's labor illusion /
  operational transparency: users preferred *longer* waits when the effort was
  visible. Narrated work reads as effort-on-my-behalf; silent work reads as risk.
  ([paper](https://pubsonline.informs.org/doi/10.1287/mnsc.1110.1376))
- **Token anxiety is Dietvorst in disguise.** Money burned on an unwanted direction
  is a highly visible error — the exact trigger for abandonment. The industry's #1
  complaint class confirms it: Manus users losing $1200/day with no pre-run cost
  estimate, Devin's "ACU guessing game," no refunds on failed sessions.
  ([Manus reviews](https://uk.trustpilot.com/review/manus.im), [Devin review](https://easyclaw.com/blog/knowledge/devin-ai-review/))

**What products converged on (2024–26):** plan-before-run as a *hard gate*, not a
convention — Claude Code plan mode (writes blocked until approval), Devin's
interactive planning ("the most valuable checkpoint — you catch misunderstanding
cheaply"), Replit plan mode, deep research's editable plan. During runs: a ticking
step list + drill-in activity feed + artifacts as proof (Manus's computer view,
Devin's follow panel). Copilot data: previewing a draft before "apply" raised
acceptance 28%.

**Design consequences:** announce before spending — what, why, what you'll get,
rough cost; a veto window early, notification-only later; narrate during; deliver
artifacts as the progress indicator. Plans show *scope* ("what I will and won't
touch"), which is what catches misunderstanding cheaply.

## 4. Expectations in honest units

- **Any number stated first becomes the anchor** (Tversky & Kahneman). Say "4
  days" and you are scored against 4 days — even if the number was theater.
- **Calendar promises get disconfirmed by design.** Planning fallacy: humans
  anchor on best cases and miss; every missed date is a disconfirmation event
  (§1). A blocker-based estimate — *"done once I have Salesforce access"* —
  **cannot be missed**: it converts the wait into a shared dependency and names
  who holds the key.
- **AI speed breaks human duration priors — in both directions.** A 240-person
  latency study: *faster* AI answers were rated less thoughtful and less useful —
  speed reads as shallowness unless the artifact carries proof of depth (sources,
  steps). And work slower than chat-speed feels broken without visible progress.
  ([study](https://neurosciencenews.com/latency-perception-thoughtful-ai-30597/))
  So: never inflate an estimate to seem humanly plausible, and never deliver fast
  work without its evidence attached.
- **Time-to-value is the churn lever.** ~75% of SaaS users abandon within the
  first week without an early value moment. The first win must land in minutes.
- **The proven contract for long runs:** a time band up front ("5–30 min"),
  permission to walk away, notification on completion (deep research). For
  day/week-scale agents: blocker-based status boards ("waiting on your
  credentials"), not clocks. ([deep research](https://openai.com/index/introducing-deep-research/), [Slack agent governance](https://docs.slack.dev/ai/agent-governance/))

**Design consequences:** three kinds of horizon, each honest — **agent-time** in
minutes (true minutes), **human-unlocks** named by the key ("once Ads access
lands"), **real dates** only where a date is real (external deadline, weekly
rhythm). Under-promise; attach evidence of depth to fast work.

## 5. Adoption phases — the established ladders

- **Muir's trust stages**: predictability → dependability → faith — the
  observe → verify → delegate arc has 40 years of human-automation evidence.
- **Sheridan & Verplank's levels of automation**: a 10-level *dial* from "human
  does everything" through "computer suggests, human approves" to full autonomy;
  operators set the dial by trust vs self-confidence. The dial should be visible
  and per-task-type, not global.
- **Parasuraman & Riley**: miscalibrated trust produces both disuse and misuse;
  trust grows slowly, collapses on visible failure, recovers slowly. **After an
  error: drop that task-type one autonomy level and show the correction** —
  defending the output accelerates abandonment.
- Industry framing converged on the same thing: "progressive delegation" with a
  named middle tier as default (Claude Code auto mode, Cursor auto-review,
  Operator's confirm-consequential-actions).

**Design consequence:** the adoption arc (Hear → Reflect → Prove → Agree → Earn →
Own, [vision.md](./vision.md) §4) is Muir's ladder made legible to the human —
and it should be the primary thing the surface shows.

## 6. Anti-patterns with names attached

- **Silent spend on a misunderstood task** — Manus/Devin's #1 complaint; no
  pre-run estimate, charged for failures.
- **Acting on wrong assumptions** rather than asking the one question — "vague
  requirements produce results from mediocre to unusable" (Devin reviews).
- **Fake or self-narrated progress** — the Replit incident (agent deleted a prod
  DB, fabricated 4,000 fake users, faked test results) is the canonical trust
  cautionary tale. Status must be computed from ground truth, never from the
  model's self-narrative — curiosity's server-computed percents already follow
  this rule; keep it absolute.
- **Loop-without-escalation** — retrying a failing approach while the meter runs.
- **Question fatigue** is real but second-order; wrong-assumption damage is
  first-order.

---

## 7. Where curiosity stands today (diagnosis)

Against the evidence above, the current flow (mapped from `plugin_curiosity` 0.12.0):

| Evidence says | Curiosity today |
|---|---|
| Reflect back and confirm before running (§2) | **Explicitly banned.** `MISSION_GATE_FLOW`: "restating the mission back and asking 'did I get that right?' is the failure — save first." Mission saved verbatim; the reflect-back arrives *after* kickoff research, inside an 11-section artifact. |
| 2–3 sharp discovery questions (§2) | **Banned before save** ("do NOT ask for links, repos, docs, metrics…"); after save, the only question allowed is "what NAME do you want to give me." |
| Announce before spending (§3) | Kickoff fires ~3 s after `mission_set` — ~20 tool calls of research the human never previewed. Recurring runs (daily 09:00, nightly dream, heartbeats every 2–4 h) spend without a next-step preview. |
| Blocker-based, honest-unit expectations (§4) | The machinery half-exists: loops carry `unlock` + `human_cost`, asks must ride value. But kickoff **mandates 5–8 calendar-dated goals** on day one — maximal anchoring at the moment of least knowledge — and the JD mandates "in about a week" / "in 30 days" horizons in agent-chosen free text. |
| First win in minutes (§4) | Good: kickoff produces the brief + wiki stubs + first insight fast. But it's buried in an 11-section artifact — the win doesn't *read* as a win. |
| Visible autonomy dial, per-task (§5) | `rung` and `risk_ceiling` exist on the mission row but are never shown to the human; graduation (`phase_advance`) is a single global gate. |
| Ground-truth status (§6) | Good and worth protecting: percents are server-computed; agents forbidden to self-report numbers; `OWNER_WORDS` bans jargon. |
| Surface answers the adopter's questions | The pane shows agent internals (abilities, gap boards, heartbeats, revision stamps) — an admin dashboard, not an adoption journey. Roy's verdict: "lots of params, lots of text, very little clarity." |

The revamp, in one sentence: **keep the engine, invert the opening** — listen →
reflect → confirm → announce-then-run → expectations in honest units — and make the
surface show the journey instead of the machinery. The approach we lean on:
[ideas.md](./ideas.md) · mechanics: [considerations.md](./considerations.md).
