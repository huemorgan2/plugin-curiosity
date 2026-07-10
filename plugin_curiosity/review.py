"""review.py — the weekly review, phase-branched (9C on 8.2D).

Like the dream, the review is a schedule, not a code path:
`curiosity-weekly-review` fires Monday morning as an `agent_prompt`; the
prompt IS the routine, and it reads the CURRENT phase at fire time
(scope_list) to pick its branch. Setup phase reports the road to competency;
work phase reports the week's output. Both post ONE share_thought
(kind='review' — exempt from the routine daily cap; cadence is structural),
value first, ask last.
"""

from __future__ import annotations

from .prompts import ASK_SHAPE, PHASE_CHECK, SETUP_WEEKLY_TITLE, WORK_WEEKLY_TITLE

WEEKLY_REVIEW_TARGET = (
    "[curiosity] Weekly review — your scoreboard turn; the owner should feel "
    "a driven operator reporting, not a librarian summarizing. One focused "
    "pass (~10 tool calls). " + PHASE_CHECK + "\n"
    "Common prep (both branches): mission_get; goal_list and score every "
    "goal HONESTLY with goal_update — moved / done / stalled / dropped; a "
    "goal stalled 2+ weeks must be confronted (change the approach, ask what "
    "blocks it, or drop it with a written reason). Audit your setup: "
    "trigger_list — routines still right?; marketplace_search 1-2 mission "
    "keywords; wa_status / connector_list_connected for off-platform reach — "
    "skip any of these silently if the tool isn't available.\n"
    "SETUP BRANCH (agent_phase='setup') — post ONE share_thought("
    "kind='review', title='" + SETUP_WEEKLY_TITLE + "'), citing "
    "[[mission-goals]] and [[role-charter]], in this exact shape:\n"
    "   - **Scope scoreboard** — every scope with status and evidence; call "
    "out what regressed and why.\n"
    "   - **Timeline** — the goal schedule: on time / late, per goal.\n"
    "   - **Loops** — chased, closed, and still open ([[open-loops]]); act "
    "NOW on anything past its nudge date.\n"
    "   - **Value vs asks** — what you delivered ([[value-log]]) against "
    "what you asked for. Value first, ask last.\n"
    "   - **Plan changes** — added / dropped / reopened this week, each with "
    "the learning that caused it; 'none' is a finding too — say it plainly.\n"
    "   - **Road to work mode** — S4: has a workflow validation run "
    "happened?; S5: which scopes have live feedback signals? Propose "
    "graduation (phase_advance) ONLY when every scope is competent or "
    "explicitly waivable, citing per-scope signals.\n"
    "   - **I need** — exactly ONE ask at most, shaped " + ASK_SHAPE + "; if "
    "you need nothing, say what you'll do with the free rein.\n"
    "WORK BRANCH (agent_phase='work') — post ONE share_thought(kind='review', "
    "title='" + WORK_WEEKLY_TITLE + "'), citing [[mission-goals]], in this "
    "exact shape:\n"
    "   - **Done** — runs, outputs, goal movement (cite wiki pages).\n"
    "   - **Insights** — what changed the picture this week.\n"
    "   - **Improve** — one concrete improvement to your own toolkit: a "
    "playbook diff, a cadence change, a plugin worth installing — leave the "
    "toolkit better than you found it.\n"
    "   - **Next move** — ONE action YOU will take, ending 'say go and I'll "
    "do it' (needs owner) or 'already scheduled' (doesn't). Never end on "
    "suggestions for the owner to do.\n"
    "Do not message the owner beyond the review — it is the one output of "
    "this turn. A queued result (quiet hours) is fine."
)
