"""0.9.10 — the agent-authored status line.

The Missions hero shows one line in the agent's own words (current_state_set),
never a UI-invented sentence. Store round-trip, validation, tool surface,
prompt instruction, migration entry, and the UI contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

UI = Path(__file__).parent.parent / "plugin_curiosity" / "ui"


@pytest_asyncio.fixture
async def sstore(sf, store):
    from plugin_curiosity.scopes import ScopeStore

    await store.set("own the weekly newsletter end to end")
    return ScopeStore(sf)


@pytest.fixture
def sctx(ctx, sstore):
    from plugin_curiosity.scopes import register_tools

    register_tools(ctx, sstore)
    return ctx


async def call(ctx, tool, **kw):
    return await ctx.tool_registry.registered[tool][1](**kw)


@pytest.mark.asyncio
async def test_current_state_round_trip(sstore):
    state = await sstore.state()
    assert state["current_state"] == ""
    assert state["current_state_age_days"] is None

    out = await sstore.current_state_set(
        "Working on making myself good enough for this job — mapping the catalog first."
    )
    assert out["current_state"].startswith("Working on")
    state = await sstore.state()
    assert state["current_state"] == out["current_state"]
    assert state["current_state_age_days"] == 0  # server-computed, fresh


@pytest.mark.asyncio
async def test_current_state_validation(sstore):
    with pytest.raises(ValueError, match="non-empty"):
        await sstore.current_state_set("   ")
    with pytest.raises(ValueError, match="200"):
        await sstore.current_state_set("x" * 201)
    # whitespace collapsed to one line
    out = await sstore.current_state_set("two\n  lines   squashed")
    assert out["current_state"] == "two lines squashed"


@pytest.mark.asyncio
async def test_current_state_requires_active_mission(sf):
    from plugin_curiosity.scopes import ScopeStore

    empty = ScopeStore(sf)
    with pytest.raises(ValueError, match="no active mission"):
        await empty.current_state_set("anything")


@pytest.mark.asyncio
async def test_tool_registered_auto_approve_and_working(sctx, sstore):
    tool_def = sctx.tool_registry.registered["current_state_set"][0]
    assert tool_def.policy == "auto_approve"
    assert "own words" in tool_def.description

    out = await call(sctx, "current_state_set", text="Onboarding — job description shared, waiting for the owner to read and approve.")
    assert out["current_state"].startswith("Onboarding")
    err = await call(sctx, "current_state_set", text="")
    assert "error" in err


@pytest.mark.asyncio
async def test_phase_and_stage_flips_remind_to_refresh(sctx, sstore):
    out = await call(sctx, "stage_set", stage="S1")
    assert "current_state_set" in out.get("reminder", "")
    out = await call(sctx, "phase_advance", to="setup", reason="test")
    assert "current_state_set" in out.get("reminder", "")


def test_prompt_instructs_status_line():
    from plugin_curiosity.mission import prompt_fragment

    frag = prompt_fragment({"statement": "s", "autonomy_rung": 1, "risk_ceiling": "low"})
    assert "current_state_set" in frag


def test_migration_covers_upgrading_databases():
    from plugin_curiosity.models import _ADDITIVE_COLUMNS

    cols = dict(_ADDITIVE_COLUMNS["curiosity_missions"])
    assert "current_state" in cols and "current_state_at" in cols


def test_hero_renders_agent_words_not_hardcoded_sentence():
    js = (UI / "app.js").read_text()
    assert "current_state" in js, "hero must read the agent-authored line"
    # the old hardcoded first-person sentence must be gone from the UI
    assert "making myself good enough" not in js
    assert "setting myself up" not in js
