"""loops.py — the open-loops ledger + ask economics + value log (phase 9B).

The durability engine: every question asked, promise made, thing waited on,
handoff, and ask becomes a loop row with a nudge schedule — nothing silently
dies. Asks are the scarce resource: at most ONE open at a time, and each must
ride on fresh delivered value (the talented-hire law, structurally enforced —
`loop_open` rejects a second concurrent ask and an ask with no value-log
entry newer than the last closed ask; the error text steers the model
mid-turn).

Nudge ladder: +2d at open, +5d on the first nudge, weekly after — patient,
not naggy. Pure function over `now` so it is testable without time mocking.

Mirrors: [[open-loops]] (open + recently closed, with waiting-since and nudge
count) and [[value-log]] (receipts, newest first) — rebuilt on every mutation,
same write-through pattern as goals/scopes.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from luna_sdk import PluginContext, ToolDef

from .models import Loop, Mission, ValueEntry

log = logging.getLogger("plugin-curiosity")

LOOP_KINDS = ("question", "promise", "waiting_on", "handoff", "ask")
LOOP_STATUSES = ("open", "answered", "closed", "abandoned")

LOOPS_SLUG = "open-loops"
VALUE_SLUG = "value-log"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def next_nudge(now: datetime, nudge_count: int) -> datetime:
    """The nudge ladder as a pure function: at open (count 0) → +2d; after the
    first nudge (count 1) → +5d; weekly from then on."""
    if nudge_count <= 0:
        return now + timedelta(days=2)
    if nudge_count == 1:
        return now + timedelta(days=5)
    return now + timedelta(days=7)


def _loop_dict(lp: Loop) -> dict[str, Any]:
    return {
        "id": str(lp.id),
        "kind": lp.kind,
        "statement": lp.statement,
        "who": lp.who,
        "status": lp.status,
        "resolution": lp.resolution,
        "unlock": lp.unlock,
        "human_cost": lp.human_cost,
        "value_ref": str(lp.value_ref) if lp.value_ref else None,
        "opened_at": lp.opened_at.isoformat() if lp.opened_at else None,
        "next_nudge_at": lp.next_nudge_at.isoformat() if lp.next_nudge_at else None,
        "nudge_count": lp.nudge_count,
        "closed_at": lp.closed_at.isoformat() if lp.closed_at else None,
    }


def _value_dict(v: ValueEntry) -> dict[str, Any]:
    return {
        "id": str(v.id),
        "statement": v.statement,
        "evidence": v.evidence,
        "linked_ask_id": str(v.linked_ask_id) if v.linked_ask_id else None,
        "delivered_at": v.delivered_at.isoformat() if v.delivered_at else None,
    }


class LoopStore:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    async def _mission(self, s) -> Mission | None:
        q = (
            select(Mission)
            .where(Mission.active.is_(True))
            .order_by(Mission.created_at.desc())
        )
        return (await s.execute(q)).scalars().first()

    async def open(
        self,
        kind: str,
        statement: str,
        *,
        who: str = "owner",
        unlock: str = "",
        human_cost: str = "",
        value_ref: str = "",
    ) -> dict[str, Any]:
        if kind not in LOOP_KINDS:
            raise ValueError(f"kind must be one of {LOOP_KINDS}")
        statement = (statement or "").strip()
        if not statement:
            raise ValueError("loop statement must be non-empty")
        async with self._sf() as s:
            m = await self._mission(s)
            if m is None:
                raise ValueError("no active mission — set a mission first")
            ref_uuid: uuid.UUID | None = None
            if kind == "ask":
                # the law's teeth — errors steer the model mid-turn
                q = select(Loop).where(
                    Loop.mission_id == m.id, Loop.kind == "ask", Loop.status == "open"
                )
                open_ask = (await s.execute(q)).scalars().first()
                if open_ask is not None:
                    raise ValueError(
                        f"One ask at a time — close loop {open_ask.id} first "
                        f"(open ask: '{open_ask.statement[:80]}'). The I-need "
                        "slot is single."
                    )
                if not unlock.strip():
                    raise ValueError(
                        "an ask needs `unlock` — say what the grant lets you "
                        "additionally do"
                    )
                if not value_ref.strip():
                    raise ValueError(
                        "an ask needs `value_ref` — the value-log entry it "
                        "rides on (deliver value first, then ask; "
                        "value_log_add the win and reference it)"
                    )
                try:
                    ref_uuid = uuid.UUID(str(value_ref))
                except ValueError:
                    raise ValueError(f"value_ref {value_ref!r} is not a value-log id") from None
                ref = await s.get(ValueEntry, ref_uuid)
                if ref is None or ref.mission_id != m.id:
                    raise ValueError(f"no value-log entry with id {value_ref}")
                # fresh value: newer than the last CLOSED ask
                q = (
                    select(Loop.closed_at)
                    .where(
                        Loop.mission_id == m.id,
                        Loop.kind == "ask",
                        Loop.closed_at.is_not(None),
                    )
                    .order_by(Loop.closed_at.desc())
                )
                last_closed = (await s.execute(q)).scalars().first()
                if last_closed is not None and ref.delivered_at <= last_closed:
                    raise ValueError(
                        "Deliver value first, then ask — the referenced value "
                        "predates your last ask. Log a fresh win with "
                        "value_log_add and ride it."
                    )
            now = _utcnow()
            lp = Loop(
                mission_id=m.id,
                kind=kind,
                statement=statement,
                who=(who or "owner").strip() or "owner",
                unlock=unlock.strip(),
                human_cost=human_cost.strip(),
                value_ref=ref_uuid,
                next_nudge_at=next_nudge(now, 0),
            )
            s.add(lp)
            await s.commit()
            return _loop_dict(lp)

    async def close(self, loop_id: str, status: str, resolution: str = "") -> dict[str, Any]:
        if status not in ("answered", "closed", "abandoned"):
            raise ValueError("status must be one of ('answered', 'closed', 'abandoned')")
        resolution = (resolution or "").strip()
        if status == "abandoned" and not resolution:
            raise ValueError(
                "abandoning a loop REQUIRES a resolution — the stated reason "
                "the owner sees; loops never just vanish"
            )
        try:
            key = uuid.UUID(str(loop_id))
        except ValueError:
            raise LookupError(f"no loop with id {loop_id}") from None
        async with self._sf() as s:
            lp = await s.get(Loop, key)
            if lp is None:
                raise LookupError(f"no loop with id {loop_id}")
            lp.status = status
            lp.resolution = resolution
            lp.closed_at = _utcnow()
            lp.next_nudge_at = None
            await s.commit()
            return _loop_dict(lp)

    async def nudge(self, loop_id: str) -> dict[str, Any]:
        """Record one nudge: increments the count and advances next_nudge_at
        up the ladder."""
        try:
            key = uuid.UUID(str(loop_id))
        except ValueError:
            raise LookupError(f"no loop with id {loop_id}") from None
        async with self._sf() as s:
            lp = await s.get(Loop, key)
            if lp is None:
                raise LookupError(f"no loop with id {loop_id}")
            if lp.status != "open":
                raise ValueError("only open loops can be nudged")
            lp.nudge_count += 1
            lp.next_nudge_at = next_nudge(_utcnow(), lp.nudge_count)
            await s.commit()
            return _loop_dict(lp)

    async def list(self, *, status: str | None = None) -> list[dict[str, Any]]:
        async with self._sf() as s:
            m = await self._mission(s)
            if m is None:
                return []
            q = select(Loop).where(Loop.mission_id == m.id).order_by(Loop.opened_at)
            if status is not None:
                if status not in LOOP_STATUSES:
                    raise ValueError(f"status must be one of {LOOP_STATUSES}")
                q = q.where(Loop.status == status)
            rows = (await s.execute(q)).scalars().all()
            return [_loop_dict(lp) for lp in rows]

    async def value_add(
        self, statement: str, evidence: str, *, linked_ask_id: str = ""
    ) -> dict[str, Any]:
        statement = (statement or "").strip()
        evidence = (evidence or "").strip()
        if not statement:
            raise ValueError("value statement must be non-empty")
        if not evidence:
            raise ValueError(
                "value needs evidence — a wiki page ([[slug]]) or artifact "
                "link the owner can check"
            )
        async with self._sf() as s:
            m = await self._mission(s)
            if m is None:
                raise ValueError("no active mission — set a mission first")
            ask_uuid: uuid.UUID | None = None
            if linked_ask_id.strip():
                try:
                    ask_uuid = uuid.UUID(str(linked_ask_id))
                except ValueError:
                    raise ValueError(f"linked_ask_id {linked_ask_id!r} is not a loop id") from None
            v = ValueEntry(
                mission_id=m.id, statement=statement, evidence=evidence,
                linked_ask_id=ask_uuid,
            )
            s.add(v)
            await s.commit()
            return _value_dict(v)

    async def value_list(self) -> list[dict[str, Any]]:
        async with self._sf() as s:
            m = await self._mission(s)
            if m is None:
                return []
            q = (
                select(ValueEntry)
                .where(ValueEntry.mission_id == m.id)
                .order_by(ValueEntry.delivered_at.desc())
            )
            rows = (await s.execute(q)).scalars().all()
            return [_value_dict(v) for v in rows]


_KIND_MARK = {
    "question": "❓", "promise": "🤝", "waiting_on": "⏳", "handoff": "📤", "ask": "🙏",
}


def render_loops_page(loops: list[dict[str, Any]]) -> str:
    """[[open-loops]] body: open loops with waiting-since + nudge count, then
    recently closed ones with their resolutions."""
    open_ = [lp for lp in loops if lp["status"] == "open"]
    closed = [lp for lp in loops if lp["status"] != "open"]
    lines: list[str] = []
    if not open_:
        lines.append("*No open loops — every thread is resolved.*")
    else:
        lines.append("Threads I am keeping alive (nothing dies silently):")
        lines.append("")
        for lp in open_:
            mark = _KIND_MARK.get(lp["kind"], "•")
            since = (lp["opened_at"] or "")[:10]
            head = f"- {mark} **{lp['statement']}** — {lp['kind']}, {lp['who']}, open since {since}"
            if lp["nudge_count"]:
                head += f", nudged {lp['nudge_count']}×"
            lines.append(head)
            if lp["kind"] == "ask" and lp["unlock"]:
                lines.append(f"  - unlocks: {lp['unlock']}")
    if closed:
        lines += ["", "## Recently closed"]
        for lp in closed[-10:]:
            res = f" — {lp['resolution']}" if lp["resolution"] else ""
            lines.append(f"- {lp['statement']} ({lp['status']}{res})")
    lines.append("")
    return "\n".join(lines)


def render_value_page(entries: list[dict[str, Any]]) -> str:
    """[[value-log]] body: receipts, newest first, evidence verbatim."""
    if not entries:
        return (
            "*No value logged yet — deliver something useful with the tools "
            "you already have, then record it here (value_log_add). Asks ride "
            "on these receipts.*\n"
        )
    lines = ["Value I have delivered, newest first (asks ride on these):", ""]
    for v in entries:
        date = (v["delivered_at"] or "")[:10]
        lines.append(f"- {date}: **{v['statement']}** — evidence: {v['evidence']}")
    lines.append("")
    return "\n".join(lines)


async def _mirror_to_wiki(ctx: PluginContext, store: LoopStore) -> str:
    from . import wikibind

    try:
        wiki = ctx.provider_registry.get("wiki")
    except Exception:  # noqa: BLE001
        return "wiki provider unavailable — loop pages not mirrored"
    try:
        wk = await wikibind.wiki_kwargs(ctx, store._sf)  # noqa: SLF001
        loops = await store.list()
        open_count = sum(1 for lp in loops if lp["status"] == "open")
        await wiki.upsert_page(
            LOOPS_SLUG, "Open Loops", render_loops_page(loops),
            summary=f"{open_count} open loop(s)", note="loop ledger write-through",
            **wk,
        )
        values = await store.value_list()
        await wiki.upsert_page(
            VALUE_SLUG, "Value Log", render_value_page(values),
            summary=f"{len(values)} receipt(s)", note="value log write-through",
            **wk,
        )
        return "ok"
    except Exception as e:  # noqa: BLE001
        log.warning("loop wiki mirror failed", exc_info=True)
        return f"wiki mirror failed: {e}"


async def ensure_loop_mirrors(ctx: PluginContext, store: LoopStore) -> str:
    """Upgrade path (on-load): a pre-9B mission gets [[open-loops]] and
    [[value-log]] seeded once when absent."""
    from . import wikibind

    async with store._sf() as s:  # noqa: SLF001
        if await store._mission(s) is None:  # noqa: SLF001
            return "no mission"
    try:
        wiki = ctx.provider_registry.get("wiki")
        wk = await wikibind.wiki_kwargs(ctx, store._sf)  # noqa: SLF001
        if (
            await wiki.get_page(LOOPS_SLUG, **wk) is not None
            and await wiki.get_page(VALUE_SLUG, **wk) is not None
        ):
            return "already present"
    except Exception:  # noqa: BLE001
        return "wiki provider unavailable"
    return await _mirror_to_wiki(ctx, store)


def register_tools(ctx: PluginContext, store: LoopStore) -> None:
    from . import telemetry

    async def _open(
        kind: str, statement: str, who: str = "owner",
        unlock: str = "", human_cost: str = "", value_ref: str = "",
    ) -> dict[str, Any]:
        try:
            loop = await store.open(
                kind, statement, who=who, unlock=unlock,
                human_cost=human_cost, value_ref=value_ref,
            )
        except ValueError as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "loop"})
        return {"loop": loop, "wiki_mirror": await _mirror_to_wiki(ctx, store)}

    async def _close(id: str, status: str, resolution: str = "") -> dict[str, Any]:
        try:
            loop = await store.close(id, status, resolution)
        except (ValueError, LookupError) as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "loop"})
        return {"loop": loop, "wiki_mirror": await _mirror_to_wiki(ctx, store)}

    async def _nudge(id: str) -> dict[str, Any]:
        try:
            loop = await store.nudge(id)
        except (ValueError, LookupError) as e:
            return {"error": str(e)}
        return {"loop": loop, "wiki_mirror": await _mirror_to_wiki(ctx, store)}

    async def _list(status: str | None = None) -> dict[str, Any]:
        try:
            loops = await store.list(status=status)
        except ValueError as e:
            return {"error": str(e)}
        if not loops:
            return {
                "loops": [],
                "note": (
                    "no loops recorded — every question you ask, promise you "
                    "make, and thing you wait on should be opened as a loop "
                    "(loop_open) so it never silently dies"
                ),
            }
        return {"loops": loops}

    async def _value_add(
        statement: str, evidence: str, linked_ask_id: str = ""
    ) -> dict[str, Any]:
        try:
            entry = await store.value_add(statement, evidence, linked_ask_id=linked_ask_id)
        except ValueError as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "value"})
        return {"value": entry, "wiki_mirror": await _mirror_to_wiki(ctx, store)}

    defs: list[tuple[ToolDef, Any]] = [
        (
            ToolDef(
                name="loop_open",
                description=(
                    "Open a loop for anything that must not silently die: a "
                    "question you asked (kind=question), a promise you made "
                    "(promise), something you await (waiting_on), a handoff "
                    "(handoff), or an ask of the owner (ask). Asks are "
                    "scarce: ONE open at a time, and each must reference "
                    "fresh delivered value (value_ref from value_log_add) "
                    "plus the `unlock` it buys. Mirrors to [[open-loops]]."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": list(LOOP_KINDS)},
                        "statement": {
                            "type": "string",
                            "description": "The thread — what was asked/promised/awaited.",
                        },
                        "who": {
                            "type": "string",
                            "description": "Who it involves: 'owner', 'self', or a person's name.",
                        },
                        "unlock": {
                            "type": "string",
                            "description": "(asks) What the grant lets you additionally do.",
                        },
                        "human_cost": {
                            "type": "string",
                            "description": "(asks) What it costs the owner — minutes, a click, an intro.",
                        },
                        "value_ref": {
                            "type": "string",
                            "description": "(asks) The value-log entry id this ask rides on.",
                        },
                    },
                    "required": ["kind", "statement"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _open,
        ),
        (
            ToolDef(
                name="loop_close",
                description=(
                    "Close a loop: answered (you got the answer/grant), closed "
                    "(done/no longer relevant with a reason), or abandoned "
                    "(REQUIRES a resolution — the reason the owner sees). "
                    "Never let a loop just vanish."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "The loop id (from loop_list)."},
                        "status": {
                            "type": "string",
                            "enum": ["answered", "closed", "abandoned"],
                        },
                        "resolution": {
                            "type": "string",
                            "description": "How it resolved — required for abandoned.",
                        },
                    },
                    "required": ["id", "status"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _close,
        ),
        (
            ToolDef(
                name="loop_nudge",
                description=(
                    "Record that you re-raised an open loop (rephrased, named "
                    "the blocked goal). Advances its nudge schedule up the "
                    "ladder (+2d → +5d → weekly) so patrols stay patient, "
                    "not naggy."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "The loop id."},
                    },
                    "required": ["id"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _nudge,
        ),
        (
            ToolDef(
                name="loop_list",
                description=(
                    "Your open-loops ledger — every live thread with kind, "
                    "who, waiting-since, and nudge schedule. Patrol it at the "
                    "start of every daily pass: act on anything past its "
                    "next_nudge_at BEFORE new research."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": list(LOOP_STATUSES),
                            "description": "Filter by status (default: all).",
                        },
                    },
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _list,
        ),
        (
            ToolDef(
                name="value_log_add",
                description=(
                    "Record value you actually delivered to the owner, with "
                    "evidence they can check (a [[wiki-page]] or artifact "
                    "link). These receipts are what asks ride on — deliver "
                    "first, log it, then ask. Mirrors to [[value-log]]."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "statement": {
                            "type": "string",
                            "description": "The win, in the owner's terms.",
                        },
                        "evidence": {
                            "type": "string",
                            "description": "Where they can see it — [[wiki-page]] or link.",
                        },
                        "linked_ask_id": {
                            "type": "string",
                            "description": "If this win used a granted ask, that ask's loop id (grant → payoff).",
                        },
                    },
                    "required": ["statement", "evidence"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _value_add,
        ),
    ]
    for tool_def, handler in defs:
        ctx.tool_registry.register("plugin-curiosity", tool_def, handler)
