"""feedback.py — acting on owner feedback + the reasons ledger (10.006).

The gap this closes: owner criticism produced empathy, not change — "your
report is shit" got a perfect acknowledgment and an untouched playbook. Three
structural pieces:

1. [[owner-decisions]] — the reasons ledger. Every owner instruction lands as
   a row WITH ITS WHY (decision_log), so later feedback that contradicts an
   earlier instruction can be reconciled out loud: keep, demote, or replace.
   DB is the source of truth; the wiki page is a rebuilt mirror (same
   write-through pattern as goals/loops — no read-modify-append races).
2. feedback_note — owner feedback is DATA with a debt attached: a note whose
   `changed_refs` is empty is acknowledged-but-not-acted-on, and it stays a
   red item on every heartbeat and weekly review until feedback_act closes it
   with the refs of what actually changed.
3. design_map — "look at all your prompts" gets a handle: one call returns
   the live behavior surface (identity + personality, mission, wiki pages,
   playbooks, triggers, unactioned feedback) so the audit step of the
   feedback contract has ground truth instead of guesses.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text as _sql

from luna_sdk import PluginContext, ToolDef

from .models import FeedbackNote, Mission, OwnerDecision

log = logging.getLogger("plugin-curiosity")

DECISIONS_SLUG = "owner-decisions"

DECISION_SOURCES = ("setup", "instruction", "feedback")
DECISION_STATUSES = ("active", "demoted", "replaced")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _decision_dict(d: OwnerDecision) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "asked": d.asked,
        "why": d.why,
        "lives_in": d.lives_in,
        "source": d.source,
        "status": d.status,
        "status_note": d.status_note,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


def _feedback_dict(f: FeedbackNote) -> dict[str, Any]:
    return {
        "id": str(f.id),
        "quote": f.quote,
        "diagnosis": f.diagnosis,
        "changed_refs": f.changed_refs,
        "reconciled": f.reconciled,
        "acted": bool(f.acted_at),
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


class FeedbackStore:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    async def _mission_id(self, s) -> uuid.UUID | None:
        q = select(Mission.id).where(Mission.active.is_(True)).order_by(Mission.created_at.desc())
        return (await s.execute(q)).scalars().first()

    # -- decisions ----------------------------------------------------------
    async def decision_add(
        self, asked: str, why: str = "", lives_in: str = "", source: str = "instruction"
    ) -> dict[str, Any]:
        if not asked.strip():
            raise ValueError("asked is required — the owner's instruction, in their words")
        if source not in DECISION_SOURCES:
            raise ValueError(f"source must be one of {DECISION_SOURCES}")
        async with self._sf() as s:
            d = OwnerDecision(
                mission_id=await self._mission_id(s),
                asked=asked.strip(), why=why.strip(), lives_in=lives_in.strip(),
                source=source,
            )
            s.add(d)
            await s.commit()
            await s.refresh(d)
            return _decision_dict(d)

    async def decision_restate(
        self, id: str, status: str, status_note: str
    ) -> dict[str, Any]:
        """Reconcile an earlier decision against new feedback: demote it
        (kept, but no longer front-and-center) or mark it replaced. The note
        is REQUIRED — it is the owner-readable why."""
        if status not in ("demoted", "replaced", "active"):
            raise ValueError("status must be demoted, replaced, or active")
        if not status_note.strip():
            raise ValueError("status_note is required — say how this was reconciled")
        async with self._sf() as s:
            d = await s.get(OwnerDecision, uuid.UUID(id))
            if d is None:
                raise LookupError(f"no decision {id}")
            d.status = status
            d.status_note = status_note.strip()
            await s.commit()
            await s.refresh(d)
            return _decision_dict(d)

    async def decision_list(self) -> list[dict[str, Any]]:
        async with self._sf() as s:
            rows = (
                (await s.execute(select(OwnerDecision).order_by(OwnerDecision.created_at)))
                .scalars().all()
            )
            return [_decision_dict(d) for d in rows]

    # -- feedback -----------------------------------------------------------
    async def feedback_add(
        self, quote: str, diagnosis: str = "", changed_refs: str = "", reconciled: str = ""
    ) -> dict[str, Any]:
        if not quote.strip():
            raise ValueError("quote is required — the owner's feedback, in their words")
        async with self._sf() as s:
            f = FeedbackNote(
                mission_id=await self._mission_id(s),
                quote=quote.strip(), diagnosis=diagnosis.strip(),
                changed_refs=changed_refs.strip(), reconciled=reconciled.strip(),
                acted_at=_utcnow() if changed_refs.strip() else None,
            )
            s.add(f)
            await s.commit()
            await s.refresh(f)
            return _feedback_dict(f)

    async def feedback_act(
        self, id: str, changed_refs: str, reconciled: str = ""
    ) -> dict[str, Any]:
        if not changed_refs.strip():
            raise ValueError(
                "changed_refs is required — name what actually changed "
                "(playbook name+version, identity field, trigger name, wiki slug)"
            )
        async with self._sf() as s:
            f = await s.get(FeedbackNote, uuid.UUID(id))
            if f is None:
                raise LookupError(f"no feedback note {id}")
            f.changed_refs = changed_refs.strip()
            if reconciled.strip():
                f.reconciled = reconciled.strip()
            f.acted_at = _utcnow()
            await s.commit()
            await s.refresh(f)
            return _feedback_dict(f)

    async def feedback_list(self, unactioned_only: bool = False) -> list[dict[str, Any]]:
        async with self._sf() as s:
            q = select(FeedbackNote).order_by(FeedbackNote.created_at)
            if unactioned_only:
                q = q.where(FeedbackNote.acted_at.is_(None))
            rows = (await s.execute(q)).scalars().all()
            return [_feedback_dict(f) for f in rows]

    async def unactioned_count(self) -> int:
        return len(await self.feedback_list(unactioned_only=True))


# -- wiki mirror -------------------------------------------------------------

def render_decisions_page(
    decisions: list[dict[str, Any]], feedback: list[dict[str, Any]]
) -> str:
    """[[owner-decisions]] body: the reasons ledger the agent consults before
    changing itself, plus the feedback log with its acted/red state."""
    lines = [
        "What the owner asked of me and why — I read this before changing "
        "how I work, so new feedback gets reconciled against old asks "
        "instead of silently overwriting them.",
        "",
        "## Decisions",
        "",
    ]
    if not decisions:
        lines.append("*Nothing recorded yet.*")
    else:
        lines.append("| date | the ask (owner's words) | why | lives in | status |")
        lines.append("|---|---|---|---|---|")
        for d in decisions:
            date = (d["created_at"] or "")[:10]
            status = d["status"]
            if d["status_note"]:
                status += f" — {d['status_note']}"
            cells = [date, d["asked"], d["why"] or "—", d["lives_in"] or "—", status]
            lines.append("| " + " | ".join(c.replace("|", "/") for c in cells) + " |")
    lines += ["", "## Feedback log", ""]
    if not feedback:
        lines.append("*No feedback recorded yet.*")
    else:
        for f in feedback:
            date = (f["created_at"] or "")[:10]
            state = f"changed: {f['changed_refs']}" if f["acted"] else "NOT ACTED ON YET"
            lines.append(f"- {date}: \"{f['quote']}\" → {state}")
            if f["reconciled"]:
                lines.append(f"  - reconciled: {f['reconciled']}")
    lines.append("")
    return "\n".join(lines)


async def _mirror_to_wiki(ctx: PluginContext, store: FeedbackStore) -> str:
    from . import wikibind

    try:
        wiki = ctx.provider_registry.get("wiki")
    except Exception:  # noqa: BLE001
        return "wiki provider unavailable — owner-decisions not mirrored"
    try:
        wk = await wikibind.wiki_kwargs(ctx, store._sf)  # noqa: SLF001
        decisions = await store.decision_list()
        feedback = await store.feedback_list()
        open_count = sum(1 for f in feedback if not f["acted"])
        await wiki.upsert_page(
            DECISIONS_SLUG, "Owner decisions",
            render_decisions_page(decisions, feedback),
            summary=f"{len(decisions)} decision(s), {open_count} feedback item(s) open",
            note="reasons ledger write-through",
            **wk,
        )
        return "ok"
    except Exception as e:  # noqa: BLE001
        log.warning("owner-decisions wiki mirror failed", exc_info=True)
        return f"wiki mirror failed: {e}"


# -- design map ---------------------------------------------------------------

async def build_design_map(ctx: PluginContext, store: FeedbackStore) -> dict[str, Any]:
    """The live behavior surface, best-effort per source: anything
    unreachable is reported as such rather than omitted silently."""
    out: dict[str, Any] = {}

    # identity + personality (core table; lazy row — may not exist yet)
    try:
        async with store._sf() as s:  # noqa: SLF001
            row = (await s.execute(_sql("SELECT * FROM identity LIMIT 1"))).mappings().first()
        if row is None:
            out["identity"] = "no identity row yet (setup not started)"
        else:
            out["identity"] = {
                k: v for k, v in dict(row).items()
                if k in (
                    "name", "emoji", "mission", "persona", "owner_name",
                    "instructions", "tone", "verbosity", "formality",
                    "use_emoji", "proactive", "honesty_mode", "setup_completed",
                )
            }
    except Exception as e:  # noqa: BLE001
        out["identity"] = f"unreachable: {e}"

    # mission register
    try:
        async with store._sf() as s:  # noqa: SLF001
            m = (
                (await s.execute(select(Mission).where(Mission.active.is_(True))))
                .scalars().first()
            )
        out["mission"] = (
            {
                "statement": m.statement, "agent_phase": m.agent_phase,
                "setup_stage": m.setup_stage, "wiki_id": getattr(m, "wiki_id", None),
            }
            if m is not None else "no active mission"
        )
    except Exception as e:  # noqa: BLE001
        out["mission"] = f"unreachable: {e}"

    # wiki pages that steer behavior
    out["wiki_pages"] = [
        "job-description", "success-criteria", "role-charter", "mission-goals",
        "open-loops", "value-log", DECISIONS_SLUG, "setup-heartbeat",
    ]

    # playbooks (another plugin's tables — present only when it's installed)
    try:
        async with store._sf() as s:  # noqa: SLF001
            rows = (
                await s.execute(_sql(
                    "SELECT name, display_name, version, status, agent_autonomy, "
                    "when_to_use FROM playbooks"
                ))
            ).mappings().all()
        out["playbooks"] = [dict(r) for r in rows] or "none defined"
    except Exception:  # noqa: BLE001
        out["playbooks"] = "playbooks plugin not installed"

    # triggers (scheduler tools — cross-plugin, best-effort)
    try:
        lister = ctx.tool_registry.get("trigger_list").handler
        out["triggers"] = await lister()
    except KeyError:
        out["triggers"] = "trigger_list tool not available"
    except Exception as e:  # noqa: BLE001
        out["triggers"] = f"unreachable: {e}"

    out["feedback_unactioned"] = await store.unactioned_count()
    out["note"] = (
        "this is your whole behavior surface — when feedback arrives, the "
        "artifact producing the criticized behavior is on this map; find it "
        "and change it, then record it (feedback_note / feedback_act)"
    )
    return out


# -- tools --------------------------------------------------------------------

def register_tools(ctx: PluginContext, store: FeedbackStore) -> None:
    async def _decision_log(
        asked: str, why: str = "", lives_in: str = "", source: str = "instruction"
    ) -> dict[str, Any]:
        try:
            d = await store.decision_add(asked, why=why, lives_in=lives_in, source=source)
        except ValueError as e:
            return {"error": str(e)}
        return {"decision": d, "wiki_mirror": await _mirror_to_wiki(ctx, store)}

    async def _decision_restate(id: str, status: str, status_note: str) -> dict[str, Any]:
        try:
            d = await store.decision_restate(id, status, status_note)
        except (ValueError, LookupError) as e:
            return {"error": str(e)}
        return {"decision": d, "wiki_mirror": await _mirror_to_wiki(ctx, store)}

    async def _decision_list() -> dict[str, Any]:
        return {"decisions": await store.decision_list()}

    async def _feedback_note(
        quote: str, diagnosis: str = "", changed_refs: str = "", reconciled: str = ""
    ) -> dict[str, Any]:
        try:
            f = await store.feedback_add(
                quote, diagnosis=diagnosis, changed_refs=changed_refs, reconciled=reconciled
            )
        except ValueError as e:
            return {"error": str(e)}
        out: dict[str, Any] = {
            "feedback": f,
            "wiki_mirror": await _mirror_to_wiki(ctx, store),
        }
        if not f["acted"]:
            out["warning"] = (
                "recorded but NOT ACTED ON — this stays a red item on every "
                "heartbeat and weekly review until you change the implicated "
                "artifact (playbook_edit / update_self / trigger_update / "
                "wiki edit) and close it with feedback_act(id, changed_refs). "
                "If you can act now, act NOW, in this same turn."
            )
        return out

    async def _feedback_act(id: str, changed_refs: str, reconciled: str = "") -> dict[str, Any]:
        try:
            f = await store.feedback_act(id, changed_refs, reconciled=reconciled)
        except (ValueError, LookupError) as e:
            return {"error": str(e)}
        return {"feedback": f, "wiki_mirror": await _mirror_to_wiki(ctx, store)}

    async def _feedback_list(unactioned_only: bool = False) -> dict[str, Any]:
        items = await store.feedback_list(unactioned_only=unactioned_only)
        out: dict[str, Any] = {"feedback": items}
        red = [f for f in items if not f["acted"]]
        if red:
            out["red_items"] = (
                f"{len(red)} feedback item(s) not acted on — fix the artifact "
                "and close each with feedback_act before anything else"
            )
        return out

    async def _design_map() -> dict[str, Any]:
        return await build_design_map(ctx, store)

    defs: list[tuple[ToolDef, Any]] = [
        (
            ToolDef(
                name="decision_log",
                description=(
                    "Record an owner instruction/decision WITH ITS WHY in the "
                    "reasons ledger ([[owner-decisions]]). Use it the moment "
                    "the owner states a lasting preference — how to report, "
                    "what to include, style, priorities — and for every setup "
                    "answer that shapes how you work. lives_in names where "
                    "you implemented it (playbook, persona, report format)."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "asked": {
                            "type": "string",
                            "description": "The instruction, in the owner's words.",
                        },
                        "why": {
                            "type": "string",
                            "description": "Their reason, as best you know it.",
                        },
                        "lives_in": {
                            "type": "string",
                            "description": "Where it is implemented (playbook name, identity field, trigger, wiki page).",
                        },
                        "source": {"type": "string", "enum": list(DECISION_SOURCES)},
                    },
                    "required": ["asked"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _decision_log,
        ),
        (
            ToolDef(
                name="decision_restate",
                description=(
                    "Reconcile an earlier owner decision against new feedback "
                    "that contradicts or overlaps it: demoted (kept, but no "
                    "longer front-and-center — say where it moved), replaced, "
                    "or back to active. status_note is what the owner reads."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "The decision id (from decision_list)."},
                        "status": {"type": "string", "enum": ["demoted", "replaced", "active"]},
                        "status_note": {
                            "type": "string",
                            "description": "How you reconciled it, in owner words.",
                        },
                    },
                    "required": ["id", "status", "status_note"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _decision_restate,
        ),
        (
            ToolDef(
                name="decision_list",
                description=(
                    "The reasons ledger: every owner instruction with its why "
                    "and where it lives. READ THIS before changing how you "
                    "work in response to feedback — new feedback may "
                    "contradict an old ask, and that gets reconciled out "
                    "loud, never silently overwritten."
                ),
                parameters={"type": "object", "properties": {}},
                policy="auto_approve",
                risk_level="low",
            ),
            _decision_list,
        ),
        (
            ToolDef(
                name="feedback_note",
                description=(
                    "Record owner feedback on your behavior/output — their "
                    "words in `quote`, your diagnosis of which artifact "
                    "produced the behavior, and `changed_refs` naming what "
                    "you changed (playbook name+version, identity field, "
                    "trigger, wiki slug). Feedback with empty changed_refs "
                    "is a debt: it stays red on every heartbeat and weekly "
                    "review until feedback_act closes it."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "quote": {
                            "type": "string",
                            "description": "The feedback, in the owner's words.",
                        },
                        "diagnosis": {
                            "type": "string",
                            "description": "Which artifact produced the criticized behavior, and why.",
                        },
                        "changed_refs": {
                            "type": "string",
                            "description": "What you changed, comma-separated (e.g. 'playbook daily-report v3, identity.persona').",
                        },
                        "reconciled": {
                            "type": "string",
                            "description": "If this contradicted an earlier owner ask: how you reconciled (keep/demote/replace + where).",
                        },
                    },
                    "required": ["quote"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _feedback_note,
        ),
        (
            ToolDef(
                name="feedback_act",
                description=(
                    "Close a feedback debt: after changing the implicated "
                    "artifact, record what changed (changed_refs) on the "
                    "feedback note so it stops showing red."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "The feedback id (from feedback_list)."},
                        "changed_refs": {
                            "type": "string",
                            "description": "What changed — playbook name+version, identity field, trigger, wiki slug.",
                        },
                        "reconciled": {
                            "type": "string",
                            "description": "How a contradiction with an earlier ask was resolved, if any.",
                        },
                    },
                    "required": ["id", "changed_refs"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _feedback_act,
        ),
        (
            ToolDef(
                name="feedback_list",
                description=(
                    "Your feedback ledger with acted/red state. Check "
                    "unactioned_only=true on every heartbeat and weekly "
                    "review — anything there outranks new work."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "unactioned_only": {"type": "boolean"},
                    },
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _feedback_list,
        ),
        (
            ToolDef(
                name="design_map",
                description=(
                    "Your whole behavior surface in one call: identity + "
                    "personality values, mission, behavior-steering wiki "
                    "pages, playbooks, triggers, and open feedback debts. "
                    "Call this FIRST when the owner criticizes your "
                    "behavior/output — the artifact that produced it is on "
                    "this map."
                ),
                parameters={"type": "object", "properties": {}},
                policy="auto_approve",
                risk_level="low",
            ),
            _design_map,
        ),
    ]
    for tool_def, handler in defs:
        ctx.tool_registry.register("plugin-curiosity", tool_def, handler)
