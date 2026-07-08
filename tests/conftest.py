"""Minimal `luna_sdk` stub (same pattern as plugin-wiki) plus a fake
PluginContext exposing the three cross-plugin seams mission.py touches:
tool_registry (scheduler tools), provider_registry (wiki), and
config_registry (identity write-through). Fakes record calls for assertions."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest
import pytest_asyncio


def _install_luna_sdk_stub() -> None:
    if "luna_sdk" in sys.modules:
        return

    from sqlalchemy import JSON, Uuid
    from sqlalchemy.orm import DeclarativeBase

    mod = types.ModuleType("luna_sdk")

    class _Kwargs:
        def __init__(self, **kw: Any) -> None:
            self.__dict__.update(kw)

    class PluginManifest(_Kwargs):
        pass

    class ToolDef(_Kwargs):
        pass

    class PluginContext:  # pragma: no cover - structural stand-in
        pass

    class LunaPlugin:  # pragma: no cover - structural stand-in
        manifest: Any

        async def on_load(self, ctx: Any) -> None: ...

    def declarative_base():
        class Base(DeclarativeBase):
            pass

        return Base

    mod.LunaPlugin = LunaPlugin
    mod.PluginContext = PluginContext
    mod.PluginManifest = PluginManifest
    mod.ToolDef = ToolDef
    mod.declarative_base = declarative_base
    mod.UUID = Uuid
    mod.JSONB = JSON
    sys.modules["luna_sdk"] = mod


_install_luna_sdk_stub()


@pytest_asyncio.fixture
async def sf():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from plugin_curiosity.models import ALL_TABLES

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        for table in ALL_TABLES:
            await conn.run_sync(table.create, checkfirst=True)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


@pytest_asyncio.fixture
async def store(sf):
    from plugin_curiosity.mission import MissionStore

    return MissionStore(sf)


class FakeToolRegistry:
    """Registers curiosity's tools; serves fake scheduler tools."""

    def __init__(self) -> None:
        self.registered: dict[str, tuple[Any, Any]] = {}
        self.trigger_created: list[dict] = []
        self.trigger_updated: list[dict] = []
        self.existing_triggers: list[dict] = []
        self.scheduler_installed = True
        self.has_update_tool = True

    def register(self, plugin: str, tool_def: Any, handler: Any) -> None:
        self.registered[tool_def.name] = (tool_def, handler)

    def get(self, name: str):
        if name in self.registered:
            reg = types.SimpleNamespace(handler=self.registered[name][1])
            return reg
        if not self.scheduler_installed:
            raise KeyError(name)
        if name == "trigger_list":
            async def _list(**kw):
                return {"triggers": list(self.existing_triggers)}
            return types.SimpleNamespace(handler=_list)
        if name == "trigger_create":
            async def _create(**kw):
                self.trigger_created.append(kw)
                self.existing_triggers.append(
                    {"id": f"trg-{len(self.trigger_created)}", "name": kw["name"],
                     "target": kw.get("target"), "enabled": True})
                return {"id": f"trg-{len(self.trigger_created)}", "expr_cron": "0 9 * * *",
                        "next_run_at": "2026-01-01T09:00:00Z"}
            return types.SimpleNamespace(handler=_create)
        if name == "trigger_update":
            if not self.has_update_tool:
                raise KeyError(name)
            async def _update(**kw):
                self.trigger_updated.append(kw)
                for t in self.existing_triggers:
                    if t["id"] == kw["id"] and kw.get("target") is not None:
                        t["target"] = kw["target"]
                return {"id": kw["id"], "expr_cron": "0 9 * * *",
                        "next_run_at": "2026-01-01T09:00:00Z"}
            return types.SimpleNamespace(handler=_update)
        raise KeyError(name)


class FakeWikiProvider:
    def __init__(self) -> None:
        self.pages: dict[str, dict] = {}
        self.upserts: list[str] = []

    async def get_page(self, slug: str):
        return self.pages.get(slug)

    async def upsert_page(self, slug: str, title: str, body: str, summary: str = "", note: str = ""):
        self.pages[slug] = {"slug": slug, "title": title, "body": body, "summary": summary}
        self.upserts.append(slug)
        return self.pages[slug]


class FakeProviderRegistry:
    def __init__(self, wiki: FakeWikiProvider | None) -> None:
        self._wiki = wiki

    def get(self, name: str):
        if name == "wiki" and self._wiki is not None:
            return self._wiki
        raise KeyError(name)


class FakeConfigRegistry:
    def __init__(self, has_identity: bool = True) -> None:
        self.writes: list[dict] = []
        self._has_identity = has_identity

    def get(self, section_id: str):
        if section_id != "identity" or not self._has_identity:
            return None
        reg = self

        class _Section:
            async def writer(self, changes: dict) -> dict:  # noqa: PLR6301
                reg.writes.append(changes)
                return {"updated": True, "values": changes}

        return _Section()


@pytest.fixture
def ctx(store, sf):
    """Fake PluginContext with recording seams, tools pre-registered."""
    from plugin_curiosity.comms import ReflectionLog
    from plugin_curiosity.comms import register_tools as register_comms_tools
    from plugin_curiosity.mission import register_tools

    c = types.SimpleNamespace(
        tool_registry=FakeToolRegistry(),
        provider_registry=FakeProviderRegistry(FakeWikiProvider()),
        config_registry=FakeConfigRegistry(),
        muted_posts=[],
    )

    async def send_muted_message(title, content, **kw):
        c.muted_posts.append({"title": title, "content": content, **kw})
        return {"ok": True}

    c.send_muted_message = send_muted_message
    c.reflections = ReflectionLog(sf)
    register_tools(c, store)
    register_comms_tools(c, c.reflections)
    return c
