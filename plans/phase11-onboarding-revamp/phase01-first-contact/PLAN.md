# Phase 01 — First contact (the most important phase)

First impressions are hard to change. This phase owns the very first minutes of
a Luna's life: what she says unprompted, and how curiosity takes the lead when
installed. Everything else builds on the trust set here.

## Scope

**A. Fresh-Luna self-intro (luna core — regardless of curiosity).**
On first boot, Luna receives a system message that she is on, and she
introduces herself: who she is, what she can do in three concrete examples,
one question ("what should I take off your plate first?"). Mechanics:
- New core feature, plan `luna/plans/037-fresh-boot-self-intro/` (luna repo
  needs its own plan + execution_summary; main branch).
- First-boot detection: a state flag (e.g. `core.first_boot_intro_sent`);
  fires once via the muted-turn machinery (`channel="moment"`), through the
  startup hook — NOT `on_load` tasks (they die silently under `luna serve`;
  use `app.router.on_startup`).
- Convergent: flag checked before send; reaper-safe under concurrent boots.
- Content plain-words, no jargon; short — 5 lines max.

**B. Curiosity dominates the intro when installed.**
- If curiosity is installed at first boot, the core intro defers: curiosity's
  install kickoff IS the intro (core checks whether a plugin claims the
  intro — simplest: core sends its intro only if no plugin has posted a
  moment-turn within the boot window; explicit takeover beats timing —
  a manifest capability `provides_intro = True` on `PluginManifest`).
- Rewrite `INSTALL_KICKOFF_CONTENT` (research.py:293) from "give me a
  mission" to possibility-teaching: Luna introduces herself as the person
  Roy's method describes — an FDE hiring herself — with **three concrete
  before/after examples** of what a mission unlocks, then ONE opening
  question. No feature lists, no parameters.
- First-turn direction: the missionless system prompt (MISSION_GATE_FLOW
  intro section) makes the agent lead the first exchange — ask about the
  business, listen, teach one possibility — not wait passively.

## Testable units

| # | Unit | Test |
|---|---|---|
| 1 | Core intro fires once on fresh boot | luna core test: fresh state → intro sent; second boot → not resent; concurrent boot → one intro |
| 2 | Core intro defers to curiosity | test: manifest `provides_intro` → core stays silent |
| 3 | Kickoff content teaches possibilities | curiosity unit: content has 3 before/after examples, 1 question, no banned jargon (OWNER_WORDS), no "give me a mission" |
| 4 | Kickoff still convergent | existing `test_kickoff.py` flags/skip-on-mission regressions stay green |
| 5 | First live turn quality | dojo on fresh QA Luna (:8766): boot fresh → intro arrives; first user reply gets curiosity-led direction, ≤3 questions, no form-wall |

## Regression gate

Full plugin-curiosity pytest suite green + luna core test suite for touched
modules + dojo scenario 5 passes twice. Verify on a real running Luna
(fresh DB) before summary.

## Versions

luna core: minor bump per its own plan. plugin-curiosity: 0.12.1
(intro-only change, no schema).

## Exit

`execution_summary.md` here (+ in luna/plans/037): what shipped, test counts,
what we learned about the first interaction → feeds phase02's intake wording.
