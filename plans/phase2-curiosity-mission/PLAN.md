# Phase 2 — plugin-curiosity, the mission & the action rails

**Goal:** Luna can be *given a mission*, she owns it at native priority, she knows she has a
wiki to fill — **and the rails for acting are wired from the start**: she can schedule her own
recurring work and author/trigger playbooks that take real actions. This is the "she gets a
mission and gets curious" moment, built so that *actioning* is an easy step forward, not a
later re-architecture.

**Depends on:** Phase 1 (`WikiProvider`), Phase 0 (scheduler + playbooks on the dev Luna).
**Spike:** none (SP-lite).

---

## Scope

**In:** the `missions` table; `set_mission` / `refine_mission` / `get_mission`; write-through
to core's `Identity.mission`; autonomy-rung + risk-ceiling fields; consumption of
`WikiProvider`; **registration of recurring schedules via `plugin-scheduler`**; **the
playbook-authoring/triggering path via `plugin-playbooks`**.

**Out:** the research prompt logic (phase 4), the dream (phase 5), onboarding UX (phase 6).
Actual side-effecting actions stay **approval-gated** in v1 — the rails are built, the ceiling
stays conservative.

---

## Model

`missions` table (plugin-owned): `id, statement, autonomy_rung (1–4), risk_ceiling, active,
created_at, updated_at`. Single active row in v1.

**Write-through (no core change):** `set_mission` writes the structured row **and** copies
`statement` into the existing `Identity.mission` field (renders at system-prompt slot #4 via
`mission_block()`). `refine_mission` updates both.

## Tools

- `set_mission(statement, rung=1)` — `auto_approve`; write-through + seed 2–4 wiki stub pages
  (via `WikiProvider`) + **register the mission's recurring schedules** (below).
- `refine_mission(statement | rung)` — update both stores; re-sync schedules.
- `get_mission()` — active mission + rung.

## The action rails (the "easy step forward")

Two existing plugins are wired in now so nothing is bolted on later:

1. **Recurring wake via `plugin-scheduler`.** On `set_mission`, curiosity calls
   `trigger_create(name, schedule_expr, action_type, target, timezone)` to register its
   cadence — e.g. a nightly dream (phase 5) and a daily research pass (phase 4). `action_type`
   is `agent_prompt` (a prompt the fired turn executes) or `playbook` (a named playbook).
   The scheduler's relay **wakes the machine**, so these fire even when Luna is asleep. No
   asyncio loop in our plugin.
2. **Author + trigger playbooks via `plugin-playbooks`.** Curiosity's system-prompt fragment
   teaches Luna that, when she identifies a repeatable action, she can `playbook_propose` /
   `playbook_edit` a playbook and run it (or schedule it via `action_type="playbook"`). A
   playbook's `tool_call` steps can send email, message, or call APIs — **each gated by that
   tool's approval policy** (`auto_approve` runs; `prompt_always` shows an approval card, even
   in a headless fire). So "self-improving" (wiki + dreams) and "actioning" (playbooks) share
   one substrate.

   > **Phase-0 constraint (verified live):** `playbook_propose`/`playbook_edit` are
   > `chat_only=True` — they are NOT available inside scheduled/muted fire turns. Playbook
   > *authoring* therefore happens in real chat turns (Luna proposing during conversation, or
   > a fired turn *asking the owner in chat* to co-author next time they talk). Fired turns
   > can still *run* existing playbooks (`action_type="playbook"`) and use all non-chat_only
   > tools (wiki, scheduler, research). Do not design any fired flow that requires authoring
   > a playbook mid-fire; if that becomes essential, it's a deliberate policy change to the
   > playbooks plugin, not a workaround.

**Autonomy ceiling in v1:** `autonomy_rung`/`risk_ceiling` are stored and inform the prompt,
but side-effecting tools stay approval-gated (rung 4 = *execute-with-approval*). Granting
unattended execution (rung 4 auto / rung 5) is a deliberate later toggle, not new code — it's
flipping tool policies via `PolicyResolver.upsert`. The rails make that a config change.

---

## Steps

1. Create `missions` table; implement the three tools in `mission.py`.
2. Implement write-through to `Identity.mission`; verify the statement renders in the live
   system prompt (slot #4).
3. On `set_mission`, seed wiki stubs and call `trigger_create` for the mission's cadence
   (placeholder targets now; phase 4/5 fill the prompts/playbooks).
4. Add the curiosity prompt fragment that makes playbook authoring + triggering a known,
   encouraged capability; confirm the agent can `playbook_propose` a mission-relevant playbook
   and that a side-effecting step correctly hits the approval gate.

## Acceptance criteria

- [ ] `set_mission("grow signups")` renders that statement in the live system prompt (slot #4).
- [ ] The structured row and `Identity.mission` stay in sync across set/refine.
- [ ] Setting a mission seeds wiki stubs **and** registers recurring schedules on
      `plugin-scheduler` (verify via `trigger_list`).
- [ ] The agent can author a playbook (`playbook_propose`) whose `tool_call` step is
      approval-gated; running it surfaces the approval card rather than executing silently.
- [ ] Exactly one active mission is enforced.

## Notes / risks

- Extend the existing `Identity.mission`; do not add a mission concept to core.
- Keep the ceiling conservative in v1 (approval-gated actions). The point of this phase is that
  *lifting* it later is a policy flip, because the scheduler + playbook rails already exist.
