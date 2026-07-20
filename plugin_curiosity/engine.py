"""engine.py — the single goal-engine switch (0.10.0, phase 07).

Curiosity's whole goal machinery routes through ONE resolved value:

- ``goalseek`` — plugin-goalseek is installed; mission goals live in its
  governed engine (stages, policies, heartbeats, the Goals pane). Curiosity's
  ``goal_set`` delegates the open and keeps a pointer row for mission
  grouping; ``goal_update``/``goal_list`` are served by goal-seek itself
  (curiosity registers them as deferential fallbacks — see goals.py).
- ``internal`` — standalone curiosity, exactly the 0.9.x ledger.

One switch, obeyed everywhere: no other module may probe the registry for
``goal_*`` tools — every goal-seek touch (detection, delegated opens, live
reads) lives HERE, enforced by a guard test. Scattered per-path detection is
how half-switched bugs happen.

Manual override for debugging only (documented as unsupported-for-users):
``LUNA_CURIOSITY_GOAL_ENGINE=internal|goalseek``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger("plugin-curiosity")

GOAL_ENGINE_INTERNAL = "internal"
GOAL_ENGINE_GOALSEEK = "goalseek"

# Goal-seek's open tool is the detection probe: it exists in every goal-seek
# version and no other plugin registers it. (goal_list/goal_update would be
# ambiguous — curiosity itself serves those names when standalone.)
_PROBE_TOOL = "goal_open"

# Last resolved value — pane/overview visibility only, never a decision input
# (resolution is a dict lookup; probing live on every call can't go stale).
_last: dict[str, str | None] = {"value": None}


def resolve_goal_engine(ctx: Any) -> str:
    """The switch. Live probe on every call; env override wins."""
    override = (os.environ.get("LUNA_CURIOSITY_GOAL_ENGINE") or "").strip().lower()
    if override in (GOAL_ENGINE_INTERNAL, GOAL_ENGINE_GOALSEEK):
        _last["value"] = override
        return override
    try:
        ctx.tool_registry.get(_PROBE_TOOL)
        resolved = GOAL_ENGINE_GOALSEEK
    except Exception:  # noqa: BLE001 - any resolution failure = not installed
        resolved = GOAL_ENGINE_INTERNAL
    if _last["value"] != resolved:
        log.info("goal engine resolved: %s", resolved)
    _last["value"] = resolved
    return resolved


def last_resolved() -> str | None:
    """What the switch said last time anyone asked (pane display only)."""
    return _last["value"]


# --- the only goal-seek call sites in the package ---------------------------


async def _call(ctx: Any, tool: str, /, **kwargs: Any) -> dict[str, Any]:
    handler = ctx.tool_registry.get(tool).handler
    out = await handler(**kwargs)
    if not isinstance(out, dict):  # pragma: no cover - goal-seek returns dicts
        return {"result": out}
    return out


def _iso_or_none(free_text: str | None) -> str | None:
    """Goal-seek deadlines are real datetimes; curiosity target dates are
    free-form ('end of July'). Pass through only what parses — anything else
    rides in the provenance note instead of breaking the open."""
    if not free_text:
        return None
    from datetime import datetime

    try:
        datetime.fromisoformat(free_text.strip())
    except ValueError:
        return None
    return free_text.strip()


async def engine_open(
    ctx: Any,
    *,
    statement: str,
    definition_of_done: str,
    deadline: str | None = None,
    opened_by: str = "agent",
    note: str | None = None,
    mission_id: str | None = None,
) -> dict[str, Any]:
    """Delegate one open to goal-seek. Returns goal-seek's goal dict (raises
    what goal-seek raises — the caller reports honestly). The open may come
    back stage='proposed' (agent opens await an owner card): that is a valid
    outcome, not an error — the goal activates by itself on approve.
    ``opened_via='curiosity'`` (+ mission id) rides along as provenance;
    engines that don't know the kwarg ignore it."""
    iso_deadline = _iso_or_none(deadline)
    if deadline and not iso_deadline:
        note = f"Target: {deadline}. {note or ''}".strip()
    out = await _call(
        ctx,
        "goal_open",
        statement=statement,
        definition_of_done=definition_of_done,
        deadline=iso_deadline,
        opened_by=opened_by,
        opened_via="curiosity",
        **({"mission_id": str(mission_id)} if mission_id else {}),
    )
    gid = out.get("id")
    if note and gid and out.get("status") != "rejected":
        try:
            await _call(ctx, "goal_update", goal_id=gid, note=note)
        except Exception:  # noqa: BLE001 - the note is provenance, not the open
            log.debug("post-open note failed for %s", gid, exc_info=True)
    return out


async def engine_list(ctx: Any, *, include_closed: bool = True) -> list[dict[str, Any]]:
    """Live goal list from goal-seek (its own dict shape — see goals.py for
    the mapping into curiosity's)."""
    out = await _call(ctx, "goal_list", include_closed=include_closed)
    goals = out.get("goals")
    return list(goals) if isinstance(goals, list) else []


async def engine_get(ctx: Any, goal_id: str) -> dict[str, Any]:
    """One live goal with its table summary (v2 carries counts and the
    needs-you number that the lean list omits). Raises what goal-seek raises;
    a pre-v2 goal comes back marked ``legacy_v1`` — see goals.py's repoint
    pass."""
    return await _call(ctx, "goal_get", goal_id=goal_id)


# --- curiosity-shape mapping -------------------------------------------------

# goal-seek stage/outcome → curiosity status. Open stages are all "active"
# (parked/waiting/proposed are engine mechanics, not owner-facing statuses);
# terminal outcomes map by their honest meaning.
_OUTCOME_STATUS = {
    "achieved": "done",
    "abandoned": "dropped",
    "expired": "dropped",
    "failed": "stalled",
    "escalated": "stalled",
}


def _progress_note(g: dict[str, Any]) -> str:
    """One owner-readable line: '18/50 done · needs you: 2' from a v2 table
    summary; a closed goal's reason; empty when the engine said nothing."""
    table = g.get("table")
    if isinstance(table, dict) and table.get("total") is not None:
        parts = [f"{table.get('terminal', 0)}/{table.get('total', 0)} done"]
        waiting = table.get("waiting") or 0
        if waiting:
            parts.append(f"{waiting} waiting")
        needs_you = g.get("needs_you") or 0
        if needs_you:
            parts.append(f"needs you: {needs_you}")
        return " · ".join(parts)
    reason = g.get("outcome_reason")
    if isinstance(reason, dict):
        return reason.get("summary", "")
    return ""


def to_curiosity_dict(g: dict[str, Any]) -> dict[str, Any]:
    """A goal-seek goal rendered in the dict shape curiosity's pane, mirror,
    and activity stream already consume — plus the engine truth fields
    (``engine``/``stage``/``outcome``) so no surface has to guess. v2 dicts
    carry a ``table`` summary — it becomes the progress line."""
    stage = g.get("stage") or ""
    outcome = g.get("outcome") or None
    if stage == "closed":
        status = _OUTCOME_STATUS.get(outcome or "", "dropped")
    else:
        # proposed/active/parked are all "active" to curiosity's 4-status
        # ledger; the stage field carries the engine truth for richer surfaces
        status = "active"
    deadline = g.get("deadline") or ""
    return {
        "id": str(g.get("id") or ""),
        "statement": g.get("statement") or "",
        "why": "",
        "target_date": str(deadline)[:10] if deadline else "",
        "status": status,
        "progress_note": _progress_note(g),
        "expected_result": g.get("definition_of_done") or "",
        "readiness": None,
        "readiness_note": "",
        "created_at": g.get("created_at"),
        "updated_at": g.get("updated_at") or g.get("created_at"),
        # engine truth — surfaces that can say more, do
        "engine": GOAL_ENGINE_GOALSEEK,
        "stage": stage,
        "outcome": outcome,
        "outcome_label": g.get("outcome_label"),
    }
