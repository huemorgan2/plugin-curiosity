# Phase 8.1 — Curiosity takes over on install: prompt primacy + first-load kickoff

**Problem (observed on the vaselin-test tenant).** Installing plugin-curiosity
changed nothing until the owner explicitly asked about missions:
1. Its fragment is appended near the END of the system prompt while the
   onboarding addendum outranks it by position — persuasion lost to order.
2. v0.4.2 asked only "in your FIRST exchange"; installed mid-conversation the
   window had passed (0.4.3 renews every reply — persuasion again, not
   mechanism).
3. Nothing conversational happens at install — the only signal is core's
   generic "welcome the new plugin" moment, best-effort and mission-blind.

**Fix strategy (per aspect-oriented review).** Two levers:
- Core: `prompt.assemble` hook — luna plan `plans/025-prompt-assemble-hook/`
  (tracked in the luna repo). Curiosity is its first consumer.
- Plugin: first-load muted kickoff — no core change needed, ships regardless.

---

## Phase A — luna core: `prompt.assemble` hook
Execute luna `plans/025-prompt-assemble-hook/PLAN.md` (phases 01-03 there):
HookRegistry + `PromptSection.source` + `ctx.hooks` (scoped, torn down on
unload like providers in 008.999) + runtime mount + tests. Details live in the
luna plan; execution summary goes in that folder.

## Phase B — curiosity consumes the hook (prompt primacy)
In `on_load`, feature-detect and register:
```python
hooks = getattr(ctx, "hooks", None)
if hooks:
    hooks.register("prompt.assemble", self._reorder, priority=60)
```
`_reorder(ctx)`: if the mission store is empty (missionless = the takeover
case), move curiosity's own section to immediately BEFORE the onboarding
addendum section; if no onboarding section, before the personality block.
With a mission set: leave order alone (the mission fragment doesn't need
primacy). Old cores (no `ctx.hooks`): current appended-fragment behavior, no
crash — the plugin must stay installable on unpatched cores.

Tests (`tests/test_prompt_primacy.py`):
- fake hooks registry: missionless → own section lands before onboarding;
  with mission → order untouched; no `ctx.hooks` attr → on_load still clean.
- reorder never touches foreign section text (contract-compliance).

## Phase C — first-load mission kickoff (hook-free)
- New one-row state flag `kickoff_sent` in curiosity's tables.
- In `schedule_on_load_work`'s task (loop-safe already): if no mission AND
  `kickoff_sent` is unset AND `ctx.send_muted_message` exists → send ONE muted
  message (channel="moment"): instruct the agent to introduce its curiosity
  capability in its own voice and ask the owner for a mission NOW, framing the
  stakes (research/wiki/dreams stay dark without one); set `kickoff_sent`.
- Never resend on upgrade/reboot (flag persists); mission_set path unchanged.

Tests (`tests/test_kickoff.py`):
- fresh install, no mission → exactly one muted send; flag set.
- second load / upgrade → zero sends. Mission already set → zero sends.
- core without `send_muted_message` → no crash, flag untouched (retry next load).

## Phase D — verify live + ship
- QA Luna (port 8123 procedure): fresh install of curiosity on a missionless
  agent → muted kickoff lands in chat; system-prompt breakdown shows the
  curiosity section ABOVE the onboarding addendum; setting a mission restores
  normal order and fires the existing kickoff protocol.
- Bump plugin-curiosity to 0.5.0 (all three stamps — test_manifest.py guards);
  commit; package; publish to the Render dev marketplace
  (`LUNA_MP_BASE=https://luna-marketplaces.onrender.com`, slug `official`).
- Write `execution_summary.md` here AND in luna
  `plans/025-prompt-assemble-hook/` for the core part.

## Non-goals
- Other pointcuts (llm.call, tool.call, egress), HookedModel, dispatch
  unification — future plans per the aspect notes.
- Onboarding-addendum content changes; plugin-contributed onboarding steps.
- plugin-wiki changes (none needed).

## Risks
- Hosted tenants on old cores see only Phase C behavior (kickoff message, no
  reorder) — acceptable: the kickoff + 0.4.3 renew-every-reply fragment cover
  the gap until cores update.
- Reorder vs prompt-cache: moving sections changes the prompt prefix only for
  missionless agents — bounded, short-lived state.
