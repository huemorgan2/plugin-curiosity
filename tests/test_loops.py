"""Open-loops ledger + ask economics + value log (9B): nudge ladder, one-ask
law, fresh-value requirement, mirrors, daily-prompt patrol step."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def lstore(sf, store):
    from plugin_curiosity.loops import LoopStore

    await store.set("own the weekly newsletter end to end")
    return LoopStore(sf)


@pytest.fixture
def lctx(ctx, lstore):
    from plugin_curiosity.loops import register_tools

    register_tools(ctx, lstore)
    return ctx


async def call(ctx, tool, **kw):
    return await ctx.tool_registry.registered[tool][1](**kw)


@pytest.mark.asyncio
async def test_loop_round_trip_non_ask_kinds(lstore):
    from plugin_curiosity.loops import LOOP_KINDS

    for kind in LOOP_KINDS:
        if kind == "ask":
            continue
        lp = await lstore.open(kind, f"thread for {kind}", who="sam")
        assert lp["status"] == "open" and lp["kind"] == kind
        assert lp["next_nudge_at"] is not None and lp["nudge_count"] == 0
    assert len(await lstore.list(status="open")) == len(LOOP_KINDS) - 1
    with pytest.raises(ValueError):
        await lstore.open("bogus", "x")
    with pytest.raises(ValueError):
        await lstore.open("question", "   ")
    with pytest.raises(ValueError):
        await lstore.list(status="bogus")


@pytest.mark.asyncio
async def test_loop_requires_active_mission(sf):
    from plugin_curiosity.loops import LoopStore

    empty = LoopStore(sf)
    with pytest.raises(ValueError, match="no active mission"):
        await empty.open("question", "who is the audience?")
    assert await empty.list() == []
    assert await empty.value_list() == []


def test_nudge_ladder_pure_function():
    from plugin_curiosity.loops import next_nudge

    now = datetime(2026, 7, 9, 12, 0)
    assert next_nudge(now, 0) == now + timedelta(days=2)
    assert next_nudge(now, 1) == now + timedelta(days=5)
    assert next_nudge(now, 2) == now + timedelta(days=7)
    assert next_nudge(now, 9) == now + timedelta(days=7)


@pytest.mark.asyncio
async def test_nudge_advances_ladder_open_only(lstore):
    lp = await lstore.open("waiting_on", "IG login from owner")
    n1 = await lstore.nudge(lp["id"])
    assert n1["nudge_count"] == 1
    n2 = await lstore.nudge(lp["id"])
    assert n2["nudge_count"] == 2 and n2["next_nudge_at"] > n1["next_nudge_at"]
    await lstore.close(lp["id"], "answered", "got it")
    with pytest.raises(ValueError, match="only open loops"):
        await lstore.nudge(lp["id"])
    with pytest.raises(LookupError):
        await lstore.nudge(str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_abandon_requires_resolution(lstore):
    lp = await lstore.open("promise", "draft five captions by friday")
    with pytest.raises(ValueError, match="REQUIRES a resolution"):
        await lstore.close(lp["id"], "abandoned")
    closed = await lstore.close(lp["id"], "abandoned", "owner cancelled the campaign")
    assert closed["status"] == "abandoned" and closed["closed_at"]
    assert closed["next_nudge_at"] is None
    with pytest.raises(ValueError):
        await lstore.close(lp["id"], "open")
    with pytest.raises(LookupError):
        await lstore.close(str(uuid.uuid4()), "closed", "x")


@pytest.mark.asyncio
async def test_ask_economics_unlock_and_value_ref_required(lstore):
    # non-ask kinds need neither
    q = await lstore.open("question", "which product sells best?")
    assert q["unlock"] == "" and q["value_ref"] is None

    with pytest.raises(ValueError, match="needs `unlock`"):
        await lstore.open("ask", "connect my WhatsApp", value_ref=str(uuid.uuid4()))
    with pytest.raises(ValueError, match="needs `value_ref`"):
        await lstore.open("ask", "connect my WhatsApp", unlock="reach you off-platform")
    with pytest.raises(ValueError, match="not a value-log id"):
        await lstore.open("ask", "x", unlock="y", value_ref="not-a-uuid")
    with pytest.raises(ValueError, match="no value-log entry"):
        await lstore.open("ask", "x", unlock="y", value_ref=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_one_ask_at_a_time(lstore):
    v = await lstore.value_add("shipped the audience map", "[[audience-map]]")
    a1 = await lstore.open("ask", "grant analytics access", unlock="see real funnels",
                           value_ref=v["id"])
    with pytest.raises(ValueError, match="One ask at a time"):
        await lstore.open("ask", "also connect WhatsApp", unlock="off-platform reach",
                          value_ref=v["id"])
    await lstore.close(a1["id"], "answered", "granted")
    # value v now predates the last closed ask — a new ask can't ride it
    with pytest.raises(ValueError, match="Deliver value first"):
        await lstore.open("ask", "connect WhatsApp", unlock="off-platform reach",
                          value_ref=v["id"])
    v2 = await lstore.value_add("used the grant: funnel report", "[[funnel-report]]",
                                linked_ask_id=a1["id"])
    a2 = await lstore.open("ask", "connect WhatsApp", unlock="off-platform reach",
                           value_ref=v2["id"])
    assert a2["status"] == "open" and a2["value_ref"] == v2["id"]


@pytest.mark.asyncio
async def test_fresh_value_boundary_exact(lstore, sf):
    """value delivered_at == last ask closed_at is NOT fresh (<= rejects)."""
    from sqlalchemy import select

    from plugin_curiosity.models import Loop, ValueEntry

    v = await lstore.value_add("first win", "[[win-1]]")
    a = await lstore.open("ask", "first ask", unlock="u", value_ref=v["id"])
    await lstore.close(a["id"], "answered", "granted")
    v2 = await lstore.value_add("second win", "[[win-2]]")
    # force delivered_at to exactly the ask's closed_at
    async with sf() as s:
        ask = await s.get(Loop, uuid.UUID(a["id"]))
        entry = await s.get(ValueEntry, uuid.UUID(v2["id"]))
        entry.delivered_at = ask.closed_at
        await s.commit()
    with pytest.raises(ValueError, match="Deliver value first"):
        await lstore.open("ask", "second ask", unlock="u", value_ref=v2["id"])
    async with sf() as s:
        entry = await s.get(ValueEntry, uuid.UUID(v2["id"]))
        entry.delivered_at = entry.delivered_at + timedelta(microseconds=1)
        await s.commit()
    a2 = await lstore.open("ask", "second ask", unlock="u", value_ref=v2["id"])
    assert a2["status"] == "open"


@pytest.mark.asyncio
async def test_value_log_requires_evidence(lstore):
    with pytest.raises(ValueError, match="needs evidence"):
        await lstore.value_add("did a thing", "  ")
    with pytest.raises(ValueError):
        await lstore.value_add("  ", "[[page]]")
    v = await lstore.value_add("posted the plan", "[[content-plan]]")
    entries = await lstore.value_list()
    assert entries[0]["id"] == v["id"] and entries[0]["evidence"] == "[[content-plan]]"


@pytest.mark.asyncio
async def test_tool_policies_and_steering_errors(lctx):
    for name in ("loop_open", "loop_close", "loop_nudge", "loop_list", "value_log_add"):
        tool_def, _ = lctx.tool_registry.registered[name]
        assert tool_def.policy == "auto_approve", name
    # handlers return steering errors, never raise
    res = await call(lctx, "loop_open", kind="ask", statement="gimme access")
    assert "unlock" in res["error"]
    res = await call(lctx, "loop_close", id=str(uuid.uuid4()), status="closed")
    assert "error" in res
    res = await call(lctx, "loop_list")
    assert res["loops"] == [] and "never silently dies" in res["note"]


@pytest.mark.asyncio
async def test_mirrors_write_through(lctx):
    wiki = lctx.provider_registry.get("wiki")
    res = await call(lctx, "loop_open", kind="question",
                     statement="who actually buys the planters?", who="owner")
    assert res["wiki_mirror"] == "ok"
    body = wiki.pages["open-loops"]["body"]
    assert "who actually buys the planters?" in body and "❓" in body

    v = await call(lctx, "value_log_add", statement="shipped week-1 content plan",
                   evidence="[[content-plan]] five posts, ready to use")
    assert v["wiki_mirror"] == "ok"
    vbody = wiki.pages["value-log"]["body"]
    assert "[[content-plan]] five posts, ready to use" in vbody  # evidence verbatim

    a = await call(lctx, "loop_open", kind="ask", statement="connect WhatsApp",
                   unlock="mission continues when the tab closes",
                   value_ref=v["value"]["id"])
    body = wiki.pages["open-loops"]["body"]
    assert "🙏" in body and "unlocks: mission continues when the tab closes" in body

    await call(lctx, "loop_close", id=a["loop"]["id"], status="answered",
               resolution="owner connected it")
    body = wiki.pages["open-loops"]["body"]
    assert "Recently closed" in body and "owner connected it" in body


@pytest.mark.asyncio
async def test_loop_mirrors_seeded_on_upgrade_load(lctx, lstore):
    """A pre-9B mission (no loop pages) gets both mirrors on load."""
    from plugin_curiosity.loops import ensure_loop_mirrors

    wiki = lctx.provider_registry.get("wiki")
    assert "open-loops" not in wiki.pages and "value-log" not in wiki.pages
    assert await ensure_loop_mirrors(lctx, lstore) == "ok"
    assert "open-loops" in wiki.pages and "value-log" in wiki.pages
    assert "No open loops" in wiki.pages["open-loops"]["body"]
    assert "No value logged yet" in wiki.pages["value-log"]["body"]
    assert await ensure_loop_mirrors(lctx, lstore) == "already present"


@pytest.mark.asyncio
async def test_loop_mirror_degrades_without_wiki(lstore):
    import types

    from conftest import FakeToolRegistry

    from plugin_curiosity.loops import register_tools

    class _NoWiki:
        def get(self, name):
            raise KeyError(name)

    c = types.SimpleNamespace(tool_registry=FakeToolRegistry(), provider_registry=_NoWiki())
    register_tools(c, lstore)
    res = await c.tool_registry.registered["loop_open"][1](
        kind="promise", statement="weekly digest every monday")
    assert res["loop"]["statement"] == "weekly digest every monday"
    assert "not mirrored" in res["wiki_mirror"]


def test_daily_prompt_has_loop_patrol():
    from plugin_curiosity.research import DAILY_RESEARCH_TARGET

    assert "0. LOOP PATROL" in DAILY_RESEARCH_TARGET
    assert DAILY_RESEARCH_TARGET.index("LOOP PATROL") < DAILY_RESEARCH_TARGET.index("mission_get")
    assert "UNUSED-GRANT CHECK" in DAILY_RESEARCH_TARGET
    assert "loop_nudge" in DAILY_RESEARCH_TARGET and "loop_close" in DAILY_RESEARCH_TARGET


def test_stub_slugs_include_loop_pages():
    from plugin_curiosity.mission import _STUB_SLUGS

    assert "open-loops" in _STUB_SLUGS and "value-log" in _STUB_SLUGS
