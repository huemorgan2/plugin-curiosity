"""next_steps.py — next-step cards (11.002/M2): no spend the owner couldn't
have seen coming.

Every self-directed run opens with a card — what, why, what it produces, what
it costs — BEFORE the spend. The autonomy rung decides the card's teeth:

* rung 1-2 → **proposed**: the owner holds a veto window (VETO_WINDOW_H of
  WAKING time — quiet hours pause the clock) before `next_step_start` will
  let the work begin. Silence past the deadline = proceed by default, said
  plainly (the same no-guilt shape as the confirm gate's timeout note).
* rung 3+ → **announced**: the card posts and the work starts immediately.
* a scheduled routine fire (daily research, heartbeat, weekly review) posts
  with `scheduled=true` → announced regardless of rung: the schedule itself
  is owner-visible on the pane ("next_up"), so the spend was foreseeable —
  the card is the transparency record of what THIS fire does. Anything a
  routine invents BEYOND its standing scope takes the normal proposed path.

A redirect ("owner said no / do it differently") closes the card with
`outcome='redirected'` and a REQUIRED `plan_change_note` — the silent-retry
loop (post the same step again as if nothing happened) is the failure mode
this module exists to kill, and the handlers refuse it with steering errors
(flows belong in the tool layer, not in prose).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from luna_sdk import PluginContext, ToolDef
from sqlalchemy import select

from . import telemetry
from .comms import QUIET_END_HOUR, QUIET_START_HOUR
from .models import Mission, NextStep, ValueEntry

log = logging.getLogger("plugin-curiosity")

STEP_STATUSES = ("proposed", "announced", "running", "done", "redirected")

# rung >= ANNOUNCE_RUNG posts announced (no veto wait); below it, proposed
ANNOUNCE_RUNG = 3

# the owner's redirect window, in WAKING hours (quiet hours pause the clock)
VETO_WINDOW_H = 2.0


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _now_local() -> datetime:
    return datetime.now(UTC).astimezone()


def card_mode(rung: int) -> str:
    """The rung → card-status mapping (rung 1-2 proposed, 3+ announced)."""
    return "announced" if rung >= ANNOUNCE_RUNG else "proposed"


def _quiet_state(t: datetime) -> tuple[bool, datetime]:
    """(in quiet hours?, next boundary) for the tz-aware local time `t` —
    same hour bounds as comms (21:00–08:00 local)."""
    if t.hour >= QUIET_START_HOUR:
        nxt = (t + timedelta(days=1)).replace(
            hour=QUIET_END_HOUR, minute=0, second=0, microsecond=0
        )
        return True, nxt
    if t.hour < QUIET_END_HOUR:
        return True, t.replace(hour=QUIET_END_HOUR, minute=0, second=0, microsecond=0)
    return False, t.replace(hour=QUIET_START_HOUR, minute=0, second=0, microsecond=0)


def veto_deadline(now: datetime, window_h: float = VETO_WINDOW_H) -> datetime:
    """`now` + `window_h` of WAKING time: the veto clock pauses through quiet
    hours (a card posted at 20:30 doesn't time out while the owner sleeps).
    Pure — takes a tz-aware local datetime, returns one."""
    remaining = timedelta(hours=window_h)
    t = now
    for _ in range(8):  # a 2 h window never spans more than a few boundaries
        in_quiet, boundary = _quiet_state(t)
        if in_quiet:
            t = boundary
            continue
        if boundary - t >= remaining:
            return t + remaining
        remaining -= boundary - t
        t = boundary
    return t + remaining


def _step_dict(st: NextStep) -> dict[str, Any]:
    return {
        "id": str(st.id),
        "what": st.what,
        "why": st.why,
        "produces": st.produces,
        "cost_text": st.cost_text,
        "status": st.status,
        "wait_until": st.wait_until.isoformat() if st.wait_until else None,
        "value_ref": str(st.value_ref) if st.value_ref else None,
        "plan_change_note": st.plan_change_note,
        "source": st.source,
        "created_at": st.created_at.isoformat() if st.created_at else None,
        "started_at": st.started_at.isoformat() if st.started_at else None,
        "finished_at": st.finished_at.isoformat() if st.finished_at else None,
    }


class NextStepStore:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    async def _mission(self, s) -> Mission | None:
        q = (
            select(Mission)
            .where(Mission.active.is_(True))
            .order_by(Mission.created_at.desc())
        )
        return (await s.execute(q)).scalars().first()

    async def post(
        self,
        what: str,
        *,
        why: str = "",
        produces: str = "",
        cost_text: str = "",
        source: str = "agent",
        scheduled: bool = False,
        retro: bool = False,
    ) -> dict[str, Any]:
        what = (what or "").strip()
        if not what:
            raise ValueError("a next-step card needs `what` — the one-line action")
        async with self._sf() as s:
            m = await self._mission(s)
            if m is None:
                raise ValueError("no active mission — set a mission first")
            now = _utcnow()
            if retro:
                status, wait_until, finished = "done", None, now
            elif scheduled:
                # the schedule is owner-visible on the pane — the spend was
                # foreseeable; the card records what this fire does
                status, wait_until, finished = "announced", None, None
            else:
                status = card_mode(m.autonomy_rung or 1)
                wait_until = (
                    veto_deadline(_now_local()).astimezone(UTC)
                    if status == "proposed"
                    else None
                )
                finished = None
            st = NextStep(
                mission_id=m.id,
                what=what,
                why=(why or "").strip(),
                produces=(produces or "").strip(),
                cost_text=(cost_text or "").strip(),
                status=status,
                wait_until=wait_until,
                source=source or "agent",
                finished_at=finished,
            )
            s.add(st)
            await s.commit()
            await s.refresh(st)
            return _step_dict(st)

    async def _open_step(self, s, step_id: str | None) -> NextStep:
        """Resolve a card by id, or the newest still-open one when the id is
        omitted (LLM ergonomics: 'close your card' shouldn't need bookkeeping)."""
        if step_id:
            try:
                key = uuid.UUID(str(step_id))
            except ValueError:
                raise ValueError(f"step_id {step_id!r} is not a card id") from None
            st = await s.get(NextStep, key)
            if st is None:
                raise ValueError(f"no next-step card with id {step_id}")
            return st
        q = (
            select(NextStep)
            .where(NextStep.status.in_(("proposed", "announced", "running")))
            .order_by(NextStep.created_at.desc())
        )
        st = (await s.execute(q)).scalars().first()
        if st is None:
            raise ValueError(
                "no open next-step card — post one first with next_step_post"
            )
        return st

    async def start(
        self, step_id: str | None = None, *, owner_ok: bool = False
    ) -> dict[str, Any]:
        async with self._sf() as s:
            st = await self._open_step(s, step_id)
            if st.status == "running":
                return {**_step_dict(st), "note": "already running"}
            if st.status in ("done", "redirected"):
                raise ValueError(
                    f"card is already {st.status} — post a NEW card for new work"
                )
            now = _utcnow()
            timed_out = False
            if st.status == "proposed" and not owner_ok:
                # SQLite hands DateTime(timezone=True) back naive — normalize
                # before comparing against the aware clock.
                wu = st.wait_until
                if wu is not None and wu.tzinfo is None:
                    wu = wu.replace(tzinfo=UTC)
                if wu is not None and now < wu:
                    raise ValueError(
                        "veto window open until "
                        f"{wu.isoformat()} — the owner has until then "
                        "to redirect this step. Do free prep only; call "
                        "next_step_start after that time, or pass owner_ok=true "
                        "ONLY if the owner explicitly approved in chat."
                    )
                timed_out = st.wait_until is not None
            st.status = "running"
            st.started_at = now
            await s.commit()
            await s.refresh(st)
            d = _step_dict(st)
            if timed_out:
                d["note"] = (
                    "the veto window passed with no reply — proceeding by "
                    "default. If you message the owner, say so plainly in one "
                    "line, no guilt, and invite them to redirect any time."
                )
            return d

    async def done(
        self,
        step_id: str | None = None,
        *,
        outcome: str = "done",
        value_ref: str = "",
        plan_change_note: str = "",
    ) -> dict[str, Any]:
        if outcome not in ("done", "redirected"):
            raise ValueError("outcome must be 'done' or 'redirected'")
        async with self._sf() as s:
            st = await self._open_step(s, step_id)
            if st.status in ("done", "redirected"):
                raise ValueError(f"card is already {st.status}")
            if outcome == "redirected" and not (plan_change_note or "").strip():
                raise ValueError(
                    "a redirect needs `plan_change_note` — what the owner said "
                    "and how the plan changes. NEVER silently retry the same "
                    "step; the note is what makes the change visible."
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
                if ref is None or ref.mission_id != st.mission_id:
                    raise ValueError(f"no value-log entry with id {value_ref}")
            st.status = outcome
            st.value_ref = ref_uuid
            st.plan_change_note = (plan_change_note or "").strip()
            st.finished_at = _utcnow()
            await s.commit()
            await s.refresh(st)
            return _step_dict(st)

    async def list(self, limit: int = 20) -> list[dict[str, Any]]:
        async with self._sf() as s:
            q = select(NextStep).order_by(NextStep.created_at.desc()).limit(limit)
            return [_step_dict(st) for st in (await s.execute(q)).scalars().all()]

    async def current(self) -> dict[str, Any] | None:
        """The newest still-open card — what the owner's pane shows."""
        async with self._sf() as s:
            q = (
                select(NextStep)
                .where(NextStep.status.in_(("proposed", "announced", "running")))
                .order_by(NextStep.created_at.desc())
            )
            st = (await s.execute(q)).scalars().first()
            return _step_dict(st) if st else None


async def record_scheduled_step(
    sf,
    what: str,
    *,
    why: str = "",
    produces: str = "",
    cost_text: str = "",
    source: str = "kickoff",
) -> dict[str, Any] | None:
    """Plugin-side card for a run the plugin itself spawns (the deep kickoff):
    announced + running in one write, best-effort — a card failure must never
    block the run it describes."""
    try:
        store = NextStepStore(sf)
        card = await store.post(
            what,
            why=why,
            produces=produces,
            cost_text=cost_text,
            source=source,
            scheduled=True,
        )
        return await store.start(card["id"])
    except Exception:  # noqa: BLE001 — advisory record, never fatal
        log.warning("scheduled next-step card failed", exc_info=True)
        return None


def register_tools(ctx: PluginContext, store: NextStepStore) -> None:
    async def _post(
        what: str,
        why: str = "",
        produces: str = "",
        cost_text: str = "",
        scheduled: bool = False,
        retro: bool = False,
    ) -> dict[str, Any]:
        try:
            card = await store.post(
                what,
                why=why,
                produces=produces,
                cost_text=cost_text,
                scheduled=scheduled,
                retro=retro,
            )
        except ValueError as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "next_step"})
        if card["status"] == "proposed":
            card["next"] = (
                "card is up — the owner can redirect until "
                f"{card['wait_until']}. Do FREE prep only (reading, drafting "
                "notes); call next_step_start after that time — a later turn "
                "picking this up starts immediately."
            )
        elif card["status"] == "announced":
            card["next"] = "announced — call next_step_start and begin now."
        return card

    async def _start(step_id: str = "", owner_ok: bool = False) -> dict[str, Any]:
        try:
            step = await store.start(step_id or None, owner_ok=owner_ok)
        except ValueError as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "next_step"})
        return step

    async def _done(
        step_id: str = "",
        outcome: str = "done",
        value_ref: str = "",
        plan_change_note: str = "",
    ) -> dict[str, Any]:
        try:
            step = await store.done(
                step_id or None,
                outcome=outcome,
                value_ref=value_ref,
                plan_change_note=plan_change_note,
            )
        except ValueError as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "next_step"})
        return step

    defs: list[tuple[ToolDef, Any]] = [
        (
            ToolDef(
                name="next_step_post",
                description=(
                    "Post your next-step card BEFORE any self-directed work "
                    "that costs real time or resources: what (one-line "
                    "action), why (why now), produces (what the owner gets), "
                    "cost_text (what it costs, plain words). At autonomy "
                    "rung 1-2 it posts as PROPOSED — the owner has a ~2 "
                    "waking-hour veto window before you may start; at rung "
                    "3+ it is ANNOUNCED and you start immediately. Pass "
                    "scheduled=true ONLY inside a scheduler-fired routine "
                    "doing its normal work (the owner already sees the "
                    "schedule). retro=true records finished work after the "
                    "fact (nightly dream only)."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "what": {
                            "type": "string",
                            "description": "the one-line action you are about to take",
                        },
                        "why": {"type": "string", "description": "why now"},
                        "produces": {
                            "type": "string",
                            "description": "what the owner gets out of it",
                        },
                        "cost_text": {
                            "type": "string",
                            "description": "what it costs (time, calls, money), plain words",
                        },
                        "scheduled": {
                            "type": "boolean",
                            "description": (
                                "true only inside a scheduler-fired routine's "
                                "normal work — posts announced regardless of rung"
                            ),
                        },
                        "retro": {
                            "type": "boolean",
                            "description": "record already-finished work (dream consolidation)",
                        },
                    },
                    "required": ["what"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _post,
        ),
        (
            ToolDef(
                name="next_step_start",
                description=(
                    "Start the work a card describes. A PROPOSED card refuses "
                    "until its veto window passes — the error tells you until "
                    "when; pass owner_ok=true ONLY when the owner explicitly "
                    "approved in chat. step_id may be omitted: the newest "
                    "open card is used."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "step_id": {
                            "type": "string",
                            "description": "card id from next_step_post (omit = newest open card)",
                        },
                        "owner_ok": {
                            "type": "boolean",
                            "description": "the owner explicitly approved this step in chat",
                        },
                    },
                    "required": [],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _start,
        ),
        (
            ToolDef(
                name="next_step_done",
                description=(
                    "Close a card when its work lands. outcome='done' links "
                    "the value-log receipt via value_ref (value_log_add "
                    "first, then reference it). outcome='redirected' is for "
                    "when the owner said no or changed direction — "
                    "plan_change_note is REQUIRED (their words + the new "
                    "plan), then post a NEW card for the changed plan; never "
                    "silently retry the same step. step_id may be omitted: "
                    "the newest open card is used."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "step_id": {
                            "type": "string",
                            "description": "card id (omit = newest open card)",
                        },
                        "outcome": {
                            "type": "string",
                            "enum": ["done", "redirected"],
                            "description": "how the step ended",
                        },
                        "value_ref": {
                            "type": "string",
                            "description": "value-log entry id the work produced (if any)",
                        },
                        "plan_change_note": {
                            "type": "string",
                            "description": (
                                "REQUIRED on redirect: what the owner said and "
                                "how the plan changes"
                            ),
                        },
                    },
                    "required": [],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _done,
        ),
    ]
    for tool_def, handler in defs:
        ctx.tool_registry.register("plugin-curiosity", tool_def, handler)
