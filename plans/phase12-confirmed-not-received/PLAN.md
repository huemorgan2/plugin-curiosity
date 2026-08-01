# Phase 12 — Confirmed, not received (no unconfirmed spend, ever)

Trigger: production incident (marketplace agent `vaselin-shiran-personal-trainer`,
2026-08-01). After a curiosity upgrade the agent — before the owner said
anything — created a mission, never validated it, and streamed long scaffolding
text. Root causes, all shipped behavior in ≤0.19.0:

1. **The 12 h timeout-proceed** (`research.maybe_start_deep_kickoff`): an
   unconfirmed mission "proceeds by default" — and the janitor runs **on plugin
   load**, so the upgrade itself fires the deep pass for any pre-existing
   S0/unconfirmed mission (`confirmed_at` is a new column → every pre-0.13
   mission qualifies).
2. **The 24 h draft reaper** promotes an intake draft to a mission **verbatim,
   with zero validation**, through the full `mission_set` path (wiki, identity,
   schedules, brief).
3. **"The owner's NEXT message ALWAYS ends intake"** — a reply about anything
   else force-triggers `mission_set` + kickoff; mission detection latches onto
   work mentioned in passing.
4. **Recurring schedules register at `mission_set`** — daily research / dream /
   weekly fires spend tokens on a mission the owner never confirmed.

All four violate revision-2 of the vision ([phase11 vision.md](../phase11-onboarding-revamp/vision.md)):
Law 1 *"the mission is confirmed, not received"*, Law 2 *"no token is spent
that the human couldn't have seen coming"*, and the adoption arc's step-2 exit
condition (*"Human confirms: 'yes, that's it'"*). Silence-is-consent was
designed for small announced steps after trust exists — never for the mission
itself.

Doctrine (phase11 closing): flows belong in the tool layer — these gates are
code-side, not prose-side.

## Changes

- **research.py — timeout-proceed → one-time re-ask.** Delete
  `CONFIRM_NOTE_TIMEOUT`. `maybe_start_deep_kickoff`: an unconfirmed at-gate
  mission older than `CONFIRM_TIMEOUT_H` gets ONE flag-guarded muted nudge
  (reflect the mission back, ask for the yes/redirect, ≤4 lines, no other
  work) — the deep pass fires **only** from `mission_confirm`. Crash-recovery
  (confirmed-but-never-spawned) and past-S0 grandfather branches unchanged.
  Generic flag helpers shared with the deep-pass flag.
- **mission.py — reaper → nudger.** `reap_stale_draft` →
  `nudge_stale_draft`: a >24 h draft posts ONE flag-guarded nudge that
  re-raises the ask with the owner's verbatim words ("is this the mission you
  want me to own?") and keeps the draft safe forever. Never promotes.
  Mission-active draft clearing unchanged.
- **mission.py — schedules gated on the yes.** `mission_set` / `mission_refine`
  / `mission_schedules_sync` / on-load sync register the four recurring
  triggers only when the mission is confirmed or past S0 (grandfathered);
  `mission_confirm` registers them. On-load additionally **retracts**
  schedules a pre-0.20 version registered for a still-unconfirmed at-gate
  mission (best-effort raw-handler deletes, like the heartbeat dedupe).
- **Intake prompts — on-topic rule.** `MISSION_GATE_FLOW` (+ state block,
  missionless fragment, `mission_draft`/`mission_get` steers): detection
  requires work the owner is handing YOU — a passing mention on a detour is
  never the mission. "NEXT message ALWAYS ends intake" → the next **on-topic**
  message ends intake (any engagement, however thin, saves — the one-round ban
  and impatience-overrides stay); a detour message is handled fully, the draft
  stays safe, the reply closes with one line renewing the thread; never save
  off a detour.
- **No auto-proceed promises.** `BRIEF_CONTENT` drops "proceed within about
  half a day" → "say go and I'll dig in; until then I stay light". Same purge
  in `mission_confirm`'s description and the prompt fragment's confirm line —
  which also gains: the owner engaging you to start the work counts as a yes
  (call `mission_confirm` then).

## Testable units

| # | Unit | Test |
|---|---|---|
| 1 | No timeout-proceed | backdated unconfirmed mission → janitor "nudged", no KICKOFF post, nudge posted once; repeat call → "already nudged", no second post |
| 2 | Upgrade path | on-load janitor on at-gate unconfirmed mission never spawns the deep pass |
| 3 | Draft never promotes | backdated draft → "nudged", draft retained, no mission created; nudge carries verbatim words; repeat → "already nudged"; mission-active clearing unchanged |
| 4 | Schedules wait for the yes | `mission_set` → zero triggers registered; `mission_confirm` → all four; on-load retracts pre-0.20 registrations while unconfirmed; grandfathered/confirmed sync unchanged |
| 5 | Confirm still releases exactly once | existing unit-5 tests green (confirmed branch untouched) |
| 6 | Prompt shapes | gate flow carries on-topic + detour + handing-YOU rules; brief/confirm surfaces carry no auto-proceed promise |

## Regression gate

Full pytest suite green (intake/kickoff/mission/journey/next-steps suites
updated where they asserted the old contracts).

## Version

plugin-curiosity **0.20.0** (behavior change; flag rows only, no schema
migration). All three stamps (pyproject, luna-plugin.toml, manifest).

## Exit

`execution_summary.md`; tag + push plugin repo; package + publish 0.20.0 to
marketplaces.com.ai.
