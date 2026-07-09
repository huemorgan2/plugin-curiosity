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
]

KICKOFF_TITLE = "Mission kickoff"

# breathing room so the mission_set turn finishes streaming before the
# kickoff reaction turn starts competing for the loop (tests set this to 0)
KICKOFF_DELAY_S = 3.0

_KICKOFF_CONTENT = """\
Your mission was just set: {statement}

Do the mission kickoff NOW, in this turn — the owner should feel that a
driven agent just took ownership, not that a librarian filed a note. Keep it
tight (about 10-14 tool calls; depth comes from the daily research schedule):

1. Run 2-3 web_search queries on the core of the mission; web_fetch the one or
   two most substantive results.
2. Write what you learned into the wiki: flesh out [[mission-domain]] with a
   first researched pass (wiki_patch), and record each real source with
   wiki_cite. No uncited claims.
3. Record 3-5 sharp open questions to pursue next (wiki_ask), and put the ones
   that frame the mission on [[mission-open-questions]].
4. COMMIT to 2-3 concrete goals with goal_set — specific, checkable outcomes
   YOU will drive, each with a target date. These are your commitments, not
   suggestions; the daily research passes work them and the weekly review
   scores them.
5. Scan your own setup against the mission: if you have marketplace_search,
   search it with 1-2 mission keywords — is there a plugin that would let you
   actually DO part of this instead of only reading about it? If you have
   wa_status or connector_list_connected, check whether you can reach the
   owner off-platform (WhatsApp / email). Note real gaps for the ask below;
   skip silently if these tools aren't available.
6. Then reply to the owner with the **Mission Kickoff** artifact, in this
   exact shape:
   - **Brief** — 3-5 lines: the mission in your own words and how you'll
     attack it.
   - **Quick win** — ONE concrete, immediately useful insight you just found,
     with its source URL.
   - **My goals** — the 2-3 goals you just committed to, with target dates:
     "Here's what I'm going after."
   - **Open questions** — the 3-5 questions you recorded.
   - **Next move** — ONE concrete action YOU will take (a routine you'll
     schedule, a draft you'll produce, a plugin you want installed, a channel
     you want connected — "install X and I can actually do Y", "connect me to
     your WhatsApp so the mission doesn't pause when you close this tab").
     End with "say go and I'll do it" when it needs the owner, or "already
     scheduled" when it doesn't. NEVER end on a list of suggestions for the
     owner to do — end on what YOU will do.
If a repeatable routine would serve the mission (a weekly scan, a digest),
fold it into **Next move** or note it as a 'playbook idea' open question
(playbook tools are chat-only).
"""

DAILY_RESEARCH_TARGET = (
    "[curiosity] Daily research pass. You OWN this mission — work it like a "
    "relentless operator, one focused pass (~10 tool calls).\n"
    "1. mission_get for your current mission, then goal_list for your goal "
    "ledger. Pick the ONE goal you can advance TODAY (wiki_list_questions / "
    "wiki_toc to see where the wiki is thin on it). No goals yet? Commit 2-3 "
    "with goal_set first.\n"
    "2. Advance it: web_search, then web_fetch the substantive sources.\n"
    "3. Record what you learned: wiki_write/wiki_patch the relevant pages, "
    "wiki_cite every real source, wiki_resolve_question anything you "
    "answered, wiki_ask new questions you uncovered.\n"
    "4. goal_update the goal you worked: what moved, in one or two lines. If "
    "it has stopped moving, say so honestly (status='stalled').\n"
    "5. End the pass with a share_thought IF you advanced a goal or learned "
    "something that changes the picture — a one-liner counts: 'Moved <goal>: "
    "<what changed> [[wiki-page]]'. It enforces the noise budget (1/day, "
    "quiet hours queue), so a blocked/queued result is fine. Skip only a "
    "genuinely empty pass.\n"
    "6. If you notice a repeatable routine worth automating, record it as an "
    "open question tagged 'playbook idea' — propose the playbook in a normal "
    "chat turn (playbook tools are chat-only)."
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
and ask directly: what mission do they want you to own? Offer one or two
concrete framings to make answering easy (the problem they most want off
their plate; what they'd hand a sharp new hire). Keep it short and warm; end
on the question.
"""


async def run_install_kickoff(ctx: PluginContext) -> None:
    """Post the one-time install kickoff moment (no tools — the reaction turn
    just speaks). The caller owns the once-only flag."""
    await ctx.send_muted_message(
        INSTALL_KICKOFF_TITLE,
        INSTALL_KICKOFF_CONTENT,
        channel="moment",
        source="curiosity",
    )


async def run_kickoff(ctx: PluginContext, statement: str) -> None:
    """Post the kickoff moment. Runs as a fire-and-forget task from
    mission_set; the short delay lets the mission_set turn finish streaming
    before the kickoff reaction turn starts competing for the loop."""
    await asyncio.sleep(KICKOFF_DELAY_S)
    try:
        await ctx.send_muted_message(
            KICKOFF_TITLE,
            _KICKOFF_CONTENT.format(statement=statement),
            channel="moment",
            source="curiosity",
            tools=KICKOFF_TOOLS,
        )
        log.info("mission kickoff moment posted")
    except Exception:  # noqa: BLE001
        log.warning("mission kickoff failed", exc_info=True)


def spawn_kickoff(ctx: PluginContext, statement: str) -> str:
    try:
        asyncio.get_running_loop().create_task(run_kickoff(ctx, statement))  # noqa: RUF006
        return "started"
    except RuntimeError:
        return "no event loop — kickoff skipped"
