# WS5 — Mission & Trust Model

> Deliverable for Theme F of the [research plan](../research_plan.md). Companion to
> [vision.md](../vision.md) §4 (core loop) and §8 (design principle 5, the autonomy ladder).
>
> **Scope:** F1 the MISSION object, F2 the AUTONOMY LADDER + tool-policy mapping, F3 mission
> scope vs. global memory / per-mission wiki, and a v1-vs-later cut.

---

## 0. Grounded facts this design builds on

All decisions below are anchored to real code, not the vision prose. The load-bearing findings:

1. **A "mission" already exists — as a single free-text string on the singleton identity row.**
   `mission` is an `IDENTITY_FIELDS` entry in
   [`luna/luna/identity/service.py`](../../../luna/luna/identity/service.py) (line 22-30,
   with legacy `purpose` back-compat), stored on the `Identity` model in
   [`luna/luna/data/models.py`](../../../luna/luna/data/models.py) (`mission: Mapped[str | None]`,
   line 212), and versioned on every edit. It is rendered into the system prompt by
   `mission_block()` in [`luna/luna/agent/system_prompt.py`](../../../luna/luna/agent/system_prompt.py)
   (line 102), placed at slot #4 — **before** persona, right after the base prompt. Header
   `HEADER_MISSION = "Mission (what you're for)"` and seed `DEFAULTS_MISSION` live in
   [`luna/luna/prompts/seeds.py`](../../../luna/luna/prompts/seeds.py) (lines 242, 263).
   So the agent already "owns a goal" via a top-priority prompt section. **We extend this;
   we do not invent a prompt slot.**

2. **Plugins inject prompt text via `prompt_sections()` — but land in the low-priority `plugins`
   slot.** `LunaPlugin.prompt_sections()`
   ([`luna/luna/plugins/base.py`](../../../luna/luna/plugins/base.py) line 247) is called every
   turn and its strings render *after* tools/skills (`key="plugins"`), not at slot #4. This
   matters: a mission rendered from a plugin is demonstrably lower-priority than the native
   `mission_block`. (See §F1 for how we reconcile this.)

3. **Tool policy and risk are plain strings on `ToolDef`, and risk is metadata only.**
   `policy ∈ {auto_approve, prompt_first_time_only, prompt_always, block}` and
   `risk_level ∈ {low, medium, high}`
   ([`luna/luna/plugins/base.py`](../../../luna/luna/plugins/base.py) lines 50-51). There is no
   `RiskLevel`/`ToolPolicy` enum. Crucially: **`risk_level` does NOT participate in the
   auto-vs-prompt decision today** — a `high`-risk tool with `policy="auto_approve"` still
   auto-fires (its only current effect is a 2-second wait on the approval card). The gate is
   driven entirely by `policy`.

4. **Policy is resolved at call time and is overridable per-tool via a DB table.** The dispatch
   gate in [`luna/luna/agent/runtime.py`](../../../luna/luna/agent/runtime.py) (line 764) calls
   `resolver.resolve("tool_call", tool_name, tool_def)`. `PolicyResolver`
   ([`luna/luna/approval/policy.py`](../../../luna/luna/approval/policy.py)) resolves first-hit-wins:
   in-process cache → exact `approval_policy` row `(kind, target)` → wildcard `(kind, "*")` row →
   `tool_def.effective_policy()` → safe default `prompt_always`. **The owner (or a plugin) can
   `upsert()` rows into `approval_policy` to override any tool's declared policy at runtime.**
   This table is our promotion mechanism.

5. **Plugins own isolated DB tables (E4).** A plugin declares its own
   `luna_sdk.declarative_base()`, defines models (convention: `plugin_<name>_*` table names,
   `UUID()` PKs, `JSONB` for lists, `Text` for markdown), and creates them idempotently in
   `on_load` (`table.create(checkfirst=True)` on `ctx.engine`) — see
   [`plugins/plugin-interview/plugin_interview/models.py`](../../../plugins/plugin-interview/plugin_interview/models.py)
   and its `on_load`. **Plugin tables live in a separate SQLite file — no JOINs to core's
   `identity`/memory tables; cross-references are by id only.**

6. **Proactive-on-load exists (E11):** `ctx.send_muted_message(title, content, respond=True)`
   ([`luna/luna/plugins/context.py`](../../../luna/luna/plugins/context.py) line 106) posts a
   collapsed line into chat and lets the agent take a real turn. It is **one-shot**, guarded by a
   persisted flag in plugin-interview. This is how onboarding fires.

7. **Tiers are specified but unenforced.** `Account.plan` (default `"free"`) exists in
   luna-service but is written nowhere, gated on nowhere, and **not plumbed into the tenant
   machine's env** — a plugin inside a Luna cannot read its tier today. So autonomy rungs 4-5
   *conceptually* map to Pro/Power, but there is no runtime entitlement to gate on. v1 must not
   depend on tier plumbing that does not exist.

**Design consequence:** the mission object lives in the **curiosity plugin's own table** (rich,
per-mission, evolves fast), and its *statement* is mirrored into the native `mission_block` slot
so the agent owns the goal at top priority. Autonomy is enforced by writing `approval_policy`
rows plus a **plugin-level risk ceiling** the mission carries (since core's `risk_level` gate
does not exist yet).

---

## F1 — The MISSION object

### Where it lives

**A new table in the curiosity plugin's own DB (E4), not on core's `Identity` row.**

Rationale:
- The identity `mission` field is a single free-text string with no room for scope, rung, links,
  or status. A first-class mission needs structure, so it needs its own model.
- Missions are *per-mission* (§F3) and expected to grow, be superseded, and carry a wiki + tool
  bindings — that is plugin-owned state, exactly the `plugin-interview` shape (sessions + derived
  briefs + a meta table).
- Keeping it in the plugin means installing/removing the curiosity plugin cleanly adds/removes the
  whole mission concept, per the plugin-isolation contract.

**But the mission *statement* must reach slot #4**, not the low-priority `plugins` slot (fact #2).
Two ways, pick one:

- **v1 (recommended, zero core change): write-through to the identity `mission` field.** When
  `set_mission` creates/activates a mission, the plugin also calls the identity config writer
  (`manage_config(section="identity", changes={"mission": <rendered statement>})`, exactly how
  `personality-template` writes `section="personality"`). The native `mission_block` then renders
  it at slot #4 for free. The plugin's `prompt_sections()` adds only the *dynamic* extras (current
  rung, scope reminder, "you are on rung 2: advise, do not execute") that don't belong in the
  durable identity string.
- **later (needs one core PR): a dedicated section builder.** Add a `mission_from_plugin` section
  + `SECTION_LABELS` key in `system_prompt.py` fed by the plugin, so the plugin owns the whole
  slot-#4 render without round-tripping through identity. Cleaner, but touches core; defer.

**Decision: v1 uses write-through.** The single active mission's statement lives in *both* the
plugin table (source of truth, structured) and the identity `mission` string (a rendered mirror
for the prompt). The plugin is the writer; identity is a projection.

### Fields

| Field | Type | Notes |
|-------|------|-------|
| `id` | `UUID()` PK | `plugin_mission_missions.id` |
| `statement` | `Text` | The durable one-paragraph "what I'm here to accomplish," in Luna's own restated words. This is what mirrors into identity `mission`. |
| `title` | `Text` | Short label, e.g. "Grow the paying funnel." For UI + wiki naming. |
| `scope` | `JSONB` (list[str]) | In-scope sub-domains / boundaries. e.g. `["funnel", "ads", "landing pages", "tracked events"]`. |
| `non_goals` | `JSONB` (list[str]) | Explicit out-of-scope. e.g. `["pricing changes", "product roadmap"]`. Bounds curiosity and proposals. |
| `autonomy_rung` | `int` (1-5) | Current rung on the ladder (§F2). Default `1`. |
| `risk_ceiling` | `Text` | Max tool `risk_level` the mission may auto-exercise: `low` \| `medium` \| `high`. Default `low`. The gate mechanism (§F2). |
| `wiki_id` | `UUID()` nullable | FK-by-id to the WS1 per-mission wiki root. No DB-level FK (separate file); id reference only. |
| `linked_tools` | `JSONB` (list[str]) | Tool names the mission is permitted to use (the mission's tool allow-list). Empty = read-only defaults only. |
| `status` | `Text` | `draft` \| `active` \| `paused` \| `archived`. Indexed. Exactly one `active` at a time in v1 (§F3). |
| `created_at` | `Text` (ISO) | |
| `updated_at` | `Text` (ISO, onupdate) | |
| `promoted_at` | `Text` (ISO) nullable | Timestamp of last rung promotion — the audit trail for "how fast did trust grow." |

A sibling `plugin_mission_meta` key/value table holds one-time flags (`onboarding_greeted`), mirroring
`plugin_interview_meta`.

> Derived artifacts (the "mission brief" markdown) are **rendered on read** from these fields +
> wiki, not stored as a blob — following plugin-interview's `render_brief()` convention. Keeps the
> row small and the brief always-fresh.

### Schema (SQLAlchemy, plugin-owned)

```python
# plugins/plugin-curiosity/plugin_curiosity/models.py
import uuid as _uuid
from datetime import UTC, datetime
from luna_sdk import declarative_base, JSONB, UUID          # E4 types
from sqlalchemy import Text, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column

Base = declarative_base()   # fresh MetaData, isolated from core

def _now() -> str:
    return datetime.now(UTC).isoformat()

class Mission(Base):
    __tablename__ = "plugin_mission_missions"

    id:            Mapped[_uuid.UUID] = mapped_column(UUID(), primary_key=True, default=_uuid.uuid4)
    title:         Mapped[str]        = mapped_column(Text, default="", nullable=False)
    statement:     Mapped[str]        = mapped_column(Text, default="", nullable=False)
    scope:         Mapped[list]       = mapped_column(JSONB, default=list, nullable=False)
    non_goals:     Mapped[list]       = mapped_column(JSONB, default=list, nullable=False)
    autonomy_rung: Mapped[int]        = mapped_column(Integer, default=1, nullable=False)
    risk_ceiling:  Mapped[str]        = mapped_column(Text, default="low", nullable=False)  # low|medium|high
    wiki_id:       Mapped[str | None] = mapped_column(UUID(), nullable=True)
    linked_tools:  Mapped[list]       = mapped_column(JSONB, default=list, nullable=False)
    status:        Mapped[str]        = mapped_column(Text, default="draft", nullable=False, index=True)  # draft|active|paused|archived
    created_at:    Mapped[str]        = mapped_column(Text, default=_now, nullable=False)
    updated_at:    Mapped[str]        = mapped_column(Text, default=_now, onupdate=_now, nullable=False)
    promoted_at:   Mapped[str | None] = mapped_column(Text, nullable=True)

# created idempotently in on_load:
#   async with ctx.engine.begin() as conn:
#       for t in Base.metadata.sorted_tables:
#           await conn.run_sync(t.create, checkfirst=True)
```

### Example row

```json
{
  "id": "b3f1c2a0-1e5d-4c9a-9f0e-2a7b6c4d1e88",
  "title": "Grow the paying funnel",
  "statement": "Grow traffic that converts to paying customers by optimizing campaign budgets, ads, landing pages, and the events we track — starting by understanding the current funnel deeply before proposing changes.",
  "scope": ["conversion funnel", "paid ads", "landing pages", "tracked events", "SEO / AIO"],
  "non_goals": ["pricing changes", "product roadmap decisions", "outbound sales"],
  "autonomy_rung": 2,
  "risk_ceiling": "low",
  "wiki_id": "d9a4...funnel-wiki-root",
  "linked_tools": ["web_search", "web_fetch", "funnel_get_campaigns", "funnel_get_landing_pages", "wiki_read", "wiki_write_page", "share_thought"],
  "status": "active",
  "created_at": "2026-07-07T09:12:04+00:00",
  "updated_at": "2026-07-08T03:00:11+00:00",
  "promoted_at": "2026-07-08T08:40:22+00:00"
}
```

### How it gets set

Two entry points, both landing on the same `Mission` row:

1. **`set_mission` tool** (agent-callable), registered on `ctx.tools`:

   ```python
   ctx.tools.register(
       name="set_mission",
       description="Create or update the active mission Luna owns.",
       parameters={
           "type": "object",
           "properties": {
               "statement": {"type": "string"},
               "title":     {"type": "string"},
               "scope":     {"type": "array", "items": {"type": "string"}},
               "non_goals": {"type": "array", "items": {"type": "string"}},
           },
           "required": ["statement"],
       },
       handler=self._tool_set_mission,     # writes the row, then write-through to identity.mission
       policy="prompt_first_time_only",    # owner confirms the first mission write; edits are cheap
       risk_level="low",
   )
   ```

   The handler (a) upserts the `Mission` row with `status="active"`, `autonomy_rung=1`,
   `risk_ceiling="low"`; (b) write-throughs `statement` into the identity `mission` field so it
   reaches slot #4; (c) creates the wiki root (WS1) and stores `wiki_id`.

2. **Onboarding (E11 muted message).** On first load with **no active mission**, the plugin fires
   one `send_muted_message` guarded by `plugin_mission_meta.onboarding_greeted`:

   > *"You don't have a mission yet. Ask the owner, in one line, what they'd most like you to own —
   > then restate it back in your own words and call `set_mission`. Don't ask for tools or setup;
   > just get the goal."*

   The agent then has a short exchange, restates the mission (vision §6 "restate in her own
   words"), and calls `set_mission`. This is the "mission → curiosity" inversion from vision §2:
   the first thing that happens is Luna getting the goal, not configuration.

### How it enters the system prompt (so the agent "owns the goal")

Per turn, three things reach the model:

1. **Slot #4 (native, top priority):** the identity `mission` string (the write-through mirror of
   `statement`) rendered by `mission_block()` under `HEADER_MISSION`. This is the durable "what
   you're for."
2. **`prompt_sections()` (plugin slot):** a short dynamic block the plugin emits every turn —
   current rung, its rule, and scope/non-goals as a live reminder:

   > ```
   > ## Your mission stance (rung 2 of 5 — Reflect & advise)
   > You may: research, read product data, build the wiki, share thoughts, ask questions.
   > You may NOT: draft change-lists yet, and you may NOT execute any write action.
   > In scope: conversion funnel, paid ads, landing pages, tracked events, SEO/AIO.
   > Out of scope (do not act on): pricing changes, product roadmap, outbound sales.
   > ```

   This keeps the *behavioral contract of the current rung* in front of the model without bloating
   the durable identity string, and updates instantly when the rung changes.
3. **Wiki context (WS1):** a TOC / retrieved slice — out of scope for this doc.

The split is deliberate: **the goal is durable and top-priority (identity slot); the leash is
dynamic and rung-scoped (plugin slot).**

---

## F2 — The AUTONOMY LADDER

Five rungs from vision §8, mapped onto the **real** policy/risk machinery. The central mechanism:

> **The mission carries a `risk_ceiling`, and climbing a rung raises it. A tool is auto-exercisable
> only if its `risk_level ≤ ceiling` AND it is in `linked_tools`. Higher-risk-than-ceiling tools
> are downgraded to `prompt_always` (per-action approval), and off-mission tools are not offered
> at all.** Because core's `risk_level` does not gate anything today (fact #3), the ceiling is
> enforced in the **curiosity plugin layer**, which writes `approval_policy` rows via
> `PolicyResolver.upsert()` (fact #4) when a rung changes.

### The rungs

| Rung | Luna may… | Permitted tool policy / risk | `risk_ceiling` | What the user sees | PROMOTION signal → next rung |
|------|-----------|------------------------------|:-------------:|--------------------|------------------------------|
| **1. Observe & learn** | Web research, read-only product data, build/edit the wiki, consolidate ("dream"). No output claims about the owner's systems yet. | `auto_approve`, `risk_level=low` only (web_search/fetch, funnel read tools, wiki_write). | `low` | A mission brief + first wiki stubs + one sharp insight, fast (vision §8 "quick wins"). Spend receipts. | Owner **reads a reflection and reacts positively** ("nice," 👍, "keep going", asks a follow-up). One clear positive engagement with a shared thought. |
| **2. Reflect & advise** | Everything in 1, **plus** proactively share opinions, findings, and questions on a cadence. Still read/think only. | Same as rung 1 (`auto_approve` / `low`). No new tool risk — the change is *behavioral licence to opine*, encoded in the prompt-section rule. | `low` | Regular short reflections with a point of view + one question each. The "she gets it" moment (vision §9, Day 1-3). | Owner **engages with the substance** — answers a question, says "you're right / go deeper on X", or explicitly "what would you change?". A request for recommendations is the trigger. |
| **3. Draft & recommend** | Produce concrete, scoped **outputs**: change-lists, ad copy, playbook drafts, a scorecard. Output only — **nothing is executed**. | Still `auto_approve` / `low` — drafting is generating text into the wiki / a message, not calling a write tool. Any write-tool call is `prompt_always`. | `low` | A ranked, concrete proposal ("7 changes to the pricing page, by lift × effort") the owner can copy-paste or hand off. The "handing me a plan" moment (§9, Day 5). | Owner **grants a write tool / connects an integration**, or says "do it / you have access." This is the deliberate, explicit hand-of-keys — the ladder's whole purpose (vision §8). **← v1 ends here.** |
| **4. Execute with approval** | Make changes behind **per-action** approval. Every write is a card the owner OKs. | Write tools flipped to `prompt_always` (or `prompt_first_time_only`). `risk_level` up to `medium`. | `medium` | An approval card per action, each naming the concrete change; a running log of what shipped. | Owner **stops rejecting / uses "always" grants** repeatedly for a class of action — i.e. approvals become rubber-stamps. Sustained clean approval history for a tool class. |
| **5. Own** | Act autonomously within guardrails (scope, non-goals, ceiling). | Selected write tools set to `auto_approve` within scope; `risk_level` up to `high` only for explicitly-owned tools. Everything else still gated. | `high` (scoped) | A digest of what Luna did, not a stream of cards. "Fine — you own the landing page. Go." (§9, Week 2). | (terminal) Owner can demote at any time. |

### How climbing a rung unlocks tools — the concrete mechanism

Promotion is a single plugin operation, `promote_mission(mission_id, to_rung)`, that does three
things:

1. **Bump the row:** `autonomy_rung`, `risk_ceiling`, `promoted_at`, and possibly extend
   `linked_tools`.
2. **Rewrite `approval_policy` rows** via `PolicyResolver.upsert("tool_call", <tool>, <policy>)`
   for each tool the rung affects. This is the *real* lever — it overrides the tool's declared
   policy at call time (fact #4). Examples:
   - Promote to rung 4 for the landing-page builder:
     `upsert("tool_call", "lp_update_block", "prompt_always")` — was `block`/absent, now gated-on.
   - Promote to rung 5 for that tool: `upsert("tool_call", "lp_update_block", "auto_approve")`.
   - Demote: `upsert(..., "block")` or `prompt_always`.
3. **Emit the new rung rule** into `prompt_sections()` (rung + its licence + scope), so the model's
   behavioral contract changes the same turn.

**The `risk_ceiling` gate** (belt-and-suspenders, plugin-enforced): before offering a tool to the
agent for this mission, the plugin checks `tool.risk_level ≤ ceiling` and `tool.name ∈ linked_tools`.
Tools above the ceiling are either withheld or force-registered at `prompt_always`. This closes the
gap that core's `risk_level` is currently inert — the mission is the thing that makes risk
meaningful.

> **Why enforce in the plugin, not core?** Fact #3: core does not gate on `risk_level` and fact #7:
> there is no tier entitlement plumbed to plugins. Building a mission-aware ceiling into core's
> dispatch gate is the "later" clean version (a core PR that makes `PolicyResolver` accept a
> mission risk-ceiling). For v1, the plugin owns the ceiling and expresses it through the existing
> `approval_policy` table — no core change required.

### Promotion is a gesture, never automatic

Every promotion is triggered by an **observed human gesture** (the rightmost column), never by
Luna deciding she's ready. Rungs 1→2→3 promote on *engagement* signals (a reaction, a question
answered, a "go deeper"); rungs 3→4→5 promote on *explicit grants* (connecting a tool, "you have
access," repeated "always" approvals). The plugin can *suggest* it's ready ("I think I understand
enough to draft changes — want to see them?") but the owner performs the promotion. This is the
trust model: **Luna earns; the human promotes.**

---

## F3 — Mission scope vs. global memory & per-mission wiki

Three stores, three scopes:

| Store | Scope today | Scope under this design |
|-------|-------------|-------------------------|
| **Atomic memory** (`memory_facts`) | **Global per Luna** — no `mission_id` (research plan §1.1) | **Stays global.** Fast-recall facts about the owner ("drinks coffee", "company is B2B") are cross-mission by nature. |
| **Wiki** (WS1) | Does not exist | **Per-mission** from day one — `Mission.wiki_id` roots each mission's knowledge base. |
| **Mission** (this doc) | Single free-text identity string | Structured row, **single active** (v1). |

**Interaction rules:**

- **Memory stays global; the wiki is the mission-scoped layer.** This matches vision §5 ("wiki and
  memory are complementary"): memory is the fast, cross-mission recall layer; the wiki is the slow,
  per-mission understanding layer. A mission reads global memory (owner facts help every mission)
  but writes its deep, evolving theory into *its own* wiki, so two missions never pollute each
  other's worldview.
- **Cross-reference by id only** (fact #5): the mission row's `wiki_id` points at the wiki root;
  wiki pages may cite memory facts; memory facts may cite a wiki page id. No JOINs — these live in
  different SQLite files.
- **The mission's `scope`/`non_goals` bound what curiosity writes.** Off-scope findings don't get a
  wiki page under this mission; non-goals are surfaced in the prompt so Luna won't propose them.

### v1 stance: single active mission

**Recommend exactly one `status="active"` mission per Luna in v1.** Reasons:

- The identity `mission` slot #4 is a single string — write-through only makes sense for one active
  mission. Multiple concurrent missions would need the "later" dedicated section builder and a way
  to arbitrate slot #4.
- Global memory is un-scoped; with one active mission there's no ambiguity about which mission a
  fact belongs to. Multiple missions would force us to decide memory scoping *now*, which the
  research plan (§1.1, A5) explicitly leaves open.
- The whole emotional arc (vision §9) is about *one* relationship deepening. Parallel missions
  dilute the "she gets *this*" signal and multiply the proactive-message noise budget (D3 risk).
- The autonomy ladder is per-mission; multiple missions at different rungs multiply the trust
  surface and the approval-policy bookkeeping.

The schema already supports later multi-mission (missions are rows with `status`); v1 simply
enforces the invariant "at most one active" in `set_mission` (activating one pauses any other).
Switching missions = pause A, activate B, re-write-through slot #4, swap the wiki context. Cheap,
and it defers the hard memory-scoping question until there's evidence we need concurrency.

---

## v1 vs. later — the cut

**v1 ships rungs 1-3 only: Observe & learn → Reflect & advise → Draft & recommend. No write
execution (no rung 4-5).**

| | v1 | Later |
|---|----|----|
| Rungs | **1-3** (observe / advise / draft) | 4-5 (execute-with-approval / own) |
| Tool risk | `low` only, `auto_approve` (web + read-only product tools + wiki + share) | `medium`/`high` write tools gated then owned |
| Mission storage | Plugin table + write-through to identity `mission` | Optional dedicated core section builder |
| Ceiling enforcement | **Plugin-level** (`approval_policy` upserts + `risk_ceiling` check) | Core `PolicyResolver` accepts a mission risk-ceiling |
| Missions | **Single active** | Multi-mission + memory scoping |
| Tier gating | None — rungs 1-3 need no entitlement | Rungs 4-5 map to Pro/Power once `Account.plan` is plumbed to plugins |

**Why stop at rung 3 for v1:**

1. **It matches where the value is.** The vision's entire wedge (§1, §8) is that rungs 1-3 need
   *almost no setup* and are what makes the human *want* to grant 4-5. v1 proves the wedge; it
   doesn't need to execute anything.
2. **Zero new integrations, zero risk.** Rungs 1-3 use only `auto_approve` / `low` tools that
   already exist (`plugin-web-access`, `plugin-funnelfighters` read-only). No write path means no
   way for background curiosity to damage the owner's systems — the exact `R6`/`R2` mitigation the
   research plan calls for.
3. **No dependency on unbuilt plumbing.** Rungs 4-5 need either a real `risk_level` gate in core or
   tier entitlement in plugins — **neither exists** (facts #3, #7). Shipping them would mean
   building cross-repo infrastructure (luna-service is read-only for us) before the wedge is even
   validated.
4. **The rung-3 → rung-4 boundary is exactly the ceremony we want to sell.** v1 ends precisely at
   "here's a concrete plan; grant me a tool and I'll do it" — the call-to-action that earns
   ownership (vision §6). The paid, execute-capable tiers are the natural upsell *after* v1 proves
   Luna's judgment.

**What later unlocks:** the `risk_ceiling` field and `promote_mission` mechanism are built in v1
but only ever range over `low`; rungs 4-5 are the same mechanism with the ceiling raised and write
tools bound — no re-architecture, just extending the range and (cleanly) moving the ceiling check
into core's dispatch gate.

---

## Summary of concrete decisions

1. **Mission = a row in the curiosity plugin's own table** (`plugin_mission_missions`), structured
   (statement, scope, non_goals, rung, risk_ceiling, wiki_id, linked_tools, status, timestamps).
2. **Statement write-throughs into the identity `mission` field** so it renders at native slot #4;
   the plugin's `prompt_sections()` adds the dynamic rung/scope leash.
3. **Set via a `set_mission` tool** (`prompt_first_time_only`) + an E11 muted-message onboarding
   nudge fired once when no active mission exists.
4. **The autonomy ladder is enforced by `risk_ceiling` + `linked_tools`, applied by writing
   `approval_policy` rows via `PolicyResolver.upsert`** — the mission carries the ceiling; climbing
   a rung raises it and re-writes policy rows. Core's inert `risk_level` becomes meaningful because
   the *mission* gates on it (plugin-side in v1).
5. **Promotion is always a human gesture** (engagement for 1→3, explicit grants for 3→5); Luna
   earns and suggests, the human promotes.
6. **Memory stays global; the wiki is per-mission; exactly one active mission in v1.**
7. **v1 = rungs 1-3, no write execution**, no new integrations, no dependency on unbuilt core-gate
   or tier plumbing.
