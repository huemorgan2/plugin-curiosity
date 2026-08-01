# 10.002 — The panes: Missions rebuilt + the NOC split

**Ships:** plugin-curiosity **0.9.1**. Depends on 10.001 (overview v2).
UI-only — no schema or contract changes.

**Parent:** [../PLAN.md](../PLAN.md) §3–§4. **MANDATORY:** read
`/vision/ux_guidelines.md` (all sections) before touching any file here;
every section must pass eyebrow → bottom-line headline → one-line bullets →
expandable detail, calm surfaces, `(i)`-affordance tooltips for optional
depth only.

---

## 1. Missions pane — rebuild (`ui/index.html`, `app.js`, `style.css`)

Four sections, strict order, wide padding, few panels:

1. **ACTIVE MISSION** — hero kept (the one gradient). Eyebrow, mission
   statement headline, support = agent's own one-line restatement, plain-word
   phase (`Onboarding — setting myself up` / `Working the mission`), morale
   line. Autonomy/risk chips REMOVED (→ NOC).
2. **JOB DESCRIPTION** — living-draft stamp (`draft v{role_version} ·
   revised {date} — {reason}`); the four blocks rendered as bullets
   (numbered where the shape numbers them); assumptions with check-dots
   (verified ● / checking ◐ / broken → rendered as the discovery that
   revises it). `shape_ok:false` → raw text + honest note. Missing page →
   "I haven't written my job description yet — it lands with kickoff."
3. **SETUP — X% complete** — ring headline (keep the praised ring), support
   `we are in the onboarding phase`; ability rows: bold one-line title +
   thin % bar + number; expand → subtasks as one-line bullets with status
   dots + notes. **Zero `S\d` strings anywhere.**
4. **GOALS** — headline = next goal + date; the timeline visual: horizontal
   line across the goal horizon, dot per goal, bubble = ONE word + one
   number; past dots green/red by outcome. Below: numbered next-2–3 only,
   two lines each — required-result line, then green/amber/red readiness
   text from `readiness_note`. Farther goals: dots only.

**Needs-from-you** stays as a slim strip under the hero (one line per ask,
chat deep-link); role pivots render as their own card ("Big change: … —
here's why, weigh in").

REMOVED from this pane (all → NOC): heartbeat panel, activity stream,
knowledge shelf, what-happens-next, role wall, gap board, past missions,
pace chip. Empty/blocked states kept, rewritten to the grammar.

## 2. NOC pane — new sidebar section

- Manifest: `sidebar_sections` gains `{id:"noc", label:"NOC",
  icon:"activity", sort_order:46}`; served at `/ui/noc/` (same static-app
  pattern, same token CSS, cache-busted `?v=<version>`).
- Panels (moved, visually consistent, density allowed): role wall + incident
  strip (work-phase hero), heartbeat (pulse/streak/history, live beat), gap
  board (internal view of abilities), activity stream, knowledge shelf,
  what-happens-next (triggers + nudges), autonomy/risk/pace chips,
  past-missions shelf.
- Both panes consume the ONE overview payload; live-bridge events power both
  (`luna-ui-ready` handshake each).

## 3. Verify

- **Unit:** route serves `/ui/noc/`; registry advertises both sections;
  no server change beyond the manifest/routes — keep it thin.
- **Local dojo** (extends 10.001's walkthrough): pane HTML/JSON has zero
  `S\d` labels; four sections present in order; JD stamp shows
  role_version; ability bars match ability_list percents; goal timeline
  data-contract (dots = dated goals, bubbles one word + number); pivot card
  appears after the discovery leg; NOC registered + served + carries the
  moved panels; live event updates both panes.
- **Guidelines pass:** explicit checklist review against
  `/vision/ux_guidelines.md` §§1–7 (enforcement section) — recorded in the
  execution summary.
- **Production e2e** (the phase's proving run): fresh disposable Luna,
  artifact installed at runtime from marketplaces.com.ai, prod scheduler
  through tunnel, disposable account (delete after; enumerate before
  creating): adoption → JD/abilities/goals live on the pane → heartbeat
  fire → re-score visible → pivot leg → both panes. Screenshot set for the
  summary.
- Three version stamps, push (huemorgan2), publish 0.9.1, `execution_summary.md`.
