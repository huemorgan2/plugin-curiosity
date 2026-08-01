"""Weekly review (8.2D) + relentless prompt surgery (8.2B) + reach (8.2F)."""

from __future__ import annotations

import pytest

from plugin_curiosity import review
from plugin_curiosity.mission import MISSION_SCHEDULES, prompt_fragment
from plugin_curiosity.research import _KICKOFF_CONTENT, DAILY_RESEARCH_TARGET, KICKOFF_TOOLS


async def call(ctx, name, **kw):
    return await ctx.tool_registry.registered[name][1](**kw)


def test_weekly_review_schedule_is_wired():
    weekly = next(s for s in MISSION_SCHEDULES if s["name"] == "curiosity-weekly-review")
    assert weekly["schedule_expr"] == "every monday at 09:30"
    assert weekly["action_type"] == "agent_prompt"
    assert weekly["target"] == review.WEEKLY_REVIEW_TARGET


def test_monthly_review_schedule_is_wired():
    monthly = next(
        s for s in MISSION_SCHEDULES if s["name"] == "curiosity-monthly-review"
    )
    # exact scheduler-service grammar — anything else fails to parse
    assert monthly["schedule_expr"] == "on the 1st of every month at 09:45"
    assert monthly["action_type"] == "agent_prompt"
    assert monthly["target"] == review.MONTHLY_REVIEW_TARGET


def test_weekly_review_target_shape():
    t = review.WEEKLY_REVIEW_TARGET
    assert "goal_list" in t and "goal_update" in t
    assert "kind='review'" in t and "[[mission-goals]]" in t
    # the scoreboard confronts stalls and asks for exactly one thing
    assert "stalled" in t and "exactly ONE ask" in t
    # setup + reach audit, feature-detected
    assert "trigger_list" in t and "marketplace_search" in t
    assert "wa_status" in t and "connector_list_connected" in t
    assert "isn't available" in t
    assert "Next move" in t


def test_weekly_work_note_is_five_lines_with_prediction_discipline():
    """11.008/M7: the work-phase weekly is a 5-line note — numbers server-
    computed, at most one proposal, 'No issues' only when literally true,
    incident weeks propose nothing."""
    t = review.WEEKLY_REVIEW_TARGET
    for line in ("**Ran**", "**Cost vs value**", "**Health**",
                 "**Proposal**", "**Next move**"):
        assert line in t, line
    assert "FIVE headed" in t
    # numbers come from the server, never the model
    assert "metrics_snapshot" in t
    assert "never compute or estimate a metric yourself" in t
    # honesty gate on the health line
    assert "'No issues' ONLY when literally true" in t
    # prediction discipline: open for real, report the closed bet's verdict
    assert "proposal_open" in t and "proposal_list" in t
    assert "predicted X" in t and "actual Y" in t
    # p09 dojo run-1: Gemini dodged with "No proposal this week as focus
    # remained on optimizing current operations" — a normal week must bet
    assert "ALWAYS places its bet" in t
    assert "'nothing to improve' is never true" in t
    # never-share-turn law
    assert "recovery and proposals never share a turn" in t


def test_monthly_review_target_shape():
    t = review.MONTHLY_REVIEW_TARGET
    from plugin_curiosity.prompts import MONTHLY_TITLE

    assert f"title='{MONTHLY_TITLE}'" in t
    assert "kind='review'" in t
    for line in ("**Promised vs delivered**", "**Cost and savings**",
                 "**Opportunities**", "**Decision**"):
        assert line in t, line
    # every opportunity anchored to a stored owner quote or receipt
    assert "[[owner-decisions]]" in t
    assert "no anchor stays off the list" in t
    # downsells are first-class
    assert "DOWNSELLS" in t and "shrink or drop" in t
    # exactly one decision ask, one-word answerable
    assert "exactly ONE decision" in t
    # numbers server-computed; no-data said plainly
    assert "metrics_snapshot" in t and "no data yet" in t
    # boundary source is feature-detected
    assert "policy_list" in t and "isn't available" in t
    # incident months add no new bets
    assert "recovery and proposals never share a turn" in t
    # a setup-phase month reports progress-vs-promise, not opportunities
    assert "setup progress vs promise" in t
    # CARD FIRST — scheduled self-spend is announced
    assert "scheduled=true" in t


@pytest.mark.asyncio
async def test_review_kind_bypasses_daily_cap(ctx, monkeypatch):
    from plugin_curiosity import comms

    monkeypatch.setattr(comms, "in_quiet_hours", lambda now=None: False)
    first = await call(ctx, "share_thought", body="routine insight [[mission]]")
    assert first.get("posted")
    blocked = await call(ctx, "share_thought", body="second routine [[mission]]")
    assert blocked.get("blocked")
    rev = await call(
        ctx,
        "share_thought",
        body="weekly scoreboard [[mission-goals]]",
        title="Weekly mission review",
        kind="review",
    )
    assert rev.get("posted")


@pytest.mark.asyncio
async def test_work_weekly_note_refuses_to_post_without_a_bet(ctx, store, monkeypatch):
    """p09 dojo runs 1-2: prose alone lost — Gemini posted 'No proposal this
    week' on a normal week twice. The flow lives in the tool layer: the
    work-phase note refuses to post until a bet exists."""
    from plugin_curiosity import comms
    from plugin_curiosity.prompts import WORK_WEEKLY_TITLE

    monkeypatch.setattr(comms, "in_quiet_hours", lambda now=None: False)
    await store.set("own the weekly newsletter end to end")
    blocked = await call(
        ctx, "share_thought", body="- **Proposal** — none [[mission-goals]]",
        title=WORK_WEEKLY_TITLE, kind="review")
    assert "proposal_open" in blocked.get("error", "")
    assert "recovery first" in blocked["error"]

    await ctx.proposal_store.open("faster digest", "saves ~20 min/week")
    posted = await call(
        ctx, "share_thought",
        body="- **Proposal** — faster digest, saves ~20 min/week [[mission-goals]]",
        title=WORK_WEEKLY_TITLE, kind="review")
    assert posted.get("posted")


@pytest.mark.asyncio
async def test_closed_bet_note_must_carry_the_verdict(ctx, store, monkeypatch):
    """p09 dojo run-3: the note after a close said 'No proposals closed this
    week' over a bet closed minutes earlier. The gate demands the verdict
    words and hands the exact sentence to quote."""
    from plugin_curiosity import comms
    from plugin_curiosity.prompts import WORK_WEEKLY_TITLE

    monkeypatch.setattr(comms, "in_quiet_hours", lambda now=None: False)
    await store.set("own the weekly newsletter end to end")
    p = await ctx.proposal_store.open(
        "faster digest", "saves you ~30 min/week", predicted_minutes=30)
    await ctx.proposal_store.decide(p["id"], decision="accepted")
    closed = await ctx.proposal_store.close(
        p["id"], actual="saved ~25 min/week", actual_minutes=25)
    assert closed["verdict"].startswith("predicted saves you ~30 min/week, actual")
    assert "held" in closed["verdict"]

    blocked = await call(
        ctx, "share_thought", body="- **Proposal** — nothing new [[mission-goals]]",
        title=WORK_WEEKLY_TITLE, kind="review")
    assert "verdict" in blocked.get("error", "")
    assert "predicted saves you ~30 min/week" in blocked["error"]

    listing = await ctx.proposal_store.list()
    assert listing["last_closed"]["verdict"] == closed["verdict"]

    posted = await call(
        ctx, "share_thought",
        body=f"- **Proposal** — {closed['verdict']} [[mission-goals]]",
        title=WORK_WEEKLY_TITLE, kind="review")
    assert posted.get("posted")


@pytest.mark.asyncio
async def test_recovery_week_and_setup_note_skip_the_bet_gate(ctx, monkeypatch):
    from plugin_curiosity import comms
    from plugin_curiosity.prompts import SETUP_WEEKLY_TITLE, WORK_WEEKLY_TITLE

    monkeypatch.setattr(comms, "in_quiet_hours", lambda now=None: False)
    rec = await call(
        ctx, "share_thought",
        body="no proposal this week — recovery first [[mission-goals]]",
        title=WORK_WEEKLY_TITLE, kind="review")
    assert rec.get("posted")
    setup = await call(
        ctx, "share_thought", body="setup scoreboard [[mission-goals]]",
        title=SETUP_WEEKLY_TITLE, kind="review")
    assert setup.get("posted")


@pytest.mark.asyncio
async def test_agent_facing_kinds_are_guarded(ctx, monkeypatch):
    from plugin_curiosity import comms

    monkeypatch.setattr(comms, "in_quiet_hours", lambda now=None: False)
    # dream/kickoff are structural kinds — the tool coerces them to routine
    res = await call(ctx, "share_thought", body="sneaky [[mission]]", kind="dream")
    assert res.get("posted")
    blocked = await call(ctx, "share_thought", body="again [[mission]]", kind="kickoff")
    assert blocked.get("blocked")  # both counted as routine → cap hit


def test_mission_kickoff_commits_goals_and_scans_reach():
    # phase14 split: the PLANNING pass scans capabilities and reach (and
    # cannot commit anything); the EXECUTION pass commits the goals.
    from plugin_curiosity.research import _PLAN_EXEC_CONTENT, PLAN_EXEC_TOOLS

    t = _KICKOFF_CONTENT
    assert "marketplace_search" in t
    assert "wa_status" in t and "connector_list_connected" in t
    assert "get_plugin_status" in t
    for tool in ("get_plugin_status", "marketplace_search", "wa_status",
                 "connector_list_connected"):
        assert tool in KICKOFF_TOOLS
    assert "goal_set" not in KICKOFF_TOOLS  # planning cannot commit
    e = _PLAN_EXEC_CONTENT
    assert "goal_set" in e
    # ends on Luna's action, never on homework for the owner
    assert "NEVER end on a list of suggestions" in e
    for tool in ("goal_set", "goal_list", "marketplace_search"):
        assert tool in PLAN_EXEC_TOOLS


def test_daily_pass_works_the_ledger_and_reports():
    t = DAILY_RESEARCH_TARGET
    assert "goal_list" in t and "goal_update" in t
    assert "ONE goal" in t and "TODAY" in t
    assert "share_thought" in t and "Moved" in t
    # the old default was silence; 8.2 flips it — only an empty pass is quiet
    assert "work quietly" not in t
    assert "Skip only a genuinely empty pass" in t


def test_mission_fragment_is_relentless():
    frag = prompt_fragment(
        {"statement": "grow signups", "autonomy_rung": 2, "risk_ceiling": "low"}
    )
    assert "relentless" in frag and "goal ledger" in frag
    assert "[[mission-goals]]" in frag
    assert "CHANGE" in frag
    # capability hunger: propose installs/connections that unlock real action
    assert "install" in frag and "connect" in frag
