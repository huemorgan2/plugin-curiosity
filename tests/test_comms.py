"""Phase-4 acceptance: share_thought guardrails — grounding, daily cap,
quiet hours + queue drain — and the posting mechanics (moment, source,
read-tool allowlist, fire-and-forget)."""

from __future__ import annotations

import asyncio

import pytest

from plugin_curiosity import comms

# captured before the autouse fixture monkeypatches the module attribute
_real_in_quiet_hours = comms.in_quiet_hours


async def share(ctx, **kwargs):
    return await ctx.tool_registry.registered["share_thought"][1](**kwargs)


async def settle():
    """Let fire-and-forget _post tasks run."""
    for _ in range(3):
        await asyncio.sleep(0)


@pytest.fixture(autouse=True)
def daytime(monkeypatch):
    """Guardrail tests control the clock explicitly; default to daytime."""
    monkeypatch.setattr(comms, "in_quiet_hours", lambda now=None: False)


@pytest.mark.asyncio
async def test_ungrounded_thought_rejected(ctx):
    r = await share(ctx, body="I have a feeling signups are seasonal.")
    assert "error" in r and "ungrounded" in r["error"]
    await settle()
    assert ctx.muted_posts == []


@pytest.mark.asyncio
async def test_grounded_thought_posts_a_badged_moment(ctx):
    r = await share(ctx, body="Signups spike on Mondays — see [[mission-domain]].")
    assert r.get("posted")
    await settle()
    (post,) = ctx.muted_posts
    assert post["channel"] == "moment"
    assert post["source"] == "curiosity"
    assert post["tools"] == comms.REFLECTION_TOOLS  # grounded reaction turn
    assert "[[mission-domain]]" in post["content"]


@pytest.mark.asyncio
async def test_url_counts_as_grounding(ctx):
    r = await share(ctx, body="Fresh finding: https://example.com/report shows a 20% lift.")
    assert r.get("posted")


@pytest.mark.asyncio
async def test_daily_cap_blocks_second_routine_thought(ctx):
    assert (await share(ctx, body="First insight [[mission-domain]].")).get("posted")
    r2 = await share(ctx, body="Second insight [[mission-domain]].")
    assert r2.get("blocked") and "cap" in r2["note"]
    await settle()
    assert len(ctx.muted_posts) == 1
    # non-routine kinds (kickoff/dream) are exempt from the routine cap
    r3 = await comms.share(
        ctx, ctx.reflections, body="Dream digest [[mission-domain]].", kind="dream"
    )
    assert r3.get("posted")


@pytest.mark.asyncio
async def test_quiet_hours_queue_and_morning_drain(ctx, monkeypatch):
    monkeypatch.setattr(comms, "in_quiet_hours", lambda now=None: True)
    r = await share(ctx, body="Night thought [[mission-domain]].")
    assert r.get("queued") and "quiet hours" in r["note"]
    await settle()
    assert ctx.muted_posts == []  # nothing posted at night

    monkeypatch.setattr(comms, "in_quiet_hours", lambda now=None: False)
    drained = await comms.drain_queue(ctx, ctx.reflections)
    assert drained["drained"] == 1
    await settle()
    assert len(ctx.muted_posts) == 1
    # the drained routine thought consumed today's cap
    r2 = await share(ctx, body="Another [[mission-domain]].")
    assert r2.get("blocked")


@pytest.mark.asyncio
async def test_drain_respects_cap_excess_stays_queued(ctx, monkeypatch):
    monkeypatch.setattr(comms, "in_quiet_hours", lambda now=None: True)
    await share(ctx, body="A [[mission-domain]].")
    await share(ctx, body="B [[mission-domain]].")

    monkeypatch.setattr(comms, "in_quiet_hours", lambda now=None: False)
    drained = await comms.drain_queue(ctx, ctx.reflections)
    assert drained["drained"] == 1  # cap = 1/day; the second waits for tomorrow
    assert len(await ctx.reflections.queued()) == 1


@pytest.mark.asyncio
async def test_quiet_hours_boundaries():
    from datetime import datetime

    mk = lambda h: datetime(2026, 7, 7, h, 0)  # noqa: E731
    assert _real_in_quiet_hours(mk(21))
    assert _real_in_quiet_hours(mk(23))
    assert _real_in_quiet_hours(mk(3))
    assert _real_in_quiet_hours(mk(7))
    assert not _real_in_quiet_hours(mk(8))
    assert not _real_in_quiet_hours(mk(12))
    assert not _real_in_quiet_hours(mk(20))


@pytest.mark.asyncio
async def test_share_thought_tooldef_policy(ctx):
    tool_def, _ = ctx.tool_registry.registered["share_thought"]
    assert tool_def.policy == "auto_approve"
    assert "wiki-page" in tool_def.description  # teaches grounding
