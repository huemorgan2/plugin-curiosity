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
) -> dict[str, Any]:
    """Delegate one open to goal-seek. Returns goal-seek's goal dict (raises
    what goal-seek raises — the caller reports honestly)."""
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


def to_curiosity_dict(g: dict[str, Any]) -> dict[str, Any]:
    """A goal-seek goal rendered in the dict shape curiosity's pane, mirror,
    and activity stream already consume — plus the engine truth fields
    (``engine``/``stage``/``outcome``) so no surface has to guess."""
    stage = g.get("stage") or ""
    outcome = g.get("outcome") or None
    if stage == "closed":
        status = _OUTCOME_STATUS.get(outcome or "", "dropped")
    else:
        status = "active"
    deadline = g.get("deadline") or ""
    return {
        "id": str(g.get("id") or ""),
        "statement": g.get("statement") or "",
        "why": "",
        "target_date": str(deadline)[:10] if deadline else "",
        "status": status,
        "progress_note": (g.get("outcome_reason") or {}).get("summary", "")
        if isinstance(g.get("outcome_reason"), dict)
        else "",
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
