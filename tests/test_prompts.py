"""9C prompt surgery: single-source consts, per-branch content, exact titles,
anti-pattern absence, phase-aware fragment."""

from __future__ import annotations

from plugin_curiosity.mission import prompt_fragment
from plugin_curiosity.prompts import (
    ASK_SHAPE,
    LOOP_DISCIPLINE,
    PHASE_CHECK,
    SETUP_WEEKLY_TITLE,
    TALENTED_HIRE_LAW,
    WORK_WEEKLY_TITLE,
)
from plugin_curiosity.research import _KICKOFF_CONTENT, DAILY_RESEARCH_TARGET
from plugin_curiosity.review import WEEKLY_REVIEW_TARGET

MISSION = {"statement": "grow signups", "autonomy_rung": 2, "risk_ceiling": "low"}


def test_shared_lines_exactly_once_per_surface():
    assert _KICKOFF_CONTENT.count(TALENTED_HIRE_LAW) == 1
    assert _KICKOFF_CONTENT.count(ASK_SHAPE) == 1
    assert DAILY_RESEARCH_TARGET.count(ASK_SHAPE) == 1
    assert WEEKLY_REVIEW_TARGET.count(ASK_SHAPE) == 1
    assert DAILY_RESEARCH_TARGET.count(LOOP_DISCIPLINE) == 1
    frag_setup = prompt_fragment(MISSION, "setup")
    assert frag_setup.count(TALENTED_HIRE_LAW) == 1


def test_kickoff_setup_arc_shape():
    t = _KICKOFF_CONTENT
    # S0: sharper restatement, plan-changing questions as loops, no asks
    assert "SHARPER" in t and "plan-changing questions" in t
    assert "loop_open(kind='question')" in t
    assert "ZERO access asks" in t
    # S1: charter all seven kinds, timebox language, canonical example
    assert "ALL seven kinds" in t and "workflow_approval" in t
    assert "stub/summary wiki depth" in t and "NO deep corpus" in t
    assert "WRONG: 'connect me to AdWords" in t
    # S2: big-batch goals + ratification line — kickoff only
    assert "5-8 dated goals" in t and "cover EVERY" in t
    assert "push back now" in t
    assert "stage_set('S2')" in t


def test_daily_is_phase_branched():
    t = DAILY_RESEARCH_TARGET
    assert PHASE_CHECK in t
    assert "SETUP BRANCH (agent_phase='setup')" in t
    assert "WORK BRANCH (agent_phase='work')" in t
    # patrol runs before either branch
    assert t.index("LOOP PATROL") < t.index("SETUP BRANCH")
    # patrol self-heals asks that rode a tool past the ledger (9D run-3 gap:
    # same-turn discipline missed 3 straight runs on request_credential asks)
    assert "BACKFILL CHECK" in t
    # setup-only: overdue confrontation + event-driven replan + anti-pattern
    assert "CONFRONT overdue goals" in t
    assert "change the plan TODAY" in t
    assert "stopped learning" in t
    assert "stopped learning" not in WEEKLY_REVIEW_TARGET
    assert "stopped learning" not in _KICKOFF_CONTENT
    # work-only: rolling goals (taper) — not in kickoff
    assert "2-3 goals rolling" in t
    assert "rolling" not in _KICKOFF_CONTENT
    # grant-payoff rule
    assert "Use every grant VISIBLY by the next daily pass" in t


def test_weekly_titles_exact_and_branched():
    t = WEEKLY_REVIEW_TARGET
    assert PHASE_CHECK in t
    assert f"title='{SETUP_WEEKLY_TITLE}'" in t
    assert f"title='{WORK_WEEKLY_TITLE}'" in t
    assert SETUP_WEEKLY_TITLE == "Setup report — getting ready for the job"
    assert WORK_WEEKLY_TITLE == "Work report — week in review"
    # setup branch blocks
    for block in ("Scope scoreboard", "Value vs asks", "Plan changes",
                  "Road to work mode", "I need"):
        assert block in t, block
    assert "'none' is a finding too" in t
    assert "phase_advance" in t
    # work branch blocks
    for block in ("Done", "Insights", "Improve", "Next move"):
        assert block in t, block
    assert "leave the toolkit better" in t
    # value first, ask last ("I need" alone also occurs inside the phase-one
    # doctrine text — probe the bolded section labels)
    assert t.index("**Value vs asks**") < t.index("**I need**")


def test_fragment_phase_posture():
    setup = prompt_fragment(MISSION, "setup")
    default = prompt_fragment(MISSION)  # no phase → setup posture
    work = prompt_fragment(MISSION, "work")
    assert TALENTED_HIRE_LAW in setup and TALENTED_HIRE_LAW in default
    assert "small, redirectable increments" in setup
    assert TALENTED_HIRE_LAW not in work
    assert "leave the toolkit better" in work and "mastery" in work
    # shared operator base survives in both
    for frag in (setup, work):
        assert "relentless" in frag and "[[mission-goals]]" in frag
    # missionless branch untouched by 9C
    missionless = prompt_fragment(None)
    assert "no active mission yet" in missionless
    assert TALENTED_HIRE_LAW not in missionless


def test_anti_patterns_absent():
    for surface in (_KICKOFF_CONTENT, DAILY_RESEARCH_TARGET, WEEKLY_REVIEW_TARGET,
                    prompt_fragment(MISSION, "setup"), prompt_fragment(MISSION, "work")):
        assert "work quietly" not in surface
    # never end on homework for the owner
    assert "never on homework" in DAILY_RESEARCH_TARGET
    assert "NEVER end on a list of suggestions" in _KICKOFF_CONTENT


def test_prompt_budget_sanity():
    # branching halves active text; keep total payloads bounded (chars).
    # 9.001 raised the setup-side budgets deliberately: the phase-one
    # doctrine + stage ladder + heartbeat contract ride every setup surface
    # (owner-mandated frame). The WORK fragment stays lean — relentless
    # setup verbosity is phase-scoped by design. 9.002 raised the review
    # budget for the NOC forcing: the weekly-scores line shape rides BOTH
    # branches (the pane parses those lines) plus the drift audit. Phase 10
    # raised the setup surfaces again — the FDE doctrine, JD shape, ability
    # contract, question cadence, materiality rule and no-blame frame ride
    # the kickoff and setup fragment (the job model IS the setup product).
    # 0.9.2 raised daily/weekly/kickoff/setup: OWNER_WORDS (plain-words rule)
    # and WIKI_BINDING (mission-wiki scoping) ride every recurring surface —
    # both are correctness contracts, not verbosity.
    # 0.9.10 raised setup/work: the STATUS LINE rule (current_state_set —
    # the pane shows the agent's one-liner verbatim; a UI-invented sentence
    # was the alternative) rides both phase branches.
    # 0.9.11 raised every surface: OWNER_WORDS grew an explicit vocabulary
    # map (ratify→approve, charter→job description, …) — owner-reported
    # jargon leak; the mapping IS the fix, so it rides every surface the
    # rule rides.
    # 0.9.12 raised setup/work fragments: three rare tools moved behind the
    # mission-changes skill, and every prompt that names one must also say
    # "load the skill the turn before" (tools unlock next turn) — the
    # load-ahead warning is the price of pulling three schemas out of EVERY
    # turn's prompt, a large net context win.
    # 0.9.14 (10.006) raised every fragment: the feedback contract (owner
    # criticism → same-turn structural change), the reasons-ledger rule and
    # the proactivity rule ride BOTH phase branches — correctness contracts;
    # the alternative was feedback answered with empathy and an untouched
    # playbook. The weekly review gained the feedback-debt red check.
    # 0.12.0 (jobs-dojo bug 3) raised the kickoff budget: the already-supplied
    # check (never re-ask for data the owner just gave) is a correctness
    # contract, not verbosity — the artifact re-asked for a pasted SaaS ledger.
    assert len(DAILY_RESEARCH_TARGET) < 5500
    assert len(WEEKLY_REVIEW_TARGET) < 8800
    assert len(_KICKOFF_CONTENT.format(statement="x", wiki_note="")) < 13600
    assert len(prompt_fragment(MISSION, "setup")) < 13100
    wiki_bound = dict(MISSION, wiki_id="grow-signups-abc123")
    assert len(prompt_fragment(wiki_bound, "setup")) < 13300
    assert len(prompt_fragment(wiki_bound, "work")) < 6100


def test_owner_words_covers_chat_and_tool_output_translation():
    """0.9.3: the role-resilience dojo caught 'Setup stage: still S0' said
    straight to the owner in chat — the rule must name chat replies and the
    parroting vector (repeating codes out of tool results)."""
    from plugin_curiosity.prompts import OWNER_WORDS

    assert "chat replies" in OWNER_WORDS
    assert "translate" in OWNER_WORDS
