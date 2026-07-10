"""plugin-curiosity routes. /status proves the cross-plugin seam — the "wiki"
provider resolved from THIS plugin's ctx. /mission exposes the active mission
(walkthrough + UI surface). /reflect posts a source="curiosity" reflection via
the core muted-message channel (phase-3 contract; phase 4's share_thought adds
cadence guardrails on top). 9.002: /missions/overview + /missions/{id} feed
the Missions pane, and /ui/ serves the pane itself (static iframe app, same
pattern as plugin-marketplace)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from . import comms, overview
from .goals import GoalStore
from .loops import LoopStore
from .mission import MissionStore
from .scopes import ScopeStore
from .telemetry import HeartbeatStore


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
        from .loops import LoopStore
        from .scopes import ScopeStore

        # 9A/9B QA: this call site is the run that SURVIVES under uvicorn —
        # omitting the stores here silently skipped the charter/loop mirror
        # seeding even though on_load passed them.
        schedule_on_load_work(
            ctx,
            store,
            reflections,
            ScopeStore(ctx.db_session_factory),
            LoopStore(ctx.db_session_factory),
        )

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

    # ---- Missions pane (9.002) ----

    scope_store = ScopeStore(ctx.db_session_factory)
    goal_store = GoalStore(ctx.db_session_factory)
    loop_store = LoopStore(ctx.db_session_factory)
    heartbeat_store = HeartbeatStore(ctx.db_session_factory)

    @router.get("/missions/overview")
    async def missions_overview(user=Depends(get_current_user)):
        return await overview.build_overview(
            ctx,
            missions=store,
            scope_store=scope_store,
            goal_store=goal_store,
            loop_store=loop_store,
            heartbeat_store=heartbeat_store,
        )

    @router.get("/missions/{mission_id}")
    async def mission_history(mission_id: str, user=Depends(get_current_user)):
        detail = await overview.mission_detail(ctx.db_session_factory, mission_id)
        if detail is None:
            raise HTTPException(404, "no such mission")
        return detail

    # The pane itself — same serving pattern as plugin-marketplace: no-cache
    # (ETag revalidation) + the plugin version stamped onto asset refs so a
    # Cloudflare-edge-cached app.js can never outlive an upgrade.
    ui_dir = Path(__file__).parent / "ui"
    _NO_CACHE = {"Cache-Control": "no-cache"}

    def _versioned_index() -> Response:
        from . import CuriosityPlugin

        v = CuriosityPlugin.manifest.version
        html = (ui_dir / "index.html").read_text()
        html = html.replace('href="style.css"', f'href="style.css?v={v}"')
        html = html.replace('src="app.js"', f'src="app.js?v={v}"')
        return Response(content=html, media_type="text/html", headers=_NO_CACHE)

    @router.get("/ui/")
    async def serve_ui_root():
        if (ui_dir / "index.html").exists():
            return _versioned_index()
        return Response(
            content="<h1>plugin-curiosity UI not shipped</h1>", media_type="text/html"
        )

    @router.get("/ui/{path:path}")
    async def serve_ui(path: str):
        if not path or path == "/":
            path = "index.html"
        target = (ui_dir / path).resolve()
        if not str(target).startswith(str(ui_dir.resolve())):
            raise HTTPException(403, "Forbidden")
        if not target.exists():
            if (ui_dir / "index.html").exists():
                return _versioned_index()
            raise HTTPException(404, "Not found")
        return FileResponse(str(target), headers=_NO_CACHE)

    app.include_router(router)
