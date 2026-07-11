"""Phase-4 acceptance: the kickoff moment (quick win) and the real
daily-research trigger target, including in-place target re-sync."""

from __future__ import annotations

import asyncio

import pytest

from plugin_curiosity import research
from plugin_curiosity.mission import MISSION_SCHEDULES


async def call(ctx, tool: str, **kwargs):
    return await ctx.tool_registry.registered[tool][1](**kwargs)


@pytest.fixture(autouse=True)
def fast_kickoff(monkeypatch):
    monkeypatch.setattr(research, "KICKOFF_DELAY_S", 0)
    monkeypatch.setattr(research, "KICKOFF_RETRY_S", 0)


@pytest.mark.asyncio
async def test_mission_set_spawns_kickoff_moment(ctx):
    r = await call(ctx, "mission_set", statement="grow signups")
    assert r["kickoff"] == "started"
    for _ in range(5):
        await asyncio.sleep(0)  # let the fire-and-forget task run
    (post,) = [p for p in ctx.muted_posts if p["title"] == research.KICKOFF_TITLE]
    assert post["channel"] == "moment"
    assert post["source"] == "curiosity"
    assert "grow signups" in post["content"]
    # the artifact shape is instructed (phase 10 setup arc): brief + job
    # description + ladder + timeline + open questions
    for marker in ("Brief", "My job description", "My ladder", "My goals", "Open questions"):
        assert marker in post["content"]


@pytest.mark.asyncio
async def test_kickoff_tools_are_research_scoped(ctx):
    await call(ctx, "mission_set", statement="grow signups")
    for _ in range(5):
        await asyncio.sleep(0)
    (post,) = [p for p in ctx.muted_posts if p["title"] == research.KICKOFF_TITLE]
    tools = post["tools"]
    assert "web_search" in tools and "wiki_write" in tools and "wiki_cite" in tools
    # the kickoff reply IS the artifact; share_thought would double-post
    assert "share_thought" not in tools
    # playbook authoring is chat_only — never allowlisted in a muted turn
    assert not any(t.startswith("playbook") for t in tools)


@pytest.mark.asyncio
async def test_kickoff_retries_a_dead_turn(ctx):
    """9D run-13: the kickoff turn died to a transient API ConnectTimeout and
    the mission silently stranded at S0. post_muted_message reports the dead
    turn via an ``error`` key (no exception) — kickoff must retry."""
    calls = []
    real = ctx.send_muted_message

    async def flaky(title, content, **kw):
        calls.append(title)
        if len(calls) < 3:
            return {"responded": False, "error": "turn failed: APITimeoutError"}
        return await real(title, content, **kw)

    ctx.send_muted_message = flaky
    await research.run_kickoff(ctx, "grow signups")
    assert len(calls) == 3  # two dead turns, third lands
    (post,) = [p for p in ctx.muted_posts if p["title"] == research.KICKOFF_TITLE]
    assert "grow signups" in post["content"]


@pytest.mark.asyncio
async def test_kickoff_gives_up_after_bounded_attempts(ctx):
    calls = []

    async def dead(title, content, **kw):
        calls.append(title)
        return {"responded": False, "error": "turn failed: APITimeoutError"}

    ctx.send_muted_message = dead
    await research.run_kickoff(ctx, "grow signups")
    assert len(calls) == research.KICKOFF_ATTEMPTS  # bounded, no infinite loop


def test_daily_research_target_is_wired():
    daily = next(s for s in MISSION_SCHEDULES if s["name"] == "curiosity-daily-research")
    assert daily["target"] == research.DAILY_RESEARCH_TARGET
    assert "Placeholder" not in daily["target"]
    # the fired routine teaches the full loop: read mission, research, record,
    # cite, share through the guardrails, defer playbook authoring to chat
    for marker in ("mission_get", "web_search", "wiki_cite", "share_thought", "chat-only"):
        assert marker in daily["target"]


@pytest.mark.asyncio
async def test_sync_updates_stale_target_in_place(ctx):
    ctx.tool_registry.existing_triggers = [
        {"id": "trg-old", "name": "curiosity-daily-research",
         "target": "old placeholder", "expr_raw": "every day at 09:00",
         "enabled": True},
    ]
    r = await call(ctx, "mission_set", statement="grow signups")
    updated = ctx.tool_registry.trigger_updated
    assert [u["id"] for u in updated] == ["trg-old"]
    assert updated[0]["target"] == research.DAILY_RESEARCH_TARGET
    # only the drifted field is sent — the schedule was already current
    assert "schedule_expr" not in updated[0]
    # dream + weekly review were missing -> created; research updated in place
    assert {c["name"] for c in ctx.tool_registry.trigger_created} == {
        "curiosity-nightly-dream",
        "curiosity-weekly-review",
    }
    assert "curiosity-daily-research" in r["schedules"]

    # second set: everything current -> no churn
    await call(ctx, "mission_set", statement="ship the app")
    assert len(ctx.tool_registry.trigger_updated) == 1
    assert len(ctx.tool_registry.trigger_created) == 2


@pytest.mark.asyncio
async def test_sync_tolerates_old_scheduler_without_update_tool(ctx):
    ctx.tool_registry.has_update_tool = False
    ctx.tool_registry.existing_triggers = [
        {"id": "trg-old", "name": "curiosity-daily-research",
         "target": "old placeholder", "expr_raw": "every day at 09:00",
         "enabled": True},
    ]
    r = await call(ctx, "mission_set", statement="grow signups")
    # create-only sync: no crash, dream still created, research left as-is
    assert r["mission"]["statement"] == "grow signups"
    assert ctx.tool_registry.trigger_updated == []
