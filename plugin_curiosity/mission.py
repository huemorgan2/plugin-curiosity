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
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update

from luna_sdk import PluginContext, ToolDef

from . import dream, gating, prompts, research, review, telemetry, wikibind
from .models import Mission, MissionDraft
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
    # 10.006: the reasons ledger — every owner instruction with its why and
    # where it lives (feedback.py rebuilds it on every decision/feedback
    # mutation); the audit trail feedback gets reconciled against.
    "owner-decisions",
)


# 9.001B: the success-criteria page — what success looks like, in a place the
# kickoff fills, the owner ratifies, and the weekly review scores against.
SUCCESS_SLUG = "success-criteria"
_LEGACY_METRICS_SLUG = "mission-metrics"

_SUCCESS_STUB_BODY = (
    "*What success looks like for the mission: {statement}*\n\n"
    "*Job expectations and what will make the owner call this successful — "
    "drafted by the agent, sharpened with the owner, and approved by the "
    "owner together with the job description. Goals must trace to a "
    "criterion on this page; what the job needs lives at [[role-charter]].*\n"
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
            "What success looks like",
            body,
            summary="what success looks like — for the owner to read and approve",
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
    confirmed = getattr(m, "confirmed_at", None)
    if confirmed is not None and confirmed.tzinfo is None:  # SQLite loses tzinfo
        confirmed = confirmed.replace(tzinfo=UTC)
    return {
        "id": str(m.id),
        "statement": m.statement,
        "origin_statement": getattr(m, "origin_statement", "") or "",
        "confirmed_at": confirmed.isoformat() if confirmed else None,
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

    async def set(
        self,
        statement: str,
        rung: int = 1,
        risk_ceiling: str = "low",
        origin_statement: str = "",
    ) -> dict[str, Any]:
        statement = statement.strip()
        if not statement:
            raise ValueError("mission statement must be non-empty")
        if not RUNG_MIN <= rung <= RUNG_MAX:
            raise ValueError(f"autonomy_rung must be {RUNG_MIN}-{RUNG_MAX}")
        if risk_ceiling not in RISK_CEILINGS:
            raise ValueError(f"risk_ceiling must be one of {RISK_CEILINGS}")
        async with self._sf() as s:
            # 11.001: an unconsumed intake draft supplies the origin when the
            # caller didn't — the owner's verbatim words are never lost; every
            # draft is consumed by the set either way.
            if not origin_statement:
                d = (
                    await s.execute(
                        select(MissionDraft).order_by(MissionDraft.created_at).limit(1)
                    )
                ).scalar_one_or_none()
                if d is not None:
                    origin_statement = d.verbatim
            await s.execute(delete(MissionDraft))
            # single active mission: deactivate any predecessor
            await s.execute(update(Mission).where(Mission.active).values(active=False))
            m = Mission(
                statement=statement,
                origin_statement=origin_statement.strip(),
                autonomy_rung=rung,
                risk_ceiling=risk_ceiling,
            )
            s.add(m)
            await s.commit()
            return _mission_dict(m)

    async def draft(self, verbatim: str) -> dict[str, Any]:
        """Store the owner's mission words the instant they land. Convergent:
        if a draft already exists the OLDEST wins — the second call returns it
        instead of adding a rival (concurrent turns race any list-before-
        create; oldest-wins converges)."""
        verbatim = verbatim.strip()
        if not verbatim:
            raise ValueError("draft must be non-empty — the owner's words as stated")
        async with self._sf() as s:
            existing = (
                await s.execute(
                    select(MissionDraft).order_by(MissionDraft.created_at).limit(1)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return self._draft_dict(existing)
            d = MissionDraft(verbatim=verbatim)
            s.add(d)
            await s.commit()
            return self._draft_dict(d)

    async def draft_get(self) -> dict[str, Any] | None:
        """The oldest (winning) draft, or None."""
        async with self._sf() as s:
            d = (
                await s.execute(
                    select(MissionDraft).order_by(MissionDraft.created_at).limit(1)
                )
            ).scalar_one_or_none()
            return self._draft_dict(d) if d else None

    async def clear_drafts(self) -> int:
        async with self._sf() as s:
            result = await s.execute(delete(MissionDraft))
            await s.commit()
            return result.rowcount or 0

    async def confirm(self) -> dict[str, Any]:
        """Stamp confirmed_at on the active mission (idempotent — an already
        confirmed mission keeps its original stamp)."""
        async with self._sf() as s:
            m = (
                await s.execute(select(Mission).where(Mission.active))
            ).scalar_one_or_none()
            if m is None:
                raise LookupError("no active mission — nothing to confirm")
            if m.confirmed_at is None:
                m.confirmed_at = datetime.now(UTC)
                await s.commit()
            return _mission_dict(m)

    @staticmethod
    def _draft_dict(d: MissionDraft) -> dict[str, Any]:
        created = d.created_at
        age_hours: float | None = None
        if created is not None:
            if created.tzinfo is None:  # SQLite loses tzinfo
                created = created.replace(tzinfo=UTC)
            age_hours = (datetime.now(UTC) - created).total_seconds() / 3600.0
        return {
            "id": str(d.id),
            "verbatim": d.verbatim,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            # server-computed: agents have no clock
            "age_hours": round(age_hours, 2) if age_hours is not None else None,
        }

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


# 11.001/M1: how long an unconsumed intake draft may sit before the reaper
# promotes it to the mission AS STATED. The owner said the words; a dead
# conversation must not orphan them.
DRAFT_REAP_AGE_H = 24.0


async def reap_stale_draft(ctx: PluginContext, store: MissionStore) -> str:
    """Promote a >24 h-old intake draft to the mission, verbatim, through the
    full mission_set tool path (identity, wiki, schedules, kickoff). Runs from
    on-load work and per-turn fire-and-forget — concurrent calls converge:
    store.set keeps a single active mission and consumes every draft, and the
    oldest draft is the only one either call promotes."""
    if await store.get() is not None:
        n = await store.clear_drafts()
        return f"cleared {n} draft(s): mission active" if n else "no draft"
    d = await store.draft_get()
    if d is None:
        return "no draft"
    if (d["age_hours"] or 0) < DRAFT_REAP_AGE_H:
        return "draft fresh"
    try:
        setter = ctx.tool_registry.get("mission_set").handler
    except Exception:  # noqa: BLE001 - registry not ready; retry next pass
        return "mission_set unavailable"
    result = await setter(statement=d["verbatim"], origin_statement=d["verbatim"])
    if isinstance(result, dict) and result.get("error"):
        return f"promotion failed: {result['error']}"
    log.info("stale mission draft promoted verbatim after %sh", DRAFT_REAP_AGE_H)
    return "promoted"


def register_tools(ctx: PluginContext, store: MissionStore) -> None:
    async def _set(
        statement: str,
        rung: int = 1,
        risk_ceiling: str = "low",
        origin_statement: str = "",
    ) -> dict[str, Any]:
        try:
            mission = await store.set(
                statement, rung=rung, risk_ceiling=risk_ceiling,
                origin_statement=origin_statement,
            )
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
            # fire-and-forget: the instant-brief moment posts right after this
            # turn (11.001: the deep pass waits for mission_confirm / 12 h).
            # Read the succinct-persona signal HERE (turn session is live) so
            # the background task carries a flag, not a second DB read.
            "kickoff": research.spawn_kickoff(
                ctx, mission["statement"], wiki_slug=slug,
                compact=await research._prefers_compact(ctx),
            ),
            "reminder": (
                "set your one-line status now with current_state_set — the "
                "owner's pane shows it under the mission statement. A quick "
                "first-look brief posts in a moment; the deep setup pass "
                "waits for the owner's yes — when they confirm (any 'go'/"
                "'yes'/'sounds right'), call mission_confirm."
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
            draft = await store.draft_get()
            if draft is not None:
                return {
                    "mission": None,
                    "draft": draft,
                    "note": (
                        "no active mission, but an intake draft holds the "
                        "owner's words — save it with mission_set (sharpened "
                        "statement, origin_statement=the draft verbatim) on "
                        "their next reply, or immediately if they seem done "
                        "answering"
                    ),
                }
            return {"mission": None, "note": "no active mission — ask the owner for one"}
        return {"mission": mission}

    async def _draft(verbatim: str) -> dict[str, Any]:
        try:
            draft = await store.draft(verbatim)
        except ValueError as e:
            return {"error": str(e)}
        return {
            "draft": draft,
            "next": (
                "their words are safe — now, if mission_set is not among your "
                "tools yet, call load_tools(group='curiosity') in this SAME "
                "reply (its tools go live next turn, never this one), then "
                "ask your ONE round of discovery questions (max 2-3, only "
                "ones whose answers change your plan) in this same reply. On "
                "the owner's NEXT message you MUST call mission_set "
                "(sharpened statement, origin_statement=this verbatim) no "
                "matter how much they answered — never a second question "
                "round. If they show ANY impatience, skip the questions and "
                "save with mission_set at the first turn it is available."
            ),
        }

    async def _confirm() -> dict[str, Any]:
        try:
            mission = await store.confirm()
        except LookupError as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "mission"})
        out: dict[str, Any] = {"mission": mission}
        # routed through the janitor: it holds the once-per-mission claim AND
        # the grandfather guard (a pre-split mission past S0 never re-fires)
        out["deep_kickoff"] = await research.maybe_start_deep_kickoff(ctx, store)
        return out

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
                name="mission_draft",
                description=(
                    "Capture the owner's mission words VERBATIM the instant "
                    "they first state work they want you to own — before any "
                    "reply text, before any question. This protects their "
                    "words while you ask your single round of discovery "
                    "questions (max 2-3, same reply, only questions whose "
                    "answers would change your plan). On the owner's NEXT "
                    "message you save with mission_set — never a second "
                    "question round; if the owner seems impatient, skip the "
                    "questions and call mission_set immediately."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "verbatim": {
                            "type": "string",
                            "description": "The owner's mission words exactly as they wrote them.",
                        },
                    },
                    "required": ["verbatim"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _draft,
        ),
        (
            ToolDef(
                name="mission_set",
                description=(
                    "Adopt a new mission (replaces any active one). Call it "
                    "when the intake round is done — the owner's next message "
                    "after your questions, or immediately on any sign of "
                    "impatience — with the sharpened statement and their "
                    "verbatim words as origin_statement (auto-filled from "
                    "your mission_draft if omitted). Writes the "
                    "mission into your identity (system prompt), seeds starter "
                    "wiki pages, registers your recurring research/dream "
                    "schedules, and posts a quick first-look brief (the deep "
                    "setup pass waits for mission_confirm). autonomy_rung "
                    "1-4: how proactively you may act (4 = execute-with-approval; "
                    "unattended execution is a later owner decision, not a rung)."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "statement": {"type": "string", "description": "The mission, one clear sentence or short paragraph."},
                        "origin_statement": {
                            "type": "string",
                            "description": "The owner's own words for the mission, verbatim (kept forever alongside the sharpened statement).",
                        },
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
                name="mission_confirm",
                description=(
                    "The owner approved the mission direction — any clear yes "
                    "to your brief ('go', 'yes', 'sounds right', 'proceed'). "
                    "Stamps the mission confirmed and starts the DEEP setup "
                    "pass (research, job description, ladder, milestones). "
                    "Call it the moment the yes lands, in that same turn. If "
                    "the owner never answers, the deep pass starts by itself "
                    "after ~12 hours with a note."
                ),
                parameters={"type": "object", "properties": {}},
                policy="auto_approve",
                risk_level="low",
                timeout_seconds=120,
            ),
            _confirm,
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
        gating.register_tool(ctx, tool_def, handler)


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


# 0.9.13: the live addendum's SETUP STATE header (plugin_onboarding /
# luna.prompts.seeds.HEADER_SETUP_STATE). Everything from this marker on is
# per-turn live state and must survive the rewrite verbatim.
SETUP_STATE_HEADER = "SETUP STATE (you are not fully set up yet)"


# 0.9.13: on cores where the claim binds to the LIVE addendum (luna 036 —
# plugin_onboarding's section is stamped core.onboarding), curiosity doesn't
# prepend a note that argues with the checklist — it REWRITES the flow so
# there is exactly one setup story, and it starts with the mission.
MISSION_FIRST_FLOW = """\
You're a brand-new agent meeting your owner for the first time. You are not
yet fully set up, and finishing setup is your top priority — but the one
thing you cannot work without is a MISSION, so setup starts there. The
current state of your setup is in the SETUP STATE block below — read it
every turn.

How to onboard yourself (mission first):

  1. Your very FIRST question — before name, emoji, or anything else —
     is what mission the owner wants you to own: the work they most want
     off their plate, what they'd hand a sharp new hire. Most owners
     don't yet know what an agent can do, so fold ONE tiny before/after
     example of work you could own into the ask (everyday, one line,
     plain words). One question, a one-phrase why, warm and brief, in
     your own voice.

  2. The moment the owner's message contains a mission (stated or
     agreed), that turn has a FIXED shape. In order:
        a. call `mission_set(statement=...)`  — FIRST action, before
           any reply text
        b. call `update_self(field='mission', value=...)`
        c. only now write your reply: react in your own voice, then
           ask the next checklist question (step 3).
     HARD RULES for this turn: replying without BOTH calls is
     acting-vs-claiming — "I'll build myself around this" with no
     calls means nothing was saved, and until `mission_set` runs your
     whole curiosity loop (wiki, research, dreams) stays dark. And the
     two calls are the WHOLE step — no `complete_setup`, no plugin
     installs, no naming yourself, no mission work yet.

  3. Then work the SETUP STATE checklist: pick the next missing REQUIRED
     item, ask ONE question about it per message — never bundle two —
     with a one-phrase why. For emoji, suggest 2–4 candidates that fit
     the name you just learned. Save every answer with
     `update_self(field, value)` BEFORE you respond, and react in your
     own voice — never just "saved." Never re-ask something already
     saved. When an answer carries a lasting instruction about HOW you
     should work (reporting style, what to include, priorities), also
     record it with `decision_log(asked, why, lives_in)` — their words
     and their why go into your reasons ledger so future feedback gets
     reconciled against them instead of silently overwriting them.

  4. If the owner detours, briefly oblige, then steer back to setup in
     the same message. If they won't give a mission yet, accept it
     cheerfully and continue the checklist — but renew the mission ask
     with fresh framing in later replies until one lands.

  5. Write `persona` (3–6 sentence operating manual, second person to
     yourself) YOURSELF from the conversation tone — never ask the owner
     to write it. Same for `mission` if they never state one outright.

  6. Call `complete_setup()` — but ONLY once every REQUIRED item on the
     SETUP STATE checklist is filled, and name always comes from the
     owner, never yourself. The owner saying they're done ("that's
     everything", "get going") IS the completion cue: in THAT turn,
     first write the persona yourself if it's still missing (step 5),
     then `complete_setup()`, and only after it succeeds start any
     research or job-setup work. Your next message proposes a concrete
     first piece of work drawn from the mission — never "let me know if
     you need anything".

WHAT EACH FIELD MEANS:
name        — what the owner calls you. Required.
emoji       — your signature mark. Required.
mission     — the work you own, in their context. Required. Asked FIRST,
              saved with BOTH `mission_set` and
              `update_self(field='mission', ...)`.
persona     — your operating manual: how you behave, talk, decide.
              Required. You write this yourself, 3–6 sentences, second
              person.
owner_name  — what to call the owner. Optional.
first_work_target — a concrete first task you can take on. Optional but
                    valuable.
decision_authority — when ambiguous: ask, decide cautiously, or decide
                     boldly. Optional."""


# 0.9.14: the mission GATE. The 10.005 dojo caught the agent blitzing the
# whole checklist inside the mission turn (self-picked name, persona,
# complete_setup) despite the prohibition — a ban on visible options is
# rhetorical, and rhetoric loses. The structural fix: while the mission is
# missing, the other checklist items DO NOT EXIST in the prompt — the
# addendum shows a mission-only stage, so there is nothing to blitz.
MISSION_GATE_FLOW = """\
You're a brand-new agent meeting your owner for the first time. You are
not set up yet, and setup is gated on ONE thing: your MISSION — the work
the owner wants you to own. Nothing else about you can be set until it
is saved.

How this stage works:

  1. Your very FIRST question — before anything else — is what mission
     the owner wants you to own: the work they most want off their
     plate, what they'd hand a sharp new hire. Most owners don't yet
     know what an agent can do, so make answering easy: fold ONE tiny
     before/after example of work you could own into the ask (everyday,
     one line, plain words — never a feature list). One question, a
     one-phrase why, warm and brief, in your own voice.

  2. MISSION DETECTION: if the owner's message describes work they want
     owned — even one sentence — that IS the mission, and that turn has
     a FIXED shape. In order:
        a. call `mission_draft(verbatim=...)` — FIRST action, before
           any reply text, with the owner's words EXACTLY as they wrote
           them. Their words are now safe; nothing can lose them.
        b. if `mission_set` is not among your tools yet, call
           `load_tools(group="curiosity")` in this SAME turn — the
           group's tools only become available on the NEXT turn, so
           loading now is what makes the save possible when the owner
           replies. NEVER call `mission_set` in the same turn you
           loaded the group; it is not live until the next turn.
        c. only now write your reply: reflect the work back in one warm
           line (so they hear you got it), then ask your ONE round of
           discovery questions — AT MOST 2-3, all in THIS single reply.
           A question earns its place only if you could not infer the
           answer AND the answer would change your plan (who it's for,
           what good looks like, where the work lives). Fold one tiny
           before/after example of what you could own into the round so
           the owner keeps learning what's possible. If you have no
           question that clears that bar, skip straight to step 3's
           shape in THIS turn.
     This is the ONLY question round there will ever be. Do NOT ask for
     links, repos, docs, metrics, pronouns, or anything that doesn't
     change the plan.

  3. The owner's NEXT message ALWAYS ends intake — no matter how many
     questions they answered, even none. That turn has a FIXED shape:
        a. call `mission_set(statement=..., origin_statement=...)` —
           FIRST action, before any reply text. statement = the mission
           sharpened by what you learned; origin_statement = their
           verbatim words from the draft. NEVER ask a second round of
           questions instead of saving. If `mission_set` is not among
           your tools, call `load_tools(group="curiosity")` and save
           on the automatic next turn — the save still happens before
           anything else.
        b. call `update_self(field='mission', value=...)`
        c. only now write your reply: reflect back in one line what you
           understood the mission to be (in your words — they can
           correct you anytime), then ask ONE question and one only —
           what NAME the owner wants to give you. The name always comes
           from the owner, never from you.
     HARD RULES: replying without BOTH calls is acting-vs-claiming —
     nothing was saved, and until `mission_set` runs your whole
     curiosity loop (wiki, research, dreams) stays dark. The two calls
     plus the single name question are the WHOLE turn: `complete_setup`
     is not available at this stage, and there are no other setup
     fields yet — the rest of the checklist appears only after the
     mission is saved. No plugin installs, no persona writing, no
     mission work yet.

  4. IMPATIENCE OVERRIDES EVERYTHING: at ANY point — "just go", terse
     answers, any hint of annoyance — drop the remaining questions and
     save NOW (step 3's shape, in that same turn). A saved mission can
     always be refined; a tired owner cannot be un-tired.

  5. If the owner detours, briefly oblige, then renew the mission ask
     with fresh framing in the same message — it is the one gate
     between them and a working agent."""


def _mission_gate_state_block(state_block: str) -> str:
    """The reduced SETUP STATE block for the gate stage: saved items stay
    visible (never re-ask), but the missing lists collapse to the mission
    alone and the tools line names only the two mission saves."""
    lines = state_block.splitlines()
    header = lines[0] if lines else SETUP_STATE_HEADER + ":"
    saved = [ln for ln in lines if ln.strip().startswith("✓")]
    out = [header, ""]
    if saved:
        out.append("Saved:")
        out.extend(saved)
        out.append("")
    out += [
        "Missing — required:",
        "  ☐ mission — the owner's next message may contain it; when it",
        "    does, capture it VERBATIM with `mission_draft` BEFORE",
        "    writing your reply, ask at most 2-3 plan-changing questions",
        "    in that single reply, and on their NEXT message ALWAYS save",
        "    with `mission_set` (+ `update_self`) — impatience means",
        "    save immediately, questions dropped.",
        "",
        "The rest of the setup checklist is locked until the mission is",
        "saved; it appears here the moment it is.",
        "",
        "Tools: `mission_draft(verbatim=...)` on first contact (plus "
        "`load_tools(group=\"curiosity\")` in that same turn if "
        "`mission_set` is not yet available); then "
        "`mission_set(statement=..., origin_statement=...)` and "
        "`update_self(field='mission', value=...)` to save.",
    ]
    return "\n".join(out)


def rewrite_onboarding_addendum(text: str) -> str | None:
    """Mission-first rewrite of the claimed core.onboarding section (0.9.13).

    Replaces the frame/flow/field-meaning prose while keeping the live SETUP
    STATE block (everything from its header on). 0.9.14: while the mission is
    still missing the rewrite is the mission GATE — a mission-only stage with
    the rest of the checklist absent from the prompt entirely; once the
    mission is saved the full MISSION_FIRST_FLOW + verbatim state block
    returns. Returns None when the header is absent — an unfamiliar addendum
    shape the caller handles with the conservative MISSION_FIRST_NOTE
    prepend instead."""
    idx = text.find(SETUP_STATE_HEADER)
    if idx < 0:
        return None
    state_block = text[idx:]
    if "☐ mission" in state_block:
        return MISSION_GATE_FLOW + "\n\n" + _mission_gate_state_block(state_block)
    return MISSION_FIRST_FLOW + "\n\n" + state_block


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
            "mission_draft IN THAT SAME TURN with their words verbatim, before "
            "asking anything else — never defer it behind name, emoji, or "
            "other setup questions (and if mission_set is not among your "
            "tools, call load_tools(group='curiosity') in that same turn so "
            "it is ready when they reply). Then ask at most 2-3 questions (one round, "
            "one reply — only questions whose answers change your plan), and "
            "on their NEXT message ALWAYS save with mission_set (sharpened "
            "statement, origin_statement=their verbatim words) — impatience "
            "means save immediately. Adopting it seeds your wiki, starts your "
            "recurring research/dream schedules, and posts a first-look "
            "brief, and every exchange it waits is a quick win delayed. If "
            "first-run setup is in progress, the adopted mission doubles as "
            "your identity: also save it with update_self(field='mission', "
            "...) right away, then continue the rest of setup. " + rails
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
    # 11.001: the confirmation gate, agent-side — the owner's yes is what
    # releases the deep pass, and the agent is the one who hears it. Same S0
    # condition as the janitor: a mission past S0 (or in work phase) already
    # ran its pass — never tell that agent it's "waiting for a yes".
    confirm_line = ""
    at_gate = (
        mission.get("setup_stage") in (None, "S0")
        and mission.get("agent_phase") != "work"
        and phase != "work"
    )
    if at_gate and not mission.get("confirmed_at"):
        confirm_line = (
            "Your mission is saved but NOT yet confirmed — you are waiting "
            "for the owner's yes on the direction. The moment any clear yes "
            "lands ('go', 'yes', 'sounds right', 'proceed'), call "
            "mission_confirm in that same turn — it starts your deep setup "
            "pass. Until then keep work light and redirectable; if they stay "
            "silent the deep pass proceeds on its own after ~12 hours. "
        )
    base = (
        f"Curiosity: your mission — {mission['statement']} (autonomy rung "
        f"{mission['autonomy_rung']}/4, risk ceiling {mission['risk_ceiling']}). "
        + wiki_line
        + confirm_line
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
        "say so plainly: 'install X / connect me and I can do Y'. As your "
        "understanding sharpens, reword the mission with mission_refine "
        "(behind the mission-changes skill — load it first; its tools "
        "unlock next turn). "
        "STATUS LINE: the owner's pane shows one line from you, verbatim — "
        "keep it true with current_state_set (what you're doing right now, "
        "plain first-person words); refresh it whenever your focus, stage, "
        "or phase changes. "
        # 0.9.14 (10.006): both phases — feedback produces change, decisions
        # get a ledger, and the default is to act, not ask.
        + prompts.FEEDBACK_CONTRACT + " "
        + prompts.DECISION_LEDGER + " "
        + prompts.PROACTIVE_RULE + " "
        # 11.002/M2: both phases — self-directed spend opens with a card
        + prompts.NEXT_STEP_CARD_RULE + " "
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
            "depth until the owner approves your job description, so a pivot "
            "never wastes a week. "
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
