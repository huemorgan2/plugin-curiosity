"""Phase13 — one round means one round (intake idempotence):
- mission_draft's repeat call is a tool-layer REFUSAL ("round is SPENT"),
  never a silent echo of the ask-your-questions steering;
- the first-call steering tolerates questions already written before the
  call (send the reply AS IS — never repeat/reword/expand);
- prompt assembly is draft-aware: with a captured draft the missionless
  fragment, the gate flow, and the reduced state block all flip to
  save-only — no capture/ask vocabulary survives into the drafted stage;
- the setup gate's gated descriptions/errors speak the draft-first
  contract (the pre-11.001 "no confirmation round" wording is gone).
"""

from __future__ import annotations

import pytest

from plugin_curiosity import CuriosityPlugin, setup_gate
from plugin_curiosity import mission as mission_mod


async def call(ctx, tool: str, **kwargs):
    return await ctx.tool_registry.registered[tool][1](**kwargs)


# ---- Unit 1: the repeat draft call refuses ----------------------------------


@pytest.mark.asyncio
async def test_store_draft_reports_pre_existence(store):
    d1 = await store.draft("first words")
    assert d1["already_existed"] is False
    d2 = await store.draft("rival words")
    assert d2["already_existed"] is True
    assert d2["verbatim"] == "first words"  # oldest still wins


@pytest.mark.asyncio
async def test_draft_get_shape_has_no_existence_flag(store):
    await store.draft("first words")
    assert "already_existed" not in (await store.draft_get())


@pytest.mark.asyncio
async def test_repeat_draft_tool_call_refuses_round_spent(ctx, store):
    r1 = await call(ctx, "mission_draft", verbatim="run my hiring pipeline")
    assert "already_drafted" not in r1
    assert "already_existed" not in r1["draft"]
    # the first call already tolerates questions written before the call —
    # this is what stops the "text + call, result re-orders, ask again" loop
    assert "AS IS" in r1["next"]
    assert "never repeat" in r1["next"]

    r2 = await call(ctx, "mission_draft", verbatim="run my hiring pipeline")
    assert r2["already_drafted"] is True
    assert "SPENT" in r2["next"]
    assert "Do NOT ask" in r2["next"]
    assert "mission_set" in r2["next"]
    assert "already_existed" not in r2["draft"]
    # nothing changed server-side
    assert (await store.draft_get())["verbatim"] == "run my hiring pipeline"


# ---- Unit 2: the drafted stage in every prompt surface ----------------------


DRAFT = {"verbatim": "run my hiring pipeline", "age_hours": 0.1}


def test_missionless_fragment_with_draft_never_asks():
    frag = mission_mod.prompt_fragment(None, draft=DRAFT)
    assert "SPENT" in frag
    assert DRAFT["verbatim"] in frag  # the owner's words ride along
    assert "ask at most 2-3 questions" not in frag
    assert "mission_set" in frag and "origin_statement" in frag
    assert "load_tools(group='curiosity')" in frag  # the hop still taught
    assert "DETOUR" in frag
    assert "Action rails" in frag  # rails survive the drafted variant


def test_missionless_fragment_without_draft_unchanged():
    frag = mission_mod.prompt_fragment(None)
    assert "ask at most 2-3 questions" in frag
    assert "mission_draft" in frag


def test_state_block_drafted_variant_is_save_only():
    block = mission_mod._mission_gate_state_block(
        "SETUP STATE:\n  ✓ name — Luna\n  ☐ mission", has_draft=True
    )
    assert "SPENT" in block
    assert "capture it VERBATIM" not in block
    assert "2-3" not in block
    assert "never call `mission_draft` again" in block
    assert "mission_set" in block and "update_self" in block
    assert "✓ name — Luna" in block  # saved items stay visible


def test_state_block_ask_variant_unchanged():
    block = mission_mod._mission_gate_state_block("SETUP STATE:\n  ☐ mission")
    assert "capture it VERBATIM" in block
    assert "mission_draft" in block


_GATE_ADDENDUM = (
    "You're a brand-new agent.\n\nHow to onboard yourself:\n\n"
    f"{mission_mod.SETUP_STATE_HEADER}:\n\nMissing — required:\n"
    "  ☐ mission\n  ☐ name\n\n"
    "Tools: `update_self(field, value)`, `complete_setup()`."
)


def test_rewrite_addendum_drafted_stage():
    out = mission_mod.rewrite_onboarding_addendum(_GATE_ADDENDUM, has_draft=True)
    assert out.startswith(mission_mod.MISSION_GATE_FLOW_DRAFTED)
    assert "ALREADY captured" in out
    assert "capture it VERBATIM" not in out
    assert "AT MOST 2-3" not in out


def test_rewrite_addendum_ask_stage_unchanged():
    out = mission_mod.rewrite_onboarding_addendum(_GATE_ADDENDUM)
    assert out.startswith(mission_mod.MISSION_GATE_FLOW)


def test_drafted_gate_flow_never_asks():
    flow = mission_mod.MISSION_GATE_FLOW_DRAFTED
    assert "SPENT" in flow
    assert "never call `mission_draft` again" in flow
    assert "AT MOST 2-3" not in flow
    assert "IMPATIENCE" in flow
    assert "DETOUR" in flow
    assert "origin_statement" in flow


# ---- Unit 6: prompt_sections wiring (through the real store) ----------------


@pytest.mark.asyncio
async def test_prompt_sections_emits_drafted_fragment(store):
    p = CuriosityPlugin()
    p._store = store
    p._missing = []
    p._activated = True
    p._scopes = None
    await store.draft("run my hiring pipeline")
    sections = await p.prompt_sections()
    assert len(sections) == 1
    assert "SPENT" in sections[0]
    assert "ask at most 2-3 questions" not in sections[0]


@pytest.mark.asyncio
async def test_prompt_sections_without_draft_keeps_the_ask(store):
    p = CuriosityPlugin()
    p._store = store
    p._missing = []
    p._activated = True
    p._scopes = None
    sections = await p.prompt_sections()
    assert "ask at most 2-3 questions" in sections[0]


# ---- Unit 5: the gate vocabulary joins the draft-first contract -------------


def test_gated_update_self_desc_is_draft_first():
    desc = setup_gate.UPDATE_SELF_DESC_GATED
    assert "no confirmation round" not in desc
    assert "AS STATED" not in desc
    assert "mission_draft" in desc
    assert "ON-TOPIC" in desc
    assert "never a fresh question round" in desc


def test_locked_errors_are_draft_first():
    field_hint = setup_gate._LOCKED_FIELD_ERROR["hint"]
    assert "mission_draft" in field_hint
    assert "Never re-open the question round" in field_hint
    complete_hint = setup_gate._LOCKED_COMPLETE_ERROR["hint"]
    assert "mission_draft" in complete_hint
    assert "never a fresh question round" in complete_hint
