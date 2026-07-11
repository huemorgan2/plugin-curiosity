"""abilities.py — the qualification ladder (phase 10.001).

The role decomposes into 3-7 "Ability to …" items, each with 2-6 concrete
subtasks. The agent derives them (ability_upsert), re-scores them on every
heartbeat fire (ability_task_set), and the pane renders per-ability percents
plus the overall setup % — ALL percents are server-computed here (done=1,
in_progress=0.5, missing/blocked=0; setup % = unweighted mean of ability
percents). Agents never do arithmetic.

Convergence over exactly-once: the natural key is (mission_id, slug-of-title),
so two concurrent turns re-deriving the same ladder converge onto the same
rows instead of duplicating (the 0.8.1 heartbeat-reaper lesson, applied at
design time). Task upserts merge by slug and never delete — dropping a task
is a plan change, not a silent disappearance.

All three tools are auto_approve: the ladder is the agent's own bookkeeping.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy import select

from luna_sdk import PluginContext, ToolDef

from .models import Ability, AbilityTask, Mission

log = logging.getLogger("plugin-curiosity")

ABILITY_STATUSES = ("building", "ready", "degraded")
TASK_STATUSES = ("done", "in_progress", "missing", "blocked")

_TASK_WEIGHT = {"done": 1.0, "in_progress": 0.5, "missing": 0.0, "blocked": 0.0}


def slugify(title: str) -> str:
    """The natural-key half: lowercase kebab of the title, stable across
    re-derivations that phrase the same ability the same way."""
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return s[:120]


def task_percent(tasks: list[dict[str, Any]]) -> int:
    """done=1, in_progress=0.5, missing/blocked=0 — rounded percent.
    Zero tasks reads as 0% (an ability with no concrete subtasks is not
    progress, it is a missing decomposition)."""
    if not tasks:
        return 0
    total = sum(_TASK_WEIGHT.get(t["status"], 0.0) for t in tasks)
    return round(100 * total / len(tasks))


def setup_percent(abilities: list[dict[str, Any]]) -> int | None:
    """Unweighted mean of ability percents; None when no abilities exist
    (callers fall back to the 9.002 stage-based % during the upgrade
    window)."""
    if not abilities:
        return None
    return round(sum(a["percent"] for a in abilities) / len(abilities))


def _task_dict(t: AbilityTask) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "title": t.title,
        "slug": t.slug,
        "status": t.status,
        "note": t.note,
        "evidence_ref": t.evidence_ref,
        "sort_order": t.sort_order,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _ability_dict(a: Ability, tasks: list[AbilityTask]) -> dict[str, Any]:
    task_dicts = [_task_dict(t) for t in tasks]
    return {
        "id": str(a.id),
        "title": a.title,
        "why": a.why,
        "status": a.status,
        "sort_order": a.sort_order,
        "tasks": task_dicts,
        "percent": task_percent(task_dicts),
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


class AbilityStore:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    async def _active(self, s) -> Mission | None:
        q = (
            select(Mission)
            .where(Mission.active.is_(True))
            .order_by(Mission.created_at.desc())
        )
        return (await s.execute(q)).scalars().first()

    async def _tasks(self, s, ability_id) -> list[AbilityTask]:
        q = (
            select(AbilityTask)
            .where(AbilityTask.ability_id == ability_id)
            .order_by(AbilityTask.sort_order, AbilityTask.slug)
        )
        return list((await s.execute(q)).scalars().all())

    async def upsert(
        self,
        title: str,
        *,
        why: str = "",
        status: str | None = None,
        sort_order: int | None = None,
        tasks: list[dict[str, Any] | str] | None = None,
    ) -> dict[str, Any]:
        title = (title or "").strip()
        if not title:
            raise ValueError("ability title must be non-empty")
        slug = slugify(title)
        if not slug:
            raise ValueError("ability title must contain letters or digits")
        if status is not None and status not in ABILITY_STATUSES:
            raise ValueError(f"status must be one of {ABILITY_STATUSES}")
        async with self._sf() as s:
            m = await self._active(s)
            if m is None:
                raise ValueError("no active mission — set a mission first")
            a = (
                await s.execute(
                    select(Ability).where(
                        Ability.mission_id == m.id, Ability.slug == slug
                    )
                )
            ).scalars().first()
            if a is None:
                a = Ability(mission_id=m.id, title=title, slug=slug, why=why.strip())
                s.add(a)
                await s.flush()
            else:
                a.title = title  # phrasing may sharpen; slug is the identity
                if why.strip():
                    a.why = why.strip()
            if status is not None:
                a.status = status
            if sort_order is not None:
                a.sort_order = int(sort_order)
            # merge tasks by slug — statuses of untouched existing tasks
            # survive a re-derivation; nothing is ever deleted here
            existing = {t.slug: t for t in await self._tasks(s, a.id)}
            for i, item in enumerate(tasks or []):
                if isinstance(item, str):
                    item = {"title": item}
                t_title = (item.get("title") or "").strip()
                if not t_title:
                    continue
                t_slug = slugify(t_title)
                t_status = item.get("status")
                if t_status is not None and t_status not in TASK_STATUSES:
                    raise ValueError(f"task status must be one of {TASK_STATUSES}")
                row = existing.get(t_slug)
                if row is None:
                    row = AbilityTask(
                        ability_id=a.id,
                        title=t_title,
                        slug=t_slug,
                        status=t_status or "missing",
                        note=(item.get("note") or "").strip(),
                        evidence_ref=(item.get("evidence_ref") or "").strip(),
                        sort_order=item.get("sort_order", i),
                    )
                    s.add(row)
                    existing[t_slug] = row
                else:
                    row.title = t_title
                    if t_status is not None:
                        row.status = t_status
                    if item.get("note") is not None:
                        row.note = str(item["note"]).strip()
                    if item.get("evidence_ref") is not None:
                        row.evidence_ref = str(item["evidence_ref"]).strip()
            await s.commit()
            return _ability_dict(a, await self._tasks(s, a.id))

    async def _resolve_ability(self, s, ability: str) -> Ability:
        """By id first, then by slug/title within the active mission."""
        try:
            key = uuid.UUID(str(ability))
        except ValueError:
            key = None
        if key is not None:
            a = await s.get(Ability, key)
            if a is not None:
                return a
        m = await self._active(s)
        if m is None:
            raise LookupError("no active mission")
        slug = slugify(ability)
        a = (
            await s.execute(
                select(Ability).where(Ability.mission_id == m.id, Ability.slug == slug)
            )
        ).scalars().first()
        if a is None:
            raise LookupError(f"no ability matching '{ability}' — see ability_list")
        return a

    async def task_set(
        self,
        ability: str,
        task: str,
        status: str,
        *,
        note: str | None = None,
        evidence_ref: str | None = None,
    ) -> dict[str, Any]:
        if status not in TASK_STATUSES:
            raise ValueError(f"status must be one of {TASK_STATUSES}")
        task_title = (task or "").strip()
        if not task_title:
            raise ValueError("task must be non-empty")
        async with self._sf() as s:
            a = await self._resolve_ability(s, ability)
            t_slug = slugify(task_title)
            row = None
            for t in await self._tasks(s, a.id):
                if t.slug == t_slug or str(t.id) == task_title:
                    row = t
                    break
            if row is None:
                # a gap discovered mid-heartbeat lands as a new subtask —
                # convergence beats a LookupError here
                row = AbilityTask(
                    ability_id=a.id, title=task_title, slug=t_slug, status=status
                )
                s.add(row)
            else:
                row.status = status
            if note is not None:
                row.note = note.strip()
            if evidence_ref is not None:
                row.evidence_ref = evidence_ref.strip()
            await s.commit()
            return {"ability": a.title, "task": _task_dict(row)}

    async def list(self) -> dict[str, Any]:
        async with self._sf() as s:
            m = await self._active(s)
            if m is None:
                return {"abilities": [], "setup_percent": None}
            q = (
                select(Ability)
                .where(Ability.mission_id == m.id)
                .order_by(Ability.sort_order, Ability.created_at)
            )
            rows = (await s.execute(q)).scalars().all()
            abilities = [_ability_dict(a, await self._tasks(s, a.id)) for a in rows]
            return {"abilities": abilities, "setup_percent": setup_percent(abilities)}


def register_tools(ctx: PluginContext, store: AbilityStore) -> None:
    from . import telemetry

    async def _upsert(
        title: str,
        why: str = "",
        tasks: list | None = None,
        status: str | None = None,
        sort_order: int | None = None,
    ) -> dict[str, Any]:
        try:
            ability = await store.upsert(
                title, why=why, tasks=tasks, status=status, sort_order=sort_order
            )
        except ValueError as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "ability"})
        return {"ability": ability}

    async def _task_set(
        ability: str,
        task: str,
        status: str,
        note: str | None = None,
        evidence_ref: str | None = None,
    ) -> dict[str, Any]:
        try:
            result = await store.task_set(
                ability, task, status, note=note, evidence_ref=evidence_ref
            )
        except (ValueError, LookupError) as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "ability"})
        return result

    async def _list() -> dict[str, Any]:
        result = await store.list()
        if not result["abilities"]:
            result["note"] = (
                "no abilities derived yet — decompose your job description "
                "into 3-7 'Ability to …' items with ability_upsert, each with "
                "2-6 concrete subtasks"
            )
        return result

    defs: list[tuple[ToolDef, Any]] = [
        (
            ToolDef(
                name="ability_upsert",
                description=(
                    "Create or update one ability of your qualification "
                    "ladder — an 'Ability to …' item your job description "
                    "requires, with its concrete subtasks. Idempotent on the "
                    "title: re-deriving the same ability updates it in place "
                    "(existing task statuses survive; nothing is deleted). "
                    "Derive 3-7 abilities per role, 2-6 subtasks each."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "The ability, phrased 'Ability to …' — owner-readable, no jargon.",
                        },
                        "why": {
                            "type": "string",
                            "description": "Which part of the job description needs it.",
                        },
                        "tasks": {
                            "type": "array",
                            "description": "Concrete subtasks; strings or {title, status, note, evidence_ref}.",
                            "items": {
                                "anyOf": [
                                    {"type": "string"},
                                    {
                                        "type": "object",
                                        "properties": {
                                            "title": {"type": "string"},
                                            "status": {"type": "string", "enum": list(TASK_STATUSES)},
                                            "note": {"type": "string"},
                                            "evidence_ref": {"type": "string"},
                                        },
                                        "required": ["title"],
                                    },
                                ]
                            },
                        },
                        "status": {"type": "string", "enum": list(ABILITY_STATUSES)},
                        "sort_order": {"type": "integer"},
                    },
                    "required": ["title"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _upsert,
        ),
        (
            ToolDef(
                name="ability_task_set",
                description=(
                    "Re-score one subtask of an ability: done / in_progress / "
                    "missing / blocked, with an optional note and evidence "
                    "reference (a wiki page or validated run). Your heartbeat "
                    "re-scores tasks every fire; a new gap you discover lands "
                    "here as a new subtask automatically."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "ability": {
                            "type": "string",
                            "description": "Ability id or title (from ability_list).",
                        },
                        "task": {
                            "type": "string",
                            "description": "Task title (or id). An unknown title creates the subtask.",
                        },
                        "status": {"type": "string", "enum": list(TASK_STATUSES)},
                        "note": {"type": "string"},
                        "evidence_ref": {"type": "string"},
                    },
                    "required": ["ability", "task", "status"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _task_set,
        ),
        (
            ToolDef(
                name="ability_list",
                description=(
                    "Your qualification ladder — every ability with its "
                    "subtasks, server-computed percent per ability, and the "
                    "overall setup percent. Read it at the start of every "
                    "heartbeat fire; never compute percents yourself."
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
