"""Phase 10.001 — the job model: abilities ladder, job description,
goal readiness, role pivots, overview v2.

Covers plan §5's unit list: % math (0.5 weight, empty sets), upsert
convergence (double-derive → no dupes), role_version bump in the pivot
transaction, JD parser (good / missing block / malformed), contract
presence on every surface (prompt-primacy pattern), and the overview's
stage-% fallback while abilities are empty."""

from __future__ import annotations

import pytest

from plugin_curiosity.abilities import (
    AbilityStore,
    setup_percent,
    slugify,
    task_percent,
)


# ---- pure math --------------------------------------------------------------


def test_slugify():
    assert slugify("Ability to contact every customer!") == (
        "ability-to-contact-every-customer"
    )
    assert slugify("  Weird---spacing  ") == "weird-spacing"
    assert slugify("x" * 300) == "x" * 120


def test_task_percent_weights():
    assert task_percent([]) == 0
    assert task_percent([{"status": "done"}]) == 100
    assert task_percent([{"status": "in_progress"}]) == 50
    assert task_percent([{"status": "missing"}, {"status": "blocked"}]) == 0
    # done + in_progress + missing + blocked = (1 + 0.5 + 0 + 0) / 4
    assert task_percent(
        [{"status": s} for s in ("done", "in_progress", "missing", "blocked")]
    ) == 38


def test_setup_percent_mean_and_empty():
    assert setup_percent([]) is None
    assert setup_percent([{"percent": 100}, {"percent": 0}]) == 50
    assert setup_percent([{"percent": 100}, {"percent": 50}, {"percent": 25}]) == 58


# ---- store: convergence, auto-create, pivot txn ------------------------------


async def _mission(store):
    await store.set("run customer onboarding")


@pytest.mark.asyncio
async def test_upsert_convergence_no_dupes(sf, store):
    await _mission(store)
    ab = AbilityStore(sf)
    a1 = await ab.upsert(
        "Ability to contact every customer",
        why="core of onboarding",
        tasks=["find contact channel", "draft outreach playbook"],
    )
    # concurrent-turn re-derivation: same title, overlapping tasks
    a2 = await ab.upsert(
        "Ability to contact every customer",
        tasks=["find contact channel", "verify deliverability"],
    )
    assert a1["id"] == a2["id"]
    listed = await ab.list()
    assert len(listed["abilities"]) == 1
    tasks = listed["abilities"][0]["tasks"]
    # merged by slug, never deleted: 2 original + 1 new
    assert len(tasks) == 3
    assert a2["why"] == "core of onboarding"  # merge keeps existing why


@pytest.mark.asyncio
async def test_task_set_scores_and_autocreates(sf, store):
    await _mission(store)
    ab = AbilityStore(sf)
    a = await ab.upsert("Ability to answer product questions", tasks=["read docs"])
    scored = await ab.task_set(a["id"], "read docs", "done", evidence_ref="[[mission-domain]]")
    assert scored["task"]["status"] == "done"
    # unknown subtask converges to a new row instead of erroring
    await ab.task_set(a["id"], "map the FAQ gaps", "in_progress")
    listed = await ab.list()
    (only,) = listed["abilities"]
    assert {t["slug"] for t in only["tasks"]} == {"read-docs", "map-the-faq-gaps"}
    assert only["percent"] == 75  # (1 + 0.5) / 2
    assert listed["setup_percent"] == 75
    with pytest.raises(ValueError):
        await ab.task_set(a["id"], "read docs", "nonsense")


@pytest.mark.asyncio
async def test_role_pivot_bumps_version_in_one_txn(sf, store):
    from plugin_curiosity.scopes import ScopeStore

    await _mission(store)
    sc = ScopeStore(sf)
    r1 = await sc.plan_change_add("learned the taxonomy is deeper")  # refine
    assert r1["kind"] == "refine" and "role_version" not in r1
    state = await sc.state()
    assert state["role_version"] == 1
    r2 = await sc.plan_change_add(
        "owner's real need is retention, not acquisition", kind="role_pivot"
    )
    assert r2["role_version"] == 2
    assert (await sc.state())["role_version"] == 2
    changes = await sc.plan_changes()
    assert [c["kind"] for c in changes] == ["refine", "role_pivot"]
    with pytest.raises(ValueError):
        await sc.plan_change_add("bad", kind="mystery")


@pytest.mark.asyncio
async def test_scope_attaches_to_ability(sf, store):
    from plugin_curiosity.scopes import ScopeStore

    await _mission(store)
    ab = AbilityStore(sf)
    a = await ab.upsert("Ability to reach customers", tasks=["channel audit"])
    sc = ScopeStore(sf)
    s = await sc.add("communication_paths", "email + WhatsApp", ability_id=a["id"])
    assert s["ability_id"] == a["id"]


# ---- goal readiness -----------------------------------------------------------


@pytest.mark.asyncio
async def test_goal_readiness_fields(sf, store):
    from plugin_curiosity.goals import GoalStore, render_goals_page

    await _mission(store)
    gs = GoalStore(sf)
    g = await gs.add(
        "first 5 customers onboarded",
        target_date="2026-07-20",
        expected_result="5 signed-off onboarding checklists",
        readiness="amber",
        readiness_note="have playbook; missing CRM access",
    )
    assert g["readiness"] == "amber"
    g2 = await gs.update(g["id"], readiness="green", readiness_note="CRM granted")
    assert g2["readiness"] == "green"
    page = render_goals_page(await gs.list())
    assert "🟢 green — CRM granted" in page
    assert "expected result: 5 signed-off onboarding checklists" in page
    with pytest.raises(ValueError):
        await gs.add("x", readiness="chartreuse")


# ---- JD parser -----------------------------------------------------------------


_JD_GOOD = """\
*Living draft v1 — I revise this as I learn.*

## How I will accomplish this mission
- learn the product from the docs and real tickets
- contact every new customer within a day

## After onboarding
In about a week you should see:
1. every new signup greeted within 24h
2. a weekly digest of onboarding blockers

## In 30 days
1. onboarding time cut in half
2. a playbook the team can run without me

## Working assumptions
- signups arrive ~5/day — I will verify against the signup feed
"""


def test_jd_parser_good():
    from plugin_curiosity.overview import parse_job_description

    jd = parse_job_description(_JD_GOOD)
    assert jd["shape_ok"] is True and jd["exists"] is True
    assert "raw" not in jd
    assert jd["sections"]["method"]["items"][0].startswith("learn the product")
    assert jd["sections"]["after_onboarding"]["intro"].startswith("In about a week")
    assert len(jd["sections"]["in_30_days"]["items"]) == 2
    assert "verify against the signup feed" in jd["sections"]["working_assumptions"]["items"][0]


def test_jd_parser_missing_block_and_malformed():
    from plugin_curiosity.overview import parse_job_description

    missing = parse_job_description(
        "## How I will accomplish this mission\n- do things\n## In 30 days\n1. win\n"
    )
    assert missing["shape_ok"] is False
    assert missing["raw"].startswith("## How")
    malformed = parse_job_description("just prose, no headings at all")
    assert malformed["shape_ok"] is False and malformed["exists"] is True
    empty = parse_job_description("")
    assert empty["exists"] is False and empty["shape_ok"] is False


# ---- contract presence (prompt primacy) ----------------------------------------


def test_contracts_ride_every_setup_surface():
    from plugin_curiosity.mission import prompt_fragment
    from plugin_curiosity.prompts import (
        ABILITY_CONTRACT,
        FDE_DOCTRINE,
        HEARTBEAT_CONTRACT,
        JOB_DESCRIPTION_SHAPE,
        MATERIALITY_RULE,
        NO_BLAME,
        RATIFICATION_FORCING,
        VALUE_QUESTION_CADENCE,
    )
    from plugin_curiosity.research import _KICKOFF_CONTENT, DAILY_RESEARCH_TARGET
    from plugin_curiosity.review import WEEKLY_REVIEW_TARGET

    kickoff = _KICKOFF_CONTENT.format(statement="x")
    for const in (
        FDE_DOCTRINE,
        JOB_DESCRIPTION_SHAPE,
        ABILITY_CONTRACT,
        VALUE_QUESTION_CADENCE,
    ):
        assert kickoff.count(const) == 1

    mission = {"statement": "x", "autonomy_rung": 1, "risk_ceiling": "low"}
    frag = prompt_fragment(mission, "setup")
    for const in (
        FDE_DOCTRINE,
        ABILITY_CONTRACT,
        VALUE_QUESTION_CADENCE,
        MATERIALITY_RULE,
        NO_BLAME,
    ):
        assert const in frag
    # work fragment stays lean — no setup-phase doctrine
    assert FDE_DOCTRINE not in prompt_fragment(mission, "work")

    # heartbeat re-scores the ladder; ratification covers the JD
    assert "ability_list" in HEARTBEAT_CONTRACT
    assert "ability_task_set" in HEARTBEAT_CONTRACT
    assert "job-description" in RATIFICATION_FORCING
    # daily pass reads the ladder and judges materiality
    assert "ability_list" in DAILY_RESEARCH_TARGET
    assert "role_pivot" in DAILY_RESEARCH_TARGET
    # weekly review audits the JD shape and the ladder
    assert "job-description" in WEEKLY_REVIEW_TARGET
    assert "ability_list" in WEEKLY_REVIEW_TARGET


def test_jd_stub_seeded_on_mission_set():
    from plugin_curiosity.mission import _STUB_SLUGS

    assert "job-description" in _STUB_SLUGS


# ---- overview v2 -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_overview_v2_ladder_jd_and_pivots(sf, ctx, store):
    from plugin_curiosity.goals import GoalStore
    from plugin_curiosity.loops import LoopStore
    from plugin_curiosity.overview import build_overview
    from plugin_curiosity.scopes import ScopeStore
    from plugin_curiosity.telemetry import HeartbeatStore

    await store.set("run customer onboarding")
    sc = ScopeStore(sf)
    await sc.stage_set("S2")
    gs = GoalStore(sf)
    ls = LoopStore(sf)
    hb = HeartbeatStore(sf)
    ab = AbilityStore(sf)

    kwargs = dict(
        missions=store, scope_store=sc, goal_store=gs, loop_store=ls,
        heartbeat_store=hb, ability_store=ab,
    )

    # upgrade window: no abilities yet → stage-weighted fallback (S2 = 50%)
    o = await build_overview(ctx, **kwargs)
    assert o["abilities"] == []
    assert o["setup_percent"] == o["setup"]["percent"] == 50

    # ladder lands → ability mean wins the dial
    a = await ab.upsert("Ability to greet every signup", tasks=["channel", "playbook"])
    await ab.task_set(a["id"], "channel", "done")
    wiki = ctx.provider_registry.get("wiki")
    await wiki.upsert_page("job-description", "Job Description", _JD_GOOD)
    await sc.plan_change_add("retention beats acquisition", kind="role_pivot")

    o = await build_overview(ctx, **kwargs)
    assert len(o["abilities"]) == 1
    assert o["setup_percent"] == 50  # (1 + 0) / 2 tasks — ability mean, not stage
    assert o["abilities"][0]["percent"] == 50
    jd = o["job_description"]
    assert jd["shape_ok"] is True
    assert jd["role_version"] == 2  # the pivot bumped it
    assert jd["latest_pivot"]["kind"] == "role_pivot"
    assert o["mission"]["role_version"] == 2
    # the pivot is an owner decision → needs_from_you; marked in activity
    assert any(n["kind"] == "pivot" for n in o["needs_from_you"])
    plan_events = [e for e in o["activity"] if e["kind"] == "plan"]
    assert any(e["text"].startswith("ROLE PIVOT — ") for e in plan_events)
    # 9.002 fields all preserved
    for key in ("gap_board", "loops", "value_log", "heartbeats", "pace",
                "sentiment", "next_up", "wiki_shelf", "noc", "activity"):
        assert key in o


@pytest.mark.asyncio
async def test_ability_tools_registered(sf, ctx, store):
    from plugin_curiosity.abilities import register_tools

    register_tools(ctx, AbilityStore(sf))
    for name in ("ability_upsert", "ability_task_set", "ability_list"):
        tool_def, _ = ctx.tool_registry.registered[name]
        assert tool_def.policy == "auto_approve"

    await store.set("run customer onboarding")
    _, upsert = ctx.tool_registry.registered["ability_upsert"]
    r = await upsert(title="Ability to answer questions", tasks=["read docs"])
    assert r["ability"]["percent"] == 0
    _, task_set = ctx.tool_registry.registered["ability_task_set"]
    r2 = await task_set(ability=r["ability"]["id"], task="read docs", status="done")
    assert r2["task"]["status"] == "done"
    _, lister = ctx.tool_registry.registered["ability_list"]
    out = await lister()
    assert out["setup_percent"] == 100


@pytest.mark.asyncio
async def test_upgrade_nudge_once_for_pre_ladder_mission(sf, ctx, store):
    import plugin_curiosity as pc

    await store.set("legacy mission from 0.8.1")
    ab = AbilityStore(sf)
    sent = await pc.maybe_nudge_ability_upgrade(ctx, store, ab)
    assert sent is True
    (post,) = [p for p in ctx.muted_posts if p["title"] == "Your qualification ladder"]
    assert "ability_upsert" in post["content"]
    # once ever — flag stops the second send
    assert await pc.maybe_nudge_ability_upgrade(ctx, store, ab) is False


@pytest.mark.asyncio
async def test_upgrade_nudge_skipped_when_ladder_exists(sf, ctx, store):
    import plugin_curiosity as pc

    await store.set("fresh 0.9.0 mission")
    ab = AbilityStore(sf)
    await ab.upsert("Ability to do the job", tasks=["step one"])
    assert await pc.maybe_nudge_ability_upgrade(ctx, store, ab) is False
    assert not [p for p in ctx.muted_posts if p["title"] == "Your qualification ladder"]
