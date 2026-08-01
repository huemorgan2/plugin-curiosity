# Phase 10 — The FDE phase: generalized job setup + the Missions pane rebuilt

**Goal:** two halves of one idea.

1. **Generalize setup.** For EVERY possible mission the owner gives, Luna runs a
   complete adoption process on herself — learn about the job, write her own job
   description, decompose the role into abilities, plan dated goals, propose how
   things should work, and set herself up. We are replacing the team of FDEs
   (forward-deployed engineers) that normally adopts an agent into a role — and
   giving the agent that job. Today the *doctrine* exists (vision §8, S0–S5,
   scopes, heartbeat); what's missing is the **job-shaped data model** the owner
   actually thinks in: job description, abilities with completion %, goals with
   expected results.
2. **Rebuild the Missions pane** around that model, per Roy's 2026-07-11 review
   ("so many words so little meaning") and the recovered 12:10 spec: four
   confidence-building sections in strict order, everything else out to a NOC
   view. Full compliance with `/vision/ux_guidelines.md` (read it first — §§1–7).

**Version:** plugin-curiosity **0.9.0**.

**Owner's one-line test:** a first-time user opens Missions and understands
from what's visible alone: *what the agent is on, how it will do the job, how
far setup is, and what will happen when.* Confidence, not telemetry. Tooltips
stay — behind `(i)` affordances, for gradual discovery of optional depth
("how is this % computed?") — never as the way a section gets understood.

---

## 1. Why the current model falls short of "replace the FDEs"

What an FDE team actually produces when adopting an agent into a role:

| FDE deliverable | Curiosity today | Gap |
|---|---|---|
| Job description ("here is what the agent will do") | scattered: [[role-charter]] free prose | no forced shape → pane can't render it, owner never sees a crisp JD |
| Capability plan ("the abilities this role requires, and their build-out state") | `curiosity_scopes` — flat, 7 kinds, status per scope | no grouping into owner-legible *abilities*, no per-ability % — the gap board reads as internal bookkeeping |
| Rollout timeline ("by week 2 you can expect…") | `curiosity_goals` (statement, target_date, status) | no *expected result* ("what you will observably see"), no have/missing readiness, no timeline visual |
| Working agreement (how approvals, contacts, escalation work) | implicit in scopes/loops | agent never *proposes the design* as a first-class artifact |
| Onboarding status report | stage ladder S0–S5 | S-codes are internal jargon; % math is stage-weighted, not ability-weighted |

Everything below generalizes by one rule: **the framework owns the SHAPE, the
agent derives the CONTENT from the mission.** No mission-specific anything in
code — FunnelFighters is only ever an example in a prompt.

---

## 2. The generalized job model (data + contracts)

### 2A. Job description — `[[job-description]]`, prompt-forced shape

New wiki page in the fixed shelf set, authored at kickoff, revised on plan
changes. Shape contract (`JOB_DESCRIPTION_SHAPE` in `prompts.py`, same
mechanism as `SUCCESS_TABLE_SHAPE`) — the page MUST contain four headed
sections, each renderable (the fourth, `## Working assumptions`, is defined
with the discovery loop in 2D):

1. `## How I will accomplish this mission` — 3–6 one-line bullets, plain words
   ("to accomplish the mission I will …"). A short paragraph max.
2. `## After onboarding` — opens with a horizon the agent picks and states
   ("once setup is complete — about <N days/weeks>"), then NUMBERED bullets of
   what the agent will do in its role, each an observable behavior.
3. `## In 30 days` — numbered bullets of what the owner can expect once the
   agent has learned and self-improved ("after I learn and improve myself,
   expect: …").

Free prose is welcome around the sections; only the three headers + bullets
are load-bearing (the pane parses exactly these). Kickoff drafts it; the
S3 ratification now covers charter + success-criteria **+ job description**;
dream/review keep it current (a JD that never changes past week one is a
plan-is-alive violation).

### 2B. Ability ladder — the 2-level setup hierarchy with %

New tables (additive migration):

- `curiosity_abilities` — id, mission_id, title ("Ability to contact all
  Funnel-Fighter users and help them"), why (one line: which part of the JD it
  serves), sort_order, status (`building | ready | degraded`), created_at.
- `curiosity_ability_tasks` — id, ability_id, title (one line), status
  (`done | in_progress | missing | blocked`), note (one line, e.g. "missing
  Matan"), evidence_ref (optional [[value-log]] cite), sort_order.

Rules:

- **Derivation is the agent's job** (`ABILITY_CONTRACT` in `prompts.py`):
  at kickoff, decompose the role into **3–7 abilities** — each phrased as
  "Ability to <do something the owner cares about>" — and each into 2–6
  concrete subtasks. Every scope (`curiosity_scopes`) gets an `ability_id`
  FK (nullable for migration): the gap board becomes the *internal* view,
  abilities the *owner* view of the same reality.
- **% is computed, never asserted:** ability % = done subtasks / total
  (in_progress counts 0.5). **Setup completion % = mean of ability
  percents.** This REPLACES the stage-weighted % on the pane; the S0–S5
  ladder stays as internal machinery (stage gates, ratification forcing)
  but no S-code ever renders in the UI again (ux_guidelines §4).
- **Heartbeat maintains it:** `HEARTBEAT_CONTRACT` gains one clause — every
  fire re-scores ability tasks against current state (new tool calls:
  `ability_task_set`), and a new gap discovered mid-setup MUST land as a
  subtask under an ability (or a new ability, with a plan-change note).
  Convergence criterion is unchanged but now cites ability %.
- Tools (auto-approve, mirroring scope tools): `ability_upsert`,
  `ability_task_set`, `ability_list` (returns computed percents — agents
  don't do arithmetic).
- **Upgrade path:** on first load at 0.9.0 with an active mission and zero
  abilities, register a one-shot nudge (existing muted-message mechanism)
  telling the agent to derive abilities from the existing scope ledger in
  its next heartbeat. No data migration beyond the nullable FK.

### 2C. Goals — expected result + readiness + the next-2-3 rule

`curiosity_goals` gains columns (additive): `expected_result` (one short line
— "what you can expect to observably see when this lands"), `readiness`
(`green | amber | red` — do we have what this goal needs?), `readiness_note`
(one line: what we have / what's missing). `GOAL_CONTRACT` addition:

- Goals are **dated and horizon-spread** — days, weeks, months; the agent
  decides the dates (heavy at setup start, rolling later — vision §8).
- Only the **next 2–3 goals** carry expected_result + readiness detail. A
  goal many steps away is a dot on the timeline, nothing more — do not
  explain it at all.
- Readiness is re-scored on every heartbeat and review (it is the goal-level
  rollup of ability/scope state).

### 2D. Gradual role discovery — draft, learn, revise

**The role is discovered, not specified.** Everything in 2A–2C ships instantly
as a DRAFT and is expected to change. One loop, repeated for the life of the
mission:

> **deliver value → surface one learning → (at most) one question → revise → next step.**

Contracts (single-sourced in `prompts.py`):

1. **Draft-first, fast.** JD v1, abilities v1, goals v1 all land in the
   kickoff turn — shallow, cheap, labeled "first draft — sharpens as I
   learn." Never a long silent thinking session before the owner sees
   anything (vision principle 2).
2. **Working assumptions are explicit.** [[job-description]] gains a forced
   fourth block: `## Working assumptions` — one line per assumption, each
   stating it AND how it gets checked ("assuming ~5–10 hands-on customers —
   verifying against real signup volume"). The heartbeat re-checks
   assumptions against current knowledge every fire. A broken assumption is
   a *discovery*, never an error.
3. **Verify yourself before asking** (`VALUE_QUESTION_CADENCE`). Every
   proactive share ends with at most ONE question — the one that solidifies
   the highest-leverage uncertainty. Never ask what the agent can check
   itself (the site, the data, the wiki) — the owner may not know either;
   the signup form she finds on the website can teach more than an
   interview. Questionnaires are banned.
4. **Materiality rule.** A learning *within* one ability → revise directly,
   log a plan change (`kind=refine`) — visible in the NOC, no owner action.
   A learning that changes the role's *shape* (ability added/dropped, JD
   block rewritten, goals re-dated) → a **role pivot**: post
   "what I discovered → what changes → what I need from you", log
   `kind=role_pivot`, open a loop for the owner's input, and refresh
   ratification of the changed artifact only (not the whole charter).
5. **No blame.** Pivots are the learning process of agent AND human —
   "same job, different context." Never apologize; show the discovery and
   the improved plan.

Canonical examples baked into the contract (as illustrations — the rule is
mission-agnostic): *"onboard customers to FunnelFighters"* drafted for 5–10
hands-on customers, until the agent reads the site, finds self-signup at
~100/day, and pivots communication, detail-capture, and follow-up — owner
input requested. *"Build my website for X"* — mid-work discovery that it's
an e-commerce site → abilities and goals rethought.

Data (additive): `curiosity_plan_changes.kind` gains `refine | role_pivot`;
`curiosity_missions` gains `role_version`, incremented per pivot.

### 2E. The FDE doctrine — prompt generalization

`PHASE_ONE_DOCTRINE` is extended (one paragraph, single-sourced): *you are
the forward-deployed engineer of your own adoption.* Three duties added to
the driving questions:

1. **Learn the job itself** — research how this role is done well in the
   world (not just the domain): its workflows, tools, failure modes,
   benchmarks. The role, derived from the mission, is a research subject.
2. **Suggest how things should work** — propose the working design to the
   owner as part of the charter: contact/approval points, who to talk to,
   what data flows where, escalation, cadence. The owner ratifies a
   *design*, not just a mission restatement.
3. **Set yourself up** — drive every ability from missing → ready with the
   talented-hire law unchanged (value before asks, every ask names its
   unlock).

Kickoff procedure is re-ordered accordingly: restate mission → research the
ROLE → draft [[job-description]] (2A) → derive abilities (2B) → charter
scopes under abilities → dated goals with readiness (2C) → post for
ratification → author heartbeat. Dojo must verify this works for an
arbitrary, never-seen mission (we test with a non-FunnelFighters mission on
purpose — e.g. "grow a ceramics studio's instagram into a sales channel").

---

## 3. Missions pane — rebuilt (the recovered 12:10 spec)

Read `/vision/ux_guidelines.md` first; every section uses eyebrow →
bottom-line headline → one-line bullets → expand. Wide padding, few panels,
no hover-only meaning, zero jargon. **Four sections, this order:**

### 3.1 ACTIVE MISSION
Keep the hero (one gradient). Eyebrow `ACTIVE MISSION`, headline = the
mission statement, support line = agent's one-line restatement in its own
words (from [[mission]]) — reflects back that the agent is ON it. Phase
shown in plain words: `Onboarding — setting myself up` / `Working the
mission`. Morale line stays (it earned its place); autonomy/risk chips move
to the NOC.

### 3.2 JOB DESCRIPTION  *(new — the missing section)*
Renders the blocks of [[job-description]] verbatim:
- eyebrow `JOB DESCRIPTION`, headline = the mission-method one-liner;
- support line = the living-draft stamp: `draft v3 · revised Jul 11 — found
  self-signup on your site` (`role_version` + latest role-shape plan change);
- `How I will accomplish this` — the 3–6 bullets;
- `After onboarding (~2 weeks)` — numbered, observable behaviors;
- `In 30 days` — numbered expectations;
- `Working assumptions` — one-line bullets, each with a check-status dot
  (verified ● / checking ◐ / broken → shown as the discovery that revises it).
Each block collapsed to its bullets; no paragraph walls. Full revision
history lives in the NOC activity stream, not here. If the page or a section
is missing → honest empty state ("I haven't written my job description yet —
it lands with kickoff").

### 3.3 SETUP COMPLETION X%
- Eyebrow `SETUP`, headline = **X% complete** with the progress ring (the
  one praised element — keep it), support line `we are in the onboarding
  phase`.
- Below: the **2-level ability hierarchy** — one row per ability: bold
  one-line title + its own thin % bar + % number; expand → its subtasks as
  one-line bullets with status dots (done ● / in progress ◐ / missing ○ /
  blocked, red) and their one-line notes.
- No S-codes anywhere. The internal stage gate surfaces only as at most one
  plain-words line inside "Needs from you" (e.g. "Waiting on you to approve
  my job description").

### 3.4 GOALS
- Eyebrow `GOALS`, headline = next goal + date ("20 listings — Jul 14").
- **Timeline visual:** a horizontal line spanning the goal horizon; a dot
  per dated goal; each dot carries a bubble with ONE word + one number
  ("listings · 20", "revenue · 2k"). Past dots green/red by outcome.
- Below, a numbered list: next 2–3 goals only, each exactly two lines —
  (1) one short line stating the goal as a **required result** ("what you
  will see happen"); (2) readiness in colored text (green = have what we
  need / amber = partial / red = missing X) from `readiness_note`. Farther
  goals appear as dots only, no explanation at all.

**Kept, minimized:** "Needs from you" (it IS confidence-critical — the
agent is never silently stuck) as a slim strip under the hero, one line per
open ask, deep-link to chat. A **role pivot** renders here as its own card:
"Big change: hands-on → multi-user onboarding. Here's why — weigh in." **Everything else leaves this pane** (§4).

Empty/blocked states keep 9.002 behavior, rewritten to the new grammar.

## 4. The NOC pane — where the machinery lives

Roy: "HEARTBEAT / activity / knowledge — the state of the agent — all live
actions should be in the NOC dashboard, not here." So: second sidebar
section from the same plugin (`sidebar_sections` gains
`{id:"noc", label:"NOC", icon:"activity", sort_order:46}`), same static-app
pattern, `/ui/noc/`:

- **Role wall** (9.002 §6 tiles + incident strip — work phase hero here now),
- **Heartbeat** (pulse, streak, history, live bridge beat),
- **Activity stream** (merged timeline),
- **Knowledge shelf** (wiki cards),
- **What happens next** (trigger fires + loop nudges),
- autonomy + risk chips, pace band, past-missions shelf.

Same tokens, same grammar, denser by design — a control room is allowed
density, the Missions pane is not. Overview API serves both (one payload,
two views); live-bridge events unchanged.

---

## 5. API + parsing changes

- `GET /missions/overview` gains: `job_description` (parsed 4-block
  structure + raw + `role_version` + latest role-shape change line),
  `abilities[]` (with computed percents + tasks), `setup_percent`
  (ability-mean), goals gain `expected_result`, `readiness`,
  `readiness_note`; pivots surface in `needs_from_you`; response keeps all
  9.002 fields (NOC needs them).
- Parser: job-description block parser next to the success-table parser —
  headers + bullets only, everything else ignored. Malformed page → serve
  raw + `shape_ok:false`; the weekly review already audits shape drift, add
  JD + readiness to that audit.
- All computed numbers server-side (`ability % / setup % / timeline
  positions`) — agents have no clock and do no math.

## 6. Companion upgrades — plugin-wiki & plugin-scheduler

Phase 10 as specced changes neither. But both carry generic gaps that force
curiosity into workarounds; closing them makes each plugin better *on its own
terms* — nothing curiosity-specific leaks in. Each ships as its own version
with its own tests; curiosity **feature-detects** (marketplace index lists
latest only, so min-version pins are fragile) and keeps its fallback path.

### plugin-wiki (generic: structure + history)

0. **Multi-wiki (already underway — owner's separate change):** wiki gains
   multiple isolated wikis, each with a name + a description the dream keeps
   summarized. Curiosity adopts it: **one wiki per mission** — adoption
   creates/binds a wiki named for the mission; the fixed page shelf
   ([[job-description]], [[success-criteria]], …) lives inside it; a
   re-mission archives the old wiki whole (mission history keeps its wiki, a
   far better archive than orphaned pages in one global namespace). Needs
   from wiki: provider reads scoped by wiki (`get(page, wiki=…)`), and
   curiosity stores the bound wiki id on the mission row. Pane deep-links
   scope to the mission's wiki.
1. **Section/table extraction in the provider** — `get_section(page, header)`
   and `get_table(page, header)` returning parsed rows/bullets. Today
   curiosity hand-parses raw markdown for [[success-criteria]] and (in this
   phase) [[job-description]]; any pane-rendering plugin will want this.
   Curiosity's parsers become thin wrappers; fallback: current bespoke
   parsing.
2. **Page revisions** — `wiki_write` records (ts, one-line reason); provider
   exposes `revisions(page)`. Generically valuable ("watch the agent's
   understanding evolve") and powers the JD living-draft stamp
   ("draft v3 · revised Jul 11 — found self-signup") from real history
   instead of only `role_version` + plan-change joins.

### plugin-scheduler (generic: idempotency + provenance)

1. **Named-unique triggers** — `trigger_create(..., unique_name=…)` does a
   server-side upsert. Kills the heartbeat-duplicate TOCTOU class **at the
   source** (0.8.1's reaper was a workaround; it stays as defense in depth).
   Any plugin authoring named cadences wants exactly this — prompt
   discipline is probabilistic across concurrent turns, invariants belong in
   code.
2. **Trigger provenance** — `created_by` (plugin/turn) + a free `purpose`
   label, surfaced in `trigger_list`. The NOC's "what happens next" then
   shows honest machinery for every trigger, not just ones whose names it
   recognizes.

Sequencing: these are two small independent plans (wiki first — C's parser
prefers it), landable before or in parallel with phase 10; phase 10 does not
block on them.

## 7. Docs + guidelines

- `vision/ux_guidelines.md`: calm-surfaces rule (§6) — **already applied**
  with this plan (no hover-only meaning, wide padding, precise wording).
- `research/luna-curiosity/vision.md` §8: one paragraph on the FDE framing —
  the agent as its own forward-deployed engineer; job description +
  abilities as the legible artifacts of phase one.
- Workspace vision folder: already present in `luna-plugins.code-workspace`
  — no action.

---

## 8. Work plan

Execution is split into three shippable sub-phases (detail lives there):

| sub-phase | ships | scope |
|---|---|---|
| [10.001-job-model](./10.001-job-model/PLAN.md) | curiosity 0.9.0 | data, tools, contracts, discovery loop, overview v2 (rows A–C) |
| [10.002-panes](./10.002-panes/PLAN.md) | curiosity 0.9.1 | Missions rebuild + NOC split, guidelines pass, prod e2e (rows D–E) |
| [10.003-companions](./10.003-companions/PLAN.md) | wiki +1, scheduler +1, curiosity 0.9.2 | §6 upgrades + feature-detected adoption (parallel/optional) |

The row table below is the phase-level summary:

| step | what | tests |
|---|---|---|
| **A. Data + tools** | `curiosity_abilities` + `curiosity_ability_tasks`, scope `ability_id` FK, goal columns; `plan_changes.kind` (`refine`/`role_pivot`), `missions.role_version`, `missions.wiki_id` (nullable — bound when multi-wiki ships, §6); `ability_upsert` / `ability_task_set` / `ability_list`; % math server-side | unit: % math (0.5 in-progress), rollup, role_version bump, migration idempotence |
| **B. Contracts** | `JOB_DESCRIPTION_SHAPE` (4 blocks incl. working assumptions), `ABILITY_CONTRACT`, goal readiness + next-2-3 rule, FDE doctrine extension, **discovery loop: `VALUE_QUESTION_CADENCE` + materiality rule + no-blame framing (2D)**, kickoff re-order, heartbeat re-scores abilities AND assumptions, ratification covers JD (pivot → re-ratify changed artifact only), review audits shapes; upgrade nudge (derive abilities from existing scopes) | unit: contract text present on every surface (prompt-primacy suite pattern), single-sourcing |
| **C. Overview v2** | JD parser, abilities payload, setup %, goal fields; `shape_ok` fallbacks | unit against fake registries: parse, malformed page, empty states |
| **D. Missions pane rebuild** | 4 sections per §3, ability hierarchy, goal timeline visual, needs-strip; delete heartbeat/activity/wiki/next/NOC panels from this view; ux_guidelines checklist pass | visual pass against guidelines checklist (enforcement §) |
| **E. NOC pane** | second sidebar section + `/ui/noc/`, panels moved, live bridge on both | dojo asserts both registered + served |
| **F. Verify + ship** | full unit suite; **local dojo** (fresh Luna + local scheduler, a NON-funnel mission): kickoff → JD page with 4 blocks → abilities derived with % → goals with readiness → overview contract → pane renders 4 sections, zero `S\d` strings in served HTML/JSON labels → NOC has the moved panels → heartbeat re-scores a task → **discovery leg: plant a fact that breaks a working assumption (e.g. a page revealing self-signup volume) → assert the agent pivots (role_version bump, pivot card in needs-from-you, at most ONE question asked, changed artifact re-ratified, no apology framing)** → upgrade path (0.8.1 data + 0.9.0 load → nudge → abilities appear); **production e2e** (marketplace artifact, prod scheduler, disposable account, delete after); ship 0.9.0 to marketplaces.com.ai | dojo asserts the *outcome*, dumb-user style: short answers, no steering |

Order: A → B → C → D∥E → F. B before C (parser needs the shapes). Plugin
version bumped in **all three stamps** (in-code manifest authoritative).

## 9. Open decisions (defaults chosen, flag if wrong)

1. **NOC as second sidebar section** of plugin-curiosity (not a tab inside
   Missions) — default YES: "not here" was explicit, and a separate surface
   keeps Missions calm.
2. **Setup % = unweighted mean of abilities** — default yes; weights are
   agent-gameable and unexplainable to a first-time user.
3. **S-ladder survives internally** (gates/forcing) but is banned from all
   user-facing strings — default yes; removing it entirely is a bigger
   surgery with no owner-visible payoff.
