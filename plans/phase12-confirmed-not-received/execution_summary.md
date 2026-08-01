# Phase 12 — execution summary

**Shipped: plugin-curiosity 0.20.0** (2026-08-01). Incident response: the
marketplace agent `vaselin-shiran-personal-trainer` created a mission before
the owner said anything, never validated it, and streamed a long deep-pass
artifact — violating revision-2 Law 1 ("the mission is confirmed, not
received") and Law 2 ("no token is spent that the human couldn't have seen
coming"). All four root causes are closed, in code (tool-layer gates), not
prose.

## What changed

1. **Timeout-proceed deleted** (`research.py`). `CONFIRM_NOTE_TIMEOUT` is
   gone. An unconfirmed at-gate mission older than 12 h now earns ONE
   flag-guarded muted re-ask (`CONFIRM_NUDGE_*`: mission_get, ≤4 lines,
   reflect the mission back, ask for the yes, "you never proceed on your
   own"). The deep S0→S2 pass fires **only** from `mission_confirm`.
   Crash-recovery (confirmed-but-never-spawned) and the past-S0 grandfather
   branches are unchanged. Generic `flag_get`/`flag_set` helpers now back
   both the deep-pass claim and the nudge claims.

2. **Draft reaper → draft nudger** (`mission.py`). `reap_stale_draft` is now
   `nudge_stale_draft`: a >24 h unconsumed intake draft earns ONE
   flag-guarded nudge carrying the owner's verbatim words ("is this the
   mission you want me to own?") and an explicit "Do NOT call mission_set
   now". It never promotes; the draft stays safe forever.
   Mission-active draft clearing is unchanged.

3. **Recurring schedules wait for the yes** (`mission.py`, `__init__.py`).
   `schedules_gated()` gates `mission_set` / `mission_refine` /
   `mission_schedules_sync` / on-load sync behind confirmed-or-past-S0;
   `mission_confirm` registers the four triggers. On load, a still-gated
   mission gets `retract_schedules()` — the upgrade-path repair that
   withdraws triggers a pre-0.20 version registered at `mission_set`
   (they come back whole on confirm).

4. **Intake prompt rules** (`MISSION_GATE_FLOW` + state block, missionless
   fragment, `mission_draft`/`mission_set`/`mission_get` steers). Detection
   requires work the owner **hands YOU to own** — passing mentions are never
   a mission. "NEXT message ALWAYS ends intake" → the next **ON-TOPIC**
   message ends intake (any engagement, however thin; one-round ban and
   impatience-overrides stay). New DETOUR rule: a reply about something else
   never ends intake and is never the mission — handle it fully, keep the
   draft safe, close with one line renewing the thread.

5. **Auto-proceed promises purged everywhere.** `BRIEF_CONTENT`,
   `mission_confirm`/`mission_set` descriptions, the prompt fragment's
   confirm line (which also gained: the owner engaging you to start the work
   counts as a yes), and the owner-facing overview "needs from you" card all
   now say the same thing: nothing deep runs without the yes.

## Verification

Full suite: **539 passed** (`pytest -q`). New/updated coverage:
- unit 1–2: `test_stale_unconfirmed_mission_nudges_once_never_proceeds`,
  `test_confirm_nudge_flag_survives_process_restart` — no KICKOFF post ever
  without confirm; nudge posts exactly once across janitor re-runs and
  process restarts; the yes still releases the pass afterward.
- unit 3: `test_stale_draft_nudges_once_and_never_promotes`,
  `test_draft_nudge_flag_survives_process_restart` — no mission, no identity
  write, no triggers, no wiki; verbatim words in the nudge.
- unit 4: `test_mission_set_registers_no_schedules`,
  `test_confirm_registers_schedules`, `test_schedules_sync_tool_gated_until_confirm`,
  `test_retract_schedules_withdraws_pre_phase12_registrations`,
  `test_schedules_not_gated_once_confirmed_or_past_s0`.
- unit 5: existing confirm-releases-exactly-once tests green, untouched.
- unit 6: prompt-shape tests for on-topic/detour/hands-YOU rules and the
  absence of every auto-proceed promise.
- Ten older tests that asserted the pre-phase12 "schedules register at
  mission_set" contract were updated to confirm-first.

## Version

0.20.0 — behavior change, flag rows only (`confirm_nudge_sent:<mission_id>`,
`draft_nudge_sent:<draft_id>`), no schema migration. Three stamps aligned:
`pyproject.toml`, `plugin_curiosity/luna-plugin.toml`, `PluginManifest`.
