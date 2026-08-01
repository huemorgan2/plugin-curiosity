"""proposals.py — the prediction-carrying improvement ledger (11.008/M7).

The weekly note may carry at most ONE micro-proposal, and every proposal is a
bet stated BEFORE the work: `predicted` (owner units, required at open) vs
`actual` (required at close). The point is calibration the owner can check —
"you said 20 min/week, it saved 25" — so proposal quality becomes data
instead of vibes.

Flow lives in the tool layer, not in prose: a second open while one proposal
is pending is refused with a steering hint naming the open one; closing
without `actual` is refused; a decline is terminal (propose something better,
don't re-litigate). Convergent by title — re-opening the same title while it
is still open returns the existing row (concurrent review turns must not
duplicate the bet).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from luna_sdk import PluginContext, ToolDef
from sqlalchemy import select

from . import telemetry
from .models import Mission, Proposal, ValueEntry

log = logging.getLogger("plugin-curiosity")

PROPOSAL_STATUSES = ("proposed", "accepted", "declined", "done", "dropped")
OPEN_STATUSES = ("proposed", "accepted")

# prediction accuracy tolerance: actual within ±30% of predicted counts as hit
ACCURACY_TOLERANCE = 0.30


def _utcnow() -> datetime:
    return datetime.now(UTC)


def prediction_hit(
    predicted_minutes: int | None, actual_minutes: int | None
) -> bool | None:
    """Server-computed calibration verdict: None when either side lacks a
    number (a prose-only prediction is legal — it just isn't scoreable)."""
    if not predicted_minutes or actual_minutes is None:
        return None
    return abs(actual_minutes - predicted_minutes) <= ACCURACY_TOLERANCE * predicted_minutes


def _dict(p: Proposal) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "title": p.title,
        "predicted": p.predicted,
        "predicted_minutes": p.predicted_minutes,
        "status": p.status,
        "actual": p.actual,
        "actual_minutes": p.actual_minutes,
        "prediction_hit": prediction_hit(p.predicted_minutes, p.actual_minutes)
        if p.status == "done"
        else None,
        "decision_note": p.decision_note,
        "value_ref": str(p.value_ref) if p.value_ref else None,
        "source": p.source,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "decided_at": p.decided_at.isoformat() if p.decided_at else None,
        "closed_at": p.closed_at.isoformat() if p.closed_at else None,
    }


def _verdict(p: Proposal) -> str | None:
    """The ready-made verdict sentence for a scored bet — the weekly note's
    Proposal line quotes this verbatim (p09 dojo run-3: given only raw
    fields, the model wrote 'No proposals closed this week' over a bet it
    had closed minutes earlier)."""
    if p.status not in ("done", "dropped"):
        return None
    lead = f"predicted {p.predicted}, actual {p.actual}"
    hit = prediction_hit(p.predicted_minutes, p.actual_minutes)
    if hit is True:
        return lead + " — the prediction held (within ±30%)"
    if hit is False:
        return lead + " — the prediction missed (outside ±30%)"
    return lead


class ProposalStore:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    async def _mission(self, s) -> Mission | None:
        q = (
            select(Mission)
            .where(Mission.active.is_(True))
            .order_by(Mission.created_at.desc())
        )
        return (await s.execute(q)).scalars().first()

    async def _open(self, s) -> Proposal | None:
        q = (
            select(Proposal)
            .where(Proposal.status.in_(OPEN_STATUSES))
            .order_by(Proposal.created_at.desc())
        )
        return (await s.execute(q)).scalars().first()

    async def has_live_bet(self, *, days: int = 7) -> bool:
        """An open proposal, or one closed in the last `days` — the weekly
        note's Proposal line has something real to say."""
        async with self._sf() as s:
            if await self._open(s) is not None:
                return True
            cutoff = datetime.now(UTC).timestamp() - days * 86400
            q = (
                select(Proposal)
                .where(Proposal.closed_at.is_not(None))
                .order_by(Proposal.closed_at.desc())
            )
            last = (await s.execute(q)).scalars().first()
            if last is None or last.closed_at is None:
                return False
            closed = last.closed_at
            if closed.tzinfo is None:
                closed = closed.replace(tzinfo=UTC)
            return closed.timestamp() >= cutoff

    async def weekly_note_gap(self, body: str, *, days: int = 7) -> str | None:
        """What the work-phase weekly note is missing, or None when it may
        post. The flow lives here, not in prose (p09 dojo: Gemini dodged the
        bet twice and denied a bet it closed minutes earlier)."""
        low = (body or "").lower()
        if "recovery first" in low:
            return None  # incident week — recovery and proposals never share a turn
        if not await self.has_live_bet(days=days):
            return (
                "the weekly note carries a bet — no proposal is open and none "
                "closed this week. Call proposal_open first (title + predicted "
                "payoff in owner units, e.g. 'saves you ~20 min/week'), then "
                "repost the note. Only an incident week skips the bet, and its "
                "Proposal line says 'no proposal this week — recovery first'."
            )
        async with self._sf() as s:
            q = (
                select(Proposal)
                .where(Proposal.status.in_(("done", "dropped")))
                .order_by(Proposal.closed_at.desc())
            )
            last = (await s.execute(q)).scalars().first()
        if last is not None and last.closed_at is not None:
            closed = last.closed_at
            if closed.tzinfo is None:
                closed = closed.replace(tzinfo=UTC)
            fresh = closed.timestamp() >= _utcnow().timestamp() - days * 86400
            if fresh and not ("predicted" in low and "actual" in low):
                return (
                    "a bet closed this week — the Proposal line LEADS with its "
                    f"verdict, quoted: \"{_verdict(last)}\". Add it and repost."
                )
        return None

    async def open(
        self,
        title: str,
        predicted: str,
        *,
        predicted_minutes: int | None = None,
        value_ref: str = "",
        source: str = "review",
    ) -> dict[str, Any]:
        title = (title or "").strip()
        predicted = (predicted or "").strip()
        if not title:
            raise ValueError("a proposal needs `title` — the one-line improvement")
        if not predicted:
            raise ValueError(
                "a proposal needs `predicted` — the expected payoff in the "
                "owner's units ('saves you ~20 min/week'), stated BEFORE the "
                "work. No prediction, no proposal."
            )
        async with self._sf() as s:
            m = await self._mission(s)
            if m is None:
                raise ValueError("no active mission — set a mission first")
            existing = await self._open(s)
            if existing is not None:
                if existing.title.strip().lower() == title.lower():
                    # convergent: same bet re-opened is the same bet
                    return {**_dict(existing), "note": "already open"}
                raise ValueError(
                    f"one proposal at a time — '{existing.title}' is still "
                    f"{existing.status}. Close it (proposal_close) or record "
                    "the owner's decision (proposal_decide) first; the weekly "
                    "note carries at most ONE open proposal."
                )
            ref_uuid: uuid.UUID | None = None
            if (value_ref or "").strip():
                try:
                    ref_uuid = uuid.UUID(str(value_ref))
                except ValueError:
                    raise ValueError(
                        f"value_ref {value_ref!r} is not a value-log id"
                    ) from None
                ref = await s.get(ValueEntry, ref_uuid)
                if ref is None or ref.mission_id != m.id:
                    raise ValueError(f"no value-log entry with id {value_ref}")
            p = Proposal(
                mission_id=m.id,
                title=title,
                predicted=predicted,
                predicted_minutes=(
                    max(0, int(predicted_minutes))
                    if predicted_minutes is not None
                    else None
                ),
                value_ref=ref_uuid,
                source=source or "review",
            )
            s.add(p)
            await s.commit()
            await s.refresh(p)
            return _dict(p)

    async def _resolve(self, s, proposal_id: str | None) -> Proposal:
        if proposal_id:
            try:
                key = uuid.UUID(str(proposal_id))
            except ValueError:
                raise ValueError(
                    f"proposal_id {proposal_id!r} is not a proposal id"
                ) from None
            p = await s.get(Proposal, key)
            if p is None:
                raise ValueError(f"no proposal with id {proposal_id}")
            return p
        p = await self._open(s)
        if p is None:
            raise ValueError(
                "no open proposal — open one first with proposal_open"
            )
        return p

    async def decide(
        self, proposal_id: str | None = None, *, decision: str = "accepted",
        note: str = "",
    ) -> dict[str, Any]:
        if decision not in ("accepted", "declined"):
            raise ValueError("decision must be 'accepted' or 'declined'")
        async with self._sf() as s:
            p = await self._resolve(s, proposal_id)
            if p.status == "declined":
                raise ValueError(
                    "this proposal was declined — a decline is final; propose "
                    "something better next week instead of re-litigating."
                )
            if p.status in ("done", "dropped"):
                raise ValueError(f"proposal is already closed ({p.status})")
            if p.status == "accepted" and decision == "accepted":
                return {**_dict(p), "note": "already accepted"}
            p.status = decision
            p.decision_note = (note or "").strip()
            p.decided_at = _utcnow()
            if decision == "declined":
                p.closed_at = p.decided_at
            await s.commit()
            await s.refresh(p)
            d = _dict(p)
            if decision == "accepted":
                d["next"] = (
                    "accepted — do the work, then proposal_close with `actual` "
                    "in the SAME units you predicted; the next weekly note "
                    "reports predicted vs actual."
                )
            return d

    async def close(
        self,
        proposal_id: str | None = None,
        *,
        outcome: str = "done",
        actual: str = "",
        actual_minutes: int | None = None,
        value_ref: str = "",
    ) -> dict[str, Any]:
        if outcome not in ("done", "dropped"):
            raise ValueError("outcome must be 'done' or 'dropped'")
        if not (actual or "").strip():
            raise ValueError(
                "closing needs `actual` — what actually happened, in the same "
                "owner units as the prediction ('saved ~25 min/week'), or why "
                "it was dropped. The prediction was public; the result is too."
            )
        async with self._sf() as s:
            p = await self._resolve(s, proposal_id)
            if p.status in ("declined", "done", "dropped"):
                raise ValueError(f"proposal is already closed ({p.status})")
            if p.status == "proposed" and outcome == "done":
                raise ValueError(
                    "this proposal has no decision yet — record the owner's "
                    "yes/no first (proposal_decide); only an ACCEPTED proposal "
                    "closes as done. Use outcome='dropped' to withdraw it."
                )
            ref_uuid: uuid.UUID | None = p.value_ref
            if (value_ref or "").strip():
                try:
                    ref_uuid = uuid.UUID(str(value_ref))
                except ValueError:
                    raise ValueError(
                        f"value_ref {value_ref!r} is not a value-log id"
                    ) from None
                ref = await s.get(ValueEntry, ref_uuid)
                if ref is None or ref.mission_id != p.mission_id:
                    raise ValueError(f"no value-log entry with id {value_ref}")
            p.status = outcome
            p.actual = actual.strip()
            p.actual_minutes = (
                max(0, int(actual_minutes)) if actual_minutes is not None else None
            )
            p.value_ref = ref_uuid
            p.closed_at = _utcnow()
            await s.commit()
            await s.refresh(p)
            d = _dict(p)
            d["verdict"] = _verdict(p)
            d["next"] = (
                "the next weekly note's Proposal line LEADS with this "
                "verdict, quoted verbatim."
            )
            return d

    async def list(
        self, *, limit: int = 20, mission_id: str | None = None
    ) -> dict[str, Any]:
        """Open proposal + recent history + the last closed bet with its
        server-computed calibration verdict (the weekly note reads this)."""
        async with self._sf() as s:
            q = select(Proposal)
            if mission_id is not None:
                try:
                    key = uuid.UUID(str(mission_id))
                except ValueError:
                    return {"open": None, "last_closed": None, "proposals": []}
                q = q.where(Proposal.mission_id == key)
            q = q.order_by(Proposal.created_at.desc()).limit(limit)
            rows_orm = (await s.execute(q)).scalars().all()
            rows = [_dict(p) for p in rows_orm]
            open_row = next((r for r in rows if r["status"] in OPEN_STATUSES), None)
            closed_rows = [
                p for p in rows_orm
                if p.status in ("done", "dropped", "declined")
            ]
            closed_rows.sort(
                key=lambda p: p.closed_at or p.created_at, reverse=True
            )
            last_closed = None
            if closed_rows:
                last_closed = _dict(closed_rows[0])
                last_closed["verdict"] = _verdict(closed_rows[0])
            return {
                "open": open_row,
                "last_closed": last_closed,
                "proposals": rows,
            }


def register_tools(ctx: PluginContext, store: ProposalStore) -> None:
    async def _open(
        title: str,
        predicted: str,
        predicted_minutes: int | None = None,
        value_ref: str = "",
    ) -> dict[str, Any]:
        try:
            p = await store.open(
                title,
                predicted,
                predicted_minutes=predicted_minutes,
                value_ref=value_ref,
            )
        except ValueError as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "proposal"})
        return p

    async def _decide(
        proposal_id: str = "", decision: str = "accepted", note: str = ""
    ) -> dict[str, Any]:
        try:
            p = await store.decide(proposal_id or None, decision=decision, note=note)
        except ValueError as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "proposal"})
        return p

    async def _close(
        proposal_id: str = "",
        outcome: str = "done",
        actual: str = "",
        actual_minutes: int | None = None,
        value_ref: str = "",
    ) -> dict[str, Any]:
        try:
            p = await store.close(
                proposal_id or None,
                outcome=outcome,
                actual=actual,
                actual_minutes=actual_minutes,
                value_ref=value_ref,
            )
        except ValueError as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "proposal"})
        return p

    async def _list(limit: int = 20) -> dict[str, Any]:
        return await store.list(limit=limit)

    defs: list[tuple[ToolDef, Any]] = [
        (
            ToolDef(
                name="proposal_open",
                description=(
                    "Open your ONE improvement micro-proposal (weekly review, "
                    "normally): title = the one-line improvement, predicted = "
                    "the expected payoff in the OWNER'S units ('saves you ~20 "
                    "min/week'), stated before any work. predicted_minutes = "
                    "the numeric half (per week) when you can put a number on "
                    "it — that is what makes your calibration scoreable. Only "
                    "one proposal may be open at a time; the tool refuses a "
                    "second and names the open one. A turn handling an "
                    "incident opens NO proposal."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "the one-line improvement",
                        },
                        "predicted": {
                            "type": "string",
                            "description": (
                                "expected payoff in owner units, e.g. 'saves "
                                "you ~20 min/week'"
                            ),
                        },
                        "predicted_minutes": {
                            "type": "integer",
                            "description": "numeric prediction (minutes/week), if you have one",
                        },
                        "value_ref": {
                            "type": "string",
                            "description": "value-log entry id this proposal builds on (optional)",
                        },
                    },
                    "required": ["title", "predicted"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _open,
        ),
        (
            ToolDef(
                name="proposal_decide",
                description=(
                    "Record the owner's decision on the open proposal: "
                    "decision='accepted' or 'declined', note = their words. "
                    "Call this ONLY when the owner actually said yes or no — "
                    "never decide for them. A decline is final; propose "
                    "something better next time instead. proposal_id may be "
                    "omitted: the open proposal is used."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "proposal_id": {
                            "type": "string",
                            "description": "proposal id (omit = the open proposal)",
                        },
                        "decision": {
                            "type": "string",
                            "enum": ["accepted", "declined"],
                            "description": "what the owner said",
                        },
                        "note": {
                            "type": "string",
                            "description": "the owner's words",
                        },
                    },
                    "required": ["decision"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _decide,
        ),
        (
            ToolDef(
                name="proposal_close",
                description=(
                    "Close the accepted proposal when its work lands: actual "
                    "= what actually happened, in the SAME owner units as the "
                    "prediction ('saved ~25 min/week') — REQUIRED; "
                    "actual_minutes = the numeric half when the prediction "
                    "had one. outcome='dropped' withdraws a proposal that "
                    "didn't pan out (actual then says why). The next weekly "
                    "note reports predicted vs actual verbatim."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "proposal_id": {
                            "type": "string",
                            "description": "proposal id (omit = the open proposal)",
                        },
                        "outcome": {
                            "type": "string",
                            "enum": ["done", "dropped"],
                            "description": "how it ended",
                        },
                        "actual": {
                            "type": "string",
                            "description": (
                                "what actually happened, same units as "
                                "predicted — required"
                            ),
                        },
                        "actual_minutes": {
                            "type": "integer",
                            "description": "numeric actual (minutes/week), if measurable",
                        },
                        "value_ref": {
                            "type": "string",
                            "description": "value-log receipt the work produced (optional)",
                        },
                    },
                    "required": ["actual"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _close,
        ),
        (
            ToolDef(
                name="proposal_list",
                description=(
                    "Your proposal ledger: the open proposal (if any), the "
                    "last closed one with its predicted-vs-actual verdict "
                    "(read this before writing the weekly note — when a bet "
                    "closed this week, the note's Proposal line quotes "
                    "last_closed.verdict verbatim), and recent history."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "max rows (default 20)"},
                    },
                    "required": [],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _list,
        ),
    ]
    for tool_def, handler in defs:
        ctx.tool_registry.register("plugin-curiosity", tool_def, handler)
