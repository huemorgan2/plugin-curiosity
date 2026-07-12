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
) -> dict[str, Any]:
    """The honest half of the contentment gauge — pure clock math, no vibes.

    Bands: `stalled` — 2+ loops past their nudge date, or a stage sat on for
    7+ days (5+ if it's the un-ratified S2). `dragging` — one overdue loop,
    S2 at the 3-day ratification-forcing threshold, or 4+ days on any stage.
    `ahead` — advanced a stage within ~1 day with nothing overdue. Else
    `on-track`. Work phase paces only on loop debt (stages are done).
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
            reasons.append(f"charter un-ratified for {stage_age_days} days")
        elif stage_age_days >= 7:
            reasons.append(f"{stage_age_days} days at the '{stage_word}' step")
    elif overdue_loops == 1 or stage_age_days >= 4 or (setup_stage == "S2" and stage_age_days >= 3):
        band = "dragging"
        if overdue_loops == 1:
            reasons.append("1 loop past its nudge date")
        if setup_stage == "S2" and stage_age_days >= 3:
            reasons.append(f"ratification pending {stage_age_days} days")
        elif stage_age_days >= 4:
            reasons.append(f"{stage_age_days} days at the '{stage_word}' step")
    elif stage_age_days <= 1 and setup_stage not in ("S0",):
        band = "ahead"
        reasons.append(f"reached '{stage_word}' within the last day")
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
