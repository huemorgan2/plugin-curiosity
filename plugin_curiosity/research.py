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
from sqlalchemy import text as _sql

from .prompts import (
    ABILITY_CONTRACT,
    ALREADY_SUPPLIED,
    ASK_SHAPE,
    CANONICAL_EXAMPLE,
    COMPACT_ARTIFACT,
    EXEC_SUMMARY_SHAPE,
    FDE_DOCTRINE,
    HEARTBEAT_CONTRACT,
    HEARTBEAT_NAME,
    HONEST_HORIZONS,
    JOB_DESCRIPTION_SHAPE,
    LOOP_DISCIPLINE,
    MATERIALITY_RULE,
    NEXT_TOUCH_RULE,
    NO_BLAME,
    OWNER_WORDS,
    PHASE_CHECK,
    PHASE_ONE_DOCTRINE,
    PLAN_LEDGER_RULE,
    PLAN_SHAPE,
    RATIFICATION_FORCING,
    SETUP_STAGE_DEFS,
    SUCCESS_TABLE_SHAPE,
    TALENTED_HIRE_LAW,
    VALUE_QUESTION_CADENCE,
    WIKI_BINDING,
)

log = logging.getLogger("plugin-curiosity")

# Allowlist for the PLANNING pass reaction turn (phase14: the deep pass no
# longer scaffolds — it researches and puts a numbered plan on the owner's
# desk). The allowlist IS the gate for this muted turn: scope_set, stage_set,
# ability_upsert, goal_set, trigger_create, loop_open, value_log_add are
# deliberately ABSENT — the planning turn physically cannot set the agent up.
# share_thought is deliberately absent: the reply IS the visible artifact.
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
    # phase14: capability research — the plan cites what Luna can ACTUALLY
    # do, never a guess (absent names are simply not in the reaction turn's
    # toolset — harmless when a plugin isn't installed).
    "get_plugin_status",
    "marketplace_search",
    "wa_status",
    "connector_list_connected",
    # phase14: the numbered plan ledger — open and write the plan, never
    # approve it (the OK is the owner's, in chat, later) and never execute
    # it (setup_plan_start / the scaffolding tools are not in this belt).
    "setup_plan_open",
    "setup_plan_list",
    # 11.002/M2: the pass's card is posted plugin-side before this turn
    # spawns (announced+running); the turn closes it at the end.
    "next_step_done",
]

KICKOFF_TITLE = "Mission planning"

# --- 11.001/M1: the kickoff split. mission_set posts an INSTANT BRIEF -------
# --- (~3 s, a handful of calls, owner watching); the deep S0→S2 pass waits --
# --- for mission_confirm — an owner "go" — and for NOTHING else (phase12). --

BRIEF_TITLE = "Mission first look"

# deliberately tiny: the brief must land while the owner is still looking
BRIEF_TOOLS = [
    "mission_get",
    "web_search",
    "web_fetch",
]

BRIEF_CONTENT = """\
Your mission was just set: {statement}

This turn is your INSTANT BRIEF — the owner is watching right now, so speed
beats depth: a HANDFUL of tool calls at most (one or two quick web_search /
web_fetch if a fact would sharpen it; zero is fine), no wiki writes, no
goals, no scopes — your deep pass handles all of that later.

Reply with three short parts, plain words, your own voice:
1. **What I heard** — the mission restated in your own words, one line,
   sharper than it was said.
2. **First look** — one genuinely interesting observation you can already
   offer (from what you know, or one quick search).
3. **3 things I could do for you** — three concrete, everyday pieces of
   work you could own under this mission, one line each.

Close by asking for their yes: if this direction is right, they say "go"
and you dig in properly — research, your job description, milestones. Until
then you stay light and redirectable — nothing deep runs without their yes.
One short question, warm, done.
"""

# how long an unconfirmed mission waits before the ONE re-ask nudge fires.
# 11.012/phase12: there is NO timeout-proceed anymore — the deep pass runs
# only on mission_confirm. Silence earns a single re-ask, never a spend
# (revision-2 Law 1: the mission is confirmed, not received).
CONFIRM_TIMEOUT_H = 12.0

CONFIRM_NOTE_CONFIRMED = "\nThe owner confirmed the direction — go.\n"

CONFIRM_NUDGE_TITLE = "Mission awaiting your yes"

CONFIRM_NUDGE_TOOLS = ["mission_get"]

CONFIRM_NUDGE_CONTENT = (
    "Your mission is saved but the owner never answered your first-look "
    "brief — the direction is still unconfirmed, and nothing deep runs "
    "without their yes. This turn is ONE short re-ask and nothing else:\n"
    "1. mission_get to see the current statement.\n"
    "2. Reply with at most 4 short lines, plain words, your own voice: "
    "reflect the mission back in your own words (sharper than it was "
    "said), ask if you got it right — a simple 'go' starts the real work — "
    "and make clear they can redirect or reword it at any time.\n"
    "Do NO research, NO wiki writes, NO goals in this turn. If they stay "
    "silent, keep waiting — you never proceed on your own; their pane "
    "shows the pending yes."
)

# once-per-mission guard for the deep pass, persisted in the Flag register
_DEEP_KICKOFF_FLAG = "deep_kickoff_started"

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
Your mission: {statement}
{confirm_note}
You are in SETUP phase — this turn is your PLANNING pass (~12-18 tool
calls). You research the JOB and what you can ACTUALLY do, then put a
NUMBERED PLAN on the owner's desk. You build NOTHING in this turn — no
scopes, no goals, no abilities, no heartbeat; those tools are not even in
this turn's belt, by design. Everything you produce is a reviewable draft.
{wiki_note}"""
    + OWNER_WORDS
    + "\n"
    + PLAN_LEDGER_RULE
    + "\n"
    + PHASE_ONE_DOCTRINE
    + "\n"
    + FDE_DOCTRINE
    + "\n"
    + TALENTED_HIRE_LAW
    + "\n"
    + ALREADY_SUPPLIED
    + """

Understand the JOB sharper than you were told:
1. Restate the mission SHARPER than the owner said it — one line; it heads
   your charter.
2. Research the ROLE, not just the domain: 2-3 web_search — at least one on
   how this JOB is done well (who does this work, what their week looks
   like, what tools they lean on), web_fetch the 1-2 most substantive hits.
   If the mission names a company or site, check the real thing FIRST — what
   you find there beats what you were told. Record 2-3 NON-OBVIOUS
   observations on [[mission-domain]] (wiki_patch + wiki_cite — no uncited
   claims).
3. Draft [[job-description]] v1 (wiki_write) — YOUR job description, from
   the mission plus what you just learned about the role. The owner reviews
   this page — it is the first thing you put on their desk. """
    + JOB_DESCRIPTION_SHAPE
    + """
4. Write [[success-criteria]] (wiki_write): what success looks like — what
   will make the owner call you successful. 3-6 concrete criteria,
   owner-checkable. """
    + SUCCESS_TABLE_SHAPE
    + """
   The owner approves this page together with your job description; the
   plan's milestones must trace to it.

Research what Luna can ACTUALLY do — never assume a capability exists:
5. get_plugin_status — read EVERY installed plugin and the tools it gives
   you; this list, not your imagination, is what you can do today. Then
   marketplace_search 1-2 mission keywords (a plugin that does part of the
   job is a step closed — name it in the plan and ask to install), and
   wa_status / connector_list_connected for off-platform reach — skip
   silently if a tool isn't available. Findings go in the plan as "what I
   have / what I'm missing", cited from the tool results.

Write the numbered plan and put it on the owner's desk:
6. setup_plan_open(name=<short-kebab-handle>, objective=<one line>) — it
   allocates your plan's number and returns the wiki slug. wiki_write the
   FULL technical plan there, every detail you would otherwise carry in
   your head. """
    + PLAN_SHAPE
    + """
   The technical steps name the exact abilities, the scopes across all
   seven kinds (knowledge, people, communication_paths, tools_data_access,
   workflow_approval, playbooks, routines_feedback), the 3-5 MILESTONES
   you will commit to — each with an honest horizon (horizon_kind +
   horizon_ref, NEVER a guessed calendar date) and traced to a criterion
   on [[success-criteria]] — the heartbeat trigger you will create, and
   any install/access you need. """
    + HONEST_HORIZONS
    + """
7. Reply with the **Mission plan** artifact:
   - **Brief** — the mission in your own words, sharper.
   - **What I found** — the 2-3 non-obvious role observations, with
     sources, and the capability inventory: what I have / what I'm missing.
   - **My job description** — the essentials of [[job-description]],
     labeled draft v1, for their review.
   - **What success looks like** — the essentials of [[success-criteria]],
     in the owner's terms.
   - **The plan** — plan {{number}} by name, its technical steps in
     one-line-each owner terms, pointing at the full page on the wiki.
   - **What I need from you** — read the job description and the plan;
     push back on anything.
   Close with: "nothing here runs until your OK — say ok or go and I
   execute exactly this plan; or tell me what to change and I write the
   next numbered plan." Then STOP. Do NOT call setup_plan_approve — the OK
   is the owner's to give, in chat, in their own words. Silence is never a
   yes.
8. LAST: a next-step card for this pass was posted before the turn started
   — close it now with next_step_done.
"""
)

DAILY_RESEARCH_TARGET = (
    "[curiosity] Daily pass. You OWN this mission — one focused pass "
    "(~10 tool calls). " + PHASE_CHECK + "\n"
    "CARD FIRST (before step 0): this fire is self-directed spend — post its "
    "next-step card: next_step_post(what=this pass's one action, why, "
    "produces, cost_text, scheduled=true — this run rides your owner-visible "
    "schedule) then next_step_start. An action BEYOND the routine (new "
    "outreach, money, a third party) gets its OWN card WITHOUT scheduled — "
    "at rung 1-2 it waits out its veto window; start it a later turn. At the "
    "end of the pass, next_step_done (value_ref if you logged a win).\n"
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
    + WIKI_BINDING + " " + OWNER_WORDS + " " + HONEST_HORIZONS + "\n"
    "SETUP BRANCH (agent_phase='setup'): you are QUALIFYING yourself for "
    "this job — every action today closes a named gap on your ladder: which "
    "tools, access, people, or knowledge am I missing? do I know what "
    "success looks like ([[success-criteria]])?\n"
    "1. mission_get, then goal_list and ability_list. CONFRONT overdue "
    "goals first: a goal with a real date (horizon_kind 'date') past it "
    "gets replanned, escalated, or dropped TODAY (goal_update with the "
    "reason) — never carried silently. A goal on_unlock or "
    "awaiting_approval is NEVER overdue — it is blocked: confront the "
    "BLOCKER (nudge its loop, re-raise the approval with its ~5-minute "
    "cost), not the goal. " + RATIFICATION_FORCING + " Also trigger_list: if your own "
    "'" + HEARTBEAT_NAME + "' trigger is missing, recreate it per your "
    "heartbeat contract BEFORE anything else.\n"
    "2. Pick the ONE goal you can advance TODAY and advance it with a small "
    "S1-style value pass: web_search / web_fetch, record on the wiki "
    "(wiki_write/wiki_patch + wiki_cite), stub/summary depth until the "
    "owner approves the job description. scope_update the scope it grew and "
    "ability_task_set any subtask that moved, with evidence.\n"
    "3. EVENT-DRIVEN REPLAN: if today's learning changes the plan, change "
    "the plan TODAY (plan_change_note + scope_set/goal_set/ability_upsert), "
    "not at the weekly. Judge materiality: a detail refines the plan "
    "(kind='refine'); a discovery that changes what the JOB IS becomes a "
    "pivot PROPOSAL (kind='role_pivot' — evidence, what changes, what you'd "
    "stop/start; the owner decides). A plan that never changes after week 1 "
    "means you stopped learning.\n"
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
changes what you ARE: you can now own a mission end-to-end — work it around
the clock, learn it deeper every day, and report real results.

None of that runs until the owner gives you a mission. Most people don't yet
know what work an agent can take off their plate — so don't ask them to
imagine it; SHOW them. Speak up NOW, in your own voice and personality, and
teach possibility with 2–3 tiny concrete before/after examples, one line
each, everyday and plain (for instance: inquiries sat unanswered overnight →
every inquiry gets a solid draft reply within minutes; nobody knew which ads
paid → a weekly one-pager says where the budget leaks; "we should follow up
more" → every quiet customer gets a warm nudge at the right moment). Pick
examples that fit what you know about this owner; plain words, no tool or
plugin names, no feature lists.

Then tell them plainly how it works: once they give you a mission, you first
make yourself QUALIFIED for it — a setup phase where they see exactly what
you're missing and how close you are — and then you run it as your job,
starting small and earning more as you show results. Ask directly: what
mission do they want you to own? Offer one or two concrete framings to make
answering easy (the problem they most want off their plate; what they'd hand
a sharp new hire). Keep it short and warm; end on the question.
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


_COMPACT_WORDS = (
    "succinct", "concise", "compact", "brief", "terse", "short",
    "keep it short", "keep things short", "no fluff", "to the point",
    "bullet", "tl;dr", "tldr", "minimal",
)


async def _prefers_compact(ctx: PluginContext) -> bool:
    """True when the owner's identity/persona asks for short output. Reads the
    core identity row (verbosity + free-text tone/instructions/persona) — the
    same signal the chat path already honors. Best-effort: any read failure
    means fall back to the full artifact."""
    sf = getattr(ctx, "db_session_factory", None)
    if sf is None:
        return False
    try:
        async with sf() as s:
            row = (
                await s.execute(_sql("SELECT * FROM identity LIMIT 1"))
            ).mappings().first()
    except Exception:  # noqa: BLE001 — no identity row / unreachable → full artifact
        return False
    if not row:
        return False
    d = dict(row)
    verbosity = str(d.get("verbosity") or "").strip().lower()
    if verbosity in ("compact", "succinct", "concise", "brief", "short", "low", "terse"):
        return True
    blob = " ".join(
        str(d.get(k) or "") for k in ("tone", "instructions", "persona")
    ).lower()
    return any(w in blob for w in _COMPACT_WORDS)


async def _post_moment_with_retries(
    ctx: PluginContext, title: str, content: str, tools: list[str]
) -> None:
    """Post one kickoff-family moment with real retry spacing.

    post_muted_message swallows turn exceptions and returns an ``error`` key
    instead (a dead turn otherwise looks like a turn that chose silence), so
    failure is detected from the result, not an exception. Retrying re-posts
    the moment message too — acceptable: a failed turn means the first moment
    was never reacted to, and a lost kickoff strands the mission at S0."""
    await asyncio.sleep(KICKOFF_DELAY_S)
    for attempt in range(1, KICKOFF_ATTEMPTS + 1):
        try:
            result = await ctx.send_muted_message(
                title,
                content,
                channel="moment",
                source="curiosity",
                tools=tools,
            )
        except Exception:  # noqa: BLE001
            log.warning("%s failed (attempt %s)", title, attempt, exc_info=True)
            result = None
        if result is not None and not result.get("error"):
            log.info("%s moment posted", title)
            return
        if attempt < KICKOFF_ATTEMPTS:
            log.warning(
                "%s turn died (attempt %s): %s",
                title,
                attempt,
                (result or {}).get("error", "exception"),
            )
            await asyncio.sleep(KICKOFF_RETRY_S)
    log.warning("%s abandoned after %s attempts", title, KICKOFF_ATTEMPTS)


def _wiki_note(wiki_slug: str | None) -> str:
    if not wiki_slug:
        return ""
    return (
        f"\nYour mission wiki is '{wiki_slug}' — pass wiki='{wiki_slug}' "
        "to EVERY wiki_* call in this turn; pages written elsewhere are "
        "invisible to your mission surfaces.\n"
    )


async def run_brief(ctx: PluginContext, statement: str) -> None:
    """The instant brief — fire-and-forget from mission_set."""
    await _post_moment_with_retries(
        ctx, BRIEF_TITLE, BRIEF_CONTENT.format(statement=statement), BRIEF_TOOLS
    )


async def run_kickoff(
    ctx: PluginContext,
    statement: str,
    wiki_slug: str | None = None,
    compact: bool = False,
    confirm_note: str = "",
) -> None:
    """The PLANNING pass (phase14 — formerly the deep S0→S2 pass; it now
    researches and writes the numbered plan, and builds nothing). Fired by
    mission_confirm only — never directly by mission_set (11.001) and never
    by a timeout (phase12)."""
    content = _KICKOFF_CONTENT.format(
        statement=statement, wiki_note=_wiki_note(wiki_slug),
        confirm_note=confirm_note,
    )
    if compact:
        content += "\n\n" + COMPACT_ARTIFACT
    await _post_moment_with_retries(ctx, KICKOFF_TITLE, content, KICKOFF_TOOLS)


# --- phase14: the EXECUTION pass — runs an owner-APPROVED numbered plan -----
# --- and nothing else. Spawned ONLY by setup_plan_approve (the owner's OK ---
# --- recorded) or the janitor recovering an approved-but-unspawned plan. ----

PLAN_EXEC_TITLE = "Setup plan execution"

# The scaffolding set lives HERE — the one turn allowed to build, because an
# owner-approved plan says exactly what to build.
PLAN_EXEC_TOOLS = [
    "mission_get",
    "setup_plan_start",
    "setup_plan_close",
    "setup_plan_list",
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
    "scope_set",
    "scope_update",
    "scope_list",
    "stage_set",
    "ability_upsert",
    "ability_task_set",
    "ability_list",
    "goal_set",
    "goal_list",
    "loop_open",
    "loop_list",
    "value_log_add",
    "plan_change_note",
    "trigger_create",
    "trigger_list",
    "marketplace_search",
    "wa_status",
    "connector_list_connected",
    "next_step_done",
]

_PLAN_EXEC_CONTENT = (
    """\
Your mission: {statement}

The owner APPROVED setup plan {plan_label} — their words: "{owner_words}".
This turn EXECUTES that plan — exactly what its page says, nothing more
(S0→S2, ~18-24 tool calls).
{wiki_note}"""
    + OWNER_WORDS
    + "\n"
    + PLAN_LEDGER_RULE
    + "\n"
    + SETUP_STAGE_DEFS
    + "\n"
    + HONEST_HORIZONS
    + "\n"
    + FDE_DOCTRINE
    + "\n"
    + ALREADY_SUPPLIED
    + """

1. setup_plan_start() FIRST — it marks the plan executing and unlocks the
   scaffolding tools. If it refuses, STOP: reply with one short line naming
   the ledger state; execute nothing.
2. wiki_read '{plan_slug}' and execute its ## Technical steps IN ORDER,
   exactly as written — a step not in the plan does not happen. The steps
   will typically build:
   - your qualification ladder. """
    + ABILITY_CONTRACT
    + """
   - your scopes across the seven kinds, each attached to the ability it
     serves (scope_set with ability_id).
   - your 3-5 milestones (goal_set) with the horizons the plan wrote, each
     traced to [[success-criteria]]; for the next 1-2 set expected_result
     and readiness with a one-line readiness_note.
   - your OWN setup heartbeat — born HERE, as a plan step: trigger_list
     first; if it somehow already exists, leave it; else trigger_create
     NOW. """
    + HEARTBEAT_CONTRACT
    + """
   Small in-flight adjustments (a rename, a scope the plan implied) are
   fine — note each in the summary. Anything that changes the plan's SHAPE
   stops the run: skip it, close honestly, and draft the next numbered
   plan instead.
3. If the plan includes a first value pass, run it with what you already
   have. """
    + CANONICAL_EXAMPLE
    + """. Stub/summary wiki depth only; value_log_add anything real you
   delivered (evidence: the wiki page).
4. Ask ONLY plan-changing questions, each as a loop —
   loop_open(kind='question'), stating what it unblocks — and record it
   with wiki_ask. ZERO access asks in this turn. """
    + VALUE_QUESTION_CADENCE
    + """
5. stage_set('S2') when the plan's steps are done.
6. ALWAYS — success, partial, or failure — wiki_write the execution
   summary at '{summary_slug}'. """
    + EXEC_SUMMARY_SHAPE
    + """
7. setup_plan_close(outcome='done' or 'failed', note=one line) — it
   refuses until the summary page exists; that is the contract, not a bug.
8. Reply short and honest: what ran, what you built, what failed or was
   skipped, and [[{summary_slug}]] for the record. Anything left undone,
   failed, or newly discovered becomes the NEXT numbered plan — drafted
   with setup_plan_open, put on the owner's desk, NEVER executed before
   their fresh OK. NEVER end on a list of suggestions for the owner to
   do. """
    + NEXT_TOUCH_RULE
    + """
9. LAST: a next-step card for this pass was posted before the turn started
   — close it now with next_step_done (value_ref = the value-log entry
   from step 3 if you logged one).
"""
)


async def run_plan_execution(
    ctx: PluginContext,
    statement: str,
    plan: dict,
    wiki_slug: str | None = None,
    compact: bool = False,
) -> None:
    """The EXECUTION pass for one approved plan. Fired by setup_plan_approve
    only — the owner's recorded OK is the sole path here (phase14)."""
    content = _PLAN_EXEC_CONTENT.format(
        statement=statement,
        plan_label=plan.get("label") or plan.get("slug", "?"),
        owner_words=plan.get("decision_note") or "ok",
        plan_slug=plan["slug"],
        summary_slug=plan["summary_slug"],
        wiki_note=_wiki_note(wiki_slug),
    )
    if compact:
        content += "\n\n" + COMPACT_ARTIFACT
    await _post_moment_with_retries(ctx, PLAN_EXEC_TITLE, content, PLAN_EXEC_TOOLS)


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
    + "\n" + WIKI_BINDING
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


async def dedupe_heartbeats(ctx: PluginContext) -> int | None:
    """Self-heal the EXACTLY-ONE heartbeat invariant. Two concurrent turns
    (mission-adoption chat + detached kickoff) can each pass their
    list-before-create check and author a duplicate — prompt discipline is
    probabilistic across turns (9.002 prod e2e). Delete every extra, keeping
    the OLDEST: its fire history carries the streak. Runs from plugin code
    via the raw handlers, so trigger_delete's prompt_always approval policy
    never parks an agent turn on cleanup. Returns the number deleted; None
    when the scheduler cannot be consulted."""
    try:
        lister = ctx.tool_registry.get("trigger_list").handler
        deleter = ctx.tool_registry.get("trigger_delete").handler
    except KeyError:
        return None
    try:
        listed = await lister()
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(listed, dict) or "error" in listed:
        return None
    beats = [t for t in listed.get("triggers", []) if t.get("name") == HEARTBEAT_NAME]
    if len(beats) <= 1:
        return 0
    beats.sort(key=lambda t: str(t.get("created_at") or ""))
    deleted = 0
    for extra in beats[1:]:
        tid = extra.get("id")
        if not tid:
            continue
        try:
            result = await deleter(id=str(tid))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(result, dict) and result.get("error"):
            continue
        deleted += 1
    if deleted:
        log.info("heartbeat dedupe: removed %s duplicate trigger(s), kept oldest", deleted)
    return deleted


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


def spawn_kickoff(
    ctx: PluginContext,
    statement: str,
    wiki_slug: str | None = None,
    compact: bool = False,
) -> str:
    """mission_set's fire-and-forget: since 11.001 this spawns the INSTANT
    BRIEF — the deep S0→S2 pass waits behind the confirm gate. Signature kept
    from the pre-split API (wiki_slug/compact ride the deep pass only)."""
    try:
        asyncio.get_running_loop().create_task(  # noqa: RUF006
            run_brief(ctx, statement)
        )
        return "brief started"
    except RuntimeError:
        return "no event loop — kickoff skipped"


# --- 11.001: the confirm gate — deep pass starts exactly once per mission ---

_deep_claims: set[str] = set()  # in-process dedupe alongside the DB flag

# phase12: the one-time confirm re-ask, same claim+flag shape as the deep pass
_CONFIRM_NUDGE_FLAG = "confirm_nudge_sent"
_nudge_claims: set[str] = set()


async def flag_get(sf, key: str) -> str | None:
    from .models import Flag

    async with sf() as s:
        row = await s.get(Flag, key)
        return row.value if row is not None else None


async def flag_set(sf, key: str, value: str) -> None:
    from .models import Flag

    async with sf() as s:
        row = await s.get(Flag, key)
        if row is None:
            s.add(Flag(key=key, value=value))
        else:
            row.value = value
        await s.commit()


def _deep_flag_key(mission_id: str) -> str:
    return f"{_DEEP_KICKOFF_FLAG}:{mission_id}"


async def _deep_flag_get(sf, mission_id: str) -> str | None:
    return await flag_get(sf, _deep_flag_key(mission_id))


async def _deep_flag_set(sf, mission_id: str, value: str) -> None:
    await flag_set(sf, _deep_flag_key(mission_id), value)


async def spawn_deep_kickoff_once(
    ctx: PluginContext,
    sf,
    mission: dict,
    *,
    compact: bool = False,
    confirm_note: str = CONFIRM_NOTE_CONFIRMED,
) -> str:
    """Start the deep pass at most once per mission. In-process claim plus a
    persisted flag: concurrent callers (mission_confirm racing the timeout
    janitor) converge on a single spawn."""
    mid = str(mission["id"])
    if mid in _deep_claims:
        return "already started"
    if await _deep_flag_get(sf, mid) is not None:
        _deep_claims.add(mid)
        return "already started"
    _deep_claims.add(mid)
    await _deep_flag_set(sf, mid, "started")
    # 11.002/M2: the pass's card, plugin-side — deterministic, before the
    # spend; the kickoff turn closes it (step 13). Best-effort by design.
    from .next_steps import record_scheduled_step

    await record_scheduled_step(
        sf,
        "Planning pass — research the mission and Luna's real capabilities, "
        "draft my job description, write numbered setup plan 001 for your "
        "review",
        why="the owner confirmed the mission direction",
        produces="job description, success criteria, a reviewable setup plan "
        "— nothing executes until the owner's OK",
        cost_text="one working turn (~15 tool calls), a few web searches",
        source="kickoff",
    )
    try:
        asyncio.get_running_loop().create_task(  # noqa: RUF006
            run_kickoff(
                ctx,
                mission["statement"],
                wiki_slug=mission.get("wiki_id"),
                compact=compact,
                confirm_note=confirm_note,
            )
        )
        return "started"
    except RuntimeError:
        return "no event loop — deep kickoff skipped"


# --- phase14: the execution pass spawns at most once per PLAN ---------------

_PLAN_EXEC_FLAG = "plan_exec_started"
_plan_exec_claims: set[str] = set()


async def spawn_plan_execution_once(
    ctx: PluginContext, sf, mission: dict, plan: dict
) -> str:
    """Start the execution pass at most once per plan. Same claim+flag shape
    as the deep pass: setup_plan_approve racing the janitor converges on a
    single spawn."""
    pid = str(plan["id"])
    if pid in _plan_exec_claims:
        return "already started"
    flag_key = f"{_PLAN_EXEC_FLAG}:{pid}"
    if await flag_get(sf, flag_key) is not None:
        _plan_exec_claims.add(pid)
        return "already started"
    _plan_exec_claims.add(pid)
    await flag_set(sf, flag_key, "started")
    from .next_steps import record_scheduled_step

    label = plan.get("label") or plan.get("slug", "?")
    await record_scheduled_step(
        sf,
        f"Execute setup plan {label} — exactly what its page says",
        why="the owner approved the plan"
        + (f' ("{plan["decision_note"]}")' if plan.get("decision_note") else ""),
        produces="the setup the plan describes + its execution summary at "
        f"[[{plan.get('summary_slug', '?')}]]",
        cost_text="one long working turn (~20 tool calls)",
        source="kickoff",
    )
    try:
        asyncio.get_running_loop().create_task(  # noqa: RUF006
            run_plan_execution(
                ctx,
                mission["statement"],
                plan,
                wiki_slug=mission.get("wiki_id"),
                compact=await _prefers_compact(ctx),
            )
        )
        return "started"
    except RuntimeError:
        return "no event loop — plan execution skipped"


def _parse_created(value) -> "datetime | None":
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    if not value:
        return None
    try:
        parsed = _dt.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=_UTC)


async def maybe_start_deep_kickoff(ctx: PluginContext, store, plan_store=None) -> str:
    """The confirm-gate janitor (on-load + per-turn 'next contact'):
    - an APPROVED plan whose execution pass never spawned (process died
      between approve and spawn) starts it now (phase14);
    - a CONFIRMED mission whose planning pass never spawned starts it now;
    - an UNCONFIRMED mission older than CONFIRM_TIMEOUT_H gets ONE muted
      re-ask nudge — the deep pass NEVER starts without the owner's yes
      (phase12: the timeout-proceed is gone; it fired unasked on upgrades);
    - a mission already past S0 (or in work phase) predates the split or ran
      its pass — grandfathered, never re-fired."""
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    mission = await store.get()
    if mission is None:
        return "no mission"
    sf = store._sf  # noqa: SLF001
    mid = str(mission["id"])
    if mission.get("setup_stage") not in (None, "S0") or mission.get("agent_phase") == "work":
        if mid not in _deep_claims:
            _deep_claims.add(mid)
            if await _deep_flag_get(sf, mid) is None:
                await _deep_flag_set(sf, mid, "grandfathered")
        return "already past S0"
    if plan_store is not None:
        plan = await plan_store.current()
        if plan is not None and plan["status"] == "approved":
            return await spawn_plan_execution_once(ctx, sf, mission, plan)
    if mission.get("confirmed_at"):
        return await spawn_deep_kickoff_once(
            ctx, sf, mission, compact=await _prefers_compact(ctx),
            confirm_note=CONFIRM_NOTE_CONFIRMED,
        )
    created = _parse_created(mission.get("created_at"))
    if created is None:
        return "no created_at"
    age_h = (_dt.now(_UTC) - created).total_seconds() / 3600.0
    if age_h < CONFIRM_TIMEOUT_H:
        return "waiting for confirmation"
    nudge_key = f"{_CONFIRM_NUDGE_FLAG}:{mid}"
    if mid in _nudge_claims or await flag_get(sf, nudge_key) is not None:
        _nudge_claims.add(mid)
        return "already nudged"
    _nudge_claims.add(mid)
    await flag_set(sf, nudge_key, "sent")
    result = await ctx.send_muted_message(
        CONFIRM_NUDGE_TITLE,
        CONFIRM_NUDGE_CONTENT,
        channel="moment",
        source="curiosity",
        tools=CONFIRM_NUDGE_TOOLS,
    )
    if isinstance(result, dict) and result.get("error"):
        log.info("confirm nudge not delivered: %s", result["error"])
    return "nudged"
