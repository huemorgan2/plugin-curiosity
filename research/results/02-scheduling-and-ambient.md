# WS2 — Scheduling & Ambient Behavior

**Question:** Where does the recurring clock live that fires Luna's "dream," digests, and
reactive research — given hosted Lunas run on ephemeral Fly machines that sleep?

**Answer (updated):** It is already half-built. Luna has a designed-and-partially-implemented
**external scheduler** (Plan 023). Curiosity should target *that* interface, not invent its
own clock. This retires the plan's biggest risk (R1) from "no home exists" to "finish the
clock half of an existing, correctly-architected system."

---

## 1. Grounded State of the Scheduler

Sources in-repo:
- `luna-service/plans/023-external-scheduler/PLAN.md` — the primary hosted design.
- `luna-service/plans/luna-proposals/023-external-scheduler-plugin.md` — the plugin side.
- `luna/plans/014-clone-scheduler/PLAN.md` — plugin-based scheduler (Phase 014).
- `luna/plans/006-tasks-engine/006.711-cron-triggers/PLAN.md` — in-process cron, **PARKED**.
- `luna/plugins/plugin_playbooks/definition.py:73` — `TriggerDef.cron` field exists but is
  **hard-rejected** (`raise ValueError("Cron triggers are not supported yet (Phase 014)")`).

### Why ephemeral machines forced the design
A hosted Luna is a scale-to-zero Fly machine; it cannot be trusted to keep its own cron
(it's asleep). So the clock moves to the **control plane** (Render, always-on): it ticks,
**wakes** the tenant machine, and **fires** a plugin trigger that does the work. Quote from
Plan 023:

> An ephemeral machine cannot be trusted to keep its own cron. So for the hosted product the
> *clock* moves to the control plane: we tick, we wake the tenant machine, and we trigger a
> Luna plugin that does the actual work.

### What already exists (the delivery half) ✅
- **Trigger contract / `TriggerSource` registry** — `luna/triggers/__init__.py` (Plan 006.713).
  Plugins publish/consume triggers.
- **Relay outbox + forwarder** — `luna-service/cloud/relay/forwarder.py`: signed delivery,
  **auto-wake of stopped machines**, retry with exponential backoff, dead-lettering. Started
  in `cloud/main.py:154`.
- **Machine wake** — `cloud/api/proxy.py::_try_wake_agent`. No new wake path needed.
- **Signing** — Standard Webhooks headers via `derive_relay_secret(root, agent_id)`.
- **Gateway token auth** for machine→control-plane calls.

### What is missing (the clock half) 🚧
Per Plan 023, none of these are implemented yet:
- Schema: no `external_schedules` table (`cloud/db/models.py`).
- Expression engine: `cloud/scheduler/expr.py` (cron + NL parse → `next_run_at`).
- Ticker: `cloud/scheduler/ticker.py` (poll ~15s, enqueue fires).
- Registration API: `cloud/api/scheduler_routes.py` (`POST /api/scheduler/schedules`).
- Provisioning env `SCHEDULER_MODE=external`, admin visibility, tests.
- Plugin side: an `external-scheduler` plugin exposing `schedule_create/list/delete` tools
  and a `/api/p/external-scheduler/fire` ingress endpoint.

**Net:** the hard, cross-cutting infra (wake + signed delivery + trigger emission) is done.
What's left is comparatively mechanical: a table, a cron parser, a poll loop, a CRUD route,
and a plugin that registers schedules upstream and receives fires.

---

## 2. The Fire Path (target interface for Curiosity)

```
Control Plane (Render, always-on)              Tenant Luna (Fly, ephemeral)
┌──────────────────────────────┐               ┌─────────────────────────────┐
│ external_schedules table      │               │ external-scheduler plugin    │
│  name, cron_expr, next_run_at │               │  tools: schedule_create/...  │
│ ticker.py  (poll ~15s)        │               │  ingress: POST /api/p/       │
│   └─ due? → enqueue fire       │──wake+POST──▶ │        external-scheduler/fire│
│ relay forwarder (sign, wake,   │   (signed)    │   → emit trigger:            │
│  retry, dead-letter)           │               │     playbook.run.requested   │
└──────────────────────────────┘               │     OR message.received      │
                                                └─────────────────────────────┘
```

**Fire payload** (POST `/api/p/external-scheduler/fire`):
```json
{
  "fire_id": "uuid",
  "schedule_id": "uuid",
  "action_type": "playbook | agent_prompt",
  "target": "playbook-name OR prompt-text",
  "inputs": {},
  "fired_at": "ISO8601"
}
```

Two modes (Plan 023 decision D1), selected by `SCHEDULER_MODE`:
- **external** (hosted): clock on control plane; plugin registers schedules upstream and
  keeps a display mirror; control plane fires.
- **local** (OSS/dev): clock is an in-plugin `croniter` tick loop writing to the plugin's own
  DB; same internal fire emission. Lets us develop Curiosity's cadences **without the control
  plane** and without waiting on Plan 023.

Granularity: 5-field cron + natural-language ("every weekday at 9am"); `min_interval_seconds`
floor (default 60s); overdue fires once (no catch-up storms).

---

## 3. Recommendation for Luna Curiosity

**Do not build a clock. Consume the scheduler's fire event.** Concretely:

1. **Curiosity is a scheduler *consumer*, not a scheduler.** The curiosity plugin registers
   one or more schedules (via `schedule_create`, or directly if we build local mode first)
   and handles the resulting trigger. For the "dream," the natural `action_type` is
   `agent_prompt` with a target like *"Run your nightly consolidation over mission
   {id}"* — or `playbook` if we make the dream a durable playbook (see §4).

2. **Cadences we need (v1):**
   | Cadence | Trigger | action_type | Notes |
   |---------|---------|-------------|-------|
   | Nightly **dream** (consolidate → wiki edits → thoughts) | cron, e.g. `0 3 * * *` in user's tz | `agent_prompt` or `playbook` | The core ambient behavior. Must survive machine sleep — the control-plane wake handles this. |
   | Weekly **digest** | cron, e.g. `0 8 * * MON` | `agent_prompt` | Batched reflection; low frequency. |
   | Reactive **news spike** (later) | webhook/connector trigger, not cron | event | Out of v1; uses the same trigger contract. |

3. **Develop against `local` mode first.** Build and iterate the dream/digest routines using
   the in-plugin `croniter` loop (`SCHEDULER_MODE=local`) on a dev Luna. This unblocks
   Curiosity entirely from Plan 023's hosted work — the fire *interface* is identical, so
   nothing is thrown away when hosted external mode lands.

4. **Coordinate, don't fork.** luna-service is read-only for us. The clean path is: Curiosity
   defines exactly what it needs from the fire contract (payload fields, `action_type`
   semantics, per-mission targeting), and hands luna-service owners a short spec. Everything
   Curiosity needs is already contemplated by Plan 023 — we are a *first consumer* that
   justifies finishing it, not a new requirement.

---

## 4. Dream: `agent_prompt` vs `playbook`

The nightly consolidation ("dream") can fire two ways:

- **`agent_prompt`** — fire a prompt that tells the agent to consolidate. Simplest; fully
  agent-driven; flexible but non-deterministic and harder to bound in tokens.
- **`playbook`** — make the dream a durable [plugin-playbooks](../../../plugins/plugin-playbooks/)
  workflow: (1) list wiki pages touched since last dream, (2) summarize new research, (3)
  update pages, (4) draft one shared thought, (5) enqueue the thought for delivery.
  Deterministic, resumable, bounded, and legible in the playbook canvas.

**Recommendation:** the dream is a **playbook** with agent-driven steps inside it. This gives
predictable structure (the user can see the nightly routine and its cost) while keeping the
reasoning open-ended where it must be — exactly the "deterministic routine wrapping
agent-driven reasoning" split the vision calls for. It also reuses playbooks' existing
trigger binding rather than adding a parallel path.

---

## 5. Suspend / Idle Survival

Solved by the existing infra: the relay forwarder **wakes** a stopped machine before
delivering, with retry and dead-lettering. Curiosity inherits this for free by using the fire
path. The one design rule: **never rely on an in-process timer inside a hosted Luna** — it
will be asleep. All hosted cadence must originate from the control-plane ticker.

---

## 6. Open Items to Confirm with luna-service Owners

- Does `action_type: "playbook"` pass through `inputs` we can use to scope the fire to a
  specific `mission_id`? (Needed so the dream knows which mission it's consolidating.)
- Timezone handling for user-facing cadences ("3am" in whose tz?).
- Is building **local mode** in the curiosity plugin acceptable for dev, or should we wait for
  external mode? (Recommend: yes, build local mode — it's in the OSS design already.)
- Priority: is Curiosity a strong enough first consumer to pull Plan 023 forward on the
  roadmap?

---

## 7. Impact on the Research Plan

- **Risk R1 downgraded** from "ambient behavior has no native home" to "finish the clock half
  of an already-architected scheduler; develop against local mode meanwhile." Still the
  critical-path dependency, but no longer an unknown.
- **Spike SP2 ("nightly dream")** becomes: implement local-mode cron in the curiosity plugin,
  fire a dream playbook, prove it consolidates wiki pages. No control-plane work required to
  prove the loop.
- The vision's "dream every night at some hour" is directly supported by cron + NL scheduling.
