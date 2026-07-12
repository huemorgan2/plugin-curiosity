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
import inspect
import logging
from typing import Any

from sqlalchemy import select, update

from luna_sdk import PluginContext, ToolDef

from . import dream, prompts, research, review, telemetry, wikibind
from .models import Mission
from .scopes import STAGE_LABELS

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
    # "purpose" is the owner-facing provenance label (scheduler 0.3.0); it is
    # stripped from the payload when the installed plugin-scheduler predates
    # the parameter.
    {
        "name": "curiosity-daily-research",
        "schedule_expr": "every day at 09:00",
        "action_type": "agent_prompt",
        "target": research.DAILY_RESEARCH_TARGET,
        "purpose": "daily learning pass on the mission",
    },
    {
        "name": "curiosity-nightly-dream",
        "schedule_expr": "every day at 02:00",
        "action_type": "agent_prompt",
        "target": dream.DREAM_TARGET,
        "purpose": "nightly consolidation of the day's learning",
    },
    # 8.2: the weekly scoreboard turn — goals scored, setup audited, one ask.
    # Monday 09:30 keeps it clear of the 09:00 daily research fire.
    {
        "name": "curiosity-weekly-review",
        "schedule_expr": "every monday at 09:30",
        "action_type": "agent_prompt",
        "target": review.WEEKLY_REVIEW_TARGET,
        "purpose": "weekly scoreboard for the owner",
    },
]

# Wiki stubs seeded on mission_set: a hub page (holds the statement) linking
# to starter stubs the research loop will fill.
_STUB_SLUGS = (
    "mission-domain",
    "mission-open-questions",
    # phase 10: the agent's own job description — how it will accomplish the
    # mission, what the owner sees after onboarding and in 30 days, working
    # assumptions. Drafted v1 in kickoff S0, living document thereafter
    # (rewritten on role pivots; role_version stamps the revision).
    "job-description",
    # 9.001B: the success definition — job expectations, what makes the agent
    # successful in the owner's eyes. Drafted in the kickoff's S0, ratified
    # with the charter (S3), scored against in the weekly review. Replaces
    # the pre-9.001 "mission-metrics" stub, which no surface ever filled.
    "success-criteria",
    # 8.2: the goal ledger's owner-readable mirror (goals.py rebuilds it on
    # every goal_set/goal_update; the stub just makes the link resolvable
    # from day one)
    "mission-goals",
    # 9A: the role charter — scopes, stage marker, Plan-changes log
    # (scopes.py rebuilds it on every scope/stage/phase mutation)
    "role-charter",
    # 9B: open loops + the value receipts log (loops.py rebuilds both on
    # every loop/value mutation)
    "open-loops",
    "value-log",
)


# 9.001B: the success-criteria page — what success looks like, in a place the
# kickoff fills, the owner ratifies, and the weekly review scores against.
SUCCESS_SLUG = "success-criteria"
_LEGACY_METRICS_SLUG = "mission-metrics"

_SUCCESS_STUB_BODY = (
    "*What success looks like for the mission: {statement}*\n\n"
    "*Job expectations and what will make the owner call this successful — "
    "drafted by the agent in kickoff S0, sharpened with the owner, RATIFIED "
    "together with [[role-charter]] (that ratification is stage S3). Goals "
    "must trace to a criterion on this page.*\n"
)


async def ensure_success_criteria_page(ctx: PluginContext, store: MissionStore) -> str:
    """Upgrade path (on-load, 9.001B): a pre-9.001 mission has the orphaned
    [[mission-metrics]] stub and no [[success-criteria]]. Seed the new page
    once — carrying over any real content the old page accumulated — so the
    success definition has a home without waiting for a new mission_set.
    The old page is left in place (history stays readable)."""
    m = await store.get()
    if m is None:
        return "no mission"
    try:
        wiki = ctx.provider_registry.get("wiki")
    except Exception:  # noqa: BLE001
        return "wiki provider unavailable"
    wk = await wikibind.wiki_kwargs(ctx, store._sf)  # noqa: SLF001
    try:
        if await wiki.get_page(SUCCESS_SLUG, **wk) is not None:
            return "already present"
        legacy = await wiki.get_page(_LEGACY_METRICS_SLUG, **wk)
        body = _SUCCESS_STUB_BODY.format(statement=m["statement"])
        if legacy and legacy.get("body") and "*Stub — " not in legacy["body"]:
            body = legacy["body"].rstrip() + "\n\n" + body
        await wiki.upsert_page(
            SUCCESS_SLUG,
            "Success Criteria",
            body,
            summary="what success looks like — to be ratified with the charter",
            note="9.001B upgrade seed",
            **wk,
        )
    except Exception as e:  # noqa: BLE001
        # a downgraded wiki plugin on a multi-wiki DB can raise on duplicated
        # slugs (slug-only get_page sees both namespaces) — scaffolding is
        # best-effort, never a load failure
        log.warning("success-criteria seed skipped: %s", e)
        return f"skipped: {e}"
    return "seeded"


def _mission_dict(m: Mission) -> dict[str, Any]:
    # setup_stage_owner_words: role-resilience dojo caught agents quoting the
    # bare code to owners ("still at S0") — a prompt rule alone didn't stop it,
    # so the dict itself carries the words to say.
    words = STAGE_LABELS.get(m.setup_stage)
    return {
        "id": str(m.id),
        "statement": m.statement,
        "autonomy_rung": m.autonomy_rung,
        "risk_ceiling": m.risk_ceiling,
        "active": m.active,
        "agent_phase": m.agent_phase,
        "setup_stage": m.setup_stage,
        "setup_stage_owner_words": f"{words[0]} — {words[1]}" if words else m.setup_stage,
        "role_version": getattr(m, "role_version", 1) or 1,
        "wiki_id": getattr(m, "wiki_id", None),
        "phase_entered_at": m.phase_entered_at.isoformat() if m.phase_entered_at else None,
        "stage_entered_at": m.stage_entered_at.isoformat() if m.stage_entered_at else None,
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

    async def list_all(self) -> list[dict[str, Any]]:
        """Every mission ever set, active first then newest first — the
        Missions pane's history shelf (9.002)."""
        async with self._sf() as s:
            rows = (
                (
                    await s.execute(
                        select(Mission).order_by(
                            Mission.active.desc(), Mission.created_at.desc()
                        )
                    )
                )
                .scalars()
                .all()
            )
            return [_mission_dict(m) for m in rows]


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


async def _seed_wiki_stubs(
    ctx: PluginContext, statement: str, wk: dict[str, Any] | None = None
) -> str:
    """Seed the mission hub page + starter stubs — into the mission's own
    wiki when one was bound (wk={"wiki": slug}), the global namespace
    otherwise. Existing pages are left alone (idempotent for re-set missions;
    hub is rewritten to the new statement on purpose — it IS the mission
    page)."""
    wk = wk or {}
    try:
        wiki = ctx.provider_registry.get("wiki")
    except Exception:  # noqa: BLE001
        return "wiki provider unavailable — no stubs seeded"
    links = " ".join(f"[[{s}]]" for s in _STUB_SLUGS)
    seeded: list[str] = []
    skipped: list[str] = []
    # per-slug guard: a downgraded wiki plugin on a multi-wiki DB raises on
    # duplicated slugs (slug-only lookups see both namespaces) — stubs are
    # best-effort scaffolding and must never abort mission adoption
    try:
        await wiki.upsert_page(
            "mission",
            "Mission",
            f"> {statement}\n\nStart here: {links}\n",
            summary=statement[:200],
            note="mission_set",
            **wk,
        )
        seeded.append("mission")
    except Exception as e:  # noqa: BLE001
        log.warning("mission hub seed skipped: %s", e)
        skipped.append("mission")
    for slug in _STUB_SLUGS:
        try:
            if await wiki.get_page(slug, **wk) is None:
                body = (
                    _SUCCESS_STUB_BODY.format(statement=statement)
                    if slug == SUCCESS_SLUG
                    else f"*Stub — to be researched for the mission: {statement}*\n"
                )
                await wiki.upsert_page(
                    slug,
                    slug.replace("-", " ").title(),
                    body,
                    summary="stub",
                    note="mission_set stub",
                    **wk,
                )
                seeded.append(slug)
        except Exception as e:  # noqa: BLE001
            log.warning("stub seed skipped for %s: %s", slug, e)
            skipped.append(slug)
    if skipped:
        return f"seeded {seeded}, skipped {skipped} (wiki degraded)"
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
    # 0.9.2: provenance + race-safety, feature-detected off the installed
    # plugin-scheduler's handler signatures. list-before-create stays even
    # with unique_name available — a 0.3.0 plugin talking to an OLD service
    # would otherwise create a duplicate on every on-load sync.
    def _params(handler) -> set[str]:
        try:
            return set(inspect.signature(handler).parameters)
        except (TypeError, ValueError):
            return set()

    creator_params = _params(creator)
    updater_params = _params(updater) if updater is not None else set()
    listed = await _retry_tool(lister)
    if "error" in listed:
        return f"scheduler unreachable: {listed['error']}"
    existing = {t.get("name"): t for t in listed.get("triggers", [])}
    created, updated = [], []
    for spec in MISSION_SCHEDULES:
        payload = {k: v for k, v in spec.items() if k != "purpose"}
        if "unique_name" in creator_params:
            payload["unique_name"] = True
        if "purpose" in creator_params and spec.get("purpose"):
            payload["purpose"] = spec["purpose"]
        if "created_by" in creator_params:
            payload["created_by"] = "plugin-curiosity"
        current = existing.get(spec["name"])
        if current is None:
            result = await _retry_tool(creator, **payload)
            if "error" in result:
                return f"trigger_create({spec['name']}) failed: {result['error']}"
            created.append(spec["name"])
            continue
        drift = _spec_drift(current, spec) if updater is not None else {}
        if (
            "purpose" in updater_params
            and spec.get("purpose")
            and current.get("purpose") != spec["purpose"]
        ):
            drift["purpose"] = spec["purpose"]
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
        # 0.9.2: bind the mission's own wiki BEFORE seeding, so the stubs land
        # in it. None (old wiki plugin / bind failure) = global namespace,
        # exactly the pre-0.9.2 behavior. A replaced mission's wiki is left
        # untouched — its knowledge stays browsable from the history shelf.
        slug = await wikibind.bind_wiki(ctx, mission["statement"], mission["id"])
        if slug:
            await wikibind.persist_wiki_id(store._sf, mission["id"], slug)  # noqa: SLF001
            mission["wiki_id"] = slug
        wk = {"wiki": slug} if slug else {}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "mission"})
        return {
            "mission": mission,
            "identity_sync": await _write_through_identity(ctx, mission["statement"]),
            "wiki_stubs": await _seed_wiki_stubs(ctx, mission["statement"], wk),
            "schedules": await _sync_schedules(ctx),
            # fire-and-forget: the kickoff moment posts right after this turn
            "kickoff": research.spawn_kickoff(ctx, mission["statement"], wiki_slug=slug),
            "reminder": (
                "set your one-line status now with current_state_set — the "
                "owner's pane shows it under the mission statement"
            ),
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
        await telemetry.emit_ui_event(ctx, "changed", {"what": "mission"})
        out: dict[str, Any] = {"mission": mission}
        if statement is not None:
            out["identity_sync"] = await _write_through_identity(ctx, mission["statement"])
            # keep the bound wiki's shelf label honest on a reworded mission
            if mission.get("wiki_id"):
                try:
                    wiki = ctx.provider_registry.get("wiki")
                    if callable(getattr(wiki, "update_wiki", None)):
                        await wiki.update_wiki(
                            mission["wiki_id"],
                            description=mission["statement"][:200],
                        )
                except Exception:  # noqa: BLE001
                    log.debug("wiki description refresh failed", exc_info=True)
        out["schedules"] = await _sync_schedules(ctx)
        return out

    async def _get() -> dict[str, Any]:
        mission = await store.get()
        if mission is None:
            return {"mission": None, "note": "no active mission — ask the owner for one"}
        return {"mission": mission}

    # 0.9.3: self-heal for wiped/broken schedules. Before this, sync only ran
    # inside mission_set/mission_refine — an agent that found its triggers gone
    # (server reset, account migration) had to hand-craft trigger_create calls
    # and usually restored just the heartbeat. One idempotent tool restores the
    # whole spec: missing triggers are created, drifted ones repaired.
    async def _schedules_sync() -> dict[str, Any]:
        mission = await store.get()
        if mission is None:
            return {"error": "no active mission — no schedules to sync"}
        return {"schedules": await _sync_schedules(ctx)}

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
        (
            ToolDef(
                name="mission_schedules_sync",
                description=(
                    "Verify and restore your recurring mission schedules "
                    "(research, dream, review, setup heartbeat). Idempotent: "
                    "missing triggers are recreated, drifted ones repaired, "
                    "healthy ones left alone. Use this whenever an audit shows "
                    "triggers missing or wrong — do not hand-craft "
                    "trigger_create calls for your own mission schedules."
                ),
                parameters={"type": "object", "properties": {}},
                policy="auto_approve",
                risk_level="low",
                timeout_seconds=120,
            ),
            _schedules_sync,
        ),
    ]
    for tool_def, handler in defs:
        ctx.tool_registry.register("plugin-curiosity", tool_def, handler)


# 0.9.7 (core 034/phase03): on claim cores the mission-first ordering is not
# persuasion prose inside the fragment — it is written INTO the onboarding
# addendum itself, via the plugin's core.onboarding claim. This is the text
# the _occupy_prompt handler prepends to that section while missionless.
MISSION_FIRST_NOTE = (
    "MISSION FIRST (curiosity): before anything on this checklist, your very "
    "FIRST question to the owner is what mission they want you to own — "
    "before name, emoji, or any other setup question. The rest of the "
    "checklist resumes once the mission ask is on the table; the moment a "
    "mission lands, call mission_set in that same turn."
)


def prompt_fragment(
    mission: dict[str, Any] | None,
    phase: str | None = None,
    slot_mode: bool = False,
) -> str:
    """The curiosity capability note. With a mission: own it + the rails,
    plus the phase posture (9C — setup: the talented hire earning autonomy;
    work: mastery and toolkit improvement). Without: know how to get one.

    slot_mode (0.9.7): True on cores that grant prompt-slot claims — the
    fragment then OCCUPIES the core.drive slot and the checklist ordering is
    handled by MISSION_FIRST_NOTE inside the addendum, so the missionless
    text drops its 'this note OVERRIDES its ordering' prose."""
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
        # reorders its checklist. Post-launch sharpening: the ask renews on
        # EVERY reply until a mission lands — an installed-but-missionless
        # curiosity loop is completely dark (no wiki, no research, no dreams),
        # and an owner who skipped the first ask never heard about it again.
        ordering = (
            "If a first-run setup flow is "
            "active (a SETUP STATE block appears in these instructions), this "
            "note OVERRIDES its ordering: do NOT open with the next missing "
            "checklist item — your very FIRST question to the owner is what "
            "mission they want you to own, before name, emoji, or any other "
            "setup question; the rest of the checklist resumes after the "
            "mission ask is on the table. "
        )
        if slot_mode:
            ordering = ""  # MISSION_FIRST_NOTE rides in the addendum instead
        return (
            "Curiosity: you have no active mission yet — getting one is your top "
            "priority, and it is critical: without a mission your whole "
            "curiosity loop stays dark (no wiki, no daily research, no nightly "
            "dreams, no proactive insights). " + ordering + "Until a mission is adopted, "
            "renew the ask in EVERY reply: help with whatever the owner asked "
            "first, then urge them to give you a mission — in your own voice "
            "and personality, with fresh framing each time (a mission in life; "
            "the work they want you to own; the problem they most want off "
            "their plate; what they'd hand a sharp new hire), never repeating "
            "an earlier phrasing verbatim. Make the stakes felt, and tell "
            "them plainly how it works: once they give you a mission you "
            "first make yourself QUALIFIED for it — a setup phase where they "
            "see exactly what you are missing and how close you are — then "
            "you run it as your job. You set yourself up to best serve it — "
            "research it, build a knowledge wiki, watch over it while they "
            "sleep. The "
            "moment they state a mission (or you agree on one together), call "
            "mission_set IN THAT SAME TURN, before asking anything else — never "
            "defer it behind name, emoji, or other setup questions; adopting it "
            "seeds your wiki, starts your recurring research/dream schedules, "
            "and kicks off a same-day quick win, and every exchange it waits is "
            "a quick win delayed. If first-run setup is in progress, the "
            "adopted mission doubles as your identity: also save it with "
            "update_self(field='mission', ...) right away, then continue the "
            "rest of setup. " + rails
        )
    # 0.9.2: a bound mission wiki is stated concretely — the generic rule
    # (prompts.WIKI_BINDING) rides in surfaces that can't know the slug.
    wiki_line = ""
    if mission.get("wiki_id"):
        wiki_line = (
            f"Your mission wiki is '{mission['wiki_id']}' — pass "
            f"wiki='{mission['wiki_id']}' to EVERY wiki_* call (read, write, "
            "patch, ask, toc, search); pages written elsewhere are invisible "
            "to your mission surfaces. "
        )
    base = (
        f"Curiosity: your mission — {mission['statement']} (autonomy rung "
        f"{mission['autonomy_rung']}/4, risk ceiling {mission['risk_ceiling']}). "
        + wiki_line
        + prompts.OWNER_WORDS + " "
        "You OWN this mission and you are relentless about it: you keep a goal "
        "ledger ([[mission-goals]] — goal_set / goal_update / goal_list), you "
        "advance a goal every day, and you drive toward CHANGE, not just "
        "understanding. Teach yourself the domain (wiki_* tools, open "
        "questions), but never stop at suggestions — when you see a way to "
        "make a real difference, propose the action YOU will take and ask for "
        "the go-ahead (or take it, within your autonomy rung). When a "
        "capability would let you do more — a plugin from the marketplace, a "
        "connected channel (WhatsApp, email) to reach the owner off-platform — "
        "say so plainly: 'install X / connect me and I can do Y'. Use "
        "mission_refine as your understanding sharpens. "
        "STATUS LINE: the owner's pane shows one line from you, verbatim — "
        "keep it true with current_state_set (what you're doing right now, "
        "plain first-person words); refresh it whenever your focus, stage, "
        "or phase changes. "
    )
    if phase == "work":
        posture = (
            prompts.PHASE_TWO_LINE + " The routine is yours — run it with "
            "mastery, keep 2-3 goals rolling, and every week leave the "
            "toolkit better than you found it (a playbook diff, a cadence "
            "change, a plugin worth adding). Charter upkeep continues: record "
            "answers as scope evidence and keep [[role-charter]] honest. "
        )
    else:
        # 9.001A: the doctrine opens the posture — the frame first, then the
        # HOW (talented-hire law + phase-10 FDE stance), then the mechanics
        # (ladder, loop discipline, heartbeat, next-touch, ratification
        # forcing) and the phase-10 discovery discipline (question cadence,
        # materiality, no-blame).
        posture = (
            prompts.PHASE_ONE_DOCTRINE + " "
            + prompts.FDE_DOCTRINE + " "
            + prompts.TALENTED_HIRE_LAW + " "
            "Corollary: work in small, redirectable increments — stub/summary "
            "depth until the owner ratifies your charter, so a pivot never "
            "wastes a week. "
            + prompts.SETUP_STAGE_DEFS + " "
            + prompts.ABILITY_CONTRACT + " "
            + prompts.LOOP_DISCIPLINE + " "
            + prompts.HEARTBEAT_CONTRACT + " "
            + prompts.NEXT_TOUCH_RULE + " "
            + prompts.RATIFICATION_FORCING + " "
            + prompts.VALUE_QUESTION_CADENCE + " "
            + prompts.MATERIALITY_RULE + " "
            + prompts.NO_BLAME + " "
        )
    return base + posture + rails
