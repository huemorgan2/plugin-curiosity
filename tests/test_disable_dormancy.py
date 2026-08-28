"""0.26.0 (core 072): plugin OFF means dormant.

on_disable pauses (never deletes) the triggers curiosity answers for and
records the exact ids; on_enable resumes exactly that set; on_unload cancels
the pending on-load task; _plugin_disabled reads core's plugins registry and
fails open."""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import text

from plugin_curiosity import (
    PAUSED_BY_DISABLE_FLAG,
    CuriosityPlugin,
    _flag_get,
    _flag_set,
    _onload,
    _plugin_disabled,
)


def _plugin(ctx) -> CuriosityPlugin:
    p = CuriosityPlugin()
    p._ctx = ctx
    return p


@pytest.fixture(autouse=True)
def _clean_onload():
    saved = dict(_onload)
    _onload["loop"] = None
    _onload["task"] = None
    yield
    _onload.update(saved)


async def test_on_disable_pauses_owned_enabled_triggers_only(ctx, sf):
    ctx.tool_registry.existing_triggers = [
        {"id": "hb", "name": "curiosity-setup-heartbeat", "enabled": True},
        {"id": "dream", "name": "curiosity-nightly-dream", "enabled": True,
         "created_by": "plugin-curiosity"},
        {"id": "byid", "name": "renamed-by-agent", "enabled": True,
         "created_by": "plugin-curiosity"},
        {"id": "foreign", "name": "owner-daily-digest", "enabled": True},
        {"id": "already-off", "name": "curiosity-weekly-review", "enabled": False,
         "created_by": "plugin-curiosity"},
    ]
    await _plugin(ctx).on_disable()
    assert sorted(ctx.tool_registry.trigger_paused) == ["byid", "dream", "hb"]
    recorded = json.loads(await _flag_get(sf, PAUSED_BY_DISABLE_FLAG))
    assert sorted(recorded) == ["byid", "dream", "hb"]


async def test_on_enable_resumes_recorded_set_and_clears_flag(ctx, sf):
    await _flag_set(sf, PAUSED_BY_DISABLE_FLAG, json.dumps(["hb", "dream"]))
    await _plugin(ctx).on_enable()
    assert sorted(ctx.tool_registry.trigger_resumed) == ["dream", "hb"]
    assert await _flag_get(sf, PAUSED_BY_DISABLE_FLAG) is None


async def test_on_enable_without_record_is_a_noop(ctx):
    await _plugin(ctx).on_enable()
    assert ctx.tool_registry.trigger_resumed == []


async def test_on_disable_without_scheduler_is_safe(ctx):
    ctx.tool_registry.scheduler_installed = False
    await _plugin(ctx).on_disable()  # must not raise
    assert ctx.tool_registry.trigger_paused == []


async def test_on_unload_cancels_pending_onload_task(ctx):
    async def _sleeper():
        await asyncio.sleep(60)

    task = asyncio.get_running_loop().create_task(_sleeper())
    _onload["task"] = task
    _onload["loop"] = asyncio.get_running_loop()
    await _plugin(ctx).on_unload()
    await asyncio.sleep(0)
    assert task.cancelled()
    assert _onload["task"] is None and _onload["loop"] is None


async def test_plugin_disabled_reads_core_registry(sf):
    async with sf() as s:
        await s.execute(text("CREATE TABLE plugins (name TEXT PRIMARY KEY, enabled BOOLEAN)"))
        await s.execute(text("INSERT INTO plugins (name, enabled) VALUES ('plugin-curiosity', 0)"))
        await s.commit()
    assert await _plugin_disabled(sf) is True
    async with sf() as s:
        await s.execute(text("UPDATE plugins SET enabled = 1 WHERE name = 'plugin-curiosity'"))
        await s.commit()
    assert await _plugin_disabled(sf) is False


async def test_plugin_disabled_fails_open_without_table(sf):
    assert await _plugin_disabled(sf) is False
