"""Phase14 acceptance: setup runs on NUMBERED, owner-approved plans.

The incident: once the mission set, the agent went on a tangent and built
its own setup unasked. This suite pins the ledger — plan 001/002/… drafted
to the wiki, the owner's explicit OK as the ONLY release, an execution
summary after EVERY run, and tool-layer gates so a chat turn cannot
scaffold past the ledger.
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import select

from plugin_curiosity import planning, research
from plugin_curiosity.mission import prompt_fragment
from plugin_curiosity.planning import PlanStore
from plugin_curiosity.research import (
    _KICKOFF_CONTENT,
    _PLAN_EXEC_CONTENT,
    KICKOFF_TOOLS,
    PLAN_EXEC_TOOLS,
)


async def call(ctx, tool: str, **kwargs):
    return await ctx.tool_registry.registered[tool][1](**kwargs)


async def _drain():
    for _ in range(10):
        await asyncio.sleep(0)


@pytest.fixture(autouse=True)
def fast_kickoff(monkeypatch):
    monkeypatch.setattr(research, "KICKOFF_DELAY_S", 0)
    monkeypatch.setattr(research, "KICKOFF_RETRY_S", 0)


@pytest_asyncio.fixture
async def pctx(ctx, sf, store):
    """ctx with the plan-ledger tools registered and a mission on file."""
    plans = PlanStore(sf)
    planning.register_tools(ctx, plans, store)
    await store.set("own the weekly newsletter end to end")
    ctx.plan_store = plans
    return ctx


def _wiki(ctx):
    return ctx.provider_registry.get("wiki")


async def _stamp_stage(sf, stage):
    from plugin_curiosity.models import Mission

    async with sf() as s:
        m = (await s.execute(select(Mission))).scalars().one()
        m.setup_stage = stage
        await s.commit()


# ------------------------------------------------- unit 1: the numbered store

@pytest.mark.asyncio
async def test_store_numbers_slugs_and_supersedes_drafts(sf, store):
    plans = PlanStore(sf)
    with pytest.raises(LookupError):
        await plans.open("initial-setup")  # no mission, no ledger
    await store.set("own the weekly newsletter")

    p1 = await plans.open("Initial Setup!!", objective="stand up the role")
    assert p1["seq"] == 1
    assert p1["label"] == "001-initial-setup"
    assert p1["slug"] == "setup-plans/001-initial-setup"
    assert p1["summary_slug"] == "setup-plans/001-initial-setup-execution-summary"
    assert p1["status"] == "draft"

    # opening over an unapproved draft supersedes it — the amendment path
    p2 = await plans.open("initial-setup-v2")
    assert p2["seq"] == 2
    assert p2["superseded"] == "001-initial-setup"
    ledger = await plans.list()
    assert [p["status"] for p in ledger] == ["superseded", "draft"]


@pytest.mark.asyncio
async def test_store_transitions_demand_the_owner_and_the_order(sf, store):
    plans = PlanStore(sf)
    await store.set("own the weekly newsletter")
    await plans.open("initial-setup")

    # no owner words, no approval; a draft cannot start
    with pytest.raises(ValueError, match="owner_words is required"):
        await plans.approve("")
    with pytest.raises(ValueError, match="only an APPROVED plan starts"):
        await plans.start()

    approved = await plans.approve("ok, run it")
    assert approved["status"] == "approved"
    assert approved["decision_note"] == "ok, run it"

    # a live plan blocks the next number until it is finished
    with pytest.raises(ValueError, match="finish it"):
        await plans.open("tangent-plan")
    # approval is draft-only; close follows start
    with pytest.raises(ValueError, match="already approved"):
        await plans.approve("ok again")
    with pytest.raises(ValueError, match="close follows setup_plan_start"):
        await plans.close("done")

    started = await plans.start()
    assert started["status"] == "executing"
    with pytest.raises(ValueError, match="outcome must be"):
        await plans.close("shipped")
    closed = await plans.close("done", note="all steps ran")
    assert closed["status"] == "done"

    # the ledger is history; the desk is clear; numbering never resets
    assert await plans.current() is None
    p2 = await plans.open("whatsapp-channel")
    assert p2["seq"] == 2 and "superseded" not in p2


# --------------------------------------------- unit 2: tools, pages, spawning

@pytest.mark.asyncio
async def test_open_mirrors_ledger_and_steers_to_the_owner(pctx):
    r = await call(pctx, "setup_plan_open", name="initial-setup",
                   objective="stand up the role")
    assert r["plan"]["label"] == "001-initial-setup"
    assert r["wiki_mirror"] == "ok"
    assert "silence is never a yes" in r["next"]
    index = _wiki(pctx).pages["setup-plans"]
    assert "001 — initial-setup" in index["body"]


@pytest.mark.asyncio
async def test_approve_refuses_without_a_readable_plan_page(pctx):
    await call(pctx, "setup_plan_open", name="initial-setup")
    r = await call(pctx, "setup_plan_approve", owner_words="ok go")
    assert "cannot approve a plan they cannot read" in r["error"]
    assert not [p for p in pctx.muted_posts
                if p["title"] == research.PLAN_EXEC_TITLE]


@pytest.mark.asyncio
async def test_approve_spawns_the_execution_pass_exactly_once(pctx, sf):
    opened = await call(pctx, "setup_plan_open", name="initial-setup")
    slug = opened["plan"]["slug"]
    await _wiki(pctx).upsert_page(slug, "Plan 001", "## Objective\nsteps…")

    r = await call(pctx, "setup_plan_approve", owner_words="ok, run plan 001")
    assert r["plan"]["status"] == "approved"
    assert r["execution"] == "started"
    await _drain()
    (post,) = [p for p in pctx.muted_posts
               if p["title"] == research.PLAN_EXEC_TITLE]
    assert post["tools"] == PLAN_EXEC_TOOLS
    assert slug in post["content"]
    assert opened["plan"]["summary_slug"] in post["content"]
    assert "ok, run plan 001" in post["content"]  # the owner's words ride along

    # the claim + persisted flag converge on a single spawn (janitor race)
    mission = {"id": "m", "statement": "s"}
    again = await research.spawn_plan_execution_once(
        pctx, sf, mission, r["plan"])
    assert again == "already started"
    # re-approval is refused too — the OK was already recorded
    r2 = await call(pctx, "setup_plan_approve", owner_words="ok")
    assert "already approved" in r2["error"]


@pytest.mark.asyncio
async def test_close_refuses_until_the_summary_page_exists(pctx):
    opened = await call(pctx, "setup_plan_open", name="initial-setup")
    plan = opened["plan"]
    await _wiki(pctx).upsert_page(plan["slug"], "Plan 001", "## Objective\n…")
    await call(pctx, "setup_plan_approve", owner_words="ok")
    started = await call(pctx, "setup_plan_start")
    assert started["plan"]["status"] == "executing"

    blocked = await call(pctx, "setup_plan_close", outcome="done")
    assert plan["summary_slug"] in blocked["error"]
    assert "success or failure" in blocked["error"]

    await _wiki(pctx).upsert_page(
        plan["summary_slug"], "001 summary",
        "## What ran\n## What worked\n## What failed or was skipped\n## Next")
    closed = await call(pctx, "setup_plan_close", outcome="done", note="ran")
    assert closed["plan"]["status"] == "done"
    assert "NEXT numbered plan" in closed["next"]
    listing = await call(pctx, "setup_plan_list")
    assert [p["status"] for p in listing["plans"]] == ["done"]


# --------------------------- unit 3+4: the split — planning pass cannot build

def test_planning_pass_researches_and_asks_but_cannot_scaffold():
    for tool in ("get_plugin_status", "setup_plan_open", "setup_plan_list",
                 "wiki_write", "marketplace_search"):
        assert tool in KICKOFF_TOOLS, tool
    for tool in ("scope_set", "stage_set", "ability_upsert", "goal_set",
                 "trigger_create", "loop_open", "setup_plan_approve",
                 "setup_plan_start"):
        assert tool not in KICKOFF_TOOLS, tool
    assert "You build NOTHING" in _KICKOFF_CONTENT
    assert "Silence is never a yes" in _KICKOFF_CONTENT


def test_execution_pass_carries_the_scaffolding_and_the_summary_law():
    for tool in ("setup_plan_start", "setup_plan_close", "scope_set",
                 "stage_set", "ability_upsert", "goal_set", "trigger_create"):
        assert tool in PLAN_EXEC_TOOLS, tool
    assert "setup_plan_open" not in PLAN_EXEC_TOOLS  # amendments wait for chat
    assert "setup_plan_start() FIRST" in _PLAN_EXEC_CONTENT
    assert "ALWAYS" in _PLAN_EXEC_CONTENT
    assert "{summary_slug}" in _PLAN_EXEC_CONTENT


# ------------------------------------- unit 5: the interactive-turn tool gate

@pytest.mark.asyncio
async def test_execution_gate_refuses_s0_scaffolding_outside_a_plan(pctx, sf, store):
    gate = planning.execution_gate(store, pctx.plan_store)
    refusal = await gate()
    assert "numbered plans" in refusal["error"]
    assert "none — open one" in refusal["hint"]

    await call(pctx, "setup_plan_open", name="initial-setup")
    refusal = await gate()
    assert "001-initial-setup (draft)" in refusal["hint"]


@pytest.mark.asyncio
async def test_execution_gate_opens_inside_a_plan_and_grandfathers(pctx, sf, store):
    gate = planning.execution_gate(store, pctx.plan_store)
    opened = await call(pctx, "setup_plan_open", name="initial-setup")
    await _wiki(pctx).upsert_page(opened["plan"]["slug"], "p", "b")
    await call(pctx, "setup_plan_approve", owner_words="ok")
    assert "numbered plans" in (await gate())["error"]  # approved ≠ executing
    await call(pctx, "setup_plan_start")
    assert await gate() is None  # the execution turn builds freely

    # past-S0 missions predate the ledger — never gated
    await _wiki(pctx).upsert_page(opened["plan"]["summary_slug"], "s", "b")
    closed = await call(pctx, "setup_plan_close", outcome="failed", note="n")
    assert closed["plan"]["status"] == "failed"
    assert "numbered plans" in (await gate())["error"]
    await _stamp_stage(sf, "S1")
    assert await gate() is None


@pytest.mark.asyncio
async def test_execution_gate_never_gates_missionless_turns(sf):
    from plugin_curiosity.mission import MissionStore

    gate = planning.execution_gate(MissionStore(sf), PlanStore(sf))
    assert await gate() is None


@pytest.mark.asyncio
async def test_scope_set_is_wired_through_the_gate(pctx, sf, store):
    from plugin_curiosity import scopes

    gate = planning.execution_gate(store, pctx.plan_store)
    scopes.register_tools(pctx, scopes.ScopeStore(sf), plan_gate=gate)
    blocked = await call(pctx, "scope_set", kind="mission",
                         name="I own the newsletter")
    assert "numbered plans" in blocked["error"]
    blocked = await call(pctx, "stage_set", stage="S1")
    assert "numbered plans" in blocked["error"]
    # updates stay open — refining what an execution built is not new setup
    assert "scope_update" in pctx.tool_registry.registered


# ------------------------- unit 6: every chat turn knows the ledger position

def _mission(**kw):
    base = {"statement": "own the newsletter", "autonomy_rung": 2,
            "risk_ceiling": "low", "setup_stage": "S0",
            "confirmed_at": "2026-08-01T00:00:00+00:00"}
    base.update(kw)
    return base


def test_fragment_carries_the_plan_state_per_status():
    plan = {"label": "001-initial-setup", "status": "draft",
            "slug": "setup-plans/001-initial-setup",
            "summary_slug": "setup-plans/001-initial-setup-execution-summary"}
    frag = prompt_fragment(_mission(), plan=plan)
    assert "DRAFT on the owner's desk" in frag
    assert "Silence is never a yes" in frag

    frag = prompt_fragment(_mission(), plan={**plan, "status": "approved"})
    assert "APPROVED" in frag and "do not re-open" in frag

    frag = prompt_fragment(_mission(), plan={**plan, "status": "executing"})
    assert "EXECUTING" in frag
    assert "[[setup-plans/001-initial-setup-execution-summary]]" in frag

    # confirmed, no plan yet — the fragment demands the ledger, not a tangent
    frag = prompt_fragment(_mission())
    assert "No setup plan is on the desk yet" in frag

    # past S0 the ledger arc is over — no plan chatter
    frag = prompt_fragment(_mission(setup_stage="S2"), plan=plan)
    assert "DRAFT" not in frag


def test_setup_posture_carries_the_ledger_rule():
    from plugin_curiosity import prompts

    frag = prompt_fragment(_mission())
    assert "SETUP RUNS ON NUMBERED PLANS" in frag
    assert prompts.PLAN_LEDGER_RULE in frag
    # work phase runs no setup — the rule stays out of its posture
    assert "SETUP RUNS ON NUMBERED PLANS" not in prompt_fragment(
        _mission(agent_phase="work"), phase="work")


@pytest.mark.asyncio
async def test_janitor_recovers_an_approved_but_unspawned_plan(pctx, sf, store):
    """Process died between approve and spawn: on-load the janitor sees the
    approved plan and starts its execution pass — once."""
    opened = await call(pctx, "setup_plan_open", name="initial-setup")
    await _wiki(pctx).upsert_page(opened["plan"]["slug"], "p", "b")
    await pctx.plan_store.approve("ok go")  # approved, but nothing spawned

    r = await research.maybe_start_deep_kickoff(pctx, store, pctx.plan_store)
    assert r == "started"
    await _drain()
    (post,) = [p for p in pctx.muted_posts
               if p["title"] == research.PLAN_EXEC_TITLE]
    assert opened["plan"]["slug"] in post["content"]
    # idempotent across restarts — the flag survives the claim set
    research._plan_exec_claims.clear()
    again = await research.maybe_start_deep_kickoff(pctx, store, pctx.plan_store)
    assert again == "already started"
