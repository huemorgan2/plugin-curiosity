"""scopes.py — the agent-phase state machine + role scopes (phase 9A).

The structural spine of "Setup for Work → Work Mode". A role is more than a
topic: it decomposes into scopes — the areas the agent must become competent
in (knowledge, people, communication paths, tools/data access, workflow &
approval points, playbooks, routines & feedback loops). The agent charters
them itself (scope_set), tracks its competency per scope (scope_update, both
directions — a later learning can invalidate earlier competence), marks the
furthest RATIFIED setup-arc stage (stage_set), and graduates to work mode
through an owner-approved gate (phase_advance, `prompt_always` — the approval
card IS the graduation sign-off).

Write-through: every mutation rebuilds the [[role-charter]] wiki page — stage
marker on top, role statement, scopes grouped by kind, then the append-only
**Plan changes** log (plan_change_note): the living plan's audit trail.

All tools except phase_advance are auto_approve: self-bookkeeping on the
plugin's own tables. phase_advance is the one owner-visible state flip.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from luna_sdk import PluginContext, ToolDef

from . import gating
from .models import Mission, PlanChange, Scope

log = logging.getLogger("plugin-curiosity")

SCOPE_KINDS = (
    "knowledge",
    "people",
    "communication_paths",
    "tools_data_access",
    "workflow_approval",
    "playbooks",
    "routines_feedback",
)
SCOPE_STATUSES = ("missing", "in_progress", "competent")
SETUP_STAGES = ("S0", "S1", "S2", "S3", "S4", "S5")
# Owner-facing words for the stages (0.9.2 — ux_guidelines §4: S-codes are
# internal shorthand and never render on an owner surface; lives here, not in
# overview.py, so the charter mirror can use it without a circular import).
STAGE_LABELS = {
    "S0": ("understood", "mission restated in my own words, first observations noted"),
    "S1": ("mapped", "listed what the job needs, checked the tools work, delivered a first win"),
    "S2": ("shared", "job description, what success looks like, and dated goals shared for your review"),
    "S3": ("approved", "you read the job description and approved it"),
    "S4": ("proven", "one real piece of work done end-to-end"),
    "S5": ("running", "regular check-ins and feedback are flowing"),
}
AGENT_PHASES = ("setup", "work")
# phase 10 materiality rule: a within-ability learning is a "refine"; a
# learning that changes the role's SHAPE is a "role_pivot" — it bumps the
# mission's role_version in the same transaction and surfaces to the owner.
PLAN_CHANGE_KINDS = ("refine", "role_pivot")

CHARTER_SLUG = "role-charter"
CHARTER_TITLE = "What this job needs"

_KIND_LABEL = {
    "knowledge": "Knowledge",
    "people": "People",
    "communication_paths": "Communication paths",
    "tools_data_access": "Tools & data access",
    "workflow_approval": "Workflow & approval points",
    "playbooks": "Playbooks",
    "routines_feedback": "Routines & feedback loops",
}
_STATUS_MARK = {"missing": "⬜", "in_progress": "🟡", "competent": "✅"}
# owner-facing words for scope statuses (enum values stay internal)
_STATUS_WORD = {"missing": "not started", "in_progress": "in progress", "competent": "ready"}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _scope_dict(s: Scope) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "kind": s.kind,
        "name": s.name,
        "why": s.why,
        "status": s.status,
        "evidence": s.evidence,
        "ability_id": str(s.ability_id) if s.ability_id else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


class ScopeStore:
    """Scopes + phase/stage state + the Plan-changes log, all keyed on the
    single active mission row."""

    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    async def _active(self, s) -> Mission | None:
        q = (
            select(Mission)
            .where(Mission.active.is_(True))
            .order_by(Mission.created_at.desc())
        )
        return (await s.execute(q)).scalars().first()

    async def state(self) -> dict[str, Any] | None:
        async with self._sf() as s:
            m = await self._active(s)
            if m is None:
                return None
            # stage_age_days is server-computed — agents have no clock, so a
            # recency gate ("un-ratified past 3 days") must ship as a number,
            # not a timestamp. Pre-9.001 rows have no stage_entered_at; the
            # mission's creation is the best available stage start.
            stage_since = m.stage_entered_at or m.created_at
            if stage_since is not None and stage_since.tzinfo is None:
                # SQLite round-trips DateTime(timezone=True) as naive UTC
                stage_since = stage_since.replace(tzinfo=UTC)
            age_days = max(0, (_utcnow() - stage_since).days) if stage_since else 0
            cs_at = getattr(m, "current_state_at", None)
            if cs_at is not None and cs_at.tzinfo is None:
                cs_at = cs_at.replace(tzinfo=UTC)
            return {
                "mission_id": str(m.id),
                "statement": m.statement,
                "agent_phase": m.agent_phase,
                "setup_stage": m.setup_stage,
                "stage_age_days": age_days,
                "role_version": getattr(m, "role_version", 1) or 1,
                "phase_entered_at": (
                    m.phase_entered_at.isoformat() if m.phase_entered_at else None
                ),
                "current_state": getattr(m, "current_state", "") or "",
                # server-computed (agents have no clock): how stale the line is
                "current_state_age_days": (
                    max(0, (_utcnow() - cs_at).days) if cs_at else None
                ),
            }

    @staticmethod
    def _parse_ability_id(ability_id: str | None) -> uuid.UUID | None:
        if not ability_id:
            return None
        try:
            return uuid.UUID(str(ability_id))
        except ValueError:
            raise ValueError(f"ability_id is not a valid id: {ability_id}") from None

    async def add(
        self, kind: str, name: str, *, why: str = "", ability_id: str | None = None
    ) -> dict[str, Any]:
        if kind not in SCOPE_KINDS:
            raise ValueError(f"kind must be one of {SCOPE_KINDS}")
        name = (name or "").strip()
        if not name:
            raise ValueError("scope name must be non-empty")
        akey = self._parse_ability_id(ability_id)
        async with self._sf() as s:
            m = await self._active(s)
            if m is None:
                raise ValueError("no active mission — set a mission first")
            sc = Scope(
                mission_id=m.id, kind=kind, name=name, why=why.strip(), ability_id=akey
            )
            s.add(sc)
            await s.commit()
            return _scope_dict(sc)

    async def update(
        self,
        scope_id: str,
        *,
        status: str | None = None,
        evidence: str | None = None,
        why: str | None = None,
        ability_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            key = uuid.UUID(str(scope_id))
        except ValueError:
            raise LookupError(f"no scope with id {scope_id}") from None
        async with self._sf() as s:
            sc = await s.get(Scope, key)
            if sc is None:
                raise LookupError(f"no scope with id {scope_id}")
            if status is not None:
                if status not in SCOPE_STATUSES:
                    raise ValueError(f"status must be one of {SCOPE_STATUSES}")
                sc.status = status
            if evidence is not None:
                sc.evidence = evidence.strip()
            if why is not None:
                sc.why = why.strip()
            if ability_id is not None:
                sc.ability_id = self._parse_ability_id(ability_id)
            await s.commit()
            return _scope_dict(sc)

    async def list(self) -> list[dict[str, Any]]:
        async with self._sf() as s:
            m = await self._active(s)
            if m is None:
                return []
            q = (
                select(Scope)
                .where(Scope.mission_id == m.id)
                .order_by(Scope.kind, Scope.created_at)
            )
            rows = (await s.execute(q)).scalars().all()
            return [_scope_dict(sc) for sc in rows]

    async def stage_set(self, stage: str) -> dict[str, Any]:
        if stage not in SETUP_STAGES:
            raise ValueError(f"stage must be one of {SETUP_STAGES}")
        async with self._sf() as s:
            m = await self._active(s)
            if m is None:
                raise ValueError("no active mission — set a mission first")
            m.setup_stage = stage
            m.stage_entered_at = _utcnow()
            await s.commit()
        return {"setup_stage": stage}

    async def current_state_set(self, text: str) -> dict[str, Any]:
        text = " ".join((text or "").split())
        if not text:
            raise ValueError("current state must be non-empty — one plain sentence")
        if len(text) > 200:
            raise ValueError(
                "current state is one line the owner reads at a glance — "
                f"say it in under 200 characters (got {len(text)})"
            )
        async with self._sf() as s:
            m = await self._active(s)
            if m is None:
                raise ValueError("no active mission — set a mission first")
            m.current_state = text
            m.current_state_at = _utcnow()
            await s.commit()
        return {"current_state": text}

    async def phase_set(self, to: str) -> dict[str, Any]:
        if to not in AGENT_PHASES:
            raise ValueError(f"phase must be one of {AGENT_PHASES}")
        async with self._sf() as s:
            m = await self._active(s)
            if m is None:
                raise ValueError("no active mission — set a mission first")
            m.agent_phase = to
            m.phase_entered_at = _utcnow()
            await s.commit()
        return {"agent_phase": to}

    async def plan_change_add(self, entry: str, *, kind: str = "refine") -> dict[str, Any]:
        entry = (entry or "").strip()
        if not entry:
            raise ValueError("plan-change entry must be non-empty")
        if kind not in PLAN_CHANGE_KINDS:
            raise ValueError(f"kind must be one of {PLAN_CHANGE_KINDS}")
        async with self._sf() as s:
            m = await self._active(s)
            if m is None:
                raise ValueError("no active mission — set a mission first")
            pc = PlanChange(mission_id=m.id, entry=entry, kind=kind)
            s.add(pc)
            result = {
                "entry": pc.entry,
                "kind": kind,
            }
            if kind == "role_pivot":
                # the bump and the log entry commit together — a pivot the
                # pane can't stamp (or a stamp with no entry) must not exist
                m.role_version = (m.role_version or 1) + 1
                result["role_version"] = m.role_version
            await s.commit()
            result["date"] = pc.created_at.date().isoformat()
            return result

    async def plan_changes(self) -> list[dict[str, Any]]:
        async with self._sf() as s:
            m = await self._active(s)
            if m is None:
                return []
            q = (
                select(PlanChange)
                .where(PlanChange.mission_id == m.id)
                .order_by(PlanChange.created_at)
            )
            rows = (await s.execute(q)).scalars().all()
            return [
                {
                    "entry": pc.entry,
                    "kind": getattr(pc, "kind", "refine") or "refine",
                    "date": pc.created_at.date().isoformat(),
                }
                for pc in rows
            ]


def render_charter_page(
    state: dict[str, Any],
    scopes: list[dict[str, Any]],
    plan_changes: list[dict[str, Any]],
) -> str:
    """The [[role-charter]] page body: stage marker → role statement → scopes
    grouped by kind → append-only Plan changes."""
    stage_word = STAGE_LABELS.get(state["setup_stage"], (state["setup_stage"], ""))[0]
    lines = [
        f"**Where I am: {state['agent_phase']} phase — {stage_word}**",
        "",
        f"Role: {state['statement']}",
        "",
        "## What this job needs",
    ]
    if not scopes:
        lines.append(
            "*Nothing here yet — I'm still listing what this job needs "
            "(knowledge, people, communication paths, tools & data access, "
            "workflow & approval points, playbooks, routines & feedback).*"
        )
    else:
        by_kind: dict[str, list[dict[str, Any]]] = {}
        for sc in scopes:
            by_kind.setdefault(sc["kind"], []).append(sc)
        for kind in SCOPE_KINDS:
            group = by_kind.get(kind)
            if not group:
                continue
            lines.append(f"### {_KIND_LABEL[kind]}")
            for sc in group:
                mark = _STATUS_MARK.get(sc["status"], "•")
                word = _STATUS_WORD.get(sc["status"], sc["status"])
                lines.append(f"- {mark} **{sc['name']}** — {word}")
                if sc["why"]:
                    lines.append(f"  - why: {sc['why']}")
                if sc["evidence"]:
                    lines.append(f"  - evidence: {sc['evidence']}")
    lines += ["", "## Plan changes"]
    if not plan_changes:
        lines.append("*None yet — a plan that never changes after week 1 means "
                     "you stopped learning.*")
    else:
        for pc in plan_changes:
            mark = "🔄 ROLE PIVOT — " if pc.get("kind") == "role_pivot" else ""
            lines.append(f"- {pc['date']}: {mark}{pc['entry']}")
    lines.append("")
    return "\n".join(lines)


async def _mirror_to_wiki(ctx: PluginContext, store: ScopeStore) -> str:
    from . import wikibind

    try:
        wiki = ctx.provider_registry.get("wiki")
    except Exception:  # noqa: BLE001
        return "wiki provider unavailable — charter page not mirrored"
    try:
        state = await store.state()
        if state is None:
            return "no active mission — charter page not mirrored"
        wk = await wikibind.wiki_kwargs(ctx, store._sf)  # noqa: SLF001
        scopes = await store.list()
        competent = sum(1 for sc in scopes if sc["status"] == "competent")
        stage_word = STAGE_LABELS.get(state["setup_stage"], (state["setup_stage"], ""))[0]
        await wiki.upsert_page(
            CHARTER_SLUG,
            CHARTER_TITLE,
            render_charter_page(state, scopes, await store.plan_changes()),
            summary=(
                f"{state['agent_phase']} phase, {stage_word} — "
                f"{competent}/{len(scopes)} scopes competent"
            ),
            note="role charter write-through",
            **wk,
        )
        return "ok"
    except Exception as e:  # noqa: BLE001
        log.warning("charter wiki mirror failed", exc_info=True)
        return f"wiki mirror failed: {e}"


async def ensure_charter_mirror(ctx: PluginContext, store: ScopeStore) -> str:
    """Upgrade path (on-load): a pre-9A mission never had a [[role-charter]]
    page — seed it once when a mission exists and the page is absent, so the
    upgraded agent's charter surface appears without a mission_set."""
    from . import wikibind

    state = await store.state()
    if state is None:
        return "no mission"
    try:
        wiki = ctx.provider_registry.get("wiki")
        wk = await wikibind.wiki_kwargs(ctx, store._sf)  # noqa: SLF001
        if await wiki.get_page(CHARTER_SLUG, **wk) is not None:
            return "already present"
    except Exception:  # noqa: BLE001
        return "wiki provider unavailable"
    return await _mirror_to_wiki(ctx, store)


def register_tools(ctx: PluginContext, store: ScopeStore) -> None:
    from . import telemetry

    async def _set(
        kind: str, name: str, why: str = "", ability_id: str | None = None
    ) -> dict[str, Any]:
        try:
            scope = await store.add(kind, name, why=why, ability_id=ability_id)
        except ValueError as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "scope"})
        return {"scope": scope, "wiki_mirror": await _mirror_to_wiki(ctx, store)}

    async def _update(
        id: str,
        status: str | None = None,
        evidence: str | None = None,
        why: str | None = None,
        ability_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            scope = await store.update(
                id, status=status, evidence=evidence, why=why, ability_id=ability_id
            )
        except (ValueError, LookupError) as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "scope"})
        return {"scope": scope, "wiki_mirror": await _mirror_to_wiki(ctx, store)}

    async def _list() -> dict[str, Any]:
        state = await store.state()
        scopes = await store.list()
        if not scopes:
            return {
                "state": state,
                "scopes": [],
                "note": (
                    "no scopes chartered yet — decompose the role with "
                    "scope_set across the seven kinds and track competency "
                    "per scope"
                ),
            }
        return {"state": state, "scopes": scopes}

    async def _stage(stage: str) -> dict[str, Any]:
        try:
            result = await store.stage_set(stage)
        except ValueError as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "stage", "stage": stage})
        result["wiki_mirror"] = await _mirror_to_wiki(ctx, store)
        result["reminder"] = (
            "if what you're doing changed, refresh your one-line status with "
            "current_state_set"
        )
        return result

    async def _current_state(text: str) -> dict[str, Any]:
        try:
            result = await store.current_state_set(text)
        except ValueError as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "current_state"})
        return result

    async def _note(entry: str, kind: str = "refine") -> dict[str, Any]:
        try:
            change = await store.plan_change_add(entry, kind=kind)
        except ValueError as e:
            return {"error": str(e)}
        if kind == "role_pivot":
            await telemetry.emit_ui_event(ctx, "changed", {"what": "role_pivot"})
        return {"plan_change": change, "wiki_mirror": await _mirror_to_wiki(ctx, store)}

    async def _advance(to: str, waive: list | None = None, reason: str = "") -> dict[str, Any]:
        waive = [str(w) for w in (waive or [])]
        if to not in AGENT_PHASES:
            return {"error": f"phase must be one of {AGENT_PHASES}"}
        state = await store.state()
        if state is None:
            return {"error": "no active mission — set a mission first"}
        if to == "work":
            scopes = await store.list()
            if not scopes:
                return {
                    "error": (
                        "no scopes chartered yet — a graduation with nothing "
                        "chartered is meaningless; scope_set the role first"
                    )
                }
            blockers = [
                sc for sc in scopes if sc["status"] != "competent" and sc["id"] not in waive
            ]
            if blockers:
                listed = ", ".join(f"'{sc['name']}' ({sc['status']})" for sc in blockers)
                return {
                    "error": (
                        f"competency gate: not every scope is competent — {listed}. "
                        "Reach competency, or pass waive=[scope ids] to graduate "
                        "anyway (waivers are recorded in the charter)."
                    )
                }
            for sc in scopes:
                if sc["id"] in waive:
                    note = (
                        f"Graduated to work with scope '{sc['name']}' waived "
                        f"(status: {sc['status']})"
                    )
                    if reason:
                        note += f" — {reason}"
                    await store.plan_change_add(note)
        try:
            result = await store.phase_set(to)
        except ValueError as e:
            return {"error": str(e)}
        if to == "setup":
            await store.plan_change_add(
                f"Returned to setup phase — {reason or 'unspecified reason'}"
            )
        await telemetry.emit_ui_event(ctx, "changed", {"what": "phase", "phase": to})
        result["wiki_mirror"] = await _mirror_to_wiki(ctx, store)
        result["reminder"] = (
            "your phase just changed — refresh your one-line status with "
            "current_state_set so the owner's pane says what you're doing now"
        )
        return result

    defs: list[tuple[ToolDef, Any]] = [
        (
            ToolDef(
                name="scope_set",
                description=(
                    "Charter one scope of your role — an area you must become "
                    "competent in before you can truly do the job. Kinds: "
                    "knowledge, people, communication_paths, tools_data_access, "
                    "workflow_approval, playbooks, routines_feedback. Created "
                    "as status=missing; mirrors to [[role-charter]]. Attach "
                    "each scope to the ability it serves (ability_id from "
                    "ability_list) — every scope belongs to an ability."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": list(SCOPE_KINDS)},
                        "name": {
                            "type": "string",
                            "description": "The scope — one concrete area, e.g. 'read access to the funnel analytics'.",
                        },
                        "why": {
                            "type": "string",
                            "description": "Why the role needs it.",
                        },
                        "ability_id": {
                            "type": "string",
                            "description": "The ability this scope serves (from ability_list).",
                        },
                    },
                    "required": ["kind", "name"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _set,
        ),
        (
            ToolDef(
                name="scope_update",
                description=(
                    "Update a scope's competency honestly: missing → "
                    "in_progress → competent as you actually get there, with "
                    "evidence. BOTH directions are legal — when a later "
                    "learning invalidates earlier work, regress the scope "
                    "(competent → in_progress) and say why."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "The scope id (from scope_list)."},
                        "status": {"type": "string", "enum": list(SCOPE_STATUSES)},
                        "evidence": {
                            "type": "string",
                            "description": "What proves the status — a wiki page, a validated run, an owner confirmation.",
                        },
                        "why": {"type": "string"},
                        "ability_id": {
                            "type": "string",
                            "description": "Re-attach the scope to the ability it serves (from ability_list).",
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
                name="scope_list",
                description=(
                    "Your role charter — every scope with kind, status, and "
                    "evidence, plus your current phase (setup/work), "
                    "setup-arc stage, and stage_age_days (server-computed "
                    "days in the current stage). Read it before planning "
                    "any setup work."
                ),
                parameters={"type": "object", "properties": {}},
                policy="auto_approve",
                risk_level="low",
            ),
            _list,
        ),
        (
            ToolDef(
                name="current_state_set",
                description=(
                    "Your one-line status, in your own words, shown verbatim "
                    "at the top of the owner's Missions pane under the "
                    "mission statement — what you are doing right now at the "
                    "mission level (e.g. 'Working on making myself good "
                    "enough for this job — mapping the glaze catalog first.'). "
                    "Plain words, first person, no internal codes, under 200 "
                    "characters. Refresh it whenever what you're doing "
                    "changes: after mission_set, a stage or phase change, a "
                    "weekly review, or a shift in focus. scope_list shows "
                    "current_state_age_days — if it's older than a few days, "
                    "it's probably stale."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The status line, one plain sentence in your own voice.",
                        },
                    },
                    "required": ["text"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _current_state,
        ),
        (
            ToolDef(
                name="stage_set",
                description=(
                    "Mark the furthest setup-arc stage actually reached "
                    "(S0-S5 — the ladder is defined once in your "
                    "instructions: S2 = shared, S3 = owner APPROVED the "
                    "job-description + success-criteria, S4 = workflow "
                    "validated, S5 = feedback signals live). S3 and above require the "
                    "owner's explicit word; regress when a learning reopens "
                    "earlier work."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "stage": {"type": "string", "enum": list(SETUP_STAGES)},
                    },
                    "required": ["stage"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _stage,
        ),
        (
            ToolDef(
                name="plan_change_note",
                description=(
                    "Append a dated entry to the charter's Plan-changes log: "
                    "what you added/dropped/reopened and the learning that "
                    "caused it. Every real plan change gets one — the living "
                    "plan's audit trail the owner can read. kind='refine' "
                    "(default) for within-ability learning you absorbed "
                    "yourself; kind='role_pivot' ONLY when the learning "
                    "changes the SHAPE of the role — a pivot bumps your job "
                    "description's draft version and surfaces to the owner "
                    "for input."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "entry": {
                            "type": "string",
                            "description": "The change + the learning, one or two lines. For a pivot: what I discovered → what changes → what I need from you.",
                        },
                        "kind": {
                            "type": "string",
                            "enum": list(PLAN_CHANGE_KINDS),
                            "default": "refine",
                        },
                    },
                    "required": ["entry"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _note,
        ),
        (
            ToolDef(
                name="phase_advance",
                description=(
                    "Flip your macro-phase. to='work' proposes GRADUATION — "
                    "allowed only when every scope is competent (or explicitly "
                    "waived with waive=[scope ids]; waivers are recorded in "
                    "the charter); the owner's approval of this call IS the "
                    "graduation sign-off. to='setup' is always allowed — "
                    "returning to setup when the role shifted is honesty, "
                    "not failure."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "enum": list(AGENT_PHASES)},
                        "waive": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Scope ids to waive past the competency gate (recorded in the charter).",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Why now — cited in the charter's Plan-changes log.",
                        },
                    },
                    "required": ["to"],
                },
                # the core's dispatch gate knows auto_approve /
                # prompt_first_time_only / prompt_always / block — an unknown
                # policy string is NOT gated (QA: "ask" fired straight through)
                policy="prompt_always",
                risk_level="medium",
            ),
            _advance,
        ),
    ]
    for tool_def, handler in defs:
        gating.register_tool(ctx, tool_def, handler)
