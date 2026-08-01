# Phase 6 — Execution Summary (onboarding & validation)

> Status: **COMPLETE** — run 14: **13/13 checks + 2/2 probes** on a genuinely
> fresh Luna. The road there, by run: 8 → 11/13 (approve-until-complete owner
> loop fixed setup; busy dream declined on thin-day judgment) · 9 → 12/13
> (aged wiki fixed busy-day; empty-day sim leaked today's revisions + context)
> · 10 → 12/13 (share_thought reaction turn raced quiet-conversation staging
> via ORDER BY updated_at DESC) · 11 → 11/13 (quiescence staging held, but
> check 7 still failed — the dream gate "since the last dream" references
> state the model can't observe; plus a 1b detector false-negative on a
> deferral phrase) · 12 → 12/13 (mechanical "within 24h" gate ALSO failed —
> undecidable without a clock; see learnings) · 13 → aborted (MacBook
> unplugged; Chromium suspended network I/O at 15% battery) · 14 → 13/13,
> zero nudges on the mission beat, empty-day dream declined citing age_days.

## What was done

1. **Explored Luna's real first-run flow** (no wizard UI exists): `plugin_onboarding`
   injects a setup addendum via `prompt_sections()` while `User.setup.complete` is
   false; the frontend auto-fires `POST /api/onboarding/start` on an empty fresh
   install, producing an unprompted greeting turn in a "Getting started" conversation.
   Tools: `update_self` / `complete_setup`.
2. **Mission-first onboarding shipped entirely in plugin-curiosity** (no core, no
   plugin_onboarding change). The no-mission `prompt_fragment` — which sits AFTER the
   onboarding addendum in the system prompt — instructs the agent to ask for a mission
   in its FIRST exchange (before name/emoji) and to adopt it with `mission_set` the
   moment it's stated, bridging it into identity with `update_self(field='mission')`.
   - 0.4.1: first version ("adopt it immediately").
   - 0.4.2: hardened after run 1 ("call mission_set IN THAT SAME TURN, before asking
     anything else — never defer it behind name, emoji, or other setup questions").
   27/27 unit tests green; fragment wording pinned in `tests/test_mission.py`.
3. **Stood up an isolated fresh Luna** for validation: port 8001, `luna_fresh` DB
   (alembic migrates on serve), `LUNA_REDIS_URL=…/1`, scratch `LUNA_MANAGED_DIR` with
   plugin_funnelfighters/plugin_playbooks/plugin_web_access copied from dev's
   managed_plugins, own scheduler-service account `fresh-luna` on :8123. 21 plugins
   load clean; funnelfighters ships installed-but-disabled (needs a real API key), so
   the growth mission runs on model knowledge — same as dev.
4. **Wrote the phase-6 dojo walkthrough** (`dojo/tests/curiosity-phase6/walkthrough.mjs`,
   headed Playwright): fresh-state assertion → unprompted mission-first greeting →
   same-turn mission adoption + identity bridge → same-day quick win + wiki seeded from
   zero → conversational setup completion → both recurring triggers on the fresh
   scheduler account → busy-day dream (consolidation + exactly one Morning thought) →
   empty-day dream no-op (wiki backdated 3 days) → playbook authored in chat with its
   side-effecting run approval-gated.

## Results

**Final: run 14 = 13/13 walkthrough checks + 2/2 probes.** Full arc on one fresh
install: empty state → mission-first greeting (missionIdx=161, nameIdx=-1) →
same-turn `mission_set` + identity bridge → 1,908-char same-day quick win + wiki
seeded 0→4 pages/5 open questions → conversational setup through two approval-card
waves (six `update_self` fields approved, `complete_setup` flipped auth/status) →
both recurring triggers on the fresh scheduler account → real Tavily research day
(revisions 6→8, 6 real-URL citations) → busy-day dream consolidation (8→10) with
exactly one Morning thought → empty-day dream graceful no-op (10→10, 0 thoughts,
"Every page has age_days >= 1 … Quiet night — nothing to consolidate.") →
approval-gated playbook run (pending row, zero executions). Probes: wiki sidebar
renders the mission wiki (11 nodes / 5 pages); rung-3 draft recommendation shared
as a grounded reflection citing [[mission-domain]] + [[competitors]]. Evidence:
`dojo/results/curiosity-phase6/run14/` (checks.json + 8 screenshots).

_(History — run 1: 0/2 early checks exposed fragment weakness; run 2:
green through the whole onboarding arc, checks 0–3b, 5, 8; run 3: node crash on an
uncaught Playwright timeout, exposed the SSE cancel-scope mechanism; run 4: 10/13;
run 5: killed by Chromium suspending network I/O on battery; run 6: 10/13 again —
which forced the live-forensics session that found the REAL root cause of every
"dead" setup turn: the approval gate [see learnings]. Run 7 added owner-approval
polling + a Tavily key, and still failed check 4: the approver exited on the first
assistant reply, but approval cards arrive in WAVES — identity fields first,
persona/purpose only after the first batch returns — and mid-turn continuation
messages persist early, so "a reply appeared" is a false done-signal; the second
wave parked the turn unapproved. Run 8 replaces reply-waiting with an
approve-and-poll loop that runs until `auth/status.onboarding_complete` flips.)_

## What was encountered / learned

- **Prompt-fragment strength matters at checklist boundaries.** 0.4.1's "adopt it
  immediately" lost to the onboarding addendum's own checklist: the model asked for
  the mission FIRST (inversion worked) but then deferred `mission_set` behind
  name/emoji ("Before I lock it in…"). 0.4.2's explicit "IN THAT SAME TURN / never
  defer" fixed it — run 2 adopted in the same turn, with the identity bridge.
- **Mission-first works in substance, not in the word "mission."** The greeting asked
  "What kind of work do you want me to own for you?" — dojo checks must match meaning
  (own-this-work framings), not the literal token.
- **Transient Anthropic ConnectTimeouts kill agent turns silently.** Three turns in
  run 2 (setup + both dreams) died on `httpcore.ConnectTimeout`; the conversation just
  never gets an assistant message. Dojo hardening: nudge-once for chat turns; for
  scheduler fires, require an assistant message after the injected fire prompt before
  judging the beat, and re-fire once on a dead turn.
- **Chat turns live and die with their SSE stream** (run 3). Turns execute inside
  `sse_starlette.EventSourceResponse`'s cancel scope: a hung Anthropic streaming
  request keeps the turn (and the busy composer) alive ~10 min until the SDK timeout,
  and closing/reloading the page CANCELS the in-flight turn (CancelledError + leaked
  asyncpg connections in the log). Dojo consequence, now encoded in `typeAndSend`:
  on a busy composer, reload the page — it cancels the stuck turn — then retype.
  Product follow-up (post-v1): detach turn execution from the SSE request scope if
  turns should survive a closed tab. Saved to memory (`luna-turns-die-with-sse`).
- **THE root cause of every "dead" setup turn (runs 2–6): the approval gate.**
  Identity writes (`update_self` for name/emoji/owner/persona/purpose) resolve to a
  `prompt` policy; the setup turn issues them as PARALLEL tool calls and each parks on
  `await approvals.request(...)` until the owner clicks a confirmation card. The dojo
  never clicked, so the turn blocked forever — silent but alive, indistinguishable from
  a dead turn from the outside. Proven live via a curl SSE probe: the turn streamed its
  opening text, hung; four pending `update_self` approval rows sat in the DB; approving
  them via `POST /api/p/plugin-approvals/{id}/approve` resumed the turn ~55 minutes
  later, ran all four tools, then persona/purpose cards, then `complete_setup` — and the
  stream finished with a normal `done` event. Earlier diagnoses (ConnectTimeout, hung
  Anthropic stream, SDK ~10min timeout) were wrong or incidental. Dojo fix: the
  walkthrough now plays the attentive owner — it polls pending approvals during the
  setup beat and approves plugin-onboarding cards, scoped so the playbook beat's gate
  assertion is untouched.
- **Approval cards arrive in waves; "a reply appeared" is a false done-signal** (run 7).
  The setup turn writes identity fields first, and only after that batch returns does
  the model write persona/purpose — a SECOND wave of cards. Mid-turn continuation
  messages persist as assistant messages while the turn is still running, so an
  approver that stops at the first assistant reply abandons the turn exactly when the
  second wave parks it (run 7's check-4 failure: name/emoji/owner approved, setup never
  completed). Fix: the owner loop approves + polls `auth/status` until
  `onboarding_complete` flips (10-min budget, nudge once at 6), with no reply-based
  exit at all. Run 8: check 4 green for the first time since run 2 — both card waves
  approved live, `complete_setup` ran, 11/13 overall.
- **"All pages created today" reads as setup noise even when today's work is real**
  (run 8). With Tavily live the research pass made a genuine cited edit
  (revisions 6→7), the pass's own routine reflection posted as a `share_thought`
  moment — and the dream STILL declined: mission created today + every page created
  today looked like install-day noise, not a learning day. Defensible again; the
  dojo day was unrealistic, not the dream. Fix: age wiki pages/revisions and the
  mission by 3 days before firing the research pass, so today's edit stands out on
  an established wiki.
- **A "nothing happened today" simulation must hide EVERY trace of today** (run 9).
  After a genuinely busy day, backdating `wiki_pages.updated_at` alone leaks: today's
  `wiki_revisions` rows survive, and — decisively — the busy dream's own
  "Consolidation complete" reply sits one minute above in the same conversation the
  next fire lands in. The run-9 empty-day dream read that context, said "3 pages
  touched today," and consolidated again — correct model reasoning, broken simulation
  (in run 8 the same context showed a DECLINE, which is why check 7 passed there).
  Fix: backdate revisions too, delete reflections, and park the empty-day fire in a
  fresh quiet conversation (scheduler fires land in the most recent conversation).
- **…and async reaction turns race that staging** (run 10). share_thought posts its
  moment fire-and-forget; the reaction turn was still running when beat 7 staged the
  quiet conversation, finished after the "Good night" exchange, bumped the onboarding
  conversation's `updated_at` — and `send_muted_message` targets ORDER BY updated_at
  DESC, so the fire landed back in the busy conversation. Fix: wait for global
  message quiescence (message count stable over a 30s window) before staging.
- **A prompt gate the model can't verify is no gate at all** (run 11). With the
  simulation finally airtight — quiescence held, the fire landed in the staged quiet
  conversation, every timestamp backdated — the empty-day dream consolidated anyway.
  The gate said "if nothing changed since the last dream," but the model has no
  observable record of when the last dream ran (reflections aren't tool-readable, and
  the staged conversation is fresh), so 3-day-old stub-looking pages read as
  never-consolidated backlog. Its reply even hallucinated "today's metrics research"
  — it never anchored on updated_at. Runs 9/10/11 failed three different ways for
  this one root cause. Fix in dream.py, not the dojo: the gate is now mechanical —
  "if no page has updated_at within the last 24 hours, reply 'quiet night' and stop;
  trust the timestamps over how the content looks." Rule of thumb: every autonomous
  no-op gate must be decidable from tool output alone.
- **…and "decidable from tool output" includes having a clock** (run 12). The
  mechanical 24h gate ALSO failed — the model consolidated without even mentioning
  timestamps. Root cause one level deeper: Luna's system prompt injects no current
  date/time anywhere (`luna/agent/system_prompt.py` has no clock), so the model saw
  `updated_at: 2026-07-05T…` but had no way to know today is 2026-07-08 — "within
  the last 24 hours" is undecidable without a *now*. Run 8's decline worked because
  that pattern was relative (every page same-day as the mission); an absolute
  recency test can never work. Fix: plugin-wiki's `_page_meta` now returns a
  server-computed `age_days` per page (float, rounded to 0.1), and the dream gate
  is numeric: "if every page has age_days >= 1 → quiet night, stop." 17/17
  plugin-wiki + 27/27 plugin-curiosity tests green. Corollary for phase 7: any
  scheduled routine that reasons about recency needs either a server-computed age
  or a fire-time timestamp in the trigger message — consider adding "fired at
  <iso>" to plugin_scheduler's emit wrapper.
- **Two run-8 "anomalies" that are actually phase-3 design working as built:** the
  mystery user-role message mid-research ("I filled in the [[mission-metrics]]
  page…") is `share_thought`'s moment posting, and its reaction turn saying "write
  tools aren't available this turn" is the REFLECTION_TOOLS read-only allowlist
  (wiki_toc/read/search + mission_get). Neither is a bug; both belong in the
  validation narrative.
- **The dojo's own "nudge" can be the killer** (run 4). Because turns die with their SSE
  stream, a `page.goto` used to nudge a silent conversation CANCELS a blocked-but-alive
  turn — run 4's setup turn got zero assistant output and the log showed two
  CancelledErrors and no network error: the walkthrough's 300s nudge murdered the turn
  it was probing (a turn that, per the above, was waiting on approval cards).
- **A late approval still resumes the turn cleanly.** The model response with the tool
  calls is fully received before the gates run, so the connection's death during the
  wait doesn't strand the turn; pool sockets to Anthropic show up CLOSED but the next
  request just opens a new one. Owner-approval latency is therefore safe at the turn
  level — but nothing tells the owner a turn is *waiting* vs *thinking* (product
  follow-up: composer/status hint while a turn is parked on approvals).
- **A seeded wiki is not a learning day** (run 4). The busy-day dream ran fine but judged
  the day thin — "all four pages were created today and not touched since" — and correctly
  declined to consolidate or emit a morning thought. Defensible model behavior; the dojo
  was wrong, not the dream. Fix: fire `curiosity-daily-research` run-now first and wait
  for wiki growth, then dream. (The empty-day no-op check passed legitimately in run 4 —
  the model reasoned from the backdated timestamps.)
- **…and a key-less research pass cannot produce one** (run 6). With no Tavily key the
  research trigger fired, hit "all web research requires a Tavily API key", made one
  token wiki revision, and the dream again (correctly) declined. On a fresh install the
  whole learning loop hinges on web access being configured. Run 7 gives the fresh Luna
  the real Tavily key via `LUNA_TAVILY_API_KEY` so the research day is real; the
  graceful degradation path (request_credential → vault card) stays validated from
  run 6's kickoff.
- **Battery power is a dojo hazard** (run 5). On a discharging MacBook, Chromium
  suspended network I/O (`net::ERR_NETWORK_IO_SUSPENDED`, no system sleep logged) — the
  SSE POST carrying the mission turn closed ~2s after send and the turn was cancelled
  with nothing in the server log. Same SSE cancel scope, new killer. Fixes: launch
  Chromium with `--disable-background-networking --disable-renderer-backgrounding
  --disable-backgrounding-occluded-windows --disable-background-timer-throttling
  --disable-features=BatterySaverMode`, run node under `caffeinate -i`, and give beat 2 a
  mission-poll + nudge-once retry (assert on the mission API, not on a single reply).
- **`| tee` masks the test's exit code** — run 3 reported exit 0 while node crashed
  on an uncaught Playwright TimeoutError. `set -o pipefail` from run 4 on; helpers
  that wait on UI state must not throw raw (typeAndSend now returns false instead).
- **plugin-scheduler records `outcome: "emitted: agent_prompt"` even when the agent
  turn dies mid-stream.** A dead dream turn is indistinguishable from a healthy no-op
  by outcome alone — run 2's empty-day check "passed" falsely this way. Follow-up for
  phase 7: fire outcome should reflect turn exceptions (e.g. `error: <type>`), not
  just emission.
- **Unconfigured web search degrades gracefully and visibly.** Kickoff hit
  `web_search is not configured` (no tavily key on the fresh install), probed the key
  gateway, found none, and used `request_credential` — the owner gets a secure vault
  form in chat, and the kickoff still delivered an artifact from model knowledge.
  This is exactly the right first-run behavior; no fix needed.
- **Scheduler fires land in the most recent active conversation** (here the
  "Getting started" onboarding conversation) as injected user messages. Cosmetically
  odd during onboarding but harmless; post-v1 consideration: a dedicated
  mission/journal conversation for scheduled turns.
- Fresh-Luna isolation recipe that works: shell env beats `.env` via
  `load_dotenv(override=False)` — only DATABASE_URL/REDIS_URL/MANAGED_DIR/
  SCHEDULER_ACCOUNT_ID/SECRET need overriding; service URL + Anthropic key inherit
  from `luna/.env`. In-tree symlinked plugins (curiosity/wiki/scheduler) pick up
  version bumps on restart; marketplace-installed ones must be copied into the
  scratch managed dir.

## For the future

- The scheduler-outcome follow-up above (phase 7 touches plugin-scheduler anyway).
- Onboarding + dream interleaving: if the owner abandons setup mid-flow, nightly
  fires still run with the setup addendum active. Run 2 suggests turns still execute;
  consider having plugin_onboarding suppress its addendum on scheduler-fired turns
  post-v1.
- `pending=4` approvals accumulated in run 2's playbook beat — the model retried the
  gated step; the gate held every time. Rails proven, but approval-card dedup for
  retried playbook steps would reduce owner noise.
