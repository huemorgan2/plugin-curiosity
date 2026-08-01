"""Adoption-funnel KPIs (11.008/M7): every number server-computed from
fixtures, honest None when the source has no data, goalseek probe
feature-detected, DB gatherer end-to-end, tool + route registration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from plugin_curiosity.telemetry import compute_metrics

T0 = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)


def test_empty_world_is_all_no_data():
    m = compute_metrics()
    assert m["time_to_confirmed_mission_hours"] is None
    assert m["time_to_first_win_hours"] is None
    assert m["setup_to_work_days"] is None
    assert m["card_redirect_rate"] is None
    assert m["expectation_hit_rate"] is None
    assert m["boundary_exceptions"] is None       # source absent
    assert m["time_to_self_report_hours"] is None  # no incident ledger
    assert m["hypercare_exit_rate"] is None
    assert m["proposal_acceptance_rate"] is None
    assert m["prediction_accuracy"] is None


def test_funnel_head_times():
    m = compute_metrics(
        mission={
            "created_at": T0,
            "confirmed_at": T0 + timedelta(hours=3),
            "agent_phase": "work",
            "phase_entered_at": T0 + timedelta(days=12),
        },
        values=[
            {"delivered_at": T0 + timedelta(hours=51)},
            {"delivered_at": T0 + timedelta(hours=99)},
        ],
    )
    assert m["time_to_confirmed_mission_hours"] == 3.0
    # first win counts from CONFIRMATION (the mission's real start), earliest
    # receipt wins
    assert m["time_to_first_win_hours"] == 48.0
    assert m["setup_to_work_days"] == 12.0


def test_setup_phase_has_no_setup_to_work_number():
    m = compute_metrics(
        mission={"created_at": T0, "agent_phase": "setup",
                 "phase_entered_at": None}
    )
    assert m["setup_to_work_days"] is None


def test_card_redirect_rate_counts_only_closed_cards():
    m = compute_metrics(cards=[
        {"status": "done"}, {"status": "done"}, {"status": "done"},
        {"status": "redirected"},
        {"status": "running"}, {"status": "proposed"},  # open — not in the base
    ])
    assert m["cards_closed"] == 4
    assert m["card_redirect_rate"] == 0.25


def test_expectation_hit_rate_over_resolved_goals_only():
    m = compute_metrics(goals=[
        {"status": "done"}, {"status": "done"}, {"status": "dropped"},
        {"status": "active"}, {"status": "stalled"},  # unresolved — excluded
    ])
    assert m["goals_resolved"] == 3
    assert m["expectation_hit_rate"] == 0.67


def test_boundary_source_present_vs_absent():
    absent = compute_metrics(boundaries=None)
    assert absent["boundary_exceptions"] is None
    present = compute_metrics(boundaries=[
        {"status": "active", "checks_count": 3, "denies_count": 2},
        {"status": "active", "checks_count": 1, "denies_count": 0},
        {"status": "proposed", "checks_count": 0, "denies_count": 0},
    ])
    assert present["boundary_exceptions"] == {
        "active": 2, "checks": 4, "exceptions": 2,
    }
    # installed-but-zero is DATA, not absence
    zero = compute_metrics(boundaries=[])
    assert zero["boundary_exceptions"] == {"active": 0, "checks": 0,
                                           "exceptions": 0}


def test_self_report_span_when_an_incident_ledger_exists():
    m = compute_metrics(incidents=[
        {"happened_at": T0, "reported_at": T0 + timedelta(hours=1)},
        {"happened_at": T0, "reported_at": T0 + timedelta(hours=2)},
    ])
    assert m["time_to_self_report_hours"] == 1.5
    assert compute_metrics(incidents=[])["time_to_self_report_hours"] is None


def test_hypercare_exit_math_and_override_totals():
    m = compute_metrics(automations=[
        {"hypercare_since": T0, "promoted_at": T0 + timedelta(days=8),
         "overrides": 1, "ignores": 0},
        {"hypercare_since": T0, "promoted_at": None,
         "overrides": 2, "ignores": 3},
        {"hypercare_since": None, "promoted_at": None,
         "overrides": 0, "ignores": 0},  # still building
    ])
    assert m["hypercare_entered"] == 2
    assert m["hypercare_exit_rate"] == 0.5
    assert m["hypercare_exit_days_avg"] == 8.0
    # no run counter exists — totals, never a fabricated rate
    assert m["automation_overrides"] == 3
    assert m["automation_ignores"] == 3


def test_proposal_acceptance_and_prediction_accuracy():
    m = compute_metrics(proposals=[
        {"status": "done", "predicted_minutes": 20, "actual_minutes": 22},
        {"status": "done", "predicted_minutes": 20, "actual_minutes": 40},
        {"status": "done", "predicted_minutes": None, "actual_minutes": 30},
        {"status": "declined", "predicted_minutes": 5, "actual_minutes": None},
        {"status": "proposed", "predicted_minutes": 9, "actual_minutes": None},
    ])
    # decided = 2 done + 1 declined; accepted side = the 3 done/dropped
    assert m["proposals_decided"] == 4
    assert m["proposal_acceptance_rate"] == 0.75
    # only numeric done rows are scoreable; 22/20 hits, 40/20 misses
    assert m["prediction_scored"] == 2
    assert m["prediction_accuracy"] == 0.5


# ---- gatherer over a real (sqlite) DB --------------------------------------


@pytest.mark.asyncio
async def test_gather_metrics_end_to_end(ctx, store, sf):
    from plugin_curiosity import proposals as pr
    from plugin_curiosity.telemetry import gather_metrics

    await store.set("own the weekly newsletter end to end")
    ps = pr.ProposalStore(sf)
    await ps.open("faster digest", "saves ~20 min/week", predicted_minutes=20)
    await ps.decide(decision="accepted")
    await ps.close(outcome="done", actual="saved ~21 min/week",
                   actual_minutes=21)
    m = await gather_metrics(ctx, sf)
    assert m["proposals_decided"] == 1
    assert m["proposal_acceptance_rate"] == 1.0
    assert m["prediction_accuracy"] == 1.0
    # goalseek absent on the fake registry → probe returns source-absent
    assert m["boundary_exceptions"] is None


@pytest.mark.asyncio
async def test_gather_metrics_probes_policy_list_when_present(ctx, store, sf):
    import types

    from plugin_curiosity.telemetry import gather_metrics

    await store.set("own the weekly newsletter end to end")

    async def _policy_list(**kw):
        return {"boundaries": [
            {"status": "active", "checks_count": 2, "denies_count": 2},
        ]}

    ctx.tool_registry.registered["policy_list"] = (
        types.SimpleNamespace(name="policy_list"), _policy_list)
    m = await gather_metrics(ctx, sf)
    assert m["boundary_exceptions"] == {"active": 1, "checks": 2,
                                        "exceptions": 2}


@pytest.mark.asyncio
async def test_gather_metrics_without_mission_is_honest(ctx, sf):
    from plugin_curiosity.telemetry import gather_metrics

    m = await gather_metrics(ctx, sf)
    assert "no active mission" in m["error"]


# ---- surfaces ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_metrics_snapshot_tool_registered(ctx, store, sf):
    from plugin_curiosity import telemetry
    from plugin_curiosity.telemetry import HeartbeatStore

    telemetry.register_tools(ctx, HeartbeatStore(sf))
    assert "metrics_snapshot" in ctx.tool_registry.registered
    td = ctx.tool_registry.registered["metrics_snapshot"][0]
    assert td.policy == "auto_approve"
    assert "verbatim" in td.description  # quote, never compute
    await store.set("own the weekly newsletter end to end")
    out = await ctx.tool_registry.registered["metrics_snapshot"][1]()
    assert "proposal_acceptance_rate" in out
