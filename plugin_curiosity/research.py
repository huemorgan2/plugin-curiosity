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
]

KICKOFF_TITLE = "Mission kickoff"

# breathing room so the mission_set turn finishes streaming before the
# kickoff reaction turn starts competing for the loop (tests set this to 0)
KICKOFF_DELAY_S = 3.0

_KICKOFF_CONTENT = """\
Your mission was just set: {statement}

Do the mission kickoff NOW, in this turn — the owner should feel value in this
first session. Keep it tight (about 8-12 tool calls; depth comes from the
daily research schedule, not from this one turn):

1. Run 2-3 web_search queries on the core of the mission; web_fetch the one or
   two most substantive results.
2. Write what you learned into the wiki: flesh out [[mission-domain]] with a
   first researched pass (wiki_patch), and record each real source with
   wiki_cite. No uncited claims.
3. Record 3-5 sharp open questions to pursue next (wiki_ask), and put the ones
   that frame the mission on [[mission-open-questions]].
4. Then reply to the owner with the **Mission Kickoff** artifact, in this
   exact shape:
   - **Brief** — 3-5 lines: the mission in your own words and how you'll
     attack it.
   - **Quick win** — ONE concrete, immediately useful insight you just found,
     with its source URL.
   - **Open questions** — the 3-5 questions you recorded.
If a repeatable routine would serve the mission (a weekly scan, a digest),
note it as an open question — you can propose it as a playbook in a normal
chat turn later (playbook tools are chat-only).
"""

DAILY_RESEARCH_TARGET = (
    "[curiosity] Daily research pass. Work the mission like a curious new "
    "hire; keep it to one focused pass (~10 tool calls).\n"
    "1. mission_get for your current mission; wiki_list_questions and "
    "wiki_toc for where the wiki is thin.\n"
    "2. Pick the ONE most valuable open question or gap. Research it: "
    "web_search, then web_fetch the substantive sources.\n"
    "3. Record what you learned: wiki_write/wiki_patch the relevant pages, "
    "wiki_cite every real source, wiki_resolve_question anything you "
    "answered, wiki_ask new questions you uncovered.\n"
    "4. If — and only if — you found something the owner would genuinely "
    "want interrupted with, share it with share_thought (cite the wiki page "
    "or source; it enforces the noise budget, so a blocked/queued result is "
    "fine). Otherwise work quietly.\n"
    "5. If you notice a repeatable routine worth automating, record it as an "
    "open question tagged 'playbook idea' — propose the playbook in a normal "
    "chat turn (playbook tools are chat-only)."
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
