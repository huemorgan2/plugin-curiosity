# Luna project feedback — what to change to make the agent more able

Source: phase 10 (FDE job setup, 10.001–10.003) plus the five-role resilience
dojo suite (`luna/dojo/tests/role-resilience/five-roles.mjs`, first run 34/39).
Every item below was observed on a live Luna, not inferred. Items marked
**fixed** already shipped during phase 10; the rest are recommendations for
the Luna core.

## What already changed because of this work (fixed)

1. **Marketplace search had a structural recall gap** — `marketplace_search`
   matched the query as a literal substring of name+description. r2 ("Etsy
   shipping labels") searched five owner-vocabulary terms, got zero hits every
   time, and told the owner "zero plugins available" while plugin-charts,
   plugin-connectors, and plugin-web-access sat in the index. An empty result
   was indistinguishable from an empty marketplace. Fixed in luna 032:
   zero-hit-with-query returns the full catalog with a note so the agent
   judges relevance by description. Broader lesson: **any tool whose empty
   result is ambiguous ("no matches" vs "nothing exists") will mislead the
   agent**; return enough context to tell the two apart.

2. **Agents parrot tool-output jargon to owners — and a prompt rule alone
   does not stop it.** Tools that return stage codes (S0..S5), enum values,
   or internal names get quoted verbatim in chat ("Setup stage: still S0" —
   r5 live chat). Curiosity 0.9.3 added an explicit prompt mandate to
   translate tool-returned codes; the r5 rerun leaked anyway. What worked is
   0.9.4: the tool result itself carries the owner words next to the code
   (`setup_stage_owner_words`), and computed reason strings use stage words,
   never codes — yet r5-rerun2 still leaked once in a diagnostic list. The
   full conclusion after three runs: **if the agent must never say a code,
   don't make the code its working vocabulary either.** Curiosity's setup
   protocol instructs the agent in S-codes (`stage_set('S2')`), so it thinks
   in them and enumeration-style replies pull them out. Recommendation
   (curiosity 0.10.0, and a pattern for every plugin): make the plain words
   the enum values themselves (`understood`..`wired`); codes should not
   exist anywhere an LLM reads or writes. Data-shape mitigations
   (plain-language sibling fields, worded reason strings) are still worth
   shipping — they reduce the rate — but vocabulary design is the fix.

3. **No self-heal path for background schedules.** When r5's triggers were
   wiped server-side, the agent noticed and reported honestly, but its only
   repair tool was raw `trigger_create` — it hand-rebuilt one of four
   schedules. Plugins that own a *set* of triggers need an idempotent
   resync tool (curiosity 0.9.3 `mission_schedules_sync`). Core
   recommendation: the scheduler plugin could offer a declarative
   "desired-set" registration so any plugin gets reconciliation for free.

## Where the agent is already strong (keep and protect)

4. **Self-recovery across tool failures is real.** When `mission_set` died
   mid-turn (10.001), the agent completed the same outcome through
   `mission_refine` without being told. Redundant, overlapping tools are a
   resilience feature, not bloat.

5. **Honesty under uncertainty held everywhere.** r2 reported a genuine gap
   instead of hallucinating a plugin, then researched real products (Shippo,
   EasyPost, Pirate Ship). r5 reported the trigger wipe instead of papering
   over it. Nothing in phase 10 pressured the agent into confabulation; keep
   prompt budgets tight so this survives.

## Core platform changes that would make the agent more able

6. **Turns die with their SSE stream.** A page reload cancels the in-flight
   turn; scheduler fires report "emitted" even when the turn is already dead.
   The agent loses work it believes it finished. Recommendation: decouple
   turn execution from the delivery stream (run to completion server-side,
   let the client re-attach), and make fire delivery acknowledge turn
   *completion*, not turn *start*.

7. **Approval gates park turns silently.** A turn awaiting an approval card
   looks identical to a hung turn — to the owner and to any monitoring. The
   dojo needed an API-side approval pump to make progress at all.
   Recommendation: surface "waiting on your approval since <time>" in the
   chat stream and in `/api/ui` state, and let a parked turn time out into a
   resumable state instead of holding the slot.

8. **Agents have no clock.** No date/time in the system prompt, so any
   recency judgment ("is this wiki stale?") silently fails or gets invented.
   Plugins now work around it server-side (wiki `age_days`). Recommendation:
   inject current datetime into the system prompt in Luna core; it is cheap
   and removes a whole class of quiet wrongness.

9. **Concurrent turns race list-before-create invariants.** Any prompt-level
   "check if X exists before creating it" is a race under concurrent
   streams; we saw duplicate heartbeats until a code reaper (keep-oldest)
   enforced convergence. Recommendation: core guidance that uniqueness
   invariants live in code (unique_name upserts, reapers), never in prompts.

10. **`on_load` background tasks die silently under `luna serve`.**
    Bootstrap loops must hang off `app.router.on_startup`. Recommendation:
    either fix task lifetime under serve or document the startup hook as the
    only supported path — plugins keep rediscovering this the hard way.

11. **The marketplace index lists latest-only.** Downgrade/rollback and
    staged-upgrade testing require a hand-built pin-index. Recommendation:
    keep N previous versions in the index; rollback is a first-class
    operation for an agent that installs its own tools.

12. **The composer queues under concurrent streams** (dojo observation):
    owner sends during a busy multi-stream period can sit queued with no
    feedback. The 031 live-queue work on the shell addresses the UI half;
    the server half (visibility into queued/parked turns) is still open.

## One-line summary

The agent's reasoning is rarely the limiting factor. What limits it is
(a) tools whose outputs are ambiguous or internal-jargon-shaped, and
(b) platform seams — stream-tied turns, silent parking, no clock, no
reconciliation primitives — that convert recoverable situations into
invisible failures. Fixing the seams buys more capability than prompt work.
