# Phase 9 — Role competency & work mode: setup → mastery, with durable follow-through

**Owner-observed problem (verbatim intent).** "The agent was engaged and took steps
to be proactive but then it stopped. It didn't try and find the right people, to get
my contact, to move forward. I am now blind into what it wants to do and it no
longer feels proactive."

**What the owner asked for:**
1. Goals **with timelines into the future** — the agent proposes what it thinks we
   should achieve and by when, sets them, then strives. Heavy goal-setting at the
   beginning, tapering to an ongoing cadence.
2. Two agent macro-phases:
   - **Phase One — setup for work.** Whatever role the mission implies, the agent
     draws the full picture of what that role means and sets itself up toward
     that end: people, communication paths, knowledge, tools, playbooks
     (authored AND validated) — everything needed to be proficient in the role.
     *Example:* if the mission is "manage the whole funnel", the role picture
     spans every funnel stage — traffic sources, landing pages, conversion,
     retention — and the setup covers who owns each stage, which systems hold
     the data, and what access/playbooks each stage needs. The funnel is only an
     example; the same applies to any role a mission implies.
   - **Phase Two — work mode.** Routine execution, and every cadence (day/week) a
     reflection report: what was done, insights, and suggestions to improve
     tools / playbooks / methods.
3. Phase One must run with **eagerness, follow-up, and durability** — the agent
   defines all the scopes of its role and persists dynamically through every step
   toward competency in the role; the work phase then drives toward mastery.
4. **The agent owns its own setup — and pays for it in value.** Setting up an
   agent to do a role is a delicate, hard task: the right tool access, the right
   data, the workflow contact/approval points with the human (possibly several
   approval people in a workflow), and the context + feedback loops needed for
   improvement. Today that is always the *human* setting up the agent. The agent
   must take that responsibility on itself: proactively define the complete
   setup, understand the complete goal with the human, and set out to do it —
   but choose a path that brings the human real value at **every single step**
   they take: every explanation they give, every question they answer, every
   tool they grant. Not *"to manage the funnel I need the AdWords connection —
   it takes 3 days and is very hard to get"* but *"I looked at the funnel with
   the tools I already have — I already see 3 areas to improve: SEO, page
   speed, user flow — I'd love to share them. And I can do more once I get the
   AdWords API connect."* Like hiring a talented new employee: they don't
   require you to set them up with everything first — you see they're smart,
   asking the right questions with the right enthusiasm from the interview
   onward, and that motivates you to hire them and then give them everything
   they need to be better. **They earn the setup, step by step.**
5. **Effort and time spent must grow with understanding and trust.** In the
   beginning the agent increments in small steps of value and time; as it gains
   more trust and understanding it can go after bigger, longer setups and
   actions. It is wrong that after the user's first line about the mission the
   agent launches a very long research project and builds a massive knowledge
   corpus — only for one answer later to shift that understanding dramatically
   and waste it all. Both the effort invested and the time between check-ins
   scale up as the real goal and purpose become clearer and trust is earned.

---

## 1. Evidence — tenant log diagnosis (vaselin-test-…-pluginsdk-9849753)

Tenant: https://luna.com.ai/a/vaselin-test-0-13-016-8-5-pluginsdk-9849753-2/p/wiki
Full 310-message dump read end-to-end (tenant Postgres via Fly → Render). Findings:

1. **No proactive machinery installed at all.** The tenant runs luna core 0.19.002
   with playbooks / interview / giphy / browser / files / web-access — **no
   plugin-curiosity, no plugin-wiki, no plugin-scheduler**. `agent_tasks` is empty.
   Nothing can fire without the user. (plugin-funnelfighters present but disabled.)
2. **Day-1 questions were never followed up.** Msg 30: the agent asked sharp scoping
   questions ("What does FunnelFighters do? Who are the customers?…"). The user
   never answered. The agent **never asked again** — not once in 17 days.
3. **All activity was user-pulled.** Message bursts only on days the user showed up
   (6/20, 6/24, 6/25, 6/27, 7/6); silence between. Every artifact (site-crawler
   playbook, SEO audit, fibonacci playbook, screenshots) was user-initiated.
4. **The agent asks, it doesn't propose.** Msg 160: "I'm ready to work — what do
   you need done?" — no plan, no goals, no timeline, no "here's what I'll do".
5. **Installs announced, never leveraged.** 7/6: GIPHY and Interview install
   moments (each duplicated); the log ends with the agent *describing* the
   interview module — no follow-through, no use of it toward the mission.
6. **Owner is blind.** The agent's intentions live only in chat scrollback. No
   goals page, no plan of record, no "what I'm doing next" surface.

The complaint maps 1:1: engagement was user-pulled; open questions rot; no goals or
timelines; no visible plan; no pursuit of people/contact paths.

**Deployment corollary (not a design item):** no plugin behavior can fix a tenant
that doesn't run the plugins. Shipping phase 9 must include getting
curiosity+wiki(+scheduler wiring) onto the hosted tenants — see §7.

## 2. Reflection — what phases 0–8 solved, and the gap that remains

What we built so far, honestly scored against "role competency":

| Capability | Phase | State |
|---|---|---|
| Knowledge substrate (wiki, citations, graph) | 1, 1.5 | ✅ strong |
| Mission adoption, same-turn, mission-first onboarding | 2, 6, 8.1 | ✅ strong |
| Research/reflect/dream cadences | 4, 5, 7 | ✅ fires in production |
| Goals with target dates + weekly scoreboard + Next move | 8.2 | ✅ shipped (0.6.0) |
| Capability-gap scan, outbound-reach ask | 8.2 | ✅ shipped (ask-only) |
| **Role definition** — what does this mission *mean* I must be able to do | — | ❌ missing |
| **Setup vs work phase distinction**; competency gate; mastery loop | — | ❌ missing |
| **Follow-up durability** — unanswered questions / promised actions chased | — | ❌ missing (the #1 observed failure) |
| **People & communication-path map** | — | ❌ missing (8.2 F covers owner reach only) |
| **Playbook authoring + validation as setup work** | — | ❌ missing (playbooks plugin exists; curiosity never drives it) |
| **Plan-of-record visibility** (owner never blind) | — | ⚠️ partial ([[mission-goals]] exists; no forward plan/timeline surface) |

Root lesson of 8.x, which phase 9 is built on: **structural mechanisms survive;
prompt-only enthusiasm decays.** "Be eager" prose produced one good day; the goal
ledger, triggers, and write-through mirrors kept working. So every phase 9 promise
(follow up, persist, report) gets a table, a trigger, or a gate — not an adjective.

**Future items from earlier phases — adopted / still deferred:**
- ADOPT (was "Out (later)" in high-level-plan §9): **rung-4 flavored work mode** —
  in work mode the agent drafts and executes *validated playbooks* through the
  existing approval gates. No PolicyResolver/risk_ceiling work; gates as-is.
- ADOPT (phase 3 note): differentiate proactive messages by **title**, not new
  `source` values (Setup report / Work report / Morning thought).
- ADOPT (8.2 F follow-through): connected-channel delivery for unseen reports —
  already in 0.6.0 rails; phase 9 makes the weekly report use it.
- DEFER unchanged: multiple missions, goal hierarchies/OKRs, spend receipts,
  news-spike webhook triggers, playbook-wrapped dream, autonomy-ladder
  enforcement changes.

---

## 3. Design

One law and seven mechanisms (A–G). A, B, C, G are structural (tables +
triggers + gates); D, E, F are prompt/cadence surgery on the 8.2 surfaces.
B carries the **setup arc** — the detailed shape of agent phase one.

**The talented-hire law (governs everything in setup):**
> **Never an ask without value already delivered, and every ask names its
> unlock.** The agent leads with what it can do *today* with the tools it
> already has; each thing it needs from the human is requested only after a
> visible win, in the canonical shape *"I did [value] with what I have —
> with [grant] I can additionally [unlock]."* Every step the human takes
> (answer, explanation, key, connection, approval) must pay them back
> immediately and visibly. Trust is the currency; value is how it's minted.

**The small-increments corollary:** the SIZE of each step obeys the same
economics as the asks. Early on, understanding is at its minimum and every
conclusion is provisional — so steps are small and cheap: a timeboxed research
pass, a one-page finding, a stub the owner can redirect. Big investments (a
deep knowledge corpus, a long build, an expensive setup) are made only after
the understanding they depend on has been *ratified* by the owner — never off
the first line of a mission statement. As ratified understanding and trust
accumulate, step size and the time between check-ins grow deliberately: short
leash first, longer leash earned. Practically: before charter ratification
(S2), no pass exceeds a shallow timebox; after ratification, depth is spent
only on scopes the owner confirmed; in work mode, long autonomous stretches
are the norm because the plan has survived contact with the owner.

This law and its corollary are enforced structurally (G) and by stage-gating
depth in the prompts — the 8.x lesson is that prompt-only enthusiasm decays.

### A. Agent phase state machine — `setup` → `work`
- `curiosity_phase` state (on the mission row or a 1-row table): `setup` | `work`,
  plus `entered_at`.
- **Setup** is entered at mission adoption (kickoff). **Work** is entered only by
  an explicit **graduation**: the agent proposes it in a weekly report ("all scopes
  competent — I'm ready to switch to work mode; say go"), the owner approves.
  A `phase_advance` tool (owner-approval-gated, not auto_approve) flips it.
- The mission prompt fragment becomes **phase-aware**: setup text drives role
  building; work text drives routine execution + improvement. One fragment, two
  branches — same pattern as the missionless/mission split today.
- Regression path: owner can say "back to setup" (`phase_advance(to="setup")`) —
  e.g. after a mission refinement widens the role.

### B. Role charter, competency map, and the SETUP ARC — the agent owns its setup

**Structural spine.** New table `curiosity_scopes` (id, kind, name, why, status:
`missing|in_progress|competent`, evidence, updated_at) + tools `scope_set`,
`scope_update`, `scope_list` (auto_approve — self-bookkeeping). Write-through to
`[[role-charter]]` like goals mirror to `[[mission-goals]]`. Scope kinds — the
full setup surface a human would normally have to design, now the agent's job:
- **knowledge** — domains I must understand (wiki coverage)
- **people** — stakeholders, decision makers, whose input unblocks me; per
  person: who/why/path to them (see E)
- **communication paths** — channels to the owner and the world (8.2 F reach
  check folds in here)
- **tools, data & access** — plugins/connectors/keys/data sources I need
  (8.2 C capability-gap scan folds in here), each with a human-cost estimate
- **workflow & approval points** — where the human(s) review/approve; who
  approves what when several people are involved; escalation path; check-in
  cadence and channel
- **playbooks** — the recurring work of the role, each AUTHORED and VALIDATED
  (see F)
- **routines & feedback loops** — triggers/cadences beyond the built-in three,
  and how each scope's quality gets measured so work mode can improve it

**Every scope must be covered by at least one goal with a target date** (D).
**Competency gate:** graduation (A) may only be proposed when every scope is
`competent` or the owner explicitly waives the stragglers.

**The setup arc — S0–S5.** The stages are an explicit ordered algorithm written
into the kickoff/daily/weekly prompts (8.1 learning: an explicit algorithm beats
generic prose; the model executes checklists faithfully). Only `setup|work` is
stored state (A); the current stage is visible at the top of `[[role-charter]]`
so the owner always knows where the agent is on its own runway.

- **S0 — Interview-grade first turn (the kickoff itself).** Prove understanding
  before asking for anything: restate the mission sharper than the owner said
  it; show 2-3 non-obvious observations about the domain from immediate
  research; ask ONLY the questions whose answers change the plan (each opens a
  loop, each states what it unblocks). Zero access asks in this turn.
  *Expectation: the kickoff reads like the candidate you decide to hire in the
  first ten minutes — smart questions, visible enthusiasm, no demands.*
- **S1 — Capability inventory & first value, BEFORE any ask.** "What can I do
  TODAY with what I already have?" Inventory the tools/plugins/data actually
  reachable now; run the first value pass on those alone; deliver 2-3 concrete,
  cited findings or artifacts within the first day(s). This is the AdWords
  example: funnel review with current tools first — SEO, page speed, user flow
  — the access ask comes after, riding the win. **Passes are small and
  timeboxed** (small-increments corollary): shallow, redirectable artifacts —
  no deep corpus building before the charter is ratified, because one answer
  at S2 can shift the whole picture.
  *Expectation: at least one `value_log` entry (G) exists before the first ask
  loop opens (structurally enforced, not requested), and pre-ratification
  wiki output stays stub/summary depth.*
- **S2 — Complete-goal alignment: charter ratification.** Draw the full picture
  and get the human to co-own it: `[[role-charter]]` with all scopes, the dated
  goal timeline (D), the proposed workflow/approval points, and the ordered
  access plan — cheapest-highest-unlock first, each item with its human-cost
  and its unlock. Close: "this is my complete understanding of the goal and my
  road to being great at it — push back now." Owner edits/ratifies in reply;
  disagreements become charter revisions, not silent drift.
  *Expectation: after this turn the owner can answer "what is my agent trying
  to become and by when" from one wiki page.*
- **S3 — Progressive capability acquisition: earn each grant.** Work the access
  plan one ask at a time (G caps open asks at ONE). Each ask in the canonical
  shape and riding delivered value. **The grant-payoff rule:** a granted tool /
  key / connection / answer MUST be used visibly by the next daily fire — post
  the result and log the value ("you connected X yesterday — here's the first
  thing it found"). A grant that sits unused destroys the trust that earned it;
  the unused-grant check is part of daily loop patrol (C).
  *Expectation: every human step is followed within ~24h by a visible payoff
  referencing that step.*
- **S4 — Workflow & approval-point validation.** Don't just document the
  workflow scope — run it: push one real item through the proposed approval
  path (a draft through the approver; a report through the check-in channel) and
  record the run in the charter. Multiple approvers: the charter names who
  approves what; the validation run exercises at least one non-owner approval
  point if one exists.
  *Expectation: the workflow scope reaches `competent` only via a validated
  live run, same bar as playbooks (F).*
- **S5 — Feedback-loop instrumentation.** For each scope, write down how
  improvement will be measured in work mode (what signal exists, what to
  instrument, where it's recorded — wiki page, playbook output, metric the
  owner supplies). This is what makes the work-mode reflection report (F)
  data-driven instead of vibes.
  *Expectation: the graduation proposal cites, per scope, the feedback signal
  work mode will use.*

The arc is a spiral, not a gantt: S1-value passes keep running throughout; S3
asks continue as long as the access plan has items. The stage marker tracks the
furthest *ratified* stage.

**The charter is a LIVING plan — replan forward, refix backward.** The setup
plan is drawn at the moment the agent knows the least (that is what planning at
the beginning means). Every material learning — a ratification answer, a grant's
first results, a validation run, a person met, a system discovered — triggers a
charter pass:
- **Replan forward:** re-derive the remaining scopes/goals/asks from what is now
  known. Drop what is no longer needed — a goal, a planned playbook, an access
  ask ("turns out I don't need the CRM key; the export covers it" —
  `goal_update(dropped)` / ask loop closed with the reason, visible). Add what
  wasn't known — a scope or access item that just became visible ("your answer
  revealed everything runs through HubSpot — I need a connection to it; added
  to the access plan"). New items enter the same dated-goal + ask-economics
  machinery as the originals.
- **Refix backward:** a later stage can invalidate earlier *completed* work —
  S4's workflow run can prove an S2 assumption wrong; a granted tool can show a
  wiki page or playbook built in week 1 was based on a false premise. Then the
  earlier output is REOPENED, not papered over: `scope_update` back to
  `in_progress` (competency is revocable), the artifact is corrected, and the
  fix is stated plainly ("I set up X wrong in week 1 — here's what I corrected
  and why"). Owning a misstep is part of earning trust, same as owning a win.
- **Structural support:** scope status transitions are unrestricted in both
  directions (`competent → in_progress` legal); goals/asks/loops already carry
  dropped/closed-with-reason paths; every charter pass appends a dated entry to
  a **Plan changes** section in `[[role-charter]]` (what was added, dropped,
  reopened, and the learning that caused it) — the owner watches the plan
  evolve instead of discovering drift.
- **Cadence:** the weekly setup report carries a **Plan changes** block (may be
  "none"); the daily prompt's rule is event-driven — "if today's learning
  changes the plan, change the plan today, not at the weekly."
Anti-pattern line in the prompt: "a plan that never changes after week 1 means
you stopped learning, not that you planned well."

### C. Open-loops ledger — the durability engine (fixes the #1 failure)
The tenant agent asked good questions once and never again. Never again:
- New table `curiosity_loops` (id, kind: `question|promise|waiting_on|handoff`,
  statement, who (owner|self|<person>), opened_at, next_nudge_at, nudge_count,
  status: `open|answered|closed|abandoned`, resolution).
- Tools `loop_open`, `loop_close`, `loop_list` (auto_approve). Prompt rule, all
  surfaces: **every question you ask the owner and every action you promise
  becomes a loop, in the same turn.**
- **The daily trigger's step 0 becomes loop patrol:** `loop_list` → any loop past
  `next_nudge_at` MUST be acted on before new research: re-ask (rephrased, with
  why it blocks which goal), try the connected channel if the platform went
  unseen, propose a default ("if I don't hear back by Friday I'll assume X and
  proceed"), or close it with an explicit assumption. Backoff ladder baked into
  the prompt: nudge at +2d, +5d, then weekly inside the review's **I need** slot —
  never silent abandonment; `abandoned` requires a stated reason the owner sees.
- Loops mirror into `[[open-loops]]` (write-through) so the owner sees exactly
  what the agent is waiting on and what it promised.
- Noise stays bounded: loop nudges ride the existing daily share (one message,
  loops section on top), not extra messages.

### D. Goals with timelines, front-loaded then tapering
Upgrades to the 8.2 ledger (no schema change; `target_date` exists):
- **Kickoff (setup):** 5–8 goals covering all scopes, each with a target date the
  agent proposes ("W1: …, W2: …, by <date>: …"). The artifact shows them as a
  **timeline**, not a list.
- **Overdue detection is structural:** daily trigger step includes "any goal past
  target_date and not done → confront TODAY: replan the date with a reason,
  escalate the blocker as a loop, or drop with a reason." Weekly scoreboard gets
  an **On time / late** column.
- **Taper:** in work mode the goal-setting instruction changes to rolling — keep
  2–3 active work goals, refill as they close; the big-batch language is
  setup-branch only. This is the owner's "first sets a lot, then ongoing."

### E. People & communication paths — "find the right people, get my contact"
- Kickoff + weekly: build/refresh `[[people]]` — the role's stakeholder map. For
  each: who they are, why they matter, current path to them (none / via owner /
  direct channel), and what's needed from them.
- Where a needed person has no path, that's a scope gap → a goal + a loop:
  **ask the owner for the intro/contact** ("to move goal 2 I need 15 minutes with
  whoever owns the ad account — who is that, and can you connect us?"). This is
  exactly the pursued-contact behavior the owner missed.
- Guardrail unchanged from 8.2 F: **no third-party outreach uninvited** — paths to
  people are requested through the owner; direct contact only on a channel the
  owner explicitly sanctioned for that person. Owner-only outbound stays the rule.

### F. Playbooks as setup deliverables; work mode runs and improves them
- Soft dep on plugin-playbooks (feature-detect like scheduler/marketplace tools;
  absent → scope kind `playbooks` degrades to documented procedures in the wiki).
- **Setup:** each recurring job in the role charter becomes a playbook goal:
  author it, then **validate** it — run it on a real-but-safe input, record the
  run + result in `[[playbook-validation]]`, mark the scope `competent` only after
  a passing validated run. (The tenant log shows validation is where playbooks
  actually get debugged — schema/loop errors surfaced only on runs.)
- **Work mode:** the routine IS the playbooks — daily/weekly triggers execute or
  advance them through existing approval gates (adopted rung-4 flavor). The
  weekly **reflection report** (owner's ask, verbatim): *what was done* (runs,
  outputs, goal movement), *insights*, and *suggestions to improve
  tools / playbooks / methods* — each suggestion concrete: a diff to a playbook,
  a trigger cadence change, a plugin to add, ending with **Next move**.
- Weekly report titles by phase (per phase-3 learning: differentiate by title):
  setup → **"Setup report — road to competency"** (scope scoreboard, loops,
  timeline, asks); work → **"Work report — week in review"** (reflection report).

### G. Ask economics + value log — the talented-hire law, enforced

The structural teeth behind "value on every single step":
- **Loops grow an `ask` kind** (C's table): fields `unlock` (what it enables —
  required), `human_cost` (the agent's honest estimate: a sentence, an OAuth
  click, 3 days of IT), `value_ref` (the value_log entry it rides on).
- **New table `curiosity_value_log`** (id, statement, evidence — wiki slug /
  artifact link, delivered_at, linked_ask_id nullable) + tool `value_log_add`
  (auto_approve). Mirror `[[value-log]]` — the running receipts of what the
  agent has produced for the human.
- **Enforced rules (in `loop_open`, not just prose):**
  1. At most ONE `ask` loop open at a time — the single **I need** slot
     becomes a hard invariant, not a style rule.
  2. Opening an `ask` requires ≥1 `value_log` entry newer than the last closed
     ask (S1's "value before any ask" for the first one). `loop_open` rejects
     otherwise with a message telling the agent to go deliver value first —
     the error itself steers the behavior mid-turn.
  3. `value_ref` is filled at open time: every ask names the win it rides on.
- **Artifact ordering rule (prompt, all surfaces):** value first, ask last.
  Kickoff, daily note, weekly report all present what was delivered before what
  is needed; anti-pattern line: "never open with a requirement."
- **Weekly scoreboard line:** *Value delivered vs asks made* (count + the list)
  — the owner literally watches the agent earn its setup.
- **Ask sequencing (prompt):** order the access plan by unlock-per-human-cost;
  a "3 days and very hard to get" item is scheduled late and big-win-funded,
  never the opening move.

### Owner-visible experience after phase 9
- mission_set → interview-grade kickoff: sharp restatement + first observations
  + the few questions that matter (as loops) — zero demands, day one.
- Day 1-2 → first value pass from existing tools only ("I already see 3 areas
  to improve — want them?"), then the charter: full role picture, scopes, dated
  goal timeline, workflow/approval points, ordered access plan. Ratify once.
- Daily → loop patrol first (nothing rots, grants get their payoff shown), then
  goal-driven work, one-line note — value first, at most one open ask.
- Weekly (setup) → competency scoreboard: scopes, timeline on-time/late, loops
  chased, value-vs-asks, ONE ask. Weekly (work) → reflection report with
  concrete improvement proposals.
- `[[role-charter]]` (with stage marker), `[[mission-goals]]`, `[[open-loops]]`,
  `[[people]]`, `[[value-log]]` — the owner sees what the agent wants to do and
  what it has earned at any moment. Never blind.
- Graduation is an event the owner approves; mastery loop begins.

---

## 4. Implementation phases

Each step is discrete and independently testable; each has its own detailed
plan in a subfolder (execution order 9A → 9E, each gated on the previous):

| Step | Plan | Deliverable | Testable by |
|------|------|-------------|-------------|
| **9A** | [phase9a-state-machine-and-scopes/](phase9a-state-machine-and-scopes/PLAN.md) | `setup\|work` phase state + stage marker; `curiosity_scopes` + tools; approval-gated `phase_advance` with competency gate; `[[role-charter]]` mirror + **Plan changes** log | unit tests + dev-Luna tool round-trips, no LLM behavior needed |
| **9B** | [phase9b-loops-asks-value/](phase9b-loops-asks-value/PLAN.md) | `curiosity_loops` (incl. `ask` kind) + `curiosity_value_log` + tools; ask-economics enforcement in `loop_open` (one ask; value-before-ask); nudge ladder; `[[open-loops]]`/`[[value-log]]` mirrors; daily loop-patrol splice | unit tests incl. rejection paths + dev-Luna round-trips |
| **9C** | [phase9c-prompt-surgery/](phase9c-prompt-surgery/PLAN.md) | setup arc S0–S5 as numbered procedures across kickoff/daily/weekly/fragment; phase-branched targets + titles; single-source law/ask-shape consts; people-map + playbook-validation instructions | prompt-content assertions per branch |
| **9D** | [phase9d-live-verification/](phase9d-live-verification/PLAN.md) | dojo walkthrough `curiosity-phase9/`: 11 behavioral checks (kickoff shape, earned first ask, enforcement visible, durability nudge, grant→payoff, replan/refix, S4 validation, graduation, work-mode report) mapped to the acceptance criteria | fresh-Luna walkthrough, green twice |
| **9E** | [phase9e-ship/](phase9e-ship/PLAN.md) | 0.7.0 three-stamp bump; publish + sha verify; upgrade e2e from the real artifact; tenant rollout; execution_summary.md | marketplace artifact + upgrade walkthrough |

### Acceptance criteria (implementation goals, measurable)
1. Before the first ask: ≥1 value_log entry, 0 open ask loops — enforced, not
   requested.
2. At no point: >1 open ask loop.
3. Every human step (answered loop / granted tool) has a payoff artifact within
   the next daily fire that references it.
4. Every scope: ≥1 dated goal; overdue goals confronted within one daily fire.
5. No question to the owner exists outside the loops table (spot-check in 9D
   transcripts).
6. Owner can reconstruct "what is it trying to become, by when, what does it
   need, what has it delivered" from wiki pages alone — no scrollback needed.
7. Graduation only through the gate + owner approval; work-mode weekly matches
   the reflection-report shape (done/insights/improvements/Next move).
8. The plan visibly evolves: every material learning produces a dated **Plan
   changes** entry (add/drop/reopen + cause) in `[[role-charter]]`; invalidated
   completed work is reopened and corrected, never papered over.
9. Effort scales with ratified understanding: before S2 ratification, research
   output is stub/summary depth (no page over a shallow-pass size, spot-checked
   in 9D transcripts); depth spending starts only on owner-confirmed scopes;
   check-in spacing grows over the arc, never shrinks the owner's early
   steering window.

## 5. Dependencies / interactions
- Hard: plugin-wiki (as today). Soft (feature-detect): scheduler, marketplace,
  playbooks, whatsapp/connectors.
- Builds directly on 8.2's ledger/review/reach — no rework, only branch + extend.
- No core changes anticipated. If graduation-approval UX needs a card, reuse the
  existing approval-gate surface (memory: approval gates park turns — dojo must
  approve via API).

## 6. Non-goals
- Autonomy-ladder / PolicyResolver enforcement changes; approval gates as-is.
- Multiple missions; OKR hierarchies; spend receipts; news-spike triggers;
  third-party outreach.
- Onboarding-flow changes (8.1 primacy already owns that seam).

## 7. Ship-to-tenant note (outside plugin scope, required for the owner to feel it)
The observed tenant has none of this machinery. After 9E: upgrade the hosted
tenant image to a core ≥0.33.001 (prompt.assemble hook) and install
plugin-wiki + plugin-curiosity 0.7.0 (+ scheduler relay wiring, already
production-verified in phase 8). The 8.1 no-restart kickoff makes the install
itself the first proactive moment.

## 8. Risks
- **Prompt bloat:** three new instruction blocks ride existing surfaces; keep each
  under ~10 lines; phase-branching halves what's active at any time.
- **Loop-nudge noise:** bounded — nudges ride the single daily note; ladder maxes
  at weekly; owner can close any loop with one sentence.
- **Over-eager scoping:** a grandiose role charter → cap scopes (≤8) and goals
  (≤8) in the kickoff prompt; owner ratifies the charter in the kickoff reply.
- **Graduation stall:** if the owner never approves, setup mode still does real
  work (goals advance); the weekly re-proposes at most once per report.
- **Prompt-only compliance decay:** the load-bearing pieces (state, scopes, loops,
  dates, asks, value log, triggers) are tables and cron — they survive weak turns
  (8.x lesson).
- **Value-first can delay genuinely blocking access:** if truly nothing useful is
  possible without a grant, S1 still produces value from public research (the
  wiki always works); the exception is explicit in the prompt — a blocking ask
  may come early ONLY with the plan of what happens the hour after it's granted.
- **Gaming the value gate** (logging trivia as value to unlock an ask): value_log
  entries require evidence refs and appear verbatim in `[[value-log]]` and the
  weekly scoreboard — the owner sees exactly what was claimed; cheap entries
  embarrass the agent in front of the person it's trying to impress, and the
  weekly prompt says so.
