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

# Visibility group for every tool this plugin registers (core's
# agent/tool_groups.py). Declaring it here keeps future tools out of the
# always-visible fail-open set without a lockstep core release.
TOOL_GROUP = "curiosity"


def stamp_group(tool_def: Any) -> Any:
    """Declare the visibility group on cores that support ToolDef.group.

    Old cores have no `group` field and pydantic rejects assignment to an
    undeclared attribute, so probe model_fields first. Degrade to the core's
    static partition — never let grouping break registration.
    """
    try:
        if "group" in getattr(type(tool_def), "model_fields", {}) and tool_def.group is None:
            tool_def.group = TOOL_GROUP
    except Exception:  # noqa: BLE001
        pass
    return tool_def

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
    stamp_group(tool_def)
    if tool_def.name in GATED_TOOLS and getattr(ctx, "skill_registry", None) is not None:
        try:
            ctx.tool_registry.register(PLUGIN_NAME, tool_def, handler, skill_gated=True)
            return
        except TypeError:  # core knows skills but not the kwarg — stay visible
            pass
    ctx.tool_registry.register(PLUGIN_NAME, tool_def, handler)
