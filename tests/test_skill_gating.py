"""0.9.12 — rare tools behind the mission-changes skill.

Three plan-of-record tools (mission_refine, mission_schedules_sync,
phase_advance) register skill_gated when the core has a skill registry;
everything else stays in the every-turn toolset. Muted reaction turns
(kickoff, heartbeat nudge, reflections) run without load_skill, so
nothing on those allowlists may ever be gated.
"""

from __future__ import annotations

import types

import pytest

from conftest import FakeProviderRegistry, FakeSkillRegistry, FakeToolRegistry, FakeWikiProvider

from plugin_curiosity.gating import GATED_TOOLS, SKILL_NAME


@pytest.fixture
def skill_ctx(store, sstore, sf):
    """ctx WITH a skill registry — gating active."""
    from plugin_curiosity.mission import register_tools as register_mission_tools
    from plugin_curiosity.scopes import register_tools as register_scope_tools

    c = types.SimpleNamespace(
        tool_registry=FakeToolRegistry(),
        skill_registry=FakeSkillRegistry(),
        provider_registry=FakeProviderRegistry(FakeWikiProvider()),
    )
    register_mission_tools(c, store)
    register_scope_tools(c, sstore)
    return c


@pytest.fixture
def sstore(sf):
    from plugin_curiosity.scopes import ScopeStore

    return ScopeStore(sf)


def test_rare_tools_gated_when_core_has_skills(skill_ctx):
    assert skill_ctx.tool_registry.gated == set(GATED_TOOLS)


def test_frequent_tools_stay_visible(skill_ctx):
    reg = skill_ctx.tool_registry
    for name in ("mission_set", "mission_get", "scope_set", "scope_update",
                 "scope_list", "stage_set", "plan_change_note", "current_state_set"):
        assert name in reg.registered, name
        assert name not in reg.gated, name


def test_old_core_degrades_to_ungated(store):
    """No skill_registry on ctx → every tool registers, none gated."""
    from plugin_curiosity.mission import register_tools

    c = types.SimpleNamespace(tool_registry=FakeToolRegistry())
    register_tools(c, store)
    assert "mission_refine" in c.tool_registry.registered
    assert c.tool_registry.gated == set()


def test_skill_registered_with_exact_tool_list(skill_ctx, store, sf):
    """The plugin's _register_skill puts the mission-changes skill in the
    registry with exactly the gated tool names."""
    import plugin_curiosity as pc

    plugin = pc.CuriosityPlugin()
    plugin._register_skill(skill_ctx)
    assert SKILL_NAME in skill_ctx.skill_registry.skills
    owner, skill = skill_ctx.skill_registry.skills[SKILL_NAME]
    assert owner == "plugin-curiosity"
    assert sorted(skill.tools) == sorted(GATED_TOOLS)
    # menu line + body are owner/agent-facing: plain words, load-ahead warning
    assert "load" in skill.description.lower()
    assert "NEXT turn" in skill.body


def test_muted_turn_allowlists_never_gated():
    """Muted turns can't load skills — their allowlisted tools must stay
    visible. plan_change_note rides KICKOFF_TOOLS: it must NOT be gated."""
    from plugin_curiosity.comms import REFLECTION_TOOLS
    from plugin_curiosity.research import HEARTBEAT_NUDGE_TOOLS, KICKOFF_TOOLS

    for allowlist in (KICKOFF_TOOLS, HEARTBEAT_NUDGE_TOOLS, REFLECTION_TOOLS):
        overlap = set(allowlist) & set(GATED_TOOLS)
        assert not overlap, f"gated tools on a muted-turn allowlist: {overlap}"
    assert "plan_change_note" not in GATED_TOOLS


def test_prompts_mention_the_skill_where_gated_tools_appear():
    """Every recurring prompt that tells the agent to call a gated tool must
    also tell her to load the skill ahead of time."""
    from plugin_curiosity.mission import prompt_fragment
    from plugin_curiosity.prompts import HEARTBEAT_CONTRACT
    from plugin_curiosity.review import WEEKLY_REVIEW_TARGET

    frag = prompt_fragment({"statement": "s", "autonomy_rung": 1, "risk_ceiling": "low"})
    for surface, tool in (
        (WEEKLY_REVIEW_TARGET, "phase_advance"),
        (HEARTBEAT_CONTRACT, "phase_advance"),
        (frag, "mission_refine"),
    ):
        assert tool in surface
        assert SKILL_NAME in surface, f"{tool} referenced without naming {SKILL_NAME}"
