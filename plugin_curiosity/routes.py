"""plugin-curiosity routes. /status proves the cross-plugin seam — the "wiki"
provider resolved from THIS plugin's ctx. /mission exposes the active mission
(walkthrough + UI surface). /reflect posts a source="curiosity" reflection via
the core muted-message channel (phase-3 contract; phase 4's share_thought adds
cadence guardrails on top)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .mission import MissionStore


class ReflectBody(BaseModel):
    title: str = "Reflection"
    body: str
    # A reflection is a "moment": the muted line records what curiosity handed
    # the model, and the badged reply is Luna voicing the thought. awareness
    # (respond=False) records the line only — no badge, no turn.
    respond: bool = True
    conversation_id: str | None = None


def register_routes(app, ctx):
    from luna_sdk import get_current_user

    store = MissionStore(ctx.db_session_factory)
    router = APIRouter(prefix="/api/p/plugin-curiosity", tags=["curiosity"])

    @router.get("/mission")
    async def mission(user=Depends(get_current_user)):
        return {"mission": await store.get()}

    @router.post("/reflect")
    async def reflect(payload: ReflectBody, user=Depends(get_current_user)):
        return await ctx.send_muted_message(
            payload.title,
            payload.body,
            channel="moment" if payload.respond else "awareness",
            conversation_id=payload.conversation_id,
            source="curiosity",
        )

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
