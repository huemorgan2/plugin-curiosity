"""planning.py — the numbered setup-plan ledger (phase14: plan, ask, act).

The incident: once a mission lands, the agent assumes it knows how to set
itself up and builds its scaffolding unasked. This module makes setup run
on NUMBERED PLANS instead — the agent researches Luna's real capabilities,
writes plan `[[setup-plans/001-<name>]]` (full technical detail), and the
owner's explicit OK is the ONLY thing that releases execution. Every
execution — success or failure — leaves an execution-summary page; every
amendment or retry is a NEW number. The whole history stays on the wiki.

The gates live in the tool layer, not in prose (phase11 doctrine):

  - ``setup_plan_open`` refuses while a plan is approved/executing (a
    still-draft predecessor is superseded — that IS the amendment path);
  - ``setup_plan_approve`` refuses while the plan's wiki page is missing
    (the owner cannot approve a plan they cannot read) and records the
    owner's words; it is what spawns the execution pass;
  - ``setup_plan_start`` refuses unless the plan is approved;
  - ``setup_plan_close`` refuses until the execution-summary page exists;
  - ``execution_gate`` (wired into scope_set / stage_set / ability_upsert /
    goal_set by _activate) refuses scaffolding for an S0 setup mission
    outside an executing plan — chat turns cannot tangent past the ledger.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from luna_sdk import PluginContext, ToolDef
from sqlalchemy import func, select

from . import gating
from . import gating
from .models import Mission, SetupPlan

log = logging.getLogger("plugin-curiosity")

PLAN_STATUSES = ("draft", "approved", "executing", "done", "failed", "superseded")
# statuses that block a new setup_plan_open (draft is NOT live: opening over
# a draft supersedes it — the amendment path)
LIVE_STATUSES = ("approved", "executing")
# statuses the "current plan" pointer scans, newest first
OPEN_STATUSES = ("draft", "approved", "executing")

PLANS_INDEX_SLUG = "setup-plans"
SUMMARY_SUFFIX = "-execution-summary"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _kebab(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug[:80] or "plan"


def plan_slug(seq: int, name: str) -> str:
    return f"setup-plans/{seq:03d}-{_kebab(name)}"


def _dict(p: SetupPlan) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "seq": p.seq,
        "label": f"{p.seq:03d}-{_kebab(p.name)}",
        "name": p.name,
        "slug": p.slug,
        "summary_slug": p.summary_slug,
        "objective": p.objective,
        "status": p.status,
        "decision_note": p.decision_note,
        "outcome_note": p.outcome_note,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "approved_at": p.approved_at.isoformat() if p.approved_at else None,
        "started_at": p.started_at.isoformat() if p.started_at else None,
        "closed_at": p.closed_at.isoformat() if p.closed_at else None,
    }


class PlanStore:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    async def _mission(self, s) -> Mission | None:
        q = (
            select(Mission)
            .where(Mission.active.is_(True))
            .order_by(Mission.created_at.desc())
        )
        return (await s.execute(q)).scalars().first()

    async def _current(self, s, mission_id) -> SetupPlan | None:
        q = (
            select(SetupPlan)
            .where(
                SetupPlan.mission_id == mission_id,
                SetupPlan.status.in_(OPEN_STATUSES),
            )
            .order_by(SetupPlan.seq.desc())
        )
        return (await s.execute(q)).scalars().first()

    async def current(self) -> dict[str, Any] | None:
        """The one plan in flight (draft/approved/executing), or None."""
        async with self._sf() as s:
            mission = await self._mission(s)
            if mission is None:
                return None
            plan = await self._current(s, mission.id)
            return _dict(plan) if plan is not None else None

    async def open(self, name: str, objective: str = "") -> dict[str, Any]:
        """Allocate the next numbered plan as a draft. A live (approved or
        executing) plan refuses; a still-draft predecessor is superseded —
        every amendment is a new number, never an edit."""
        if not str(name).strip():
            raise ValueError("name is required — one short kebab-case handle")
        async with self._sf() as s:
            mission = await self._mission(s)
            if mission is None:
                raise LookupError("no active mission — set a mission first")
            live = await self._current(s, mission.id)
            superseded = None
            if live is not None:
                if live.status in LIVE_STATUSES:
                    raise ValueError(
                        f"plan {live.seq:03d} ({live.name}) is {live.status} — "
                        "finish it (setup_plan_start / setup_plan_close) "
                        "before opening the next one"
                    )
                live.status = "superseded"
                superseded = f"{live.seq:03d}-{_kebab(live.name)}"
            max_seq = (
                await s.execute(
                    select(func.max(SetupPlan.seq)).where(
                        SetupPlan.mission_id == mission.id
                    )
                )
            ).scalar_one_or_none() or 0
            seq = int(max_seq) + 1
            slug = plan_slug(seq, name)
            plan = SetupPlan(
                mission_id=mission.id,
                seq=seq,
                name=str(name).strip(),
                slug=slug,
                summary_slug=slug + SUMMARY_SUFFIX,
                objective=str(objective).strip(),
            )
            s.add(plan)
            await s.commit()
            await s.refresh(plan)
            out = _dict(plan)
            if superseded:
                out["superseded"] = superseded
            return out

    async def approve(self, owner_words: str) -> dict[str, Any]:
        """draft → approved, recording the owner's words verbatim."""
        if not str(owner_words).strip():
            raise ValueError(
                "owner_words is required — the owner's OK, verbatim; if you "
                "don't have their words, you don't have their OK"
            )
        async with self._sf() as s:
            mission = await self._mission(s)
            if mission is None:
                raise LookupError("no active mission")
            plan = await self._current(s, mission.id)
            if plan is None:
                raise LookupError(
                    "no plan on the desk — setup_plan_open one and write its "
                    "wiki page first"
                )
            if plan.status != "draft":
                raise ValueError(
                    f"plan {plan.seq:03d} is already {plan.status} — approval "
                    "applies to a draft"
                )
            plan.status = "approved"
            plan.decision_note = str(owner_words).strip()
            plan.approved_at = _utcnow()
            await s.commit()
            await s.refresh(plan)
            return _dict(plan)

    async def start(self) -> dict[str, Any]:
        """approved → executing. THE gate: without an approved plan there is
        nothing to start, and the scaffolding tools stay refused."""
        async with self._sf() as s:
            mission = await self._mission(s)
            if mission is None:
                raise LookupError("no active mission")
            plan = await self._current(s, mission.id)
            if plan is None:
                raise LookupError(
                    "no plan on the desk — nothing is approved, nothing runs"
                )
            if plan.status != "approved":
                raise ValueError(
                    f"plan {plan.seq:03d} is {plan.status} — only an APPROVED "
                    "plan starts; the owner's OK (setup_plan_approve) comes "
                    "first, and it comes from the owner"
                )
            plan.status = "executing"
            plan.started_at = _utcnow()
            await s.commit()
            await s.refresh(plan)
            return _dict(plan)

    async def close(self, outcome: str, note: str = "") -> dict[str, Any]:
        """executing → done|failed."""
        if outcome not in ("done", "failed"):
            raise ValueError("outcome must be 'done' or 'failed'")
        async with self._sf() as s:
            mission = await self._mission(s)
            if mission is None:
                raise LookupError("no active mission")
            plan = await self._current(s, mission.id)
            if plan is None or plan.status != "executing":
                raise ValueError(
                    "no executing plan — close follows setup_plan_start"
                )
            plan.status = outcome
            plan.outcome_note = str(note).strip()
            plan.closed_at = _utcnow()
            await s.commit()
            await s.refresh(plan)
            return _dict(plan)

    async def list(self) -> list[dict[str, Any]]:
        """The full numbered ledger for the active mission, oldest first."""
        async with self._sf() as s:
            mission = await self._mission(s)
            if mission is None:
                return []
            q = (
                select(SetupPlan)
                .where(SetupPlan.mission_id == mission.id)
                .order_by(SetupPlan.seq.asc())
            )
            return [_dict(p) for p in (await s.execute(q)).scalars().all()]


def render_plans_page(plans: list[dict[str, Any]]) -> str:
    if not plans:
        return (
            "# Setup plans\n\nNo setup plans yet. Every change to my setup "
            "starts as a numbered plan here, runs only on your OK, and "
            "leaves a numbered execution summary — success or failure.\n"
        )
    lines = [
        "# Setup plans",
        "",
        "Numbered plans + execution summaries — nothing ran without your OK.",
        "",
    ]
    for p in plans:
        entry = f"- **{p['seq']:03d} — {p['name']}** · {p['status']} · [[{p['slug']}]]"
        if p["status"] in ("done", "failed"):
            entry += f" · [[{p['summary_slug']}]]"
        if p["decision_note"]:
            entry += f' · your words: "{p["decision_note"]}"'
        lines.append(entry)
    lines.append("")
    return "\n".join(lines)


async def _mirror_to_wiki(ctx: PluginContext, store: PlanStore) -> str:
    from . import wikibind

    try:
        wiki = ctx.provider_registry.get("wiki")
    except Exception:  # noqa: BLE001
        return "wiki provider unavailable — plan ledger not mirrored"
    try:
        wk = await wikibind.wiki_kwargs(ctx, store._sf)  # noqa: SLF001
        plans = await store.list()
        await wiki.upsert_page(
            PLANS_INDEX_SLUG, "Setup plans", render_plans_page(plans),
            summary=f"{len(plans)} plan(s)", note="plan ledger write-through",
            **wk,
        )
        return "ok"
    except Exception as e:  # noqa: BLE001
        log.warning("plan ledger wiki mirror failed", exc_info=True)
        return f"wiki mirror failed: {e}"


async def _page_exists(ctx: PluginContext, store: PlanStore, slug: str) -> bool | None:
    """True/False when the wiki answered; None when it cannot be consulted
    (the caller decides — approval refuses on None, close refuses too:
    without a readable page there is nothing reviewed/recorded)."""
    from . import wikibind

    try:
        wiki = ctx.provider_registry.get("wiki")
    except Exception:  # noqa: BLE001
        return None
    try:
        wk = await wikibind.wiki_kwargs(ctx, store._sf)  # noqa: SLF001
        return (await wiki.get_page(slug, **wk)) is not None
    except Exception:  # noqa: BLE001
        return None


def execution_gate(mission_store, plan_store: PlanStore):
    """The scaffolding gate, tool layer: an async callable returning None
    (allowed) or an error dict (refused). Wired by _activate into the
    CREATE tools — scope_set, stage_set, ability_upsert, goal_set. Updates
    stay open: refining what an approved execution built is not a new
    execution. Grandfathering: missionless turns, work-phase missions, and
    missions already past S0 (their scaffolding predates the ledger) are
    never gated."""

    async def gate() -> dict[str, Any] | None:
        try:
            mission = await mission_store.get()
        except Exception:  # noqa: BLE001 — a broken probe must not brick tools
            return None
        if mission is None:
            return None  # the mission gate owns missionless behavior
        if mission.get("agent_phase") == "work":
            return None
        if mission.get("setup_stage") not in (None, "S0"):
            return None
        try:
            plan = await plan_store.current()
        except Exception:  # noqa: BLE001
            return None
        if plan is not None and plan["status"] == "executing":
            return None
        return {
            "error": "setup runs on numbered plans — nothing scaffolds "
            "before the owner's OK",
            "hint": (
                "your setup executes only inside an approved plan: "
                "setup_plan_open, write the full technical plan at its "
                "wiki slug, put it on the owner's desk, and WAIT for "
                "their explicit OK (then setup_plan_approve with their "
                "words — execution runs from there). Current plan: "
                + (
                    f"{plan['label']} ({plan['status']})"
                    if plan
                    else "none — open one"
                )
            ),
        }

    return gate


def register_tools(ctx: PluginContext, store: PlanStore, mission_store) -> None:
    from . import research, telemetry

    async def _open(name: str, objective: str = "") -> dict[str, Any]:
        try:
            plan = await store.open(name, objective=objective)
        except (ValueError, LookupError) as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "setup_plan"})
        return {
            "plan": plan,
            "wiki_mirror": await _mirror_to_wiki(ctx, store),
            "next": (
                f"wiki_write the FULL technical plan at '{plan['slug']}' "
                "now (exact sections required), then put it on the owner's "
                "desk: point them at the page and ASK for their OK. You "
                "execute NOTHING from it until their explicit OK lands in "
                "chat — silence is never a yes."
            ),
        }

    async def _approve(owner_words: str) -> dict[str, Any]:
        current = await store.current()
        if current is not None and current["status"] == "draft":
            exists = await _page_exists(ctx, store, current["slug"])
            if exists is not True:
                return {
                    "error": (
                        f"the plan page '{current['slug']}' does not exist — "
                        "the owner cannot approve a plan they cannot read. "
                        "wiki_write it first, then ask for their OK again."
                    )
                }
        try:
            plan = await store.approve(owner_words)
        except (ValueError, LookupError) as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "setup_plan"})
        out: dict[str, Any] = {
            "plan": plan,
            "wiki_mirror": await _mirror_to_wiki(ctx, store),
        }
        mission = await mission_store.get()
        if mission is not None:
            out["execution"] = await research.spawn_plan_execution_once(
                ctx, store._sf, mission, plan  # noqa: SLF001
            )
        return out

    async def _start() -> dict[str, Any]:
        try:
            plan = await store.start()
        except (ValueError, LookupError) as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "setup_plan"})
        return {
            "plan": plan,
            "wiki_mirror": await _mirror_to_wiki(ctx, store),
            "next": (
                f"execute EXACTLY what [[{plan['slug']}]] says — nothing "
                "more. When done (or when anything fails), wiki_write the "
                f"summary at '{plan['summary_slug']}' FIRST, then "
                "setup_plan_close."
            ),
        }

    async def _close(outcome: str, note: str = "") -> dict[str, Any]:
        current = await store.current()
        if current is not None and current["status"] == "executing":
            exists = await _page_exists(ctx, store, current["summary_slug"])
            if exists is not True:
                return {
                    "error": (
                        "no execution summary on the wiki — every "
                        "execution, success or failure, leaves one. "
                        f"wiki_write '{current['summary_slug']}' first "
                        "(What ran / What worked / What failed or was "
                        "skipped / Next), then close."
                    )
                }
        try:
            plan = await store.close(outcome, note=note)
        except (ValueError, LookupError) as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "setup_plan"})
        return {
            "plan": plan,
            "wiki_mirror": await _mirror_to_wiki(ctx, store),
            "next": (
                "tell the owner what happened, short and honest. Anything "
                "left undone, failed, or newly discovered becomes the NEXT "
                "numbered plan (setup_plan_open) — drafted, on their desk, "
                "and NOT executed until their fresh OK."
            ),
        }

    async def _list() -> dict[str, Any]:
        plans = await store.list()
        if not plans:
            return {
                "plans": [],
                "note": (
                    "no setup plans yet — setup happens only through "
                    "numbered, owner-approved plans (setup_plan_open)"
                ),
            }
        return {"plans": plans}

    defs: list[tuple[ToolDef, Any]] = [
        (
            ToolDef(
                name="setup_plan_open",
                description=(
                    "Open the next NUMBERED setup plan (001, 002, …) as a "
                    "draft. Setup never runs on your own judgment: every "
                    "change to your setup is written as a plan the owner "
                    "reads and OKs first. Returns the wiki slug you must "
                    "write the full technical plan to. Refused while a "
                    "plan is approved or executing; opening over an "
                    "unapproved draft supersedes it (amendments are new "
                    "numbers, never edits)."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Short kebab-case handle, e.g. 'initial-setup' or 'whatsapp-channel'.",
                        },
                        "objective": {
                            "type": "string",
                            "description": "One line: what this plan sets up and why now.",
                        },
                    },
                    "required": ["name"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _open,
        ),
        (
            ToolDef(
                name="setup_plan_approve",
                description=(
                    "Record the owner's explicit OK on the current draft "
                    "plan — and start its execution. Call ONLY when the "
                    "owner's latest message plainly approves the plan "
                    "('ok', 'go', 'approved', 'run it'); NEVER on silence, "
                    "NEVER on your own judgment, never because waiting "
                    "feels slow. owner_words carries their approval "
                    "verbatim. Refused while the plan's wiki page is "
                    "missing — the owner cannot approve a plan they "
                    "cannot read."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "owner_words": {
                            "type": "string",
                            "description": "The owner's OK, verbatim, from their latest message.",
                        },
                    },
                    "required": ["owner_words"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _approve,
        ),
        (
            ToolDef(
                name="setup_plan_start",
                description=(
                    "Mark the approved plan as executing — the FIRST call "
                    "of the execution turn. Refused unless the current "
                    "plan is APPROVED (the owner's OK, recorded via "
                    "setup_plan_approve, is the only path here). While no "
                    "plan is executing, the scaffolding tools (scope_set, "
                    "ability_upsert, goal_set, stage_set) refuse."
                ),
                parameters={"type": "object", "properties": {}},
                policy="auto_approve",
                risk_level="low",
            ),
            _start,
        ),
        (
            ToolDef(
                name="setup_plan_close",
                description=(
                    "Close the executing plan as done or failed. Refused "
                    "until the execution-summary wiki page exists at "
                    "'<plan-slug>-execution-summary' — EVERY execution, "
                    "success or failure, leaves that artifact. Anything "
                    "left undone becomes the next numbered plan, which "
                    "waits for a fresh owner OK."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "outcome": {
                            "type": "string",
                            "enum": ["done", "failed"],
                        },
                        "note": {
                            "type": "string",
                            "description": "One line on how it went.",
                        },
                    },
                    "required": ["outcome"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _close,
        ),
        (
            ToolDef(
                name="setup_plan_list",
                description=(
                    "The numbered setup-plan ledger for the active mission "
                    "— every plan, its status, its wiki page, and its "
                    "execution summary. The transparent history of how "
                    "you set yourself up."
                ),
                parameters={"type": "object", "properties": {}},
                policy="auto_approve",
                risk_level="low",
            ),
            _list,
        ),
    ]
    for tool_def, handler in defs:
        ctx.tool_registry.register("plugin-curiosity", gating.stamp_group(tool_def), handler)
