"""0.11.0 — the v2 seam, curiosity side.

Goal-seek 2.x speaks a richer dialect: lean lists + a per-goal table summary
(goal_get), 'proposed' as a normal open outcome, and legacy_v1 answers for
pre-upgrade ids. These tests pin the mapping (progress line), the proposed
tolerance, the mission-id provenance passthrough, list enrichment, and the
pointer-repair pass that heals v1 pointers after the engine's own upgrade.
"""

from __future__ import annotations

import types
from typing import Any

import pytest
import pytest_asyncio

from plugin_curiosity import engine
from plugin_curiosity import goals as goals_mod
from plugin_curiosity.goals import GoalStore

from conftest import FakeProviderRegistry, FakeWikiProvider

pytestmark = pytest.mark.asyncio


class GoalseekV2Fake:
    """goal-seek 2.x tool surface: lean goal_list, rich goal_get (table +
    needs_you), goal_open that may return 'proposed', legacy_v1 answers for
    ids living in the retired v1 engine."""

    def __init__(self) -> None:
        self.goals: dict[str, dict[str, Any]] = {}   # v2 rows (lean)
        self.rich: dict[str, dict[str, Any]] = {}    # goal_get extras per id
        self.legacy: dict[str, dict[str, Any]] = {}  # v1 rows, goal_get-only
        self.opens: list[dict] = []
        self.notes: list[dict] = []
        self.open_stage = "active"
        self._n = 0

    def add_goal(self, stage="active", **extra) -> str:
        self._n += 1
        gid = f"gs2-{self._n:04d}"
        self.goals[gid] = {
            "id": gid, "statement": f"goal {self._n}", "stage": stage,
            "outcome": extra.pop("outcome", None),
            "definition_of_done": "done is done", "deadline": None,
            "created_at": "2026-07-18T00:00:00+00:00",
            "updated_at": "2026-07-18T00:00:00+00:00",
        }
        if extra:
            self.rich[gid] = extra
        return gid

    async def goal_open(self, **kw):
        self.opens.append(kw)
        gid = self.add_goal(stage=self.open_stage)
        row = dict(self.goals[gid])
        row["statement"] = kw.get("statement", row["statement"])
        self.goals[gid]["statement"] = row["statement"]
        return row

    async def goal_update(self, **kw):
        self.notes.append(kw)
        return dict(self.goals.get(kw.get("goal_id", ""), {}))

    async def goal_list(self, **kw):
        return {"goals": [dict(g) for g in self.goals.values()],
                "count": len(self.goals)}

    async def goal_get(self, goal_id: str, **kw):
        if goal_id in self.goals:
            return {**self.goals[goal_id], **self.rich.get(goal_id, {})}
        if goal_id in self.legacy:
            return {**self.legacy[goal_id], "legacy_v1": True}
        raise LookupError(f"goal {goal_id} not found")


class Registry:
    def __init__(self, gs: GoalseekV2Fake | None) -> None:
        self.registered: dict[str, Any] = {}
        self._gs = gs

    def register(self, plugin, tool_def, handler, *, skill_gated=False,
                 yields_to=None):
        if self._gs is not None and yields_to == "plugin-goalseek":
            return
        self.registered[tool_def.name] = handler

    def get(self, name: str):
        if self._gs is not None:
            fn = getattr(self._gs, name, None)
            if fn is not None and name.startswith("goal_"):
                return types.SimpleNamespace(handler=fn)
        if name in self.registered:
            return types.SimpleNamespace(handler=self.registered[name])
        raise KeyError(name)


@pytest_asyncio.fixture
async def env(sf):
    gs = GoalseekV2Fake()
    ctx = types.SimpleNamespace(
        tool_registry=Registry(gs),
        provider_registry=FakeProviderRegistry(FakeWikiProvider()),
        db_session_factory=sf,
        events=None,
    )
    store = GoalStore(sf)
    return types.SimpleNamespace(ctx=ctx, store=store, gs=gs)


# ── mapping: the progress line ───────────────────────────────────────────────


class TestV2Mapping:
    async def test_table_becomes_progress_line(self):
        d = engine.to_curiosity_dict({
            "id": "g", "statement": "s", "stage": "active",
            "table": {"total": 50, "terminal": 18, "waiting": 3},
            "needs_you": 2,
        })
        assert d["progress_note"] == "18/50 done · 3 waiting · needs you: 2"
        assert d["status"] == "active"

    async def test_quiet_table_keeps_line_short(self):
        d = engine.to_curiosity_dict({
            "id": "g", "statement": "s", "stage": "active",
            "table": {"total": 5, "terminal": 0, "waiting": 0}, "needs_you": 0,
        })
        assert d["progress_note"] == "0/5 done"

    async def test_closed_goal_uses_reason_summary(self):
        d = engine.to_curiosity_dict({
            "id": "g", "statement": "s", "stage": "closed",
            "outcome": "achieved",
            "outcome_reason": {"summary": "all 5 demos booked"},
        })
        assert d["status"] == "done"
        assert d["progress_note"] == "all 5 demos booked"

    async def test_proposed_stage_is_active_status(self):
        d = engine.to_curiosity_dict(
            {"id": "g", "statement": "s", "stage": "proposed"})
        assert d["status"] == "active"
        assert d["stage"] == "proposed"


# ── goal_set: proposed tolerance + mission-id provenance ─────────────────────


class TestSetViaGoalseekV2:
    async def test_proposed_open_keeps_pointer_and_says_carry_on(self, env):
        env.gs.open_stage = "proposed"
        out = await goals_mod._set_via_goalseek(  # noqa: SLF001
            env.ctx, env.store, statement="Book 5 demos",
            expected_result="5 on the calendar",
        )
        assert out["goal"]["stage"] == "proposed"
        assert "Do NOT wait" in out["note"]
        pointers = await env.store.pointer_map()
        assert out["goal"]["id"] in pointers

    async def test_mission_id_rides_into_the_open(self, env):
        class MissionStore:
            async def get(self):
                return {"id": "m-42", "statement": "grow"}

        goals_mod.register_tools(env.ctx, env.store,
                                 mission_store=MissionStore())
        out = await env.ctx.tool_registry.registered["goal_set"](
            statement="Book 5 demos")
        assert out["engine"] == "goalseek"
        assert env.gs.opens[0]["mission_id"] == "m-42"
        assert env.gs.opens[0]["opened_via"] == "curiosity"

    async def test_mission_store_failure_never_blocks_the_open(self, env):
        class BrokenMissionStore:
            async def get(self):
                raise RuntimeError("db down")

        goals_mod.register_tools(env.ctx, env.store,
                                 mission_store=BrokenMissionStore())
        out = await env.ctx.tool_registry.registered["goal_set"](
            statement="Book 5 demos")
        assert out["engine"] == "goalseek"
        assert "mission_id" not in env.gs.opens[0]


# ── list enrichment: counts on the board ─────────────────────────────────────


class TestListEnrichment:
    async def test_open_goals_get_table_counts(self, env):
        gid = env.gs.add_goal(table={"total": 10, "terminal": 4, "waiting": 1},
                              needs_you=1)
        await env.store.add_pointer(gid, statement="goal 1")
        out = await goals_mod.list_mission_goals(env.ctx, env.store)
        assert out[0]["progress_note"] == "4/10 done · 1 waiting · needs you: 1"

    async def test_get_failure_degrades_to_lean_dict(self, env):
        gid = env.gs.add_goal()
        await env.store.add_pointer(gid, statement="goal 1")

        async def broken_get(goal_id, **kw):
            raise RuntimeError("engine hiccup")

        env.gs.goal_get = broken_get
        out = await goals_mod.list_mission_goals(env.ctx, env.store)
        assert len(out) == 1  # the lean dict still renders
        assert out[0]["progress_note"] == ""


# ── the pointer-repair pass (engine v1 → v2) ─────────────────────────────────


class TestRepointStalePointers:
    async def test_open_v1_goal_reopens_and_repoints(self, env):
        env.gs.legacy["v1-0001"] = {
            "id": "v1-0001", "statement": "finish the launch page",
            "definition_of_done": "page is live", "stage": "active",
            "deadline": None,
        }
        await env.store.add_pointer("v1-0001", statement="finish the launch page")
        out = await goals_mod.repoint_stale_pointers(env.ctx, env.store)
        assert out["repointed"] == 1 and out["retired"] == 0
        # re-open is owner-approved (the original migration card was)
        assert env.gs.opens[0]["opened_by"] == "owner"
        assert env.gs.opens[0]["statement"] == "finish the launch page"
        pointers = await env.store.pointer_map()
        assert list(pointers) == ["gs2-0001"]
        # second run: pointer now names a live v2 goal — nothing to heal
        again = await goals_mod.repoint_stale_pointers(env.ctx, env.store)
        assert again["repointed"] == 0 and again["retired"] == 0

    async def test_closed_v1_goal_retires_with_honest_status(self, env):
        env.gs.legacy["v1-0002"] = {
            "id": "v1-0002", "statement": "old push", "stage": "closed",
            "outcome": "achieved",
            "outcome_reason": {"summary": "shipped in June"},
        }
        await env.store.add_pointer("v1-0002", statement="old push")
        out = await goals_mod.repoint_stale_pointers(env.ctx, env.store)
        assert out["retired"] == 1 and out["repointed"] == 0
        assert await env.store.pointer_map() == {}  # pointer cleared
        rows = await env.store.list()
        assert rows[0]["status"] == "done"
        assert rows[0]["progress_note"] == "shipped in June"

    async def test_unknown_id_left_as_snapshot(self, env):
        await env.store.add_pointer("gone-forever", statement="mystery goal")
        out = await goals_mod.repoint_stale_pointers(env.ctx, env.store)
        assert out == {"repointed": 0, "retired": 0, "of": 1}
        assert "gone-forever" in await env.store.pointer_map()

    async def test_all_live_is_a_noop(self, env):
        gid = env.gs.add_goal()
        await env.store.add_pointer(gid, statement="goal 1")
        out = await goals_mod.repoint_stale_pointers(env.ctx, env.store)
        assert out["note"] == "all pointers live"
        assert env.gs.opens == []

    async def test_internal_engine_is_a_noop(self, sf):
        ctx = types.SimpleNamespace(
            tool_registry=Registry(None),
            provider_registry=FakeProviderRegistry(FakeWikiProvider()),
            db_session_factory=sf, events=None,
        )
        store = GoalStore(sf)
        out = await goals_mod.repoint_stale_pointers(ctx, store)
        assert out["note"] == "engine is internal"
