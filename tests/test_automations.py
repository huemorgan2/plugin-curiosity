"""The automation loop (11.006/M5): build → sample sign-off → hypercare →
run. State machine legality + the go-live gate, sign-off before any
autonomous run (waiver recorded distinctly), hypercare promotion math with
correction resets and the announce payload, adoption alarm + retire path,
and the owner-facing catalog words."""

from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import update

from plugin_curiosity import automations as am
from plugin_curiosity import journey
from plugin_curiosity.models import Automation


@pytest_asyncio.fixture
async def astore(sf, store):
    await store.set("own the weekly newsletter end to end")
    return am.AutomationStore(sf)


@pytest.fixture
def actx(ctx, astore):
    am.register_tools(ctx, astore)
    return ctx


async def call(ctx, tool, **kw):
    return await ctx.tool_registry.registered[tool][1](**kw)


FULL = dict(
    scope="the Friday newsletter only",
    target="draft ready by Thursday 18:00 every week",
    kill_switch="say 'stop the newsletter automation' and it stops",
    failure_detect="no draft by Thursday noon posts a loud failure note",
)


async def _make(astore, **over):
    kw = {**FULL, **over}
    return await astore.register("draft the Friday newsletter", **kw)


async def _to_hypercare(astore):
    a = await _make(astore)
    await astore.signoff_request(a["id"], samples="in: 3 real drafts → out: …")
    return await astore.signoff(a["id"])


async def _backdate_hypercare(sf, automation_id: str, days: int = 8) -> None:
    async with sf() as s:
        await s.execute(
            update(Automation)
            .where(Automation.id == _uuid.UUID(automation_id))
            .values(hypercare_since=datetime.now(UTC) - timedelta(days=days))
        )
        await s.commit()


# ---- registration + the go-live gate ---------------------------------------


@pytest.mark.asyncio
async def test_register_requires_mission_and_what(sf):
    empty = am.AutomationStore(sf)
    with pytest.raises(ValueError, match="no active mission"):
        await empty.register("run reports")


@pytest.mark.asyncio
async def test_register_requires_what(astore):
    with pytest.raises(ValueError, match="what"):
        await astore.register("   ")


@pytest.mark.asyncio
async def test_register_starts_in_building(astore):
    a = await _make(astore)
    assert a["state"] == "building"
    assert a["state_label"] == "being built"


@pytest.mark.asyncio
@pytest.mark.parametrize("gap", ["kill_switch", "target", "failure_detect"])
async def test_golive_gate_blocks_each_missing_field(astore, gap):
    a = await _make(astore, **{gap: ""})
    with pytest.raises(ValueError, match="go-live gate"):
        await astore.signoff_request(a["id"], samples="in → out")
    # and it stayed in building
    assert (await astore.list())[0]["state"] == "building"


@pytest.mark.asyncio
async def test_signoff_request_requires_samples(astore):
    a = await _make(astore)
    with pytest.raises(ValueError, match="samples"):
        await astore.signoff_request(a["id"], samples="  ")


@pytest.mark.asyncio
async def test_signoff_request_moves_to_awaiting(astore):
    a = await _make(astore)
    d = await astore.signoff_request(a["id"], samples="in: x → out: y")
    assert d["state"] == "awaiting_your_signoff"
    assert "Do NOT run this automation autonomously" in d["next"]


# ---- sign-off: no autonomous run before it, waiver recorded distinctly -----


@pytest.mark.asyncio
async def test_no_run_report_before_signoff(astore):
    a = await _make(astore)
    with pytest.raises(ValueError, match="run reports apply to"):
        await astore.run_report(a["id"], ok=True)
    await astore.signoff_request(a["id"], samples="in → out")
    with pytest.raises(ValueError, match="run reports apply to"):
        await astore.run_report(a["id"], ok=True)


@pytest.mark.asyncio
async def test_signoff_only_from_awaiting(astore):
    a = await _make(astore)
    with pytest.raises(ValueError, match="awaiting_your_signoff"):
        await astore.signoff(a["id"])


@pytest.mark.asyncio
async def test_signoff_approved_enters_hypercare(astore):
    a = await _to_hypercare(astore)
    assert a["state"] == "hypercare"
    assert a["signoff_kind"] == "approved"
    assert a["signoff_at"] is not None
    assert a["clean_runs"] == 0


@pytest.mark.asyncio
async def test_waiver_requires_note_and_is_recorded_distinctly(astore):
    a = await _make(astore)
    await astore.signoff_request(a["id"], samples="in → out")
    with pytest.raises(ValueError, match="waiver"):
        await astore.signoff(a["id"], waived=True)
    d = await astore.signoff(a["id"], waived=True, note="just run it — owner")
    assert d["signoff_kind"] == "waived"
    assert d["signoff_note"] == "just run it — owner"
    assert d["state"] == "hypercare"


# ---- hypercare math: streak, correction reset, promotion + announce --------


@pytest.mark.asyncio
async def test_clean_runs_count_but_no_promotion_inside_week(astore):
    a = await _to_hypercare(astore)
    for _ in range(am.CLEAN_RUNS_N + 2):
        d = await astore.run_report(a["id"], ok=True)
    assert d["state"] == "hypercare"  # streak done, week not elapsed
    assert d["clean_runs"] == am.CLEAN_RUNS_N + 2
    assert "announce" not in d


@pytest.mark.asyncio
async def test_correction_resets_streak_and_requires_note(astore):
    a = await _to_hypercare(astore)
    for _ in range(3):
        await astore.run_report(a["id"], ok=True)
    with pytest.raises(ValueError, match="correction_note"):
        await astore.run_report(a["id"], ok=False)
    d = await astore.run_report(a["id"], ok=False, correction_note="typo in intro")
    assert d["clean_runs"] == 0
    assert d["corrections"] == 1
    assert d["state"] == "hypercare"


@pytest.mark.asyncio
async def test_promotion_needs_streak_and_full_week(astore, sf):
    a = await _to_hypercare(astore)
    await _backdate_hypercare(sf, a["id"])
    for _ in range(am.CLEAN_RUNS_N - 1):
        d = await astore.run_report(a["id"], ok=True)
        assert d["state"] == "hypercare"
    d = await astore.run_report(a["id"], ok=True)
    assert d["state"] == "running"
    assert d["promoted"] is True
    # announced with the numbers, never silent
    assert str(am.CLEAN_RUNS_N) in d["announce"]
    assert "0 corrections" in d["announce"]
    assert FULL["kill_switch"] in d["announce"]


@pytest.mark.asyncio
async def test_promotion_due_is_pure_and_exact(astore, sf):
    a = await _to_hypercare(astore)
    now = datetime.now(UTC)
    async with sf() as s:
        row = await s.get(Automation, _uuid.UUID(a["id"]))
        row.clean_runs = am.CLEAN_RUNS_N
        row.hypercare_since = now - timedelta(days=am.HYPERCARE_MIN_DAYS - 1)
        assert am.promotion_due(row, now) is False
        row.hypercare_since = now - timedelta(days=am.HYPERCARE_MIN_DAYS)
        assert am.promotion_due(row, now) is True
        row.clean_runs = am.CLEAN_RUNS_N - 1
        assert am.promotion_due(row, now) is False


@pytest.mark.asyncio
async def test_running_correction_drops_back_to_hypercare(astore, sf):
    a = await _to_hypercare(astore)
    await _backdate_hypercare(sf, a["id"])
    for _ in range(am.CLEAN_RUNS_N):
        d = await astore.run_report(a["id"], ok=True)
    assert d["state"] == "running"
    d = await astore.run_report(a["id"], ok=False, correction_note="sent to wrong list")
    assert d["state"] == "hypercare"
    assert d["clean_runs"] == 0
    assert "extra watch" in d["next"]


# ---- pause / resume / retire ------------------------------------------------


@pytest.mark.asyncio
async def test_pause_works_from_any_live_state_and_resume_reenters_hypercare(
    astore,
):
    a = await _to_hypercare(astore)
    for _ in range(3):
        await astore.run_report(a["id"], ok=True)
    d = await astore.pause(a["id"], note="owner said stop")
    assert d["state"] == "paused"
    with pytest.raises(ValueError, match="already paused"):
        await astore.pause(a["id"])
    d = await astore.resume(a["id"])
    assert d["state"] == "hypercare"  # never straight back to running
    assert d["clean_runs"] == 0


@pytest.mark.asyncio
async def test_resume_before_any_signoff_goes_back_to_building(astore):
    a = await _make(astore)
    await astore.pause(a["id"])
    d = await astore.resume(a["id"])
    assert d["state"] == "building"


@pytest.mark.asyncio
async def test_retire_needs_owner_ok_and_note(astore):
    a = await _to_hypercare(astore)
    with pytest.raises(ValueError, match="owner"):
        await astore.retire(a["id"])
    with pytest.raises(ValueError, match="note"):
        await astore.retire(a["id"], owner_ok=True)
    d = await astore.retire(a["id"], owner_ok=True, note="yes, drop it")
    assert d["state"] == "retired"
    # retired is terminal
    with pytest.raises(ValueError, match="already retired"):
        await astore.retire(a["id"], owner_ok=True, note="again")
    with pytest.raises(ValueError, match="retired"):
        await astore.pause(a["id"])


# ---- adoption telemetry + alarm ---------------------------------------------


@pytest.mark.asyncio
async def test_adoption_alarm_fires_at_threshold(astore):
    a = await _to_hypercare(astore)
    for i in range(am.ADOPTION_ALARM_N - 1):
        d = await astore.adoption_event(a["id"], kind="override")
        assert "alarm" not in d
    d = await astore.adoption_event(a["id"], kind="ignore")
    assert "alarm" in d
    assert "propose retiring" in d["alarm"]
    assert d["overrides"] == am.ADOPTION_ALARM_N - 1
    assert d["ignores"] == 1


@pytest.mark.asyncio
async def test_adoption_kind_validated(astore):
    a = await _to_hypercare(astore)
    with pytest.raises(ValueError, match="override"):
        await astore.adoption_event(a["id"], kind="disliked")


# ---- catalog: plain state words, retired hidden -----------------------------


def test_state_words_cover_every_state_with_plain_words():
    for state in am.STATES:
        css, label = am.STATE_WORDS[state]
        assert css in ("run", "watch", "ask")  # the pane's only pill classes
        # lifecycle enums never leak into the owner's words
        assert "hypercare" not in label
        assert "signoff" not in label
        assert "_" not in label


@pytest.mark.asyncio
async def test_services_block_plain_words_and_retired_hidden(astore):
    a = await _to_hypercare(astore)
    b = await astore.register("watch competitor pricing", **FULL)
    await astore.retire(b["id"], owner_ok=True, note="owner said drop it")
    block = am.services_block(await astore.list(include_retired=True))
    assert [i["name"] for i in block["items"]] == ["draft the Friday newsletter"]
    item = block["items"][0]
    assert item["state"] == "watch"
    assert item["state_label"] == "extra watch"
    assert item["sub"] == FULL["target"]
    assert "1 automation" in block["headline"]


def test_services_block_hidden_when_empty():
    assert am.services_block([]) is None
    assert am.services_block([{"state": "retired"}]) is None


# ---- journey wiring: waiting button + services section ----------------------


def _journey(mission=None, automations=None, services=None):
    mission = mission or {
        "id": "m1",
        "statement": "own the newsletter",
        "confirmed_at": "2026-07-01",
        "agent_phase": "work",
        "setup_stage": None,
        "autonomy_rung": 2,
        "created_at": "2026-07-01T00:00:00+00:00",
    }
    return journey.build_journey(
        mission=mission,
        goals_list=[],
        loops_open=[],
        loops_all=[],
        value_log=[],
        next_steps=[],
        intake=[],
        services=services,
        automations=automations,
    )


def test_awaiting_signoff_gets_waiting_button():
    j = _journey(
        automations=[
            {"id": "a1", "what": "draft the newsletter", "state": "awaiting_your_signoff"},
            {"id": "a2", "what": "other", "state": "running"},
        ]
    )
    assert "waiting" in j["sections"]
    items = j["waiting"]["items"]
    assert len(items) == 1
    assert items[0]["action"] == "approve_automation"
    assert items[0]["object_id"] == "a1"
    assert "sample runs" in items[0]["text"]


def test_services_section_appears_with_block():
    block = {"headline": "What I run for you — 1 automation", "items": [{"name": "x"}]}
    j = _journey(services=block)
    assert "services" in j["sections"]
    assert j["services"] == block


def test_no_automations_no_services_section():
    j = _journey()
    assert "services" not in j["sections"]
    assert "waiting" not in j["sections"]


# ---- tool layer -------------------------------------------------------------


@pytest.mark.asyncio
async def test_tools_registered_and_errors_are_dicts(actx):
    for t in (
        "automation_register",
        "automation_signoff_request",
        "automation_signoff",
        "automation_run_report",
        "automation_adoption_event",
        "automation_pause",
        "automation_resume",
        "automation_retire",
        "automation_state",
    ):
        assert t in actx.tool_registry.registered
    out = await call(actx, "automation_register", what="")
    assert "error" in out


@pytest.mark.asyncio
async def test_tool_flow_end_to_end(actx):
    a = await call(actx, "automation_register", what="draft the newsletter", **FULL)
    assert a["state"] == "building"
    # gate refusal comes back as an error dict, not an exception
    bad = await call(actx, "automation_signoff_request", samples="")
    assert "error" in bad
    d = await call(
        actx, "automation_signoff_request", automation_id=a["id"], samples="in → out"
    )
    assert d["state"] == "awaiting_your_signoff"
    d = await call(actx, "automation_signoff", automation_id=a["id"])
    assert d["state"] == "hypercare"
    d = await call(actx, "automation_run_report", automation_id=a["id"], ok=True)
    assert d["clean_runs"] == 1
    st = await call(actx, "automation_state")
    assert st["count"] == 1
    assert st["automations"][0]["state_label"] == "extra watch"


@pytest.mark.asyncio
async def test_omitted_id_targets_newest_live_automation(actx, astore):
    await _make(astore)
    d = await call(actx, "automation_signoff_request", samples="in → out")
    assert d["state"] == "awaiting_your_signoff"


@pytest.mark.asyncio
async def test_unknown_id_and_no_automation_errors(actx):
    out = await call(actx, "automation_pause", automation_id=str(_uuid.uuid4()))
    assert "no automation with id" in out["error"]
    out = await call(actx, "automation_pause")
    assert "automation_register" in out["error"]
