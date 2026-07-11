"""overview.py — the Missions pane's data layer (9.002B).

One aggregation, `build_overview`, feeds the whole pane: mission + history,
the setup dial, the gap board, goals, loops, value log, heartbeat pulse,
pace/sentiment (computed in telemetry.py — exactly one implementation to
explain), the wiki knowledge shelf, the merged activity stream, and the
work-phase NOC wall parsed from [[success-criteria]].

Everything cross-plugin is best-effort: a missing wiki page degrades to an
`exists: false` shelf entry, an unreachable scheduler degrades to an empty
trigger list — the overview endpoint itself must never 500 while the pane is
the owner's window into a possibly half-broken install.

The NOC wall parses structure the prompts FORCE (prompts.SUCCESS_TABLE_SHAPE
and WEEKLY_SCORES_SHAPE): a `| criterion | measure | target | horizon |`
table and `- <date> | <criterion> | <status> | <evidence>` score lines under
"## Weekly scores". Parsers are lenient about whitespace and extra columns
but never guess: unparseable lines are skipped, and the pane shows what the
agent actually wrote.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from luna_sdk import PluginContext

from . import telemetry
from .abilities import AbilityStore
from .goals import GoalStore
from .loops import LoopStore, _loop_dict, _value_dict
from .mission import MissionStore, _mission_dict
from .models import (
    Ability,
    AbilityTask,
    HeartbeatReport,
    Loop,
    Mission,
    PlanChange,
    Scope,
    ValueEntry,
)
from .scopes import _KIND_LABEL, SCOPE_KINDS, SETUP_STAGES, ScopeStore
from .telemetry import HeartbeatStore

log = logging.getLogger("plugin-curiosity")

# The knowledge shelf — every owner-facing page curiosity maintains, in
# reading order. Labels say what each page IS (self-explanation layer 1).
WIKI_SHELF = (
    ("mission", "Mission hub", "the mission statement and its trailhead"),
    ("job-description", "Job description", "how Luna will do the job — her living draft"),
    ("role-charter", "Role charter", "scopes, stage marker, plan changes"),
    ("success-criteria", "Success criteria", "what success looks like — the scoreboard"),
    ("mission-goals", "Goals", "the dated commitments Luna scores weekly"),
    ("mission-domain", "Domain map", "what Luna has learned about the territory"),
    ("mission-open-questions", "Open questions", "what Luna knows she doesn't know"),
    ("open-loops", "Open loops", "questions, promises, asks — nothing vanishes"),
    ("value-log", "Value log", "delivered wins with checkable evidence"),
    ("setup-heartbeat", "Heartbeat journal", "verdict lines from every heartbeat fire"),
)

STAGE_LABELS = {
    "S0": ("understood", "mission restated sharper, first observations recorded"),
    "S1": ("inventoried", "scopes chartered, reachable tools verified, first value delivered"),
    "S2": ("posted", "job description, charter, success criteria and dated goals posted to the owner"),
    "S3": ("ratified", "the owner ratified the job description, charter and success criteria"),
    "S4": ("validated", "one real workflow run validated end-to-end"),
    "S5": ("wired", "live feedback signals flowing per scope"),
}

SCORE_STATUSES = ("on-track", "at-risk", "met", "missed")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_dt(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


# --- NOC wall parsers (the structure prompts.SUCCESS_TABLE_SHAPE forces) ----


def parse_criteria_table(body: str) -> list[dict[str, str]]:
    """Rows of the `| criterion | measure | target | horizon |` table."""
    rows: list[dict[str, str]] = []
    in_table = False
    for line in (body or "").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            in_table = False
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        head = [c.lower() for c in cells[:4]]
        if head == ["criterion", "measure", "target", "horizon"]:
            in_table = True
            continue
        if set(cells[0]) <= {"-", ":", " "}:  # separator row
            continue
        if in_table:
            rows.append(
                {
                    "criterion": cells[0],
                    "measure": cells[1],
                    "target": cells[2],
                    "horizon": cells[3],
                }
            )
    return rows


_SCORE_LINE = re.compile(r"^[-*]\s+(.+)$")


def parse_weekly_scores(body: str) -> list[dict[str, str]]:
    """`- <date> | <criterion> | <status> | <evidence>` lines under the
    '## Weekly scores' heading. Newest last (append-only by contract)."""
    scores: list[dict[str, str]] = []
    in_section = False
    for line in (body or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            in_section = "weekly scores" in stripped.lstrip("# ").lower()
            continue
        if not in_section:
            continue
        m = _SCORE_LINE.match(stripped)
        if not m:
            continue
        parts = [p.strip() for p in m.group(1).split("|")]
        if len(parts) < 3:
            continue
        status = parts[2].lower()
        if status not in SCORE_STATUSES:
            continue
        scores.append(
            {
                "date": parts[0],
                "criterion": parts[1],
                "status": status,
                "evidence": parts[3] if len(parts) > 3 else "",
            }
        )
    return scores


# --- job-description parser (the structure prompts.JOB_DESCRIPTION_SHAPE ----
# --- forces: four headed sections, bullets/numbered items inside) -----------

# (key, the heading text the prompt mandates) — matching is case-insensitive
# and ignores trailing punctuation, but never guesses a missing section.
JD_SECTIONS = (
    ("method", "how i will accomplish this mission"),
    ("after_onboarding", "after onboarding"),
    ("in_30_days", "in 30 days"),
    ("working_assumptions", "working assumptions"),
)

_JD_ITEM = re.compile(r"^(?:[-*]|\d+[.)])\s+(.+)$")


def parse_job_description(body: str) -> dict[str, Any]:
    """The 4-block [[job-description]] structure. Bullets and numbered items
    under each mandated `##` heading; free prose between items is kept as the
    section's intro line. shape_ok only when all four sections exist with at
    least one item each — otherwise the raw body rides along so the pane can
    show what the agent actually wrote instead of guessing."""
    wanted = {heading: key for key, heading in JD_SECTIONS}
    sections: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    for line in (body or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("##"):
            title = stripped.lstrip("# ").strip().rstrip(":.").lower()
            key = wanted.get(title)
            current = None
            if key is not None:
                current = {"intro": "", "items": []}
                sections[key] = current
            continue
        if current is None or not stripped:
            continue
        m = _JD_ITEM.match(stripped)
        if m:
            current["items"].append(m.group(1).strip())
        elif not current["items"] and not current["intro"]:
            current["intro"] = stripped
    shape_ok = all(
        key in sections and sections[key]["items"] for key, _ in JD_SECTIONS
    )
    out: dict[str, Any] = {
        "exists": bool((body or "").strip()),
        "shape_ok": shape_ok,
        "sections": sections,
    }
    if not shape_ok:
        out["raw"] = body or ""
    return out


def build_noc(criteria: list[dict], scores: list[dict]) -> dict[str, Any]:
    """Work-phase role wall: one tile per criterion (latest score wins),
    incident strip (at-risk/missed, newest first), per-criterion uptime
    (share of scored weeks that were on-track or met)."""
    tiles = []
    for c in criteria:
        own = [s for s in scores if s["criterion"].lower() == c["criterion"].lower()]
        latest = own[-1] if own else None
        good = sum(1 for s in own if s["status"] in ("on-track", "met"))
        tiles.append(
            {
                **c,
                "latest": latest,
                "scored_weeks": len(own),
                "uptime_pct": round(100 * good / len(own)) if own else None,
            }
        )
    incidents = [s for s in reversed(scores) if s["status"] in ("at-risk", "missed")]
    return {"tiles": tiles, "incidents": incidents[:10], "scores_total": len(scores)}


# --- best-effort cross-plugin reads -----------------------------------------


async def wiki_shelf(ctx: PluginContext) -> list[dict[str, Any]]:
    try:
        wiki = ctx.provider_registry.get("wiki")
    except Exception:  # noqa: BLE001
        return [
            {"slug": slug, "label": label, "role": role, "exists": False}
            for slug, label, role in WIKI_SHELF
        ]
    shelf = []
    for slug, label, role in WIKI_SHELF:
        entry: dict[str, Any] = {"slug": slug, "label": label, "role": role, "exists": False}
        try:
            page = await wiki.get_page(slug)
        except Exception:  # noqa: BLE001
            page = None
        if page:
            entry.update(
                exists=True,
                title=page.get("title") or label,
                summary=page.get("summary", ""),
                age_days=page.get("age_days"),
                updated_at=page.get("updated_at"),
            )
        shelf.append(entry)
    return shelf


async def wiki_page_body(ctx: PluginContext, slug: str) -> str:
    try:
        wiki = ctx.provider_registry.get("wiki")
        page = await wiki.get_page(slug)
        return (page or {}).get("body", "") or ""
    except Exception:  # noqa: BLE001
        return ""


async def trigger_snapshot(ctx: PluginContext) -> list[dict[str, Any]]:
    """Curiosity's own triggers (name starts with 'curiosity-'), or [] when
    the scheduler can't be consulted."""
    try:
        lister = ctx.tool_registry.get("trigger_list").handler
        listed = await lister()
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(listed, dict) or "error" in listed:
        return []
    out = []
    for t in listed.get("triggers", []):
        name = t.get("name", "")
        if not name.startswith("curiosity-"):
            continue
        out.append(
            {
                "name": name,
                "schedule": t.get("schedule") or t.get("cron") or t.get("spec") or "",
                "next_fire_at": t.get("next_fire_at") or t.get("next_run_at"),
                "enabled": t.get("enabled", True),
            }
        )
    return out


# --- the aggregation ---------------------------------------------------------


def _setup_checklist(setup_stage: str) -> dict[str, Any]:
    """S0-S5 as a checklist: stages at or below the marker are done, the next
    one is current. Completion % counts done stages out of six."""
    try:
        reached = SETUP_STAGES.index(setup_stage)
    except ValueError:
        reached = -1
    stages = []
    for i, sid in enumerate(SETUP_STAGES):
        label, detail = STAGE_LABELS[sid]
        status = "done" if i <= reached else ("current" if i == reached + 1 else "pending")
        stages.append({"id": sid, "label": label, "detail": detail, "status": status})
    return {"stages": stages, "percent": round(100 * (reached + 1) / len(SETUP_STAGES))}


def _overdue(loops_open: list[dict], now: datetime) -> list[dict]:
    out = []
    for lp in loops_open:
        nxt = _parse_dt(lp.get("next_nudge_at"))
        if nxt is not None and nxt < now:
            out.append(lp)
    return out


def _needs_from_you(
    loops_open: list[dict],
    setup_stage: str | None,
    agent_phase: str | None,
    plan_changes: list[dict] | None = None,
) -> list[dict[str, Any]]:
    """What the owner can unblock right now — asks first, then anything
    waiting on the owner, then role-pivot proposals awaiting a decision,
    then the S2 ratification CTA."""
    needs: list[dict[str, Any]] = []
    for lp in loops_open:
        if lp["kind"] == "ask":
            needs.append(
                {
                    "kind": "ask",
                    "text": lp["statement"],
                    "unlock": lp.get("unlock", ""),
                    "human_cost": lp.get("human_cost", ""),
                    "loop_id": lp["id"],
                }
            )
        elif "owner" in (lp.get("who") or "").lower():
            needs.append(
                {
                    "kind": lp["kind"],
                    "text": lp["statement"],
                    "loop_id": lp["id"],
                }
            )
    for pc in plan_changes or []:
        needs.append(
            {
                "kind": "pivot",
                "text": pc["entry"],
                "date": pc.get("date", ""),
            }
        )
    if agent_phase == "setup" and setup_stage == "S2":
        needs.append(
            {
                "kind": "ratify",
                "text": (
                    "The charter and success criteria are posted and waiting "
                    "for your ratification — reply in chat to ratify or push back."
                ),
            }
        )
    return needs


def _what_next(
    agent_phase: str | None, setup_stage: str | None, triggers: list[dict]
) -> list[dict[str, Any]]:
    """The 'what happens next' strip: the next stage to earn, then each live
    trigger with its cadence."""
    items: list[dict[str, Any]] = []
    if agent_phase == "setup" and setup_stage in SETUP_STAGES:
        idx = SETUP_STAGES.index(setup_stage)
        if idx + 1 < len(SETUP_STAGES):
            nxt = SETUP_STAGES[idx + 1]
            label, detail = STAGE_LABELS[nxt]
            items.append(
                {"kind": "stage", "title": f"Earn {nxt} ({label})", "detail": detail}
            )
        else:
            items.append(
                {
                    "kind": "stage",
                    "title": "Graduate to work mode",
                    "detail": "phase_advance — the owner-approved graduation gate",
                }
            )
    elif agent_phase == "work":
        items.append(
            {
                "kind": "stage",
                "title": "Execute the role",
                "detail": "weekly review scores every success criterion",
            }
        )
    for t in triggers:
        items.append(
            {
                "kind": "trigger",
                "title": t["name"],
                "detail": t.get("schedule", ""),
                "next_fire_at": t.get("next_fire_at"),
            }
        )
    return items


def _activity(
    plan_changes: list[dict],
    value_log: list[dict],
    heartbeats: list[dict],
    goals: list[dict],
    loops_all: list[dict],
    limit: int = 30,
) -> list[dict[str, Any]]:
    """One merged, newest-first stream of everything that happened."""
    events: list[tuple[str, dict]] = []
    for pc in plan_changes:
        text = pc["entry"]
        if pc.get("kind") == "role_pivot":
            text = "ROLE PIVOT — " + text
        events.append(
            (
                pc["date"],
                {
                    "kind": "plan",
                    "text": text,
                    "at": pc["date"],
                    "change_kind": pc.get("kind", "refine"),
                },
            )
        )
    for v in value_log:
        at = v.get("delivered_at") or ""
        events.append((at, {"kind": "value", "text": v["statement"], "at": at}))
    for h in heartbeats:
        at = h.get("created_at") or ""
        text = f"heartbeat — streak {h['streak']}, {h['gaps_open']} gaps, {h['wobbles']} wobbles"
        if h.get("note"):
            text += f": {h['note']}"
        events.append((at, {"kind": "heartbeat", "text": text, "at": at, "morale": h.get("morale", "")}))
    for g in goals:
        at = g.get("updated_at") or g.get("created_at") or ""
        events.append((at, {"kind": "goal", "text": f"[{g['status']}] {g['statement']}", "at": at}))
    for lp in loops_all:
        if lp["status"] == "open":
            at = lp.get("opened_at") or ""
            events.append((at, {"kind": "loop", "text": f"opened ({lp['kind']}): {lp['statement']}", "at": at}))
        else:
            at = lp.get("closed_at") or ""
            events.append((at, {"kind": "loop", "text": f"{lp['status']}: {lp['statement']}", "at": at}))
    events.sort(key=lambda e: e[0], reverse=True)
    return [e[1] for e in events[:limit]]


async def build_overview(
    ctx: PluginContext,
    *,
    missions: MissionStore,
    scope_store: ScopeStore,
    goal_store: GoalStore,
    loop_store: LoopStore,
    heartbeat_store: HeartbeatStore,
    ability_store: AbilityStore | None = None,
) -> dict[str, Any]:
    from . import DEPENDENCIES, CuriosityPlugin, missing_dependencies  # runtime state, not import-time

    now = _utcnow()
    missing = missing_dependencies(ctx)
    blocked = (
        {
            "missing": missing,
            "deps": {name: spec["why"] for name, spec in DEPENDENCIES.items()},
        }
        if missing
        else None
    )

    all_missions = await missions.list_all()
    active = next((m for m in all_missions if m["active"]), None)
    state = await scope_store.state()
    agent_phase = state["agent_phase"] if state else None
    setup_stage = state["setup_stage"] if state else None

    scopes_list = await scope_store.list()
    goals_list = await goal_store.list()
    loops_all = await loop_store.list()
    loops_open = [lp for lp in loops_all if lp["status"] == "open"]
    value_log = await loop_store.value_list()
    plan_changes = await scope_store.plan_changes()

    # 10.001: the qualification ladder. setup_percent prefers the ability
    # mean; a pre-0.9.0 mission with no abilities yet falls back to the
    # 9.002 stage-weighted % so the dial never goes blank mid-upgrade.
    abilities_list: list[dict[str, Any]] = []
    ability_percent = None
    if ability_store is not None:
        listed = await ability_store.list()
        abilities_list = listed["abilities"]
        ability_percent = listed["setup_percent"]

    # 10.001: the agent's own job description, parsed into the four blocks
    # the prompts force (shape_ok=false carries the raw body instead).
    job_description = None
    if active is not None:
        jd = parse_job_description(await wiki_page_body(ctx, "job-description"))
        jd["role_version"] = active.get("role_version", 1)
        pivots = [pc for pc in plan_changes if pc.get("kind") == "role_pivot"]
        jd["latest_pivot"] = pivots[-1] if pivots else None
        job_description = jd

    # a pivot proposal is an owner decision — surface recent ones (14 days)
    # in needs_from_you; older ones live on in the activity stream only
    recent_pivots = [
        pc
        for pc in plan_changes
        if pc.get("kind") == "role_pivot"
        and (nd := _parse_dt(pc.get("date"))) is not None
        and (now - nd).days <= 14
    ]
    heartbeats = await heartbeat_store.list(
        limit=30, mission_id=active["id"] if active else None
    )
    latest_hb = heartbeats[0] if heartbeats else None
    prev_hb = heartbeats[1] if len(heartbeats) > 1 else None

    overdue = _overdue(loops_open, now)
    blocked_on_owner = sum(1 for lp in overdue if lp["kind"] in ("ask", "waiting_on"))

    pace = None
    sentiment = None
    if state is not None:
        pace = telemetry.compute_pace(
            agent_phase=agent_phase,
            setup_stage=setup_stage,
            stage_age_days=state["stage_age_days"],
            overdue_loops=len(overdue),
            now=now,
            last_report_at=_parse_dt(latest_hb["created_at"]) if latest_hb else None,
        )
        sentiment = telemetry.compute_sentiment(
            latest_hb, prev_hb, blocked_on_owner=blocked_on_owner
        )

    triggers = await trigger_snapshot(ctx)
    shelf = await wiki_shelf(ctx)

    noc = None
    if agent_phase == "work" or setup_stage in ("S2", "S3", "S4", "S5"):
        body = await wiki_page_body(ctx, "success-criteria")
        criteria = parse_criteria_table(body)
        scores = parse_weekly_scores(body)
        if criteria or scores:
            noc = build_noc(criteria, scores)

    gap_board = []
    for kind in SCOPE_KINDS:
        own = [sc for sc in scopes_list if sc["kind"] == kind]
        if own:
            gap_board.append({"kind": kind, "label": _KIND_LABEL[kind], "scopes": own})

    setup = _setup_checklist(setup_stage) if agent_phase == "setup" and setup_stage else None

    return {
        "generated_at": now.isoformat(),
        "plugin_version": CuriosityPlugin.manifest.version,
        "blocked": blocked,
        "mission": active,
        "missions": all_missions,
        "state": state,
        "setup": setup,
        # 10.001: the honest dial — ability-task mean when a ladder exists,
        # the 9.002 stage % during the upgrade window, None with no mission
        "setup_percent": (
            ability_percent
            if ability_percent is not None
            else (setup["percent"] if setup else None)
        ),
        "abilities": abilities_list,
        "job_description": job_description,
        "gap_board": gap_board,
        "goals": goals_list,
        "loops": {"open": loops_open, "overdue": len(overdue), "all_count": len(loops_all)},
        "value_log": value_log,
        "plan_changes": plan_changes,
        "heartbeats": {"latest": latest_hb, "recent": heartbeats[:10]},
        "pace": pace,
        "sentiment": sentiment,
        "needs_from_you": _needs_from_you(
            loops_open, setup_stage, agent_phase, recent_pivots
        ),
        "next_up": _what_next(agent_phase, setup_stage, triggers),
        "wiki_shelf": shelf,
        "noc": noc,
        "activity": _activity(plan_changes, value_log, heartbeats, goals_list, loops_all),
    }


async def mission_detail(sf, mission_id: str) -> dict[str, Any] | None:
    """One mission row + everything keyed to it — the history-shelf drilldown.
    Reads the tables directly: the stores answer only for the ACTIVE mission,
    and history is exactly the non-active ones."""
    try:
        key = uuid.UUID(str(mission_id))
    except ValueError:
        return None
    async with sf() as s:
        m = await s.get(Mission, key)
        if m is None:
            return None
        scopes_rows = (
            (await s.execute(select(Scope).where(Scope.mission_id == key).order_by(Scope.kind, Scope.created_at)))
            .scalars().all()
        )
        loops_rows = (
            (await s.execute(select(Loop).where(Loop.mission_id == key).order_by(Loop.opened_at)))
            .scalars().all()
        )
        value_rows = (
            (await s.execute(select(ValueEntry).where(ValueEntry.mission_id == key).order_by(ValueEntry.delivered_at)))
            .scalars().all()
        )
        pc_rows = (
            (await s.execute(select(PlanChange).where(PlanChange.mission_id == key).order_by(PlanChange.created_at)))
            .scalars().all()
        )
        hb_rows = (
            (await s.execute(select(HeartbeatReport).where(HeartbeatReport.mission_id == key).order_by(HeartbeatReport.created_at.desc()).limit(30)))
            .scalars().all()
        )
        ability_rows = (
            (await s.execute(select(Ability).where(Ability.mission_id == key).order_by(Ability.sort_order, Ability.created_at)))
            .scalars().all()
        )
        from .abilities import _ability_dict
        from .scopes import _scope_dict
        from .telemetry import _report_dict

        ability_dicts = []
        for a in ability_rows:
            task_rows = (
                (await s.execute(select(AbilityTask).where(AbilityTask.ability_id == a.id).order_by(AbilityTask.sort_order)))
                .scalars().all()
            )
            ability_dicts.append(_ability_dict(a, task_rows))

        return {
            "mission": _mission_dict(m),
            "scopes": [_scope_dict(sc) for sc in scopes_rows],
            "abilities": ability_dicts,
            "loops": [_loop_dict(lp) for lp in loops_rows],
            "value_log": [_value_dict(v) for v in value_rows],
            "plan_changes": [
                {
                    "entry": pc.entry,
                    "date": pc.created_at.date().isoformat(),
                    "kind": getattr(pc, "kind", "refine") or "refine",
                }
                for pc in pc_rows
            ],
            "heartbeats": [_report_dict(r) for r in hb_rows],
        }
