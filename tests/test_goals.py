"""Goal ledger (8.2A): store round-trip, wiki write-through, tool surface."""

from __future__ import annotations

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def gstore(sf):
    from plugin_curiosity.goals import GoalStore

    return GoalStore(sf)


@pytest.fixture
def gctx(ctx, gstore):
    from plugin_curiosity.goals import register_tools

    register_tools(ctx, gstore)
    return ctx


async def call(ctx, name, **kw):
    return await ctx.tool_registry.registered[name][1](**kw)


@pytest.mark.asyncio
async def test_goal_round_trip(gstore):
    g = await gstore.add("ship the widget", why="mission", target_date="2026-08-01")
    assert g["status"] == "active" and g["target_date"] == "2026-08-01"
    g2 = await gstore.update(g["id"], status="stalled", progress_note="blocked on API")
    assert g2["status"] == "stalled" and g2["progress_note"] == "blocked on API"
    all_goals = await gstore.list()
    assert [x["id"] for x in all_goals] == [g["id"]]
    assert await gstore.list(include_closed=False)  # stalled still shown
    await gstore.update(g["id"], status="done")
    assert await gstore.list(include_closed=False) == []


@pytest.mark.asyncio
async def test_goal_validation(gstore):
    with pytest.raises(ValueError):
        await gstore.add("   ")
    g = await gstore.add("real goal")
    with pytest.raises(ValueError):
        await gstore.update(g["id"], status="bogus")
    with pytest.raises(LookupError):
        await gstore.update("00000000-0000-0000-0000-000000000000")


def test_render_goals_page():
    from plugin_curiosity.goals import render_goals_page

    empty = render_goals_page([])
    assert "No goals committed yet" in empty and "goal_set" in empty
    body = render_goals_page(
        [
            {
                "statement": "ship the widget",
                "why": "mission",
                "target_date": "2026-08-01",
                "status": "active",
                "progress_note": "drafted",
            }
        ]
    )
    assert "ship the widget" in body and "2026-08-01" in body
    assert "🎯" in body and "[[mission]]" in body


@pytest.mark.asyncio
async def test_goal_tools_registered_auto_approve(gctx):
    for name in ("goal_set", "goal_update", "goal_list"):
        tool_def, _ = gctx.tool_registry.registered[name]
        assert tool_def.policy == "auto_approve"
        assert tool_def.risk_level == "low"


@pytest.mark.asyncio
async def test_goal_set_mirrors_to_wiki(gctx):
    res = await call(gctx, "goal_set", statement="ship the widget", target_date="2026-08-01")
    assert res["goal"]["status"] == "active"
    assert res["wiki_mirror"] == "ok"
    wiki = gctx.provider_registry.get("wiki")
    assert "mission-goals" in wiki.upserts
    assert "ship the widget" in wiki.pages["mission-goals"]["body"]

    upd = await call(gctx, "goal_update", id=res["goal"]["id"], status="done")
    assert upd["goal"]["status"] == "done"
    assert "✅" in wiki.pages["mission-goals"]["body"]


@pytest.mark.asyncio
async def test_goal_list_empty_prompts_commitment(gctx):
    res = await call(gctx, "goal_list")
    assert res["goals"] == [] and "goal_set" in res["note"]


@pytest.mark.asyncio
async def test_goal_tools_degrade_without_wiki(gstore, sf):
    import types

    from plugin_curiosity.goals import register_tools

    class _NoWiki:
        def get(self, name):
            raise KeyError(name)

    c = types.SimpleNamespace(
        tool_registry=__import__("conftest").FakeToolRegistry(),
        provider_registry=_NoWiki(),
    )
    register_tools(c, gstore)
    res = await c.tool_registry.registered["goal_set"][1](statement="x")
    assert res["goal"]["statement"] == "x"
    assert "not mirrored" in res["wiki_mirror"]
