"""research.py — the daytime learning loop, on the right primitives.

Two trigger paths, no asyncio loop, no research tool-wrapper:

1. **Kickoff (immediate, plugin-driven).** `run_kickoff` posts a *moment*
   (`send_muted_message(channel="moment", source="curiosity", tools=...)`)
   whose reaction turn does the first research pass and replies with the
   Mission Kickoff artifact — value visible in the very first session.
   mission.py fires it with `asyncio.create_task` so `mission_set` returns
   immediately.

2. **Recurring (scheduler-fired).** `DAILY_RESEARCH_TARGET` is the
   `agent_prompt` target of the `curiosity-daily-research` trigger. The fired
   turn has the full registered toolset (chat_only excluded by the runtime),
   so the instructions can use web_*, wiki_* and share_thought directly. The
   prompt re-reads the CURRENT mission at fire time via mission_get, so
   refining the mission never requires re-syncing the trigger.
"""

from __future__ import annotations

import asyncio
import logging

from luna_sdk import PluginContext

from .prompts import (
    ASK_SHAPE,
    CANONICAL_EXAMPLE,
    HEARTBEAT_CONTRACT,
    HEARTBEAT_NAME,
    LOOP_DISCIPLINE,
    NEXT_TOUCH_RULE,
    PHASE_CHECK,
    PHASE_ONE_DOCTRINE,
    RATIFICATION_FORCING,
    SETUP_STAGE_DEFS,
    TALENTED_HIRE_LAW,
)

log = logging.getLogger("plugin-curiosity")

# Allowlist for the kickoff reaction turn. share_thought is deliberately
# absent: the kickoff reply IS the visible artifact — a same-moment
# share_thought would double-post. playbook_* are chat_only and unavailable
# in muted reaction turns regardless.
KICKOFF_TOOLS = [
    "mission_get",
    "web_search",
    "web_fetch",
    "wiki_toc",
    "wiki_read",
    "wiki_search",
    "wiki_write",
    "wiki_patch",
    "wiki_cite",
    "wiki_ask",
    "wiki_list_questions",
    # 8.2: goals are committed IN the kickoff; the capability/reach scan uses
    # marketplace + channel-status tools when their plugins are installed
    # (absent names are simply not in the reaction turn's toolset — harmless).
    "goal_set",
    "goal_list",
    "marketplace_search",
    "wa_status",
    "connector_list_connected",
    # 9C: the kickoff IS the setup arc's S0→S2 — it charters scopes, opens
    # loops for its own questions, logs first value, and stamps the stage.
    "scope_set",
    "scope_update",
    "scope_list",
    "stage_set",
    "loop_open",
    "loop_list",
    "value_log_add",
    # 9.001C: the kickoff ends with the agent creating its OWN setup
    # heartbeat (a self-authored recurring trigger — trigger_create is
    # auto_approve and provided by plugin-scheduler; absent name is harmless
    # if the scheduler isn't installed).
    "trigger_create",
    "trigger_list",
]

KICKOFF_TITLE = "Mission kickoff"

# breathing room so the mission_set turn finishes streaming before the
# kickoff reaction turn starts competing for the loop (tests set this to 0)
KICKOFF_DELAY_S = 3.0

# the kickoff turn is the ONLY driver of the S0→S2 arc; if it dies to a
# transient model-API failure the owner silently never gets a charter. Retry
# with real spacing (tests set the delay to 0).
KICKOFF_ATTEMPTS = 3
KICKOFF_RETRY_S = 90.0

_KICKOFF_CONTENT = (
    """\
Your mission was just set: {statement}

You are in SETUP phase, stage S0 — the setup arc starts NOW, in this turn
(S0→S2, ~14-18 tool calls; depth comes later, from your own heartbeat and
the daily schedule).
"""
    + PHASE_ONE_DOCTRINE
    + "\n"
    + SETUP_STAGE_DEFS
    + "\n"
    + TALENTED_HIRE_LAW
    + """

S0 — understand it sharper than you were told:
1. Restate the mission SHARPER than the owner said it — one line; it heads
   your charter.
2. Shallow research only: 2-3 web_search, web_fetch the 1-2 most substantive
   hits; record 2-3 NON-OBVIOUS observations on [[mission-domain]]
   (wiki_patch + wiki_cite — no uncited claims).
3. Write [[success-criteria]] (wiki_write): what success looks like — your
   job expectations, what will make the owner call you successful — from the
   mission plus what you just learned. 3-6 concrete criteria, owner-checkable.
   This page is ratified WITH your charter; goals must trace to it.
4. Ask ONLY plan-changing questions (would the answer change your plan? if
   not, don't ask) — and if the owner's expectations are genuinely unclear,
   ONE of them is about what success looks like. Open each one as a loop —
   loop_open(kind='question'), stating what it unblocks — and record it with
   wiki_ask. ZERO access asks in this turn.

S1 — inventory what you can reach, deliver first value:
5. Charter your scopes with scope_set — every area you must become competent
   in, covering ALL seven kinds (knowledge, people, communication_paths,
   tools_data_access, workflow_approval, playbooks, routines_feedback).
   These scopes ARE your qualification inventory — the live answer to
   question (1).
6. Inventory what you can use TODAY: marketplace_search 1-2 mission keywords;
   wa_status / connector_list_connected for off-platform reach — skip
   silently if a tool isn't available. scope_update anything you verified.
7. First value pass with those alone. """
    + CANONICAL_EXAMPLE
    + """. Timebox: shallow, redirectable passes — stub/summary wiki depth
   only, NO deep corpus until the owner ratifies this charter. value_log_add
   anything real you delivered (evidence: the wiki page).

S2 — charter, success, and your own drive:
8. COMMIT to 5-8 dated goals with goal_set — together they must cover EVERY
   scope, and each must trace to a criterion on [[success-criteria]] (a goal
   that serves no success criterion is scope creep — cut it). They form a
   timeline, not a wish list.
9. Ensure your OWN setup heartbeat exists: trigger_list first — if you
   already created it (e.g. while adopting the mission), leave it; else
   create it NOW with trigger_create. """
    + HEARTBEAT_CONTRACT
    + " "
    + NEXT_TOUCH_RULE
    + """
10. stage_set('S2'), then reply with the **Mission Kickoff** artifact:
   - **Brief** — the mission in your own words, sharper.
   - **What I found** — the 2-3 non-obvious observations, with sources.
   - **What success looks like** — the essentials of [[success-criteria]],
     in the owner's terms.
   - **My charter** — the scopes by kind ([[role-charter]]).
   - **My goals** — the dated timeline: "by <date>: <goal>", 5-8 entries.
   - **Where I am** — phase: setup, stage S2 — then the gap list: what still
     stands between you and qualified, short and honest.
   - **Access plan** — ranked by unlock-per-human-cost. You will ask for AT
     MOST ONE at a time, later, riding on delivered value — the shape is
     always """
    + ASK_SHAPE
    + """.
   - **Open questions** — the plan-changing ones (each already a loop).
   - **Next move** — ONE concrete action YOU will take. End with "say go and
     I'll do it" (needs owner) or "already scheduled — my heartbeat drives
     the rest" (doesn't). NEVER end on a list of suggestions for the owner
     to do.
   Close the artifact with: "this is my charter and my definition of
   success — ratify them or push back now; your ratification moves me to
   S3."
"""
)

DAILY_RESEARCH_TARGET = (
    "[curiosity] Daily pass. You OWN this mission — one focused pass "
    "(~10 tool calls). " + PHASE_CHECK + "\n"
    "0. LOOP PATROL (both phases), before anything else: loop_list your open "
    "loops. For each loop past its next_nudge_at, act NOW — re-ask it "
    "REPHRASED, naming the goal it blocks (then loop_nudge it); or try a "
    "connected channel; or propose a sensible default; or close it with an "
    "explicit assumption (loop_close, with the reason). UNUSED-GRANT CHECK: "
    "an answered ask whose grant has no value_log entry yet is a broken "
    "promise — use the grant and value_log_add the win (linked_ask_id) "
    "TODAY. BACKFILL CHECK: a request you already voiced (chat, pending "
    "credential form, connector setup) with NO loop tracking it gets "
    "loop_open(kind='ask', unlock=..., value_ref=...) RIGHT NOW. "
    + LOOP_DISCIPLINE + "\n"
    "SETUP BRANCH (agent_phase='setup'): you are QUALIFYING yourself for "
    "this job — every action today closes a named gap: which tools, access, "
    "people, or knowledge am I missing? do I know what success looks like "
    "([[success-criteria]])?\n"
    "1. mission_get, then goal_list. CONFRONT overdue goals first: anything "
    "past its target date gets replanned, escalated, or dropped TODAY "
    "(goal_update with the reason) — never carried silently. "
    + RATIFICATION_FORCING + " Also trigger_list: if your own "
    "'" + HEARTBEAT_NAME + "' trigger is missing, recreate it per your "
    "heartbeat contract BEFORE anything else.\n"
    "2. Pick the ONE goal you can advance TODAY and advance it with a small "
    "S1-style value pass: web_search / web_fetch, record on the wiki "
    "(wiki_write/wiki_patch + wiki_cite), stub/summary depth until the "
    "charter is ratified. scope_update the scope it grew, with evidence.\n"
    "3. EVENT-DRIVEN REPLAN: if today's learning changes the plan, change "
    "the plan TODAY (plan_change_note + scope_set/goal_set), not at the "
    "weekly. A plan that never changes after week 1 means you stopped "
    "learning.\n"
    "4. Asks: at most ONE open — the ledger enforces it. The shape is "
    "always " + ASK_SHAPE + ". Use every grant VISIBLY by the next daily "
    "pass.\n"
    "5. goal_update what moved; share_thought a one-liner if anything did: "
    "'Moved <goal>: <what changed> [[wiki-page]]'. Skip only a genuinely "
    "empty pass.\n"
    "WORK BRANCH (agent_phase='work'):\n"
    "1. mission_get, then goal_list. Keep 2-3 goals rolling — when one "
    "closes, refill with goal_set in the SAME pass.\n"
    "2. Execute: advance the top goal through your validated playbooks and "
    "the agreed approval points — produce output the owner can use, not "
    "notes about it.\n"
    "3. Record: wiki updates with citations; goal_update what moved; "
    "value_log_add real wins with evidence.\n"
    "4. share_thought ONE goal-cited line: 'Moved <goal>: <what changed> "
    "[[wiki-page]]'. Skip only a genuinely empty pass.\n"
    "Both branches: end on what YOU will do next, never on homework for the "
    "owner. " + NEXT_TOUCH_RULE + " If a repeatable routine is worth "
    "automating, record it as an open question tagged 'playbook idea' "
    "(playbook tools are chat-only)."
)


# --- 8.1C: the INSTALL kickoff — fires once, on the first load with no ------
# --- mission, so installing the plugin visibly changes the agent NOW --------

INSTALL_KICKOFF_TITLE = "Curiosity awakened"

INSTALL_KICKOFF_CONTENT = """\
The curiosity plugin was just installed — and you have no mission yet. This
changes what you ARE: you can now own a mission end-to-end — research it every
day, build a knowledge wiki on it, consolidate what you learn in a nightly
dream, commit to goals and report a weekly scoreboard, and proactively share
grounded insights.

None of that runs until the owner gives you a mission. So speak up NOW, in
your own voice and personality: introduce what you just became able to do
(plain words, no tool or plugin names), make the stakes felt — a mission turns
you from a chat companion into an agent that works for them around the clock —
and tell them plainly how it works: once they give you a mission, you first
make yourself QUALIFIED for it — a setup phase where they see exactly what
you're missing and how close you are — and then you run it as your job. Ask
directly: what mission do they want you to own? Offer one or two concrete
framings to make answering easy (the problem they most want off their plate;
what they'd hand a sharp new hire). Keep it short and warm; end on the
question.
"""


async def run_install_kickoff(ctx: PluginContext) -> bool:
    """Post the one-time install kickoff moment (no tools — the reaction turn
    just speaks). Returns True only if the moment actually landed: on a
    zero-conversation fresh install post_muted_message reports
    {"error": "no target conversation"} WITHOUT raising, and the caller must
    not burn the once-only flag on that (the onboarding greeting carries the
    mission ask there; the kickoff retries on a later load for the
    installed-into-an-existing-Luna case)."""
    result = await ctx.send_muted_message(
        INSTALL_KICKOFF_TITLE,
        INSTALL_KICKOFF_CONTENT,
        channel="moment",
        source="curiosity",
    )
    if isinstance(result, dict) and result.get("error"):
        log.info("install kickoff not delivered: %s", result["error"])
        return False
    return True


async def run_kickoff(ctx: PluginContext, statement: str) -> None:
    """Post the kickoff moment. Runs as a fire-and-forget task from
    mission_set; the short delay lets the mission_set turn finish streaming
    before the kickoff reaction turn starts competing for the loop.

    post_muted_message swallows turn exceptions and returns an ``error`` key
    instead (a dead turn otherwise looks like a turn that chose silence), so
    failure is detected from the result, not an exception. Retrying re-posts
    the moment message too — acceptable: a failed turn means the first moment
    was never reacted to, and a lost kickoff strands the mission at S0."""
    await asyncio.sleep(KICKOFF_DELAY_S)
    for attempt in range(1, KICKOFF_ATTEMPTS + 1):
        try:
            result = await ctx.send_muted_message(
                KICKOFF_TITLE,
                _KICKOFF_CONTENT.format(statement=statement),
                channel="moment",
                source="curiosity",
                tools=KICKOFF_TOOLS,
            )
        except Exception:  # noqa: BLE001
            log.warning("mission kickoff failed (attempt %s)", attempt, exc_info=True)
            result = None
        if result is not None and not result.get("error"):
            log.info("mission kickoff moment posted")
            return
        if attempt < KICKOFF_ATTEMPTS:
            log.warning(
                "mission kickoff turn died (attempt %s): %s",
                attempt,
                (result or {}).get("error", "exception"),
            )
            await asyncio.sleep(KICKOFF_RETRY_S)
    log.warning("mission kickoff abandoned after %s attempts", KICKOFF_ATTEMPTS)


# --- 9.001G: the heartbeat safety net — notice a missing heartbeat, nudge ---
# --- the agent to recreate it. The net reminds; it NEVER creates the --------
# --- trigger itself (the heartbeat must stay agent-authored). ---------------

HEARTBEAT_NUDGE_TITLE = "Setup heartbeat missing"

HEARTBEAT_NUDGE_TOOLS = [
    "mission_get",
    "scope_list",
    "goal_list",
    "loop_list",
    "trigger_create",
    "trigger_list",
    "wiki_read",
    "wiki_write",
]

HEARTBEAT_NUDGE_CONTENT = (
    "You are in SETUP phase but no '" + HEARTBEAT_NAME + "' trigger exists — "
    "your self-authored drive is missing (never created, or deleted behind "
    "your back). Recreate it NOW with trigger_create.\n"
    + HEARTBEAT_CONTRACT
    + "\nCheck current state first (mission_get, scope_list) so the prompt "
    "you author names your REAL current gaps. Then reply with one short "
    "line telling the owner the heartbeat is in place and the cadence you "
    "chose."
)


async def heartbeat_exists(ctx: PluginContext) -> bool | None:
    """True/False when the scheduler answered; None when it cannot be known
    (plugin-scheduler absent or unreachable) — the caller must NOT nudge on
    None, or every scheduler blip would spawn a nudge."""
    try:
        lister = ctx.tool_registry.get("trigger_list").handler
    except KeyError:
        return None
    try:
        listed = await lister()
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(listed, dict) or "error" in listed:
        return None
    return any(t.get("name") == HEARTBEAT_NAME for t in listed.get("triggers", []))


async def run_heartbeat_nudge(ctx: PluginContext) -> bool:
    """Post the muted heartbeat nudge; True only if it actually landed."""
    result = await ctx.send_muted_message(
        HEARTBEAT_NUDGE_TITLE,
        HEARTBEAT_NUDGE_CONTENT,
        channel="moment",
        source="curiosity",
        tools=HEARTBEAT_NUDGE_TOOLS,
    )
    if isinstance(result, dict) and result.get("error"):
        log.info("heartbeat nudge not delivered: %s", result["error"])
        return False
    return True


def spawn_kickoff(ctx: PluginContext, statement: str) -> str:
    try:
        asyncio.get_running_loop().create_task(run_kickoff(ctx, statement))  # noqa: RUF006
        return "started"
    except RuntimeError:
        return "no event loop — kickoff skipped"
