"""telemetry.py — heartbeat self-reports + the pane's live bridge (9.002).

Two jobs:

1. **heartbeat_report** — the structured end of every heartbeat fire. The
   9.001 contract kept the streak in prose ([[setup-heartbeat]] verdict
   lines); 9.002 adds one auto-approve tool call per fire so the streak is
   DATA: graduation proposals cite the real number, the weekly review audits
   report-vs-page drift, and the Missions pane renders the pulse without
   parsing prose. `morale` is the agent's own words (personality-voiced by
   the contract, never an enum here).

2. **emit_ui_event** — curiosity's side of core's generic plugin-iframe
   bridge: `ctx.events.emit("ui.plugin.event", {plugin, event, payload})`
   → global SSE → Shell postMessage into the Missions pane. Best-effort by
   design: a core without the bus (or a test ctx without .events) must never
   fail the write that triggered the emit.

Pace and sentiment are server-computed HERE (not in the UI) so the pane and
any future consumer agree on the bands, and the popover explaining "how is
this computed" has exactly one implementation to describe.
"""

from __future__ import annotations

import logging
import uuid as _uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from luna_sdk import PluginContext, ToolDef

from .models import HeartbeatReport, Mission
from .scopes import STAGE_LABELS

log = logging.getLogger("plugin-curiosity")

PLUGIN_NAME = "plugin-curiosity"

PACE_BANDS = ("ahead", "on-track", "dragging", "stalled")
SENTIMENT_BANDS = ("positive", "neutral", "strained", "blocked")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite round-trips DateTime(timezone=True) as naive UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


async def emit_ui_event(ctx: PluginContext, event: str, payload: dict | None = None) -> bool:
    """Emit a live-bridge event for the Missions pane. Never raises."""
    events = getattr(ctx, "events", None)
    emit = getattr(events, "emit", None)
    if not callable(emit):
        return False
    try:
        await emit(
            "ui.plugin.event",
            {"plugin": PLUGIN_NAME, "event": event, "payload": payload or {}},
        )
        return True
    except Exception:  # noqa: BLE001
        log.debug("ui.plugin.event emit failed (%s)", event, exc_info=True)
        return False


def _report_dict(r: HeartbeatReport) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "streak": r.streak,
        "gaps_open": r.gaps_open,
        "wobbles": r.wobbles,
        "morale": r.morale,
        "note": r.note,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


class HeartbeatStore:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    async def add(
        self, streak: int, gaps_open: int, wobbles: int, morale: str, note: str = ""
    ) -> dict[str, Any]:
        async with self._sf() as s:
            m = (
                await s.execute(select(Mission).where(Mission.active))
            ).scalar_one_or_none()
            if m is None:
                raise LookupError("no active mission — nothing to report against")
            r = HeartbeatReport(
                mission_id=m.id,
                streak=max(0, int(streak)),
                gaps_open=max(0, int(gaps_open)),
                wobbles=max(0, int(wobbles)),
                morale=morale.strip()[:80],
                note=note.strip(),
            )
            s.add(r)
            await s.commit()
            return _report_dict(r)

    async def list(self, *, limit: int = 50, mission_id: str | None = None) -> list[dict[str, Any]]:
        """Newest first."""
        async with self._sf() as s:
            q = select(HeartbeatReport)
            if mission_id is not None:
                try:
                    key = _uuid.UUID(str(mission_id))
                except ValueError:
                    return []
                q = q.where(HeartbeatReport.mission_id == key)
            q = q.order_by(HeartbeatReport.created_at.desc()).limit(limit)
            rows = (await s.execute(q)).scalars().all()
            return [_report_dict(r) for r in rows]

    async def latest(self) -> dict[str, Any] | None:
        rows = await self.list(limit=1)
        return rows[0] if rows else None


def compute_pace(
    *,
    agent_phase: str,
    setup_stage: str,
    stage_age_days: int,
    overdue_loops: int,
    now: datetime | None = None,
    last_report_at: datetime | None = None,
    blocked_horizons: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The honest half of the contentment gauge — pure clock math, no vibes.

    Bands: `stalled` — 2+ loops past their nudge date, or a stage sat on for
    7+ days (5+ if it's the un-ratified S2). `dragging` — one overdue loop,
    S2 at the 3-day ratification-forcing threshold, or 4+ days on any stage.
    `ahead` — advanced a stage within ~1 day with nothing overdue. Else
    `on-track`. Work phase paces only on loop debt (stages are done).

    0.15.0 honest horizons: `blocked_horizons` are open goals whose horizon
    is someone else's move (on_unlock / awaiting_approval dicts with
    statement + horizon_ref). They NEVER worsen the band — a blocked goal is
    not a late goal — but the reason names the unlock and its ~5-minute
    human cost, so the pane blames the wait honestly.
    """
    now = now or _utcnow()
    # reasons travel into owner-facing surfaces (heartbeat notes, pace nudges)
    # — stage words, never S-codes (role-resilience dojo, curiosity 0.9.4)
    stage_word = STAGE_LABELS.get(setup_stage, (setup_stage, ""))[0]
    reasons: list[str] = []
    band = "on-track"
    if agent_phase == "work":
        if overdue_loops >= 2:
            band, reasons = "stalled", [f"{overdue_loops} loops past their nudge date"]
        elif overdue_loops == 1:
            band, reasons = "dragging", ["1 loop past its nudge date"]
    elif overdue_loops >= 2 or stage_age_days >= 7 or (setup_stage == "S2" and stage_age_days >= 5):
        band = "stalled"
        if overdue_loops >= 2:
            reasons.append(f"{overdue_loops} loops past their nudge date")
        if setup_stage == "S2" and stage_age_days >= 5:
            reasons.append(f"waiting {stage_age_days} days for you to approve the job description")
        elif stage_age_days >= 7:
            reasons.append(f"{stage_age_days} days at the '{stage_word}' step")
    elif overdue_loops == 1 or stage_age_days >= 4 or (setup_stage == "S2" and stage_age_days >= 3):
        band = "dragging"
        if overdue_loops == 1:
            reasons.append("1 loop past its nudge date")
        if setup_stage == "S2" and stage_age_days >= 3:
            reasons.append(f"job description waiting {stage_age_days} days for your approval")
        elif stage_age_days >= 4:
            reasons.append(f"{stage_age_days} days at the '{stage_word}' step")
    elif stage_age_days <= 1 and setup_stage not in ("S0",):
        band = "ahead"
        reasons.append(f"reached '{stage_word}' within the last day")
    # blocked horizons: band untouched, unlock named + the human cost
    for g in (blocked_horizons or [])[:2]:
        ref = (g.get("horizon_ref") or "").strip() or (
            "your approval" if g.get("horizon_kind") == "awaiting_approval"
            else "an unlock"
        )
        stmt = (g.get("statement") or "").strip()[:60]
        reasons.append(
            f"'{stmt}' waits on {ref} — about 5 minutes of your time unlocks it"
        )
    if band == "on-track" and not reasons:
        reasons.append("no overdue loops, stage moving at pace")
    last_report_age_hours = None
    if last_report_at is not None:
        aware = _aware(last_report_at)
        last_report_age_hours = max(0, int((now - aware).total_seconds() // 3600))
    return {
        "band": band,
        "reasons": reasons,
        "stage_age_days": stage_age_days,
        "overdue_loops": overdue_loops,
        "last_report_age_hours": last_report_age_hours,
    }


def compute_sentiment(
    latest: dict[str, Any] | None,
    previous: dict[str, Any] | None,
    *,
    blocked_on_owner: int = 0,
) -> str:
    """Stable color band behind the agent's own morale words. Deterministic
    from the structured numbers — never parses the words: `blocked` — an
    ask/waiting_on loop sits past its nudge date. `strained` — wobbles this
    fire, or the gap list grew since the previous one. `positive` — streak
    of 2+ with no wobbles. Else `neutral` (including: no report yet)."""
    if blocked_on_owner > 0:
        return "blocked"
    if latest is None:
        return "neutral"
    if latest.get("wobbles", 0) > 0:
        return "strained"
    if previous is not None and latest.get("gaps_open", 0) > previous.get("gaps_open", 0):
        return "strained"
    if latest.get("streak", 0) >= 2:
        return "positive"
    return "neutral"


# ---- adoption-funnel KPIs (11.008/M7) ----------------------------------
#
# Every number the weekly/monthly note cites is computed HERE from stored
# rows — the agent reads metrics_snapshot and quotes it; it never does the
# arithmetic itself (agents have no clock and worse calibration). Every KPI
# is None when its source has no data yet: "no data" is an honest answer,
# a fabricated denominator is not.


def _hours(a: datetime | None, b: datetime | None) -> float | None:
    a, b = _aware(a), _aware(b)
    if a is None or b is None:
        return None
    return round((b - a).total_seconds() / 3600, 1)


def _rate(hits: int, total: int) -> float | None:
    return round(hits / total, 2) if total else None


def compute_metrics(
    *,
    mission: dict[str, Any] | None = None,
    values: list[dict[str, Any]] | None = None,
    cards: list[dict[str, Any]] | None = None,
    goals: list[dict[str, Any]] | None = None,
    automations: list[dict[str, Any]] | None = None,
    proposals: list[dict[str, Any]] | None = None,
    boundaries: list[dict[str, Any]] | None = None,
    incidents: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Pure funnel math over plain dicts (datetimes where noted). `boundaries`
    / `incidents` None means the SOURCE is absent (goalseek not installed / no
    incident ledger) — distinct from an installed source with zero rows."""
    values = values or []
    cards = cards or []
    goals = goals or []
    automations = automations or []
    proposals = proposals or []
    m = mission or {}

    # funnel head: how long from first contact to a confirmed mission, and
    # from there to the first value receipt (time-to-first-win)
    confirmed = _hours(m.get("created_at"), m.get("confirmed_at"))
    start = m.get("confirmed_at") or m.get("created_at")
    first_win = None
    if values:
        first = min((_aware(v.get("delivered_at")) for v in values
                     if v.get("delivered_at")), default=None)
        first_win = _hours(start, first) if first else None
    setup_days = None
    if m.get("agent_phase") == "work":
        h = _hours(m.get("created_at"), m.get("phase_entered_at"))
        setup_days = round(h / 24, 1) if h is not None else None

    # next-step cards: how often the owner redirected a proposed spend
    closed = [c for c in cards if c.get("status") in ("done", "redirected")]
    redirected = sum(1 for c in closed if c.get("status") == "redirected")

    # expectation hit rate: of goals that RESOLVED, how many landed
    resolved = [g for g in goals if g.get("status") in ("done", "dropped")]
    hit = sum(1 for g in resolved if g.get("status") == "done")

    # automations: hypercare exits + adoption honesty (no run counter exists,
    # so overrides/ignores are reported as totals, never as a made-up rate)
    entered = [a for a in automations if a.get("hypercare_since")]
    promoted = [a for a in entered if a.get("promoted_at")]
    exit_days = [
        round(h / 24, 1)
        for a in promoted
        if (h := _hours(a.get("hypercare_since"), a.get("promoted_at"))) is not None
    ]

    # proposals: acceptance + prediction calibration (±30% band)
    decided = [p for p in proposals
               if p.get("status") in ("accepted", "declined", "done", "dropped")]
    accepted = sum(1 for p in decided
                   if p.get("status") in ("accepted", "done", "dropped"))
    from .proposals import prediction_hit

    scored = [
        hit_
        for p in proposals
        if p.get("status") == "done"
        and (hit_ := prediction_hit(
            p.get("predicted_minutes"), p.get("actual_minutes"))) is not None
    ]

    bounds = None
    if boundaries is not None:
        bounds = {
            "active": sum(1 for b in boundaries if b.get("status") == "active"),
            "checks": sum(int(b.get("checks_count") or 0) for b in boundaries),
            "exceptions": sum(int(b.get("denies_count") or 0) for b in boundaries),
        }

    self_report = None
    if incidents is not None:
        spans = [
            h for i in incidents
            if (h := _hours(i.get("happened_at"), i.get("reported_at"))) is not None
        ]
        self_report = round(sum(spans) / len(spans), 1) if spans else None

    return {
        "time_to_confirmed_mission_hours": confirmed,
        "time_to_first_win_hours": first_win,
        "setup_to_work_days": setup_days,
        "cards_closed": len(closed),
        "card_redirect_rate": _rate(redirected, len(closed)),
        "expectation_hit_rate": _rate(hit, len(resolved)),
        "goals_resolved": len(resolved),
        "boundary_exceptions": bounds,
        "time_to_self_report_hours": self_report,
        "hypercare_entered": len(entered),
        "hypercare_exit_rate": _rate(len(promoted), len(entered)),
        "hypercare_exit_days_avg": (
            round(sum(exit_days) / len(exit_days), 1) if exit_days else None
        ),
        "automation_overrides": sum(int(a.get("overrides") or 0) for a in automations),
        "automation_ignores": sum(int(a.get("ignores") or 0) for a in automations),
        "proposals_decided": len(decided),
        "proposal_acceptance_rate": _rate(accepted, len(decided)),
        "prediction_scored": len(scored),
        "prediction_accuracy": _rate(sum(scored), len(scored)),
    }


async def _probe_boundaries(ctx: PluginContext) -> list[dict[str, Any]] | None:
    """goalseek's policy_list, feature-detected: None when goalseek is absent
    (the KPI then reads 'no data', never zero)."""
    try:
        reg = ctx.tool_registry.get("policy_list")
    except Exception:  # noqa: BLE001
        return None
    if reg is None:
        return None
    try:
        out = await reg.handler()
        items = out.get("boundaries") if isinstance(out, dict) else None
        return items if isinstance(items, list) else None
    except Exception:  # noqa: BLE001
        log.debug("policy_list probe failed", exc_info=True)
        return None


async def gather_metrics(ctx: PluginContext, sf) -> dict[str, Any]:
    """DB → fixtures → compute_metrics. One read pass, newest mission only."""
    from .models import Automation, Goal, NextStep, Proposal, ValueEntry

    async with sf() as s:
        m = (
            await s.execute(
                select(Mission).where(Mission.active)
                .order_by(Mission.created_at.desc())
            )
        ).scalars().first()
        if m is None:
            return {"error": "no active mission — no funnel to measure"}
        mid = m.id

        def rows(model):  # noqa: ANN001
            return select(model).where(model.mission_id == mid)

        values = (await s.execute(rows(ValueEntry))).scalars().all()
        cards = (await s.execute(rows(NextStep))).scalars().all()
        # goals are mission-global rows (no mission_id column — pre-8.2 shape)
        goals = (await s.execute(select(Goal))).scalars().all()
        autos = (await s.execute(rows(Automation))).scalars().all()
        props = (await s.execute(rows(Proposal))).scalars().all()
        fixtures = {
            "mission": {
                "created_at": m.created_at,
                "confirmed_at": m.confirmed_at,
                "agent_phase": m.agent_phase,
                "phase_entered_at": m.phase_entered_at,
            },
            "values": [{"delivered_at": v.delivered_at} for v in values],
            "cards": [{"status": c.status} for c in cards],
            "goals": [{"status": g.status} for g in goals],
            "automations": [
                {
                    "hypercare_since": a.hypercare_since,
                    "promoted_at": a.promoted_at,
                    "overrides": a.overrides,
                    "ignores": a.ignores,
                }
                for a in autos
            ],
            "proposals": [
                {
                    "status": p.status,
                    "predicted_minutes": p.predicted_minutes,
                    "actual_minutes": p.actual_minutes,
                }
                for p in props
            ],
        }
    fixtures["boundaries"] = await _probe_boundaries(ctx)
    return compute_metrics(**fixtures)


def register_tools(ctx: PluginContext, store: HeartbeatStore) -> None:
    async def _report(
        streak: int, gaps_open: int, wobbles: int, morale: str, note: str = ""
    ) -> dict[str, Any]:
        try:
            report = await store.add(streak, gaps_open, wobbles, morale, note=note)
        except (LookupError, ValueError) as e:
            return {"error": str(e)}
        await emit_ui_event(ctx, "heartbeat", report)
        # every fire ends here (contract clause d) — the cheapest reliable
        # moment to enforce the EXACTLY-ONE trigger invariant without an
        # approval gate or a restart
        try:
            from . import research

            await research.dedupe_heartbeats(ctx)
        except Exception:  # noqa: BLE001
            log.debug("heartbeat dedupe after report failed", exc_info=True)
        return {"report": report}

    ctx.tool_registry.register(
        PLUGIN_NAME,
        ToolDef(
            name="heartbeat_report",
            description=(
                "End every setup-heartbeat fire with this: your structured "
                "pulse. streak = consecutive clean fires (no new gaps, no "
                "wobbles); gaps_open = what still stands between you and "
                "qualified; wobbles = things that broke or regressed THIS "
                "fire; morale = how the work feels, in your own voice, one "
                "or two words consistent with your persona (never a status "
                "code); note = one line of context the owner sees verbatim."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "streak": {"type": "integer", "minimum": 0},
                    "gaps_open": {"type": "integer", "minimum": 0},
                    "wobbles": {"type": "integer", "minimum": 0},
                    "morale": {"type": "string", "description": "1-2 words, your own voice"},
                    "note": {"type": "string", "description": "one line, owner-facing"},
                },
                "required": ["streak", "gaps_open", "wobbles", "morale"],
            },
            policy="auto_approve",
            risk_level="low",
        ),
        _report,
    )

    async def _snapshot() -> dict[str, Any]:
        return await gather_metrics(ctx, store._sf)

    ctx.tool_registry.register(
        PLUGIN_NAME,
        ToolDef(
            name="metrics_snapshot",
            description=(
                "Your server-computed adoption scoreboard: time to confirmed "
                "mission, time to first win, card redirect rate, expectation "
                "hit rate, boundary exceptions, hypercare exits, automation "
                "overrides, proposal acceptance and prediction accuracy. "
                "Read this BEFORE writing a weekly or monthly note and quote "
                "its numbers verbatim — never compute or estimate a metric "
                "yourself. A None value means 'no data yet'; say that "
                "plainly rather than inventing a number."
            ),
            parameters={"type": "object", "properties": {}, "required": []},
            policy="auto_approve",
            risk_level="low",
        ),
        _snapshot,
    )
