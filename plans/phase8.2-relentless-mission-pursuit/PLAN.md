# Phase 8.2 — Relentless mission pursuit: goals, drive, self-improvement

**Problem (owner-observed).** After mission_set the owner sees one kickoff and
then at most one reflection per day. Luna researches and *suggests* but never
commits, never proposes what SHE will do, never audits her own setup, never
asks for capabilities. It reads as a passive analyst, not an agent that cares.

**Root cause.** Every engagement surface in the plugin was designed for LOW
NOISE, none for VISIBLE DRIVE:

Current owner-visible touchpoints (complete inventory):
1. Missionless nag — fragment renews the mission ask every reply (0.4.3+).
2. `mission_set` → Mission Kickoff moment (~3 s later): Brief / Quick win /
   Open questions. Ends on open questions — suggestions, no commitment.
3. Daily research (scheduler, `DAILY_RESEARCH_TARGET`): "work quietly...
   otherwise share nothing." Owner usually sees zero output.
4. Nightly dream 02:00: one queued "Morning thought", and the prompt says
   "a silent night beats a hollow thought."
5. `share_thought`: hard cap 1 routine/day, quiet hours queue.
6. Mission prompt fragment: "keep the wiki current, share grounded insights" —
   librarian language, no goals, no change-the-world posture.

Nothing anywhere: sets goals, tracks progress, proposes actions Luna will take
herself, scans for missing capabilities, or reviews her own setup. That's the
gap between "she did research" and "she's ON it."

---

## Design: six mechanisms

### A. Goal ledger — Luna sets her own goals and is held to them
- New table `curiosity_goals` (id, statement, why, target_date, status:
  active|done|stalled|dropped, progress_note, updated_at).
- Tools: `goal_set`, `goal_update` (progress/status), `goal_list`
  (all auto_approve; goals are Luna's own commitments, not side effects).
- Kickoff (research.py `_KICKOFF_CONTENT`) grows step 5: "Commit to 2-3
  concrete goals with target dates (`goal_set`) and CLOSE the kickoff with
  them: 'Here's what I'm going after: ...'". The kickoff artifact gains a
  **My goals** section.
- `DAILY_RESEARCH_TARGET` reworked: step 1 becomes `goal_list` — pick the
  goal you can advance TODAY; after the pass, `goal_update` with what moved.
  Research serves goals, not generic "the most valuable open question".
- Wiki page `[[mission-goals]]` seeded by `_seed_wiki_stubs` as the
  human-readable mirror (goal_set/update write through to it).

### B. Bias to action — every artifact ends with "Next move"
Prompt-only changes, all three surfaces:
- Kickoff, daily research share_thought, and weekly review must END with
  **Next move**: ONE concrete action *Luna proposes to take herself*
  (a playbook she'll author, a trigger she'll create, a draft she'll produce,
  a plugin she wants installed) — with "say go and I'll do it" when it needs
  approval, or "I've already scheduled it" when it doesn't (autonomy rung
  permitting). Explicit anti-pattern line: "never end on a list of
  suggestions for the OWNER to do — end on what YOU will do."
- Mission prompt fragment rewritten from librarian to operator: "You own this
  mission and you are relentless about it: you keep goals ([[mission-goals]]),
  you advance one every day, you propose and take actions — not just
  suggestions. When you see a way to make a real difference, say so and ask
  to act."

### C. Capability-gap scan — "install these and I can make a real difference"
- No core change needed: `plugin_marketplace` already registers agent tools
  (`marketplace_search`, `marketplace_install`, ...). Soft dep, feature-detect
  via `ctx.tool_registry` like the scheduler tools.
- Kickoff gains step: run `marketplace_search` on mission keywords; if a
  plugin would materially help, name it in **Next move**: "Install plugin-X
  and I can actually DO Y instead of only reading about it."
- Weekly review (D) repeats the scan — the marketplace evolves, gaps reopen.
- Guardrail: propose installs, never `marketplace_install` uninvited
  (regardless of rung — installs change the agent itself; owner decides).

### D. Weekly mission review — the scoreboard turn
- New trigger `curiosity-weekly-review` (added to `_sync_schedules`, weekly,
  daytime, e.g. Mon 09:30 local) firing `WEEKLY_REVIEW_TARGET` (new prompt
  const, mirrors research.py style):
  1. `mission_get`, `goal_list`, wiki_toc.
  2. Score each goal honestly: moved / stalled / done. `goal_update` statuses.
  3. Self-setup audit: list own triggers (`trigger_list`), plugins in play,
     `marketplace_search` for gaps — "what about MY setup limits the mission?"
  4. Post ONE review via `share_thought(kind="review")`: **This week** (what
     I did) / **Scoreboard** (goals + status) / **Next week** (what I'll go
     after) / **I need** (one ask: a capability, a decision, an intro) /
     **Next move**.
- comms.py: new kind `"review"`, exempt from the routine daily cap (like
  kickoff/dream — its cadence is structural: the trigger fires weekly).
- Stalled-goal escalation: review prompt instructs — a goal stalled 2+ weeks
  must be confronted: change approach, ask the owner what's blocking, or
  `goal_update(status="dropped")` with the reason. Never let it rot silently.

### E. Louder daily presence (bounded)
- Daily research prompt: replace "if — and only if — ... otherwise work
  quietly" with "end the pass with a share_thought IF you advanced a goal or
  learned something that changes the picture — a one-line 'moved goal 2:
  ...' with the wiki citation counts. Skip only genuinely empty passes."
  Cap stays 1/day, so worst case is still one line a day — but the default
  flips from silent to visible progress.

### F. Outbound reach — pursue a direct line to the owner
The relationship must not end at the platform tab. Luna actively works to get
connected to the owner's real channels — email, WhatsApp — so she can reach
them where they live.
- Existing surface (no core change): plugin-whatsapp registers `wa_send` /
  `wa_status`; plugin-connectors registers `connector_search_apps` /
  `connector_list_connected` / `connector_request_enable` (Composio: Gmail,
  ...). All soft deps — feature-detect via `ctx.tool_registry`.
- **Reach check** in kickoff step and weekly-review self-audit: can I reach
  the owner off-platform? (`wa_status` connected? `connector_list_connected`
  shows an email app?) If not, the **I need** ask becomes: "Connect me to
  your WhatsApp/email — the mission doesn't pause when you close this tab:
  I can send you the morning thought, flag urgent findings, and nudge on
  stalled goals where you'll actually see them." If the channel plugins are
  not installed at all, this merges with the capability-gap ask (C):
  "install plugin-whatsapp / plugin-connectors and connect me."
- **Once connected**: mission fragment rails grow one line — deliver
  genuinely urgent, grounded findings via the connected channel; the weekly
  review and morning thought MAY go out there when the owner hasn't opened
  the platform that day. Same noise budget applies (share_thought caps count
  regardless of channel); quiet hours apply doubly to outbound.
- Guardrails: never message third parties about the mission uninvited —
  outbound engagement is owner-only; connecting a channel always goes through
  its own consent/OAuth flow (`connector_request_enable`, WhatsApp pairing) —
  Luna asks, the owner connects.

## Owner-visible cadence after 8.2
- Install → mission ask every reply (8.1 kickoff makes it immediate).
- mission_set → kickoff with goals + Next move + plugin asks.
- Daily → one-line progress note (goal-cited) most days.
- Weekly → scoreboard review with self-audit and one ask.
- Anytime → stalls confronted, capability gaps named, actions proposed.
- Off-platform → until connected, Luna asks for a WhatsApp/email line; once
  connected, urgent findings and unseen reviews reach the owner there.

---

## Phases

### Phase A — goal ledger
models.py `Goal` table; `goals.py` (store + 3 tools); seed `[[mission-goals]]`
stub; tests: set/update/list round-trip, write-through to wiki, tools
registered on load.

### Phase B — prompt surgery
research.py `_KICKOFF_CONTENT` (goals step + My goals + Next move +
marketplace scan), `DAILY_RESEARCH_TARGET` (goal-driven + visible progress
note), mission.py `prompt_fragment` (operator language, both branches).
Tests: prompt-content assertions (key phrases present; "work quietly" gone).

### Phase C — weekly review + outbound reach
`review.py` with `WEEKLY_REVIEW_TARGET` (incl. reach check from F);
`_sync_schedules` grows the weekly trigger (idempotent, spec-drift covered
like the existing two); comms.py `kind="review"` exemption; kickoff and
mission fragment gain the reach-check / connected-channel lines (F).
Tests: schedule sync creates/repairs the trigger; review kind bypasses the
routine cap; quiet-hours queueing still applies; prompts reference wa_/
connector_ tools only behind feature-detection language.

### Phase D — verify live + ship
- QA Luna (port 8123 procedure): fresh mission → kickoff shows goals +
  Next move + a marketplace ask; fire the weekly trigger manually
  (scheduler API) → scoreboard review posts; goal tools round-trip in chat.
- Bump to 0.6.0 (all three stamps — test_manifest.py guards), commit, package,
  publish to Render dev marketplace; execution_summary.md here.

## Dependencies / interactions
- Needs scheduler (soft, as today) for daily/weekly/dream; wiki hard (as today).
- marketplace tools: soft — absent tools skip the scan gracefully.
- plugin-whatsapp / plugin-connectors: soft — absent, the reach ask becomes
  an install ask; present-but-unconnected, it becomes a connect ask.
- Independent of 8.1 (prompt primacy/kickoff); both touch `prompt_fragment`
  missionless text — if 8.1 executes first, rebase B on it.

## Non-goals
- Autonomy-rung enforcement changes; approval-gate changes.
- Multi-mission support; goal hierarchies/OKRs.
- Core changes — none required (verified: marketplace agent tools exist).

## Risks
- Noise: bounded by existing caps + structural weekly cadence; daily note is
  one line. If an owner complains, the daily-note instruction is one string.
- Marketplace search quality: if the index is thin, asks may be weak — the
  prompt says "only name a plugin you'd actually use this week".
- Prompt-only mechanisms (B, E) depend on model compliance; the ledger (A)
  and trigger (C, D) are structural and survive weak compliance.
- Outbound (F) can feel invasive if overdone: bounded by the same caps and
  quiet hours, owner-only, and "only when the platform wasn't opened today";
  the owner can disconnect the channel at any time and Luna must not re-ask
  more than once a week (the review's single **I need** slot).
