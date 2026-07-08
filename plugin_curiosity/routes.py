"""plugin-curiosity routes. /status proves the cross-plugin seam — the "wiki"
provider resolved from THIS plugin's ctx. /mission exposes the active mission
(walkthrough + UI surface)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .mission import MissionStore


def register_routes(app, ctx):
    from luna_sdk import get_current_user

    store = MissionStore(ctx.db_session_factory)
    router = APIRouter(prefix="/api/p/plugin-curiosity", tags=["curiosity"])

    @router.get("/mission")
    async def mission(user=Depends(get_current_user)):
        return {"mission": await store.get()}

    @router.get("/status")
    async def status(user=Depends(get_current_user)):
        try:
            wiki = ctx.provider_registry.get("wiki")
            return {
                "wiki_provider": "resolved",
                "wiki_pages": await wiki.page_count(),
                "wiki_open_questions": len(await wiki.open_questions()),
            }
        except Exception as e:  # noqa: BLE001 — status must not 500
            return {"wiki_provider": "unavailable", "error": str(e)}

    app.include_router(router)
