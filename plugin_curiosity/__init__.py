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

9.002: wiki + scheduler become HARD dependencies (manifest depends_on + a
runtime gate — knowledge lives in wiki pages, drive lives in triggers;
without them curiosity is meaningless, so it goes inert instead of degrading
surface by surface), and the agent's inner workings get an owner-facing
Missions pane (sidebar section + static iframe app served from routes).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from luna_sdk import LunaPlugin, PluginContext, PluginManifest

try:  # cores with plugin-owned panes (the 9.002 target) export it
    from luna_sdk import SidebarSection
except ImportError:  # pragma: no cover - older core: no pane, plugin still loads
    SidebarSection = None

try:  # cores with the skill system (006.0) export it
    from luna_sdk import SkillDef
except ImportError:  # pragma: no cover - older core: tools register ungated
    SkillDef = None

# 0.9.7 (core 034/phase03) feature probe: cores that support prompt-slot
# claims export CLAIMABLE_SOURCES from luna_sdk. Older cores don't — the
# plugin then keeps its legacy append+reorder behavior.
try:
    from luna_sdk import CLAIMABLE_SOURCES  # noqa: F401
    _CLAIMS_SUPPORTED = True
except ImportError:  # pragma: no cover - older core
    _CLAIMS_SUPPORTED = False

from . import (
    abilities,
    comms,
    engine,
    feedback,
    gating,
    goals,
    loops,
    mission,
    research,
    scopes,
    setup_gate,
    telemetry,
)
from .abilities import AbilityStore
from .feedback import FeedbackStore
from .goals import GoalStore
from .loops import LoopStore
from .mission import (
    MISSION_FIRST_NOTE,
    MissionStore,
    prompt_fragment,
    register_tools,
    rewrite_onboarding_addendum,
)
from .models import ALL_TABLES, Flag, apply_additive_migrations
from .scopes import ScopeStore
from .telemetry import HeartbeatStore

log = logging.getLogger("plugin-curiosity")

# Grace period before the on-load schedule sync: on a runtime plugin install
# other plugins (notably plugin-scheduler, whose trigger_* tools the sync
# calls) may still be loading. Tests set this to 0.
SYNC_ON_LOAD_DELAY_S = 15.0

INSTALL_KICKOFF_FLAG = "install_kickoff_sent"

# 9.001G: at most one heartbeat nudge per UTC day — restarts must not turn
# the safety net into a nag.
HEARTBEAT_NUDGE_FLAG = "heartbeat_nudge_date"

# 10.001: one-shot upgrade nudge — a pre-0.9.0 mission has scopes but no
# ability ladder; the nudge tells the agent to derive one from its existing
# scope ledger on the next heartbeat. Never re-sent once flagged.
ABILITY_UPGRADE_FLAG = "ability_upgrade_nudge_sent"

ABILITY_UPGRADE_NUDGE = (
    "[curiosity] Your plugin was upgraded: you now keep a qualification "
    "LADDER — 3-7 abilities ('Ability to …'), each with 2-6 concrete "
    "subtasks, percents computed for you. Your mission predates this: you "
    "have scopes but no ladder. On your NEXT setup-heartbeat fire (or now, "
    "if the owner is around): derive your abilities from [[role-charter]] "
    "and your scope ledger with ability_upsert, attach each scope to its "
    "ability (scope_update ability_id), score the subtasks honestly with "
    "ability_task_set, and draft [[job-description]] if it does not exist. "
    "This is a ladder re-derivation, not new work — do not redo research."
)

# 9.002A: the hard-dependency gate. The manifest's depends_on is enforced by
# the loader only for in-tree strict discovery; managed/marketplace installs
# need this runtime gate. While a dependency is missing curiosity is INERT —
# no tools, no moments, no schedules — and both the owner (pane blocked
# screen) and the agent (paused prompt fragment) can see which and why.
DEPENDENCIES = {
    "plugin-wiki": {
        "probe": "provider:wiki",
        "why": "the wiki is where I keep everything I learn for the mission",
    },
    "plugin-scheduler": {
        "probe": "tool:trigger_create",
        "why": "the scheduler is what lets me act on my own, around the clock",
    },
}

DEPENDENCY_BLOCKED_FLAG = "dependency_blocked"
DEPENDENCY_NOTICE_FLAG = "dependency_blocked_notice"


def missing_dependencies(ctx: PluginContext) -> list[str]:
    """The dependencies whose runtime seams are absent right now."""
    missing: list[str] = []
    for name, spec in DEPENDENCIES.items():
        kind, _, key = spec["probe"].partition(":")
        try:
            if kind == "provider":
                ctx.provider_registry.get(key)
            else:
                ctx.tool_registry.get(key)
        except Exception:  # noqa: BLE001 - any failure to resolve = missing
            missing.append(name)
    return missing


def blocked_fragment(missing: list[str]) -> str:
    """The agent-facing paused note — same legibility bar as the two-phase
    model: the agent can EXPLAIN its own paused state."""
    reasons = "; ".join(
        f"{name} ({DEPENDENCIES[name]['why']})" for name in DEPENDENCIES
    )
    return (
        "Curiosity is installed but PAUSED — it requires " + reasons + ". "
        "Missing right now: " + ", ".join(missing) + ". None of your "
        "curiosity capabilities (missions, research, goals, heartbeat) run "
        "until the missing plugin(s) are installed. If the owner asks about "
        "missions or growth work, say so plainly and point them at the "
        "marketplace to install what's missing."
    )

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

# The loaded plugin instance — lets the on-load work (scheduled from either
# on_load or the routes startup hook) re-evaluate the dependency gate in the
# loop that survives. At in-tree boot curiosity can load BEFORE wiki/scheduler
# (alphabetical), so an on_load-time "blocked" verdict may be a load-order
# race; the serving-loop re-check after SYNC_ON_LOAD_DELAY_S is authoritative.
_plugin: "CuriosityPlugin | None" = None


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


async def _setup_incomplete(sf) -> bool:
    """0.9.13: True while first-run setup is in progress. Raw SQL because the
    SDK exposes no identity accessor. The identity row is created lazily on
    the first turn, so on the table three states matter: no row at all =
    setup never started (fresh install — still in setup), row with
    setup_completed false = mid-setup, row true = done. A failed query (no
    identity table, exotic core) reads as 'not in setup' so the kickoff
    behaves exactly as before."""
    try:
        from sqlalchemy import text as _sql

        async with sf() as s:
            row = (
                await s.execute(_sql("SELECT setup_completed FROM identity LIMIT 1"))
            ).first()
        return row is None or not row[0]
    except Exception:  # noqa: BLE001
        return False


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
    if await _setup_incomplete(sf):
        # 0.9.13: first-run setup owns the mission ask (mission-first flow in
        # the claimed onboarding slot) — a kickoff now would ask twice. Defer
        # WITHOUT setting the flag: it stays armed for a post-setup
        # missionless agent and self-cancels above once a mission exists.
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


async def maybe_nudge_ability_upgrade(
    ctx: PluginContext, store: MissionStore, ability_store: AbilityStore
) -> bool:
    """10.001 upgrade path: active mission + zero abilities → one muted nudge
    (ever) to derive the ladder from the existing scope ledger. Fresh 0.9.0
    missions never hit this — the kickoff creates abilities in the same turn
    the mission lands, before this on-load check can observe zero."""
    sf = ctx.db_session_factory
    if await _flag_get(sf, ABILITY_UPGRADE_FLAG) is not None:
        return False
    if await store.get() is None:
        return False
    listed = await ability_store.list()
    if listed["abilities"]:
        await _flag_set(sf, ABILITY_UPGRADE_FLAG, "skipped: abilities present")
        return False
    if not callable(getattr(ctx, "send_muted_message", None)):
        return False
    result = await ctx.send_muted_message(
        "Your qualification ladder",
        ABILITY_UPGRADE_NUDGE,
        channel="moment",
        source="curiosity",
    )
    if isinstance(result, dict) and result.get("error"):
        log.info("ability upgrade nudge not delivered: %s", result["error"])
        return False
    await _flag_set(sf, ABILITY_UPGRADE_FLAG)
    return True


def schedule_on_load_work(
    ctx: PluginContext,
    store: MissionStore,
    reflections: comms.ReflectionLog,
    scope_store: ScopeStore | None = None,
    loop_store: LoopStore | None = None,
    ability_store: AbilityStore | None = None,
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
        # 9.002A: no owner-facing sends while the dependency gate is (still)
        # closed — the authoritative re-check comes after the sleep.
        if not missing_dependencies(ctx):
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
        # 9.002A: the authoritative gate check — every plugin that will load
        # has loaded by now. Blocked → tell the agent's owner once and do NO
        # other on-load work; satisfied → (late-)activate and continue.
        if _plugin is not None:
            missing = await _plugin.reevaluate_gate(ctx)
            if missing:
                try:
                    await _plugin.maybe_send_blocked_notice(ctx, missing)
                except Exception:  # noqa: BLE001
                    log.warning("dependency-blocked notice failed", exc_info=True)
                return
        try:
            await maybe_send_install_kickoff(ctx, store)
        except Exception:  # noqa: BLE001
            log.warning("install kickoff on load failed", exc_info=True)
        # 0.10.0: goal-engine handover. With goal-seek installed and open
        # internal goals unmigrated, run the one-time pointer conversion —
        # under a single owner approval card; declined/undecided retries on
        # a later load (idempotent). Runs BEFORE the missionless early-return:
        # the migration is about goal rows, which can outlive their mission.
        if (
            _plugin is not None
            and _plugin._goals is not None
            and engine.resolve_goal_engine(ctx) == engine.GOAL_ENGINE_GOALSEEK
        ):
            try:
                result = await goals.migrate_internal_goals(ctx, _plugin._goals)
                if result.get("migrated") or result.get("note") != "nothing to migrate":
                    log.info("goal migration on load: %s", result)
            except Exception:  # noqa: BLE001
                log.warning("goal migration on load failed", exc_info=True)
            # 0.11.0: heal pointers stranded by the engine's own v1 → v2
            # upgrade — still-open goals re-open in v2 and the pointer
            # follows; ended goals become plain history rows. Idempotent.
            try:
                result = await goals.repoint_stale_pointers(ctx, _plugin._goals)
                if result.get("repointed") or result.get("retired"):
                    log.info("pointer repair on load: %s", result)
            except Exception:  # noqa: BLE001
                log.warning("pointer repair on load failed", exc_info=True)
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
        try:
            await research.dedupe_heartbeats(ctx)
        except Exception:  # noqa: BLE001
            log.warning("heartbeat dedupe on load failed", exc_info=True)
        if scope_store is not None:
            try:
                if await maybe_nudge_heartbeat(ctx, scope_store):
                    log.info("setup-heartbeat nudge posted")
            except Exception:  # noqa: BLE001
                log.warning("heartbeat nudge on load failed", exc_info=True)
        if ability_store is not None:
            try:
                if await maybe_nudge_ability_upgrade(ctx, store, ability_store):
                    log.info("ability upgrade nudge posted")
            except Exception:  # noqa: BLE001
                log.warning("ability upgrade nudge on load failed", exc_info=True)

    # keep a strong ref — the loop itself only holds weak refs to tasks, and
    # a task sleeping through boot would otherwise be GC-able mid-flight
    _onload["task"] = loop.create_task(_run())


# 0.9.7 (core 034/phase03): declared prompt-slot claims — core.drive (the
# curiosity fragment replaces the default drive slot) and core.onboarding
# (mission-first ordering written into the setup checklist itself). Passed
# only where PluginManifest knows the field, so older cores load unchanged.
# Mirrored in luna-plugin.toml [prompt] for the install-time consent card.
_manifest_extra: dict = {}
if "prompt_overrides" in getattr(PluginManifest, "model_fields", {}):
    _manifest_extra["prompt_overrides"] = ["core.drive", "core.onboarding"]


class CuriosityPlugin(LunaPlugin):
    manifest = PluginManifest(
        name="plugin-curiosity",
        version="0.11.0",
        description=(
            "Mission-driven curiosity: research, wiki-building, nightly dreams, "
            "self-set goals, weekly mission reviews, proactive reflections, and "
            "a Missions pane that makes the agent's inner workings visible."
        ),
        capabilities=["wiki"],
        # 9.002A: hard by design — knowledge lives in wiki pages, drive lives
        # in triggers. The loader enforces this for in-tree loads only; the
        # runtime gate (missing_dependencies) covers managed installs.
        depends_on=["plugin-wiki", "plugin-scheduler"],
        db_tables=[t.name for t in ALL_TABLES],
        routes_module="routes",
        # 0.9.5: ONE sidebar entry. The operations wall (ex-NOC) lives inside
        # the Missions pane as its second tab ("Operational dashboard"),
        # embedded from ui/noc/ — the noc/ directory keeps its URL so old
        # deep links and the embed share one document.
        # 0.9.13: labeled "Curiosity", right under Chat (10) and ahead of
        # Playbooks (25) — the mission is the agent's core.
        sidebar_sections=(
            [SidebarSection(id="missions", label="Curiosity", icon="target", sort_order=15)]
            if SidebarSection is not None
            else []
        ),
        **_manifest_extra,
    )

    def __init__(self) -> None:
        self._store: MissionStore | None = None
        self._goals: GoalStore | None = None
        self._scopes: ScopeStore | None = None
        self._loops: LoopStore | None = None
        self._abilities: AbilityStore | None = None
        self._heartbeats: HeartbeatStore | None = None
        self._feedback: FeedbackStore | None = None
        self._reflections: comms.ReflectionLog | None = None
        self._ctx: PluginContext | None = None
        self._activated = False
        # None = gate not yet evaluated; [] = satisfied; [names] = blocked
        self._missing: list[str] | None = None

    async def on_load(self, ctx: PluginContext) -> None:
        global _plugin
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
        self._abilities = AbilityStore(ctx.db_session_factory)
        self._heartbeats = HeartbeatStore(ctx.db_session_factory)
        self._feedback = FeedbackStore(ctx.db_session_factory)
        self._reflections = comms.ReflectionLog(ctx.db_session_factory)
        self._ctx = ctx
        _plugin = self
        # 9.002A: the dependency gate. Satisfied → activate now (tools, hooks
        # — the normal path for runtime installs, whose deps are long loaded).
        # Missing → stay INERT; the serving-loop on-load work re-checks after
        # the settle delay (in-tree boot can load curiosity before its deps)
        # and either late-activates or posts the one-time blocked notice.
        missing = await self.reevaluate_gate(ctx)
        if missing:
            log.warning(
                "plugin-curiosity INERT — missing dependencies %s (re-check in %ss)",
                missing,
                SYNC_ON_LOAD_DELAY_S,
            )
        schedule_on_load_work(
            ctx,
            self._store,
            self._reflections,
            self._scopes,
            self._loops,
            self._abilities,
        )

    async def reevaluate_gate(self, ctx: PluginContext) -> list[str]:
        """Check the hard dependencies; (late-)activate when satisfied.
        Returns the currently missing dependency names ([] = running)."""
        missing = missing_dependencies(ctx)
        self._missing = missing
        try:
            await _flag_set(
                ctx.db_session_factory,
                DEPENDENCY_BLOCKED_FLAG,
                ",".join(missing),
            )
        except Exception:  # noqa: BLE001 - the flag is advisory, never fatal
            log.debug("dependency_blocked flag write failed", exc_info=True)
        if not missing and not self._activated:
            self._activate(ctx)
        return missing

    def _activate(self, ctx: PluginContext) -> None:
        """Register the plugin's live surface — tools + prompt hook. Runs
        exactly once, and only with the dependency gate open."""
        self._activated = True
        # 0.9.6: sweep our own stale registrations first. A hot upgrade/install
        # whose teardown missed (or raced) leaves the previous instance's tools
        # in the registry under this same plugin name — the collision guard
        # would then kill THIS on_load and the rollback's alike, bricking every
        # further update until a restart. Same-name sweep is always safe:
        # whatever is there under "plugin-curiosity" is a dead instance's.
        unreg = getattr(ctx.tool_registry, "unregister_plugin", None)
        if callable(unreg):
            try:
                unreg("plugin-curiosity")
            except Exception:  # noqa: BLE001
                log.warning("stale-tool sweep failed", exc_info=True)
        register_tools(ctx, self._store)
        goals.register_tools(ctx, self._goals, mission_store=self._store)
        scopes.register_tools(ctx, self._scopes)
        loops.register_tools(ctx, self._loops)
        abilities.register_tools(ctx, self._abilities)
        comms.register_tools(ctx, self._reflections)
        telemetry.register_tools(ctx, self._heartbeats)
        feedback.register_tools(ctx, self._feedback)
        # 0.9.14: the mission gate, tool layer — the dojo caught the blitz
        # surviving the prompt-only gate (the tool schemas still advertised
        # complete_setup + every field). Wrap plugin_onboarding's handlers:
        # while the mission is missing, update_self takes only the mission
        # and complete_setup refuses. Load order may put onboarding after
        # us — the per-turn reinstall in _occupy_prompt converges it.
        setup_gate.install_setup_gate(ctx, lambda: self._store)
        self._register_skill(ctx)
        self._register_config_section(ctx)
        # 8.1B → 0.9.7: prompt primacy. On claim cores (034/phase03) the
        # handler OCCUPIES the claimed core.drive slot and writes the
        # mission-first note into the claimed onboarding addendum; on older
        # cores it falls back to the legacy append+reorder position fix.
        # Feature-detected: cores without the hook keep the appended position.
        hooks = getattr(ctx, "hooks", None)
        if hooks is not None:
            try:
                hooks.register("prompt.assemble", self._occupy_prompt, priority=60)
            except Exception:  # noqa: BLE001
                log.warning("prompt.assemble registration failed", exc_info=True)
        log.info("plugin-curiosity loaded (tools=23)")

    def _register_config_section(self, ctx: PluginContext) -> None:
        """0.10.0 (phase-05 pattern, proven in goal-seek): a tiny read-only
        config section so the agent can answer "which goal engine is
        curiosity using?" via manage_config — no bespoke tool. Duck-typed
        (luna_sdk doesn't export ConfigSection; the registry reads
        attributes); older cores without the seam skip it."""
        register = getattr(ctx, "register_config_section", None)
        if not callable(register):
            return

        from dataclasses import dataclass, field
        from typing import Any as _Any

        @dataclass
        class _Section:
            id: str
            label: str
            description: str
            reader: _Any
            writer: _Any
            schema: _Any
            plugin: str = "plugin-curiosity"
            readonly_fields: list = field(default_factory=list)

        async def _read() -> dict:
            return {"goal_engine": engine.resolve_goal_engine(ctx)}

        async def _write(changes: dict) -> dict:
            return {
                "error": (
                    "goal_engine is resolved from what's installed (goal-seek "
                    "present → 'goalseek'), not set by hand — install or remove "
                    "plugin-goalseek to change it"
                )
            }

        try:
            register(
                _Section(
                    id="curiosity",
                    label="Curiosity",
                    description=(
                        "Curiosity's runtime wiring. goal_engine says where "
                        "mission goals live: 'goalseek' (the governed Goal-Seek "
                        "engine — Goals pane, policies, heartbeats) or "
                        "'internal' (curiosity's own ledger). Read-only."
                    ),
                    reader=_read,
                    writer=_write,
                    schema=lambda: {
                        "goal_engine": {
                            "type": "string",
                            "enum": ["internal", "goalseek"],
                            "readonly": True,
                            "description": "Resolved from installed plugins.",
                        }
                    },
                    readonly_fields=["goal_engine"],
                )
            )
        except Exception:  # noqa: BLE001 — a registry quirk must not fail activate
            log.warning("curiosity config section registration failed", exc_info=True)

    def _register_skill(self, ctx: PluginContext) -> None:
        """0.9.12: the mission-changes skill. Its three tools (gating.GATED_TOOLS)
        each fire a handful of times over a mission's life — their schemas ride
        behind this skill instead of every turn's prompt. Older cores (no skill
        registry / no SkillDef) register the tools ungated via gating.register_tool,
        so nothing is ever hidden without a skill to unlock it."""
        reg = getattr(ctx, "skill_registry", None)
        if reg is None or SkillDef is None:
            return
        unreg = getattr(reg, "unregister_plugin", None)
        if callable(unreg):  # same stale-sweep rationale as the tool sweep above
            try:
                unreg("plugin-curiosity")
            except Exception:  # noqa: BLE001
                log.warning("stale-skill sweep failed", exc_info=True)
        try:
            reg.register(
                "plugin-curiosity",
                SkillDef(
                    name=gating.SKILL_NAME,
                    description=(
                        "Big mission changes — reword the mission, move between "
                        "setup and work phases (graduation), or repair mission "
                        "schedules. Load this the turn BEFORE you need the tools."
                    ),
                    body=(
                        "These tools change your mission's plan of record. They "
                        "unlock on your NEXT turn after loading this skill — load "
                        "it as soon as you see the change coming, not at the "
                        "moment you need it.\n\n"
                        "- mission_refine: reword the active mission statement or "
                        "adjust autonomy rung / risk ceiling. Use mission_set for "
                        "a genuinely new mission.\n"
                        "- phase_advance: move between setup and work phase. "
                        "to='work' proposes graduation (every scope ready, or "
                        "explicitly waived); to='setup' is always allowed.\n"
                        "- mission_schedules_sync: verify and restore your "
                        "recurring mission schedules when an audit shows triggers "
                        "missing or drifted. Never hand-craft trigger_create "
                        "calls for your own mission schedules.\n\n"
                        "Day-to-day tools (plan_change_note, stage_set, scope/"
                        "goal/loop tools) are always available and do not need "
                        "this skill."
                    ),
                    tools=list(gating.GATED_TOOLS),
                ),
            )
        except Exception:  # noqa: BLE001
            log.warning("mission-changes skill registration failed", exc_info=True)

    async def maybe_send_blocked_notice(
        self, ctx: PluginContext, missing: list[str]
    ) -> bool:
        """One muted heads-up per distinct missing-set — the chat-side mirror
        of the pane's blocked screen, so an owner who never opens the pane
        still learns why curiosity is dark."""
        if not callable(getattr(ctx, "send_muted_message", None)):
            return False
        sf = ctx.db_session_factory
        key = ",".join(sorted(missing))
        if await _flag_get(sf, DEPENDENCY_NOTICE_FLAG) == key:
            return False
        result = await ctx.send_muted_message(
            "Curiosity is paused",
            blocked_fragment(missing)
            + " Tell the owner in one short line, in your own voice: which "
            "plugin(s) are missing, what each one is to you, and that "
            "installing them from the marketplace un-pauses you.",
            channel="moment",
            source="curiosity",
        )
        if isinstance(result, dict) and result.get("error"):
            log.info("blocked notice not delivered: %s", result["error"])
            return False
        await _flag_set(sf, DEPENDENCY_NOTICE_FLAG, key)
        return True

    async def _occupy_prompt(self, hctx) -> None:
        """prompt.assemble handler (0.9.7, core 034/phase03). On claim cores
        the manifest claims core.drive + core.onboarding: the curiosity
        fragment REPLACES the core drive slot (exactly one drive section, no
        duplicate appended fragment), and while missionless the mission-first
        ordering is prepended to the onboarding addendum itself — no 'this
        note OVERRIDES its ordering' prose, no position hack. Older cores
        (luna_sdk without CLAIMABLE_SOURCES) keep the legacy reorder path."""
        # 0.9.14: re-converge the tool-layer mission gate every assembly — a
        # plugin_onboarding hot reload re-registers the pristine handlers,
        # and load order may have beaten _activate to the registry.
        if self._ctx is not None:
            try:
                setup_gate.install_setup_gate(self._ctx, lambda: self._store)
                await setup_gate.sync_gate_descriptions(self._ctx, lambda: self._store)
            except Exception:  # noqa: BLE001 - the gate is best-effort here
                log.debug("setup gate reinstall failed", exc_info=True)
        if not _CLAIMS_SUPPORTED:
            await self._reorder_prompt(hctx)
            return
        if self._store is None or self._missing:
            return  # never occupy the drive slot with the paused note
        secs = hctx.sections
        own = [s for s in secs if getattr(s, "source", "") == "plugin-curiosity"]
        if not own:
            return
        if not any(getattr(s, "source", "") == "core.drive" for s in secs):
            # No named drive slot (owner monolith override, pre-split core):
            # nothing to occupy — legacy position fix still applies.
            await self._reorder_prompt(hctx)
            return
        frag = own[0]
        for s in own:
            secs.remove(s)
        idx = next(
            i for i, s in enumerate(secs) if getattr(s, "source", "") == "core.drive"
        )
        secs[idx] = frag  # swap: claimed drop of core.drive + own-source insert
        secs[idx + 1 : idx + 1] = own[1:]
        if (await self._store.get()) is not None:
            return
        for s in secs:
            if getattr(s, "source", "") == "core.onboarding":
                # 0.9.13 (luna 036: the claim binds to the LIVE addendum):
                # rewrite the flow to mission-first, preserving the live
                # SETUP STATE block; unknown addendum shape → prepend note.
                rewritten = rewrite_onboarding_addendum(s.text)
                if rewritten is not None:
                    s.text = rewritten
                else:
                    s.text = MISSION_FIRST_NOTE + "\n\n" + s.text
                break

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
        # 9.002A: while the dependency gate is closed, the ONLY fragment is
        # the paused note — the agent knows it's paused and can explain why.
        if self._missing:
            return [blocked_fragment(self._missing)]
        if not self._activated:
            return []
        mission = await self._store.get()
        phase = None
        if mission is not None and self._scopes is not None:
            state = await self._scopes.state()
            phase = state["agent_phase"] if state else None
        sections = [prompt_fragment(mission, phase, slot_mode=_CLAIMS_SUPPORTED)]
        # 0.10.0: with the goal engine flipped, say so — the agent must know
        # its goals live in goal-seek (stages/policies, the Goals pane) and
        # that goal_set still adds mission membership on top of the open.
        if (
            mission is not None
            and getattr(self, "_ctx", None) is not None
            and engine.resolve_goal_engine(self._ctx) == engine.GOAL_ENGINE_GOALSEEK
        ):
            sections.append(
                "Your goal engine is Goal-Seek: mission goals live in its "
                "governed engine (stages, policies, heartbeats — the owner "
                "sees them in the Goals pane). goal_set still opens MISSION "
                "goals (it delegates and keeps mission membership); "
                "goal_update / goal_list are Goal-Seek's own tools — use "
                "goal_id (not id), goal_close (not status='done') to end a "
                "goal, and goal_fact_set / goal_note to record what you learn."
            )
        return sections
