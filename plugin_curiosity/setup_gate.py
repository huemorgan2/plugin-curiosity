"""0.9.14: the mission gate, tool layer.

The 10.006 dojo caught the blitz surviving the prompt-only gate: the
mission turn ran update_self x5 + complete_setup even though the rewritten
addendum showed a mission-only stage. The prompt never stood a chance —
the TOOL SCHEMAS still advertised complete_setup and every update_self
field, and update_self's own description said "MISSION and PERSONA you
write yourself". The vocabulary the agent must not use lived in the tool
list, not the prompt (same principle as the jargon fix: what she must not
do must not exist in her protocol).

So the gate moves into the handlers. While the mission is missing:

  - ``update_self`` accepts ONLY the mission field — everything else
    returns a locked error steering back to the mission ask;
  - ``complete_setup`` refuses outright;
  - both descriptions are rewritten to mission-first semantics.

Completion is thereby structurally impossible before the mission: the
other required fields cannot be saved while it's missing, and
complete_setup demands them. Installation is idempotent and re-converges
on every prompt assembly, so a plugin_onboarding hot reload (which
re-registers the pristine handlers) is healed one turn later.
"""

from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import text as sa_text

_GATE_MARK = "_curiosity_mission_gate"
# update_self aliases that mean the mission (plugin_onboarding._ALIASES).
_MISSION_FIELDS = {"mission", "purpose"}

# Stage-aware descriptions (dojo run 3): the model follows tool descriptions
# more faithfully than flow prose — run 2 blitzed on "MISSION and PERSONA you
# write yourself", run 3 asked for the name pre-save on "NAME and EMOJI come
# from the owner". So while the gate is closed the schemas must describe ONLY
# the mission stage; the full checklist text appears the moment it opens.
# sync_gate_descriptions() flips them on every prompt assembly.
UPDATE_SELF_DESC_GATED = (
    "Save a single piece of your own identity during first-run setup. "
    "RIGHT NOW exactly ONE field is unlocked: mission. The mission comes "
    "from the owner and is saved FIRST — the moment their message states "
    "the work they want you to own, call mission_set(statement=...) and "
    "then update_self(field='mission', value=<their words>) BEFORE "
    "writing your reply. Save it AS STATED — no confirmation round. "
    "Every other field is locked and unlocks the moment the mission is "
    "saved; do not ask the owner about any of them yet."
)

UPDATE_SELF_DESC_OPEN = (
    "Save a single piece of your own identity during first-run setup. "
    "NAME and EMOJI come from the owner: ask, never invent them. PERSONA "
    "you write yourself. Required fields: agent_name, emoji, mission, "
    "persona. Optional: owner_name, owner_pronouns, first_work_target, "
    "decision_authority."
)

COMPLETE_SETUP_DESC_GATED = (
    "LOCKED until the mission is saved — calling this now returns an "
    "error. Save the owner's mission first."
)

COMPLETE_SETUP_DESC_OPEN = (
    "Finish first-run setup. Returns an error listing what's missing "
    "while any required field is unsaved. The owner drives the pace of "
    "the checklist — complete only when they have given you the "
    "remaining answers. After this succeeds, your next message MUST "
    "propose a concrete first piece of work."
)

_LOCKED_FIELD_ERROR = {
    "ok": False,
    "error": "locked until the mission is saved",
    "hint": (
        "Save the owner's mission first: mission_set(statement=...), then "
        "update_self(field='mission', value=...). The other setup fields "
        "unlock the moment it is saved — and they come from the owner: "
        "ask, don't invent."
    ),
}

_LOCKED_COMPLETE_ERROR = {
    "ok": False,
    "error": "setup cannot finish: no mission saved yet",
    "hint": (
        "The mission comes from the owner. Ask for it, save it with "
        "mission_set(statement=...) and update_self(field='mission', "
        "value=...), then let the owner give you the rest of the "
        "checklist."
    ),
}


async def _identity_has_mission(sf) -> bool:
    """True when identity.mission is non-empty. A probe failure counts as
    missing — the gate stays closed, which only defers non-mission saves
    by a turn (the same turn would have failed on that DB anyway)."""
    try:
        async with sf() as s:
            row = (
                await s.execute(sa_text("SELECT mission FROM identity LIMIT 1"))
            ).scalar_one_or_none()
    except Exception:  # noqa: BLE001
        return False
    return bool(row and str(row).strip())


def _gate_probe(ctx, get_store: Callable[[], Any]):
    """An async callable answering 'is the mission saved?' — the store first
    (mission_set), the identity row second (update_self bridge)."""
    sf = ctx.db_session_factory

    async def gate_open() -> bool:
        store = get_store()
        if store is not None:
            try:
                if (await store.get()) is not None:
                    return True
            except Exception:  # noqa: BLE001 - fall through to identity probe
                pass
        return await _identity_has_mission(sf)

    return gate_open


def install_setup_gate(ctx, get_store: Callable[[], Any]) -> bool:
    """Wrap plugin_onboarding's update_self/complete_setup with the mission
    gate and set their schema descriptions to the gated (mission-only) text.
    Idempotent (marker attribute on the wrapper); safe to call every turn.
    Returns True when at least one wrapper was (re)installed, False when the
    tools are absent or already gated. sync_gate_descriptions() keeps the
    descriptions matched to the live state afterwards."""
    reg = getattr(ctx, "tool_registry", None)
    if reg is None:
        return False
    try:
        ut = reg.get("update_self")
        ct = reg.get("complete_setup")
    except (KeyError, AttributeError):
        return False

    gate_open = _gate_probe(ctx, get_store)
    installed = False

    if not getattr(ut.handler, _GATE_MARK, False):
        orig_update = ut.handler

        async def update_self_gated(field: str = "", value: str = "", **kw):
            if field not in _MISSION_FIELDS and not await gate_open():
                return dict(_LOCKED_FIELD_ERROR)
            return await orig_update(field=field, value=value, **kw)

        setattr(update_self_gated, _GATE_MARK, True)
        setattr(update_self_gated, "_curiosity_gate_orig", orig_update)
        ut.handler = update_self_gated
        ut.definition.description = UPDATE_SELF_DESC_GATED
        installed = True

    if not getattr(ct.handler, _GATE_MARK, False):
        orig_complete = ct.handler

        async def complete_setup_gated(**kw):
            if not await gate_open():
                return dict(_LOCKED_COMPLETE_ERROR)
            return await orig_complete(**kw)

        setattr(complete_setup_gated, _GATE_MARK, True)
        setattr(complete_setup_gated, "_curiosity_gate_orig", orig_complete)
        ct.handler = complete_setup_gated
        ct.definition.description = COMPLETE_SETUP_DESC_GATED
        installed = True

    return installed


async def sync_gate_descriptions(ctx, get_store: Callable[[], Any]) -> None:
    """Match the two schema descriptions to the live gate state — called on
    every prompt assembly. While the mission is missing the schemas describe
    a mission-only stage; once it's saved the full checklist text returns."""
    reg = getattr(ctx, "tool_registry", None)
    if reg is None:
        return
    try:
        ut = reg.get("update_self")
        ct = reg.get("complete_setup")
    except (KeyError, AttributeError):
        return
    open_ = await _gate_probe(ctx, get_store)()
    ut.definition.description = UPDATE_SELF_DESC_OPEN if open_ else UPDATE_SELF_DESC_GATED
    ct.definition.description = (
        COMPLETE_SETUP_DESC_OPEN if open_ else COMPLETE_SETUP_DESC_GATED
    )


def remove_setup_gate(ctx) -> None:
    """Restore the pristine handlers (plugin unload). Descriptions are left
    rewritten — they are stage-agnostic and the next onboarding reload
    restores the originals anyway."""
    reg = getattr(ctx, "tool_registry", None)
    if reg is None:
        return
    for name in ("update_self", "complete_setup"):
        try:
            rt = reg.get(name)
        except (KeyError, AttributeError):
            continue
        orig = getattr(rt.handler, "_curiosity_gate_orig", None)
        if orig is not None:
            rt.handler = orig
