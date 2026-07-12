"""0.9.6 — hot-reload convergence: a new instance's activation must survive
stale same-plugin registrations.

A hot upgrade/install whose teardown missed (or raced a concurrent update)
leaves the previous instance's tools registered under "plugin-curiosity".
The registry's collision guard would then kill the NEW version's on_load —
and the rollback's on_load too, bricking every further update until a
restart (seen on production: "Tool name collision: 'mission_set' already
registered by plugin 'plugin-curiosity'"). _activate therefore sweeps its
own plugin name before registering. Cross-plugin collisions must still
raise — that guard is load-bearing.

The registry here mirrors the core ToolRegistry's contract (collision
ValueError + unregister_plugin) without importing the core — these tests run
against the conftest luna_sdk stub, same as the rest of the suite.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from plugin_curiosity import CuriosityPlugin


class FakeToolRegistry:
    """The core ToolRegistry's contract, faithfully: name-keyed, collision
    guard raises ValueError, unregister_plugin sweeps by plugin name."""

    def __init__(self) -> None:
        self._tools: dict[str, SimpleNamespace] = {}

    def register(self, plugin, definition, handler, pre_gate_check=None, **kw):
        if definition.name in self._tools:
            existing = self._tools[definition.name]
            raise ValueError(
                f"Tool name collision: '{definition.name}' already registered by "
                f"plugin '{existing.plugin}', tried to register again from plugin '{plugin}'"
            )
        self._tools[definition.name] = SimpleNamespace(
            plugin=plugin, definition=definition, handler=handler
        )

    def unregister_plugin(self, plugin: str) -> None:
        self._tools = {n: t for n, t in self._tools.items() if t.plugin != plugin}

    def get(self, name: str):
        return self._tools[name]

    def names(self) -> list[str]:
        return list(self._tools)


def _noop(**kwargs):  # pragma: no cover - handlers never invoked here
    return None


def _stale_def(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name, description="stale copy from a dead instance", parameters={})


def _stale(reg: FakeToolRegistry, plugin: str, name: str) -> None:
    reg.register(plugin, _stale_def(name), _noop)


def test_activate_sweeps_stale_same_plugin_tools():
    reg = FakeToolRegistry()
    _stale(reg, "plugin-curiosity", "mission_set")
    _stale(reg, "plugin-curiosity", "goal_set")
    _stale(reg, "plugin-wiki", "wiki_page_upsert")

    plugin = CuriosityPlugin()
    plugin._activate(SimpleNamespace(tool_registry=reg, hooks=None))

    # the fresh registrations replaced the stale ones instead of colliding
    assert reg.get("mission_set").definition.description != "stale copy from a dead instance"
    assert "goal_set" in reg.names()
    # another plugin's tools are untouched by the sweep
    assert reg.get("wiki_page_upsert").definition.description == "stale copy from a dead instance"


def test_cross_plugin_collision_still_raises():
    reg = FakeToolRegistry()
    _stale(reg, "plugin-other", "mission_set")

    plugin = CuriosityPlugin()
    with pytest.raises(ValueError, match="collision"):
        plugin._activate(SimpleNamespace(tool_registry=reg, hooks=None))


def test_activate_survives_registry_without_unregister():
    """Older cores whose ToolRegistry lacks unregister_plugin: the sweep is
    feature-detected and skipped; a clean registry still activates fine."""
    reg = FakeToolRegistry()
    reg.unregister_plugin = None  # simulate the method being absent

    plugin = CuriosityPlugin()
    plugin._activate(SimpleNamespace(tool_registry=reg, hooks=None))
    assert "mission_set" in reg.names()
