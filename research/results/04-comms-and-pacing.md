# WS4 — Communication, Reflection & Pacing

> Deliverable for the **Luna Curiosity** initiative. Covers Theme D (communication &
> reflection) and Theme E (calls to action & pacing) from the
> [research plan](../research_plan.md). See [vision.md](../vision.md) for the "why."

This document answers: *how does curious Luna talk to her human without becoming noise,
and how does she pace her spend so tokens always feel earned?*

---

## 0. Grounded starting point (what exists today)

Everything below is confirmed by reading the code, not assumed.

| Fact | Where |
|------|-------|
| The **only** proactive mechanism today is the one-time on-load **muted message**. | `plugins/plugin-interview/plugin_interview/__init__.py:88-123` calls `ctx.send_muted_message(title, content, respond=True)`, idempotent via a persisted `install_greeted` flag. |
| `send_muted_message` routes to core `post_muted_message()`. It persists a `MessageRow(role="user", extra={"kind":"muted","title":…,"collapsed":True,"source":…})`, emits `message.created` on the event bus, and optionally runs a real agent turn. | `luna/luna/plugins/context.py:106-159` → `luna/luna/agent/muted.py:94-229` |
| Chat messages carry a **`source`** tag in `MessageRow.extra`, surfaced to the UI as `MessagePayload.source`. Playbook-run messages are tagged **`source="playbook"`** for badging. | `luna/luna/data/models.py:85-104`, `luna/luna/schemas/api.py:152-166`, `luna/plugins/plugin_webui/chat_tools.py:85-139` (`_send_chat_message` sets `source="playbook"` when `_active_run_id` is set) |
| Any caller can inject a message via **`POST /api/conversations/{conv_id}/messages`** with `kind ∈ {"chat","muted"}` (+ `title`, `urgent`). | `luna/plugins/plugin_api/app.py:735-907` |
| Delivery to the browser is **SSE only**: `message.created` events stream over `GET /api/events?topics=message.*`; the UI subscribes via `fetchEventSource`. **No push notifications, no email exist.** | `luna/plugins/plugin_api/app.py:1301-1349`, `luna/ui/src/lib/api.ts:720-751` |
| The **only real out-of-band push channel** that exists is WhatsApp: `wa_send(chat_jid, text)` (`prompt_always`, HMAC-signed gateway POST). Talk/voice are inbound-only. | `plugins/plugin-whatsapp/plugin_whatsapp/__init__.py:193-215`, `client.py:63-76` |
| The **trigger** that would fire a repeated reflection is **not** in core. The closest thing is luna-service's production **Composio relay** (ticker-free, webhook-sourced) and the **planned Plan 023 "external scheduler"** which generalizes it to cron: control-plane ticker → relay outbox → forwarder → **wakes** the Fly machine → **POSTs** a signed `/fire` event → plugin emits `message.received` / `playbook.run.requested`. | `luna-service/cloud/relay/forwarder.py:46-103`, `luna-service/plans/023-external-scheduler/PLAN.md` |
| Luna memory injects **top-5 semantic facts** into the system prompt each turn. | `luna/luna/agent/system_prompt.py` (`recall_context()`) |

**The gap in one sentence:** we have a way to *write a badged message into a conversation
and light up the client over SSE*, and a *planned* way to *wake the machine on a schedule*
— but nothing wires a scheduled wake to a repeated, cadence-controlled reflection.

---

# Theme D — Communication & Reflection

## D1. The outbound channel problem

**Question.** How does Luna send an *unprompted, repeated* reflection — not just the
one-time on-load muted message?

### The options, given the architecture

**Option A — Write into the conversation via the muted-message path + a `source` badge.**
Reuse the exact plumbing that already exists. A scheduled trigger calls
`post_muted_message(..., source="curiosity", respond=False)` (or a thin
`ctx.share_thought()` wrapper), which persists a `MessageRow`, stamps
`extra.source="curiosity"`, and emits `message.created`. If the client is open, the
reflection **live-appends over SSE** exactly like a playbook message; if closed, it's
already persisted and shows on next open.
- *Pros:* zero new delivery infrastructure; badging is free (copy `source="playbook"` →
  `source="curiosity"`, one UI colour/icon); the message is durable and legible; the
  agent can be given `respond=False` so the reflection is *authored content*, not a
  wasteful extra turn.
- *Cons:* only reaches the user **when they open the app** unless paired with a real push
  channel; needs a scheduler to fire it (WS2); `respond=True` would burn a turn — we want
  `respond=False` for pre-composed thoughts.
- *Missing in core today:* nothing structural — `post_muted_message` already accepts a
  `source` and a `respond` flag. We only need (a) a new `source` value + UI badge, and (b)
  the trigger to call it. This is the cheapest path by a wide margin.

**Option B — Push notification.** Wake the user's device when a reflection lands.
- *Pros:* reaches the user when the app is closed; matches "by the next morning…" felt
  experience.
- *Cons:* **does not exist** — no web-push, no service worker, no device registration, no
  APNs/FCM. This is a from-scratch build (permission prompt UX, token storage, a push
  service). Large, and orthogonal to curiosity.
- *Recommendation:* out of scope for v1; revisit as a platform feature.

**Option C — Email.** Send the morning note as email.
- *Pros:* reliable async reach; good for a *daily digest*; no client needs to be open.
- *Cons:* **no outbound email exists** in core or luna-service; needs an ESP integration,
  from-address/deliverability setup, unsubscribe handling. Real work, but self-contained
  and high-value for the "wake up to a note" experience.
- *Recommendation:* fast-follow after v1, specifically for the *daily digest* cadence
  (§D3), not per-thought.

**Option D — WhatsApp (existing `wa_send`).** Route urgent reflections to the user's
phone.
- *Pros:* the **one out-of-band push channel that already works** today; ideal for the
  rare *urgent* escalation ("competitor just repriced").
- *Cons:* `prompt_always` policy (needs a prior approval to send unattended); requires the
  WhatsApp plugin connected; wrong register for routine daily notes (too intrusive).
- *Recommendation:* reserve for the **urgent** tier only (§D3 escalation), never routine.

**Option E — Wait-for-next-open (passive).** Just persist; show nothing live.
- This is Option A minus the SSE live-append — strictly worse, since A already degrades to
  this when the client is closed. Not a separate choice.

### Recommendation

**Adopt Option A as the primary channel, with C (email digest) as a fast-follow and D
(WhatsApp) reserved for urgent escalation.**

Concretely:

1. **In-conversation, badged, pre-composed.** Add a thin SDK method
   `ctx.share_thought(thought: SharedThought, *, conversation_id=None, urgency="normal")`
   that wraps `post_muted_message` with `source="curiosity"` and `respond=False` (the
   reflection is content Luna already wrote during her dream pass — no extra turn). The UI
   gets one new badge (`curiosity`) alongside the existing `playbook` badge; identical
   render path.
2. **Fired by WS2, not by the plugin.** The reflection is *composed* during the nightly
   dream (a background run) and *stored*; the **outbound moment** is a separate scheduled
   fire so cadence/quiet-hours (§D3) gate delivery independently of composition. The
   trigger is luna-service's Plan 023 external scheduler: the control-plane ticker fires at
   the user's morning slot → relay forwarder **wakes** the suspended Fly machine → POSTs a
   signed `/fire` event → the curiosity plugin's fire handler pops the next queued thought
   and calls `share_thought`. This is the **"wake + POST trigger"** design in
   `luna-service/plans/023-external-scheduler/PLAN.md`, reusing the production-proven
   forwarder in `cloud/relay/forwarder.py`.
3. **Degradation is graceful.** If the machine is always-on (Pro tier), wake is a no-op. If
   the client is closed, the thought is already persisted and appears on next open. If the
   user connected WhatsApp and the thought is `urgent`, additionally route via `wa_send`.

**What must be built** (small, all in the curiosity plugin except the badge):
- SDK wrapper `share_thought` (thin; `post_muted_message` already does the work).
- One UI badge value `source="curiosity"` (mirror the `playbook` badge in `api.ts` /
  message renderer).
- A **delivery queue** table in the plugin (composed-but-undelivered thoughts) so cadence
  gating is separate from composition.
- The Plan 023 `/fire` handler in the plugin (WS2 owns the control-plane half).

**What is explicitly *not* built for v1:** web push (B), and email is deferred to a
fast-follow (C).

---

## D2. The format of a shared "thought"

A shared thought is a **fixed, skimmable template**. It is legible (the human sees Luna
think), auditable (findings cite wiki pages), interactive (one question), and honest about
cost (a "what this cost" line — the spend receipt from vision §Design-Principle-4).

### Template

```
🧠 {HEADLINE}                                    ← one line, the single takeaway

{2–3 FINDINGS}                                   ← each: a claim + a wiki link
  1. {finding} — [[Wiki Page]]
  2. {finding} — [[Wiki Page]]
  3. {finding} — [[Wiki Page]]                   ← 3rd optional

❓ {ONE QUESTION}                                 ← exactly one, answerable in a sentence

💸 {WHAT THIS COST}                              ← "~X min of research · ~$Y · Z pages read/written"

[ Go deeper ]  [ Redirect ]  [ Not useful ]      ← steer controls (see D4)
```

Rules:
- **One headline, at most three findings, exactly one question.** More than one question =
  a questionnaire = the thing the vision explicitly rejects.
- **Every finding links a wiki page** so the claim is inspectable and Luna distinguishes
  "I read this" from "I inferred this" (vision §5, risk R5).
- **The cost line is mandatory** — it is the spend receipt (Theme E3) inlined into every
  proactive message, so spend is never a separate report the user has to hunt for.
- **Steer controls are part of the message** (D4), not a separate UI.
- Target length: a phone-glanceable ~90 words of body. Long detail lives in the wiki, not
  the thought.

### Example 1 — growth mission, early (day 1)

```
🧠 Your biggest funnel leak is mobile checkout step 3, not the top of funnel.

  1. Mobile step 3 drops 47% of users — it asks "company size" before showing
     any value. Desktop drops only 12% there. — [[Funnel Map]]
  2. You're bidding on high-intent keywords ("invoice software pricing") but
     sending them to the generic homepage, not a matched landing page. — [[Landing Page Principles]]
  3. Teams in your category who fixed the matched-LP gap saw ~20% more
     trials from the same spend. — [[SEO / AIO / Virality]]

❓ Is "company size" used anywhere downstream, or can we drop it from step 3?

💸 ~18 min of research · ~$0.34 · read 14 pages, wrote 2 wiki pages

[ Go deeper on step 3 ]  [ Look at ads instead ]  [ Not useful ]
```

### Example 2 — growth mission, later (day 3, escalating toward a proposal)

```
🧠 I think I understand the funnel well enough to draft concrete landing-page fixes.

  1. Your top-3 paid keywords all land on the homepage; each deserves a matched
     page. I've outlined all three. — [[Landing Page Principles]]
  2. The event that actually predicts payment in your data is second-session
     return, not pageviews — but you don't track it yet. — [[Which Events Matter]]
  3. Two live pages have the same above-the-fold weakness (value below the fold
     on mobile). I critiqued both. — [[Funnel Map]]

❓ Want me to turn this into a ranked list of 7 changes you can hand to your
   builder — or wait until I've dug into the ad copy too?

💸 ~2.1 hrs total over 3 sessions · ~$3.80 · 61 pages read, 5 wiki pages, 12 facts

[ Draft the 7 changes ]  [ Keep researching ads first ]  [ Stop here ]
```

The second example is the **hinge**: the headline signals readiness, the question offers a
concrete next action, and the steer control `[ Draft the 7 changes ]` is the user *pulling*
the proposal forward — exactly the "understanding → call to action" arc from vision §6.

---

## D3. Cadence & noise control

Proactive messages are a **privilege, not a firehose** (vision §Design-Principle-7). The
controlling rule: **one great morning note beats ten interruptions.**

### Tiers

| Tier | What triggers it | Default cadence | Channel |
|------|------------------|-----------------|---------|
| **Routine** | Nightly dream produced ≥1 thought worth sharing | **≤ 1 message/day**, delivered at the user's morning slot | In-conversation (Option A) |
| **Digest** | Weekly rollup of the week's thoughts + open questions | **1/week** (e.g. Monday morning) | In-conversation now; email fast-follow |
| **Urgent** | Time-sensitive external event (competitor repriced, metric moved sharply) | **≤ 1/day**, bypasses quiet hours only if truly urgent | In-conversation + WhatsApp if connected |

### Concrete defaults

- **Frequency cap: at most 1 proactive message per day** in the Routine tier. If the dream
  produced several thoughts, they are **batched** into one note (headline = the strongest;
  the rest become findings or roll into the weekly digest). Never send two routine notes
  the same day.
- **Quiet hours: 21:00–08:00 local** by default. Nothing delivers during quiet hours except
  a genuine `urgent`, and even urgent is *held to the top of the next open window* unless
  the user opted into urgent-anytime. (Composition still happens overnight during the
  dream; only *delivery* respects quiet hours — this is why D1 separates compose from
  deliver.)
- **Morning slot: 08:00 local** default for Routine delivery. This is the "woke up to a
  note" moment the vision targets.
- **Urgent budget: ≤ 1 urgent/day.** A second "urgent" the same day is downgraded to
  Routine and batched. This prevents a broken news source from spamming.
- **Backoff on non-engagement:** if the user hasn't opened / reacted to the last **3**
  proactive notes, automatically drop Routine cadence to **1 every 3 days** and surface a
  gentle "I've been quiet on purpose — want me to resume daily notes?" This protects trust
  (risk R3) without going fully silent.
- **Global kill switch + per-mission mute:** the user can set "pause proactive messages"
  (all) or mute a specific mission's curiosity while keeping others.

### Escalation rules (Routine → Urgent)

A thought is `urgent` **only if all** of: (a) it references a *time-sensitive external
event* (news, competitor move, metric threshold crossed), **and** (b) acting late measurably
costs the mission, **and** (c) it wasn't already sent. Everything else is Routine. When in
doubt, Routine — the default bias is toward *less* interruption.

### Where the caps live

Per-user cadence state (last-sent timestamps per tier, quiet hours, engagement streak,
mute flags) lives in a **curiosity-plugin table** (mirrors the `plugin_interview_meta`
kv-pattern at `plugins/plugin-interview/plugin_interview/models.py:92-99`). The Plan 023
fire handler checks these caps *before* calling `share_thought`, so the scheduler can fire
freely and the plugin enforces politeness.

---

## D4. How the human steers curiosity (the two-way loop)

A reflection is a **surface, not a broadcast.** Every shared thought carries three steer
controls (the buttons in the D2 template). Reacting to a thought must change what Luna does
next.

### The three reactions

| Control | Meaning | What Luna does |
|---------|---------|----------------|
| **Go deeper** (on X) | "This thread is valuable — invest more here." | Raises the priority/weight of the linked wiki topic; the next dream pass spends its budget disproportionately on X; may schedule a focused research session sooner than the next nightly slot. |
| **Redirect** (to Y) | "Interesting, but I care more about Y." | De-prioritizes the current topic, adds/raises Y as a mission sub-topic, re-plans the next exploration around Y. |
| **Not useful / Stop** | "Don't spend on this." | Marks the topic `dropped` (won't be researched further); if repeated, lowers overall curiosity budget for the mission. |

### The loop, concretely

1. Luna delivers a thought via `share_thought` (source-badged message with steer buttons).
2. The buttons are lightweight UI that POST to a plugin route
   (`/api/p/plugin-curiosity/thoughts/{id}/react` with `reaction ∈ {deeper, redirect,
   stop}` and optional free-text). This mirrors how `plugin-interview` owns its own routes
   (`plugins/plugin-interview/plugin_interview/routes.py`).
3. **Free text is also a reaction.** If the user just *replies in chat* ("go deeper on the
   mobile form thing" / "stop looking at SEO"), the agent interprets it and calls the same
   internal `curiosity_steer(topic, action)` tool — so steering works with or without the
   buttons. The buttons are the fast path; natural language is the always-available path.
4. The reaction updates the **mission's topic weights** (the same weighted-coverage model
   `plugin-interview` already uses: `priority ∈ {low, normal, high, critical}` at
   `service.py:13`), which the next dream pass reads to decide where to spend.
5. The reaction is **logged with the thought** so Luna learns the user's taste over time
   (which kinds of findings get "go deeper" vs "not useful"), feeding memory facts about
   the user's interests.

The design goal: the user should feel they are **tuning a colleague's attention**, not
filing tickets. One tap redirects tomorrow's research.

---

# Theme E — Pacing & Spend

## E1. The "first 10 minutes" quick-win artifact

**Intuition to honour (vision §Design-Principle-2):** an early, shallow, *visible* pass
beats a long, silent, deep one. Users are wary of tokens vanishing into an opaque process.
So the very first thing Luna produces — within minutes, using **zero newly-configured
tools** — is a single legible artifact.

### The deliverable: the **Mission Kickoff**

A single in-conversation message (delivered via the same `share_thought`/muted path)
containing exactly three parts:

1. **Mission brief** — Luna's restatement of the goal *in her own words*, the sub-domains
   it touches, and how she plans to learn. Proves she understood the shape.
2. **First wiki stubs** — she creates (not fills) the initial wiki pages as titled stubs
   with a one-line intent each, and links them. Proves the knowledge base is real and she
   knows the territory.
3. **One insight** — a single, concrete, slightly non-obvious observation drawn from a
   *fast* pass (a few web searches + one or two read-only product tools), with a citation.
   Proves signal, immediately.

Plus the mandatory **cost line** and a **steer prompt** ("Want me to go deep on any of
these, or is the shape wrong?").

Hard constraints: **≤ ~10 minutes, ≤ a few hundred thousand tokens, read-only tools only,
one message.** No deep dive happens until the user has seen this and (implicitly or
explicitly) blessed it.

### Example — growth mission Kickoff

```
🧠 Mission Kickoff: "Grow traffic that converts to paying customers"

Here's how I'm reading this: it's really five linked jobs — (1) get the right
traffic, (2) match it to the right landing page, (3) remove funnel friction,
(4) track the events that actually predict payment, and (5) keep spend efficient.
I'll learn each, starting from your live data (read-only) plus best-practice research.

I've stubbed the wiki so you can watch me fill it in:
  • [[Funnel Map]] — how your actual funnel behaves, step by step
  • [[Which Events Matter]] — which tracked events predict payment
  • [[Ad Craft]] — what makes your category's ads convert
  • [[Landing Page Principles]] — matched pages vs generic homepage
  • [[SEO / AIO / Virality]] — how discovery is shifting in your space

One thing already stands out: your ff_wasted_spend report shows ~23% of paid
spend last month went to keywords with zero downstream trials — a fast, safe
place to reclaim budget. — [[Funnel Map]]

💸 ~7 min · ~$0.21 · 9 web pages + 3 product reports (ff_home_summary,
   ff_wasted_spend, ff_funnel), 5 wiki stubs

Want me to go deep on any of these tonight — or is the shape wrong?
```

(The `ff_*` tools are the real read-only tools in
[plugin-funnelfighters](../../plugins/plugin-funnelfighters/) —
`ff_wasted_spend`, `ff_funnel`, `ff_home_summary`, etc. — so this runs with **no new
integration**.)

---

## E2. When does "enough understanding" escalate learning → proposing?

Luna should convert understanding into a concrete proposal **only when she can defend it**.
We already have a proven readiness model to borrow: `plugin-interview`'s weighted-coverage
`is_ready()` (`plugins/plugin-interview/plugin_interview/service.py:83-96`).

### The escalation signal

Reuse that shape against the **mission's wiki topics** (each topic carries a
`priority ∈ {low, normal, high, critical}` and a `coverage ∈ 0..10`):

> **Ready-to-propose** = *every `high`/`critical` topic is covered to threshold* **AND**
> *priority-weighted coverage ≥ target %* **AND** *the proposal's key claims each cite a
> wiki page* (not an inference).

Concretely, the defaults mirror the interview plugin: `target_min = 7/10` per must-cover
topic, `target_pct = 80%` weighted. Additionally, curiosity-specific gates:

- **Grounding gate:** every claim the proposal rests on must trace to a *cited* wiki page
  (read, not inferred) — enforces vision risk R5 (no confident-but-wrong worldview).
- **Contradiction gate:** the last dream pass resolved (didn't just accumulate)
  contradictions on the must-cover topics.
- **User-signal accelerant:** a `Go deeper` reaction (D4) or an explicit "what would you
  do?" lowers the bar — the user is *pulling*, so Luna offers the proposal earlier even at
  ~70% coverage, clearly flagged as "early draft, still learning X."

When the signal trips, Luna doesn't silently act — she **offers** (as in D2 Example 2):
"I think I understand well enough to draft {concrete thing}. Want it now, or should I keep
learning {gap}?" The offer is a rung-3 event (draft/recommend, output-only) on the autonomy
ladder — nothing executes.

---

## E3. Spend transparency

**Principle (vision §Design-Principle-4):** the human should always roughly know why tokens
are being spent and what they bought. Two surfaces:

### (a) The per-session receipt (always on)

Every background session (a dream pass, a focused research burst) produces a **receipt**,
and the compact form is the **cost line already baked into every shared thought** (D2). The
full receipt is one tap away:

```
Session receipt — nightly dream, 2026-07-08 03:00–03:24

  Duration      24 min
  Cost          $0.51   (in: 180k tok · out: 42k tok)
  Read          17 web pages, 4 product reports
  Wrote         2 wiki pages updated, 1 created, 6 memory facts
  Produced      1 thought (delivered 08:00), 2 open questions
  Topics        Funnel Map (+3 cov), Which Events Matter (+2 cov)

  [ See the thought ]   [ Open the wiki diff ]
```

The receipt makes a multi-hour, no-user-in-the-loop session **legible after the fact** —
directly mitigating risk R2 (opaque/runaway spend). Receipts are per-session and also roll
up into a **mission-level running total** ("this mission has cost $6.20 across 9 sessions
this week").

### (b) Optional user-set budget / allowance

Let the user cap background spend. Concrete model:

- A per-mission **allowance** the user sets (e.g. `$5/week` or `50k tokens/day`), stored in
  the plugin's settings table.
- The scheduler/dream checks remaining allowance **before** starting a session. If a
  session would exceed it, Luna **holds** and sends a one-line note: *"I've used this
  week's research budget. Raise it, or I'll resume Monday."*
- Default: a **conservative allowance on** (not unlimited), so a fresh mission can't
  surprise the user. Suggested default `$3/week` background, tunable up.
- The allowance is *soft* for the quick-win Kickoff (E1) — the first 10-minute artifact
  always runs, because its whole job is to earn the trust that justifies spend.

This maps cleanly onto luna-service's tier model: Free tier = tight allowance + chat-only;
Pro = larger allowance + always-on ambient; the allowance UI is the same either way.

---

## E4. Depth control (shallow-first-then-offer-deep)

**Default: shallow first, depth opt-in and always tethered to something the user already
saw value in.** Luna does **not** ask the user to choose "quick tour vs deep dive" up front
(that's setup friction, the thing we're avoiding). Instead:

1. **Always start shallow.** The first pass is the E1 Kickoff — breadth, stubs, one insight,
   ~10 minutes. Legible and cheap.
2. **Offer depth, tied to a specific artifact.** Depth is only ever offered against
   something concrete the user just saw: *"Want me to go deep on `[[Funnel Map]]` tonight?"*
   — never an abstract "should I research more?"
3. **The user pulls depth** via a `Go deeper` reaction (D4) or natural language. Absent a
   pull, Luna stays at a **sustainable shallow rhythm** (the nightly dream keeps breadth
   fresh within budget) rather than silently diving.
4. **Depth is bounded by the allowance** (E3). A `Go deeper` schedules a focused session
   whose cost is drawn from — and capped by — the mission allowance, so "deeper" never
   means "unbounded."

This gives the emotional arc the vision wants (vision §9): Hour 1 *"it already gets the
shape,"* Day 1 *"it taught itself overnight and found something,"* Day 3 *"we think about
this the same way"* — each step is a shallow, legible pass the user chose to deepen, never a
long silent burn.

---

## Appendix — build checklist for v1 (WS4 slice)

Grounded in existing patterns; nothing here needs core surgery beyond one badge value.

| Item | Where it lives | Reuses |
|------|----------------|--------|
| `ctx.share_thought(thought, urgency)` SDK wrapper | curiosity plugin → core | `post_muted_message` (`luna/luna/agent/muted.py`), `source`/`respond` already supported |
| `source="curiosity"` UI badge | `luna/ui/src/lib/api.ts` + message renderer | mirror `source="playbook"` badge |
| Thought template + composer | curiosity plugin (dream pass) | — |
| Delivery queue + cadence/quiet-hours/allowance tables | curiosity plugin | `plugin_interview_meta` kv-pattern (`models.py:92-99`) |
| Steer routes `/thoughts/{id}/react` + `curiosity_steer` tool | curiosity plugin routes/tools | `plugin-interview` routes pattern |
| Readiness (`is_ready`) for propose-escalation | curiosity plugin service | `plugin-interview` `service.py:83-96` |
| Per-session receipt + mission running total | curiosity plugin | token-usage already surfaced in turn `done` events (`app.py` chat stream) |
| Scheduled fire → `/fire` handler | curiosity plugin + **WS2** | Plan 023 external scheduler + Composio relay forwarder |

**Deferred past v1:** web push (D1-B), email digest (D1-C, fast-follow), urgent-anytime
WhatsApp escalation beyond a connected-user opt-in.

---

*Cross-references: outbound trigger mechanism → **WS2** (scheduling); thought composition &
dream pass → **WS3** (plugin design) + **WS1** (wiki); mission object & autonomy rungs →
**WS5**.*
