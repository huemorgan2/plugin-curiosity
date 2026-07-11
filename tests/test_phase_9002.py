"""9.002 — Missions UI: the dependency gate, heartbeat telemetry, the
overview aggregation, and the NOC-wall structure forcing.

The gate tests exercise reevaluate_gate directly (not on_load) — the gate's
verdict must not depend on engine setup, and the late-activation path is
exactly what the serving-loop re-check calls."""

from __future__ import annotations

import types
from datetime import UTC, datetime, timedelta

import pytest
from conftest import (
    FakeConfigRegistry,
    FakeEvents,
    FakeProviderRegistry,
    FakeToolRegistry,
    FakeWikiProvider,
)

from plugin_curiosity import (
    DEPENDENCY_BLOCKED_FLAG,
    DEPENDENCY_NOTICE_FLAG,
    CuriosityPlugin,
    _flag_get,
    blocked_fragment,
    missing_dependencies,
)


def _bare_ctx(sf, *, wiki=True, scheduler=True):
    """A ctx with NO curiosity tools pre-registered — the gate decides."""
    c = types.SimpleNamespace(
        tool_registry=FakeToolRegistry(),
        provider_registry=FakeProviderRegistry(FakeWikiProvider() if wiki else None),
        config_registry=FakeConfigRegistry(),
        events=FakeEvents(),
        db_session_factory=sf,
        muted_posts=[],
    )
    c.tool_registry.scheduler_installed = scheduler

    async def send_muted_message(title, content, **kw):
        c.muted_posts.append({"title": title, "content": content, **kw})
        return {"ok": True}

    c.send_muted_message = send_muted_message
    return c


def _plugin(sf) -> CuriosityPlugin:
    """A plugin with stores wired but on_load never run (no engine needed)."""
    from plugin_curiosity.comms import ReflectionLog
    from plugin_curiosity.goals import GoalStore
    from plugin_curiosity.loops import LoopStore
    from plugin_curiosity.mission import MissionStore
    from plugin_curiosity.scopes import ScopeStore
    from plugin_curiosity.telemetry import HeartbeatStore

    p = CuriosityPlugin()
    p._store = MissionStore(sf)
    p._goals = GoalStore(sf)
    p._scopes = ScopeStore(sf)
    p._loops = LoopStore(sf)
    p._heartbeats = HeartbeatStore(sf)
    p._reflections = ReflectionLog(sf)
    return p


# ---- manifest ---------------------------------------------------------------


def test_manifest_hard_dependencies_declared():
    import tomllib
    from pathlib import Path

    m = CuriosityPlugin.manifest
    assert m.depends_on == ["plugin-wiki", "plugin-scheduler"]
    with open(Path(__file__).parent.parent / "plugin_curiosity" / "luna-plugin.toml", "rb") as f:
        toml = tomllib.load(f)
    assert toml["depends_on"] == m.depends_on


def test_manifest_sidebar_section():
    secs = CuriosityPlugin.manifest.sidebar_sections
    assert len(secs) == 2  # 10.002: Missions + NOC
    assert secs[0].id == "missions"
    assert secs[0].label == "Missions"


def test_ui_assets_ship_with_the_package():
    from pathlib import Path

    ui = Path(__file__).parent.parent / "plugin_curiosity" / "ui"
    for name in ("index.html", "app.js", "style.css"):
        assert (ui / name).exists(), f"ui/{name} missing"


# ---- dependency gate ----------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_satisfied_activates(sf):
    ctx = _bare_ctx(sf)
    p = _plugin(sf)
    missing = await p.reevaluate_gate(ctx)
    assert missing == []
    assert p._activated
    for tool in ("mission_set", "heartbeat_report", "scope_set", "goal_set", "loop_open"):
        assert tool in ctx.tool_registry.registered
    assert await _flag_get(sf, DEPENDENCY_BLOCKED_FLAG) == ""
    frags = await p.prompt_sections()
    assert frags and "PAUSED" not in frags[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("wiki", "scheduler", "expected"),
    [
        (False, True, ["plugin-wiki"]),
        (True, False, ["plugin-scheduler"]),
        (False, False, ["plugin-wiki", "plugin-scheduler"]),
    ],
)
async def test_gate_missing_dep_goes_inert(sf, wiki, scheduler, expected):
    ctx = _bare_ctx(sf, wiki=wiki, scheduler=scheduler)
    p = _plugin(sf)
    missing = await p.reevaluate_gate(ctx)
    assert missing == expected
    assert not p._activated
    assert ctx.tool_registry.registered == {}  # INERT: zero tools
    assert await _flag_get(sf, DEPENDENCY_BLOCKED_FLAG) == ",".join(expected)
    frags = await p.prompt_sections()
    assert len(frags) == 1 and "PAUSED" in frags[0]
    for name in expected:
        assert name in frags[0]


@pytest.mark.asyncio
async def test_gate_late_activation(sf):
    """The load-order race: inert at on_load, the serving-loop re-check finds
    the dep and activates without a restart."""
    ctx = _bare_ctx(sf, scheduler=False)
    p = _plugin(sf)
    assert await p.reevaluate_gate(ctx) == ["plugin-scheduler"]
    assert not p._activated
    ctx.tool_registry.scheduler_installed = True  # scheduler finished loading
    assert await p.reevaluate_gate(ctx) == []
    assert p._activated
    assert "heartbeat_report" in ctx.tool_registry.registered


@pytest.mark.asyncio
async def test_gate_reactivation_is_idempotent(sf):
    ctx = _bare_ctx(sf)
    p = _plugin(sf)
    await p.reevaluate_gate(ctx)
    n = len(ctx.tool_registry.registered)
    await p.reevaluate_gate(ctx)  # no double registration
    assert len(ctx.tool_registry.registered) == n


@pytest.mark.asyncio
async def test_blocked_notice_once_per_missing_set(sf):
    ctx = _bare_ctx(sf, wiki=False)
    p = _plugin(sf)
    assert await p.maybe_send_blocked_notice(ctx, ["plugin-wiki"]) is True
    assert len(ctx.muted_posts) == 1
    assert "plugin-wiki" in ctx.muted_posts[0]["content"]
    # same missing set again → silent
    assert await p.maybe_send_blocked_notice(ctx, ["plugin-wiki"]) is False
    assert len(ctx.muted_posts) == 1
    # a DIFFERENT missing set is a new fact → one more notice
    assert await p.maybe_send_blocked_notice(ctx, ["plugin-scheduler"]) is True
    assert len(ctx.muted_posts) == 2
    assert await _flag_get(sf, DEPENDENCY_NOTICE_FLAG) == "plugin-scheduler"


def test_blocked_fragment_names_the_missing_and_the_why():
    frag = blocked_fragment(["plugin-wiki"])
    assert "plugin-wiki" in frag
    assert "wiki is where I keep" in frag
    assert "marketplace" in frag


def test_missing_dependencies_probes_both_seams(sf):
    assert missing_dependencies(_bare_ctx(sf)) == []
    assert missing_dependencies(_bare_ctx(sf, wiki=False)) == ["plugin-wiki"]
    assert missing_dependencies(_bare_ctx(sf, scheduler=False)) == ["plugin-scheduler"]


# ---- heartbeat telemetry ------------------------------------------------------


@pytest.mark.asyncio
async def test_heartbeat_store_requires_active_mission(sf):
    from plugin_curiosity.telemetry import HeartbeatStore

    with pytest.raises(LookupError):
        await HeartbeatStore(sf).add(1, 2, 0, "chipper")


@pytest.mark.asyncio
async def test_heartbeat_roundtrip_clamps_and_truncates(sf, store):
    from plugin_curiosity.telemetry import HeartbeatStore

    await store.set("learn the domain")
    hb = HeartbeatStore(sf)
    r = await hb.add(-3, 2, -1, "  " + "x" * 200, note="  first fire ")
    assert r["streak"] == 0 and r["wobbles"] == 0 and r["gaps_open"] == 2
    assert len(r["morale"]) == 80
    assert r["note"] == "first fire"
    r2 = await hb.add(1, 1, 0, "steady")
    rows = await hb.list()
    assert [x["id"] for x in rows] == [r2["id"], r["id"]]  # newest first
    latest = await hb.latest()
    assert latest["morale"] == "steady"


@pytest.mark.asyncio
async def test_heartbeat_tool_emits_ui_event(sf, store, ctx):
    from plugin_curiosity import telemetry
    from plugin_curiosity.telemetry import HeartbeatStore

    await store.set("learn the domain")
    telemetry.register_tools(ctx, HeartbeatStore(sf))
    handler = ctx.tool_registry.registered["heartbeat_report"][1]
    out = await handler(streak=2, gaps_open=1, wobbles=0, morale="bright", note="all green")
    assert out["report"]["streak"] == 2
    hb_events = [e for e in ctx.events.emitted if e[1]["event"] == "heartbeat"]
    assert len(hb_events) == 1
    assert hb_events[0][0] == "ui.plugin.event"
    assert hb_events[0][1]["plugin"] == "plugin-curiosity"
    assert hb_events[0][1]["payload"]["morale"] == "bright"


@pytest.mark.asyncio
async def test_heartbeat_tool_without_mission_returns_error(sf, ctx):
    from plugin_curiosity import telemetry
    from plugin_curiosity.telemetry import HeartbeatStore

    telemetry.register_tools(ctx, HeartbeatStore(sf))
    handler = ctx.tool_registry.registered["heartbeat_report"][1]
    out = await handler(streak=1, gaps_open=0, wobbles=0, morale="keen")
    assert "error" in out
    assert not [e for e in ctx.events.emitted if e[1]["event"] == "heartbeat"]


# ---- heartbeat dedupe (9.002 prod e2e: TOCTOU duplicate) ----------------------


def _seed_duplicate_heartbeats(ctx):
    from plugin_curiosity.prompts import HEARTBEAT_NAME

    ctx.tool_registry.existing_triggers = [
        {"id": "trg-daily", "name": "curiosity-daily-research",
         "created_at": "2026-07-09T22:20:22Z"},
        {"id": "trg-young", "name": HEARTBEAT_NAME,
         "created_at": "2026-07-09T22:22:53Z"},
        {"id": "trg-old", "name": HEARTBEAT_NAME,
         "created_at": "2026-07-09T22:20:54Z"},
    ]


@pytest.mark.asyncio
async def test_dedupe_reaps_extras_keeping_oldest(sf):
    from plugin_curiosity import research

    ctx = _bare_ctx(sf)
    _seed_duplicate_heartbeats(ctx)
    assert await research.dedupe_heartbeats(ctx) == 1
    ids = [t["id"] for t in ctx.tool_registry.existing_triggers]
    assert "trg-old" in ids and "trg-daily" in ids
    assert ctx.tool_registry.trigger_deleted == ["trg-young"]


@pytest.mark.asyncio
async def test_dedupe_noop_on_single_and_none(sf):
    from plugin_curiosity import research
    from plugin_curiosity.prompts import HEARTBEAT_NAME

    ctx = _bare_ctx(sf)
    assert await research.dedupe_heartbeats(ctx) == 0
    ctx.tool_registry.existing_triggers = [
        {"id": "trg-1", "name": HEARTBEAT_NAME, "created_at": "2026-07-09T22:20:54Z"}]
    assert await research.dedupe_heartbeats(ctx) == 0
    assert ctx.tool_registry.trigger_deleted == []


@pytest.mark.asyncio
async def test_dedupe_unknowable_without_scheduler(sf):
    from plugin_curiosity import research

    ctx = _bare_ctx(sf, scheduler=False)
    assert await research.dedupe_heartbeats(ctx) is None


@pytest.mark.asyncio
async def test_heartbeat_report_reaps_duplicates(sf, store, ctx):
    """Every fire ends with heartbeat_report — the reaper rides it, so a
    duplicate born of racing turns dies within one heartbeat cycle."""
    from plugin_curiosity import telemetry
    from plugin_curiosity.telemetry import HeartbeatStore

    await store.set("learn the domain")
    _seed_duplicate_heartbeats(ctx)
    telemetry.register_tools(ctx, HeartbeatStore(sf))
    handler = ctx.tool_registry.registered["heartbeat_report"][1]
    out = await handler(streak=1, gaps_open=2, wobbles=0, morale="steady")
    assert "report" in out
    assert ctx.tool_registry.trigger_deleted == ["trg-young"]


def test_contract_single_creator_clause():
    """The race fix's prompt half: creation belongs to the kickoff (and the
    recreate nudge) alone; conversation turns may only update."""
    from plugin_curiosity.prompts import HEARTBEAT_CONTRACT
    from plugin_curiosity.research import _KICKOFF_CONTENT

    assert "born ONLY in your kickoff" in HEARTBEAT_CONTRACT
    assert "NEVER create it in an ordinary conversation" in HEARTBEAT_CONTRACT
    assert "reaped automatically" in HEARTBEAT_CONTRACT
    assert "THIS step is where it is born" in _KICKOFF_CONTENT


@pytest.mark.asyncio
async def test_mutations_emit_changed_events(sf, ctx, store):
    """The pane refetches on any 'changed' — every write tool must emit one."""
    handler = ctx.tool_registry.registered["mission_set"][1]
    await handler(statement="learn the domain")
    whats = [e[1]["payload"].get("what") for e in ctx.events.emitted if e[1]["event"] == "changed"]
    assert "mission" in whats


@pytest.mark.asyncio
async def test_emit_ui_event_never_raises():
    from plugin_curiosity.telemetry import emit_ui_event

    no_events = types.SimpleNamespace()  # ctx without .events (old core / tests)
    assert await emit_ui_event(no_events, "changed", {}) is False

    class _Boom:
        async def emit(self, *a, **kw):
            raise RuntimeError("bus down")

    boom = types.SimpleNamespace(events=_Boom())
    assert await emit_ui_event(boom, "changed", {}) is False


# ---- pace + sentiment -----------------------------------------------------------


@pytest.mark.parametrize(
    ("phase", "stage", "age", "overdue", "band"),
    [
        ("setup", "S1", 0, 0, "ahead"),
        ("setup", "S0", 0, 0, "on-track"),  # S0 day one is not "ahead"
        ("setup", "S1", 2, 0, "on-track"),
        ("setup", "S1", 4, 0, "dragging"),
        ("setup", "S2", 3, 0, "dragging"),  # ratification-forcing threshold
        ("setup", "S1", 7, 0, "stalled"),
        ("setup", "S2", 5, 0, "stalled"),
        ("setup", "S1", 2, 1, "dragging"),
        ("setup", "S1", 2, 2, "stalled"),
        ("work", "S5", 30, 0, "on-track"),  # work: stage age is irrelevant
        ("work", "S5", 0, 1, "dragging"),
        ("work", "S5", 0, 3, "stalled"),
    ],
)
def test_compute_pace_bands(phase, stage, age, overdue, band):
    from plugin_curiosity.telemetry import compute_pace

    out = compute_pace(
        agent_phase=phase, setup_stage=stage, stage_age_days=age, overdue_loops=overdue
    )
    assert out["band"] == band, out
    assert out["reasons"]  # every verdict is explainable


def test_compute_pace_reports_last_report_age():
    from plugin_curiosity.telemetry import compute_pace

    now = datetime.now(UTC)
    out = compute_pace(
        agent_phase="setup", setup_stage="S1", stage_age_days=0, overdue_loops=0,
        now=now, last_report_at=now - timedelta(hours=26),
    )
    assert out["last_report_age_hours"] == 26


@pytest.mark.parametrize(
    ("latest", "previous", "blocked", "band"),
    [
        (None, None, 0, "neutral"),
        (None, None, 1, "blocked"),
        ({"streak": 3, "gaps_open": 1, "wobbles": 0}, None, 0, "positive"),
        ({"streak": 3, "gaps_open": 1, "wobbles": 2}, None, 0, "strained"),
        ({"streak": 1, "gaps_open": 4, "wobbles": 0}, {"streak": 0, "gaps_open": 2, "wobbles": 0}, 0, "strained"),
        ({"streak": 1, "gaps_open": 2, "wobbles": 0}, {"streak": 0, "gaps_open": 2, "wobbles": 0}, 0, "neutral"),
        ({"streak": 5, "gaps_open": 0, "wobbles": 0}, None, 2, "blocked"),  # blocked wins
    ],
)
def test_compute_sentiment_bands(latest, previous, blocked, band):
    from plugin_curiosity.telemetry import compute_sentiment

    assert compute_sentiment(latest, previous, blocked_on_owner=blocked) == band


# ---- NOC parsers -----------------------------------------------------------------


_CRITERIA_BODY = """Intro prose.

| criterion | measure | target | horizon |
| --- | --- | --- | --- |
| Coverage | pages with citations | 90% | end of Q3 |
| Freshness | median page age | < 7 days | weekly |

## Weekly scores

- 2026-07-01 | Coverage | on-track | 61% and climbing, see [[value-log]]
- 2026-07-01 | Freshness | at-risk | median 11d after vacation
- 2026-07-08 | Coverage | met | 92%, see [[value-log]]
- 2026-07-08 | Freshness | on-track | median 6d
- malformed line without pipes
- 2026-07-08 | Ghost | bogus-status | ignored
"""


def test_parse_criteria_table():
    from plugin_curiosity.overview import parse_criteria_table

    rows = parse_criteria_table(_CRITERIA_BODY)
    assert [r["criterion"] for r in rows] == ["Coverage", "Freshness"]
    assert rows[0]["target"] == "90%"
    assert rows[1]["horizon"] == "weekly"
    assert parse_criteria_table("no table here") == []


def test_parse_weekly_scores():
    from plugin_curiosity.overview import parse_weekly_scores

    scores = parse_weekly_scores(_CRITERIA_BODY)
    assert len(scores) == 4  # malformed + bogus-status skipped
    assert scores[0] == {
        "date": "2026-07-01", "criterion": "Coverage", "status": "on-track",
        "evidence": "61% and climbing, see [[value-log]]",
    }


def test_build_noc_tiles_and_incidents():
    from plugin_curiosity.overview import build_noc, parse_criteria_table, parse_weekly_scores

    noc = build_noc(parse_criteria_table(_CRITERIA_BODY), parse_weekly_scores(_CRITERIA_BODY))
    cov = next(t for t in noc["tiles"] if t["criterion"] == "Coverage")
    assert cov["latest"]["status"] == "met"
    assert cov["uptime_pct"] == 100
    fresh = next(t for t in noc["tiles"] if t["criterion"] == "Freshness")
    assert fresh["uptime_pct"] == 50
    assert [i["status"] for i in noc["incidents"]] == ["at-risk"]


# ---- overview aggregation ---------------------------------------------------------


async def _seed(sf, ctx, store):
    """Mission at S2 with a scope, a goal, a loop, a value entry, a heartbeat."""
    from plugin_curiosity.goals import GoalStore
    from plugin_curiosity.loops import LoopStore
    from plugin_curiosity.scopes import ScopeStore
    from plugin_curiosity.telemetry import HeartbeatStore

    await store.set("map the support workflow")
    scope_store = ScopeStore(sf)
    await scope_store.add("knowledge", "ticket taxonomy")
    await scope_store.stage_set("S2")
    goal_store = GoalStore(sf)
    await goal_store.add("chart the top 10 ticket types", target_date="2026-07-20")
    loop_store = LoopStore(sf)
    await loop_store.open("question", "which CRM is canonical?", who="owner")
    v = await loop_store.value_add("triage cheat-sheet", "see [[value-log]]")
    hb = HeartbeatStore(sf)
    await hb.add(2, 1, 0, "focused", note="taxonomy half-mapped")
    return scope_store, goal_store, loop_store, hb, v


@pytest.mark.asyncio
async def test_overview_contract(sf, ctx, store):
    from plugin_curiosity.overview import build_overview

    scope_store, goal_store, loop_store, hb, _ = await _seed(sf, ctx, store)
    o = await build_overview(
        ctx, missions=store, scope_store=scope_store, goal_store=goal_store,
        loop_store=loop_store, heartbeat_store=hb,
    )
    assert o["blocked"] is None
    assert o["mission"]["statement"] == "map the support workflow"
    assert o["state"]["setup_stage"] == "S2"
    # setup checklist: S0-S2 done (3/6), S3 current
    assert o["setup"]["percent"] == 50
    statuses = {s["id"]: s["status"] for s in o["setup"]["stages"]}
    assert statuses["S2"] == "done" and statuses["S3"] == "current"
    assert o["gap_board"][0]["kind"] == "knowledge"
    assert len(o["goals"]) == 1
    assert o["loops"]["open"] and o["loops"]["overdue"] == 0
    assert o["heartbeats"]["latest"]["morale"] == "focused"
    assert o["pace"]["band"] in ("ahead", "on-track")
    assert o["sentiment"] == "positive"  # streak 2, no wobbles
    # needs-from-you: the owner question + the S2 ratify CTA
    kinds = [n["kind"] for n in o["needs_from_you"]]
    assert "question" in kinds and "ratify" in kinds
    # wiki shelf lists all 10 slugs (10.001 adds job-description) and
    # tolerates missing pages
    assert len(o["wiki_shelf"]) == 10
    assert all("exists" in p for p in o["wiki_shelf"])
    assert any(a["kind"] == "heartbeat" for a in o["activity"])
    assert any(n["kind"] == "stage" for n in o["next_up"])


@pytest.mark.asyncio
async def test_overview_reports_blocked(sf, store):
    from plugin_curiosity.goals import GoalStore
    from plugin_curiosity.loops import LoopStore
    from plugin_curiosity.scopes import ScopeStore
    from plugin_curiosity.telemetry import HeartbeatStore

    from plugin_curiosity.overview import build_overview

    ctx = _bare_ctx(sf, wiki=False)
    o = await build_overview(
        ctx, missions=store, scope_store=ScopeStore(sf), goal_store=GoalStore(sf),
        loop_store=LoopStore(sf), heartbeat_store=HeartbeatStore(sf),
    )
    assert o["blocked"]["missing"] == ["plugin-wiki"]
    assert "plugin-wiki" in o["blocked"]["deps"]
    assert o["mission"] is None


@pytest.mark.asyncio
async def test_overview_counts_overdue_and_blocked_on_owner(sf, ctx, store):
    from plugin_curiosity.models import Loop
    from plugin_curiosity.overview import build_overview
    from plugin_curiosity.goals import GoalStore
    from plugin_curiosity.loops import LoopStore
    from plugin_curiosity.scopes import ScopeStore
    from plugin_curiosity.telemetry import HeartbeatStore

    await store.set("map the support workflow")
    loop_store = LoopStore(sf)
    lp = await loop_store.open("waiting_on", "owner to share CRM export", who="owner")
    # age the nudge date into the past
    import uuid as _uuid

    async with sf() as s:
        row = await s.get(Loop, _uuid.UUID(lp["id"]))
        row.next_nudge_at = datetime.now(UTC) - timedelta(days=1)
        await s.commit()
    o = await build_overview(
        ctx, missions=store, scope_store=ScopeStore(sf), goal_store=GoalStore(sf),
        loop_store=loop_store, heartbeat_store=HeartbeatStore(sf),
    )
    assert o["loops"]["overdue"] == 1
    assert o["sentiment"] == "blocked"
    assert o["pace"]["band"] in ("dragging", "stalled")


@pytest.mark.asyncio
async def test_mission_detail_drilldown(sf, ctx, store):
    from plugin_curiosity.overview import mission_detail

    scope_store, *_ = await _seed(sf, ctx, store)
    mission_id = (await store.get())["id"]
    d = await mission_detail(sf, mission_id)
    assert d["mission"]["id"] == mission_id
    assert len(d["scopes"]) == 1
    assert len(d["loops"]) == 1
    assert len(d["value_log"]) == 1
    assert len(d["heartbeats"]) == 1
    assert await mission_detail(sf, "not-a-uuid") is None


# ---- prompt forcing (E) ------------------------------------------------------------


def test_heartbeat_contract_forces_the_report_tool():
    from plugin_curiosity.prompts import HEARTBEAT_CONTRACT

    assert "heartbeat_report" in HEARTBEAT_CONTRACT
    assert "morale" in HEARTBEAT_CONTRACT


def test_kickoff_forces_success_table_shape():
    from plugin_curiosity.prompts import SUCCESS_TABLE_SHAPE
    from plugin_curiosity.research import _KICKOFF_CONTENT

    assert "| criterion | measure | target | horizon |" in SUCCESS_TABLE_SHAPE
    assert SUCCESS_TABLE_SHAPE in _KICKOFF_CONTENT


def test_weekly_review_forces_scores_shape_in_both_phases():
    from plugin_curiosity.prompts import WEEKLY_SCORES_SHAPE
    from plugin_curiosity.review import WEEKLY_REVIEW_TARGET

    assert "Weekly scores" in WEEKLY_SCORES_SHAPE
    # one target string, two branches — the shape must appear in each
    assert WEEKLY_REVIEW_TARGET.count(WEEKLY_SCORES_SHAPE) == 2
    assert "Role wall" in WEEKLY_REVIEW_TARGET
    assert "DRIFT AUDIT" in WEEKLY_REVIEW_TARGET
