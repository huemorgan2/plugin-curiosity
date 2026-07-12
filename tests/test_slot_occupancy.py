"""Slot occupancy (0.9.7, core 034/phase03): the _occupy_prompt handler.

On claim cores the manifest claims core.drive + core.onboarding — the
curiosity fragment replaces the drive slot (swap pattern) and, while
missionless, the mission-first note is prepended to the onboarding addendum.
The mutability contract itself (granted claims honored, foreign diffs
reverted, core.truth untouchable) is enforced and tested core-side
(tests/034-agent-behaviour-fix/phase03 + luna_sdk.testing); here we assert
the handler's own behavior against fake sections, exactly like
test_prompt_primacy.py does for the legacy path.
"""

from __future__ import annotations

import types

import pytest

import plugin_curiosity as pc
from plugin_curiosity import CuriosityPlugin
from plugin_curiosity.mission import (
    MISSION_FIRST_FLOW,
    MISSION_FIRST_NOTE,
    SETUP_STATE_HEADER,
    prompt_fragment,
    rewrite_onboarding_addendum,
)


def _sec(source: str, text: str = "x") -> types.SimpleNamespace:
    return types.SimpleNamespace(source=source, text=text)


def _plugin(mission) -> CuriosityPlugin:
    p = CuriosityPlugin()

    class _Store:
        async def get(self):
            return mission

    p._store = _Store()
    return p


@pytest.fixture
def claims_core(monkeypatch):
    monkeypatch.setattr(pc, "_CLAIMS_SUPPORTED", True)


@pytest.mark.asyncio
async def test_missionless_fragment_occupies_drive_slot(claims_core):
    p = _plugin(None)
    stance, drive, onboarding, truth, own = (
        _sec("core.stance"),
        _sec("core.drive", "core drive"),
        _sec("core.onboarding", "SETUP STATE: checklist"),
        _sec("core.truth", "TRUTH"),
        _sec("plugin-curiosity", "mission ask"),
    )
    hctx = types.SimpleNamespace(sections=[stance, drive, onboarding, truth, own])
    await p._occupy_prompt(hctx)
    # swap: exactly one drive-position section, and it's ours
    assert hctx.sections == [stance, own, onboarding, truth]
    assert not any(s.source == "core.drive" for s in hctx.sections)
    # mission-first ordering written INTO the claimed addendum
    assert onboarding.text.startswith(MISSION_FIRST_NOTE)
    assert onboarding.text.endswith("SETUP STATE: checklist")
    assert truth.text == "TRUTH"


@pytest.mark.asyncio
async def test_mission_set_occupies_drive_without_touching_onboarding(claims_core):
    p = _plugin({"statement": "grow signups"})
    drive, onboarding, own = (
        _sec("core.drive", "core drive"),
        _sec("core.onboarding", "checklist"),
        _sec("plugin-curiosity", "mission drive"),
    )
    hctx = types.SimpleNamespace(sections=[drive, onboarding, own])
    await p._occupy_prompt(hctx)
    assert hctx.sections == [own, onboarding]
    assert onboarding.text == "checklist"  # note only rides while missionless


@pytest.mark.asyncio
async def test_blocked_plugin_never_occupies_the_slot(claims_core):
    """Dependency gate closed: the paused note must not replace core drive."""
    p = _plugin(None)
    p._missing = ["plugin-wiki"]
    drive, own = _sec("core.drive", "core drive"), _sec("plugin-curiosity", "paused")
    hctx = types.SimpleNamespace(sections=[drive, own])
    await p._occupy_prompt(hctx)
    assert hctx.sections == [drive, own]
    assert drive.text == "core drive"


@pytest.mark.asyncio
async def test_no_drive_slot_falls_back_to_legacy_reorder(claims_core):
    """Owner monolith override → no named core.drive section; the legacy
    move-after-onboarding position fix still applies."""
    p = _plugin(None)
    base, onboarding, wiki, own = (
        _sec("core"),
        _sec("core.onboarding"),
        _sec("plugin-wiki"),
        _sec("plugin-curiosity"),
    )
    hctx = types.SimpleNamespace(sections=[base, onboarding, wiki, own])
    await p._occupy_prompt(hctx)
    assert hctx.sections == [base, onboarding, own, wiki]


@pytest.mark.asyncio
async def test_legacy_core_uses_reorder_path(monkeypatch):
    monkeypatch.setattr(pc, "_CLAIMS_SUPPORTED", False)
    p = _plugin(None)
    drive, onboarding, wiki, own = (
        _sec("core.drive", "core drive"),
        _sec("plugin-onboarding", "checklist"),
        _sec("plugin-wiki"),
        _sec("plugin-curiosity"),
    )
    hctx = types.SimpleNamespace(sections=[drive, onboarding, wiki, own])
    await p._occupy_prompt(hctx)
    # reorder only: drive untouched, fragment after onboarding
    assert hctx.sections == [drive, onboarding, own, wiki]
    assert drive.text == "core drive"


@pytest.mark.asyncio
async def test_no_own_sections_is_a_noop(claims_core):
    p = _plugin(None)
    sections = [_sec("core.drive"), _sec("core.onboarding", "checklist")]
    hctx = types.SimpleNamespace(sections=list(sections))
    await p._occupy_prompt(hctx)
    assert hctx.sections == sections
    assert sections[1].text == "checklist"


_LIVE_ADDENDUM = (
    "You're a brand-new agent meeting your owner for the first time.\n\n"
    "How to onboard yourself:\n\n  1. Look at SETUP STATE. Pick the next "
    "REQUIRED item.\n\n"
    "WHAT EACH FIELD MEANS:\nname — what the owner calls you.\n\n"
    f"{SETUP_STATE_HEADER}:\n\nMissing — required:\n  ☐ name\n  ☐ emoji\n\n"
    "Tools: `update_self(field, value)`, `complete_setup()`."
)


@pytest.mark.asyncio
async def test_missionless_rewrites_live_addendum_mission_first(claims_core):
    """0.9.13 (luna 036): the claim binds to the LIVE addendum — the flow is
    REWRITTEN mission-first, the per-turn SETUP STATE block survives
    verbatim, and the old name-first flow is gone."""
    p = _plugin(None)
    drive = _sec("core.drive", "core drive")
    onboarding = _sec("core.onboarding", _LIVE_ADDENDUM)
    own = _sec("plugin-curiosity", "mission ask")
    hctx = types.SimpleNamespace(sections=[drive, onboarding, own])
    await p._occupy_prompt(hctx)
    assert onboarding.text.startswith(MISSION_FIRST_FLOW)
    assert onboarding.text.endswith("Tools: `update_self(field, value)`, `complete_setup()`.")
    assert "☐ name" in onboarding.text  # live state kept verbatim
    assert "Look at SETUP STATE. Pick the next REQUIRED item." not in onboarding.text
    assert MISSION_FIRST_NOTE not in onboarding.text  # rewrite, not prepend


def test_rewrite_helper_none_without_header():
    assert rewrite_onboarding_addendum("some other addendum shape") is None


def test_mission_first_flow_unifies_both_saves():
    assert "mission_set" in MISSION_FIRST_FLOW
    assert "update_self(field='mission', ...)" in MISSION_FIRST_FLOW
    assert "FIRST question" in MISSION_FIRST_FLOW


def test_slot_mode_fragment_drops_ordering_prose():
    legacy = prompt_fragment(None)
    slot = prompt_fragment(None, slot_mode=True)
    assert "OVERRIDES its ordering" in legacy
    assert "OVERRIDES its ordering" not in slot
    # everything else survives in both
    for phrase in ("no active mission yet", "EVERY reply", "mission_set IN THAT SAME TURN"):
        assert phrase in legacy and phrase in slot


def test_toml_declares_the_claims():
    import pathlib
    import tomllib

    p = pathlib.Path(__file__).parents[1] / "plugin_curiosity" / "luna-plugin.toml"
    data = tomllib.loads(p.read_text())
    assert data["prompt"]["overrides"] == ["core.drive", "core.onboarding"]
    assert data["version"] == CuriosityPlugin.manifest.version
