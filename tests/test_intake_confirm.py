"""Phase11/phase12 (11.001/M1, confirmed-not-received) — intake & confirm:
- mission_draft captures the owner's words verbatim, oldest-wins convergent;
- mission_set consumes every draft and auto-fills origin_statement;
- the 24 h draft nudger re-asks ONCE and NEVER promotes (phase12);
- mission_confirm stamps confirmed_at (idempotent), registers the recurring
  schedules, and releases the deep pass — schedules and the deep S0→S2 pass
  never fire from mission_set or any timeout;
- the kickoff split: mission_set posts an instant BRIEF; an unconfirmed
  mission past 12 h gets ONE re-ask nudge, never an unasked deep pass;
- prompts and overview surface the gate ("waiting for your yes").
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from plugin_curiosity import mission as mission_mod
from plugin_curiosity import research


async def call(ctx, tool: str, **kwargs):
    return await ctx.tool_registry.registered[tool][1](**kwargs)


@pytest.fixture
def kctx(ctx, sf, monkeypatch):
    ctx.db_session_factory = sf
    monkeypatch.setattr(research, "KICKOFF_DELAY_S", 0.0)
    return ctx


async def _settle():
    """Let fire-and-forget kickoff tasks run to their post."""
    for _ in range(10):
        await asyncio.sleep(0.01)


def _posts(ctx, title):
    return [p for p in ctx.muted_posts if p["title"] == title]


async def _backdate_draft(sf, hours: float) -> None:
    from sqlalchemy import update

    from plugin_curiosity.models import MissionDraft

    async with sf() as s:
        await s.execute(
            update(MissionDraft).values(
                created_at=datetime.now(UTC) - timedelta(hours=hours)
            )
        )
        await s.commit()


async def _backdate_mission(sf, hours: float) -> None:
    from sqlalchemy import update

    from plugin_curiosity.models import Mission

    async with sf() as s:
        await s.execute(
            update(Mission)
            .where(Mission.active)
            .values(created_at=datetime.now(UTC) - timedelta(hours=hours))
        )
        await s.commit()


# ---- Unit 1: draft verbatim, oldest-wins, set consumes ----------------------


@pytest.mark.asyncio
async def test_draft_stores_verbatim_with_server_age(store):
    d = await store.draft("  keep my inbox at zero and chase invoices  ")
    assert d["verbatim"] == "keep my inbox at zero and chase invoices"
    assert d["age_hours"] is not None and d["age_hours"] < 0.1
    assert (await store.draft_get())["id"] == d["id"]


@pytest.mark.asyncio
async def test_draft_oldest_wins_convergent(store):
    d1 = await store.draft("first words")
    d2 = await store.draft("rival words from a racing turn")
    assert d2["id"] == d1["id"] and d2["verbatim"] == "first words"
    assert (await store.draft_get())["verbatim"] == "first words"


@pytest.mark.asyncio
async def test_draft_rejects_empty(ctx):
    assert "error" in await call(ctx, "mission_draft", verbatim="   ")


@pytest.mark.asyncio
async def test_mission_set_consumes_draft_and_autofills_origin(ctx, store):
    await store.draft("chase my invoices")
    r = await call(ctx, "mission_set", statement="own accounts-receivable follow-up")
    assert r["mission"]["origin_statement"] == "chase my invoices"
    assert await store.draft_get() is None  # every draft consumed


@pytest.mark.asyncio
async def test_mission_set_explicit_origin_wins_and_still_consumes(ctx, store):
    await store.draft("draft words")
    r = await call(
        ctx, "mission_set", statement="sharpened", origin_statement="owner said this"
    )
    assert r["mission"]["origin_statement"] == "owner said this"
    assert await store.draft_get() is None


@pytest.mark.asyncio
async def test_mission_get_surfaces_draft_with_steering(ctx, store):
    await store.draft("grow the newsletter")
    r = await call(ctx, "mission_get")
    assert r["mission"] is None
    assert r["draft"]["verbatim"] == "grow the newsletter"
    assert "mission_set" in r["note"] and "origin_statement" in r["note"]


@pytest.mark.asyncio
async def test_mission_draft_tool_steers_one_round_then_set(ctx):
    r = await call(ctx, "mission_draft", verbatim="run my hiring pipeline")
    assert r["draft"]["verbatim"] == "run my hiring pipeline"
    nxt = r["next"]
    assert "ONE round" in nxt and "mission_set" in nxt
    assert "ON-TOPIC message" in nxt and "impatience" in nxt.lower()
    assert "DETOUR" in nxt  # a reply about something else never saves
    # mission_set rides the deferred "curiosity" tool group (luna 046
    # grouping) — the draft turn must load it or the save turn can't happen
    assert "load_tools(group='curiosity')" in nxt


def test_gate_surfaces_all_teach_the_load_tools_hop():
    # a gated agent that skips the load hop hits an unknown tool on the save
    # turn (empty result, no row) — every gate surface must teach the hop
    assert 'load_tools(group="curiosity")' in mission_mod.MISSION_GATE_FLOW
    assert "load_tools" in mission_mod._mission_gate_state_block(
        "SETUP STATE:\n  ☐ mission"
    )
    assert "load_tools(group='curiosity')" in mission_mod.prompt_fragment(None)


# ---- Unit 2: one-round cap lives in the prompts -----------------------------


def test_gate_flow_draft_first_one_round_impatience():
    flow = mission_mod.MISSION_GATE_FLOW
    assert "mission_draft" in flow and "VERBATIM" in flow.upper()
    assert "AT MOST 2-3" in flow
    assert "ONLY question round" in flow
    assert "next ON-TOPIC message ends intake" in flow
    assert "IMPATIENCE OVERRIDES EVERYTHING" in flow
    assert "origin_statement" in flow


def test_gate_flow_detection_and_detour_rules():
    """phase12: detection requires work handed to YOU (never a passing
    mention), and a detour reply never ends intake or becomes the mission."""
    flow = mission_mod.MISSION_GATE_FLOW
    assert "hands YOU work to own" in flow
    assert "NOT a mission" in flow  # passing mentions
    assert "DETOUR" in flow
    assert "confirmed, not received" in flow


def test_gate_state_block_names_draft_then_set():
    block = mission_mod._mission_gate_state_block("SETUP STATE:\n  ☐ mission")
    assert "mission_draft" in block and "mission_set" in block
    assert "2-3" in block and "ON-TOPIC" in block
    assert "detour" in block  # a detour reply never triggers the save


def test_missionless_fragment_teaches_draft_then_set():
    frag = mission_mod.prompt_fragment(None)
    assert "mission_draft IN THAT SAME TURN" in frag
    assert "origin_statement" in frag
    assert "next ON-TOPIC message save" in frag
    assert "detour" in frag
    assert "first-look" in frag  # promises the brief, not the deep pass
    # phase12: the fragment must not promise schedules at mission_set
    assert "wait for the owner's yes" in frag


# ---- Unit 3: the 24 h draft nudger (phase12 — never promotes) ---------------


@pytest.mark.asyncio
async def test_stale_draft_nudges_once_and_never_promotes(kctx, store, sf):
    mission_mod._draft_nudge_claims.clear()
    await store.draft("watch my competitors and brief me")
    await _backdate_draft(sf, 25)
    assert await mission_mod.nudge_stale_draft(kctx, store) == "nudged"
    # NOTHING was created or spent: no mission, no identity write, no
    # schedules, no wiki — the draft itself stays safe
    assert await store.get() is None
    assert (await store.draft_get())["verbatim"] == "watch my competitors and brief me"
    assert not kctx.config_registry.writes
    assert not kctx.tool_registry.trigger_created
    # the one nudge reflects the owner's verbatim words and bans the save
    nudges = _posts(kctx, mission_mod.DRAFT_NUDGE_TITLE)
    assert len(nudges) == 1
    assert "watch my competitors and brief me" in nudges[0]["content"]
    assert "Do NOT call mission_set" in nudges[0]["content"]
    assert nudges[0]["tools"] == mission_mod.DRAFT_NUDGE_TOOLS
    # janitor re-runs (on-load + per-turn) converge on the single nudge
    assert await mission_mod.nudge_stale_draft(kctx, store) == "already nudged"
    assert len(_posts(kctx, mission_mod.DRAFT_NUDGE_TITLE)) == 1


@pytest.mark.asyncio
async def test_draft_nudge_flag_survives_process_restart(kctx, store, sf):
    mission_mod._draft_nudge_claims.clear()
    await store.draft("owner words")
    await _backdate_draft(sf, 25)
    assert await mission_mod.nudge_stale_draft(kctx, store) == "nudged"

    mission_mod._draft_nudge_claims.clear()  # simulate a process restart
    assert await mission_mod.nudge_stale_draft(kctx, store) == "already nudged"
    assert len(_posts(kctx, mission_mod.DRAFT_NUDGE_TITLE)) == 1


@pytest.mark.asyncio
async def test_nudger_leaves_fresh_draft(kctx, store):
    await store.draft("fresh words")
    assert await mission_mod.nudge_stale_draft(kctx, store) == "draft fresh"
    assert (await store.draft_get())["verbatim"] == "fresh words"


@pytest.mark.asyncio
async def test_nudger_clears_drafts_when_mission_active(kctx, store):
    await call(kctx, "mission_set", statement="grow signups")
    await store.draft("late rival draft")  # raced in after the set
    assert await mission_mod.nudge_stale_draft(kctx, store) == "cleared 1 draft(s): mission active"
    assert await store.draft_get() is None


@pytest.mark.asyncio
async def test_nudger_noop_without_draft(kctx, store):
    assert await mission_mod.nudge_stale_draft(kctx, store) == "no draft"


# ---- Unit 4: the confirm gate -----------------------------------------------


@pytest.mark.asyncio
async def test_confirmed_at_unset_until_confirm_then_idempotent(kctx, store):
    r = await call(kctx, "mission_set", statement="grow signups")
    assert r["mission"]["confirmed_at"] is None

    c1 = await call(kctx, "mission_confirm")
    stamp = c1["mission"]["confirmed_at"]
    assert stamp is not None

    c2 = await call(kctx, "mission_confirm")  # idempotent: original stamp kept
    assert c2["mission"]["confirmed_at"] == stamp


@pytest.mark.asyncio
async def test_confirm_without_mission_errors(kctx):
    assert "error" in await call(kctx, "mission_confirm")


# ---- Unit 4b: recurring schedules wait for the yes (phase12) ----------------


@pytest.mark.asyncio
async def test_mission_set_registers_no_schedules(kctx, store):
    r = await call(kctx, "mission_set", statement="grow signups")
    assert r["schedules"] == mission_mod.SCHEDULES_GATED_NOTE
    assert kctx.tool_registry.trigger_created == []


@pytest.mark.asyncio
async def test_confirm_registers_schedules(kctx, store):
    await call(kctx, "mission_set", statement="grow signups")
    c = await call(kctx, "mission_confirm")
    assert c["schedules"] != mission_mod.SCHEDULES_GATED_NOTE
    created = {t["name"] for t in kctx.tool_registry.trigger_created}
    assert {s["name"] for s in mission_mod.MISSION_SCHEDULES} <= created


@pytest.mark.asyncio
async def test_schedules_sync_tool_gated_until_confirm(kctx, store):
    await call(kctx, "mission_set", statement="grow signups")
    r = await call(kctx, "mission_schedules_sync")
    assert r["schedules"] == mission_mod.SCHEDULES_GATED_NOTE
    assert kctx.tool_registry.trigger_created == []


@pytest.mark.asyncio
async def test_retract_schedules_withdraws_pre_phase12_registrations(kctx, store):
    """Upgrade path: a pre-0.20 version registered the recurring triggers at
    mission_set — on load, while the mission is still unconfirmed, they are
    withdrawn (they come back whole on mission_confirm)."""
    await call(kctx, "mission_set", statement="grow signups")
    # simulate the pre-0.20 registrations
    for i, s in enumerate(mission_mod.MISSION_SCHEDULES):
        kctx.tool_registry.existing_triggers.append(
            {"id": f"old-{i}", "name": s["name"], "target": s["target"],
             "expr_raw": s["schedule_expr"], "enabled": True}
        )
    m = await store.get()
    assert mission_mod.schedules_gated(m)
    result = await mission_mod.retract_schedules(kctx)
    assert result == f"retracted {len(mission_mod.MISSION_SCHEDULES)}"
    names = {s["name"] for s in mission_mod.MISSION_SCHEDULES}
    assert all(t["name"] not in names for t in kctx.tool_registry.existing_triggers)


@pytest.mark.asyncio
async def test_schedules_not_gated_once_confirmed_or_past_s0(kctx, store, sf):
    from sqlalchemy import update

    from plugin_curiosity.models import Mission

    await call(kctx, "mission_set", statement="grow signups")
    assert mission_mod.schedules_gated(await store.get())

    await call(kctx, "mission_confirm")
    assert not mission_mod.schedules_gated(await store.get())

    # grandfathered pre-split mission past S0: no confirmed_at, still exempt
    async with sf() as s:
        await s.execute(
            update(Mission).where(Mission.active).values(
                setup_stage="S1", confirmed_at=None
            )
        )
        await s.commit()
    assert not mission_mod.schedules_gated(await store.get())


@pytest.mark.asyncio
async def test_fragment_carries_confirm_wait_until_confirmed(kctx, store):
    await call(kctx, "mission_set", statement="grow signups")
    frag = mission_mod.prompt_fragment(await store.get())
    assert "NOT yet confirmed" in frag and "mission_confirm" in frag

    await call(kctx, "mission_confirm")
    frag2 = mission_mod.prompt_fragment(await store.get())
    assert "NOT yet confirmed" not in frag2


@pytest.mark.asyncio
async def test_overview_says_waiting_for_your_yes(kctx, store, sf):
    from plugin_curiosity.goals import GoalStore
    from plugin_curiosity.loops import LoopStore
    from plugin_curiosity.overview import build_overview
    from plugin_curiosity.scopes import ScopeStore
    from plugin_curiosity.telemetry import HeartbeatStore

    stores = dict(
        missions=store, scope_store=ScopeStore(sf), goal_store=GoalStore(sf),
        loop_store=LoopStore(sf), heartbeat_store=HeartbeatStore(sf),
    )
    await call(kctx, "mission_set", statement="grow signups")
    o = await build_overview(kctx, **stores)
    assert o["confirmation"] == {
        "confirmed": False,
        "confirmed_at": None,
        "label": "waiting for your yes",
    }
    assert o["needs_from_you"][0]["kind"] == "confirm"
    assert "yes" in o["needs_from_you"][0]["text"]

    await call(kctx, "mission_confirm")
    o2 = await build_overview(kctx, **stores)
    assert o2["confirmation"]["confirmed"] is True
    assert o2["confirmation"]["label"] == "confirmed"
    assert all(n["kind"] != "confirm" for n in o2["needs_from_you"])


@pytest.mark.asyncio
async def test_overview_confirmation_none_without_mission(kctx, store, sf):
    from plugin_curiosity.goals import GoalStore
    from plugin_curiosity.loops import LoopStore
    from plugin_curiosity.overview import build_overview
    from plugin_curiosity.scopes import ScopeStore
    from plugin_curiosity.telemetry import HeartbeatStore

    o = await build_overview(
        kctx, missions=store, scope_store=ScopeStore(sf), goal_store=GoalStore(sf),
        loop_store=LoopStore(sf), heartbeat_store=HeartbeatStore(sf),
    )
    assert o["confirmation"] is None


# ---- Unit 5: the kickoff split ----------------------------------------------


@pytest.mark.asyncio
async def test_mission_set_posts_brief_not_deep(kctx, store):
    r = await call(kctx, "mission_set", statement="grow signups")
    assert r["kickoff"] == "brief started"
    assert "mission_confirm" in r["reminder"]
    await _settle()
    briefs = _posts(kctx, research.BRIEF_TITLE)
    assert len(briefs) == 1
    assert briefs[0]["tools"] == research.BRIEF_TOOLS
    assert "grow signups" in briefs[0]["content"]
    assert _posts(kctx, research.KICKOFF_TITLE) == []  # deep pass held back


def test_brief_content_is_instant_and_asks_for_yes():
    text = research.BRIEF_CONTENT
    assert "What I heard" in text
    assert "First look" in text
    assert "3 things I could do" in text
    # phase12: no auto-proceed promise anywhere — the yes is the release
    assert "half a" not in text
    assert "nothing deep runs without their yes" in text


@pytest.mark.asyncio
async def test_confirm_releases_deep_pass_exactly_once(kctx, store):
    await call(kctx, "mission_set", statement="grow signups")
    await _settle()
    kctx.muted_posts.clear()

    c1 = await call(kctx, "mission_confirm")
    assert c1["deep_kickoff"] == "started"
    c2 = await call(kctx, "mission_confirm")
    assert c2["deep_kickoff"] == "already started"
    await _settle()

    deeps = _posts(kctx, research.KICKOFF_TITLE)
    assert len(deeps) == 1
    assert research.CONFIRM_NOTE_CONFIRMED.strip() in deeps[0]["content"]


@pytest.mark.asyncio
async def test_deep_pass_waits_before_timeout(kctx, store):
    await call(kctx, "mission_set", statement="grow signups")
    await _settle()
    kctx.muted_posts.clear()
    assert await research.maybe_start_deep_kickoff(kctx, store) == "waiting for confirmation"
    await _settle()
    assert _posts(kctx, research.KICKOFF_TITLE) == []


@pytest.mark.asyncio
async def test_stale_unconfirmed_mission_nudges_once_never_proceeds(kctx, store, sf):
    """phase12: the 12 h timeout-proceed is gone — silence earns ONE re-ask
    nudge and the deep pass waits for mission_confirm forever."""
    research._nudge_claims.clear()
    await call(kctx, "mission_set", statement="grow signups")
    await _settle()
    kctx.muted_posts.clear()
    await _backdate_mission(sf, 13)

    assert await research.maybe_start_deep_kickoff(kctx, store) == "nudged"
    # janitor re-runs (on-load + per-turn) converge on the single nudge
    assert await research.maybe_start_deep_kickoff(kctx, store) == "already nudged"
    await _settle()

    assert _posts(kctx, research.KICKOFF_TITLE) == []  # deep pass never fired
    nudges = _posts(kctx, research.CONFIRM_NUDGE_TITLE)
    assert len(nudges) == 1
    assert nudges[0]["tools"] == research.CONFIRM_NUDGE_TOOLS
    assert "never proceed on your own" in nudges[0]["content"]

    # the owner's yes still releases the deep pass after the nudge
    c = await call(kctx, "mission_confirm")
    assert c["deep_kickoff"] == "started"
    await _settle()
    assert len(_posts(kctx, research.KICKOFF_TITLE)) == 1


@pytest.mark.asyncio
async def test_confirm_nudge_flag_survives_process_restart(kctx, store, sf):
    research._nudge_claims.clear()
    await call(kctx, "mission_set", statement="grow signups")
    await _settle()
    kctx.muted_posts.clear()
    await _backdate_mission(sf, 13)
    assert await research.maybe_start_deep_kickoff(kctx, store) == "nudged"

    research._nudge_claims.clear()  # simulate a process restart
    assert await research.maybe_start_deep_kickoff(kctx, store) == "already nudged"
    assert len(_posts(kctx, research.CONFIRM_NUDGE_TITLE)) == 1


@pytest.mark.asyncio
async def test_db_flag_survives_process_restart(kctx, store, sf):
    await call(kctx, "mission_set", statement="grow signups")
    await call(kctx, "mission_confirm")
    await _settle()
    kctx.muted_posts.clear()

    research._deep_claims.clear()  # simulate a process restart
    assert await research.maybe_start_deep_kickoff(kctx, store) == "already started"
    await _settle()
    assert _posts(kctx, research.KICKOFF_TITLE) == []


@pytest.mark.asyncio
async def test_grandfather_guard_never_refires_past_s0(kctx, store, sf):
    """A 0.12.x mission upgraded mid-setup (past S0) already ran its single
    kickoff — the split must never fire a second deep pass at it."""
    from sqlalchemy import update

    from plugin_curiosity.models import Mission

    await call(kctx, "mission_set", statement="grow signups")
    await _settle()
    async with sf() as s:
        await s.execute(update(Mission).where(Mission.active).values(setup_stage="S1"))
        await s.commit()
    kctx.muted_posts.clear()

    assert await research.maybe_start_deep_kickoff(kctx, store) == "already past S0"
    m = await store.get()
    assert await research._deep_flag_get(sf, str(m["id"])) == "grandfathered"

    # even an explicit owner confirm cannot re-fire it
    c = await call(kctx, "mission_confirm")
    assert c["deep_kickoff"] == "already past S0"
    await _settle()
    assert _posts(kctx, research.KICKOFF_TITLE) == []


@pytest.mark.asyncio
async def test_grandfathered_mission_shows_no_confirm_gate(kctx, store, sf):
    """A pre-split mission past S0 has no confirmed_at — neither the prompt
    nor the owner pane may claim it is 'waiting for a yes'."""
    from sqlalchemy import update

    from plugin_curiosity.goals import GoalStore
    from plugin_curiosity.loops import LoopStore
    from plugin_curiosity.models import Mission
    from plugin_curiosity.overview import build_overview
    from plugin_curiosity.scopes import ScopeStore
    from plugin_curiosity.telemetry import HeartbeatStore

    await call(kctx, "mission_set", statement="grow signups")
    async with sf() as s:
        await s.execute(update(Mission).where(Mission.active).values(setup_stage="S1"))
        await s.commit()

    frag = mission_mod.prompt_fragment(await store.get())
    assert "NOT yet confirmed" not in frag

    o = await build_overview(
        kctx, missions=store, scope_store=ScopeStore(sf), goal_store=GoalStore(sf),
        loop_store=LoopStore(sf), heartbeat_store=HeartbeatStore(sf),
    )
    assert o["confirmation"] is None
    assert all(n["kind"] != "confirm" for n in o["needs_from_you"])


def test_deep_content_carries_confirm_note_and_milestones():
    text = research._KICKOFF_CONTENT
    assert "{confirm_note}" in text
    # phase14: the milestones are planned here (written into the numbered
    # plan page), committed later in the owner-approved execution pass
    assert "MILESTONES" in text
    assert "3-5" in text
    assert "goal_set" in research._PLAN_EXEC_CONTENT


@pytest.mark.asyncio
async def test_run_kickoff_formats_confirm_note(kctx):
    await research.run_kickoff(
        kctx, "grow signups", confirm_note=research.CONFIRM_NOTE_CONFIRMED
    )
    deeps = _posts(kctx, research.KICKOFF_TITLE)
    assert len(deeps) == 1
    assert research.CONFIRM_NOTE_CONFIRMED.strip() in deeps[0]["content"]
