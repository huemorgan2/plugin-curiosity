"""Phase-5 acceptance: the nightly-dream trigger target, schedule-expr drift
re-sync, and the sync-on-load task that refreshes an existing mission's
schedules after a plugin upgrade."""

from __future__ import annotations

import asyncio

import pytest

import plugin_curiosity
from plugin_curiosity import dream
from plugin_curiosity.mission import MISSION_SCHEDULES


async def call(ctx, tool: str, **kwargs):
    return await ctx.tool_registry.registered[tool][1](**kwargs)


async def _spin(n: int = 10) -> None:
    # real (tiny) sleeps: the on-load task awaits aiosqlite thread hops that
    # a bare sleep(0) spin never yields long enough for
    for _ in range(n):
        await asyncio.sleep(0.02)


def test_dream_target_is_wired():
    entry = next(s for s in MISSION_SCHEDULES if s["name"] == "curiosity-nightly-dream")
    assert entry["target"] == dream.DREAM_TARGET
    assert "Placeholder" not in entry["target"]
    # 02:00 = quiet hours (share_thought queues until morning) + dead hours
    assert entry["schedule_expr"] == "every day at 02:00"
    # the fired routine teaches the full consolidation loop: re-read the
    # mission, consolidate touched pages, tend the question ledger, distill
    # ONE morning thought, and no-op gracefully on a quiet day
    for marker in (
        "mission_get",
        "wiki_toc",
        "wiki_patch",
        "wiki_resolve_question",
        "share_thought",
        "Morning thought",
        "nothing to consolidate",
    ):
        assert marker in entry["target"]
    # self-contained: no mission text is baked in, the prompt re-reads it
    assert "{" not in entry["target"]


@pytest.mark.asyncio
async def test_sync_patches_schedule_expr_drift(ctx):
    """A trigger with the current target but an old fire time (0.3.0 shipped
    03:30) is PATCHed to the new schedule — and only the drifted field."""
    ctx.tool_registry.existing_triggers = [
        {"id": "trg-dream", "name": "curiosity-nightly-dream",
         "target": dream.DREAM_TARGET, "expr_raw": "every day at 03:30",
         "enabled": True},
    ]
    await call(ctx, "mission_set", statement="grow signups")
    (updated,) = [u for u in ctx.tool_registry.trigger_updated if u["id"] == "trg-dream"]
    assert updated["schedule_expr"] == "every day at 02:00"
    assert "target" not in updated


@pytest.fixture(autouse=True)
def fresh_onload_guard(monkeypatch):
    monkeypatch.setattr(plugin_curiosity, "SYNC_ON_LOAD_DELAY_S", 0)
    monkeypatch.setattr(plugin_curiosity, "_onload", {"loop": None, "task": None})


@pytest.mark.asyncio
async def test_sync_on_load_refreshes_existing_mission(ctx, store):
    await store.set("grow signups")
    ctx.tool_registry.existing_triggers = [
        {"id": "trg-dream", "name": "curiosity-nightly-dream",
         "target": "old placeholder", "expr_raw": "every day at 03:30",
         "enabled": True},
        {"id": "trg-research", "name": "curiosity-daily-research",
         "target": "old placeholder", "expr_raw": "every day at 09:00",
         "enabled": True},
    ]
    plugin_curiosity.schedule_on_load_work(ctx, store, ctx.reflections)
    await _spin()
    assert {u["id"] for u in ctx.tool_registry.trigger_updated} == {
        "trg-dream", "trg-research"
    }


@pytest.mark.asyncio
async def test_sync_on_load_noop_without_mission(ctx, store):
    plugin_curiosity.schedule_on_load_work(ctx, store, ctx.reflections)
    await _spin()
    # no mission -> the sync never touches the scheduler
    assert ctx.tool_registry.trigger_created == []
    assert ctx.tool_registry.trigger_updated == []


@pytest.mark.asyncio
async def test_on_load_work_scheduled_once_per_loop(ctx, store):
    """Both call sites (on_load + the routes startup hook) can fire on the
    same loop — the second must be a no-op or the drain could double-post."""
    await store.set("grow signups")
    ctx.tool_registry.existing_triggers = [
        {"id": "trg-dream", "name": "curiosity-nightly-dream",
         "target": "old placeholder", "expr_raw": "every day at 03:30",
         "enabled": True},
    ]
    plugin_curiosity.schedule_on_load_work(ctx, store, ctx.reflections)
    plugin_curiosity.schedule_on_load_work(ctx, store, ctx.reflections)
    await _spin()
    dream_updates = [u for u in ctx.tool_registry.trigger_updated if u["id"] == "trg-dream"]
    assert len(dream_updates) == 1
