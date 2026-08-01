"""0.18.0 (11.007) — boundaries, curiosity side: the default rule set is
proposed when the owner approves the job description (S3 "Agree"), the "My
rules" strip quotes confirmed sentences verbatim with server-counted honesty,
and the incident protocol rides both phase prompts."""

from __future__ import annotations

import types

import pytest
import pytest_asyncio

from plugin_curiosity.scopes import BOUNDARY_SEEDS, BOUNDARY_SEEDS_FLAG


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


def _fake_goalseek(ctx, error=None):
    """Register a fake goal-seek policy_propose on the shared registry."""
    calls = []

    async def _propose(**kw):
        calls.append(kw)
        if error:
            return {"error": error}
        return {"boundary": {"id": f"b{len(calls)}", "status": "proposed"}}

    ctx.tool_registry.register(
        "plugin-goalseek", types.SimpleNamespace(name="policy_propose"), _propose)
    return calls


async def _flag(sf):
    from plugin_curiosity.models import Flag

    async with sf() as s:
        row = await s.get(Flag, BOUNDARY_SEEDS_FLAG)
        return row.value if row is not None else None


# ---- seed at Agree ----------------------------------------------------------


@pytest.mark.asyncio
async def test_seeds_proposed_at_s3_once(sctx, sf):
    calls = _fake_goalseek(sctx)
    out = await call(sctx, "stage_set", stage="S3")
    assert "3 default rules proposed" in out["boundary_seeds"]
    assert len(calls) == 3
    assert {c["title"] for c in calls} == {
        "Quiet hours", "Phone needs your OK", "Spending cap"}
    assert all(c["origin"] == "set at agree" for c in calls)
    # every seed names the goal-seek test that pins its behavior
    assert all(c["test_ref"].startswith("tests/test_boundaries.py::")
               for c in calls)
    assert await _flag(sf) == "1"
    # once: the next stage move files nothing new
    out = await call(sctx, "stage_set", stage="S4")
    assert "already proposed" in out["boundary_seeds"]
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_no_seeds_before_agree(sctx, sf):
    calls = _fake_goalseek(sctx)
    for stage in ("S1", "S2"):
        out = await call(sctx, "stage_set", stage=stage)
        assert "boundary_seeds" not in out
    assert calls == [] and await _flag(sf) is None


@pytest.mark.asyncio
async def test_goalseek_absent_degrades_and_retries(sctx, sf):
    out = await call(sctx, "stage_set", stage="S3")
    assert "not installed" in out["boundary_seeds"]
    assert await _flag(sf) is None  # NOT flagged — a later install still seeds
    calls = _fake_goalseek(sctx)
    out = await call(sctx, "stage_set", stage="S4")
    assert "3 default rules proposed" in out["boundary_seeds"]
    assert len(calls) == 3 and await _flag(sf) == "1"


@pytest.mark.asyncio
async def test_seed_refusal_reported_not_flagged(sctx, sf):
    _fake_goalseek(sctx, error="rule.action_class must be one of ...")
    out = await call(sctx, "stage_set", stage="S3")
    assert "refused" in out["boundary_seeds"]
    assert await _flag(sf) is None


def test_seed_sentences_are_owner_words():
    for seed in BOUNDARY_SEEDS:
        assert seed["plain_text"].rstrip().endswith(".")
        for jargon in ("tz_source", "action_class", "outbound_contact", "enum"):
            assert jargon not in seed["plain_text"]


# ---- the "My rules" strip ---------------------------------------------------


def _fake_policy_list(ctx, boundaries):
    async def _list(**kw):
        want = kw.get("status")
        return {"boundaries": [b for b in boundaries
                               if not want or b["status"] == want]}

    ctx.tool_registry.register(
        "plugin-goalseek", types.SimpleNamespace(name="policy_list"), _list)


ACTIVE = [
    {"plain_text": "I never contact your customers outside 9:00-19:00 their local time, on any channel. If I can't tell their timezone, I don't contact them.",
     "status": "active", "checks_count": 210, "denies_count": 2,
     "confirmed_at": "2026-07-30T09:00:00+00:00", "created_at": "2026-07-29T20:00:00+00:00"},
    {"plain_text": "Phone calls always need your approval first — every call, every time.",
     "status": "active", "checks_count": 2, "denies_count": 1,
     "confirmed_at": "2026-07-31T09:00:00+00:00", "created_at": "2026-07-29T20:00:00+00:00"},
]


@pytest.mark.asyncio
async def test_rules_block_quotes_verbatim_with_honest_counts(ctx):
    from plugin_curiosity.overview import _rules

    _fake_policy_list(ctx, ACTIVE + [
        {"plain_text": "proposed thing", "status": "proposed",
         "checks_count": 0, "denies_count": 0, "created_at": "2026-08-01"}])
    block = await _rules(ctx)
    assert block["items"] == [b["plain_text"] for b in ACTIVE]  # verbatim, active only
    assert block["count_line"] == "since 2026-07-30, 212 actions checked, 3 exceptions"


@pytest.mark.asyncio
async def test_rules_block_hidden_when_absent_or_empty(ctx):
    from plugin_curiosity.overview import _rules

    assert await _rules(ctx) is None  # goal-seek not installed
    _fake_policy_list(ctx, [])
    assert await _rules(ctx) is None  # nothing active yet


@pytest.mark.asyncio
async def test_rules_block_fresh_rules_say_so(ctx):
    from plugin_curiosity.overview import _rules

    fresh = [dict(ACTIVE[0], checks_count=0, denies_count=0)]
    _fake_policy_list(ctx, fresh)
    block = await _rules(ctx)
    assert "no actions checked yet" in block["count_line"]
    assert "since 2026-07-30" in block["count_line"]


@pytest.mark.asyncio
async def test_rules_block_survives_a_broken_handler(ctx):
    from plugin_curiosity.overview import _rules

    async def _boom(**kw):
        raise RuntimeError("db gone")

    ctx.tool_registry.register(
        "plugin-goalseek", types.SimpleNamespace(name="policy_list"), _boom)
    assert await _rules(ctx) is None


def test_journey_rules_section_appears_only_with_rules():
    from plugin_curiosity.journey import build_journey

    kw = dict(mission={"statement": "grow", "active": True, "confirmed": True},
              goals_list=[], loops_open=[], loops_all=[], value_log=[],
              next_steps=[], intake=[])
    without = build_journey(**kw)
    assert "rules" not in (without.get("sections") or [])
    rules = {"items": ["I never call at night."], "count_line": "since 2026-07-30, 4 actions checked, 0 exceptions"}
    with_rules = build_journey(**kw, rules=rules)
    assert with_rules["rules"] == rules
    assert "rules" in with_rules["sections"]


# ---- incident protocol prompt -----------------------------------------------


def test_incident_protocol_order_and_content():
    from plugin_curiosity.prompts import INCIDENT_PROTOCOL as P

    # the order IS the contract: stop → self-report → owner-approved recovery
    # → postmortem → rule diff + test → announced freeze → earn back → no mix
    idx = [P.index(k) for k in (
        "STOP FIRST", "SELF-REPORT BEFORE DISCOVERY", "owner's approval",
        "blameless postmortem", "RULE DIFF PLUS A TEST", "exit criteria",
        "small slices", "recovery and ambition")]
    assert idx == sorted(idx)
    assert "policy_propose" in P  # the fix is a proposed boundary
    assert "not a fix" in P and "advice is invalid" in P
    assert "proposes no new work" in P


def test_incident_protocol_rides_both_phases_once():
    from plugin_curiosity.mission import prompt_fragment
    from plugin_curiosity.prompts import INCIDENT_PROTOCOL

    m = {"statement": "grow signups", "autonomy_rung": 2, "risk_ceiling": "low"}
    assert prompt_fragment(m, "setup").count(INCIDENT_PROTOCOL) == 1
    assert prompt_fragment(m, "work").count(INCIDENT_PROTOCOL) == 1
    assert INCIDENT_PROTOCOL not in prompt_fragment(None)
