"""plugin-curiosity — mission-driven curiosity for Luna.

The behavior plugin: give Luna a mission and she teaches herself the domain —
researching, filling her wiki (plugin-wiki), dreaming nightly to consolidate,
and proactively sharing grounded reflections. Consumes the "wiki" provider.
Authored against `luna_sdk` only.
"""

from __future__ import annotations

import logging

from luna_sdk import LunaPlugin, PluginContext, PluginManifest

from .mission import MissionStore, prompt_fragment, register_tools
from .models import ALL_TABLES

log = logging.getLogger("plugin-curiosity")


class CuriosityPlugin(LunaPlugin):
    manifest = PluginManifest(
        name="plugin-curiosity",
        version="0.2.0",
        description="Mission-driven curiosity: research, wiki-building, nightly dreams, proactive reflections.",
        capabilities=["wiki"],
        db_tables=[t.name for t in ALL_TABLES],
        routes_module="routes",
    )

    def __init__(self) -> None:
        self._store: MissionStore | None = None

    async def on_load(self, ctx: PluginContext) -> None:
        async with ctx.engine.begin() as conn:
            for table in ALL_TABLES:
                await conn.run_sync(table.create, checkfirst=True)
        self._store = MissionStore(ctx.db_session_factory)
        register_tools(ctx, self._store)
        self._ctx = ctx
        log.info("plugin-curiosity loaded (tools=3)")

    async def prompt_sections(self) -> list[str]:
        if self._store is None:
            return []
        return [prompt_fragment(await self._store.get())]
