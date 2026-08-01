"""0.9.8 — first-paint loading indicator on the Missions pane.

Before this, everything was hidden until the first /missions/overview answer:
on hosted Luna (slow auth handshake, edge revalidation) the owner stared at a
blank page. The pane now boots with a visible #loading state that every
render path — data, blocked, error — must clear. (0.21.0: the ops dashboard
pane this file also covered was removed.)
"""

from __future__ import annotations

from pathlib import Path

UI = Path(__file__).parent.parent / "plugin_curiosity" / "ui"


def test_pane_boots_with_visible_loading_state():
    html = (UI / "index.html").read_text()
    assert 'id="loading"' in html, "no loading element"
    # visible by default — the loading div itself must not start hidden
    loading_tag = html.split('id="loading"')[1].split(">")[0]
    assert "hidden" not in loading_tag, "loading starts hidden"
    assert "spinner" in html, "no spinner"


def test_every_render_path_clears_loading():
    js = (UI / "app.js").read_text()
    # render() (data + blocked paths funnel through it) and the load()
    # error path both hide it
    assert js.count("show('loading', false)") >= 2, "loading not cleared on all paths"


def test_loading_styled_with_reduced_motion_fallback():
    css = (UI / "style.css").read_text()
    assert ".loading" in css and ".spinner" in css, "styles missing"
    assert "prefers-reduced-motion" in css, "no reduced-motion fallback"
