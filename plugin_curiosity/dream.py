"""dream.py — the nightly consolidation, as a scheduler target.

The dream is a schedule, not a loop: `curiosity-nightly-dream` (registered by
mission_set, kept current by _sync_schedules) fires at 02:00 as an
`agent_prompt`, and the fired turn performs the consolidation with the full
registered toolset. There is no dream code path in the plugin — the prompt IS
the routine, mirroring research.DAILY_RESEARCH_TARGET.

Design notes (phase-5 plan):
* Self-contained — re-reads the CURRENT mission via mission_get at fire time;
  no mission text is baked into the trigger.
* The 02:00 fire lands inside quiet hours (21:00–08:00), so the dream's
  share_thought queues automatically and drains after 08:00 — the "morning
  thought" comes free from the phase-4 guardrails. The tool is routine-kind,
  so the drained thought consumes the 1/day cap: "exactly one morning
  thought" is enforced structurally.
* Safe on an empty day: step 1 checks whether anything changed today and
  no-ops gracefully (wiki state is the ledger — a failed night's fire is
  picked up by the next one).
* Kept tight (~10 tool calls) so one over-long turn doesn't hit MAX_TURNS.
"""

from __future__ import annotations

DREAM_TARGET = (
    "[curiosity] Nightly dream: consolidate today's learning. Work quietly — "
    "the owner is asleep. One focused pass (~10 tool calls), then stop.\n"
    "1. mission_get for your current mission; wiki_toc and check updated_at "
    "for pages touched in the last day. If nothing changed since the last "
    "dream, reply 'quiet night — nothing to consolidate' and stop (no wiki "
    "writes, no share_thought).\n"
    "2. wiki_read the touched pages. Consolidate them with wiki_patch: merge "
    "duplicated notes, rewrite raw fragments into clear prose, tighten "
    "summaries, add [[links]] between related pages. Keep every citation.\n"
    "3. Update the question ledger: wiki_resolve_question anything today's "
    "research actually answered; wiki_ask sharper follow-ups that emerged "
    "from consolidating.\n"
    "4. Distill ONE morning thought — the single insight from today the owner "
    "should wake up to — and share it with share_thought (title it 'Morning "
    "thought', cite the [[wiki-page]] it lives on). It will queue through "
    "quiet hours and post in the morning; a queued/blocked result is fine.\n"
    "5. Do not message the owner directly — the queued thought is the only "
    "output. If today's material was too thin for a thought worth waking up "
    "to, skip step 4 entirely; a silent night beats a hollow thought."
)
