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
async def test_agent_facing_kinds_are_guarded(ctx, monkeypatch):
    from plugin_curiosity import comms

    monkeypatch.setattr(comms, "in_quiet_hours", lambda now=None: False)
    # dream/kickoff are structural kinds — the tool coerces them to routine
    res = await call(ctx, "share_thought", body="sneaky [[mission]]", kind="dream")
    assert res.get("posted")
    blocked = await call(ctx, "share_thought", body="again [[mission]]", kind="kickoff")
    assert blocked.get("blocked")  # both counted as routine → cap hit


def test_mission_kickoff_commits_goals_and_scans_reach():
    t = _KICKOFF_CONTENT
    assert "goal_set" in t and "COMMIT" in t
    assert "My goals" in t and "Next move" in t
    assert "marketplace_search" in t
    assert "wa_status" in t and "connector_list_connected" in t
    # ends on Luna's action, never on homework for the owner
    assert "NEVER end on a list of suggestions" in t
    for tool in ("goal_set", "goal_list", "marketplace_search", "wa_status",
                 "connector_list_connected"):
        assert tool in KICKOFF_TOOLS


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
