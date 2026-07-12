"""review.py — the weekly review, phase-branched (9C on 8.2D).

Like the dream, the review is a schedule, not a code path:
`curiosity-weekly-review` fires Monday morning as an `agent_prompt`; the
prompt IS the routine, and it reads the CURRENT phase at fire time
(scope_list) to pick its branch. Setup phase reports the road to competency;
work phase reports the week's output. Both post ONE share_thought
(kind='review' — exempt from the routine daily cap; cadence is structural),
value first, ask last.

9.001: the setup branch opens with the phase line + qualification gap count,
scores the week against [[success-criteria]], and audits the agent's own
heartbeat (exists? convergence criterion in its target? verdicts accruing?) —
the weekly half of the safety net that reminds but never creates.
"""

from __future__ import annotations

from .prompts import (
    ASK_SHAPE,
    HEARTBEAT_NAME,
    OWNER_WORDS,
    PHASE_CHECK,
    PHASE_ONE_DOCTRINE,
    RATIFICATION_FORCING,
    SETUP_STAGE_DEFS,
    SETUP_WEEKLY_TITLE,
    WEEKLY_SCORES_SHAPE,
    WIKI_BINDING,
    WORK_WEEKLY_TITLE,
)

WEEKLY_REVIEW_TARGET = (
    "[curiosity] Weekly review — your scoreboard turn; the owner should feel "
    "a driven operator reporting, not a librarian summarizing. One focused "
    "pass (~10 tool calls). " + PHASE_CHECK + " " + WIKI_BINDING + " "
    + OWNER_WORDS + "\n"
    "Common prep (both branches): mission_get; goal_list and score every "
    "goal HONESTLY with goal_update — moved / done / stalled / dropped; a "
    "goal stalled 2+ weeks must be confronted (change the approach, ask what "
    "blocks it, or drop it with a written reason). Audit your setup: "
    "trigger_list — routines still right?; marketplace_search 1-2 mission "
    "keywords; wa_status / connector_list_connected for off-platform reach — "
    "skip any of these silently if the tool isn't available.\n"
    "SETUP BRANCH (agent_phase='setup'): " + PHASE_ONE_DOCTRINE + " "
    + SETUP_STAGE_DEFS + " HEARTBEAT AUDIT (from the trigger_list you "
    "already ran): '" + HEARTBEAT_NAME + "' must exist, its target must "
    "state a convergence criterion, and verdict lines must be accruing on "
    "[[setup-heartbeat]] — anything missing or malformed becomes this "
    "review's ONE action: fix it NOW (recreate/repair the trigger yourself; "
    "it is yours). DRIFT AUDIT: your heartbeat_report calls and the "
    "[[setup-heartbeat]] verdict lines must tell the same story — if the "
    "reported streak/gaps disagree with the page (or fires stopped "
    "reporting), say so in the review and correct whichever is wrong. "
    "SHAPE AUDIT (phase 10): [[job-description]] must still carry its four "
    "headed sections and read true to what you actually do now — repair "
    "drift with wiki_patch (a real role change is a plan_change_note "
    "kind='role_pivot' proposal instead, owner decides). ability_list: "
    "every ability re-scored this week (heartbeat did its job?), and your "
    "next 2-3 goals each carry expected_result + readiness — re-score "
    "readiness with goal_update where the week changed it. "
    + RATIFICATION_FORCING + "\n"
    "Post ONE share_thought(kind='review', title='" + SETUP_WEEKLY_TITLE
    + "'), citing [[mission-goals]] and [[role-charter]], in this exact "
    "shape:\n"
    "   - **Where I am** — open with the phase and stage in plain words "
    "(e.g. 'setting up — job description shared, waiting for you to read "
    "and approve') and N gaps "
    "between me and qualified (count them from your scopes + open "
    "questions); never a stage code.\n"
    "   - **Success check** — score the week against [[success-criteria]]: "
    "am I becoming the agent that page describes? If the page is still "
    "waiting for the owner's approval, say so — that approval is the ask below. "
    + WEEKLY_SCORES_SHAPE + "\n"
    "   - **Ladder** — every ability with its server-computed percent "
    "(ability_list; never state a percent you computed yourself); call out "
    "what moved and what regressed.\n"
    "   - **Scope scoreboard** — every scope with status and evidence; call "
    "out what regressed and why.\n"
    "   - **Timeline** — the goal schedule: on time / late, per goal.\n"
    "   - **Loops** — chased, closed, and still open ([[open-loops]]); act "
    "NOW on anything past its nudge date.\n"
    "   - **Value vs asks** — what you delivered ([[value-log]]) against "
    "what you asked for. Value first, ask last.\n"
    "   - **Plan changes** — added / dropped / reopened this week, each with "
    "the learning that caused it; 'none' is a finding too — say it plainly.\n"
    "   - **Road to work mode** — where the heartbeat streak stands against "
    "its convergence criterion; has a workflow validation run happened? "
    "which scopes have live feedback signals? Propose "
    "graduation (phase_advance — load the mission-changes skill the week "
    "before; its tools unlock the turn after loading) ONLY when every scope is competent or "
    "explicitly waivable AND the heartbeat streak has converged, citing "
    "per-scope signals — and on graduation demote your heartbeat to a "
    "maintenance cadence yourself (trigger_update).\n"
    "   - **I need** — exactly ONE ask at most, shaped " + ASK_SHAPE + "; if "
    "you need nothing, say what you'll do with the free rein.\n"
    "WORK BRANCH (agent_phase='work') — post ONE share_thought(kind='review', "
    "title='" + WORK_WEEKLY_TITLE + "'), citing [[mission-goals]], in this "
    "exact shape:\n"
    "   - **Done** — runs, outputs, goal movement (cite wiki pages).\n"
    "   - **Role wall** — score EVERY criterion on [[success-criteria]] "
    "this week (this is the work phase's core scoreboard). "
    + WEEKLY_SCORES_SHAPE + "\n"
    "   - **Insights** — what changed the picture this week.\n"
    "   - **Improve** — one concrete improvement to your own toolkit: a "
    "playbook diff, a cadence change, a plugin worth installing — leave the "
    "toolkit better than you found it. Post-graduation, check your old "
    "'" + HEARTBEAT_NAME + "' cadence still earns its cost — demote or "
    "delete it if not.\n"
    "   - **Next move** — ONE action YOU will take, ending 'say go and I'll "
    "do it' (needs owner) or 'already scheduled' (doesn't). Never end on "
    "suggestions for the owner to do.\n"
    "Do not message the owner beyond the review — it is the one output of "
    "this turn. A queued result (quiet hours) is fine."
)
