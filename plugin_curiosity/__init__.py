"""plugin-curiosity — mission-driven curiosity for Luna.

The behavior plugin: give Luna a mission and she teaches herself the domain —
researching, filling her wiki (plugin-wiki), dreaming nightly to consolidate,
and proactively sharing grounded reflections. Consumes the "wiki" provider.
Authored against `luna_sdk` only.
"""

from __future__ import annotations

import asyncio
import logging

from luna_sdk import LunaPlugin, PluginContext, PluginManifest

from . import comms, mission
from .mission import MissionStore, prompt_fragment, register_tools
from .models import ALL_TABLES

log = logging.getLogger("plugin-curiosity")

# Grace period before the on-load schedule sync: on a runtime plugin install
# other plugins (notably plugin-scheduler, whose trigger_* tools the sync
# calls) may still be loading. Tests set this to 0.
SYNC_ON_LOAD_DELAY_S = 15.0

# Loop-identity guard for the one-time on-load work. Under `luna serve` the
# plugin's on_load runs inside a throwaway bootstrap loop (asyncio.run in
# cli.py) — tasks created there die when that loop is disposed — and the
# routes startup hook is what lands in uvicorn's serving loop. On a runtime
# plugin install the serving loop is already started (the startup hook never
# fires) and the on_load call lands. Keying the guard on the loop lets both
# call sites schedule safely: the second call on the SAME loop is a no-op,
# while a fresh loop (the real serving loop after bootstrap) runs the work.
_onload: dict = {"loop": None, "task": None}


def schedule_on_load_work(
    ctx: PluginContext, store: MissionStore, reflections: comms.ReflectionLog
) -> None:
    """Schedule the one-time on-load work on the current loop: drain any
    overnight-queued thoughts, then refresh the mission's recurring triggers
    (a plugin upgrade that changes a trigger target or fire time must reach
    an existing mission without waiting for a mission_set/mission_refine)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _onload["loop"] is loop:
        return
    _onload["loop"] = loop

    async def _run() -> None:
        try:
            result = await comms.drain_queue(ctx, reflections)
            if result.get("drained"):
                log.info("drained %s queued thought(s) on load", result["drained"])
        except Exception:  # noqa: BLE001
            log.warning("queued-thought drain on load failed", exc_info=True)
        try:
            await asyncio.sleep(SYNC_ON_LOAD_DELAY_S)
            if await store.get() is None:
                return  # no mission — mission_set will register schedules
            result = await mission._sync_schedules(ctx)
            if result != "already registered":
                log.info("schedule sync on load: %s", result)
        except Exception:  # noqa: BLE001
            log.warning("schedule sync on load failed", exc_info=True)

    # keep a strong ref — the loop itself only holds weak refs to tasks, and
    # a task sleeping through boot would otherwise be GC-able mid-flight
    _onload["task"] = loop.create_task(_run())


class CuriosityPlugin(LunaPlugin):
    manifest = PluginManifest(
        name="plugin-curiosity",
        version="0.4.0",
        description="Mission-driven curiosity: research, wiki-building, nightly dreams, proactive reflections.",
        capabilities=["wiki"],
        db_tables=[t.name for t in ALL_TABLES],
        routes_module="routes",
    )

    def __init__(self) -> None:
        self._store: MissionStore | None = None
        self._reflections: comms.ReflectionLog | None = None

    async def on_load(self, ctx: PluginContext) -> None:
        async with ctx.engine.begin() as conn:
            for table in ALL_TABLES:
                await conn.run_sync(table.create, checkfirst=True)
        self._store = MissionStore(ctx.db_session_factory)
        self._reflections = comms.ReflectionLog(ctx.db_session_factory)
        register_tools(ctx, self._store)
        comms.register_tools(ctx, self._reflections)
        self._ctx = ctx
        schedule_on_load_work(ctx, self._store, self._reflections)
        log.info("plugin-curiosity loaded (tools=4)")

    async def prompt_sections(self) -> list[str]:
        if self._store is None:
            return []
        return [prompt_fragment(await self._store.get())]
