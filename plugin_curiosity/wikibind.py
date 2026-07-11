"""wikibind.py — mission-bound wiki binding (10.003 §3).

A mission adopted on wiki >= 0.7.0 gets its OWN named wiki: mission_set
creates it, stores the slug on Mission.wiki_id, and every curiosity surface
(mirrors, shelf, overview reads, seeded stubs) scopes its wiki calls to it.
Re-missioning leaves the old wiki untouched — its knowledge stays browsable
from the history shelf.

Feature-detected forever, never version-gated: an old wiki plugin (no
create_wiki / no `wiki` kwarg) simply means the global namespace, exactly the
pre-0.9.2 behavior. `wiki_kwargs` re-checks the PROVIDER on every call — a
mission bound under 0.7.0 whose wiki plugin was later downgraded must degrade
to global reads, not TypeError."""

from __future__ import annotations

import inspect
import logging
import re
import uuid
from typing import Any

from sqlalchemy import select, update

from luna_sdk import PluginContext

from .models import Mission

log = logging.getLogger("plugin-curiosity")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug_for(statement: str, mission_id: str) -> str:
    """Deterministic wiki slug: the statement's words, trimmed, plus a short
    mission-id suffix so two missions with the same wording never collide."""
    words = _SLUG_RE.sub("-", (statement or "").lower()).strip("-")
    base = words[:32].rstrip("-") or "mission"
    return f"{base}-{str(mission_id)[:6]}"


def supports_multi_wiki(wiki: Any) -> bool:
    """wiki >= 0.7.0: create_wiki exists AND page reads take a `wiki` kwarg."""
    if not callable(getattr(wiki, "create_wiki", None)):
        return False
    try:
        return "wiki" in inspect.signature(wiki.get_page).parameters
    except (TypeError, ValueError):
        return False


async def bind_wiki(ctx: PluginContext, statement: str, mission_id: str) -> str | None:
    """Create the mission's wiki and return its slug, or None when the
    installed wiki plugin has no multi-wiki support (global namespace then)."""
    try:
        wiki = ctx.provider_registry.get("wiki")
    except Exception:  # noqa: BLE001
        return None
    if not supports_multi_wiki(wiki):
        return None
    slug = slug_for(statement, mission_id)
    name = (statement or "Mission").strip()[:60]
    try:
        await wiki.create_wiki(slug, name, description=statement.strip()[:200])
        return slug
    except Exception:  # noqa: BLE001
        # already exists (idempotent re-bind) or a transient failure — trust
        # the listing, never a guess
        try:
            existing = {w.get("slug") for w in await wiki.list_wikis()}
            if slug in existing:
                return slug
        except Exception:  # noqa: BLE001
            pass
        log.warning("mission wiki bind failed for %s", slug, exc_info=True)
        return None


async def persist_wiki_id(sf, mission_id: str, slug: str) -> None:
    """Stamp the bound slug on the mission row (mission_set already committed
    the row; the bind happens after because the slug embeds the mission id)."""
    async with sf() as s:
        await s.execute(
            update(Mission)
            .where(Mission.id == uuid.UUID(str(mission_id)))
            .values(wiki_id=slug)
        )
        await s.commit()


async def wiki_kwargs(ctx: PluginContext, sf) -> dict[str, Any]:
    """{"wiki": slug} for every wiki call when the ACTIVE mission is bound and
    the CURRENT provider takes the kwarg; {} otherwise (global namespace).
    Callers splat it: `await wiki.get_page(slug, **wk)`."""
    try:
        async with sf() as s:
            slug = (
                await s.execute(select(Mission.wiki_id).where(Mission.active))
            ).scalars().first()
    except Exception:  # noqa: BLE001
        return {}
    if not slug:
        return {}
    try:
        wiki = ctx.provider_registry.get("wiki")
    except Exception:  # noqa: BLE001
        return {}
    try:
        if "wiki" in inspect.signature(wiki.get_page).parameters:
            return {"wiki": slug}
    except (TypeError, ValueError):
        pass
    return {}
