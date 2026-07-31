"""11.004/M4 + 11.005 (0.16.0): the journey payload behind the rebuilt
Missions tab. Testable units from phase05-surface/PLAN.md:

1. payload per lifecycle — day one is EXACTLY mission + journey + now & next;
   earning adds cards and waiting; operating adds the timeline and wins.
2. no jargon — the serialized payload never carries stage codes, rung
   numbers, horizon enums, or card statuses.
3. step derivation — recorded facts map to the right step; steps are judged
   independently (confirmed-but-no-value points at Prove).
5. the dial — rung words + revoke line; a visible error drops one notch and
   returns the say-aloud sentence (never silent, never a number).

(4 — buttons on a real Luna — and 6 — screenshot vs mock — run in the dojo.)
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from plugin_curiosity.journey import (
    RUNG_WORDS,
    build_journey,
    derive_steps,
    dial_words,
    minutes_of,
    rung_drop_sentence,
)

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def mission(**over) -> dict:
    base = {
        "id": "m-1",
        "statement": "Own the weekly newsletter end to end",
        "origin_statement": "you own my newsletter now",
        "confirmed_at": None,
        "autonomy_rung": 1,
        "active": True,
        "agent_phase": "setup",
        "setup_stage": "S0",
        "created_at": "2026-07-28T09:00:00+00:00",
        "stage_entered_at": "2026-07-28T09:00:00+00:00",
        "phase_entered_at": "2026-07-28T09:00:00+00:00",
    }
    base.update(over)
    return base


def build(m, **over) -> dict:
    kw = dict(
        mission=m, goals_list=[], loops_open=[], loops_all=[],
        value_log=[], next_steps=[], intake=[], now=NOW,
    )
    kw.update(over)
    return build_journey(**kw)


# -- 1 · payload per lifecycle ------------------------------------------------


def test_no_mission_no_journey():
    assert build(None) is None


def test_day_one_is_exactly_three_sections():
    j = build(mission())
    assert j["sections"] == ["mission", "journey", "now_next"]
    assert j["waiting"] is None and j["wins"] is None and j["happens_when"] is None
    assert not j["hero"]["confirmed"]
    # nothing runs unannounced even on an empty page — the empty note says
    # what happens next instead of showing a blank
    assert "before it runs" in j["now_next"]["empty_note"]


def test_earning_adds_cards_and_waiting():
    m = mission(confirmed_at="2026-07-28T10:00:00+00:00", setup_stage="S2")
    steps = [{
        "id": "ns-1", "what": "Read the last 10 newsletters", "why": "learn the voice",
        "produces": "a voice memo you can veto", "cost_text": "about 20 min",
        "status": "proposed", "wait_until": "2026-07-30T14:00:00+00:00",
    }]
    asks = [{
        "id": "lp-1", "kind": "ask", "statement": "Read-only mailbox access",
        "unlock": "drafting from real threads", "human_cost": "2 min", "who": "owner",
        "status": "open",
    }]
    j = build(m, next_steps=steps, loops_open=asks)
    assert j["sections"] == ["mission", "journey", "now_next", "waiting"]
    q = j["now_next"]["queued"]
    assert q["id"] == "ns-1" and q["cost"] == "about 20 min"
    assert "about 2 h" in q["hint"]  # wait_until − now, said as a promise
    # the S2 plan gate gets a real Approve button carrying the mission id
    approve = [i for i in j["waiting"]["items"] if i["action"] == "approve"]
    assert len(approve) == 1 and approve[0]["object_id"] == "m-1"
    assert "2 things" in j["waiting"]["headline"]


def test_operating_adds_timeline_and_wins():
    m = mission(
        confirmed_at="2026-07-28T10:00:00+00:00", setup_stage="S5",
        agent_phase="work", autonomy_rung=3,
    )
    goals = [
        {"status": "active", "statement": "First draft in your inbox",
         "horizon_kind": "awaiting_approval", "horizon_ref": "", "target_date": None,
         "expected_result": "a full draft to veto"},
        {"status": "active", "statement": "Voice memo written",
         "horizon_kind": "agent_minutes", "horizon_ref": "45", "target_date": None,
         "expected_result": ""},
        {"status": "active", "statement": "Issue 12 ships",
         "horizon_kind": "date", "horizon_ref": "", "target_date": "2026-08-04",
         "expected_result": ""},
    ]
    wins = [{"statement": "Draft #1 delivered", "evidence": "https://x/doc",
             "delivered_at": "2026-07-29T08:00:00+00:00"}]
    j = build(m, goals_list=goals, value_log=wins)
    assert j["sections"] == ["mission", "journey", "now_next", "happens_when", "wins"]
    # unlocks-first spine (phase04 learning): your-move rows lead, dates last
    whens = [r["when"] for r in j["happens_when"]["rows"]]
    assert whens == ["After your OK", "~45 min of my work", "By 2026-08-04"]
    assert j["wins"]["items"][0]["link"] == "https://x/doc"
    # work phase: no dimmed "when you say so" row — work already began
    assert not any(r["dimmed"] for r in j["happens_when"]["rows"])


def test_setup_timeline_ends_dimmed_on_owner_choice():
    goals = [{"status": "active", "statement": "x", "horizon_kind": "on_unlock",
              "horizon_ref": "mailbox access", "target_date": None, "expected_result": ""}]
    j = build(mission(), goals_list=goals)
    rows = j["happens_when"]["rows"]
    assert rows[0]["when"] == "Once “mailbox access” lands"
    assert rows[-1]["dimmed"] and rows[-1]["when"] == "When you say so"


def test_hero_owner_words_and_intake():
    intake = [{"you": "Who reads it?", "because": "tone depends on the audience"}]
    j = build(mission(), intake=intake)
    assert j["hero"]["you_said"] == "you own my newsletter now"
    assert j["hero"]["intake"] == intake
    # restatement identical to the owner's words → no redundant quote
    same = mission(origin_statement="Own the weekly newsletter end to end")
    assert build(same)["hero"]["you_said"] == ""


def test_wins_headline_counts_honest_minutes():
    steps = [
        {"status": "done", "cost_text": "about 20 min",
         "started_at": "2026-07-29T08:00:00+00:00", "finished_at": "2026-07-29T10:00:00+00:00"},
        {"status": "done", "cost_text": "",  # no promise → clamped wall clock
         "started_at": "2026-07-29T08:00:00+00:00", "finished_at": "2026-07-29T08:30:00+00:00"},
    ]
    loops = [{"kind": "ask", "status": "answered", "human_cost": "2 min"}]
    wins = [{"statement": "w", "evidence": "did it", "delivered_at": "2026-07-29T08:00:00+00:00"}]
    j = build(mission(), value_log=wins, next_steps=steps, loops_all=loops)
    assert j["wins"]["headline"] == "1 win · ~50 minutes of my work · you spent ~2 minutes"


def test_minutes_of_parses_honest_units():
    assert minutes_of("about 20 min") == 20
    assert minutes_of("60 to 90 min") == 75
    assert minutes_of("1.5 h") == 90
    assert minutes_of("a while") is None


# -- 2 · no jargon in the serialized payload ----------------------------------

JARGON = [
    re.compile(r"\bS[0-5]\b"),          # stage codes
    re.compile(r"\brung\b", re.I),      # the dial is words, never a number
    re.compile(r"awaiting_approval|on_unlock|agent_minutes"),  # horizon enums
    re.compile(r"\bproposed\b|\bannounced\b"),  # card statuses
    re.compile(r"horizon|setup_stage|agent_phase"),  # internal field names
]


@pytest.mark.parametrize("stage", ["S0", "S1", "S2", "S3", "S4", "S5"])
def test_no_jargon_any_stage(stage):
    m = mission(
        confirmed_at="2026-07-28T10:00:00+00:00", setup_stage=stage, autonomy_rung=2,
    )
    goals = [
        {"status": "active", "statement": "g", "horizon_kind": k, "horizon_ref": r,
         "target_date": d, "expected_result": ""}
        for k, r, d in [
            ("awaiting_approval", "", None), ("on_unlock", "access", None),
            ("agent_minutes", "30", None), ("date", "", "2026-08-04"),
            ("rhythm", "weekly", None),
        ]
    ]
    steps = [{"id": "n1", "what": "w", "why": "y", "produces": "p",
              "cost_text": "5 min", "status": "proposed", "wait_until": None},
             {"id": "n2", "what": "w2", "why": "y", "produces": "p",
              "cost_text": "5 min", "status": "running",
              "started_at": "2026-07-30T11:00:00+00:00"}]
    loops = [{"id": "l1", "kind": "ask", "statement": "a", "unlock": "u",
              "human_cost": "1 min", "who": "owner", "status": "open"}]
    wins = [{"statement": "w", "evidence": "e", "delivered_at": "2026-07-29T00:00:00+00:00"}]
    blob = json.dumps(build(
        m, goals_list=goals, next_steps=steps, loops_open=loops,
        loops_all=loops, value_log=wins,
        intake=[{"you": "q", "because": "b"}],
    ))
    for rx in JARGON:
        assert not rx.search(blob), f"jargon {rx.pattern!r} leaked: {rx.search(blob).group()}"


# -- 3 · step derivation ------------------------------------------------------


def steps_of(m, first_win=None):
    steps, cur = derive_steps(m, first_win)
    return [s["state"] for s in steps], cur


def test_fresh_mission_is_at_reflect():
    states, cur = steps_of(mission())
    assert states == ["done", "now", "todo", "todo", "todo", "todo"]
    assert cur == 1


def test_confirmed_but_no_value_points_at_prove():
    # the edge from the plan: stage raced ahead to approval, but no win has
    # landed — steps are judged independently, so "now" is Prove, and the
    # Agree mark stays honestly done
    m = mission(confirmed_at="2026-07-28T10:00:00+00:00", setup_stage="S3")
    states, cur = steps_of(m)
    assert cur == 2
    assert states == ["done", "done", "now", "done", "todo", "todo"]


def test_first_win_and_approval_point_at_earn():
    m = mission(confirmed_at="2026-07-28T10:00:00+00:00", setup_stage="S4")
    states, cur = steps_of(m, first_win="2026-07-29T08:00:00+00:00")
    assert cur == 4 and states[4] == "now"


def test_work_phase_owns_the_last_step():
    m = mission(
        confirmed_at="2026-07-28T10:00:00+00:00", setup_stage="S5", agent_phase="work",
    )
    steps, cur = derive_steps(m, "2026-07-29T08:00:00+00:00")
    assert cur == 5
    assert [s["state"] for s in steps] == ["done"] * 5 + ["now"]
    # date stamps ride the done steps; Own is a standing state
    assert steps[1]["when"] == "Jul 28"


def test_journey_headline_counts_waiting_things():
    m = mission(confirmed_at="2026-07-28T10:00:00+00:00", setup_stage="S4")
    asks = [{"id": "l1", "kind": "ask", "statement": "a", "unlock": "", "human_cost": "",
             "who": "owner", "status": "open"}]
    j = build(m, loops_open=asks, value_log=[
        {"statement": "w", "evidence": "e", "delivered_at": "2026-07-29T00:00:00+00:00"}])
    assert j["journey"]["headline"] == "Earning the setup — 1 thing waiting on you"


# -- 5 · the dial (11.005) ----------------------------------------------------


def test_dial_words_by_rung_and_clamp():
    assert dial_words(1)["words"] == "I ask before anything new"
    assert dial_words(4)["words"] == "I run the job"
    assert dial_words(0)["words"] == dial_words(1)["words"]
    assert dial_words(9)["words"] == dial_words(4)["words"]
    assert "anytime" in dial_words(2)["revoke"]


def test_rung_drop_sentence_is_words_not_numbers():
    s = rung_drop_sentence(2, True)
    assert RUNG_WORDS[2][0].lower() in s and "back a notch" in s
    assert not re.search(r"\d", s)
    assert "staying there" in rung_drop_sentence(1, False)


@pytest_asyncio.fixture
async def fstore(sf, store):
    from plugin_curiosity.feedback import FeedbackStore

    await store.set("own the weekly newsletter end to end", rung=3)
    return FeedbackStore(sf)


@pytest.mark.asyncio
async def test_drop_rung_steps_down_to_the_floor(fstore, store):
    d1 = await fstore.drop_rung()
    assert d1["dropped"] and d1["dial"]["words"] == RUNG_WORDS[2][0]
    assert "back a notch" in d1["say_aloud"]
    await fstore.drop_rung()
    assert (await store.get())["autonomy_rung"] == 1
    d3 = await fstore.drop_rung()  # floor: asking-first, still said aloud
    assert not d3["dropped"]
    assert "staying there" in d3["say_aloud"]
    assert (await store.get())["autonomy_rung"] == 1


@pytest.mark.asyncio
async def test_drop_rung_without_mission_is_none(sf):
    from plugin_curiosity.feedback import FeedbackStore

    assert await FeedbackStore(sf).drop_rung() is None


@pytest.fixture
def fctx(ctx, fstore):
    from plugin_curiosity.feedback import register_tools

    register_tools(ctx, fstore)
    return ctx


async def call(ctx, tool, **kw):
    return await ctx.tool_registry.registered[tool][1](**kw)


@pytest.mark.asyncio
async def test_visible_error_feedback_drops_the_dial_out_loud(fctx, store):
    await call(fctx, "design_map")
    out = await call(
        fctx, "feedback_note", quote="you sent the wrong draft to my boss",
        diagnosis="verify recipient before send", visible_error=True,
    )
    assert out["autonomy"]["dropped"]
    assert "back a notch" in out["autonomy"]["say_aloud"]
    assert (await store.get())["autonomy_rung"] == 2


@pytest.mark.asyncio
async def test_invisible_feedback_leaves_the_dial_alone(fctx, store):
    await call(fctx, "design_map")
    out = await call(fctx, "feedback_note", quote="reports feel too long")
    assert "autonomy" not in out
    assert (await store.get())["autonomy_rung"] == 3
