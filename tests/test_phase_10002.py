"""10.002 — the panes: Missions rebuilt to the four-section grammar, NOC
split out behind its own sidebar section (SidebarSection.path, luna 031).

The server side stays thin: one manifest entry, one route. The tests that
matter most here are the UX-grammar invariants the plan makes contractual:
zero S\\d jargon on the owner-facing pane, tooltips only behind (i)
affordances, the four sections in order.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugin_curiosity import CuriosityPlugin

UI = Path(__file__).parent.parent / "plugin_curiosity" / "ui"


# ---- manifest: one pane, two tabs (0.9.5) ------------------------------------


def test_manifest_advertises_single_pane_with_ops_tab():
    secs = CuriosityPlugin.manifest.sidebar_sections
    assert [s.id for s in secs] == ["missions"]
    assert getattr(secs[0], "path", "ui/") == "ui/"
    # the ops wall is a tab inside the Missions pane, embedded from ui/noc/
    index = (UI / "index.html").read_text()
    assert "Operational dashboard" in index
    assert 'id="ops-frame"' in index
    app = (UI / "app.js").read_text()
    assert "noc/?v=" in app  # tab 2 lazy-loads the embedded document


def test_noc_assets_ship_with_the_package():
    for name in ("index.html", "app.js", "style.css"):
        assert (UI / "noc" / name).exists(), f"ui/noc/{name} missing"
    import tomllib

    with open(Path(__file__).parent.parent / "pyproject.toml", "rb") as f:
        py = tomllib.load(f)
    assert "ui/noc/*" in py["tool"]["setuptools"]["package-data"]["plugin_curiosity"]


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


def test_tooltips_only_behind_help_affordances():
    """data-tip may exist only on (i) .help elements. 0.16.0: the Missions
    journey page has no tooltip layer at all — plain sentences carry the
    explanations; only the ops pane keeps (i) affordances."""
    for rel in ("index.html", "noc/index.html"):
        html = (UI / rel).read_text()
        for m in re.finditer(r"<[^>]*data-tip=", html):
            assert 'class="help"' in m.group(0) or "help" in m.group(0), (
                f"{rel}: data-tip outside a .help affordance: {m.group(0)[:80]}"
            )
    assert "data-tip" not in (UI / "index.html").read_text()
    assert "data-tip" not in (UI / "app.js").read_text()
    # the ops pane's hover handler must anchor exclusively to .help elements
    assert ".help[data-tip]" in (UI / "noc" / "app.js").read_text()


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
    # machinery stays off this pane (all of it lives on the NOC now)
    for gone in ('id="noc-tiles"', 'id="hb-history"', 'id="activity"',
                 'id="wiki-panel"', 'id="history-panel"', 'id="gaps-panel"',
                 'id="jd-blocks"', 'id="abilities"'):
        assert gone not in html, f"{gone} belongs to the NOC pane, not Missions"


def test_noc_pane_carries_the_moved_panels():
    html = (UI / "noc" / "index.html").read_text()
    for panel in (
        "noc-tiles",       # role wall
        "hb-latest",       # heartbeat
        "gaps",            # gap board
        "activity",        # activity stream
        "wiki",            # knowledge shelf
        "next",            # what happens next
        "chip-autonomy",   # chips moved off Missions
        "chip-risk",
        "pace",
        "history-panel",   # past missions
    ):
        assert panel in html, f"NOC pane missing {panel}"


def test_jd_and_setup_ladder_moved_to_noc():
    # 0.16.0: the living-draft JD and the ability ladder render on the ops
    # pane; the Missions tab renders the journey payload and its buttons
    noc_js = (UI / "noc" / "app.js").read_text()
    assert "Living draft" in noc_js and "role_version" in noc_js
    assert "renderSetup" in noc_js and "subtask" in noc_js
    js = (UI / "app.js").read_text()
    assert "Living draft" not in js and "goal-timeline" not in js
    # the M0a buttons post muted moment messages into the newest conversation
    assert "kind: 'muted'" in js and "channel: 'moment'" in js
    assert "/api/conversations" in js
    for say in ("Go ahead", "Change it", "Confirm", "Approve"):
        assert say in js, f"button {say!r} missing from the journey pane"


# ---- serving: /ui/noc/ stamped like /ui/ ------------------------------------


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


def test_ui_noc_serves_stamped_noc_pane(client: TestClient):
    v = CuriosityPlugin.manifest.version
    r = client.get("/api/p/plugin-curiosity/ui/noc/")
    assert r.status_code == 200
    assert f"app.js?v={v}" in r.text and f"style.css?v={v}" in r.text
    assert "Operational dashboard" in r.text  # renamed from NOC in 0.9.5


def test_ui_noc_no_trailing_slash_serves_noc_index(client: TestClient):
    r = client.get("/api/p/plugin-curiosity/ui/noc")
    assert r.status_code == 200
    assert "Operational dashboard" in r.text


def test_ui_noc_assets_served(client: TestClient):
    for asset in ("noc/app.js", "noc/style.css"):
        r = client.get(f"/api/p/plugin-curiosity/ui/{asset}")
        assert r.status_code == 200, asset
