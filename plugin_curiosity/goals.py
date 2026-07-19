"""goals.py — the goal ledger: Luna's own commitments toward the mission.

Phase 8.2 mechanism A. A mission alone reads as a topic; goals make the
pursuit visible and scoreable. Luna sets 2-3 goals at kickoff (goal_set),
reports movement after each daily pass (goal_update), and the weekly review
scores the ledger honestly — done / moved / stalled — and confronts stalls.

Write-through: every change rebuilds the human-readable [[mission-goals]]
wiki page (best-effort — a missing wiki degrades the payload note, never the
write). The DB row is the source of truth; the page is the owner's mirror.

0.10.0 — the goal-engine handover. When plugin-goalseek is installed
(engine.resolve_goal_engine == "goalseek"), mission goals live in ITS
governed engine instead of this ledger:

- ``goal_set`` delegates the open to goal-seek and keeps a POINTER row here
  (goalseek_id) — the mission-membership set that scopes every curiosity
  read to mission goals on a shared board.
- ``goal_update`` / ``goal_list`` are registered as deferential fallbacks
  (``yields_to="plugin-goalseek"``): with goal-seek installed, ITS richer
  tools serve those names; standalone, ours do — same names, either way.
- Reads (pane, mirror, review) route through :func:`list_mission_goals`,
  which maps goal-seek's dicts into this ledger's shape.

All three tools are auto_approve: goals are Luna's own commitments, not side
effects on the world. (A DELEGATED open is still governed — goal-seek's own
approval/grant flow applies to agent-opened goals.)
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from luna_sdk import PluginContext, ToolDef

from . import engine
from .models import Goal

log = logging.getLogger("plugin-curiosity")

GOAL_STATUSES = ("active", "done", "stalled", "dropped")
# phase 10 readiness: does the agent HAVE what this goal needs? green = yes,
# amber = partly, red = something is missing. readiness_note says what, in
# have/missing terms the owner can act on.
GOAL_READINESS = ("green", "amber", "red")


def _goal_dict(g: Goal) -> dict[str, Any]:
    out = {
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
    if getattr(g, "goalseek_id", ""):
        out["goalseek_id"] = g.goalseek_id
    return out


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

    # -- 0.10.0 pointer plumbing (goal-engine handover) ----------------------

    async def add_pointer(
        self,
        goalseek_id: str,
        *,
        statement: str,
        why: str = "",
        target_date: str = "",
        expected_result: str = "",
    ) -> dict[str, Any]:
        """A pointer row for a goal that LIVES in goal-seek: goalseek_id names
        the live goal, the local columns freeze the open-time snapshot. The
        pointer set is what scopes curiosity's reads to mission goals."""
        async with self._sf() as s:
            g = Goal(
                statement=(statement or "").strip(),
                why=(why or "").strip(),
                target_date=(target_date or "").strip(),
                expected_result=(expected_result or "").strip(),
                goalseek_id=str(goalseek_id),
            )
            s.add(g)
            await s.commit()
            return _goal_dict(g)

    async def pointer_map(self) -> dict[str, dict[str, Any]]:
        """goalseek_id → pointer row dict, for every pointered goal."""
        async with self._sf() as s:
            rows = (
                (await s.execute(select(Goal).where(Goal.goalseek_id != "")))
                .scalars()
                .all()
            )
            return {g.goalseek_id: _goal_dict(g) for g in rows}

    async def open_unmigrated(self) -> list[dict[str, Any]]:
        """Internal rows the one-time migration still owes goal-seek: open
        statuses, no pointer, never migrated."""
        async with self._sf() as s:
            rows = (
                (
                    await s.execute(
                        select(Goal)
                        .where(
                            Goal.goalseek_id == "",
                            Goal.migrated_at.is_(None),
                            Goal.status.in_(("active", "stalled")),
                        )
                        .order_by(Goal.created_at)
                    )
                )
                .scalars()
                .all()
            )
            return [_goal_dict(g) for g in rows]

    async def mark_migrated(self, goal_id: str, goalseek_id: str) -> None:
        """Stamp one migrated row: the local columns stay as the frozen
        snapshot; goalseek_id + migrated_at make the second run skip it."""
        async with self._sf() as s:
            g = await s.get(Goal, uuid.UUID(str(goal_id)))
            if g is None:
                return
            g.goalseek_id = str(goalseek_id)
            g.migrated_at = datetime.now(UTC)
            await s.commit()


_STATUS_MARK = {"active": "🎯", "done": "✅", "stalled": "⚠️", "dropped": "✖️"}
_READINESS_MARK = {"green": "🟢", "amber": "🟡", "red": "🔴"}


async def list_mission_goals(ctx: PluginContext, store: GoalStore) -> list[dict[str, Any]]:
    """Every mission goal, engine-routed, in the ledger's dict shape.

    internal → the local rows exactly as before. goalseek → the LIVE goals
    from goal-seek scoped to the pointer set (mission membership), mapped by
    :func:`engine.to_curiosity_dict`, enriched with the pointer's why/
    readiness (curiosity-only fields goal-seek doesn't keep), followed by the
    frozen pre-migration history rows (closed internal goals). A goal-seek
    read failure degrades to the pointer snapshots — the pane must render."""
    if engine.resolve_goal_engine(ctx) != engine.GOAL_ENGINE_GOALSEEK:
        return await store.list()
    pointers = await store.pointer_map()
    history = [
        g for g in await store.list() if not g.get("goalseek_id")
    ]  # pre-migration closed rows keep their place in reviews/value merges
    try:
        live = await engine.engine_list(ctx, include_closed=True)
    except Exception:  # noqa: BLE001 — degrade to snapshots, never blank
        log.warning("goal-seek list failed — serving pointer snapshots", exc_info=True)
        return [dict(p, engine="goalseek") for p in pointers.values()] + history
    out: list[dict[str, Any]] = []
    for g in live:
        gid = str(g.get("id") or "")
        p = pointers.get(gid)
        if p is None:
            continue  # not a mission goal — someone else's board entry
        mapped = engine.to_curiosity_dict(g)
        # curiosity-only fields ride on the pointer row
        mapped["why"] = p.get("why", "")
        mapped["readiness"] = p.get("readiness")
        mapped["readiness_note"] = p.get("readiness_note", "")
        if not mapped["target_date"]:
            mapped["target_date"] = p.get("target_date", "")
        out.append(mapped)
    return out + history


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
        if g.get("engine") == "goalseek" and g.get("id"):
            # phase 06 seam: goal-seek keeps a narrative page per goal in the
            # same wiki — the wikilink puts it on the mission graph
            lines.append(f"  - engine: goal-seek — details at [[goal-{g['id'][:8]}]]")
        lines.append(f"  - status: {g['status']}")
    lines.append("")
    return "\n".join(lines)


async def _mirror_to_wiki(ctx: PluginContext, store: GoalStore) -> str:
    from . import wikibind

    try:
        wiki = ctx.provider_registry.get("wiki")
    except Exception:  # noqa: BLE001
        return "wiki provider unavailable — goals page not mirrored"
    try:
        wk = await wikibind.wiki_kwargs(ctx, store._sf)  # noqa: SLF001
        goals = await list_mission_goals(ctx, store)
        await wiki.upsert_page(
            "mission-goals",
            "Mission Goals",
            render_goals_page(goals),
            summary=f"{sum(1 for g in goals if g['status'] == 'active')} active goal(s)",
            note="goal ledger write-through",
            **wk,
        )
        return "ok"
    except Exception as e:  # noqa: BLE001
        log.warning("goal wiki mirror failed", exc_info=True)
        return f"wiki mirror failed: {e}"


def _register_yielding(ctx: PluginContext, tool_def: ToolDef, handler: Any) -> None:
    """Register a tool that DEFERS to goal-seek's same-named tool.

    New cores take ``yields_to`` and resolve the overlap in both load orders.
    Older cores don't know the kwarg (TypeError → plain registration) and may
    already hold goal-seek's registration (ValueError → skip: same outcome as
    yielding, goal-seek serves the name)."""
    try:
        ctx.tool_registry.register(
            "plugin-curiosity", tool_def, handler, yields_to="plugin-goalseek"
        )
        return
    except TypeError:
        pass
    try:
        ctx.tool_registry.register("plugin-curiosity", tool_def, handler)
    except ValueError:
        log.info("tool %s already served by goal-seek — yielded", tool_def.name)


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
        if engine.resolve_goal_engine(ctx) == engine.GOAL_ENGINE_GOALSEEK:
            return await _set_via_goalseek(
                ctx, store,
                statement=statement, why=why, target_date=target_date,
                expected_result=expected_result,
            )
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

    set_def = (
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
    )
    yielding_defs: list[tuple[ToolDef, Any]] = [
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
    # goal_set is ALWAYS curiosity's (it adds mission membership on top of a
    # delegated open). goal_update/goal_list overlap goal-seek's names by
    # design: with goal-seek installed its richer tools serve them; standalone
    # this ledger does — the deferential registration resolves both orders.
    for tool_def, handler in set_def:
        ctx.tool_registry.register("plugin-curiosity", tool_def, handler)
    for tool_def, handler in yielding_defs:
        _register_yielding(ctx, tool_def, handler)


async def _set_via_goalseek(
    ctx: PluginContext,
    store: GoalStore,
    *,
    statement: str,
    why: str = "",
    target_date: str = "",
    expected_result: str = "",
) -> dict[str, Any]:
    """goal_set, goal-seek engine: delegate the open (goal-seek's own
    agent-open governance applies — grant or approval card), keep the pointer
    row for mission membership, refresh the mirror. Honest passthrough: a
    rejected/proposed open is reported exactly as goal-seek said it."""
    from . import telemetry

    statement = (statement or "").strip()
    if not statement:
        return {"error": "goal statement must be non-empty"}
    dod = (expected_result or "").strip() or f"Owner agrees done: {statement}"
    note_bits = [b for b in ((why or "").strip(),) if b]
    try:
        opened = await engine.engine_open(
            ctx,
            statement=statement,
            definition_of_done=dod,
            deadline=(target_date or "").strip() or None,
            opened_by="agent",
            note=("Mission goal (curiosity). " + " ".join(note_bits)).strip(),
        )
    except Exception as e:  # noqa: BLE001 — the agent must hear the real block
        return {"error": f"goal engine rejected the open: {e}", "engine": "goalseek"}
    if opened.get("status") == "rejected":
        return {**opened, "engine": "goalseek"}
    gid = str(opened.get("id") or "")
    if gid:
        await store.add_pointer(
            gid,
            statement=statement,
            why=why,
            target_date=target_date,
            expected_result=expected_result,
        )
    await telemetry.emit_ui_event(ctx, "changed", {"what": "goal"})
    return {
        "goal": opened,
        "engine": "goalseek",
        "note": (
            "opened in the Goal-Seek engine (stages, policies, heartbeats — "
            "see the Goals pane); use goal_update/goal_list to work it"
        ),
        "wiki_mirror": await _mirror_to_wiki(ctx, store),
    }


async def migrate_internal_goals(ctx: PluginContext, store: GoalStore) -> dict[str, Any]:
    """One-time pointer conversion when the engine flips to goal-seek.

    Open internal rows (active/stalled) move under ONE owner approval card —
    "move N goals into Goal-Seek" — not N separate goal_open cards: the opens
    then run as owner-approved (opened_by='owner', provenance note). Closed
    rows stay internal (history; value/review reads merge both sources).
    Idempotent: migrated rows carry goalseek_id + migrated_at and are never
    re-sent; a declined/expired card leaves everything untouched for a later
    retry. Never raises — the on-load path logs the summary."""
    pending = await store.open_unmigrated()
    if not pending:
        return {"migrated": 0, "note": "nothing to migrate"}
    approvals = getattr(ctx, "approvals", None)
    if approvals is None:
        return {"migrated": 0, "note": "no approvals engine — migration deferred"}
    try:
        decision = await approvals.request(
            kind="tool_call",
            summary=(
                f"Curiosity wants to move {len(pending)} mission goal(s) into "
                "the Goal-Seek engine"
            ),
            payload={
                "tool": "goal_open",
                "args": {"count": len(pending), "goals": [g["statement"][:80] for g in pending]},
                "curiosity": {"migration": True},
            },
            requested_by_plugin="plugin-curiosity",
            risk_level="low",
            plugin="plugin-curiosity",
        )
    except Exception as e:  # noqa: BLE001 — timeout/expired: retry next load
        return {"migrated": 0, "note": f"migration approval not decided: {e}"}
    if getattr(decision, "decision", None) != "approved":
        return {"migrated": 0, "note": "owner declined the migration"}
    migrated = 0
    for g in pending:
        try:
            opened = await engine.engine_open(
                ctx,
                statement=g["statement"],
                definition_of_done=(g.get("expected_result") or "").strip()
                or f"Owner agrees done: {g['statement']}",
                deadline=(g.get("target_date") or "").strip() or None,
                opened_by="owner",  # the migration card IS the owner's approval
                note="Migrated from curiosity's goal ledger (owner-approved migration).",
            )
        except Exception:  # noqa: BLE001 — leave unmigrated; next load retries
            log.warning("migration open failed for %s", g["id"], exc_info=True)
            continue
        gid = str(opened.get("id") or "")
        if gid:
            await store.mark_migrated(g["id"], gid)
            migrated += 1
    if migrated:
        await _mirror_to_wiki(ctx, store)
    return {"migrated": migrated, "of": len(pending)}
