"""0.16.1 / phase11-06 — "Change it" hands the owner the composer.

Luna 065 gives plugin iframes a `luna-chat` postMessage bridge: the shell
acks every valid message, so a plugin can feature-detect it. These tests pin
the app.js contract:

* a `ping` fires at startup and the `luna-chat-ack` listener flips the flag;
* both Change-it buttons prefer `prefillChat(...)` and keep the muted-moment
  fallback for cores that never ack (old core -> unchanged behavior);
* the recording buttons (Confirm / Go ahead / Approve) are NOT rerouted —
  they still post muted moments with their MOMENT_TOOLS allowlists.
"""

from __future__ import annotations

import re
from pathlib import Path

UI = Path(__file__).parent.parent / "plugin_curiosity" / "ui"
APP = (UI / "app.js").read_text()


def test_pings_the_bridge_at_startup():
    assert "action: 'ping'" in APP
    assert "pingChatBridge();" in APP  # module-level call, not just a definition


def test_ack_flips_the_flag():
    assert "luna-chat-ack" in APP
    assert re.search(r"luna-chat-ack.*CHAT_BRIDGE = true", APP)


def test_prefill_requires_the_ack_and_targets_the_parent():
    body = APP.split("function prefillChat")[1].split("\nfunction")[0]
    assert "if (!CHAT_BRIDGE) return false" in body
    assert "action: 'prefill'" in body
    assert "window.parent.postMessage" in body


def test_change_buttons_prefill_with_muted_fallback():
    # mission: prefill first, SAY.changeMission moment only when unacked
    mission = APP.split("bx.onclick")[1].split("};")[0]
    assert "prefillChat" in mission and "SAY.changeMission" in mission
    assert mission.index("prefillChat") < mission.index("SAY.changeMission")
    # step: same shape, prefix names the step
    step = APP.split("[data-change]")[1].split("});")[0]
    assert "prefillChat(`Change this step: ${b.dataset.what}" in step
    assert "SAY.changeStep" in step


def test_recording_buttons_keep_their_muted_moments():
    # Confirm / Go / Approve still record via tools — never rerouted to prefill.
    for say, tools in (
        ("SAY.confirm(", "MOMENT_TOOLS.confirm"),
        ("SAY.go(", "MOMENT_TOOLS.go"),
        ("SAY.approve(", "MOMENT_TOOLS.approve"),
    ):
        lines = [ln for ln in APP.splitlines() if say in ln and "sendMoment" in ln]
        assert lines, f"no sendMoment call site for {say}"
        for ln in lines:
            assert tools in ln
            assert "prefillChat" not in ln
