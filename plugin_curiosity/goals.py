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

# 0.15.0 (11.003/M3) honest horizons — WHEN, in units that are true:
#   agent_minutes     — the agent's own working time once unblocked (ref:
#                       minutes, e.g. "90")
#   awaiting_approval — blocked on the owner's yes (ref: what needs approving)
#   on_unlock         — blocked until a named unlock (ref: the loop / access /
#                       event it waits on); NEVER overdue — it's blocked
#   date              — a real calendar date carried by a real-world event
#                       (ref: ISO date) — the only kind that can be overdue
#   rhythm            — recurring cadence (ref: e.g. "weekly", "each Monday")
HORIZON_KINDS = ("agent_minutes", "awaiting_approval", "on_unlock", "date", "rhythm")

# kinds that mean "someone else's move" — surfaces render these blocked-on,
# never late; pace names the unlock instead of counting days
BLOCKED_HORIZON_KINDS = ("awaiting_approval", "on_unlock")


def _iso_date(text: str) -> str | None:
    """ISO date/datetime or None — kind 'date' requires a real-date source."""
    from datetime import datetime

    t = (text or "").strip()
    if not t:
        return None
    try:
        datetime.fromisoformat(t)
    except ValueError:
        return None
    return t


def _norm_horizon(kind: str, ref: str, target_date: str) -> tuple[str, str, str]:
    """Validate + normalize the horizon triple → (kind, ref, target_date).

    Rules: an explicit kind must be one of HORIZON_KINDS; kind 'date' needs a
    real ISO date in ref (guessed durations are exactly what this kills) and
    mirrors it into target_date (the pane timeline reads it). Legacy callers
    passing only target_date: an ISO value derives kind 'date'; free-form text
    ("end of July") stays an untyped note exactly as before."""
    kind = (kind or "").strip()
    ref = (ref or "").strip()
    target_date = (target_date or "").strip()
    if kind and kind not in HORIZON_KINDS:
        raise ValueError(f"horizon_kind must be one of {HORIZON_KINDS}")
    if not kind and target_date and _iso_date(target_date):
        kind, ref = "date", target_date
    if kind == "date":
        if not ref and target_date:
            ref = target_date
        if _iso_date(ref) is None:
            raise ValueError(
                "horizon_kind 'date' needs a real calendar date (ISO, e.g. "
                "'2026-08-15') carried by a real-world event. For your own "
                "work time use agent_minutes; for a wait use "
                "awaiting_approval or on_unlock; for a cadence use rhythm — "
                "never guess a date"
            )
        target_date = ref
    return kind, ref, target_date


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
        "horizon_kind": getattr(g, "horizon_kind", "") or "",
        "horizon_ref": getattr(g, "horizon_ref", "") or "",
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
        horizon_kind: str = "",
        horizon_ref: str = "",
    ) -> dict[str, Any]:
        statement = (statement or "").strip()
        if not statement:
            raise ValueError("goal statement must be non-empty")
        if readiness and readiness not in GOAL_READINESS:
            raise ValueError(f"readiness must be one of {GOAL_READINESS}")
        horizon_kind, horizon_ref, target_date = _norm_horizon(
            horizon_kind, horizon_ref, target_date
        )
        async with self._sf() as s:
            g = Goal(
                statement=statement,
                why=why.strip(),
                target_date=target_date,
                expected_result=expected_result.strip(),
                readiness=readiness,
                readiness_note=readiness_note.strip(),
                horizon_kind=horizon_kind,
                horizon_ref=horizon_ref,
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
        horizon_kind: str | None = None,
        horizon_ref: str | None = None,
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
            if horizon_kind is not None or horizon_ref is not None:
                hk = horizon_kind if horizon_kind is not None else g.horizon_kind
                hr = horizon_ref if horizon_ref is not None else g.horizon_ref
                td = target_date if target_date is not None else g.target_date
                hk, hr, td = _norm_horizon(hk, hr, td)
                g.horizon_kind, g.horizon_ref = hk, hr
                if hk == "date":
                    g.target_date = td
                    target_date = None  # already applied — skip the legacy branch
            if target_date is not None:
                hk, hr, td = _norm_horizon(g.horizon_kind, g.horizon_ref
                                           if g.horizon_kind != "date" else "",
                                           target_date)
                g.target_date = td
                if hk == "date":  # an ISO shift re-types / re-refs the horizon
                    g.horizon_kind, g.horizon_ref = hk, hr
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
        horizon_kind: str = "",
        horizon_ref: str = "",
    ) -> dict[str, Any]:
        """A pointer row for a goal that LIVES in goal-seek: goalseek_id names
        the live goal, the local columns freeze the open-time snapshot. The
        pointer set is what scopes curiosity's reads to mission goals.
        Horizon fields ride the pointer raw (goal-seek doesn't keep them)."""
        async with self._sf() as s:
            g = Goal(
                statement=(statement or "").strip(),
                why=(why or "").strip(),
                target_date=(target_date or "").strip(),
                expected_result=(expected_result or "").strip(),
                horizon_kind=(horizon_kind or "").strip(),
                horizon_ref=(horizon_ref or "").strip(),
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

    # -- 0.11.0 pointer repair (engine v1 → v2 upgrade) ----------------------

    async def repoint(self, goal_id: str, new_goalseek_id: str) -> None:
        """Swing one pointer to the goal's new home (the v2 re-open)."""
        async with self._sf() as s:
            g = await s.get(Goal, uuid.UUID(str(goal_id)))
            if g is None:
                return
            g.goalseek_id = str(new_goalseek_id)
            await s.commit()

    async def retire_pointer(self, goal_id: str, *, status: str,
                             progress_note: str = "") -> None:
        """A pointered goal that ended in the old engine becomes a plain
        history row: pointer cleared, honest final status, note says where it
        ended. It then reads exactly like pre-migration closed rows."""
        async with self._sf() as s:
            g = await s.get(Goal, uuid.UUID(str(goal_id)))
            if g is None:
                return
            g.goalseek_id = ""
            if status in GOAL_STATUSES:
                g.status = status
            if progress_note:
                g.progress_note = progress_note
            await s.commit()


_STATUS_MARK = {"active": "🎯", "done": "✅", "stalled": "⚠️", "dropped": "✖️"}
# How many open mission goals get the per-goal counts read (goal_get) on a
# pane/mirror refresh — missions hold 2-6 goals; the cap only guards runaways.
_ENRICH_CAP = 12
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
    enriched = 0
    for g in live:
        gid = str(g.get("id") or "")
        p = pointers.get(gid)
        if p is None:
            continue  # not a mission goal — someone else's board entry
        # v2's list is lean (no counts) — goal_get carries the table summary
        # that becomes the "18/50 done · needs you: 2" progress line. Capped,
        # best-effort: a failed get falls back to the lean dict.
        if g.get("stage") != "closed" and "table" not in g and enriched < _ENRICH_CAP:
            try:
                g = await engine.engine_get(ctx, gid)
                enriched += 1
            except Exception:  # noqa: BLE001 — lean dict still renders
                log.debug("goal_get enrich failed for %s", gid, exc_info=True)
        mapped = engine.to_curiosity_dict(g)
        # curiosity-only fields ride on the pointer row
        mapped["why"] = p.get("why", "")
        mapped["readiness"] = p.get("readiness")
        mapped["readiness_note"] = p.get("readiness_note", "")
        if not mapped["target_date"]:
            mapped["target_date"] = p.get("target_date", "")
        # horizons are curiosity-only too — goal-seek knows one unit (a date
        # deadline); every other kind rides the pointer snapshot
        if not mapped.get("horizon_kind"):
            mapped["horizon_kind"] = p.get("horizon_kind", "")
            mapped["horizon_ref"] = p.get("horizon_ref", "")
        out.append(mapped)
    return out + history


def _horizon_phrase(g: dict[str, Any]) -> str:
    """The owner-readable WHEN suffix, per kind. A blocked kind (on_unlock /
    awaiting_approval) reads as waiting on its unlock — never late, never
    overdue; only kind 'date' carries a calendar date."""
    hk = g.get("horizon_kind") or ""
    hr = (g.get("horizon_ref") or "").strip()
    if hk == "agent_minutes":
        return f" — about {hr} minutes of my work once I start" if hr else ""
    if hk == "awaiting_approval":
        tail = f": {hr}" if hr else ""
        return f" — waiting on your approval{tail} (~5 min of your time)"
    if hk == "on_unlock":
        return f" — starts when this unlocks: {hr}" if hr else " — waiting on an unlock"
    if hk == "date":
        return f" — target: {hr or g.get('target_date', '')}"
    if hk == "rhythm":
        return f" — rhythm: {hr}" if hr else ""
    return f" — target: {g['target_date']}" if g.get("target_date") else ""


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
        head += _horizon_phrase(g)
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


def register_tools(ctx: PluginContext, store: GoalStore,
                   mission_store: Any = None) -> None:
    from . import telemetry

    async def _mission_id() -> str | None:
        if mission_store is None:
            return None
        try:
            m = await mission_store.get()
            return str(m["id"]) if m else None
        except Exception:  # noqa: BLE001 — provenance only, never blocks
            return None

    async def _set(
        statement: str,
        why: str = "",
        target_date: str = "",
        expected_result: str = "",
        readiness: str = "",
        readiness_note: str = "",
        horizon_kind: str = "",
        horizon_ref: str = "",
    ) -> dict[str, Any]:
        if engine.resolve_goal_engine(ctx) == engine.GOAL_ENGINE_GOALSEEK:
            return await _set_via_goalseek(
                ctx, store,
                statement=statement, why=why, target_date=target_date,
                expected_result=expected_result,
                horizon_kind=horizon_kind, horizon_ref=horizon_ref,
                mission_id=await _mission_id(),
            )
        try:
            goal = await store.add(
                statement,
                why=why,
                target_date=target_date,
                expected_result=expected_result,
                readiness=readiness,
                readiness_note=readiness_note,
                horizon_kind=horizon_kind,
                horizon_ref=horizon_ref,
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
        horizon_kind: str | None = None,
        horizon_ref: str | None = None,
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
                horizon_kind=horizon_kind,
                horizon_ref=horizon_ref,
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

    horizon_params = {
        "horizon_kind": {
            "type": "string",
            "enum": list(HORIZON_KINDS),
            "description": (
                "WHEN, in honest units: agent_minutes = your own working time "
                "once unblocked; awaiting_approval = blocked on the owner's "
                "yes; on_unlock = blocked until a named unlock (never "
                "overdue); date = ONLY when a real-world event carries a real "
                "calendar date; rhythm = recurring cadence. Never guess a "
                "date for your own work."
            ),
        },
        "horizon_ref": {
            "type": "string",
            "description": (
                "The unit's value: minutes ('90'), what needs approving, the "
                "unlock it waits on, an ISO date ('2026-08-15'), or the "
                "cadence ('weekly')."
            ),
        },
    }
    set_def = (
        (
            ToolDef(
                name="goal_set",
                description=(
                    "Commit to a concrete goal in pursuit of your mission — a "
                    "specific outcome YOU will drive, with an honest horizon "
                    "(horizon_kind + horizon_ref: your work in agent-minutes, "
                    "waits by their unlock, real dates only when real). Set "
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
                        **horizon_params,
                        "target_date": {
                            "type": "string",
                            "description": (
                                "Legacy — prefer horizon_kind='date' + "
                                "horizon_ref. A real ISO date only when a "
                                "real-world event carries it."
                            ),
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
                    "(active/done/stalled/dropped), horizon shifts (an unlock "
                    "landed, a wait became your own work — re-type it with "
                    "horizon_kind/horizon_ref), and readiness re-scores "
                    "(green/amber/red + what you have / what's missing). "
                    "Update after every research pass that advanced a goal "
                    "and re-score readiness when your ladder changes; "
                    "confront stalls honestly — change approach or drop with "
                    "a reason, never let a goal rot."
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
                        **horizon_params,
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
                    "its honest horizon (work time, unlock, date, or rhythm). "
                    "Read it at the start of each research pass "
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
    horizon_kind: str = "",
    horizon_ref: str = "",
    mission_id: str | None = None,
) -> dict[str, Any]:
    """goal_set, goal-seek engine: delegate the open (goal-seek's own
    agent-open governance applies — grant or approval card), keep the pointer
    row for mission membership, refresh the mirror. Honest passthrough: a
    rejected open is reported exactly as goal-seek said it, and a 'proposed'
    return is a NORMAL outcome (the owner has a card; the goal activates by
    itself on approve) — the pointer is kept either way.

    Horizon mapping (0.15.0): goal-seek knows exactly one time unit — a real
    date deadline — so only kind 'date' maps to it. Every other kind rides
    the provenance note (and the pointer snapshot, which curiosity's reads
    prefer): a wait or a rhythm must never masquerade as a deadline."""
    from . import telemetry

    statement = (statement or "").strip()
    if not statement:
        return {"error": "goal statement must be non-empty"}
    try:
        horizon_kind, horizon_ref, target_date = _norm_horizon(
            horizon_kind, horizon_ref, target_date
        )
    except ValueError as e:
        return {"error": str(e), "engine": "goalseek"}
    dod = (expected_result or "").strip() or f"Owner agrees done: {statement}"
    note_bits = [b for b in ((why or "").strip(),) if b]
    deadline: str | None = None
    if horizon_kind == "date":
        deadline = horizon_ref
    elif horizon_kind == "rhythm":
        note_bits.append(f"Rhythm: {horizon_ref}.")
    elif horizon_kind == "agent_minutes":
        note_bits.append(f"About {horizon_ref} minutes of agent work once started.")
    elif horizon_kind == "awaiting_approval":
        note_bits.append(f"Waiting on owner approval: {horizon_ref}.")
    elif horizon_kind == "on_unlock":
        note_bits.append(f"Starts when this unlocks: {horizon_ref}.")
    else:
        deadline = (target_date or "").strip() or None
    try:
        opened = await engine.engine_open(
            ctx,
            statement=statement,
            definition_of_done=dod,
            deadline=deadline,
            opened_by="agent",
            note=("Mission goal (curiosity). " + " ".join(note_bits)).strip(),
            mission_id=mission_id,
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
            horizon_kind=horizon_kind,
            horizon_ref=horizon_ref,
        )
    await telemetry.emit_ui_event(ctx, "changed", {"what": "goal"})
    if opened.get("stage") == "proposed":
        note = (
            "opened in the Goal-Seek engine as 'proposed' — the owner has an "
            "approval card and the goal activates by itself on approve (or "
            "closes if they decline). Do NOT wait or retry; carry on."
        )
    else:
        note = (
            "opened in the Goal-Seek engine (stages, policies, heartbeats — "
            "see the Goals pane); use goal_update/goal_list to work it"
        )
    return {
        "goal": opened,
        "engine": "goalseek",
        "note": note,
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


# v1 outcome → the local status a retired pointer row keeps as history.
_V1_OUTCOME_STATUS = {
    "achieved": "done",
    "abandoned": "dropped",
    "expired": "dropped",
    "failed": "stalled",
    "escalated": "stalled",
}

# v1 stages that mean "the goal was still being worked" — those re-open in v2.
_V1_OPEN_STAGES = ("proposed", "active", "waiting", "parked", "closing")


async def repoint_stale_pointers(ctx: PluginContext, store: GoalStore) -> dict[str, Any]:
    """0.11.0: heal pointers left behind by the engine's v1 → v2 upgrade.

    Tenants that migrated under goal-seek 1.x hold ``goalseek_id`` values that
    name v1 goal rows; goal-seek 2.x serves only v2 goals, so those mission
    goals would silently vanish from every curiosity read. For each pointer
    the live list doesn't know: ask ``goal_get`` (2.x answers for v1 ids,
    marked ``legacy_v1``). Still-open v1 goals re-open in v2 (the owner
    approved the original migration; this is the same goal moving home —
    provenance note says so) and the pointer swings to the new id. Goals that
    ENDED in v1 become plain history rows with their honest final status.
    Unknown ids stay untouched (snapshots still render). Idempotent by
    construction; never raises — the on-load path logs the summary."""
    if engine.resolve_goal_engine(ctx) != engine.GOAL_ENGINE_GOALSEEK:
        return {"repointed": 0, "retired": 0, "note": "engine is internal"}
    try:
        live_ids = {str(g.get("id") or "")
                    for g in await engine.engine_list(ctx, include_closed=True)}
    except Exception as e:  # noqa: BLE001 — engine unreadable: try next load
        return {"repointed": 0, "retired": 0, "note": f"goal list unreadable: {e}"}
    pointers = await store.pointer_map()
    stale = {gsid: p for gsid, p in pointers.items() if gsid not in live_ids}
    if not stale:
        return {"repointed": 0, "retired": 0, "note": "all pointers live"}
    repointed = retired = 0
    for gsid, p in stale.items():
        try:
            old = await engine.engine_get(ctx, gsid)
        except Exception:  # noqa: BLE001 — id unknown everywhere: leave the snapshot
            log.info("stale pointer %s not found in any engine — left as snapshot", gsid)
            continue
        if not old.get("legacy_v1"):
            continue  # live v2 goal that the list missed — nothing to heal
        stage = old.get("stage") or ""
        if stage in _V1_OPEN_STAGES:
            try:
                opened = await engine.engine_open(
                    ctx,
                    statement=old.get("statement") or p.get("statement") or "",
                    definition_of_done=(old.get("definition_of_done")
                                        or p.get("expected_result")
                                        or "").strip()
                    or f"Owner agrees done: {old.get('statement') or p.get('statement')}",
                    deadline=old.get("deadline"),
                    opened_by="owner",  # the original migration was owner-approved
                    note=("Re-opened after the goal engine upgrade — this goal "
                          "moved from the old format; its earlier history "
                          "stays readable in the old records."),
                )
            except Exception:  # noqa: BLE001 — retry on a later load
                log.warning("repoint re-open failed for %s", gsid, exc_info=True)
                continue
            new_id = str(opened.get("id") or "")
            if new_id:
                await store.repoint(p["id"], new_id)
                repointed += 1
        else:
            outcome = old.get("outcome") or ""
            reason = old.get("outcome_reason")
            summary = reason.get("summary", "") if isinstance(reason, dict) else ""
            await store.retire_pointer(
                p["id"],
                status=_V1_OUTCOME_STATUS.get(outcome, "dropped"),
                progress_note=summary or "ended in the old goal format",
            )
            retired += 1
    if repointed or retired:
        await _mirror_to_wiki(ctx, store)
    return {"repointed": repointed, "retired": retired, "of": len(stale)}
