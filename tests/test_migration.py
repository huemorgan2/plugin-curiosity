"""0.10.0 — one-time pointer migration (goals.migrate_internal_goals).

Open internal rows move into goal-seek under ONE owner approval card; closed
rows stay as history; the second run is a no-op; a declined card leaves
everything untouched for a later retry.
"""

from __future__ import annotations

import types
from typing import Any

import pytest
import pytest_asyncio

from plugin_curiosity import goals as goals_mod
from plugin_curiosity.goals import GoalStore

from conftest import FakeProviderRegistry, FakeWikiProvider
from test_goals_delegation import GoalseekFake, RegistryWithGoalseek

pytestmark = pytest.mark.asyncio


class FakeApprovals:
    def __init__(self, decision: str = "approved") -> None:
        self.requests: list[dict] = []
        self._decision = decision

    async def request(self, **kw):
        self.requests.append(kw)
        return types.SimpleNamespace(decision=self._decision, reason=None)


@pytest_asyncio.fixture
async def env(sf):
    gs = GoalseekFake()
    ctx = types.SimpleNamespace(
        tool_registry=RegistryWithGoalseek(gs),
        provider_registry=FakeProviderRegistry(FakeWikiProvider()),
        db_session_factory=sf,
        approvals=FakeApprovals(),
    )
    store = GoalStore(sf)
    return types.SimpleNamespace(ctx=ctx, store=store, gs=gs)


async def _seed(store: GoalStore) -> dict[str, Any]:
    a = await store.add("Open goal A", target_date="2026-08-01",
                        expected_result="A done")
    b = await store.add("Stalled goal B")
    await store.update(b["id"], status="stalled")
    c = await store.add("Finished goal C")
    await store.update(c["id"], status="done")
    d = await store.add("Dropped goal D")
    await store.update(d["id"], status="dropped")
    return {"a": a, "b": b, "c": c, "d": d}


class TestMigration:
    async def test_only_open_rows_migrate_under_one_card(self, env):
        await _seed(env.store)
        out = await goals_mod.migrate_internal_goals(env.ctx, env.store)
        assert out["migrated"] == 2
        # ONE approval card for the whole batch
        assert len(env.ctx.approvals.requests) == 1
        card = env.ctx.approvals.requests[0]
        assert "2 mission goal(s)" in card["summary"]
        assert card["payload"]["curiosity"]["migration"] is True
        # the opens carry owner attribution (the card was the owner's yes)…
        assert all(o["opened_by"] == "owner" for o in env.gs.opens)
        # …and the provenance note rides a follow-up goal_update
        assert any(
            "Migrated from curiosity" in (n.get("note") or "") for n in env.gs.notes
        )
        # closed rows untouched
        rows = {g["statement"]: g for g in await env.store.list()}
        assert "goalseek_id" not in rows["Finished goal C"]
        assert "goalseek_id" not in rows["Dropped goal D"]

    async def test_snapshot_preserved_and_idempotent(self, env):
        seeded = await _seed(env.store)
        await goals_mod.migrate_internal_goals(env.ctx, env.store)
        # snapshot: local columns intact, pointer stamped
        rows = {g["statement"]: g for g in await env.store.list()}
        a = rows["Open goal A"]
        assert a["goalseek_id"].startswith("gs-")
        assert a["target_date"] == "2026-08-01"
        assert a["id"] == seeded["a"]["id"]
        # second run: nothing to do, no second card
        out2 = await goals_mod.migrate_internal_goals(env.ctx, env.store)
        assert out2["migrated"] == 0
        assert len(env.ctx.approvals.requests) == 1

    async def test_declined_card_migrates_nothing(self, env):
        await _seed(env.store)
        env.ctx.approvals = FakeApprovals(decision="rejected")
        out = await goals_mod.migrate_internal_goals(env.ctx, env.store)
        assert out["migrated"] == 0
        assert env.gs.opens == []
        # retryable: rows remain unmigrated
        assert len(await env.store.open_unmigrated()) == 2

    async def test_no_open_rows_no_card(self, env):
        out = await goals_mod.migrate_internal_goals(env.ctx, env.store)
        assert out == {"migrated": 0, "note": "nothing to migrate"}
        assert env.ctx.approvals.requests == []

    async def test_partial_failure_leaves_rest_retryable(self, env):
        await _seed(env.store)
        real_open = env.gs.goal_open
        calls = {"n": 0}

        async def flaky(**kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient")
            return await real_open(**kw)

        env.gs.goal_open = flaky
        out = await goals_mod.migrate_internal_goals(env.ctx, env.store)
        assert out["migrated"] == 1
        assert len(await env.store.open_unmigrated()) == 1
        # next load picks up the straggler without a fuss
        env.gs.goal_open = real_open
        out2 = await goals_mod.migrate_internal_goals(env.ctx, env.store)
        assert out2["migrated"] == 1
        assert await env.store.open_unmigrated() == []
