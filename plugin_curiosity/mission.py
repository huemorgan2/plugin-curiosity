"""Mission register + tools: mission_set / mission_refine / mission_get.

Write-through: the structured row is the source of truth for rung/ceiling; the
statement is also copied into core's Identity.mission (system-prompt slot #4)
via the identity plugin's "identity" config section — no core change, no
luna.* import. Setting a mission also seeds wiki stubs (WikiProvider) and
registers the mission's recurring schedules (plugin-scheduler tools), so the
action rails exist from day one.

Naming: NOT set_mission — core's alembic 0008 seeds an approval-policy row
`set_mission -> prompt_always` (reserved self-modification name), and DB
policy rows beat ToolDef.policy, so that name would gate every mission
adoption behind an owner card on every Luna including fresh installs.
mission_* also matches the wiki_*/trigger_*/playbook_* convention.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select, update

from luna_sdk import PluginContext, ToolDef

from . import dream, research
from .models import Mission

log = logging.getLogger("plugin-curiosity")

RUNG_MIN, RUNG_MAX = 1, 4
RISK_CEILINGS = ("low", "medium", "high")

# Recurring schedules registered on mission_set. Targets are self-contained
# prompts that re-read the CURRENT mission at fire time (via mission_get), so
# refining the statement never requires re-syncing the scheduler.
# _sync_schedules updates existing triggers in place when a target or
# schedule_expr changes between plugin versions. 02:00 is the dead-hours slot:
# inside quiet hours (the dream's share_thought queues until morning) and away
# from any daytime turn load.
MISSION_SCHEDULES: list[dict[str, str]] = [
    {
        "name": "curiosity-daily-research",
        "schedule_expr": "every day at 09:00",
        "action_type": "agent_prompt",
        "target": research.DAILY_RESEARCH_TARGET,
    },
    {
        "name": "curiosity-nightly-dream",
        "schedule_expr": "every day at 02:00",
        "action_type": "agent_prompt",
        "target": dream.DREAM_TARGET,
    },
]

# Wiki stubs seeded on mission_set: a hub page (holds the statement) linking
# to starter stubs the research loop will fill.
_STUB_SLUGS = ("mission-domain", "mission-open-questions", "mission-metrics")


def _mission_dict(m: Mission) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "statement": m.statement,
        "autonomy_rung": m.autonomy_rung,
        "risk_ceiling": m.risk_ceiling,
        "active": m.active,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


class MissionStore:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    async def set(self, statement: str, rung: int = 1, risk_ceiling: str = "low") -> dict[str, Any]:
        statement = statement.strip()
        if not statement:
            raise ValueError("mission statement must be non-empty")
        if not RUNG_MIN <= rung <= RUNG_MAX:
            raise ValueError(f"autonomy_rung must be {RUNG_MIN}-{RUNG_MAX}")
        if risk_ceiling not in RISK_CEILINGS:
            raise ValueError(f"risk_ceiling must be one of {RISK_CEILINGS}")
        async with self._sf() as s:
            # single active mission: deactivate any predecessor
            await s.execute(update(Mission).where(Mission.active).values(active=False))
            m = Mission(statement=statement, autonomy_rung=rung, risk_ceiling=risk_ceiling)
            s.add(m)
            await s.commit()
            return _mission_dict(m)

    async def refine(
        self,
        statement: str | None = None,
        rung: int | None = None,
        risk_ceiling: str | None = None,
    ) -> dict[str, Any]:
        async with self._sf() as s:
            m = (
                await s.execute(select(Mission).where(Mission.active))
            ).scalar_one_or_none()
            if m is None:
                raise LookupError("no active mission — use mission_set first")
            if statement is not None:
                statement = statement.strip()
                if not statement:
                    raise ValueError("mission statement must be non-empty")
                m.statement = statement
            if rung is not None:
                if not RUNG_MIN <= rung <= RUNG_MAX:
                    raise ValueError(f"autonomy_rung must be {RUNG_MIN}-{RUNG_MAX}")
                m.autonomy_rung = rung
            if risk_ceiling is not None:
                if risk_ceiling not in RISK_CEILINGS:
                    raise ValueError(f"risk_ceiling must be one of {RISK_CEILINGS}")
                m.risk_ceiling = risk_ceiling
            await s.commit()
            return _mission_dict(m)

    async def get(self) -> dict[str, Any] | None:
        async with self._sf() as s:
            m = (
                await s.execute(select(Mission).where(Mission.active))
            ).scalar_one_or_none()
            return _mission_dict(m) if m else None


# --- cross-plugin side effects (each best-effort: a missing peer plugin ----
# --- degrades the result payload, never fails the mission write) -----------


async def _write_through_identity(ctx: PluginContext, statement: str) -> str:
    """Copy the statement into Identity.mission (system-prompt slot #4)."""
    section = ctx.config_registry.get("identity")
    if section is None:
        return "identity section unavailable — statement not in system prompt"
    result = await section.writer({"mission": statement})
    if not result.get("updated"):
        return f"identity write failed: {result.get('error', 'unknown')}"
    return "ok"


async def _seed_wiki_stubs(ctx: PluginContext, statement: str) -> str:
    """Seed the mission hub page + starter stubs. Existing pages are left
    alone (idempotent for re-set missions; hub is rewritten to the new
    statement on purpose — it IS the mission page)."""
    try:
        wiki = ctx.provider_registry.get("wiki")
    except Exception:  # noqa: BLE001
        return "wiki provider unavailable — no stubs seeded"
    links = " ".join(f"[[{s}]]" for s in _STUB_SLUGS)
    await wiki.upsert_page(
        "mission",
        "Mission",
        f"> {statement}\n\nStart here: {links}\n",
        summary=statement[:200],
        note="mission_set",
    )
    seeded = ["mission"]
    for slug in _STUB_SLUGS:
        if await wiki.get_page(slug) is None:
            await wiki.upsert_page(
                slug,
                slug.replace("-", " ").title(),
                f"*Stub — to be researched for the mission: {statement}*\n",
                summary="stub",
                note="mission_set stub",
            )
            seeded.append(slug)
    return f"seeded {seeded}"


async def _retry_tool(handler, /, **kwargs) -> dict[str, Any]:
    """Scheduler tool handlers return {"error": str(exc)} on transport failure
    (empty string for bare timeouts). Under turn load the 10s scheduler-client
    timeout trips transiently, so retry with backoff before giving up."""
    result: dict[str, Any] = {}
    for attempt in range(3):
        if attempt:
            await asyncio.sleep(3 * attempt)
        result = await handler(**kwargs)
        if "error" not in result:
            return result
    return result


def _spec_drift(current: dict[str, Any], spec: dict[str, str]) -> dict[str, str]:
    """Fields of a live trigger that drifted from its MISSION_SCHEDULES spec
    (trigger_update kwargs). expr_raw stores the phrase as submitted, so a
    plain string compare detects a changed schedule."""
    drift: dict[str, str] = {}
    if current.get("target") != spec["target"]:
        drift["target"] = spec["target"]
    if current.get("expr_raw") != spec["schedule_expr"]:
        drift["schedule_expr"] = spec["schedule_expr"]
    return drift


async def _sync_schedules(ctx: PluginContext) -> str:
    """Ensure the mission's recurring triggers exist AND carry the current
    target prompts + schedules. Missing triggers are created; an existing
    trigger that drifted from MISSION_SCHEDULES (e.g. a placeholder target or
    an old fire time from a previous plugin version) is updated in place via
    trigger_update — identity and fire history survive. Calls
    plugin-scheduler's tool handlers directly — all involved tools are
    auto_approve."""
    try:
        lister = ctx.tool_registry.get("trigger_list").handler
        creator = ctx.tool_registry.get("trigger_create").handler
    except KeyError:
        return "plugin-scheduler not installed — no schedules registered"
    try:
        updater = ctx.tool_registry.get("trigger_update").handler
    except KeyError:
        updater = None  # older plugin-scheduler: create-only sync
    listed = await _retry_tool(lister)
    if "error" in listed:
        return f"scheduler unreachable: {listed['error']}"
    existing = {t.get("name"): t for t in listed.get("triggers", [])}
    created, updated = [], []
    for spec in MISSION_SCHEDULES:
        current = existing.get(spec["name"])
        if current is None:
            result = await _retry_tool(creator, **spec)
            if "error" in result:
                return f"trigger_create({spec['name']}) failed: {result['error']}"
            created.append(spec["name"])
            continue
        drift = _spec_drift(current, spec) if updater is not None else {}
        if drift:
            result = await _retry_tool(updater, id=current["id"], **drift)
            if "error" in result:
                return f"trigger_update({spec['name']}) failed: {result['error']}"
            updated.append(spec["name"])
    if not created and not updated:
        return "already registered"
    return f"created {created}, updated {updated}"


def register_tools(ctx: PluginContext, store: MissionStore) -> None:
    async def _set(statement: str, rung: int = 1, risk_ceiling: str = "low") -> dict[str, Any]:
        try:
            mission = await store.set(statement, rung=rung, risk_ceiling=risk_ceiling)
        except ValueError as e:
            return {"error": str(e)}
        return {
            "mission": mission,
            "identity_sync": await _write_through_identity(ctx, mission["statement"]),
            "wiki_stubs": await _seed_wiki_stubs(ctx, mission["statement"]),
            "schedules": await _sync_schedules(ctx),
            # fire-and-forget: the kickoff moment posts right after this turn
            "kickoff": research.spawn_kickoff(ctx, mission["statement"]),
        }

    async def _refine(
        statement: str | None = None,
        rung: int | None = None,
        risk_ceiling: str | None = None,
    ) -> dict[str, Any]:
        try:
            mission = await store.refine(statement=statement, rung=rung, risk_ceiling=risk_ceiling)
        except (ValueError, LookupError) as e:
            return {"error": str(e)}
        out: dict[str, Any] = {"mission": mission}
        if statement is not None:
            out["identity_sync"] = await _write_through_identity(ctx, mission["statement"])
        out["schedules"] = await _sync_schedules(ctx)
        return out

    async def _get() -> dict[str, Any]:
        mission = await store.get()
        if mission is None:
            return {"mission": None, "note": "no active mission — ask the owner for one"}
        return {"mission": mission}

    defs: list[tuple[ToolDef, Any]] = [
        (
            ToolDef(
                name="mission_set",
                description=(
                    "Adopt a new mission (replaces any active one). Writes the "
                    "mission into your identity (system prompt), seeds starter "
                    "wiki pages, registers your recurring research/dream "
                    "schedules, and starts the kickoff research pass (a Mission "
                    "Kickoff moment follows in this conversation). autonomy_rung "
                    "1-4: how proactively you may act (4 = execute-with-approval; "
                    "unattended execution is a later owner decision, not a rung)."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "statement": {"type": "string", "description": "The mission, one clear sentence or short paragraph."},
                        "rung": {"type": "integer", "minimum": 1, "maximum": 4, "default": 1},
                        "risk_ceiling": {"type": "string", "enum": list(RISK_CEILINGS), "default": "low"},
                    },
                    "required": ["statement"],
                },
                policy="auto_approve",
                risk_level="low",
                timeout_seconds=120,
            ),
            _set,
        ),
        (
            ToolDef(
                name="mission_refine",
                description=(
                    "Refine the active mission: reword the statement and/or adjust "
                    "autonomy_rung (1-4) / risk_ceiling. Keeps identity and "
                    "schedules in sync. Use mission_set for a genuinely new mission."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "statement": {"type": "string"},
                        "rung": {"type": "integer", "minimum": 1, "maximum": 4},
                        "risk_ceiling": {"type": "string", "enum": list(RISK_CEILINGS)},
                    },
                },
                policy="auto_approve",
                risk_level="low",
                timeout_seconds=120,
            ),
            _refine,
        ),
        (
            ToolDef(
                name="mission_get",
                description="Your active mission with autonomy rung and risk ceiling.",
                parameters={"type": "object", "properties": {}},
                policy="auto_approve",
                risk_level="low",
            ),
            _get,
        ),
    ]
    for tool_def, handler in defs:
        ctx.tool_registry.register("plugin-curiosity", tool_def, handler)


def prompt_fragment(mission: dict[str, Any] | None) -> str:
    """The curiosity capability note. With a mission: own it + the rails.
    Without: know how to get one."""
    rails = (
        "Action rails: schedule recurring work with the trigger_* tools (the "
        "clock is external and always-on). When you notice a repeatable action, "
        "author a playbook in conversation (playbook_propose / playbook_edit — "
        "chat-only tools) and run or schedule it by name; side-effecting steps "
        "go through their normal approval gates, so propose confidently. When "
        "you learn something the owner would genuinely want to know, share it "
        "with share_thought (cite a [[wiki-page]] or source; it enforces the "
        "noise budget — one routine reflection a day, quiet hours queue)."
    )
    if mission is None:
        # Mission-first onboarding (phase 6): the vision's inversion — mission →
        # curiosity → shared understanding → trust → setup. This fragment sits
        # after the onboarding addendum in the system prompt and deliberately
        # reorders its checklist.
        return (
            "Curiosity: you have no active mission yet — getting one is your top "
            "priority. In your FIRST exchange with the owner (even during "
            "first-run setup, before name or emoji), ask what mission they want "
            "you to own: one focused question, in your own voice. The moment "
            "they state a mission (or you agree on one together), call "
            "mission_set IN THAT SAME TURN, before asking anything else — never "
            "defer it behind name, emoji, or other setup questions; adopting it "
            "seeds your wiki, starts your recurring research/dream schedules, "
            "and kicks off a same-day quick win, and every exchange it waits is "
            "a quick win delayed. If first-run setup is in progress, the "
            "adopted mission doubles as your identity: also save it with "
            "update_self(field='mission', ...) right away, then continue the "
            "rest of setup. " + rails
        )
    return (
        f"Curiosity: your mission — {mission['statement']} (autonomy rung "
        f"{mission['autonomy_rung']}/4, risk ceiling {mission['risk_ceiling']}). "
        "You own this mission. Teach yourself the domain: keep the wiki current "
        "(wiki_* tools), note open questions, and share grounded insights when "
        "they matter. Use mission_refine as your understanding sharpens. " + rails
    )
