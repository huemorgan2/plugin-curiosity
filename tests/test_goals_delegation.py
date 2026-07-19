"""0.10.0 — goal paths route per engine (goals.py delegation layer).

With fake goal-seek tools in the registry: goal_set delegates the open and
keeps a pointer row; goal_update/goal_list register as deferential fallbacks;
list_mission_goals scopes the shared board to the mission via pointers and
maps goal-seek dicts to curiosity's shape. Without goal-seek: byte-identical
0.9.x behavior (the standalone regression rides the existing test_goals.py,
which runs with no goal-seek in the fake registry).
"""

from __future__ import annotations

import types
from typing import Any

import pytest
import pytest_asyncio

from plugin_curiosity import goals as goals_mod
from plugin_curiosity.goals import GoalStore

from conftest import FakeProviderRegistry, FakeWikiProvider

pytestmark = pytest.mark.asyncio


class GoalseekFake:
    """Just enough of goal-seek's tool surface: goal_open / goal_update /
    goal_list, dict shapes matching plugin-goalseek 0.6.0."""

    def __init__(self) -> None:
        self.goals: dict[str, dict[str, Any]] = {}
        self.opens: list[dict] = []
        self.notes: list[dict] = []
        self._n = 0

    async def goal_open(self, **kw):
        self._n += 1
        gid = f"gs-{self._n:04d}"
        row = {
            "id": gid,
            "statement": kw["statement"],
            "definition_of_done": kw["definition_of_done"],
            "stage": "active",
            "outcome": None,
            "deadline": kw.get("deadline"),
            "created_at": "2026-07-18T00:00:00+00:00",
            "updated_at": "2026-07-18T00:00:00+00:00",
        }
        self.goals[gid] = row
        self.opens.append(kw)
        return dict(row)

    async def goal_update(self, **kw):
        self.notes.append(kw)
        return dict(self.goals.get(kw.get("goal_id", ""), {}))

    async def goal_list(self, **kw):
        return {"goals": [dict(g) for g in self.goals.values()],
                "count": len(self.goals)}


class RegistryWithGoalseek:
    """Fake core registry that KNOWS yields_to (new-core behavior) and serves
    the goal-seek fakes."""

    def __init__(self, gs: GoalseekFake | None) -> None:
        self.registered: dict[str, tuple[Any, Any, str | None]] = {}
        self._gs = gs

    def register(self, plugin, tool_def, handler, *, skill_gated=False, yields_to=None):
        if self._gs is not None and yields_to == "plugin-goalseek" and (
            tool_def.name in ("goal_update", "goal_list")
        ):
            # canonical already present → yielding registration is skipped
            return
        self.registered[tool_def.name] = (tool_def, handler, yields_to)

    def get(self, name: str):
        if self._gs is not None:
            fn = getattr(self._gs, name, None)
            if fn is not None and name.startswith("goal_"):
                return types.SimpleNamespace(handler=fn)
        if name in self.registered:
            return types.SimpleNamespace(handler=self.registered[name][1])
        raise KeyError(name)


@pytest_asyncio.fixture
async def env(sf):
    gs = GoalseekFake()
    ctx = types.SimpleNamespace(
        tool_registry=RegistryWithGoalseek(gs),
        provider_registry=FakeProviderRegistry(FakeWikiProvider()),
        db_session_factory=sf,
        events=None,
    )
    store = GoalStore(sf)
    goals_mod.register_tools(ctx, store)
    return types.SimpleNamespace(ctx=ctx, store=store, gs=gs)


class TestGoalSetDelegates:
    async def test_open_lands_in_goalseek_with_pointer(self, env):
        _, handler, _ = env.ctx.tool_registry.registered["goal_set"]
        out = await handler(
            statement="Get 100 subscribers",
            why="grows the list",
            target_date="2026-08-01",
            expected_result="dashboard shows >= 100",
        )
        assert out["engine"] == "goalseek"
        assert out["goal"]["id"] == "gs-0001"
        # the open is goal-seek-governed: agent-opened
        assert env.gs.opens[0]["opened_by"] == "agent"
        assert env.gs.opens[0]["definition_of_done"] == "dashboard shows >= 100"
        assert env.gs.opens[0]["deadline"] == "2026-08-01"
        # mission membership: the pointer row
        pointers = await env.store.pointer_map()
        assert "gs-0001" in pointers
        assert pointers["gs-0001"]["statement"] == "Get 100 subscribers"

    async def test_rejected_open_passes_through_no_pointer(self, env):
        async def rejecting(**kw):
            return {"status": "rejected", "reason": "owner rejected"}

        env.gs.goal_open = rejecting
        _, handler, _ = env.ctx.tool_registry.registered["goal_set"]
        out = await handler(statement="Something")
        assert out["status"] == "rejected"
        assert await env.store.pointer_map() == {}

    async def test_engine_error_reported_not_swallowed(self, env):
        async def broken(**kw):
            raise RuntimeError("cap reached and parking failed")

        env.gs.goal_open = broken
        _, handler, _ = env.ctx.tool_registry.registered["goal_set"]
        out = await handler(statement="Something")
        assert "goal engine rejected the open" in out["error"]

    async def test_mirror_written_from_live_engine(self, env):
        _, handler, _ = env.ctx.tool_registry.registered["goal_set"]
        await handler(statement="Get 100 subscribers", target_date="2026-08-01")
        wiki = env.ctx.provider_registry.get("wiki")
        body = wiki.pages["mission-goals"]["body"]
        assert "Get 100 subscribers" in body
        assert "[[goal-gs-0001" in body  # phase 06 page link on the mirror


class TestDeferentialRegistration:
    async def test_update_and_list_yield_to_goalseek(self, env):
        # the fake new-core registry skipped both yielding registrations
        assert "goal_update" not in env.ctx.tool_registry.registered
        assert "goal_list" not in env.ctx.tool_registry.registered
        # goal_set stays curiosity's
        assert "goal_set" in env.ctx.tool_registry.registered

    async def test_standalone_registers_all_three(self, sf):
        ctx = types.SimpleNamespace(
            tool_registry=RegistryWithGoalseek(None),
            provider_registry=FakeProviderRegistry(FakeWikiProvider()),
            db_session_factory=sf,
        )
        goals_mod.register_tools(ctx, GoalStore(sf))
        assert set(ctx.tool_registry.registered) >= {"goal_set", "goal_update", "goal_list"}

    async def test_old_core_collision_degrades_to_skip(self, sf):
        """A core without yields_to that already holds goal-seek's tools:
        the ValueError collision is treated as yielding, not a crash."""

        class OldCoreRegistry:
            def __init__(self) -> None:
                self.registered: dict[str, Any] = {}
                self.taken = {"goal_update", "goal_list"}

            def register(self, plugin, tool_def, handler, *, skill_gated=False):
                if tool_def.name in self.taken:
                    raise ValueError(f"Tool name collision: '{tool_def.name}'")
                self.registered[tool_def.name] = handler

            def get(self, name):
                raise KeyError(name)

        ctx = types.SimpleNamespace(
            tool_registry=OldCoreRegistry(),
            provider_registry=FakeProviderRegistry(FakeWikiProvider()),
            db_session_factory=sf,
        )
        goals_mod.register_tools(ctx, GoalStore(sf))  # must not raise
        assert "goal_set" in ctx.tool_registry.registered


class TestListMissionGoals:
    async def test_scoped_to_pointers_and_mapped(self, env):
        _, handler, _ = env.ctx.tool_registry.registered["goal_set"]
        await handler(statement="Mission goal", why="serves the mission")
        # a foreign goal on the shared board — NOT the mission's
        await env.gs.goal_open(
            statement="Owner's private goal", definition_of_done="d",
            opened_by="owner",
        )
        listed = await goals_mod.list_mission_goals(env.ctx, env.store)
        assert [g["statement"] for g in listed] == ["Mission goal"]
        g = listed[0]
        assert g["engine"] == "goalseek"
        assert g["status"] == "active"
        assert g["why"] == "serves the mission"  # pointer-only field survives

    async def test_closed_internal_history_included(self, env):
        await env.store.add("Old internal goal")
        rows = await env.store.list()
        await env.store.update(rows[0]["id"], status="done")
        listed = await goals_mod.list_mission_goals(env.ctx, env.store)
        assert [g["statement"] for g in listed] == ["Old internal goal"]
        assert listed[0]["status"] == "done"

    async def test_engine_read_failure_degrades_to_snapshots(self, env):
        _, handler, _ = env.ctx.tool_registry.registered["goal_set"]
        await handler(statement="Mission goal")

        async def broken(**kw):
            raise RuntimeError("engine down")

        env.gs.goal_list = broken
        listed = await goals_mod.list_mission_goals(env.ctx, env.store)
        assert [g["statement"] for g in listed] == ["Mission goal"]

    async def test_internal_engine_unchanged(self, sf):
        ctx = types.SimpleNamespace(
            tool_registry=RegistryWithGoalseek(None),
            provider_registry=FakeProviderRegistry(FakeWikiProvider()),
            db_session_factory=sf,
        )
        store = GoalStore(sf)
        await store.add("plain goal", target_date="2026-08-01")
        listed = await goals_mod.list_mission_goals(ctx, store)
        assert listed == await store.list()
