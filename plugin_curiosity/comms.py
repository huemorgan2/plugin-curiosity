"""comms.py — share_thought: the proactive-reflection channel, with guardrails.

A thought posts as a `source="curiosity"` *moment* (phase-3 hook): a collapsed
muted line plus a badged reply bubble in which Luna voices the thought. The
reaction turn gets the wiki read tools so the voiced thought can ground itself
in current wiki state.

Guardrails (the noise budget):
* grounding — the body must cite a [[wiki-page]] or an http(s) source; no
  ungrounded musing.
* cadence — at most ONE routine reflection per local day. kickoff/dream kinds
  are exempt (their cadence is structural: once per mission / once per night).
* quiet hours — 21:00–08:00 local: the thought queues instead of posting. The
  queue drains on the next share_thought call, plugin load, or the /comms/drain
  route outside quiet hours. A drained routine thought counts against that
  day's cap.

Posting is fire-and-forget (`asyncio.create_task`) so the tool handler never
blocks its own agent turn waiting on the reaction turn. contextvars are
inherited by the task, so a thought shared mid-conversation lands in that
conversation.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from luna_sdk import PluginContext, ToolDef

from .models import Reflection

log = logging.getLogger("plugin-curiosity")

QUIET_START_HOUR = 21  # inclusive, local time
QUIET_END_HOUR = 8  # exclusive, local time
ROUTINE_DAILY_CAP = 1

# grounded = links a wiki page or cites a fresh web source
_GROUNDING_RE = re.compile(r"\[\[[^\]]+\]\]|https?://\S+", re.IGNORECASE)

# allowlist for the reaction turn that voices the thought (read-only grounding)
REFLECTION_TOOLS = ["wiki_toc", "wiki_read", "wiki_search", "mission_get"]


def _now_local() -> datetime:
    return datetime.now(UTC).astimezone()


def in_quiet_hours(now: datetime | None = None) -> bool:
    hour = (now or _now_local()).hour
    return hour >= QUIET_START_HOUR or hour < QUIET_END_HOUR


def is_grounded(body: str) -> bool:
    return bool(_GROUNDING_RE.search(body))


def _local_midnight_utc(now: datetime | None = None) -> datetime:
    local = now or _now_local()
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


class ReflectionLog:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    async def add(self, *, kind: str, title: str, body: str, status: str) -> dict[str, Any]:
        async with self._sf() as s:
            row = Reflection(
                kind=kind,
                title=title,
                body=body,
                status=status,
                posted_at=datetime.now(UTC) if status == "posted" else None,
            )
            s.add(row)
            await s.commit()
            return {"id": row.id, "kind": row.kind, "status": row.status}

    async def routine_posted_today(self) -> int:
        """Routine reflections posted since local midnight (cap accounting)."""
        async with self._sf() as s:
            rows = (
                await s.execute(
                    select(Reflection).where(
                        Reflection.kind == "routine",
                        Reflection.status == "posted",
                        Reflection.posted_at >= _local_midnight_utc(),
                    )
                )
            ).scalars().all()
            return len(rows)

    async def queued(self) -> list[dict[str, Any]]:
        async with self._sf() as s:
            rows = (
                await s.execute(
                    select(Reflection)
                    .where(Reflection.status == "queued")
                    .order_by(Reflection.created_at)
                )
            ).scalars().all()
            return [
                {"id": r.id, "kind": r.kind, "title": r.title, "body": r.body}
                for r in rows
            ]

    async def mark_posted(self, reflection_id) -> None:
        async with self._sf() as s:
            row = await s.get(Reflection, reflection_id)
            if row is not None:
                row.status = "posted"
                row.posted_at = datetime.now(UTC)
                await s.commit()


def _post(ctx: PluginContext, title: str, body: str) -> None:
    """Fire-and-forget moment post. contextvars (current conversation) are
    inherited by the task, so a mid-turn thought stays in its conversation."""

    async def _run() -> None:
        try:
            await ctx.send_muted_message(
                title,
                body,
                channel="moment",
                source="curiosity",
                tools=REFLECTION_TOOLS,
            )
        except Exception:  # noqa: BLE001
            log.warning("share_thought: moment post failed", exc_info=True)

    try:
        asyncio.get_running_loop().create_task(_run())  # noqa: RUF006
    except RuntimeError:
        log.warning("share_thought: no event loop — thought not posted")


async def drain_queue(ctx: PluginContext, reflections: ReflectionLog) -> dict[str, Any]:
    """Post queued thoughts once outside quiet hours. Routine thoughts respect
    the daily cap as they drain (excess stays queued for tomorrow)."""
    if in_quiet_hours():
        return {"drained": 0, "note": "still quiet hours"}
    queued = await reflections.queued()
    routine_budget = ROUTINE_DAILY_CAP - await reflections.routine_posted_today()
    drained = 0
    for item in queued:
        if item["kind"] == "routine":
            if routine_budget <= 0:
                continue
            routine_budget -= 1
        _post(ctx, item["title"], item["body"])
        await reflections.mark_posted(item["id"])
        drained += 1
    return {"drained": drained}


async def share(
    ctx: PluginContext,
    reflections: ReflectionLog,
    *,
    body: str,
    title: str = "Reflection",
    kind: str = "routine",
) -> dict[str, Any]:
    """The share_thought core: guardrails, then post or queue."""
    body = (body or "").strip()
    if not body:
        return {"error": "empty thought"}
    if not is_grounded(body):
        return {
            "error": (
                "ungrounded — a shared thought must cite a [[wiki-page]] or an "
                "http(s) source. Add the citation, or record it in the wiki "
                "instead of sharing."
            )
        }
    if kind not in ("routine", "kickoff", "dream"):
        kind = "routine"

    # drain first so an overnight queued thought posts before today's is judged
    await drain_queue(ctx, reflections)

    if in_quiet_hours():
        row = await reflections.add(kind=kind, title=title, body=body, status="queued")
        return {
            "queued": True,
            "id": str(row["id"]),
            "note": (
                f"quiet hours ({QUIET_START_HOUR}:00–{QUIET_END_HOUR:02d}:00) — "
                "the thought will post in the morning."
            ),
        }

    if kind == "routine" and await reflections.routine_posted_today() >= ROUTINE_DAILY_CAP:
        return {
            "blocked": True,
            "note": (
                "daily reflection cap reached (1/day). Record the insight in "
                "the wiki (wiki_write / wiki_patch) — tomorrow's reflection "
                "can draw on it."
            ),
        }

    row = await reflections.add(kind=kind, title=title, body=body, status="posted")
    _post(ctx, title, body)
    return {"posted": True, "id": str(row["id"])}


def register_tools(ctx: PluginContext, reflections: ReflectionLog) -> None:
    async def _share(body: str, title: str = "Reflection") -> dict[str, Any]:
        return await share(ctx, reflections, body=body, title=title, kind="routine")

    ctx.tool_registry.register(
        "plugin-curiosity",
        ToolDef(
            name="share_thought",
            description=(
                "Proactively share ONE grounded insight with the owner as a "
                "badged reflection in chat. The body must cite a [[wiki-page]] "
                "or an http(s) source. Budget: at most one routine reflection "
                "per day, and thoughts in quiet hours (21:00–08:00) queue "
                "until morning — share only what genuinely matters and record "
                "the rest in the wiki."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "body": {
                        "type": "string",
                        "description": "The insight, with its [[wiki-page]] or URL citation inline.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Short label for the collapsed line.",
                        "default": "Reflection",
                    },
                },
                "required": ["body"],
            },
            policy="auto_approve",
            risk_level="low",
        ),
        _share,
    )
