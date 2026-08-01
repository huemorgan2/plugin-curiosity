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
    HONEST_HORIZONS,
    MONTHLY_TITLE,
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
    + OWNER_WORDS + " " + HONEST_HORIZONS + "\n"
    "Common prep (both branches): CARD FIRST — this fire is self-directed "
    "spend: next_step_post(what='weekly review + scoring', produces='the "
    "weekly scoreboard post', cost_text='~10 tool calls', scheduled=true) "
    "then next_step_start; close it with next_step_done after the review "
    "posts. Then: mission_get; goal_list and score every "
    "goal HONESTLY with goal_update — moved / done / stalled / dropped; a "
    "goal stalled 2+ weeks must be confronted (change the approach, ask what "
    "blocks it, or drop it with a written reason). Audit your setup: "
    "trigger_list — routines still right?; marketplace_search 1-2 mission "
    "keywords; wa_status / connector_list_connected for off-platform reach — "
    "skip any of these silently if the tool isn't available. FEEDBACK DEBT "
    "(10.006): feedback_list(unactioned_only=true) — anything there is a RED "
    "item that outranks the rest of this review: change the implicated "
    "artifact NOW (design_map shows where it lives) and close it with "
    "feedback_act, or name the blocker in the review; never let one age a "
    "second week.\n"
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
    "   - **Timeline** — each goal by its honest horizon: dated goals on "
    "time / late; blocked goals by their unlock and whose move it is "
    "(never 'late'); your own work in agent-minutes.\n"
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
    "WORK BRANCH (agent_phase='work') — the weekly note is FIVE headed "
    "lines, short enough to read in an inbox preview; depth lives on the "
    "wiki, never in the note. Before writing: metrics_snapshot (quote its "
    "numbers verbatim — never compute or estimate a metric yourself) and "
    "proposal_list (what closed since last note, what's still open). Score "
    "EVERY criterion on [[success-criteria]] ON THE PAGE — "
    + WEEKLY_SCORES_SHAPE + " The page carries the depth; the note stays "
    "five lines. Then post ONE share_thought(kind='review', "
    "title='" + WORK_WEEKLY_TITLE + "'), citing [[mission-goals]], EXACTLY "
    "these five lines:\n"
    "   - **Ran** — what ran this week: runs, outputs, goal movement, one "
    "line (cite wiki pages).\n"
    "   - **Cost vs value** — what the week cost against what it returned, "
    "in the OWNER'S units (hours saved, messages handled, money) — numbers "
    "from metrics_snapshot and [[value-log]] only.\n"
    "   - **Health** — write 'No issues' ONLY when literally true: no "
    "incident, no overdue loop, no unactioned feedback, no boundary "
    "exception this week. Otherwise name the issue in one plain line — "
    "never soften it.\n"
    "   - **Proposal** — at most ONE improvement bet, opened for real with "
    "proposal_open (title + predicted payoff in owner units, e.g. 'saves "
    "you ~20 min/week') — a playbook diff, a cadence change, a plugin worth "
    "installing: leave the toolkit better than you found it. A normal week "
    "ALWAYS places its bet — 'nothing to improve' is never true; pick the "
    "smallest friction you met this week and call proposal_open, in this "
    "turn, before you post. If a proposal "
    "closed since the last note, LEAD with its verdict: 'predicted X, "
    "actual Y'. If one is still open, restate it in one line instead of "
    "opening another (the tool refuses a second). INCIDENT WEEK: recovery "
    "and proposals never share a turn — this line becomes 'no proposal "
    "this week — recovery first'. Post-graduation, check your old "
    "'" + HEARTBEAT_NAME + "' cadence still earns its cost — demote or "
    "delete it if not.\n"
    "   - **Next move** — ONE action YOU will take, ending 'say go and I'll "
    "do it' (needs owner) or 'already scheduled' (doesn't). Never end on "
    "suggestions for the owner to do.\n"
    "Do not message the owner beyond the review — it is the one output of "
    "this turn. A queued result (quiet hours) is fine."
)

# 11.008/M7: the monthly value ledger — promised vs delivered in the owner's
# own numbers. Same schedule mechanics as the weekly (static agent_prompt
# that reads current state at fire time); fires the 1st at 09:45, clear of
# the 09:00 daily and the Monday-09:30 weekly.
MONTHLY_REVIEW_TARGET = (
    "[curiosity] Monthly review — the value-ledger turn: promised vs "
    "delivered, in the owner's numbers. One focused pass (~12 tool calls). "
    + OWNER_WORDS + " " + HONEST_HORIZONS + "\n"
    "CARD FIRST: next_step_post(what='monthly review', produces='the "
    "monthly value report', cost_text='~12 tool calls', scheduled=true) "
    "then next_step_start; close it with next_step_done after the report "
    "posts. Gather, never guess: mission_get; metrics_snapshot (quote its "
    "numbers verbatim; a None metric is 'no data yet' — say that, never "
    "invent); goal_list; proposal_list; policy_list for boundary "
    "exceptions (skip silently if the tool isn't available); read "
    "[[success-criteria]] and [[owner-decisions]] for the numbers and "
    "words the owner actually agreed to at setup — those are what this "
    "month is scored against.\n"
    "If agent_phase='setup' (mission_get), the report is setup progress vs "
    "promise instead — where you are in plain words, what remains, and the "
    "first win's ETA in honest units; no opportunities list yet. Otherwise "
    "post ONE share_thought(kind='review', title='" + MONTHLY_TITLE
    + "'), citing [[value-log]], EXACTLY these lines:\n"
    "   - **Promised vs delivered** — each target the owner agreed to "
    "([[success-criteria]]) against what actually happened this month, "
    "from metrics_snapshot and [[value-log]]: met, missed, or no data — "
    "say which, plainly, no softening.\n"
    "   - **Cost and savings** — what the month cost against what it "
    "saved or made, in the owner's units; cite receipts.\n"
    "   - **Opportunities** — the top 1-3 next bets, EACH anchored to "
    "something the owner said or received: cite the [[owner-decisions]] "
    "quote or the value-log receipt it builds on — an opportunity with no "
    "anchor stays off the list. DOWNSELLS BELONG HERE: if something you "
    "run isn't earning its cost, proposing to shrink or drop it is a "
    "first-class opportunity — that honesty is the product.\n"
    "   - **Decision** — exactly ONE decision you need from the owner "
    "this month, phrased so one word answers it; if none, say 'nothing "
    "needed — next month runs itself'.\n"
    "INCIDENT MONTH: recovery and proposals never share a turn — a month "
    "spent on an incident reports recovery status under Promised vs "
    "delivered and lists NO new opportunities. Do not message the owner "
    "beyond the review — it is the one output of this turn. A queued "
    "result (quiet hours) is fine."
)
