"""Phase-2 acceptance: mission store semantics, write-through, wiki stubs,
schedule registration, prompt fragment."""

from __future__ import annotations

import pytest


async def call(ctx, tool: str, **kwargs):
    return await ctx.tool_registry.registered[tool][1](**kwargs)


@pytest.mark.asyncio
async def test_mission_set_creates_single_active_row(ctx, store):
    r1 = await call(ctx, "mission_set", statement="grow signups", rung=2)
    assert r1["mission"]["active"] and r1["mission"]["autonomy_rung"] == 2

    r2 = await call(ctx, "mission_set", statement="ship the mobile app")
    assert r2["mission"]["statement"] == "ship the mobile app"

    active = await store.get()
    assert active["statement"] == "ship the mobile app"
    # exactly one active row is enforced at the store level
    async with store._sf() as s:  # noqa: SLF001
        from sqlalchemy import func, select

        from plugin_curiosity.models import Mission

        n_active = (
            await s.execute(select(func.count(Mission.id)).where(Mission.active))
        ).scalar_one()
        n_total = (await s.execute(select(func.count(Mission.id)))).scalar_one()
    assert n_active == 1 and n_total == 2


@pytest.mark.asyncio
async def test_mission_set_validation(ctx):
    assert "error" in await call(ctx, "mission_set", statement="   ")
    assert "error" in await call(ctx, "mission_set", statement="x", rung=5)
    assert "error" in await call(ctx, "mission_set", statement="x", risk_ceiling="extreme")


@pytest.mark.asyncio
async def test_write_through_to_identity(ctx):
    await call(ctx, "mission_set", statement="grow signups")
    assert ctx.config_registry.writes == [{"mission": "grow signups"}]

    await call(ctx, "mission_refine", statement="grow signups by 20%")
    assert ctx.config_registry.writes[-1] == {"mission": "grow signups by 20%"}

    # rung-only refine must NOT touch identity
    n = len(ctx.config_registry.writes)
    await call(ctx, "mission_refine", rung=3)
    assert len(ctx.config_registry.writes) == n


@pytest.mark.asyncio
async def test_mission_set_seeds_wiki_stubs(ctx):
    r = await call(ctx, "mission_set", statement="grow signups")
    wiki = ctx.provider_registry.get("wiki")
    assert "mission" in wiki.pages
    assert "grow signups" in wiki.pages["mission"]["body"]
    stubs = [s for s in wiki.pages if s.startswith("mission-")]
    assert 2 <= len(stubs) <= 4
    # the hub links every stub so the graph is connected from day one
    for s in stubs:
        assert f"[[{s}]]" in wiki.pages["mission"]["body"]
    assert "seeded" in r["wiki_stubs"]


@pytest.mark.asyncio
async def test_remission_set_rewrites_hub_keeps_stub_bodies(ctx):
    await call(ctx, "mission_set", statement="grow signups")
    wiki = ctx.provider_registry.get("wiki")
    wiki.pages["mission-domain"]["body"] = "hand-researched content"
    n_upserts = len(wiki.upserts)

    await call(ctx, "mission_set", statement="ship the app")
    assert "ship the app" in wiki.pages["mission"]["body"]  # hub rewritten
    assert wiki.pages["mission-domain"]["body"] == "hand-researched content"  # stub kept
    assert len(wiki.upserts) == n_upserts + 1  # only the hub


@pytest.mark.asyncio
async def test_mission_set_registers_schedules_idempotently(ctx):
    from plugin_curiosity.mission import MISSION_SCHEDULES

    r = await call(ctx, "mission_set", statement="grow signups")
    created = ctx.tool_registry.trigger_created
    assert {c["name"] for c in created} == {s["name"] for s in MISSION_SCHEDULES}
    assert all(c["action_type"] == "agent_prompt" for c in created)
    assert "created" in r["schedules"]

    # second set: triggers already exist -> no duplicates
    await call(ctx, "mission_set", statement="ship the app")
    assert len(ctx.tool_registry.trigger_created) == len(MISSION_SCHEDULES)


@pytest.mark.asyncio
async def test_missing_peers_degrade_gracefully(ctx, store):
    ctx.tool_registry.scheduler_installed = False
    ctx.provider_registry._wiki = None  # noqa: SLF001
    ctx.config_registry._has_identity = False  # noqa: SLF001

    r = await call(ctx, "mission_set", statement="grow signups")
    assert r["mission"]["statement"] == "grow signups"  # the write itself succeeds
    assert "unavailable" in r["identity_sync"]
    assert "unavailable" in r["wiki_stubs"]
    assert "not installed" in r["schedules"]
    assert (await store.get())["statement"] == "grow signups"


@pytest.mark.asyncio
async def test_refine_and_get(ctx):
    assert (await call(ctx, "mission_get"))["mission"] is None
    assert "error" in await call(ctx, "mission_refine", rung=2)  # nothing to refine

    await call(ctx, "mission_set", statement="grow signups")
    r = await call(ctx, "mission_refine", rung=3, risk_ceiling="medium")
    assert r["mission"]["autonomy_rung"] == 3
    assert r["mission"]["risk_ceiling"] == "medium"
    assert r["mission"]["statement"] == "grow signups"

    got = (await call(ctx, "mission_get"))["mission"]
    assert got["autonomy_rung"] == 3 and got["active"]


@pytest.mark.asyncio
async def test_prompt_fragment(ctx, store):
    from plugin_curiosity.mission import prompt_fragment

    empty = prompt_fragment(None)
    assert "no active mission" in empty and "mission_set" in empty
    # mission-first onboarding (phase 6): the no-mission state actively asks
    # for a mission FIRST — before the onboarding checklist's name/emoji —
    # and bridges the adopted mission into identity via update_self
    assert "FIRST exchange" in empty and "before name or emoji" in empty
    # 0.4.3: the ask renews on every reply until a mission lands, with fresh
    # framing each time — a skipped first ask must not go silent forever
    assert "EVERY reply" in empty and "fresh framing" in empty
    assert "update_self" in empty
    assert "IN THAT SAME TURN" in empty and "never" in empty

    await call(ctx, "mission_set", statement="grow signups", rung=2)
    frag = prompt_fragment(await store.get())
    assert "grow signups" in frag
    assert "rung 2/4" in frag
    # the action rails are taught in both states
    for text in (empty, frag):
        assert "trigger_" in text and "playbook_propose" in text
