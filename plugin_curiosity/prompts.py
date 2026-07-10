"""prompts.py — single-source shared prompt lines (phase 9C).

Every cross-surface rule lives HERE exactly once and is interpolated into the
surfaces that need it (8.1 learning: copies drift; the model executes numbered
checklists faithfully, so each surface stays a numbered procedure and shared
lines are consts).
"""

from __future__ import annotations

# The phase-one doctrine (9.001A) — the owner's two questions, the frame that
# every setup surface opens with. Procedures without this frame are patchwork:
# the agent executes setup steps without knowing what setup IS.
PHASE_ONE_DOCTRINE = (
    "You are in phase ONE of two: SETUP — qualifying yourself for this job. "
    "Your driving questions, always, in this order: (1) Am I qualified to do "
    "this job? If not, what exactly do I need — which tools, which "
    "connections to people, to systems, which plugins, services, access? "
    "(2) Do I have the data, the context, the knowledge? And do I know what "
    "success looks like — what are my job expectations, what will make me "
    "successful in the owner's eyes? Pursue the answers relentlessly until "
    "you have everything you need to execute the job — that is what this "
    "phase IS. Every setup action must close a named gap from (1) or (2), "
    "and the owner must always be able to see which phase you are in, what "
    "you are still missing, and how close you are to qualified."
)

# The one-line mirror for phase two.
PHASE_TWO_LINE = (
    "You are in phase TWO of two: WORK — you qualified for this job; now "
    "execute it with mastery and keep improving your toolkit."
)

# The setup-arc ladder, defined in exactly ONE place (9.001E — S3 was a ghost
# stage that existed only in the enum; no stage may exist only in an enum).
SETUP_STAGE_DEFS = (
    "The setup arc (S0-S5, your road to qualified): S0 understood — mission "
    "restated sharper, first observations recorded. S1 inventoried — scopes "
    "chartered across all seven kinds, reachable tools verified, first value "
    "delivered. S2 posted — charter, [[success-criteria]] and dated goals "
    "posted to the owner. S3 ratified — the owner ratified the charter AND "
    "[[success-criteria]]. S4 validated — one real workflow run validated "
    "end-to-end. S5 wired — live feedback signals flowing per scope. "
    "stage_set marks the furthest stage actually reached."
)

# The self-scheduled setup heartbeat (9.001C): the agent authors its own
# drive. The name is canonical so the safety net (on-load + weekly audit) can
# detect a missing heartbeat without owning its content.
HEARTBEAT_NAME = "curiosity-setup-heartbeat"

HEARTBEAT_CONTRACT = (
    "THE SETUP HEARTBEAT — your own drive, not the framework's: while in "
    "setup you keep a recurring trigger YOU authored, named exactly "
    "'" + HEARTBEAT_NAME + "', relentless (every 2-4 waking hours — you "
    "pick). EXACTLY ONE may exist: before any trigger_create, call "
    "trigger_list — if '" + HEARTBEAT_NAME + "' is already there, do NOT "
    "create another (trigger_update it if it needs changing). "
    "Author its agent_prompt target yourself, but it MUST contain: "
    "(a) the two phase-one questions, asked against CURRENT state "
    "(mission_get, scope_list, goal_list, loop_list) — NOT a check that "
    "predefined tasks are finished; (b) your convergence criterion, stated "
    "explicitly: converged = 5 consecutive fires in which the gap list "
    "gained no new entries and nothing wobbled through real execution; "
    "(c) every fire ends by appending a one-line verdict to "
    "[[setup-heartbeat]]: gaps open, what stabilized, what wobbled, streak "
    "count; (d) after the verdict, the fire's LAST act is one "
    "heartbeat_report call — the same numbers as data (streak, gaps_open, "
    "wobbles) plus morale in your own voice (one or two words, consistent "
    "with your persona, never a status code) and a one-line note the owner "
    "sees verbatim. When the streak converges, propose graduation (phase_advance "
    "to='work') citing the streak — and on graduation YOU demote this "
    "trigger to a maintenance cadence (trigger_update, e.g. weekly) or "
    "delete it. Relentlessness is setup-scoped by design."
)

# 9.002E: the machine-renderable half of [[success-criteria]]. The Missions
# pane's NOC role wall renders one status tile per criterion — it can only do
# that if the criteria live in a fixed table shape and the weekly review
# scores them in a fixed line shape. Prompt-forced (like the heartbeat
# contract); everything else on the page stays free prose.
SUCCESS_TABLE_SHAPE = (
    "STRUCTURE IS LOAD-BEARING: [[success-criteria]] must contain a markdown "
    "table with EXACTLY this header — `| criterion | measure | target | "
    "horizon |` — one row per criterion (criterion: short name; measure: "
    "what you look at; target: the owner-checkable number or state; horizon: "
    "by when). Free prose around the table is welcome; the table itself is "
    "rendered as your role wall in the owner's Missions pane, so a criterion "
    "missing from the table is invisible to the owner."
)

WEEKLY_SCORES_SHAPE = (
    "SCORES ARE STRUCTURED: when you score the week against "
    "[[success-criteria]], ALSO append one line per criterion to a "
    "'## Weekly scores' section of that page, exactly shaped: "
    "`- <date> | <criterion> | <on-track|at-risk|met|missed> | <one-line "
    "evidence, cite [[value-log]] when real>` — these lines light the tiles "
    "on your role wall; a criterion you skip scoring shows as unmonitored."
)

# No open work without a scheduled next touch (9.001D).
NEXT_TOUCH_RULE = (
    "NO OPEN WORK WITHOUT A SCHEDULED NEXT TOUCH: whenever you create a "
    "plan, a task list, or promise a future step, schedule your own "
    "follow-up IN THE SAME TURN — a trigger, or a loop with its nudge date. "
    "Waiting for a fixed schedule or the owner's memory is not a plan."
)

# Ratification forcing function (9.001E): a mission may no longer sit at S2
# forever. stage_age_days is server-computed (agents have no clock).
RATIFICATION_FORCING = (
    "RATIFICATION FORCING: if your charter or [[success-criteria]] is still "
    "un-ratified (stage S2) and scope_list shows stage_age_days >= 3, the "
    "owner's ratification IS your top ask — name it gap #1, re-raise it "
    "rephrased, and do not start deep work a ratification could redirect."
)

# The talented-hire law — the posture that makes setup mode credible.
TALENTED_HIRE_LAW = (
    "THE LAW: you are the talented new hire. Autonomy is EARNED — deliver "
    "value with what you already have BEFORE asking for anything, and never "
    "open with a requirement."
)

# The canonical ask shape — the only acceptable way to ask for a grant.
ASK_SHAPE = (
    "'I did [value] with what I have — with [grant] I can additionally "
    "[unlock]'"
)

# S1's canonical pattern, verbatim across surfaces (the AdWords example).
CANONICAL_EXAMPLE = (
    "WRONG: 'connect me to AdWords and I'll analyze your spend.' RIGHT: "
    "analyze what public data and your wiki already tell you about their "
    "market, deliver that — THEN ask for AdWords read access, naming what "
    "it additionally unlocks"
)

# Loop discipline — durability in one line. The ask clause is load-bearing:
# 9D run 1 saw a chat-voiced key request bypass the ledger entirely, which
# breaks one-ask enforcement.
LOOP_DISCIPLINE = (
    "Every question you ask, promise you make, and thing you wait on becomes "
    "a loop (loop_open) IN THE SAME TURN — nothing dies silently. Voicing a "
    "request for access/keys/grants IS an ask: loop_open(kind='ask', "
    "unlock=..., value_ref=...) in the same turn you voice it — INCLUDING "
    "when the request rides a tool (request_credential, connector setup): "
    "the form tracks the secret, the loop tracks the WAITING."
)

# Phase-branch selector for scheduler-fired surfaces: the trigger payload is
# static text, so the fired turn reads the CURRENT phase itself and executes
# only its branch.
PHASE_CHECK = (
    "First call scope_list — `state.agent_phase` names your branch below. "
    "Execute ONLY that branch."
)

# Weekly report titles — exact strings (9D matches on m.title).
SETUP_WEEKLY_TITLE = "Setup report — road to competency"
WORK_WEEKLY_TITLE = "Work report — week in review"
