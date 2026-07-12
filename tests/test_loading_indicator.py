"""0.9.8 — first-paint loading indicator on both panes.

Before this, everything was hidden until the first /missions/overview answer:
on hosted Luna (slow auth handshake, edge revalidation) the owner stared at a
blank page. Both panes now boot with a visible #loading state that every
render path — data, blocked, error — must clear.
"""

from __future__ import annotations

from pathlib import Path

UI = Path(__file__).parent.parent / "plugin_curiosity" / "ui"

PANES = {"missions": UI, "ops dashboard": UI / "noc"}


def test_both_panes_boot_with_visible_loading_state():
    for label, root in PANES.items():
        html = (root / "index.html").read_text()
        assert 'id="loading"' in html, f"{label}: no loading element"
        # visible by default — the loading div itself must not start hidden
        loading_tag = html.split('id="loading"')[1].split(">")[0]
        assert "hidden" not in loading_tag, f"{label}: loading starts hidden"
        assert "spinner" in html, f"{label}: no spinner"


def test_every_render_path_clears_loading():
    for label, root in PANES.items():
        js = (root / "app.js").read_text()
        # render() (data + blocked paths funnel through it) and the load()
        # error path both hide it
        assert js.count("show('loading', false)") >= 2, (
            f"{label}: loading not cleared on all paths"
        )


def test_loading_styled_with_reduced_motion_fallback():
    for label, root in PANES.items():
        css = (root / "style.css").read_text()
        assert ".loading" in css and ".spinner" in css, f"{label}: styles missing"
        assert "prefers-reduced-motion" in css, f"{label}: no reduced-motion fallback"
