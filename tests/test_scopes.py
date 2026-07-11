"""Role scopes + agent-phase state machine (9A): store round-trip, competency
gate, charter write-through, plan-changes log, upgrade migration."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def sstore(sf, store):
    from plugin_curiosity.scopes import ScopeStore

    await store.set("own the weekly newsletter end to end")
    return ScopeStore(sf)


@pytest.fixture
def sctx(ctx, sstore):
    from plugin_curiosity.scopes import register_tools

    register_tools(ctx, sstore)
    return ctx


async def call(ctx, tool, **kw):
    return await ctx.tool_registry.registered[tool][1](**kw)


@pytest.mark.asyncio
async def test_scope_round_trip_per_kind(sstore):
    from plugin_curiosity.scopes import SCOPE_KINDS

    for kind in SCOPE_KINDS:
        sc = await sstore.add(kind, f"area for {kind}", why="the role needs it")
        assert sc["status"] == "missing" and sc["kind"] == kind
    scopes = await sstore.list()
    assert len(scopes) == len(SCOPE_KINDS)
    with pytest.raises(ValueError):
        await sstore.add("bogus_kind", "x")
    with pytest.raises(ValueError):
        await sstore.add("knowledge", "   ")


@pytest.mark.asyncio
async def test_scope_requires_active_mission(sf):
    from plugin_curiosity.scopes import ScopeStore

    empty = ScopeStore(sf)
    with pytest.raises(ValueError, match="no active mission"):
        await empty.add("knowledge", "the domain")
    assert await empty.state() is None
    assert await empty.list() == []


@pytest.mark.asyncio
async def test_regression_legal_and_evidence_preserved(sstore):
    sc = await sstore.add("tools_data_access", "funnel analytics read access")
    up = await sstore.update(sc["id"], status="competent", evidence="[[funnel-report]] validated")
    assert up["status"] == "competent"
    down = await sstore.update(sc["id"], status="in_progress")
    assert down["status"] == "in_progress"
    assert down["evidence"] == "[[funnel-report]] validated"
    with pytest.raises(ValueError):
        await sstore.update(sc["id"], status="bogus")
    with pytest.raises(LookupError):
        await sstore.update(str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_stage_set_and_state(sstore):
    state = await sstore.state()
    assert state["agent_phase"] == "setup" and state["setup_stage"] == "S0"
    await sstore.stage_set("S2")
    assert (await sstore.state())["setup_stage"] == "S2"
    await sstore.stage_set("S1")  # regression legal
    assert (await sstore.state())["setup_stage"] == "S1"
    with pytest.raises(ValueError):
        await sstore.stage_set("S9")


@pytest.mark.asyncio
async def test_plan_changes_dated_append_only(sstore):
    await sstore.plan_change_add("Dropped the AdWords scope — owner says everything runs through GA4")
    await sstore.plan_change_add("Added GA4 access scope")
    changes = await sstore.plan_changes()
    assert [c["entry"] for c in changes] == [
        "Dropped the AdWords scope — owner says everything runs through GA4",
        "Added GA4 access scope",
    ]
    assert all(c["date"] for c in changes)
    with pytest.raises(ValueError):
        await sstore.plan_change_add("  ")


@pytest.mark.asyncio
async def test_tool_policies(sctx):
    for name in ("scope_set", "scope_update", "scope_list", "stage_set", "plan_change_note"):
        tool_def, _ = sctx.tool_registry.registered[name]
        assert tool_def.policy == "auto_approve", name
    gate_def, _ = sctx.tool_registry.registered["phase_advance"]
    assert gate_def.policy == "prompt_always"


@pytest.mark.asyncio
async def test_charter_mirror_write_through(sctx):
    res = await call(sctx, "scope_set", kind="knowledge", name="newsletter audience", why="core")
    assert res["wiki_mirror"] == "ok"
    wiki = sctx.provider_registry.get("wiki")
    body = wiki.pages["role-charter"]["body"]
    # 0.9.2: owner-facing charter opens in plain words, never a stage code
    assert body.startswith("**Where I am: setup phase — understood**")
    assert "newsletter audience" in body and "⬜" in body

    upd = await call(sctx, "scope_update", id=res["scope"]["id"], status="competent",
                     evidence="[[audience-map]] written")
    assert upd["scope"]["status"] == "competent"
    body = wiki.pages["role-charter"]["body"]
    assert "✅" in body and "[[audience-map]] written" in body

    await call(sctx, "stage_set", stage="S3")
    assert wiki.pages["role-charter"]["body"].startswith(
        "**Where I am: setup phase — ratified**"
    )

    note = await call(sctx, "plan_change_note", entry="Reopened audience scope — list migrated")
    assert note["plan_change"]["date"]
    assert "Reopened audience scope — list migrated" in wiki.pages["role-charter"]["body"]


@pytest.mark.asyncio
async def test_phase_gate(sctx, sstore):
    # nothing chartered yet → graduation is meaningless
    res = await call(sctx, "phase_advance", to="work")
    assert "no scopes chartered" in res["error"]

    a = await sstore.add("knowledge", "the domain")
    b = await sstore.add("workflow_approval", "owner sign-off path")
    await sstore.update(a["id"], status="competent", evidence="wiki corpus")

    res = await call(sctx, "phase_advance", to="work")
    assert "competency gate" in res["error"] and "owner sign-off path" in res["error"]

    # waiver path: allowed, waiver recorded in the charter
    res = await call(sctx, "phase_advance", to="work", waive=[b["id"]], reason="owner said skip it")
    assert res["agent_phase"] == "work"
    wiki = sctx.provider_registry.get("wiki")
    body = wiki.pages["role-charter"]["body"]
    assert "waived" in body and "owner said skip it" in body
    assert body.startswith("**Where I am: work phase — understood**")

    # regression to setup always allowed, logged
    res = await call(sctx, "phase_advance", to="setup", reason="role shifted to events")
    assert res["agent_phase"] == "setup"
    assert "role shifted to events" in wiki.pages["role-charter"]["body"]

    # all competent → clean graduation
    await sstore.update(b["id"], status="competent", evidence="validated run")
    res = await call(sctx, "phase_advance", to="work")
    assert res["agent_phase"] == "work"
    state = (await call(sctx, "scope_list"))["state"]
    assert state["agent_phase"] == "work" and state["phase_entered_at"]

    res = await call(sctx, "phase_advance", to="limbo")
    assert "error" in res


@pytest.mark.asyncio
async def test_charter_seeded_on_upgrade_load(sctx, sstore):
    """A pre-9A mission (no charter page) gets [[role-charter]] on load."""
    from plugin_curiosity.scopes import ensure_charter_mirror

    wiki = sctx.provider_registry.get("wiki")
    assert "role-charter" not in wiki.pages
    assert await ensure_charter_mirror(sctx, sstore) == "ok"
    assert "role-charter" in wiki.pages
    assert await ensure_charter_mirror(sctx, sstore) == "already present"


@pytest.mark.asyncio
async def test_charter_mirror_degrades_without_wiki(sstore):
    import types

    from conftest import FakeToolRegistry

    from plugin_curiosity.scopes import register_tools

    class _NoWiki:
        def get(self, name):
            raise KeyError(name)

    c = types.SimpleNamespace(tool_registry=FakeToolRegistry(), provider_registry=_NoWiki())
    register_tools(c, sstore)
    res = await c.tool_registry.registered["scope_set"][1](kind="people", name="the designer")
    assert res["scope"]["name"] == "the designer"
    assert "not mirrored" in res["wiki_mirror"]


@pytest.mark.asyncio
async def test_additive_migration_backfills_old_db():
    """A 0.6.0-shaped curiosity_missions table (no 9A columns) gets the
    columns via apply_additive_migrations, with defaults on existing rows."""
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from plugin_curiosity.models import Mission, apply_additive_migrations

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.execute(text(
            "CREATE TABLE curiosity_missions ("
            "id CHAR(32) NOT NULL, statement TEXT NOT NULL, "
            "autonomy_rung INTEGER NOT NULL, risk_ceiling VARCHAR(16) NOT NULL, "
            "active BOOLEAN NOT NULL, created_at TIMESTAMP NOT NULL, "
            "updated_at TIMESTAMP NOT NULL, PRIMARY KEY (id))"
        ))
        await conn.execute(text(
            "INSERT INTO curiosity_missions VALUES "
            f"('{uuid.uuid4().hex}', 'legacy mission', 1, 'low', 1, "
            "'2026-01-01 09:00:00', '2026-01-01 09:00:00')"
        ))
        added = await conn.run_sync(apply_additive_migrations)
        assert added == [
            "curiosity_missions.agent_phase",
            "curiosity_missions.phase_entered_at",
            "curiosity_missions.setup_stage",
            "curiosity_missions.stage_entered_at",
            "curiosity_missions.role_version",
            "curiosity_missions.wiki_id",
        ]
        assert await conn.run_sync(apply_additive_migrations) == []  # idempotent

    sf = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sf() as s:
        m = (await s.execute(select(Mission))).scalars().one()
        assert m.agent_phase == "setup"
        assert m.setup_stage == "S0"
        assert m.phase_entered_at is None
    await engine.dispose()
