"""Prompt primacy (8.1B): the prompt.assemble reorder handler.

The handler runs against the real hook contract on new cores, but the tests
exercise it directly with fake section objects — the contract (only reorder,
never touch foreign text) is enforced and tested core-side in luna's
tests/025-prompt-assemble; here we assert the handler's own behavior.
"""

from __future__ import annotations

import types

import pytest

from plugin_curiosity import CuriosityPlugin


def _sec(source: str, text: str = "x") -> types.SimpleNamespace:
    return types.SimpleNamespace(source=source, text=text)


def _plugin_with_mission(mission) -> CuriosityPlugin:
    p = CuriosityPlugin()

    class _Store:
        async def get(self):
            return mission

    p._store = _Store()
    return p


@pytest.mark.asyncio
async def test_missionless_moves_own_sections_before_onboarding():
    p = _plugin_with_mission(None)
    core, tools, own, onboarding, pers = (
        _sec("core"),
        _sec("core"),
        _sec("plugin-curiosity", "mission ask"),
        _sec("core.onboarding"),
        _sec("core.personality"),
    )
    hctx = types.SimpleNamespace(sections=[core, tools, onboarding, pers, own])
    await p._reorder_prompt(hctx)
    assert hctx.sections == [core, tools, own, onboarding, pers]


@pytest.mark.asyncio
async def test_personality_is_the_fallback_anchor():
    p = _plugin_with_mission(None)
    core, own, pers = _sec("core"), _sec("plugin-curiosity"), _sec("core.personality")
    hctx = types.SimpleNamespace(sections=[core, pers, own])
    await p._reorder_prompt(hctx)
    assert hctx.sections == [core, own, pers]


@pytest.mark.asyncio
async def test_no_anchor_keeps_appended_position():
    p = _plugin_with_mission(None)
    core, own = _sec("core"), _sec("plugin-curiosity")
    hctx = types.SimpleNamespace(sections=[core, own])
    await p._reorder_prompt(hctx)
    assert hctx.sections == [core, own]


@pytest.mark.asyncio
async def test_mission_set_leaves_order_alone():
    p = _plugin_with_mission({"statement": "grow signups"})
    core, onboarding, own = _sec("core"), _sec("core.onboarding"), _sec("plugin-curiosity")
    hctx = types.SimpleNamespace(sections=[core, onboarding, own])
    await p._reorder_prompt(hctx)
    assert hctx.sections == [core, onboarding, own]


@pytest.mark.asyncio
async def test_handler_never_touches_foreign_sections():
    p = _plugin_with_mission(None)
    foreign = [_sec("core", "a"), _sec("plugin-wiki", "b"), _sec("core.onboarding", "c")]
    own = _sec("plugin-curiosity", "mine")
    hctx = types.SimpleNamespace(sections=[*foreign, own])
    await p._reorder_prompt(hctx)
    # every foreign object survives, identical and in relative order
    assert [s for s in hctx.sections if s is not own] == foreign
    assert [s.text for s in foreign] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_no_store_is_a_noop():
    p = CuriosityPlugin()  # on_load never ran
    sections = [_sec("core"), _sec("plugin-curiosity")]
    hctx = types.SimpleNamespace(sections=list(sections))
    await p._reorder_prompt(hctx)
    assert hctx.sections == sections


@pytest.mark.asyncio
async def test_on_load_registers_hook_when_core_offers_it(ctx, sf, monkeypatch):
    """Full on_load on a core WITH ctx.hooks: handler registered at priority
    60; on a core WITHOUT ctx.hooks the load stays clean (feature detect)."""
    import plugin_curiosity as pc
    from sqlalchemy.ext.asyncio import create_async_engine

    monkeypatch.setattr(pc, "SYNC_ON_LOAD_DELAY_S", 0)
    pc._onload["loop"] = None  # reset the loop-identity guard between tests

    registrations = []

    class _Hooks:
        def register(self, pointcut, handler, priority=100):
            registrations.append((pointcut, handler, priority))

    engine = create_async_engine("sqlite+aiosqlite://")
    ctx.engine = engine
    ctx.db_session_factory = sf
    ctx.hooks = _Hooks()

    p = CuriosityPlugin()
    await p.on_load(ctx)
    assert registrations == [("prompt.assemble", p._reorder_prompt, 60)]

    # older core: no hooks attribute — load must not raise
    pc._onload["loop"] = None
    del ctx.hooks
    await CuriosityPlugin().on_load(ctx)
    await engine.dispose()
