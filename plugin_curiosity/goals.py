"""goals.py — the goal ledger: Luna's own commitments toward the mission.

Phase 8.2 mechanism A. A mission alone reads as a topic; goals make the
pursuit visible and scoreable. Luna sets 2-3 goals at kickoff (goal_set),
reports movement after each daily pass (goal_update), and the weekly review
scores the ledger honestly — done / moved / stalled — and confronts stalls.

Write-through: every change rebuilds the human-readable [[mission-goals]]
wiki page (best-effort — a missing wiki degrades the payload note, never the
write). The DB row is the source of truth; the page is the owner's mirror.

All three tools are auto_approve: goals are Luna's own commitments, not side
effects on the world.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select

from luna_sdk import PluginContext, ToolDef

from .models import Goal

log = logging.getLogger("plugin-curiosity")

GOAL_STATUSES = ("active", "done", "stalled", "dropped")
# phase 10 readiness: does the agent HAVE what this goal needs? green = yes,
# amber = partly, red = something is missing. readiness_note says what, in
# have/missing terms the owner can act on.
GOAL_READINESS = ("green", "amber", "red")


def _goal_dict(g: Goal) -> dict[str, Any]:
    return {
        "id": str(g.id),
        "statement": g.statement,
        "why": g.why,
        "target_date": g.target_date,
        "status": g.status,
        "progress_note": g.progress_note,
        "expected_result": g.expected_result,
        "readiness": g.readiness or None,
        "readiness_note": g.readiness_note,
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "updated_at": g.updated_at.isoformat() if g.updated_at else None,
    }


class GoalStore:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    async def add(
        self,
        statement: str,
        *,
        why: str = "",
        target_date: str = "",
        expected_result: str = "",
        readiness: str = "",
        readiness_note: str = "",
    ) -> dict[str, Any]:
        statement = (statement or "").strip()
        if not statement:
            raise ValueError("goal statement must be non-empty")
        if readiness and readiness not in GOAL_READINESS:
            raise ValueError(f"readiness must be one of {GOAL_READINESS}")
        async with self._sf() as s:
            g = Goal(
                statement=statement,
                why=why.strip(),
                target_date=target_date.strip(),
                expected_result=expected_result.strip(),
                readiness=readiness,
                readiness_note=readiness_note.strip(),
            )
            s.add(g)
            await s.commit()
            return _goal_dict(g)

    async def update(
        self,
        goal_id: str,
        *,
        status: str | None = None,
        progress_note: str | None = None,
        target_date: str | None = None,
        expected_result: str | None = None,
        readiness: str | None = None,
        readiness_note: str | None = None,
    ) -> dict[str, Any]:
        try:
            key = uuid.UUID(str(goal_id))
        except ValueError:
            raise LookupError(f"no goal with id {goal_id}") from None
        async with self._sf() as s:
            g = await s.get(Goal, key)
            if g is None:
                raise LookupError(f"no goal with id {goal_id}")
            if status is not None:
                if status not in GOAL_STATUSES:
                    raise ValueError(f"status must be one of {GOAL_STATUSES}")
                g.status = status
            if progress_note is not None:
                g.progress_note = progress_note.strip()
            if target_date is not None:
                g.target_date = target_date.strip()
            if expected_result is not None:
                g.expected_result = expected_result.strip()
            if readiness is not None:
                if readiness and readiness not in GOAL_READINESS:
                    raise ValueError(f"readiness must be one of {GOAL_READINESS}")
                g.readiness = readiness
            if readiness_note is not None:
                g.readiness_note = readiness_note.strip()
            await s.commit()
            return _goal_dict(g)

    async def list(self, *, include_closed: bool = True) -> list[dict[str, Any]]:
        async with self._sf() as s:
            q = select(Goal).order_by(Goal.created_at)
            rows = (await s.execute(q)).scalars().all()
            out = [_goal_dict(g) for g in rows]
            if not include_closed:
                out = [g for g in out if g["status"] in ("active", "stalled")]
            return out


_STATUS_MARK = {"active": "🎯", "done": "✅", "stalled": "⚠️", "dropped": "✖️"}
_READINESS_MARK = {"green": "🟢", "amber": "🟡", "red": "🔴"}


def render_goals_page(goals: list[dict[str, Any]]) -> str:
    """The [[mission-goals]] page body — the owner-readable scoreboard."""
    if not goals:
        return (
            "*No goals committed yet — the mission kickoff sets the first "
            "ones (goal_set).*\n"
        )
    lines = ["Goals I have committed to for the mission (see [[mission]]):", ""]
    for g in goals:
        mark = _STATUS_MARK.get(g["status"], "•")
        head = f"- {mark} **{g['statement']}**"
        if g["target_date"]:
            head += f" — target: {g['target_date']}"
        lines.append(head)
        if g["why"]:
            lines.append(f"  - why: {g['why']}")
        if g.get("expected_result"):
            lines.append(f"  - expected result: {g['expected_result']}")
        if g.get("readiness"):
            rmark = _READINESS_MARK.get(g["readiness"], "•")
            note = f" — {g['readiness_note']}" if g.get("readiness_note") else ""
            lines.append(f"  - readiness: {rmark} {g['readiness']}{note}")
        if g["progress_note"]:
            lines.append(f"  - progress: {g['progress_note']}")
        lines.append(f"  - status: {g['status']}")
    lines.append("")
    return "\n".join(lines)


async def _mirror_to_wiki(ctx: PluginContext, store: GoalStore) -> str:
    try:
        wiki = ctx.provider_registry.get("wiki")
    except Exception:  # noqa: BLE001
        return "wiki provider unavailable — goals page not mirrored"
    try:
        goals = await store.list()
        await wiki.upsert_page(
            "mission-goals",
            "Mission Goals",
            render_goals_page(goals),
            summary=f"{sum(1 for g in goals if g['status'] == 'active')} active goal(s)",
            note="goal ledger write-through",
        )
        return "ok"
    except Exception as e:  # noqa: BLE001
        log.warning("goal wiki mirror failed", exc_info=True)
        return f"wiki mirror failed: {e}"


def register_tools(ctx: PluginContext, store: GoalStore) -> None:
    from . import telemetry

    async def _set(
        statement: str,
        why: str = "",
        target_date: str = "",
        expected_result: str = "",
        readiness: str = "",
        readiness_note: str = "",
    ) -> dict[str, Any]:
        try:
            goal = await store.add(
                statement,
                why=why,
                target_date=target_date,
                expected_result=expected_result,
                readiness=readiness,
                readiness_note=readiness_note,
            )
        except ValueError as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "goal"})
        return {"goal": goal, "wiki_mirror": await _mirror_to_wiki(ctx, store)}

    async def _update(
        id: str,
        status: str | None = None,
        progress_note: str | None = None,
        target_date: str | None = None,
        expected_result: str | None = None,
        readiness: str | None = None,
        readiness_note: str | None = None,
    ) -> dict[str, Any]:
        try:
            goal = await store.update(
                id,
                status=status,
                progress_note=progress_note,
                target_date=target_date,
                expected_result=expected_result,
                readiness=readiness,
                readiness_note=readiness_note,
            )
        except (ValueError, LookupError) as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "goal"})
        return {"goal": goal, "wiki_mirror": await _mirror_to_wiki(ctx, store)}

    async def _list() -> dict[str, Any]:
        goals = await store.list()
        if not goals:
            return {
                "goals": [],
                "note": (
                    "no goals committed yet — decompose the mission into 2-3 "
                    "concrete goals with goal_set and go after them"
                ),
            }
        return {"goals": goals}

    defs: list[tuple[ToolDef, Any]] = [
        (
            ToolDef(
                name="goal_set",
                description=(
                    "Commit to a concrete goal in pursuit of your mission — a "
                    "specific outcome YOU will drive, with a target date. Set "
                    "them at mission kickoff; add more as the picture sharpens. "
                    "For your NEXT 2-3 goals also state expected_result (what "
                    "done looks like) and readiness (green = I have everything "
                    "this needs, amber = partly, red = something is missing) "
                    "with a one-line readiness_note saying what you have and "
                    "what's missing. The ledger mirrors to the [[mission-goals]] "
                    "wiki page the owner can read."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "statement": {
                            "type": "string",
                            "description": "The goal — one concrete, checkable outcome.",
                        },
                        "why": {
                            "type": "string",
                            "description": "How achieving it serves the mission.",
                        },
                        "target_date": {
                            "type": "string",
                            "description": "When you aim to get there (e.g. '2026-07-20', 'end of July').",
                        },
                        "expected_result": {
                            "type": "string",
                            "description": "What done looks like — the required result, one line.",
                        },
                        "readiness": {"type": "string", "enum": list(GOAL_READINESS)},
                        "readiness_note": {
                            "type": "string",
                            "description": "One line: what you have / what's missing for this goal.",
                        },
                    },
                    "required": ["statement"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _set,
        ),
        (
            ToolDef(
                name="goal_update",
                description=(
                    "Record movement on a goal: progress notes, status changes "
                    "(active/done/stalled/dropped), target-date shifts, and "
                    "readiness re-scores (green/amber/red + what you have / "
                    "what's missing). Update after every research pass that "
                    "advanced a goal and re-score readiness when your ladder "
                    "changes; confront stalls honestly — change approach or "
                    "drop with a reason, never let a goal rot."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "The goal id (from goal_list)."},
                        "status": {"type": "string", "enum": list(GOAL_STATUSES)},
                        "progress_note": {
                            "type": "string",
                            "description": "What moved (or why it stalled) — one or two lines.",
                        },
                        "target_date": {"type": "string"},
                        "expected_result": {
                            "type": "string",
                            "description": "What done looks like — the required result, one line.",
                        },
                        "readiness": {"type": "string", "enum": list(GOAL_READINESS)},
                        "readiness_note": {
                            "type": "string",
                            "description": "One line: what you have / what's missing for this goal.",
                        },
                    },
                    "required": ["id"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _update,
        ),
        (
            ToolDef(
                name="goal_list",
                description=(
                    "Your goal ledger — every goal with status, progress, and "
                    "target date. Read it at the start of each research pass "
                    "and pick the goal you can advance TODAY."
                ),
                parameters={"type": "object", "properties": {}},
                policy="auto_approve",
                risk_level="low",
            ),
            _list,
        ),
    ]
    for tool_def, handler in defs:
        ctx.tool_registry.register("plugin-curiosity", tool_def, handler)
