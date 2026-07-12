"""Skill-gated registration (0.9.12).

Rare tools ride behind the ``mission-changes`` skill so their schemas stay
out of every turn's prompt. The gate holds ONLY for tools that no muted
reaction turn ever needs: muted turns (kickoff, heartbeat nudge,
reflections) and playbook agent_steps run without load_skill, so a gated
tool is unreachable there — anything on those allowlists must stay
ungated (plan_change_note rides KICKOFF_TOOLS, for example).

Cores without skill support (pre-006.0) get the tools ungated — degrade,
never hide.
"""

from __future__ import annotations

from typing import Any

PLUGIN_NAME = "plugin-curiosity"

SKILL_NAME = "mission-changes"

# Tools that change the mission's plan of record — each fires a handful of
# times over a mission's whole life. Everything else curiosity registers
# stays in the every-turn toolset.
GATED_TOOLS = (
    "mission_refine",
    "mission_schedules_sync",
    "phase_advance",
)


def register_tool(ctx: Any, tool_def: Any, handler: Any) -> None:
    """Register one tool, skill-gating it when it's rare and the core can."""
    if tool_def.name in GATED_TOOLS and getattr(ctx, "skill_registry", None) is not None:
        try:
            ctx.tool_registry.register(PLUGIN_NAME, tool_def, handler, skill_gated=True)
            return
        except TypeError:  # core knows skills but not the kwarg — stay visible
            pass
    ctx.tool_registry.register(PLUGIN_NAME, tool_def, handler)
