# Curiosity Vision — Revision 2: Adoption-First Onboarding

> The original [vision](../../vision.md) still stands: mission → curiosity → shared
> understanding → earned trust → setup → execute. This revision changes ONE thing:
> the onboarding is redesigned around how **humans adopt**, not around how fast the
> agent can start working.

---

## 1. What we got wrong

The original vision optimizes Luna's first hour: get the mission, kick off, research,
produce a brief, build wiki pages. The agent starts strong — and the human is left
behind at three points:

1. **We never really heard them.** Luna asks for a mission, gets one sentence, and
   runs. The human never felt *listened to*. They gave a compressed guess at what
   they want, watched the agent sprint off with it, and now carry a quiet worry:
   "is it even solving my problem?"

2. **They can't predict her.** Luna decides on her own what to research next. The
   human watches tokens burn for five minutes with no idea what's being bought.
   Even when the output is good, the *experience* is a slot machine: pull the
   lever, hope it was worth it.

3. **Expectations are set in the wrong units.** Goals carry calendar dates copied
   from human work rhythms. An agent that says "landing-page audit — 4 days" is
   lying twice: the audit takes her 20 minutes, and the real gap is that she's
   waiting for analytics access. Humans then anchor on the wrong thing, and both
   fast delivery ("why did it say 4 days?") and slow delivery ("it's late") damage
   trust.

None of these are technology gaps. They are adoption gaps.

---

## 2. The human we are onboarding

The person adopting Luna is not a prompt engineer evaluating capabilities. They are
someone with a job to run, who:

- **Doesn't know what's possible.** Even with decades-old tech, most people never
  knew what it could do for them. They cannot ask for what they cannot imagine —
  so "tell me your mission" is a question they are not equipped to answer well.
- **Is afraid, concretely.** The fear has a shape: *it will cost a lot, it will
  take a lot of my time, and it will never actually work.* Every AI tool they
  half-tried before confirmed it.
- **Prices risk per person, not per market.** Each human runs this calculation
  alone, about their own money, their own hours, their own reputation. Adoption
  is won one person at a time.
- **Judges by feel before results.** Long before the first deliverable, they've
  already decided whether Luna "gets it" — from whether she listened, asked the
  right questions, and reflected their problem back better than they said it.

The research behind these claims — algorithm aversion, calibrated trust,
operational transparency, expectation disconfirmation — is in
[research.md](./research.md).

---

## 3. The three onboarding laws

### Law 1 — Hear them out before doing anything

The first minutes belong to the human, not the agent. Luna's opening move is an
**intake conversation**, not a kickoff:

- **Listen first.** Let them talk about the problem in their words — the business,
  the pain, what they've tried, what failed. Short, warm, zero forms.
- **Ask the right questions — few and sharp.** Two or three questions that only
  someone who understood the problem would ask. Each question teaches the human
  something about what's possible ("do you know which of your events actually
  predicts payment?" both asks and shows).
- **Reflect back before running.** Luna restates the problem, the goal, and what
  success looks like — *better than the human said it* — and asks "did I get
  this right?" The mission is **confirmed**, not received. This is the moment the
  human decides Luna wants to solve *their* problem, not run a generic playbook.
- **Show what's possible on their case.** Not a feature list — one or two
  concrete "here's what I could do for you" examples grounded in what they just
  said. Possibility education, one person at a time.

The mission statement stops being an input and becomes the **output of a
conversation** — which the original vision already says about mission clarity
(§8: "mission clarity is the OUTPUT, not the input"). We now apply it to minute
zero, not just to the long arc.

### Law 2 — Never run unannounced

The human must always be able to answer: *what is she doing right now, why, and
what will I get out of it?* Before any self-directed spend, Luna posts a
**next-step card**:

- **What** — one line: "Audit your two live landing pages against best practice."
- **Why** — one line, tied to the confirmed mission.
- **You'll get** — the artifact: "a ranked list of fixes in the wiki + a 5-line
  summary in chat."
- **Costs about** — honest scale: "~4 minutes, a few cents." Rough is fine;
  silent is not.

Early on, next steps wait briefly for a veto/redirect ("go" is one tap; silence
is consent after the first trust rungs). Later, cards post as she starts — the
predictability stays, the friction goes. The rule never expires: **no token is
spent that the human couldn't have seen coming.** This kills the slot-machine
feeling: work becomes a sequence of small, named purchases the human watched
themselves approve.

### Law 3 — Expectations in honest units

Expectation setting is the product. Humans decide "this works / this will never
work" against expectations, not against absolute output. So Luna sets them
deliberately — and in the **right units**:

- **Blockers are named by their unlock, not by a date.** "Ready once I have
  Salesforce access" — not "4 days." The date was never the truth; the credential
  was. The human sees exactly what the wait is made of and that *they* hold the
  key.
- **Agent-time is stated honestly.** What takes her 20 minutes is promised in
  minutes, even if a human agency quotes two weeks for it. Never inflate to seem
  humanly plausible — surprising speed builds trust; theatrical estimates
  destroy it.
- **Human-time is respected.** Steps that need the human (approvals, access,
  answers) are the slow lane — flagged as such, batched, never nagging.
- **The job is spread over legible horizons.** "In the next 10 minutes / after
  you approve the brief / once access lands / by Friday's review" — a mixed
  timeline of time-based and unlock-based milestones. Real dates only where a
  date is real (an external deadline, a weekly rhythm).
- **Under-promise, then land early.** Every kept expectation is a trust deposit;
  every missed one costs ten deposits. Estimates carry the honest range, not the
  optimistic edge.

---

## 4. The adoption arc

Onboarding is a staircase the *human* climbs; Luna's job is to make each step
feel safe and obviously worth it. This is the front half of the original Phase
One, now made explicit and **shown to the human as the primary UI**:

| Step | The human's inner state | What Luna does | Exit condition |
|---|---|---|---|
| **1 · Hear** | "Will it even understand me?" | Listens, asks 2–3 sharp questions | Human has said the problem in their own words |
| **2 · Reflect** | "Does it want to solve MY problem?" | Mirrors back problem + goal + success picture | Human confirms: "yes, that's it" |
| **3 · Prove** | "Will this ever actually work?" | One quick win in minutes, zero setup, announced first | Human received something they'd have paid for |
| **4 · Agree** | "What am I signing up for?" | Proposes the plan with honest-unit expectations | Human approves the expectation timeline |
| **5 · Earn** | "How much rope do I give it?" | Setup ladder — every ask rides a delivered win | Graduation (per original vision §8) |
| **6 · Own** | "It runs; I steer." | Work mode, rolling goals, weekly reflection | Ongoing |

Steps 1–4 should fit in the first session — minutes, not days. The staircase is
also the vocabulary of the surface: the human always sees which step they're on,
what it exists to answer, and what unlocks the next one.

---

## 5. The surface: from dashboard to journey

Today's Missions pane is an admin dashboard: many panels, many parameters, agent
vocabulary (abilities, heartbeats, gap boards). It reports Luna's internals
instead of answering the adopter's three questions:

1. **Does she get what I want?** → the confirmed mission, reflected back, on top.
2. **What is she doing right now, and what's next?** → the next-step card and a
   short "what you got so far" trail.
3. **What happens when — and what's it waiting on?** → the expectation timeline
   in honest units, with blockers named by their unlock and marked "yours"/"hers."

Everything else — abilities, heartbeat mechanics, gap boards, revision stamps —
is depth behind a click, or lives in the operational tab for the rare user who
wants machinery. The redesign follows [ux_guidelines](../../../../vision/ux_guidelines.md)
strictly: one grammar, bottom line first, few words. See [mock.html](./mock.html).

---

## 6. What success looks like (additions to the original list)

- A first-time user's opening session is a **conversation**, and ends with them
  reading their own problem stated back better than they said it.
- The human can always say, unprompted, what Luna is doing *right now* and what
  it will produce. Zero "what is it burning tokens on?" moments.
- No calendar promise exists anywhere that a human duration prior generated.
  Every wait names its unlock; every estimate is honest to agent speed.
- The Missions surface answers the three adopter questions above the fold, in
  words a first-time user understands, with fewer than six visible sections.
- Measured: time-to-confirmed-mission (minutes), time-to-first-win (minutes),
  and the rate of humans who climb from step 3 to step 5 — the adoption funnel
  itself becomes the metric.
