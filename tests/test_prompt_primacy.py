"""Prompt primacy (8.1B): the prompt.assemble reorder handler.

The handler runs against the real hook contract on new cores, but the tests
exercise it directly with fake section objects — the contract (only reorder,
never touch foreign text) is enforced and tested core-side in luna's
tests/025-prompt-assemble; here we assert the handler's own behavior.

v2 semantics (after live QA): the onboarding addendum is a plugin-onboarding
section near the END of the prompt, where recency wins — so the missionless
fragment moves to immediately AFTER the onboarding section, not before it.
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
async def test_missionless_moves_own_sections_after_onboarding():
    """Realistic shape: the addendum is a plugin-onboarding section that sits
    BEFORE the curiosity fragment only because of load order, with other
    plugin sections in between. The fragment must land directly after it."""
    p = _plugin_with_mission(None)
    core, pers, onboarding, wiki, own = (
        _sec("core"),
        _sec("core.personality"),
        _sec("plugin-onboarding", "setup checklist"),
        _sec("plugin-wiki"),
        _sec("plugin-curiosity", "mission ask"),
    )
    hctx = types.SimpleNamespace(sections=[core, pers, onboarding, wiki, own])
    await p._reorder_prompt(hctx)
    assert hctx.sections == [core, pers, onboarding, own, wiki]


@pytest.mark.asyncio
async def test_core_onboarding_anchor_supported():
    """Cores that pass the addendum as a core section (source
    core.onboarding) anchor the same way: fragment directly after it."""
    p = _plugin_with_mission(None)
    core, onboarding, pers, own = (
        _sec("core"),
        _sec("core.onboarding"),
        _sec("core.personality"),
        _sec("plugin-curiosity", "mission ask"),
    )
    hctx = types.SimpleNamespace(sections=[core, onboarding, pers, own])
    await p._reorder_prompt(hctx)
    assert hctx.sections == [core, onboarding, own, pers]


@pytest.mark.asyncio
async def test_fragment_already_after_onboarding_is_stable():
    p = _plugin_with_mission(None)
    core, onboarding, own = _sec("core"), _sec("plugin-onboarding"), _sec("plugin-curiosity")
    hctx = types.SimpleNamespace(sections=[core, onboarding, own])
    await p._reorder_prompt(hctx)
    assert hctx.sections == [core, onboarding, own]


@pytest.mark.asyncio
async def test_no_onboarding_anchor_leaves_order_alone():
    """Setup complete (no addendum) but missionless: appended-at-end is
    already maximal recency — the handler must not move anything."""
    p = _plugin_with_mission(None)
    core, pers, own, wiki = (
        _sec("core"),
        _sec("core.personality"),
        _sec("plugin-curiosity"),
        _sec("plugin-wiki"),
    )
    hctx = types.SimpleNamespace(sections=[core, pers, own, wiki])
    await p._reorder_prompt(hctx)
    assert hctx.sections == [core, pers, own, wiki]


@pytest.mark.asyncio
async def test_mission_set_leaves_order_alone():
    p = _plugin_with_mission({"statement": "grow signups"})
    core, own, onboarding = _sec("core"), _sec("plugin-curiosity"), _sec("plugin-onboarding")
    hctx = types.SimpleNamespace(sections=[core, own, onboarding])
    await p._reorder_prompt(hctx)
    assert hctx.sections == [core, own, onboarding]


@pytest.mark.asyncio
async def test_handler_never_touches_foreign_sections():
    p = _plugin_with_mission(None)
    foreign = [_sec("core", "a"), _sec("plugin-onboarding", "b"), _sec("plugin-wiki", "c")]
    own = _sec("plugin-curiosity", "mine")
    hctx = types.SimpleNamespace(sections=[own, *foreign])
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
    assert registrations == [("prompt.assemble", p._occupy_prompt, 60)]

    # older core: no hooks attribute — load must not raise
    pc._onload["loop"] = None
    del ctx.hooks
    await CuriosityPlugin().on_load(ctx)
    await engine.dispose()
