"""10.006 acting-on-feedback (0.9.14): the reasons ledger, feedback debts,
the design map, the mission gate, and the prompt contracts that force
feedback to produce structural change instead of empathy."""

from __future__ import annotations

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def fstore(sf, store):
    from plugin_curiosity.feedback import FeedbackStore

    await store.set("own the weekly newsletter end to end")
    return FeedbackStore(sf)


@pytest.fixture
def fctx(ctx, fstore):
    from plugin_curiosity.feedback import register_tools

    register_tools(ctx, fstore)
    return ctx


async def call(ctx, tool, **kw):
    return await ctx.tool_registry.registered[tool][1](**kw)


# -- decisions ledger ---------------------------------------------------------


@pytest.mark.asyncio
async def test_decision_round_trip_and_reconcile(fstore):
    d = await fstore.decision_add(
        "always list exactly what actions you took",
        why="wants to audit my work",
        lives_in="daily report format",
        source="instruction",
    )
    assert d["status"] == "active"
    demoted = await fstore.decision_restate(
        d["id"], "demoted", "kept, moved to the bottom of the report"
    )
    assert demoted["status"] == "demoted"
    assert "bottom" in demoted["status_note"]
    ledger = await fstore.decision_list()
    assert len(ledger) == 1 and ledger[0]["status"] == "demoted"


@pytest.mark.asyncio
async def test_decision_requires_ask_and_valid_source(fstore):
    with pytest.raises(ValueError):
        await fstore.decision_add("   ")
    with pytest.raises(ValueError):
        await fstore.decision_add("do x", source="rumor")


@pytest.mark.asyncio
async def test_restate_requires_note(fstore):
    d = await fstore.decision_add("do x")
    with pytest.raises(ValueError):
        await fstore.decision_restate(d["id"], "demoted", "  ")
    with pytest.raises(LookupError):
        await fstore.decision_restate(
            "00000000-0000-0000-0000-000000000000", "demoted", "note"
        )


# -- feedback debts -----------------------------------------------------------


@pytest.mark.asyncio
async def test_feedback_without_changed_refs_is_a_debt(fstore):
    f = await fstore.feedback_add("your report is shit", diagnosis="report format")
    assert f["acted"] is False
    assert await fstore.unactioned_count() == 1
    closed = await fstore.feedback_act(
        f["id"], "playbook daily-report v2", reconciled="kept actions list at bottom"
    )
    assert closed["acted"] is True
    assert await fstore.unactioned_count() == 0


@pytest.mark.asyncio
async def test_feedback_with_changed_refs_is_closed_at_birth(fstore):
    f = await fstore.feedback_add(
        "lead with progress", changed_refs="trigger daily-report prompt"
    )
    assert f["acted"] is True
    assert await fstore.unactioned_count() == 0


@pytest.mark.asyncio
async def test_feedback_act_requires_refs(fstore):
    f = await fstore.feedback_add("too long")
    with pytest.raises(ValueError):
        await fstore.feedback_act(f["id"], "   ")


# -- tools + steering ---------------------------------------------------------


@pytest.mark.asyncio
async def test_tools_registered_auto_approve(fctx):
    names = {
        "decision_log", "decision_restate", "decision_list",
        "feedback_note", "feedback_act", "feedback_list", "design_map",
    }
    assert names <= set(fctx.tool_registry.registered)
    for n in names:
        td = fctx.tool_registry.registered[n][0]
        assert td.policy == "auto_approve" and td.risk_level == "low"


@pytest.mark.asyncio
async def test_audit_duty_lives_in_the_tool_descriptions(fctx):
    # Dojo runs 2+4: the audit call was skipped when only the contract prose
    # carried it — the descriptions are what the model actually follows.
    dm = fctx.tool_registry.registered["design_map"][0].description
    assert "MANDATORY first call" in dm
    assert "criticizes your behavior" in dm
    fn = fctx.tool_registry.registered["feedback_note"][0].description
    assert "design_map BEFORE" in fn


@pytest.mark.asyncio
async def test_feedback_note_refuses_without_fresh_audit(fctx):
    # Dojo runs 2/4/5: design_map skipped three times — prose and
    # descriptions both lost, so the handler enforces the audit itself.
    out = await call(fctx, "feedback_note", quote="your report is shit")
    assert "audit first" in out["error"]
    assert "design_map" in out["hint"] and "decision_restate" in out["hint"]
    await call(fctx, "design_map")
    out2 = await call(fctx, "feedback_note", quote="your report is shit")
    assert "error" not in out2
    # every record spends the audit — the next one needs a fresh map
    out3 = await call(fctx, "feedback_note", quote="still too long")
    assert "audit first" in out3["error"]


@pytest.mark.asyncio
async def test_feedback_note_tool_steers_when_unacted(fctx):
    await call(fctx, "design_map")
    out = await call(fctx, "feedback_note", quote="your report is shit")
    assert "warning" in out and "same turn" in out["warning"]
    await call(fctx, "design_map")
    out2 = await call(
        fctx, "feedback_note", quote="report fixed?",
        changed_refs="playbook daily-report v2",
    )
    assert "warning" not in out2


@pytest.mark.asyncio
async def test_feedback_list_flags_red_items(fctx):
    await call(fctx, "design_map")
    await call(fctx, "feedback_note", quote="too noisy")
    out = await call(fctx, "feedback_list", unactioned_only=True)
    assert len(out["feedback"]) == 1
    assert "red_items" in out


@pytest.mark.asyncio
async def test_tool_errors_are_dicts_not_raises(fctx):
    assert "error" in await call(fctx, "decision_log", asked="  ")
    assert "error" in await call(
        fctx, "feedback_act", id="00000000-0000-0000-0000-000000000000",
        changed_refs="x",
    )


# -- wiki mirror --------------------------------------------------------------


@pytest.mark.asyncio
async def test_mirror_writes_owner_decisions_page(fctx):
    from plugin_curiosity.feedback import DECISIONS_SLUG

    await call(
        fctx, "decision_log",
        asked="always list exactly what actions you took",
        why="wants to audit", lives_in="daily report",
    )
    await call(fctx, "design_map")
    await call(fctx, "feedback_note", quote="your report is shit")
    wiki = fctx.provider_registry.get("wiki")
    assert DECISIONS_SLUG in wiki.pages
    body = wiki.pages[DECISIONS_SLUG]["body"]
    assert "always list exactly what actions you took" in body
    assert "wants to audit" in body
    assert "NOT ACTED ON YET" in body


@pytest.mark.asyncio
async def test_mirror_degrades_without_wiki(sf, fstore):
    import types

    from plugin_curiosity import feedback as fb

    class _NoWiki:
        def get(self, name):
            raise KeyError(name)

    class _Reg:
        def __init__(self):
            self.registered = {}

        def register(self, plugin, tool_def, handler):
            self.registered[tool_def.name] = (tool_def, handler)

    c = types.SimpleNamespace(
        tool_registry=_Reg(),
        provider_registry=_NoWiki(),
        db_session_factory=sf,
    )
    fb.register_tools(c, fstore)
    out = await c.tool_registry.registered["decision_log"][1](asked="do x")
    assert out["decision"]["asked"] == "do x"
    assert "unavailable" in out["wiki_mirror"]


def test_render_decisions_page_shape():
    from plugin_curiosity.feedback import render_decisions_page

    body = render_decisions_page(
        [{
            "id": "1", "asked": "list | actions", "why": "audit",
            "lives_in": "report", "source": "instruction",
            "status": "demoted", "status_note": "moved to bottom",
            "created_at": "2026-07-14T00:00:00",
        }],
        [{
            "id": "2", "quote": "report is shit", "diagnosis": "",
            "changed_refs": "playbook v2", "reconciled": "kept actions at bottom",
            "acted": True, "created_at": "2026-07-14T00:00:00",
        }],
    )
    assert "| 2026-07-14 | list / actions |" in body  # pipes escaped
    assert "demoted — moved to bottom" in body
    assert "changed: playbook v2" in body
    assert "reconciled: kept actions at bottom" in body


# -- design map ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_design_map_surfaces(fctx):
    out = await call(fctx, "design_map")
    # sqlite test DB has no core identity / playbooks tables — best-effort
    # reporting, never a raise
    assert "identity" in out and "mission" in out
    assert out["playbooks"] == "playbooks plugin not installed"
    assert isinstance(out["triggers"], dict)  # fake scheduler answered
    assert out["feedback_unactioned"] == 0
    assert "owner-decisions" in out["wiki_pages"]
    assert out["owner_decisions"] == "none yet"


@pytest.mark.asyncio
async def test_design_map_lists_owner_decisions_with_reasons(fctx):
    await call(
        fctx, "decision_log",
        asked="list every action", why="wants to audit",
    )
    out = await call(fctx, "design_map")
    assert out["owner_decisions"][0]["asked"] == "list every action"
    assert out["owner_decisions"][0]["why"] == "wants to audit"
    assert "decision_restate" in out["note"]


@pytest.mark.asyncio
async def test_design_map_counts_debts(fctx):
    await call(fctx, "design_map")
    await call(fctx, "feedback_note", quote="too slow")
    out = await call(fctx, "design_map")
    assert out["feedback_unactioned"] == 1


# -- mission gate (0.9.14 structural blitz fix) -------------------------------

_GATED_ADDENDUM = (
    "old frame\n\nHow to onboard yourself:\n\n  1. old flow\n\n"
    "WHAT EACH FIELD MEANS:\nname — what the owner calls you.\n\n"
    "SETUP STATE (you are not fully set up yet):\n\n"
    "Missing — required:\n  ☐ name\n  ☐ emoji\n  ☐ mission\n  ☐ persona\n\n"
    "Missing — optional:\n  ☐ owner_name\n\n"
    "Tools: `update_self(field, value)`, `complete_setup()`."
)

_POST_MISSION_ADDENDUM = (
    "old frame\n\n"
    "SETUP STATE (you are not fully set up yet):\n\n"
    "Saved:\n  ✓ mission: own the newsletter\n\n"
    "Missing — required:\n  ☐ name\n  ☐ emoji\n  ☐ persona\n\n"
    "Tools: `update_self(field, value)`, `complete_setup()`."
)


def test_gate_hides_checklist_while_mission_missing():
    from plugin_curiosity.mission import (
        MISSION_GATE_FLOW,
        rewrite_onboarding_addendum,
    )

    out = rewrite_onboarding_addendum(_GATED_ADDENDUM)
    assert out.startswith(MISSION_GATE_FLOW)
    # nothing to blitz: other fields and complete_setup absent
    assert "☐ name" not in out
    assert "☐ emoji" not in out
    assert "☐ persona" not in out
    assert "complete_setup" not in out.split(MISSION_GATE_FLOW)[1]
    assert "☐ mission" in out
    assert "mission_set" in out


def test_gate_keeps_saved_items_visible():
    from plugin_curiosity.mission import rewrite_onboarding_addendum

    addendum = _GATED_ADDENDUM.replace(
        "Missing — required:", "Saved:\n  ✓ owner_name: Roy\n\nMissing — required:"
    )
    out = rewrite_onboarding_addendum(addendum)
    assert "✓ owner_name: Roy" in out


def test_full_flow_returns_once_mission_saved():
    from plugin_curiosity.mission import (
        MISSION_FIRST_FLOW,
        MISSION_GATE_FLOW,
        rewrite_onboarding_addendum,
    )

    out = rewrite_onboarding_addendum(_POST_MISSION_ADDENDUM)
    assert out.startswith(MISSION_FIRST_FLOW)
    assert MISSION_GATE_FLOW not in out
    # state block verbatim: checklist + tools line back
    assert "☐ name" in out and "complete_setup" in out


def test_gate_flow_keeps_the_pinned_mechanics():
    from plugin_curiosity.mission import MISSION_GATE_FLOW

    assert "mission_set" in MISSION_GATE_FLOW
    assert "update_self(field='mission', value=...)" in MISSION_GATE_FLOW
    assert "FIRST question" in MISSION_GATE_FLOW
    assert "never from you" in MISSION_GATE_FLOW  # name comes from the owner


# -- prompt contracts ---------------------------------------------------------


def test_feedback_contract_in_both_phases():
    from plugin_curiosity import prompts
    from plugin_curiosity.mission import prompt_fragment

    m = {
        "statement": "own the newsletter", "autonomy_rung": 1,
        "risk_ceiling": "low", "wiki_id": None,
    }
    for phase in ("setup", "work"):
        frag = prompt_fragment(m, phase=phase)
        assert prompts.FEEDBACK_CONTRACT in frag
        assert prompts.DECISION_LEDGER in frag
        assert prompts.PROACTIVE_RULE in frag


def test_contract_wording_is_mechanical():
    from plugin_curiosity.prompts import (
        DECISION_LEDGER,
        FEEDBACK_CONTRACT,
        PROACTIVE_RULE,
    )

    for phrase in (
        "design_map", "decision_list", "decision_restate", "feedback_note",
        "SAME TURN", "playbook_edit",
    ):
        assert phrase in FEEDBACK_CONTRACT
    assert "decision_log" in DECISION_LEDGER
    assert "never ask the owner" in PROACTIVE_RULE.lower()


def test_heartbeat_and_review_surface_feedback_debts():
    from plugin_curiosity.prompts import HEARTBEAT_CONTRACT
    from plugin_curiosity.review import WEEKLY_REVIEW_TARGET

    assert "feedback_list(unactioned_only=true)" in HEARTBEAT_CONTRACT
    assert "feedback_list(unactioned_only=true)" in WEEKLY_REVIEW_TARGET
    assert "feedback_act" in WEEKLY_REVIEW_TARGET


def test_owner_decisions_is_a_seeded_stub():
    from plugin_curiosity.mission import _STUB_SLUGS

    assert "owner-decisions" in _STUB_SLUGS


def test_setup_flow_carries_decision_log_duty():
    from plugin_curiosity.mission import MISSION_FIRST_FLOW

    assert "decision_log" in MISSION_FIRST_FLOW


def test_version_bumped_everywhere():
    import pathlib
    import tomllib

    import plugin_curiosity as pc

    assert pc.CuriosityPlugin.manifest.version == "0.9.14"
    root = pathlib.Path(pc.__file__).parents[1]
    assert tomllib.loads((root / "pyproject.toml").read_text())["project"][
        "version"
    ] == "0.9.14"
    assert tomllib.loads(
        (root / "plugin_curiosity" / "luna-plugin.toml").read_text()
    )["version"] == "0.9.14"


# -- 0.9.14 tool-layer mission gate ------------------------------------------
# The dojo caught the blitz surviving the prompt-only gate: the tool schemas
# still advertised complete_setup + every update_self field. The gate must
# live in the handlers.


class _GateDef:
    def __init__(self, name, description):
        self.name = name
        self.description = description


class _GateEntry:
    def __init__(self, name, desc, handler):
        self.definition = _GateDef(name, desc)
        self.handler = handler


class _GateRegistry:
    def __init__(self, entries=()):
        self._e = {e.definition.name: e for e in entries}

    def get(self, name):
        return self._e[name]


class _GateCtx:
    def __init__(self, reg):
        self.tool_registry = reg
        # the identity probe treats a failing session factory as "mission
        # missing" — the safe default; open-gate tests use the store path
        self.db_session_factory = _boom_sf


def _boom_sf():
    raise RuntimeError("no db in this test")


class _GateStore:
    def __init__(self, mission=None):
        self.mission = mission

    async def get(self):
        return self.mission


def _gated_pair():
    calls = []

    async def update_self(field="", value="", **kw):
        calls.append(("update_self", field, value))
        return {"ok": True, "field": field}

    async def complete_setup(**kw):
        calls.append(("complete_setup",))
        return {"ok": True}

    ut = _GateEntry("update_self", "MISSION and PERSONA you write yourself", update_self)
    ct = _GateEntry("complete_setup", "Finish first-run setup.", complete_setup)
    return _GateCtx(_GateRegistry([ut, ct])), ut, ct, calls


@pytest.mark.asyncio
async def test_gate_locks_non_mission_fields_and_completion():
    from plugin_curiosity.setup_gate import install_setup_gate

    ctx, ut, ct, calls = _gated_pair()
    assert install_setup_gate(ctx, lambda: _GateStore(None)) is True

    out = await ut.handler(field="name", value="Gal")
    assert out["ok"] is False and "locked" in out["error"]
    assert "mission_set" in out["hint"]
    out = await ct.handler()
    assert out["ok"] is False and "mission" in out["error"]
    assert calls == []  # neither original ever fired


@pytest.mark.asyncio
async def test_gate_lets_the_mission_through_while_locked():
    from plugin_curiosity.setup_gate import install_setup_gate

    ctx, ut, ct, calls = _gated_pair()
    install_setup_gate(ctx, lambda: _GateStore(None))
    out = await ut.handler(field="mission", value="grow adoption")
    assert out["ok"] is True
    out = await ut.handler(field="purpose", value="grow adoption")  # alias
    assert out["ok"] is True
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_gate_opens_with_an_active_mission():
    from plugin_curiosity.setup_gate import install_setup_gate

    ctx, ut, ct, calls = _gated_pair()
    install_setup_gate(ctx, lambda: _GateStore({"statement": "x"}))
    assert (await ut.handler(field="name", value="Nadav"))["ok"] is True
    assert (await ct.handler())["ok"] is True
    assert len(calls) == 2


def test_gate_install_is_idempotent_and_removable():
    from plugin_curiosity.setup_gate import install_setup_gate, remove_setup_gate

    ctx, ut, ct, _ = _gated_pair()
    orig_u, orig_c = ut.handler, ct.handler
    assert install_setup_gate(ctx, lambda: _GateStore(None)) is True
    wrapped_u = ut.handler
    assert install_setup_gate(ctx, lambda: _GateStore(None)) is False
    assert ut.handler is wrapped_u  # no double wrap
    remove_setup_gate(ctx)
    assert ut.handler is orig_u and ct.handler is orig_c


def test_gate_installs_the_mission_only_descriptions():
    from plugin_curiosity.setup_gate import install_setup_gate

    ctx, ut, ct, _ = _gated_pair()
    install_setup_gate(ctx, lambda: _GateStore(None))
    # run 3: the model follows tool descriptions over flow prose — while the
    # gate is closed the schemas must describe ONLY the mission stage: no
    # field list, no name/emoji asks, no self-written mission.
    d = ut.definition.description
    assert "exactly ONE field is unlocked: mission" in d
    assert "AS STATED" in d and "no confirmation round" in d
    assert "agent_name" not in d and "emoji" not in d
    assert "you write yourself" not in d
    assert "LOCKED until the mission is saved" in ct.definition.description


@pytest.mark.asyncio
async def test_gate_descriptions_flip_with_the_state():
    from plugin_curiosity import setup_gate

    ctx, ut, ct, _ = _gated_pair()
    setup_gate.install_setup_gate(ctx, lambda: _GateStore(None))
    await setup_gate.sync_gate_descriptions(ctx, lambda: _GateStore(None))
    assert "exactly ONE field is unlocked" in ut.definition.description
    # mission saved → the full checklist text returns
    await setup_gate.sync_gate_descriptions(ctx, lambda: _GateStore({"statement": "x"}))
    assert "never invent" in ut.definition.description
    assert "agent_name" in ut.definition.description
    assert ct.definition.description.startswith("Finish first-run setup")
    # the sync is state-pure: a closed gate restores the mission-only text
    await setup_gate.sync_gate_descriptions(ctx, lambda: _GateStore(None))
    assert "exactly ONE field is unlocked" in ut.definition.description


def test_gate_survives_missing_tools():
    from plugin_curiosity.setup_gate import install_setup_gate

    assert install_setup_gate(_GateCtx(_GateRegistry()), lambda: None) is False
