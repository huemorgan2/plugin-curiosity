"""9.001: phase-one doctrine on every setup surface, single-sourced stage
ladder, self-authored heartbeat contract + safety net, success-criteria
artifact upgrade, stage_age_days clock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from plugin_curiosity.mission import prompt_fragment
from plugin_curiosity.prompts import (
    HEARTBEAT_CONTRACT,
    HEARTBEAT_NAME,
    NEXT_TOUCH_RULE,
    PHASE_ONE_DOCTRINE,
    PHASE_TWO_LINE,
    RATIFICATION_FORCING,
    SETUP_STAGE_DEFS,
)
from plugin_curiosity.research import (
    _KICKOFF_CONTENT,
    DAILY_RESEARCH_TARGET,
    HEARTBEAT_NUDGE_CONTENT,
    INSTALL_KICKOFF_CONTENT,
    KICKOFF_TOOLS,
)
from plugin_curiosity.review import WEEKLY_REVIEW_TARGET

MISSION = {"statement": "grow signups", "autonomy_rung": 2, "risk_ceiling": "low"}


# ---------------------------------------------------------------- doctrine

def test_doctrine_on_every_setup_surface_and_only_there():
    setup_frag = prompt_fragment(MISSION, "setup")
    for surface in (_KICKOFF_CONTENT, WEEKLY_REVIEW_TARGET, setup_frag):
        assert PHASE_ONE_DOCTRINE in surface
    # the daily rides a condensed doctrine line (char budget), same questions
    assert "QUALIFYING yourself" in DAILY_RESEARCH_TARGET
    assert "do I know what success looks like" in DAILY_RESEARCH_TARGET
    work_frag = prompt_fragment(MISSION, "work")
    assert PHASE_ONE_DOCTRINE not in work_frag
    assert PHASE_TWO_LINE in work_frag
    # the doctrine leads with the two questions
    assert "Am I qualified to do this job?" in PHASE_ONE_DOCTRINE
    assert "what success looks like" in PHASE_ONE_DOCTRINE


def test_stage_ladder_single_sourced():
    # ONE definition of the ladder, interpolated everywhere it appears
    assert "S3 approved" in SETUP_STAGE_DEFS
    assert "success-criteria" in SETUP_STAGE_DEFS
    for surface in (_KICKOFF_CONTENT, WEEKLY_REVIEW_TARGET,
                    prompt_fragment(MISSION, "setup")):
        assert SETUP_STAGE_DEFS in surface


def test_next_touch_and_ratification_forcing_ride_setup_surfaces():
    setup_frag = prompt_fragment(MISSION, "setup")
    for surface in (_KICKOFF_CONTENT, DAILY_RESEARCH_TARGET, setup_frag):
        assert NEXT_TOUCH_RULE in surface
    for surface in (DAILY_RESEARCH_TARGET, WEEKLY_REVIEW_TARGET, setup_frag):
        assert RATIFICATION_FORCING in surface


def test_owner_legibility_two_phase_story():
    # the agent must be able to TELL the model, not just follow it
    assert "QUALIFIED" in prompt_fragment(None)
    assert "QUALIFIED" in INSTALL_KICKOFF_CONTENT
    assert "**What success looks like**" in _KICKOFF_CONTENT
    assert "**Where I am**" in _KICKOFF_CONTENT


# ---------------------------------------------------------------- heartbeat

def test_heartbeat_contract_surfaces():
    # kickoff step creates the trigger; the contract rides kickoff + fragment
    assert HEARTBEAT_CONTRACT in _KICKOFF_CONTENT
    assert HEARTBEAT_CONTRACT in prompt_fragment(MISSION, "setup")
    assert "trigger_create" in KICKOFF_TOOLS and "trigger_list" in KICKOFF_TOOLS
    # convergence is mandatory, not advisory
    assert "convergence criterion" in HEARTBEAT_CONTRACT
    assert "5 consecutive" in HEARTBEAT_CONTRACT
    # exactly one heartbeat: dedupe by name before creating (the adoption
    # chat turn and the kickoff turn both carry a create instruction)
    assert "EXACTLY ONE" in HEARTBEAT_CONTRACT
    assert "trigger_list" in HEARTBEAT_CONTRACT
    assert "trigger_list first" in _KICKOFF_CONTENT
    # daily recreates a missing heartbeat by canonical name; weekly audits it
    assert HEARTBEAT_NAME in DAILY_RESEARCH_TARGET
    assert HEARTBEAT_NAME in WEEKLY_REVIEW_TARGET
    assert HEARTBEAT_NAME in HEARTBEAT_NUDGE_CONTENT
    assert HEARTBEAT_CONTRACT in HEARTBEAT_NUDGE_CONTENT


@pytest.mark.asyncio
async def test_heartbeat_exists_tristate(ctx):
    from plugin_curiosity.research import heartbeat_exists

    assert await heartbeat_exists(ctx) is False
    ctx.tool_registry.existing_triggers.append(
        {"id": "trg-x", "name": HEARTBEAT_NAME, "enabled": True})
    assert await heartbeat_exists(ctx) is True
    ctx.tool_registry.scheduler_installed = False
    assert await heartbeat_exists(ctx) is None  # unknowable, not False


# ---------------------------------------------------------------- safety net

@pytest_asyncio.fixture
async def nctx(ctx, sf, store):
    """ctx wired for maybe_nudge_heartbeat: mission in setup phase."""
    await store.set("own the weekly newsletter end to end")
    ctx.db_session_factory = sf
    return ctx


async def _set_phase(sf, phase: str) -> None:
    from plugin_curiosity.models import Mission

    async with sf() as s:
        m = (await s.execute(select(Mission))).scalars().one()
        m.agent_phase = phase
        await s.commit()


@pytest.mark.asyncio
async def test_nudge_fires_once_per_day_and_never_creates(nctx, sf):
    from plugin_curiosity import maybe_nudge_heartbeat
    from plugin_curiosity.scopes import ScopeStore

    sstore = ScopeStore(sf)
    assert await maybe_nudge_heartbeat(nctx, sstore) is True
    assert len(nctx.muted_posts) == 1
    assert nctx.muted_posts[0]["title"] == "Setup heartbeat missing"
    # reminds, never creates: no trigger was authored by the net
    assert nctx.tool_registry.trigger_created == []
    # same day → throttled
    assert await maybe_nudge_heartbeat(nctx, sstore) is False
    assert len(nctx.muted_posts) == 1


@pytest.mark.asyncio
async def test_nudge_skips_when_heartbeat_present_unknowable_or_work(nctx, sf):
    from plugin_curiosity import maybe_nudge_heartbeat
    from plugin_curiosity.scopes import ScopeStore

    sstore = ScopeStore(sf)
    # heartbeat present → no nudge
    nctx.tool_registry.existing_triggers.append(
        {"id": "trg-x", "name": HEARTBEAT_NAME, "enabled": True})
    assert await maybe_nudge_heartbeat(nctx, sstore) is False
    # scheduler unknowable (None) → no nudge, no flag burned
    nctx.tool_registry.existing_triggers.clear()
    nctx.tool_registry.scheduler_installed = False
    assert await maybe_nudge_heartbeat(nctx, sstore) is False
    # work phase → not the safety net's business
    nctx.tool_registry.scheduler_installed = True
    await _set_phase(sf, "work")
    assert await maybe_nudge_heartbeat(nctx, sstore) is False
    assert nctx.muted_posts == []


@pytest.mark.asyncio
async def test_nudge_failed_send_does_not_burn_the_daily_flag(nctx, sf):
    from plugin_curiosity import maybe_nudge_heartbeat
    from plugin_curiosity.scopes import ScopeStore

    async def failing_send(title, content, **kw):
        return {"error": "no conversations"}

    nctx.send_muted_message = failing_send
    sstore = ScopeStore(sf)
    assert await maybe_nudge_heartbeat(nctx, sstore) is False

    async def ok_send(title, content, **kw):
        nctx.muted_posts.append({"title": title})
        return {"ok": True}

    nctx.send_muted_message = ok_send
    assert await maybe_nudge_heartbeat(nctx, sstore) is True  # retried same day


# ---------------------------------------------------------------- stage clock

@pytest.mark.asyncio
async def test_stage_age_days_served_and_reset_on_stage_set(sf, store):
    from plugin_curiosity.models import Mission
    from plugin_curiosity.scopes import ScopeStore

    await store.set("own the weekly newsletter end to end")
    sstore = ScopeStore(sf)
    assert (await sstore.state())["stage_age_days"] == 0
    # backdate the stage entry — agents have no clock; the server counts
    async with sf() as s:
        m = (await s.execute(select(Mission))).scalars().one()
        m.stage_entered_at = datetime.now(UTC) - timedelta(days=4)
        await s.commit()
    assert (await sstore.state())["stage_age_days"] == 4
    await sstore.stage_set("S2")
    assert (await sstore.state())["stage_age_days"] == 0  # fresh stamp


# ---------------------------------------------------------------- success page

@pytest.mark.asyncio
async def test_success_criteria_replaces_metrics_stub_on_mission_set(ctx, store):
    from plugin_curiosity.mission import _STUB_SLUGS

    assert "success-criteria" in _STUB_SLUGS
    assert "mission-metrics" not in _STUB_SLUGS
    handler = ctx.tool_registry.registered["mission_set"][1]
    await handler(statement="grow signups")
    wiki = ctx.provider_registry.get("wiki")
    assert "success-criteria" in wiki.pages
    body = wiki.pages["success-criteria"]["body"]
    assert "grow signups" in body and "role-charter" in body


@pytest.mark.asyncio
async def test_success_criteria_upgrade_seed_idempotent(ctx, store):
    from plugin_curiosity.mission import ensure_success_criteria_page

    assert await ensure_success_criteria_page(ctx, store) == "no mission"
    await store.set("grow signups")
    ctx.provider_registry.get("wiki").pages.clear()  # pre-9.001 shape
    assert await ensure_success_criteria_page(ctx, store) == "seeded"
    assert await ensure_success_criteria_page(ctx, store) == "already present"


@pytest.mark.asyncio
async def test_success_criteria_upgrade_carries_real_legacy_content(ctx, store):
    from plugin_curiosity.mission import ensure_success_criteria_page

    await store.set("grow signups")
    wiki = ctx.provider_registry.get("wiki")
    wiki.pages.clear()
    wiki.pages["mission-metrics"] = {
        "slug": "mission-metrics", "title": "Mission Metrics",
        "body": "Weekly signups baseline: 120. Target: 200 by March."}
    assert await ensure_success_criteria_page(ctx, store) == "seeded"
    body = wiki.pages["success-criteria"]["body"]
    assert body.startswith("Weekly signups baseline: 120.")
    assert "grow signups" in body
    # a still-stub legacy page is NOT carried
    wiki.pages.pop("success-criteria")
    wiki.pages["mission-metrics"]["body"] = "*Stub — seeded at kickoff.*"
    assert await ensure_success_criteria_page(ctx, store) == "seeded"
    assert "*Stub — seeded at kickoff.*" not in wiki.pages["success-criteria"]["body"]
