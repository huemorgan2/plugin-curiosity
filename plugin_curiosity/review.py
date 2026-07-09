"""review.py — the weekly mission review, as a scheduler target.

Phase 8.2 mechanism D. Like the dream, the review is a schedule, not a code
path: `curiosity-weekly-review` (registered by mission_set, kept current by
_sync_schedules) fires Monday morning as an `agent_prompt`; the prompt IS the
routine. It re-reads the CURRENT mission and goal ledger at fire time.

The review is the drumbeat that makes the pursuit visible: an honest
scoreboard of the goals, a self-audit of Luna's own setup against the mission
(installed plugins, schedules, off-platform reach), exactly ONE ask of the
owner, and a Next move. It posts via share_thought(kind='review') — exempt
from the routine daily cap (its cadence is structural: the trigger fires
weekly), still grounded and quiet-hours aware.
"""

from __future__ import annotations

WEEKLY_REVIEW_TARGET = (
    "[curiosity] Weekly mission review. You own this mission — this is your "
    "scoreboard turn, and the owner should feel a driven operator reporting, "
    "not a librarian summarizing. One focused pass (~10 tool calls).\n"
    "1. mission_get for your current mission; goal_list for the ledger; "
    "wiki_toc for what changed this week.\n"
    "2. Score every goal HONESTLY with goal_update: moved / done / stalled. "
    "A goal stalled 2+ weeks must be confronted — change the approach, ask "
    "the owner what's blocking, or drop it with a written reason "
    "(status='dropped'). Never let one rot silently.\n"
    "3. Audit your own setup against the mission: trigger_list — are your "
    "routines still right? If you have marketplace_search, scan 1-2 mission "
    "keywords — is there a plugin that would let you DO more? If you have "
    "wa_status / connector_list_connected, check your off-platform reach to "
    "the owner (WhatsApp / email). What about YOUR setup limits the mission? "
    "Skip any of these silently if the tool isn't available.\n"
    "4. Post ONE review with share_thought(kind='review', title='Weekly "
    "mission review'), citing [[mission-goals]], in this exact shape:\n"
    "   - **This week** — what YOU did (2-4 lines, cite wiki pages).\n"
    "   - **Scoreboard** — each goal with status: moved/done/stalled/dropped.\n"
    "   - **Next week** — the ONE goal you'll push hardest and how.\n"
    "   - **I need** — exactly ONE ask of the owner (a capability to "
    "install, a channel to connect me to, a decision, an intro) — the thing "
    "that would most unblock the mission. If you truly need nothing, say "
    "what you'll do with the free rein instead.\n"
    "   - **Next move** — ONE concrete action YOU will take, ending with "
    "'say go and I'll do it' (needs owner) or 'already scheduled' (doesn't). "
    "Never end on suggestions for the owner to do.\n"
    "5. Do not message the owner beyond the review — it is the one output of "
    "this turn. A queued result (quiet hours) is fine."
)
