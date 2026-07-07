"""plugin-curiosity — mission-driven curiosity for Luna.

The behavior plugin: give Luna a mission and she teaches herself the domain —
researching, filling her wiki (plugin-wiki), dreaming nightly to consolidate,
and proactively sharing grounded reflections. Consumes the "wiki" provider.
Authored against `luna_sdk` only.
"""

from __future__ import annotations

from luna_sdk import LunaPlugin, PluginContext, PluginManifest


class CuriosityPlugin(LunaPlugin):
    manifest = PluginManifest(
        name="plugin-curiosity",
        version="0.1.1",
        description="Mission-driven curiosity: research, wiki-building, nightly dreams, proactive reflections.",
        capabilities=["wiki"],
        routes_module="routes",
    )

    async def on_load(self, ctx: PluginContext) -> None:
        # Phase 2+ registers the missions table, mission tools, schedules,
        # research/dream/comms behavior.
        self._ctx = ctx
