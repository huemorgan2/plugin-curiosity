"""Proposal ledger (11.008/M7): prediction required at open, one-open cap
with steering hints, decide/close lifecycle, actual required at close,
convergent re-open, calibration verdicts, tool registration."""

from __future__ import annotations

import pytest
import pytest_asyncio

from plugin_curiosity import proposals as pr


@pytest_asyncio.fixture
async def pstore(sf, store):
    await store.set("own the weekly newsletter end to end")
    return pr.ProposalStore(sf)


@pytest.fixture
def pctx(ctx, pstore):
    pr.register_tools(ctx, pstore)
    return ctx


async def call(ctx, tool, **kw):
    return await ctx.tool_registry.registered[tool][1](**kw)


# ---- pure calibration math --------------------------------------------------


def test_prediction_hit_band():
    assert pr.prediction_hit(20, 25) is True    # +25% — inside ±30%
    assert pr.prediction_hit(20, 26) is True    # +30% exactly
    assert pr.prediction_hit(20, 27) is False   # +35%
    assert pr.prediction_hit(20, 14) is True    # -30% exactly
    assert pr.prediction_hit(20, 13) is False
    assert pr.prediction_hit(None, 25) is None  # prose-only prediction
    assert pr.prediction_hit(20, None) is None  # not yet measured
    assert pr.prediction_hit(0, 5) is None      # zero prediction unscoreable


# ---- open: prediction required, one-open cap --------------------------------


@pytest.mark.asyncio
async def test_open_requires_mission_title_and_prediction(sf, pstore):
    empty = pr.ProposalStore(sf)
    with pytest.raises(ValueError, match="predicted"):
        await pstore.open("faster digest", "")
    with pytest.raises(ValueError, match="title"):
        await pstore.open("", "saves 20 min/week")
    p = await pstore.open("faster digest", "saves you ~20 min/week",
                          predicted_minutes=20)
    assert p["status"] == "proposed" and p["predicted_minutes"] == 20


@pytest.mark.asyncio
async def test_one_open_cap_steers_to_the_open_one(pstore):
    await pstore.open("faster digest", "saves ~20 min/week")
    with pytest.raises(ValueError) as e:
        await pstore.open("new idea", "saves ~5 min/week")
    msg = str(e.value)
    assert "one proposal at a time" in msg
    assert "faster digest" in msg
    assert "proposal_decide" in msg and "proposal_close" in msg


@pytest.mark.asyncio
async def test_reopen_same_title_is_convergent(pstore):
    a = await pstore.open("faster digest", "saves ~20 min/week")
    b = await pstore.open("Faster Digest", "saves ~20 min/week")
    assert b["id"] == a["id"] and b["note"] == "already open"


@pytest.mark.asyncio
async def test_accepted_still_blocks_a_second_open(pstore):
    await pstore.open("faster digest", "saves ~20 min/week")
    await pstore.decide(decision="accepted")
    with pytest.raises(ValueError, match="one proposal at a time"):
        await pstore.open("new idea", "saves ~5 min/week")


# ---- decide -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_decline_is_terminal_and_frees_the_slot(pstore):
    await pstore.open("faster digest", "saves ~20 min/week")
    d = await pstore.decide(decision="declined", note="not this month")
    assert d["status"] == "declined" and d["closed_at"]
    with pytest.raises(ValueError, match="final"):
        await pstore.decide(proposal_id=d["id"], decision="accepted")
    nxt = await pstore.open("new idea", "saves ~5 min/week")
    assert nxt["status"] == "proposed"


@pytest.mark.asyncio
async def test_accept_steers_toward_actual(pstore):
    await pstore.open("faster digest", "saves ~20 min/week")
    d = await pstore.decide(decision="accepted", note="go")
    assert d["status"] == "accepted"
    assert "actual" in d["next"]


# ---- close ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_requires_actual_and_a_decision(pstore):
    p = await pstore.open("faster digest", "saves ~20 min/week",
                          predicted_minutes=20)
    with pytest.raises(ValueError, match="actual"):
        await pstore.close(outcome="done")
    # an undecided proposal can't be 'done' — the owner never said yes
    with pytest.raises(ValueError, match="no decision yet"):
        await pstore.close(outcome="done", actual="saved 25")
    await pstore.decide(decision="accepted")
    c = await pstore.close(outcome="done", actual="saved ~25 min/week",
                           actual_minutes=25)
    assert c["status"] == "done"
    assert c["prediction_hit"] is True
    assert c["closed_at"]
    # closed = slot free
    assert (await pstore.open("next bet", "saves ~5 min/week"))["status"] == "proposed"
    _ = p


@pytest.mark.asyncio
async def test_dropped_needs_no_decision_but_still_needs_actual(pstore):
    await pstore.open("faster digest", "saves ~20 min/week")
    c = await pstore.close(outcome="dropped",
                           actual="turned out the digest is already fast")
    assert c["status"] == "dropped"


# ---- list -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_surfaces_open_and_last_closed_with_verdict(pstore):
    await pstore.open("bet one", "saves ~20 min/week", predicted_minutes=20)
    await pstore.decide(decision="accepted")
    await pstore.close(outcome="done", actual="saved ~40 min/week",
                       actual_minutes=40)
    await pstore.open("bet two", "saves ~10 min/week")
    out = await pstore.list()
    assert out["open"]["title"] == "bet two"
    assert out["last_closed"]["title"] == "bet one"
    assert out["last_closed"]["prediction_hit"] is False  # 40 vs 20 — a miss
    assert len(out["proposals"]) == 2


# ---- tool layer -------------------------------------------------------------


@pytest.mark.asyncio
async def test_tools_registered_and_errors_are_returned_not_raised(pctx):
    for name in ("proposal_open", "proposal_decide", "proposal_close",
                 "proposal_list"):
        assert name in pctx.tool_registry.registered, name
    p = await call(pctx, "proposal_open", title="faster digest",
                   predicted="saves ~20 min/week", predicted_minutes=20)
    assert p["status"] == "proposed"
    second = await call(pctx, "proposal_open", title="other",
                        predicted="saves ~1 min/week")
    assert "one proposal at a time" in second["error"]
    d = await call(pctx, "proposal_decide", decision="accepted")
    assert d["status"] == "accepted"
    c = await call(pctx, "proposal_close", actual="saved ~22 min/week",
                   actual_minutes=22)
    assert c["status"] == "done" and c["prediction_hit"] is True
    lst = await call(pctx, "proposal_list")
    assert lst["open"] is None and lst["last_closed"]["status"] == "done"


@pytest.mark.asyncio
async def test_tool_writes_emit_ui_events(pctx):
    await call(pctx, "proposal_open", title="bet",
               predicted="saves ~20 min/week")
    assert any(p.get("payload", {}).get("what") == "proposal"
               for _, p in pctx.events.emitted)
