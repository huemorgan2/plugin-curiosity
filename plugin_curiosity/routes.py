"""plugin-curiosity routes. /status proves the cross-plugin seam — the "wiki"
provider resolved from THIS plugin's ctx. /mission exposes the active mission
(walkthrough + UI surface). /reflect posts a source="curiosity" reflection via
the core muted-message channel (phase-3 contract; phase 4's share_thought adds
cadence guardrails on top)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from . import comms
from .mission import MissionStore


class ShareBody(BaseModel):
    title: str = "Reflection"
    body: str
    kind: str = "routine"


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
    reflections = comms.ReflectionLog(ctx.db_session_factory)
    router = APIRouter(prefix="/api/p/plugin-curiosity", tags=["curiosity"])

    # On-load work must run in the SERVING loop. Under `luna serve`, on_load
    # runs in a throwaway bootstrap loop (its tasks die with it) — this
    # startup hook is what actually lands there. On a runtime install the
    # app has already started (this hook never fires) and on_load's own call
    # lands instead; the loop-identity guard makes the pair safe.
    # app.router.on_startup is the core's own idiom (cli.py mounts _reboot_mcp
    # the same way); the app object has no add_event_handler.
    def _on_startup() -> None:
        from . import schedule_on_load_work

        schedule_on_load_work(ctx, store, reflections)

    try:
        app.router.on_startup.append(_on_startup)
    except AttributeError:
        pass  # exotic host app — on_load's own call is the only path

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

    @router.post("/comms/drain")
    async def drain(user=Depends(get_current_user)):
        """Post queued thoughts if outside quiet hours (test/ops hook — the
        organic drain points are share_thought calls and plugin load)."""
        return await comms.drain_queue(ctx, reflections)

    @router.post("/comms/share")
    async def share(payload: ShareBody, user=Depends(get_current_user)):
        """Run a thought through the share_thought guardrails (test/ops hook —
        the agent-facing path is the share_thought tool, and the agent rightly
        refuses to call it with deliberately invalid input)."""
        return await comms.share(
            ctx, reflections, body=payload.body, title=payload.title, kind=payload.kind
        )

    @router.get("/comms/reflections")
    async def list_reflections(user=Depends(get_current_user)):
        return {
            "queued": await reflections.queued(),
            "routine_posted_today": await reflections.routine_posted_today(),
        }

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
