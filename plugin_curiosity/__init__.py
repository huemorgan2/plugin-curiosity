"""plugin-curiosity — mission-driven curiosity for Luna.

The behavior plugin: give Luna a mission and she teaches herself the domain —
researching, filling her wiki (plugin-wiki), dreaming nightly to consolidate,
committing to goals she scores in a weekly review, and proactively sharing
grounded reflections. Consumes the "wiki" provider. Authored against
`luna_sdk` only.

8.1: installing the plugin visibly changes the agent NOW — a one-time install
kickoff moment asks for a mission, and (on cores with the prompt.assemble
hook) the missionless fragment is moved ABOVE the onboarding addendum so the
mission ask outranks the setup checklist by position, not just persuasion.

9.001: the phase-one doctrine (am I qualified? do I know what success looks
like?) frames every setup surface; the agent authors its OWN setup heartbeat
trigger; the on-load safety net notices a setup-phase mission with no
heartbeat and nudges — it never creates the trigger itself.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from luna_sdk import LunaPlugin, PluginContext, PluginManifest

from . import comms, goals, loops, mission, research, scopes
from .goals import GoalStore
from .loops import LoopStore
from .mission import MissionStore, prompt_fragment, register_tools
from .models import ALL_TABLES, Flag, apply_additive_migrations
from .scopes import ScopeStore

log = logging.getLogger("plugin-curiosity")

# Grace period before the on-load schedule sync: on a runtime plugin install
# other plugins (notably plugin-scheduler, whose trigger_* tools the sync
# calls) may still be loading. Tests set this to 0.
SYNC_ON_LOAD_DELAY_S = 15.0

INSTALL_KICKOFF_FLAG = "install_kickoff_sent"

# 9.001G: at most one heartbeat nudge per UTC day — restarts must not turn
# the safety net into a nag.
HEARTBEAT_NUDGE_FLAG = "heartbeat_nudge_date"

# In-process claim for the install kickoff. The on-load work can run twice in
# one process (bootstrap loop + serving loop), and the DB flag is only written
# AFTER a delivered send — QA caught the two runs interleaving in that window
# and posting the moment twice. The claim's check-and-set has no await between
# check and set, so on a single thread exactly one runner wins; the claim is
# released only on a failed send so a later load can retry.
_kickoff_claimed = False

# Loop-identity guard for the one-time on-load work. Under `luna serve` the
# plugin's on_load runs inside a throwaway bootstrap loop (asyncio.run in
# cli.py) — tasks created there die when that loop is disposed — and the
# routes startup hook is what lands in uvicorn's serving loop. On a runtime
# plugin install the serving loop is already started (the startup hook never
# fires) and the on_load call lands. Keying the guard on the loop lets both
# call sites schedule safely: the second call on the SAME loop is a no-op,
# while a fresh loop (the real serving loop after bootstrap) runs the work.
_onload: dict = {"loop": None, "task": None}


async def _flag_get(sf, key: str) -> str | None:
    async with sf() as s:
        row = await s.get(Flag, key)
        return row.value if row is not None else None


async def _flag_set(sf, key: str, value: str = "1") -> None:
    async with sf() as s:
        row = await s.get(Flag, key)
        if row is None:
            s.add(Flag(key=key, value=value))
        else:
            row.value = value
        await s.commit()


async def maybe_send_install_kickoff(ctx: PluginContext, store: MissionStore) -> bool:
    """8.1C: once ever — if the plugin loads with no mission and the kickoff
    was never sent, post the install-kickoff moment (the agent introduces its
    new capability and asks for a mission NOW). The flag is set only after a
    successful send, so a core without send_muted_message (or a send that
    dies with the bootstrap loop) retries on the next load."""
    sf = ctx.db_session_factory
    if await _flag_get(sf, INSTALL_KICKOFF_FLAG) is not None:
        return False
    if await store.get() is not None:
        # a mission already exists — the ask is moot, never send
        await _flag_set(sf, INSTALL_KICKOFF_FLAG, "skipped: mission present")
        return False
    if not callable(getattr(ctx, "send_muted_message", None)):
        return False
    global _kickoff_claimed
    if _kickoff_claimed:
        return False
    _kickoff_claimed = True
    if not await research.run_install_kickoff(ctx):
        _kickoff_claimed = False
        return False  # e.g. zero conversations on a fresh install — retry later
    await _flag_set(sf, INSTALL_KICKOFF_FLAG)
    log.info("install kickoff moment posted")
    return True


async def maybe_nudge_heartbeat(ctx: PluginContext, scope_store: ScopeStore) -> bool:
    """9.001G: mission in setup phase + no self-authored heartbeat trigger →
    post a muted nudge telling the agent to create one (the net reminds; it
    NEVER creates the trigger — the heartbeat must stay agent-authored).
    Skips when the scheduler can't be consulted (None from heartbeat_exists)
    and throttles to one nudge per UTC day."""
    state = await scope_store.state()
    if state is None or state.get("agent_phase") != "setup":
        return False
    if await research.heartbeat_exists(ctx) is not False:
        return False  # exists, or unknowable — either way, no nudge
    if not callable(getattr(ctx, "send_muted_message", None)):
        return False
    sf = ctx.db_session_factory
    today = datetime.now(UTC).date().isoformat()
    if await _flag_get(sf, HEARTBEAT_NUDGE_FLAG) == today:
        return False
    if not await research.run_heartbeat_nudge(ctx):
        return False
    await _flag_set(sf, HEARTBEAT_NUDGE_FLAG, today)
    return True


def schedule_on_load_work(
    ctx: PluginContext,
    store: MissionStore,
    reflections: comms.ReflectionLog,
    scope_store: ScopeStore | None = None,
    loop_store: LoopStore | None = None,
) -> None:
    """Schedule the one-time on-load work on the current loop: drain any
    overnight-queued thoughts, send the one-time install kickoff if the loop
    is still missionless (8.1C), then refresh the mission's recurring triggers
    (a plugin upgrade that changes a trigger target or fire time must reach
    an existing mission without waiting for a mission_set/mission_refine) and
    seed the [[role-charter]] mirror for a pre-9A mission (9A upgrade path)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _onload["loop"] is loop:
        return
    _onload["loop"] = loop

    async def _run() -> None:
        try:
            result = await comms.drain_queue(ctx, reflections)
            if result.get("drained"):
                log.info("drained %s queued thought(s) on load", result["drained"])
        except Exception:  # noqa: BLE001
            log.warning("queued-thought drain on load failed", exc_info=True)
        # The sleep does double duty: it lets late-loading plugins settle AND
        # it outlives the throwaway bootstrap loop — a _run() scheduled there
        # is cancelled HERE, before the kickoff send, instead of dying mid-send
        # with the moment posted but no reaction/flag (QA run 2). Only the
        # serving-loop task reaches the send.
        await asyncio.sleep(SYNC_ON_LOAD_DELAY_S)
        try:
            await maybe_send_install_kickoff(ctx, store)
        except Exception:  # noqa: BLE001
            log.warning("install kickoff on load failed", exc_info=True)
        try:
            if await store.get() is None:
                return  # no mission — mission_set will register schedules
            result = await mission._sync_schedules(ctx)
            if result != "already registered":
                log.info("schedule sync on load: %s", result)
        except Exception:  # noqa: BLE001
            log.warning("schedule sync on load failed", exc_info=True)
        if scope_store is not None:
            try:
                result = await scopes.ensure_charter_mirror(ctx, scope_store)
                if result not in ("already present", "no mission"):
                    log.info("charter mirror seed on load: %s", result)
            except Exception:  # noqa: BLE001
                log.warning("charter mirror seed on load failed", exc_info=True)
        if loop_store is not None:
            try:
                result = await loops.ensure_loop_mirrors(ctx, loop_store)
                if result not in ("already present", "no mission"):
                    log.info("loop mirrors seed on load: %s", result)
            except Exception:  # noqa: BLE001
                log.warning("loop mirrors seed on load failed", exc_info=True)
        try:
            result = await mission.ensure_success_criteria_page(ctx, store)
            if result not in ("already present", "no mission"):
                log.info("success-criteria seed on load: %s", result)
        except Exception:  # noqa: BLE001
            log.warning("success-criteria seed on load failed", exc_info=True)
        if scope_store is not None:
            try:
                if await maybe_nudge_heartbeat(ctx, scope_store):
                    log.info("setup-heartbeat nudge posted")
            except Exception:  # noqa: BLE001
                log.warning("heartbeat nudge on load failed", exc_info=True)

    # keep a strong ref — the loop itself only holds weak refs to tasks, and
    # a task sleeping through boot would otherwise be GC-able mid-flight
    _onload["task"] = loop.create_task(_run())


class CuriosityPlugin(LunaPlugin):
    manifest = PluginManifest(
        name="plugin-curiosity",
        version="0.7.1",
        description=(
            "Mission-driven curiosity: research, wiki-building, nightly dreams, "
            "self-set goals, weekly mission reviews, proactive reflections."
        ),
        capabilities=["wiki"],
        db_tables=[t.name for t in ALL_TABLES],
        routes_module="routes",
    )

    def __init__(self) -> None:
        self._store: MissionStore | None = None
        self._goals: GoalStore | None = None
        self._scopes: ScopeStore | None = None
        self._loops: LoopStore | None = None
        self._reflections: comms.ReflectionLog | None = None

    async def on_load(self, ctx: PluginContext) -> None:
        async with ctx.engine.begin() as conn:
            for table in ALL_TABLES:
                await conn.run_sync(table.create, checkfirst=True)
            added = await conn.run_sync(apply_additive_migrations)
            if added:
                log.info("additive migration: added mission columns %s", added)
        self._store = MissionStore(ctx.db_session_factory)
        self._goals = GoalStore(ctx.db_session_factory)
        self._scopes = ScopeStore(ctx.db_session_factory)
        self._loops = LoopStore(ctx.db_session_factory)
        self._reflections = comms.ReflectionLog(ctx.db_session_factory)
        register_tools(ctx, self._store)
        goals.register_tools(ctx, self._goals)
        scopes.register_tools(ctx, self._scopes)
        loops.register_tools(ctx, self._loops)
        comms.register_tools(ctx, self._reflections)
        self._ctx = ctx
        # 8.1B: prompt primacy — on cores with the prompt.assemble hook, a
        # missionless agent gets the curiosity fragment moved ABOVE the
        # onboarding addendum. Feature-detected: older cores simply keep the
        # appended-fragment position.
        hooks = getattr(ctx, "hooks", None)
        if hooks is not None:
            try:
                hooks.register("prompt.assemble", self._reorder_prompt, priority=60)
            except Exception:  # noqa: BLE001
                log.warning("prompt.assemble registration failed", exc_info=True)
        schedule_on_load_work(
            ctx, self._store, self._reflections, self._scopes, self._loops
        )
        log.info("plugin-curiosity loaded (tools=19)")

    async def _reorder_prompt(self, hctx) -> None:
        """prompt.assemble handler: while MISSIONLESS, move this plugin's own
        section(s) to immediately AFTER the onboarding addendum, so the
        mission-first override is the last word on the setup flow it
        contradicts (the addendum is a plugin-onboarding section near the END
        of the prompt — recency is what wins there, not primacy; QA showed a
        fragment moved earlier LOSES to the checklist). No onboarding section
        → leave order alone (appended-at-end is already maximal recency).
        With a mission set: leave order alone."""
        if self._store is None or (await self._store.get()) is not None:
            return
        secs = hctx.sections
        own = [s for s in secs if getattr(s, "source", "") == "plugin-curiosity"]
        if not own:
            return
        idx = max(
            (
                i
                for i, s in enumerate(secs)
                if getattr(s, "source", "") in ("plugin-onboarding", "core.onboarding")
            ),
            default=None,
        )
        if idx is None:
            return
        anchor = secs[idx]
        for s in own:
            secs.remove(s)
        pos = secs.index(anchor) + 1
        secs[pos:pos] = own

    async def prompt_sections(self) -> list[str]:
        if self._store is None:
            return []
        mission = await self._store.get()
        phase = None
        if mission is not None and self._scopes is not None:
            state = await self._scopes.state()
            phase = state["agent_phase"] if state else None
        return [prompt_fragment(mission, phase)]
