"""Manifest sanity: the three version stamps agree (phase 8 — manifest 0.4.2
vs toml 0.4.3 vs pyproject drift kept the marketplace 'update available'
badge on forever, since the loaded plugin reports the manifest version)."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent
PKG = ROOT / "plugin_curiosity"


def _toml() -> dict:
    with open(PKG / "luna-plugin.toml", "rb") as f:
        return tomllib.load(f)


def _pyproject() -> dict:
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def _manifest():
    from plugin_curiosity import CuriosityPlugin

    return CuriosityPlugin.manifest


def test_versions_agree_everywhere():
    toml, manifest = _toml(), _manifest()
    assert toml["name"] == manifest.name == "plugin-curiosity"
    assert toml["version"] == manifest.version == _pyproject()["project"]["version"]


def test_no_provider_registered():
    """Curiosity CONSUMES the wiki provider; it must never declare one (a
    declared provider makes upgrades provider-teardown-sensitive)."""
    assert getattr(_manifest(), "provider", None) is None
    assert "provider" not in _toml()
