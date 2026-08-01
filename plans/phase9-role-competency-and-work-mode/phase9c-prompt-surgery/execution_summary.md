# Phase 9C — Prompt Surgery: Execution Summary

**Status: DONE** — 91/91 unit tests; live kickoff smoke on QA Luna :8001 (results below).

## What was built

- `plugin_curiosity/prompts.py` (new): single-source consts — `TALENTED_HIRE_LAW`, `ASK_SHAPE`, `CANONICAL_EXAMPLE` (AdWords wrong/right), `LOOP_DISCIPLINE`, `PHASE_CHECK`, and the two exact weekly titles. Every surface imports; no drift.
- **Kickoff** (`_KICKOFF_CONTENT`): rewritten as the S0→S2 setup arc in one turn — S0 sharper restatement + 2-3 non-obvious observations + plan-changing questions opened as loops + ZERO access asks; S1 charter all seven scope kinds + reach inventory + first value pass at stub/summary depth (timebox until ratification) + `value_log_add`; S2 5-8 dated goals covering every scope, `stage_set('S2')`, artifact (Brief / What I found / My charter / My goals / Access plan / Open questions / Next move), closing "push back now". `KICKOFF_TOOLS` extended with scope/stage/loop/value tools.
- **Daily** (`DAILY_RESEARCH_TARGET`): phase-branched. Scheduler targets are STATIC text, so branching is in-prompt: `PHASE_CHECK` tells the agent to call `scope_list` and execute only its branch. Step 0 LOOP PATROL (both phases) with the UNUSED-GRANT CHECK; setup branch confronts overdue goals, one-goal value pass, EVENT-DRIVEN REPLAN ("a plan that never changes after week 1 means you stopped learning"), one shaped ask max; work branch keeps 2-3 goals rolling with same-pass refill, executes through validated playbooks, logs value. Both branches end on the agent's own next move, never owner homework.
- **Weekly** (`WEEKLY_REVIEW_TARGET`): two titled branches — "Setup report — road to competency" (scope scoreboard, timeline, loops, value-vs-asks, plan changes, road to work mode with the S4/S5 gates, one shaped ask max) and "Work report — week in review" (done/insights/improve/next move). Value first, ask last, enforced by section order.
- **Fragment** (`prompt_fragment(mission, phase=None)`): phase-aware posture — setup gets the law + small-redirectable-increments corollary + loop discipline; work gets mastery/rolling-goals/toolkit-upkeep, and the law drops out (it's setup pedagogy). `prompt_sections` passes the live phase from `ScopeStore.state()`. Missionless branch untouched.
- `tests/test_prompts.py` (new, 7 tests): shared lines exactly once per surface; S0-S2 arc shape; daily branch content (replan rule and anti-pattern daily-only, rolling goals work-only); exact weekly titles + section order (value before ask); fragment posture per phase incl. law absent in work; "work quietly" absent everywhere; char-budget ceilings so future edits can't silently bloat the prompt payload.

## Errors encountered and fixes

1. **Line-wrap broke a contract string**: "NEVER end on a list of suggestions" was split across a newline+indent inside the triple-quoted kickoff, silently failing the substring asserts that guard it. Rewrapped so the phrase stays contiguous. Lesson: contract phrases in prompt text must never straddle a manual line break — the tests assert on substrings.
2. **Stale-history confound in live QA (twice)**: after wiping the mission DB, the agent still refused a new mission — first from old chat scrollback (fix: fresh conversation), then from `memory_facts` rows recalling the old mission (fix: truncate `memory_facts` too). Both refusals were CORRECT agent behavior (no silent double-mission); the QA harness was wrong. 9D walkthrough now resets memory + uses a fresh conversation.
3. **Same-turn adoption is not the contract for vague asks**: "can you like take this on?" gets a sharper proposed mission + one confirming question, and `mission_set` lands on the owner's shrug ("uh yeah sounds good"). Kept: this is the talented-hire behavior we want; drivers/walkthrough send the shrug when no mission row appears after turn 1.

## Live kickoff smoke (fresh mission, naive user)

Vague owner ask ("sister and i sell handmade soap on etsy… can you take this on?") → agent proposed a sharper mission, adopted on a shrug, and the kickoff reaction turn ran the S0→S2 arc. **12/13 checks passed** (drive9c.py): 11 scopes across all 7 kinds; 7 dated goals; 3 question loops opened DURING the pass (loop discipline transferring); ZERO ask loops; 1 value entry; stage S2; all wiki mirrors; ratification line verbatim; no connect-first ask — the artifact's Access Plan even says "one at a time, after delivering value" unprompted. The single FAIL was a literal-phrase assert ("say go and I'll do it"): the agent paraphrased its Next Move ("the moment you share the shop URL I'll run a full audit; while I wait, I'll build the keyword strategy") — behavior correct, check too literal. Behavioral asserts should test for owner-homework ABSENCE, not for exact closing phrases.

## Changes to future phases

- 9D: plan hardening added — RESET step must truncate `memory_facts` and use a fresh conversation (stale-history lesson); mission adoption needs the shrug fallback; approvals list key is `requests`, approve body needs `{reason}`.
- 9E: no changes; version bump will carry prompts.py automatically.
