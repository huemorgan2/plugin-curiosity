"""Next-step cards (11.002/M2): lifecycle, rung mapping, veto window with
quiet-hours pause, timeout-to-proceed, redirect contract, scheduled step-0
wiring, and the overview/pane surfaces."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import update

from plugin_curiosity import next_steps as ns
from plugin_curiosity.models import NextStep


@pytest_asyncio.fixture
async def nstore(sf, store):
    await store.set("own the weekly newsletter end to end")  # rung 1
    return ns.NextStepStore(sf)


@pytest.fixture
def nctx(ctx, nstore):
    ns.register_tools(ctx, nstore)
    return ctx


async def call(ctx, tool, **kw):
    return await ctx.tool_registry.registered[tool][1](**kw)


async def _expire_window(sf, step_id: str) -> None:
    """Backdate a proposed card's veto deadline into the past."""
    import uuid as _uuid

    async with sf() as s:
        await s.execute(
            update(NextStep)
            .where(NextStep.id == _uuid.UUID(step_id))
            .values(wait_until=datetime.now(UTC) - timedelta(minutes=1))
        )
        await s.commit()


# ---- rung mapping + the veto-deadline pure function -------------------------


def test_card_mode_rung_mapping():
    assert ns.card_mode(1) == "proposed"
    assert ns.card_mode(2) == "proposed"
    assert ns.card_mode(3) == "announced"
    assert ns.card_mode(4) == "announced"


def test_veto_deadline_plain_daytime():
    t = datetime(2026, 7, 30, 14, 0, tzinfo=UTC)
    assert ns.veto_deadline(t) == t + timedelta(hours=2)


def test_veto_deadline_pauses_through_quiet_hours():
    # 20:30 → 30 min run before 21:00, the rest after 08:00 → 09:30 next day
    t = datetime(2026, 7, 30, 20, 30, tzinfo=UTC)
    assert ns.veto_deadline(t) == datetime(2026, 7, 31, 9, 30, tzinfo=UTC)


def test_veto_deadline_posted_inside_quiet_hours():
    # 02:00 is asleep — the clock starts at 08:00 → 10:00 same day
    t = datetime(2026, 7, 30, 2, 0, tzinfo=UTC)
    assert ns.veto_deadline(t) == datetime(2026, 7, 30, 10, 0, tzinfo=UTC)


# ---- lifecycle --------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_requires_mission_and_what(sf):
    empty = ns.NextStepStore(sf)
    with pytest.raises(ValueError, match="no active mission"):
        await empty.post("do a thing")


@pytest.mark.asyncio
async def test_rung1_posts_proposed_with_wait_until(nstore):
    card = await nstore.post("research competitors", why="gap", produces="a page")
    assert card["status"] == "proposed"
    assert card["wait_until"] is not None
    assert card["source"] == "agent"


@pytest.mark.asyncio
async def test_rung3_posts_announced_no_wait(sf, store):
    await store.set("run the ad budget", rung=3)
    s3 = ns.NextStepStore(sf)
    card = await s3.post("rebalance campaigns")
    assert card["status"] == "announced"
    assert card["wait_until"] is None
    started = await s3.start(card["id"])
    assert started["status"] == "running" and "note" not in started


@pytest.mark.asyncio
async def test_scheduled_posts_announced_even_at_rung1(nstore):
    card = await nstore.post("daily pass", scheduled=True, source="daily")
    assert card["status"] == "announced"
    assert card["wait_until"] is None


@pytest.mark.asyncio
async def test_retro_card_lands_done(nstore):
    card = await nstore.post("nightly consolidation", retro=True, source="dream")
    assert card["status"] == "done"
    assert card["finished_at"] is not None


@pytest.mark.asyncio
async def test_start_refuses_inside_veto_window(nstore):
    card = await nstore.post("cold-email 20 prospects")
    with pytest.raises(ValueError, match="veto window open until"):
        await nstore.start(card["id"])


@pytest.mark.asyncio
async def test_owner_ok_bypasses_window(nstore):
    card = await nstore.post("cold-email 20 prospects")
    started = await nstore.start(card["id"], owner_ok=True)
    assert started["status"] == "running"
    assert "note" not in started  # an explicit yes is not a timeout


@pytest.mark.asyncio
async def test_timeout_to_proceed_carries_no_guilt_note(sf, nstore):
    card = await nstore.post("draft the outreach sequence")
    await _expire_window(sf, card["id"])
    started = await nstore.start(card["id"])
    assert started["status"] == "running"
    assert "no reply" in started["note"] and "no guilt" in started["note"]


@pytest.mark.asyncio
async def test_done_links_value_receipt(sf, nstore):
    from plugin_curiosity.loops import LoopStore

    card = await nstore.post("daily pass", scheduled=True)
    await nstore.start(card["id"])
    v = await LoopStore(sf).value_add("shipped the digest", "value-log")
    closed = await nstore.done(card["id"], value_ref=v["id"])
    assert closed["status"] == "done"
    assert closed["value_ref"] == v["id"]
    with pytest.raises(ValueError, match="already done"):
        await nstore.start(card["id"])


@pytest.mark.asyncio
async def test_done_rejects_foreign_value_ref(nstore):
    card = await nstore.post("daily pass", scheduled=True)
    with pytest.raises(ValueError, match="no value-log entry"):
        await nstore.done(card["id"], value_ref="00000000-0000-0000-0000-000000000000")


@pytest.mark.asyncio
async def test_redirect_requires_plan_change_note(nstore):
    card = await nstore.post("build a scraper")
    with pytest.raises(ValueError, match="plan_change_note"):
        await nstore.done(card["id"], outcome="redirected")
    closed = await nstore.done(
        card["id"], outcome="redirected",
        plan_change_note="owner wants manual checks first — scraper shelved",
    )
    assert closed["status"] == "redirected"
    assert "scraper shelved" in closed["plan_change_note"]


@pytest.mark.asyncio
async def test_omitted_step_id_resolves_newest_open(nstore):
    await nstore.post("older card", scheduled=True)
    newer = await nstore.post("newer card", scheduled=True)
    started = await nstore.start()  # no id
    assert started["id"] == newer["id"]
    # 0.25.0 (074/phase4): done() with no id and >1 open card is now an
    # ambiguity ERROR (it used to silently close the newest — routinely a
    # different fire's card). Explicit id closes the right one.
    with pytest.raises(ValueError, match="pass step_id"):
        await nstore.done()
    closed = await nstore.done(newer["id"])
    assert closed["id"] == newer["id"]


@pytest.mark.asyncio
async def test_no_open_card_is_a_steering_error(nstore):
    with pytest.raises(ValueError, match="no open next-step card"):
        await nstore.start()


@pytest.mark.asyncio
async def test_current_returns_newest_open_only(nstore):
    assert await nstore.current() is None
    a = await nstore.post("card a", scheduled=True)
    await nstore.start(a["id"])
    cur = await nstore.current()
    assert cur["id"] == a["id"] and cur["status"] == "running"
    await nstore.done(a["id"])
    assert await nstore.current() is None


# ---- tools ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tools_auto_approve_ungated_and_steering_errors(nctx):
    for name in ("next_step_post", "next_step_start", "next_step_done"):
        tool_def, _ = nctx.tool_registry.registered[name]
        assert tool_def.policy == "auto_approve"
        assert name not in nctx.tool_registry.gated  # muted turns must reach these
    r = await call(nctx, "next_step_post", what="")
    assert "error" in r
    await call(nctx, "next_step_post", what="a real card", scheduled=True)
    r = await call(nctx, "next_step_done", outcome="redirected")
    assert "plan_change_note" in r["error"]


@pytest.mark.asyncio
async def test_post_handler_steers_by_status(nctx):
    proposed = await call(nctx, "next_step_post", what="novel outreach")
    assert "owner can redirect until" in proposed["next"]
    r = await call(nctx, "next_step_start", step_id=proposed["id"])
    assert "veto window open" in r["error"]
    announced = await call(nctx, "next_step_post", what="daily pass", scheduled=True)
    assert "begin now" in announced["next"]


# ---- scheduled runs post a card as step 0 -----------------------------------


def test_daily_target_opens_with_card_before_loop_patrol():
    from plugin_curiosity.research import DAILY_ROUTINE_SECTION as t

    assert "next_step_post" in t and "scheduled=true" in t
    assert t.index("CARD FIRST") < t.index("0. LOOP PATROL")
    assert "next_step_done" in t


def test_weekly_review_and_heartbeat_carry_the_card_step():
    from plugin_curiosity.prompts import HEARTBEAT_CONTRACT
    from plugin_curiosity.review import WEEKLY_REVIEW_TARGET

    assert "next_step_post" in WEEKLY_REVIEW_TARGET
    assert "scheduled=true" in WEEKLY_REVIEW_TARGET
    assert "(a0)" in HEARTBEAT_CONTRACT and "next_step_post" in HEARTBEAT_CONTRACT


def test_dream_is_exempt_but_posts_retro_receipt():
    from plugin_curiosity.dream import DREAM_TARGET as t

    assert "retro=true" in t
    assert "scheduled=true" not in t  # no before-card — the owner sleeps


def test_kickoff_turn_can_close_its_card():
    from plugin_curiosity.research import _KICKOFF_CONTENT, KICKOFF_TOOLS

    assert "next_step_done" in KICKOFF_TOOLS
    assert "next_step_done" in _KICKOFF_CONTENT


def test_prompt_fragment_teaches_the_card_rule():
    from plugin_curiosity.mission import prompt_fragment

    mission = {
        "id": "x", "statement": "s", "autonomy_rung": 1, "risk_ceiling": "low",
        "confirmed_at": "2026-01-01", "setup_stage": "S1", "agent_phase": "setup",
    }
    for phase in ("setup", "work"):
        frag = prompt_fragment(mission, phase)
        assert "NEXT-STEP CARD" in frag and "next_step_post" in frag


@pytest.mark.asyncio
async def test_deep_kickoff_records_its_card_plugin_side(sf, store, ctx):
    from plugin_curiosity import research

    await store.set("own the newsletter")
    m = await store.get()
    ctx.db_session_factory = sf
    r = await research.spawn_deep_kickoff_once(ctx, sf, m)
    assert r == "started"
    cards = await ns.NextStepStore(sf).list()
    assert len(cards) == 1
    card = cards[0]
    assert card["source"] == "kickoff"
    assert card["status"] == "running"  # announced+started in one write
    assert "Planning pass" in card["what"]  # phase14: the deep pass plans, never scaffolds


# ---- overview surfaces ------------------------------------------------------


@pytest.mark.asyncio
async def test_overview_shows_card_and_veto_cta(nctx, nstore, store, sf):
    from plugin_curiosity.goals import GoalStore
    from plugin_curiosity.loops import LoopStore
    from plugin_curiosity.overview import build_overview
    from plugin_curiosity.scopes import ScopeStore
    from plugin_curiosity.telemetry import HeartbeatStore

    nctx.db_session_factory = sf
    stores = dict(
        missions=store, scope_store=ScopeStore(sf), goal_store=GoalStore(sf),
        loop_store=LoopStore(sf), heartbeat_store=HeartbeatStore(sf),
        next_step_store=nstore,
    )
    card = await nstore.post("email 20 prospects", produces="warm leads")
    o = await build_overview(nctx, **stores)
    assert o["next_step"]["id"] == card["id"]
    veto = [n for n in o["needs_from_you"] if n["kind"] == "next_step"]
    assert len(veto) == 1 and "redirect" in veto[0]["text"]
    assert any(a["kind"] == "next_step" for a in o["activity"])

    # window expired → the CTA leaves the needs list; the card stays visible
    await _expire_window(sf, card["id"])
    o2 = await build_overview(nctx, **stores)
    assert all(n["kind"] != "next_step" for n in o2["needs_from_you"])
    assert o2["next_step"]["id"] == card["id"]


@pytest.mark.asyncio
async def test_overview_without_store_keeps_shape(nctx, store, sf):
    from plugin_curiosity.goals import GoalStore
    from plugin_curiosity.loops import LoopStore
    from plugin_curiosity.overview import build_overview
    from plugin_curiosity.scopes import ScopeStore
    from plugin_curiosity.telemetry import HeartbeatStore

    o = await build_overview(
        nctx, missions=store, scope_store=ScopeStore(sf), goal_store=GoalStore(sf),
        loop_store=LoopStore(sf), heartbeat_store=HeartbeatStore(sf),
    )
    assert o["next_step"] is None and o["next_steps_recent"] == []


@pytest.mark.asyncio
async def test_mission_detail_includes_next_steps(nstore, store, sf):
    from plugin_curiosity.overview import mission_detail

    await nstore.post("daily pass", scheduled=True)
    m = await store.get()
    detail = await mission_detail(sf, m["id"])
    assert len(detail["next_steps"]) == 1
    assert detail["next_steps"][0]["what"] == "daily pass"


# ---- 0.25.0 (luna 074/phase4): veto-lapse sweeper + done affinity ----------


@pytest.mark.asyncio
async def test_sweep_lapsed_autostarts_proposed_card(nstore, sf):
    card = await nstore.post(what="draft the newsletter outline")  # rung1 → proposed
    assert card["status"] == "proposed"
    await _expire_window(sf, card["id"])
    started = await nstore.sweep_lapsed()
    assert [c["id"] for c in started] == [card["id"]]
    cur = await nstore.current()
    assert cur["id"] == card["id"] and cur["status"] == "running"
    assert cur["started_at"] is not None


@pytest.mark.asyncio
async def test_sweep_leaves_open_windows_alone(nstore):
    card = await nstore.post(what="another step")
    assert card["status"] == "proposed"
    assert await nstore.sweep_lapsed() == []
    cur = await nstore.current()
    assert cur["status"] == "proposed"


@pytest.mark.asyncio
async def test_sweep_ignores_announced_and_running(nstore):
    await nstore.post(what="scheduled thing", scheduled=True)  # announced
    assert await nstore.sweep_lapsed() == []


@pytest.mark.asyncio
async def test_done_without_id_errors_when_multiple_cards_open(nstore):
    a = await nstore.post(what="task A", scheduled=True)
    b = await nstore.post(what="task B", scheduled=True)
    with pytest.raises(ValueError, match="pass step_id"):
        await nstore.done()
    # explicit id still closes the RIGHT card
    out = await nstore.done(a["id"])
    assert out["id"] == a["id"] and out["status"] == "done"
    # only B open now — the ergonomic no-id close works again
    out2 = await nstore.done()
    assert out2["id"] == b["id"]
