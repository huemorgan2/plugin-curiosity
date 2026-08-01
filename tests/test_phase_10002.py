"""10.002 — the Missions pane rebuilt to the journey grammar.

0.21.0: the Operational dashboard (ex-NOC, ui/noc/) was removed entirely —
too much machinery for owners. The pane is one view: the journey. These
tests keep the UX-grammar invariants contractual (zero S\\d jargon, no
tooltip layer, the eight sections in order) and now also pin the absence
of the ops tab and its assets.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugin_curiosity import CuriosityPlugin

UI = Path(__file__).parent.parent / "plugin_curiosity" / "ui"


# ---- manifest: one pane, one view (0.21.0) -----------------------------------


def test_manifest_advertises_single_pane_without_ops_tab():
    secs = CuriosityPlugin.manifest.sidebar_sections
    assert [s.id for s in secs] == ["missions"]
    assert getattr(secs[0], "path", "ui/") == "ui/"
    # 0.21.0: no tabs, no embedded ops document
    index = (UI / "index.html").read_text()
    assert "Operational dashboard" not in index
    assert 'id="ops-frame"' not in index
    assert "<nav" not in index
    app = (UI / "app.js").read_text()
    assert "noc/?v=" not in app
    assert "setTab" not in app


def test_noc_assets_are_gone():
    assert not (UI / "noc").exists(), "ui/noc/ was removed in 0.21.0"
    import tomllib

    with open(Path(__file__).parent.parent / "pyproject.toml", "rb") as f:
        py = tomllib.load(f)
    assert "ui/noc/*" not in py["tool"]["setuptools"]["package-data"]["plugin_curiosity"]


def test_three_version_stamps_agree():
    import tomllib

    root = Path(__file__).parent.parent
    v = CuriosityPlugin.manifest.version
    with open(root / "pyproject.toml", "rb") as f:
        assert tomllib.load(f)["project"]["version"] == v
    with open(root / "plugin_curiosity" / "luna-plugin.toml", "rb") as f:
        assert tomllib.load(f)["version"] == v


# ---- UX grammar invariants ---------------------------------------------------


def test_missions_pane_has_zero_stage_jargon():
    """The owner never sees S0…S5 — plain words only (plan §1.3)."""
    for name in ("index.html", "app.js"):
        text = (UI / name).read_text()
        hits = re.findall(r"\bS\d\b", text)
        assert not hits, f"ui/{name} leaks stage codes: {hits}"


def test_no_tooltip_layer_on_the_journey_pane():
    """0.16.0: the journey page has no tooltip layer at all — plain
    sentences carry the explanations."""
    assert "data-tip" not in (UI / "index.html").read_text()
    assert "data-tip" not in (UI / "app.js").read_text()


def test_missions_pane_sections_in_order():
    # 0.16.0 (11.004/M4): the journey grammar — 8 sections in mock order,
    # sections 4–8 hidden until their data exists (progressive disclosure)
    html = (UI / "index.html").read_text()
    order = [
        html.index("Your mission — in my words"),
        html.index('id="journey-panel"'),
        html.index('id="nownext-panel"'),
        html.index('id="waiting-panel"'),
        html.index('id="services-panel"'),
        html.index('id="when-panel"'),
        html.index('id="wins-panel"'),
        html.index('id="rules-panel"'),
    ]
    assert order == sorted(order), "the eight sections must render in mock order"
    for late in ("waiting-panel", "services-panel", "when-panel", "wins-panel", "rules-panel"):
        i = html.index(f'id="{late}"')
        assert "hidden" in html[html.rindex("<section", 0, i):i + 60], (
            f"{late} must start hidden — day one shows exactly three sections"
        )
    # machinery stays off this pane (0.21.0: and off every pane — the ops
    # dashboard that used to carry it is gone)
    for gone in ('id="noc-tiles"', 'id="hb-history"', 'id="activity"',
                 'id="wiki-panel"', 'id="history-panel"', 'id="gaps-panel"',
                 'id="jd-blocks"', 'id="abilities"'):
        assert gone not in html, f"{gone} is machinery — it does not belong on Missions"


def test_journey_pane_owns_the_owner_actions():
    # the pane renders the journey payload and its buttons; the JD living
    # draft and ability ladder left with the ops dashboard (0.21.0)
    js = (UI / "app.js").read_text()
    assert "Living draft" not in js and "goal-timeline" not in js
    # the M0a buttons post muted moment messages into the newest conversation
    assert "kind: 'muted'" in js and "channel: 'moment'" in js
    assert "/api/conversations" in js
    for say in ("Go ahead", "Change it", "Confirm", "Approve"):
        assert say in js, f"button {say!r} missing from the journey pane"


# ---- serving: /ui/ stamped ---------------------------------------------------


class _Ctx:
    """The minimum register_routes touches at registration time."""

    def __init__(self) -> None:
        self.db_session_factory = lambda: None


@pytest.fixture()
def client() -> TestClient:
    from plugin_curiosity.routes import register_routes

    app = FastAPI()
    register_routes(app, _Ctx())
    # don't run startup hooks — they schedule on-load work against the fake ctx
    app.router.on_startup.clear()
    return TestClient(app)


def test_ui_root_serves_stamped_missions_pane(client: TestClient):
    v = CuriosityPlugin.manifest.version
    r = client.get("/api/p/plugin-curiosity/ui/")
    assert r.status_code == 200
    assert f"app.js?v={v}" in r.text and f"style.css?v={v}" in r.text
    assert "Your mission — in my words" in r.text


def test_ui_noc_falls_back_to_the_missions_pane(client: TestClient):
    # 0.21.0: a stale /ui/noc/ bookmark lands on the journey, not a 404
    r = client.get("/api/p/plugin-curiosity/ui/noc/")
    assert r.status_code == 200
    assert "Your mission — in my words" in r.text
    assert "Operational dashboard" not in r.text
