"""0.10.0 — the single goal-engine switch (engine.py).

One resolved value, obeyed everywhere; no other module may probe the
registry for goal-seek. The guard test enforces the "one switch" rule
structurally — scattered per-path detection is how half-switched bugs
happen.
"""

from __future__ import annotations

import pathlib
import types

import pytest

from plugin_curiosity import engine

pytestmark = pytest.mark.asyncio

SRC = pathlib.Path(engine.__file__).parent


class _Registry:
    def __init__(self, tools: dict) -> None:
        self._tools = tools

    def get(self, name: str):
        if name not in self._tools:
            raise KeyError(name)
        return types.SimpleNamespace(handler=self._tools[name])


def _ctx(tools: dict) -> types.SimpleNamespace:
    return types.SimpleNamespace(tool_registry=_Registry(tools))


class TestResolution:
    async def test_goalseek_when_goal_open_registered(self):
        async def goal_open(**kw):
            return {}

        assert engine.resolve_goal_engine(_ctx({"goal_open": goal_open})) == "goalseek"

    async def test_internal_when_absent(self):
        assert engine.resolve_goal_engine(_ctx({})) == "internal"

    async def test_env_override_wins(self, monkeypatch):
        async def goal_open(**kw):
            return {}

        monkeypatch.setenv("LUNA_CURIOSITY_GOAL_ENGINE", "internal")
        assert engine.resolve_goal_engine(_ctx({"goal_open": goal_open})) == "internal"
        monkeypatch.setenv("LUNA_CURIOSITY_GOAL_ENGINE", "goalseek")
        assert engine.resolve_goal_engine(_ctx({})) == "goalseek"

    async def test_garbage_override_ignored(self, monkeypatch):
        monkeypatch.setenv("LUNA_CURIOSITY_GOAL_ENGINE", "quantum")
        assert engine.resolve_goal_engine(_ctx({})) == "internal"

    async def test_last_resolved_tracks(self):
        engine.resolve_goal_engine(_ctx({}))
        assert engine.last_resolved() == "internal"


class TestGuardNoScatteredDetection:
    async def test_no_goal_probe_outside_engine(self):
        """The one-switch rule: `tool_registry.get("goal_...")` (detection or
        delegation) appears in engine.py ONLY."""
        offenders: list[str] = []
        for path in SRC.glob("*.py"):
            if path.name == "engine.py":
                continue
            text = path.read_text()
            if 'tool_registry.get("goal_' in text or "tool_registry.get('goal_" in text:
                offenders.append(path.name)
        assert offenders == []

    async def test_single_switch_definition(self):
        """Exactly one resolve_goal_engine exists (engine.py) — no module
        keeps a private copy of the switch."""
        definers = [
            p.name
            for p in SRC.glob("*.py")
            if "def resolve_goal_engine" in p.read_text()
        ]
        assert definers == ["engine.py"]


class TestOpenDelegation:
    async def test_open_passes_iso_deadline(self):
        seen: dict = {}

        async def goal_open(**kw):
            seen.update(kw)
            return {"id": "g1", "stage": "active"}

        out = await engine.engine_open(
            _ctx({"goal_open": goal_open}),
            statement="Ship the report",
            definition_of_done="Report delivered",
            deadline="2026-08-01",
        )
        assert out["id"] == "g1"
        assert seen["deadline"] == "2026-08-01"
        assert seen["opened_by"] == "agent"

    async def test_free_form_deadline_moves_to_note(self):
        seen: dict = {}
        notes: list = []

        async def goal_open(**kw):
            seen.update(kw)
            return {"id": "g2", "stage": "active"}

        async def goal_update(**kw):
            notes.append(kw)
            return {}

        await engine.engine_open(
            _ctx({"goal_open": goal_open, "goal_update": goal_update}),
            statement="s",
            definition_of_done="d",
            deadline="end of July",
            note="why-line",
        )
        assert seen["deadline"] is None
        assert notes and "end of July" in notes[0]["note"]

    async def test_rejected_open_skips_note(self):
        notes: list = []

        async def goal_open(**kw):
            return {"status": "rejected", "reason": "owner said no"}

        async def goal_update(**kw):  # pragma: no cover - must not fire
            notes.append(kw)
            return {}

        out = await engine.engine_open(
            _ctx({"goal_open": goal_open, "goal_update": goal_update}),
            statement="s", definition_of_done="d", note="n",
        )
        assert out["status"] == "rejected"
        assert notes == []


class TestCuriosityDictMapping:
    async def test_open_stage_is_active(self):
        g = {"id": "x", "statement": "s", "stage": "waiting", "outcome": None,
             "definition_of_done": "d", "created_at": "2026-07-01"}
        m = engine.to_curiosity_dict(g)
        assert m["status"] == "active"
        assert m["engine"] == "goalseek"
        assert m["expected_result"] == "d"

    async def test_terminal_outcomes_map_honestly(self):
        for outcome, status in (
            ("achieved", "done"),
            ("abandoned", "dropped"),
            ("expired", "dropped"),
            ("failed", "stalled"),
            ("escalated", "stalled"),
        ):
            g = {"id": "x", "statement": "s", "stage": "closed", "outcome": outcome}
            assert engine.to_curiosity_dict(g)["status"] == status, outcome

    async def test_deadline_becomes_target_date(self):
        g = {"id": "x", "statement": "s", "stage": "active",
             "deadline": "2026-08-01T00:00:00+00:00"}
        assert engine.to_curiosity_dict(g)["target_date"] == "2026-08-01"
