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
    """data-tip may exist only on (i) .help elements, on both panes."""
    for rel in ("index.html", "noc/index.html"):
        html = (UI / rel).read_text()
        for m in re.finditer(r"<[^>]*data-tip=", html):
            assert 'class="help"' in m.group(0) or "help" in m.group(0), (
                f"{rel}: data-tip outside a .help affordance: {m.group(0)[:80]}"
            )
    for rel in ("app.js", "noc/app.js"):
        js = (UI / rel).read_text()
        # the hover handler must anchor exclusively to .help elements
        assert ".help[data-tip]" in js, f"{rel}: tooltip layer not scoped to .help"


def test_missions_pane_sections_in_order():
    html = (UI / "index.html").read_text()
    order = [
        html.index("Active mission"),
        html.index("Job description"),
        html.index('id="setup-panel"'),
        html.index('id="goals-panel"'),
    ]
    assert order == sorted(order), "the four sections must render in plan order"
    # removed panels stay removed (all live on the NOC now)
    for gone in ("noc-tiles", "hb-history", "activity", "wiki-panel", "history-panel", "gaps-panel"):
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


def test_jd_stamp_and_pivot_card_wired():
    js = (UI / "app.js").read_text()
    assert "Living draft" in js and "role_version" in js
    assert "pivot-card" in js and "Big change" in js
    # goals: timeline + readiness two-liners
    assert "goal-timeline" in js and "readiness_note" in js


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
    assert "Active mission" in r.text


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
