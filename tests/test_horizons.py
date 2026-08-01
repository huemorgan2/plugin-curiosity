"""0.15.0 (11.003/M3) — honest horizons.

Time in honest units: a goal's WHEN is typed (horizon_kind + horizon_ref) —
agent_minutes / awaiting_approval / on_unlock / date / rhythm. Old target_date
rows migrate to kind 'date'; kind 'date' demands a real ISO date; a blocked
kind renders blocked-on-its-unlock and is NEVER overdue; pace names the
unlock and its ~5-minute human cost; the prompt law bans guessed human-rhythm
durations from every generated surface.
"""

from __future__ import annotations

import types

import pytest
import pytest_asyncio

from plugin_curiosity import goals as goals_mod
from plugin_curiosity.goals import (
    BLOCKED_HORIZON_KINDS,
    HORIZON_KINDS,
    GoalStore,
    render_goals_page,
)

from conftest import FakeProviderRegistry, FakeWikiProvider

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def gstore(sf):
    return GoalStore(sf)


# --- unit 1: typing + migration ---------------------------------------------


class TestHorizonTyping:
    async def test_every_kind_round_trips(self, gstore):
        refs = {
            "agent_minutes": "90",
            "awaiting_approval": "the job description",
            "on_unlock": "CRM access",
            "date": "2026-08-15",
            "rhythm": "weekly",
        }
        for kind in HORIZON_KINDS:
            g = await gstore.add(f"goal {kind}", horizon_kind=kind,
                                 horizon_ref=refs[kind])
            assert g["horizon_kind"] == kind
            assert g["horizon_ref"] == refs[kind]

    async def test_unknown_kind_rejected(self, gstore):
        with pytest.raises(ValueError, match="horizon_kind must be one of"):
            await gstore.add("g", horizon_kind="soon")

    async def test_date_kind_requires_real_date(self, gstore):
        with pytest.raises(ValueError, match="real calendar date"):
            await gstore.add("g", horizon_kind="date", horizon_ref="end of July")
        with pytest.raises(ValueError, match="real calendar date"):
            await gstore.add("g", horizon_kind="date")  # no ref at all

    async def test_date_kind_mirrors_target_date(self, gstore):
        g = await gstore.add("g", horizon_kind="date", horizon_ref="2026-08-15")
        assert g["target_date"] == "2026-08-15"

    async def test_legacy_iso_target_date_derives_date_kind(self, gstore):
        g = await gstore.add("g", target_date="2026-08-01")
        assert g["horizon_kind"] == "date"
        assert g["horizon_ref"] == "2026-08-01"

    async def test_legacy_freeform_target_date_stays_untyped(self, gstore):
        # pre-0.15 free-form text keeps working exactly as before — no type,
        # no error; the agent reasons about it
        g = await gstore.add("g", target_date="end of July")
        assert g["horizon_kind"] == ""
        assert g["target_date"] == "end of July"

    async def test_update_retypes_horizon(self, gstore):
        g = await gstore.add("g", horizon_kind="on_unlock", horizon_ref="CRM")
        g2 = await gstore.update(g["id"], horizon_kind="agent_minutes",
                                 horizon_ref="45")
        assert (g2["horizon_kind"], g2["horizon_ref"]) == ("agent_minutes", "45")

    async def test_update_date_kind_validates(self, gstore):
        g = await gstore.add("g")
        with pytest.raises(ValueError, match="real calendar date"):
            await gstore.update(g["id"], horizon_kind="date", horizon_ref="soon")

    async def test_migration_declares_both_columns(self):
        from plugin_curiosity.models import _ADDITIVE_COLUMNS

        cols = dict(_ADDITIVE_COLUMNS["curiosity_goals"])
        assert "horizon_kind" in cols
        assert "horizon_ref" in cols

    async def test_backfill_maps_old_target_date_rows_to_date_kind(self, sf):
        # a pre-0.15 row: target_date set, horizon empty (what an upgraded DB
        # holds after ALTER adds the columns with DEFAULT '')
        from sqlalchemy import text

        from plugin_curiosity.models import apply_additive_migrations

        async with sf() as s:
            await s.execute(text(
                "INSERT INTO curiosity_goals (id, statement, why, target_date,"
                " status, progress_note, expected_result, readiness,"
                " readiness_note, horizon_kind, horizon_ref, goalseek_id,"
                " created_at, updated_at) VALUES ('11111111111111111111111111111111',"
                " 'old dated goal', '', '2026-08-01', 'active', '', '', '', '',"
                " '', '', '', '2026-07-01 00:00:00', '2026-07-01 00:00:00')"
            ))
            await s.commit()
        # run the migration against the same engine the factory holds
        async with sf() as s:
            conn = await s.connection()
            await conn.run_sync(lambda c: apply_additive_migrations(c))
            await s.commit()
        store = GoalStore(sf)
        rows = await store.list()
        old = next(g for g in rows if g["statement"] == "old dated goal")
        assert old["horizon_kind"] == "date"
        assert old["horizon_ref"] == "2026-08-01"

    async def test_backfill_is_idempotent_and_skips_typed_rows(self, sf):
        from sqlalchemy import text

        from plugin_curiosity.models import apply_additive_migrations

        store = GoalStore(sf)
        typed = await store.add("blocked goal", horizon_kind="on_unlock",
                                horizon_ref="CRM access")
        async with sf() as s:
            conn = await s.connection()
            await conn.run_sync(lambda c: apply_additive_migrations(c))
            await conn.run_sync(lambda c: apply_additive_migrations(c))
            await s.commit()
        rows = await store.list()
        g = next(r for r in rows if r["id"] == typed["id"])
        assert g["horizon_kind"] == "on_unlock"  # untouched


# --- unit 3: never overdue on unlock ----------------------------------------


class TestBlockedNeverOverdue:
    async def test_on_unlock_renders_blocked_on_loop(self, gstore):
        await gstore.add("Email every customer", horizon_kind="on_unlock",
                         horizon_ref="mailbox access")
        page = render_goals_page(await gstore.list())
        assert "starts when this unlocks: mailbox access" in page
        assert "overdue" not in page.lower()
        assert "target:" not in page
        assert "late" not in page.lower()

    async def test_awaiting_approval_names_the_human_cost(self, gstore):
        await gstore.add("Deep research pass", horizon_kind="awaiting_approval",
                         horizon_ref="the job description")
        page = render_goals_page(await gstore.list())
        assert "waiting on your approval: the job description" in page
        assert "5 min of your time" in page

    async def test_agent_minutes_renders_own_work_time(self, gstore):
        await gstore.add("Draft the welcome flow", horizon_kind="agent_minutes",
                         horizon_ref="45")
        page = render_goals_page(await gstore.list())
        assert "about 45 minutes of my work" in page

    async def test_date_and_rhythm_render_their_units(self, gstore):
        await gstore.add("Launch-day post", horizon_kind="date",
                         horizon_ref="2026-08-15")
        await gstore.add("Weekly digest", horizon_kind="rhythm",
                         horizon_ref="weekly")
        page = render_goals_page(await gstore.list())
        assert "target: 2026-08-15" in page
        assert "rhythm: weekly" in page

    async def test_blocked_kinds_constant(self):
        assert set(BLOCKED_HORIZON_KINDS) == {"awaiting_approval", "on_unlock"}


# --- unit 4: pace blame -----------------------------------------------------


class TestPaceBlame:
    async def test_pace_names_unlock_and_human_cost(self):
        from plugin_curiosity.telemetry import compute_pace

        pace = compute_pace(
            agent_phase="setup", setup_stage="S2", stage_age_days=2,
            overdue_loops=0,
            blocked_horizons=[{
                "statement": "Email every customer",
                "horizon_kind": "on_unlock",
                "horizon_ref": "mailbox access",
            }],
        )
        assert pace["band"] == "on-track"  # blocked never worsens the band
        joined = " ".join(pace["reasons"])
        assert "mailbox access" in joined
        assert "5 minutes of your time" in joined

    async def test_awaiting_approval_defaults_to_your_approval(self):
        from plugin_curiosity.telemetry import compute_pace

        pace = compute_pace(
            agent_phase="work", setup_stage="S5", stage_age_days=0,
            overdue_loops=0,
            blocked_horizons=[{
                "statement": "Deep pass",
                "horizon_kind": "awaiting_approval",
                "horizon_ref": "",
            }],
        )
        assert "your approval" in " ".join(pace["reasons"])

    async def test_no_blocked_horizons_is_byte_identical(self):
        from plugin_curiosity.telemetry import compute_pace

        a = compute_pace(agent_phase="setup", setup_stage="S1",
                         stage_age_days=2, overdue_loops=0)
        b = compute_pace(agent_phase="setup", setup_stage="S1",
                         stage_age_days=2, overdue_loops=0,
                         blocked_horizons=[])
        assert a == b


# --- tool surface -----------------------------------------------------------


class TestToolSurface:
    async def test_goal_set_schema_carries_horizon_params(self, sf):
        class Reg:
            def __init__(self):
                self.registered = {}

            def register(self, plugin, tool_def, handler, **kw):
                self.registered[tool_def.name] = (tool_def, handler)

        ctx = types.SimpleNamespace(
            tool_registry=Reg(),
            provider_registry=FakeProviderRegistry(FakeWikiProvider()),
            db_session_factory=sf,
        )
        goals_mod.register_tools(ctx, GoalStore(sf))
        for name in ("goal_set", "goal_update"):
            props = ctx.tool_registry.registered[name][0].parameters["properties"]
            assert props["horizon_kind"]["enum"] == list(HORIZON_KINDS)
            assert "horizon_ref" in props

    async def test_goal_set_handler_passes_horizon_through(self, sf):
        class Reg:
            def __init__(self):
                self.registered = {}

            def register(self, plugin, tool_def, handler, **kw):
                self.registered[tool_def.name] = (tool_def, handler)

        ctx = types.SimpleNamespace(
            tool_registry=Reg(),
            provider_registry=FakeProviderRegistry(FakeWikiProvider()),
            db_session_factory=sf,
            events=None,
        )
        store = GoalStore(sf)
        goals_mod.register_tools(ctx, store)
        _, handler = ctx.tool_registry.registered["goal_set"]
        out = await handler(statement="g", horizon_kind="agent_minutes",
                            horizon_ref="30")
        assert out["goal"]["horizon_kind"] == "agent_minutes"
        # steering error, not crash, on a guessed date
        bad = await handler(statement="g2", horizon_kind="date",
                            horizon_ref="in a few days")
        assert "real calendar date" in bad["error"]


# --- unit 5: prompt law -----------------------------------------------------

# the guessed-duration phrases the law bans from every generated surface;
# HONEST_HORIZONS itself quotes them as negative examples, so each surface is
# scanned with the law's own text removed first
_BANNED = ("3-5 days", "in about a week", "a few days", "a couple of weeks",
           "3–5 days", "few weeks")


def _without_law(text: str) -> str:
    from plugin_curiosity.prompts import HONEST_HORIZONS, OWNER_WORDS

    return text.replace(HONEST_HORIZONS, "").replace(OWNER_WORDS, "")


class TestPromptLaw:
    async def test_law_rides_both_phase_branches(self):
        from plugin_curiosity.mission import prompt_fragment
        from plugin_curiosity.prompts import HONEST_HORIZONS

        mission = {
            "id": "m1", "statement": "grow signups", "autonomy_rung": 2,
            "risk_ceiling": "low", "wiki_id": None, "setup_stage": "S2",
            "agent_phase": "setup", "confirmed_at": "2026-07-01",
        }
        assert HONEST_HORIZONS in prompt_fragment(mission, "setup")
        assert HONEST_HORIZONS in prompt_fragment(dict(mission,
                                                       agent_phase="work"),
                                                  "work")

    async def test_law_rides_kickoff_daily_weekly(self):
        from plugin_curiosity.prompts import HONEST_HORIZONS
        from plugin_curiosity.research import _KICKOFF_CONTENT, DAILY_RESEARCH_TARGET
        from plugin_curiosity.review import WEEKLY_REVIEW_TARGET

        assert HONEST_HORIZONS in _KICKOFF_CONTENT
        assert HONEST_HORIZONS in DAILY_RESEARCH_TARGET
        assert HONEST_HORIZONS in WEEKLY_REVIEW_TARGET

    async def test_banned_durations_absent_from_generated_templates(self):
        from plugin_curiosity.mission import prompt_fragment
        from plugin_curiosity.prompts import JOB_DESCRIPTION_SHAPE
        from plugin_curiosity.research import _KICKOFF_CONTENT, DAILY_RESEARCH_TARGET
        from plugin_curiosity.review import WEEKLY_REVIEW_TARGET

        mission = {
            "id": "m1", "statement": "grow signups", "autonomy_rung": 2,
            "risk_ceiling": "low", "wiki_id": None, "setup_stage": "S2",
            "agent_phase": "setup", "confirmed_at": "2026-07-01",
        }
        surfaces = [
            JOB_DESCRIPTION_SHAPE,
            _KICKOFF_CONTENT.format(statement="x", wiki_note="",
                                    confirm_note=""),
            DAILY_RESEARCH_TARGET,
            WEEKLY_REVIEW_TARGET,
            prompt_fragment(mission, "setup"),
            prompt_fragment(dict(mission, agent_phase="work"), "work"),
        ]
        for surface in surfaces:
            cleaned = _without_law(surface).lower()
            for phrase in _BANNED:
                assert phrase not in cleaned, phrase

    async def test_kickoff_milestone_mandate_emits_typed_horizons(self):
        # phase14: the milestones are WRITTEN (with typed horizons) in the
        # planning pass's plan page and BUILT in the execution pass — the
        # mandate must ride both surfaces
        from plugin_curiosity.research import _KICKOFF_CONTENT, _PLAN_EXEC_CONTENT

        assert "honest horizon" in _KICKOFF_CONTENT
        assert "horizon_kind" in _KICKOFF_CONTENT
        assert "guessed calendar date" in _KICKOFF_CONTENT
        assert "horizon" in _PLAN_EXEC_CONTENT

    async def test_owner_words_extended_with_horizon_vocabulary(self):
        from plugin_curiosity.prompts import OWNER_WORDS

        assert "about 20 minutes of my work" in OWNER_WORDS
        assert "3-5 days" in OWNER_WORDS  # named as the banned example


# --- delegation overlay (goalseek reads keep pointer horizons) ---------------


class TestOverlay:
    async def test_engine_dict_maps_deadline_to_date_kind(self):
        from plugin_curiosity.engine import to_curiosity_dict

        g = to_curiosity_dict({"id": "gs-1", "statement": "s",
                               "stage": "active",
                               "deadline": "2026-08-01T00:00:00+00:00"})
        assert g["horizon_kind"] == "date"
        assert g["horizon_ref"] == "2026-08-01"
        g2 = to_curiosity_dict({"id": "gs-2", "statement": "s",
                                "stage": "active", "deadline": None})
        assert g2["horizon_kind"] == ""
