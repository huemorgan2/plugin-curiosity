# Phase 08 — boundaries + recovery: execution summary

Shipped: plugin-goalseek 2.4.0, plugin-curiosity 0.18.0.

## What landed

**goalseek 2.4.0**
- `goalseek_boundaries` table + `boundaries.py`: a pure owner-rule gate
  (family=`boundary`) evaluated in front of the 8-family policy gate in both
  `run()` and `run_batch()`. No active boundaries ⇒ exact pre-2.4.0 behavior.
- Action classes `outbound_contact` / `spend` / `delete`; classification
  precedence: explicit channel → delete-tool → spend-tool-or-amount → bare
  contact → ungoverned. Default-deny for governed classes once the regime is
  on (novel class → block, remedy names `policy_propose`).
- Rules: time windows (recipient- or owner-timezone, unknown/invalid tz
  fail-closed, overnight wrap), `approval_channels` (phone → always a card),
  `limits.per_day` and `limits.max_amount`.
- Server-counted honesty: `checks_count`/`denies_count`/`allows_today` bumped
  inside the effects session on every governed evaluation.
- Tools `policy_propose` (agent, convergent by title), `policy_confirm` /
  `policy_suspend` (owner cards, prompt_always), `policy_list`; REST
  `GET /boundaries`, `POST /boundaries/{id}/confirm|suspend`.
- Lifecycle: proposed → active (confirm stamps `confirmed_at`) → suspended.
  Spec's separate "confirmed" status collapsed into active+`confirmed_at`.

**curiosity 0.18.0**
- Seed-at-Agree: reaching S3 files the 3 default rules through
  `policy_propose` (origin "set at agree"), flag-gated on full success only —
  goalseek absent degrades visibly and retries at the next stage move.
- "My rules" strip: quotes active sentences verbatim + honest count line
  ("since {date}, {n} actions checked, {m} exceptions" / "no actions checked
  yet"); hidden when goalseek is absent or nothing is active.
- INCIDENT_PROTOCOL rides both phase prompts; the ORDER is the contract:
  stop first → self-report before discovery → owner-approved recovery →
  blameless postmortem → rule diff + test (advice is invalid) → announced
  freeze → earn-back — recovery and ambition never share a turn.

## Verification

- goalseek: 550 passed (36 boundary tests incl. the midnight-call
  regression); curiosity: 500 passed (12 new).
- Dojo on a real Luna (QA 8767, Gemini agent): 13/13.
  - Rules strip renders the 3 sentences verbatim, no jargon, honest fresh
    count ("no actions checked yet").
  - A real agent turn calling `goal_effect(channel=phone)` on a
    23:15-recipient-time item was DENIED: `policy_block` event with
    family=boundary, reason names "Quiet hours", attempted tool recorded,
    item never advanced, counters bumped on BOTH governing boundaries.
  - On reload the strip reads "since 2026-08-01, 2 actions checked,
    2 exceptions" — server-counted, not narrated.
  - Screenshot: `dojo_boundaries.png` (the agent also reported the block in
    owner words in chat, remedy included).

## Found live, fixed live

**Boundary block vs capability park ordering.** The first dojo run parked
the midnight call with family=`capability_missing` (phone tool not connected
on QA) and filed an ask to *connect the very tool the boundary forbids* —
the capability check ran before the boundary gate. Fixed precedence in both
paths: boundary **block** > capability park > policy evaluation, and a
capability park moves no boundary counters (nothing governed ran). 3 new
tests pin it (single, batch, counters). Unit suites can't catch this class:
the fakes register every tool, so the capability branch never fires — only
the real-Luna dojo exposed it.

## Learnings → future phases

1. **Gate-ordering bugs hide behind fully-stocked fakes.** Any phase that
   adds a new gate to a decision chain must dojo-test with a *missing*
   downstream dependency, not just a present one.
2. **Managed-dir layout is flat** (`managed_plugins/plugin_goalseek/` IS the
   python package). A nested rsync target silently leaves stale code running
   — verify with a grep for a new marker line after every sync.
3. Auto-filled item contacts make spends look like outreach — classification
   must check explicit channel/tool shape before falling back to `contact`.
4. Convergent-by-title propose lets two plugins seed the same defaults
   without dedup coordination.
5. `governing()` counts every matching boundary per check (2 boundaries
   governing one phone call → 2 checks / 2 denies). The strip's totals are
   evaluations, not actions — phase 09's metrics funnel should surface
   per-boundary rows, which stay per-action honest.

## Phase 09 feed-forward

Boundary counters (`checks_count`/`denies_count` per rule) are now a
server-computable metric source for the weekly note and the
promised-vs-delivered ledger.
