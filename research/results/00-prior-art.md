# WS6 — Prior Art Scan

*Research deliverable for the Luna Curiosity initiative. Feeds WS1 (wiki), WS2
(scheduling), WS3 (plugin), WS4 (comms/pacing), WS5 (mission/trust).*

This is a scan of documented prior art directly relevant to a self-educating,
wiki-building, reflective, proactive agent. Each area gives the **mechanism**, a
**citation**, and a **how-it-applies-to-Luna** note. Where sourcing is thin or a claim
is folklore rather than documented, it is flagged explicitly.

**Skeptic's summary up front:** the two load-bearing pillars of the vision — the "LLM
wiki" and the "dream/consolidation" pass — are both real, documented patterns with
primary sources (Karpathy's gist; Letta's sleep-time compute paper). The weaker links
are (a) the wiki as an *evolving, self-maintained per-mission* store is documented at
*personal-notes* scale, not multi-tenant product scale, and (b) "curiosity" in our
product sense is a UX framing, **not** the RL term of art — conflating them would be a
category error.

---

## 1. Karpathy's "LLM Wiki" / LLM-authored knowledge base

**What he actually proposed.** In April 2026 Karpathy posted on X about a workflow
shift — using LLMs to build and maintain a personal knowledge base rather than to
generate code — and two days later published a gist, `llm-wiki.md`, describing the
pattern. This is a *pattern, not a product*. The gist is the primary source; the X post
is the announcement. (Note: some secondary write-ups mis-date this to Nov 2025 — the
gist and the viral post are April 2026.)

**The shape of it.** A three-layer architecture:

- **`raw/`** — immutable source material (papers, repos, clipped web articles). The LLM
  reads but never edits these.
- **`wiki/`** — LLM-owned markdown: summaries, entity pages, concept pages, and
  cross-references (backlinks). The LLM maintains this entirely.
- **Schema file** (a `CLAUDE.md`-style doc) — specifies wiki structure, naming
  conventions, and the workflows for ingest / query / lint.

Plus two bookkeeping files: **`index.md`** (every page with a one-line summary, grouped
by category — the LLM reads this *first*, before drilling into pages) and **`log.md`**
(a chronological operation log so the LLM knows recent activity).

**Three operations:**
- **Ingest** — process new sources one at a time: read, write a summary, update ~10–15
  wiki pages, maintain cross-references, append to the log.
- **Query** — search relevant pages, synthesize an answer *with citations*; good answers
  can be filed back as new pages.
- **Lint** — periodic health check for contradictions, stale claims, orphan pages
  (no inbound links), and data gaps.

**Why (his argument against RAG).** *"The LLM is rediscovering knowledge from scratch on
every question. There's no accumulation."* RAG re-pieces fragments at query time; the
wiki does synthesis **once** and keeps it current via maintenance. The distinction is
**compile-time vs query-time** knowledge assembly. He claims this works without any
embedding/vector infrastructure at *moderate scale* (~100 sources, hundreds of pages);
a gist commenter reports production use at ~4,000+ interlinked concepts.

**Sourcing note.** The gist is a genuine primary source and unambiguous about the
mechanism. But it is explicitly framed for **personal research at moderate scale**, run
by a human in the loop invoking ingest/query/lint. The vision's stronger claims — a
*living, self-maintaining, per-mission* wiki that grows autonomously on a schedule — go
**beyond** what the gist documents. That extension is ours to design and de-risk (SP1),
not something Karpathy validated.

**How it applies to Luna Curiosity.** This is the direct blueprint for the wiki (vision
§5, WS1). Adopt nearly wholesale:
- `index.md` + per-page one-liners is the answer to **A3** (context injection without
  blowing the budget): inject the index, fetch pages on demand. This retires the naive
  "stuff all pages into the prompt" approach.
- The **ingest / query / lint** triad maps cleanly onto our tools (`wiki_write_page`,
  `wiki_read`, and a lint pass that belongs inside "dream").
- His **lint** operation *is* the vision's contradiction-resolution and open-questions
  surfacing — fold it into the nightly dream (§4.4).
- Mandatory citations and the raw/ vs wiki/ split directly support **R5** (grounding /
  "read vs inferred"): raw sources stay auditable, wiki claims point back to them.
- **Borrow:** markdown-on-volume storage, the index-first navigation, lint-as-health.
  **Adapt:** make ingest agent-triggered and per-mission-scoped rather than
  human-invoked and global.

---

## 2. Agent memory & reflection architectures

### 2a. Generative Agents (Park et al., 2023)

**Mechanism.** A **memory stream**: a chronological, natural-language list of the
agent's observations. Retrieval scores each memory by a weighted sum of three
min-max-normalized signals — **recency** (exponential decay), **importance**
(LLM-assigned 1–10 "poignancy" score), and **relevance** (embedding similarity to the
current query). **Reflection** periodically clusters recent high-importance memories and
prompts the LLM to synthesize higher-level inferences (e.g. "Klaus seems withdrawn"),
which are written *back* into the stream as new memories and can themselves be reflected
upon — forming a reflection tree.

**Citation.** arXiv:2304.03442 — *Generative Agents: Interactive Simulacra of Human
Behavior* (ar5iv full text: https://ar5iv.labs.arxiv.org/html/2304.03442).

**Apply to Luna.** This is the canonical **reflection** pattern the vision's "dream"
descends from. Borrow:
- **Reflection = synthesize raw observations into higher-level insights, stored as
  first-class memories.** Exactly the "raw notes → distilled thoughts" of §4.4.
- The **importance score** is a cheap, reusable signal for *what to reflect on* and
  *what to surface to the human* — a natural noise-control input for WS4.
- **Recency/importance/relevance** retrieval is worth mirroring for the *atomic memory*
  layer (which already does semantic top-5; adding recency+importance is a small, proven
  upgrade), keeping the wiki as the separate structured layer.
- **Avoid:** the full memory-stream-of-everything is expensive and unstructured. Luna's
  design is better off writing structured wiki pages than accumulating an unbounded
  event log; use the stream idea for *episodic research notes*, not as the primary store.

### 2b. Reflexion (Shinn et al., 2023)

**Mechanism.** *Verbal* reinforcement learning: after a task attempt, the agent converts
environment feedback (binary/scalar reward, or a self-evaluation) into a natural-language
"self-reflection" — a textual lesson — stored in an episodic memory buffer and prepended
as context on the next attempt. No weight updates; learning is entirely in-context text.
Reported 91% pass@1 on HumanEval vs GPT-4's 80%.

**Citation.** arXiv:2303.11366 — *Reflexion: Language Agents with Verbal Reinforcement
Learning* (https://arxiv.org/abs/2303.11366).

**Apply to Luna.** Reflexion is about *learning from doing/failing*, which is rungs 4–5
(execution) — **out of v1 scope** (rungs 1–3). But the core idea — *distill an episode
into a durable natural-language lesson and carry it forward* — is precisely how a dream
pass should turn "today's research session" into a persistent insight. **Borrow** the
"reflection-as-text-appended-to-memory" loop; **note** that its RL framing (reward signal
→ reflection) doesn't apply until Luna is acting and getting outcomes. For a
learning-only agent, the "signal" is *contradiction found / question answered*, not task
reward.

### 2c. MemGPT / Letta (Packer, Wooders et al., 2023→)

**Mechanism.** LLM-as-operating-system. Tiered memory: **core memory** (small, editable
persona/human blocks living *in* the context window), **recall memory** (searchable
conversation history), **archival memory** (vector-indexed long-term store). The agent
has **tools to edit its own memory** and pages information in/out of context itself —
"self-editing memory." Forgetting is the default; remembering requires the model to
actively call the write tool.

**Citation.** MemGPT paper + Letta docs (https://docs.letta.com/guides/agents/architectures/sleeptime/);
overview: https://sureprompts.com/blog/letta-memgpt-walkthrough.

**Apply to Luna.** Two takeaways:
- The **hierarchical / tiered** split validates the vision's "atomic memory (fast) + wiki
  (slow, structured)" complementarity (§5, A1). Luna's split is different in shape but the
  principle — hot in-context summary vs cold retrievable store — is the same proven idea.
  An **index.md pinned in context + on-demand page fetch** is Luna's "core vs archival."
- **Self-editing via tools** is the right control model: give the agent `wiki_write_page`
  / `wiki_read` and let *it* decide what to persist, rather than regex auto-extraction.
  **Caveat (documented):** memory quality then depends entirely on model judgment — a real
  risk that argues for the lint/dream pass as a safety net.

### 2d. Voyager (Wang et al., 2023) — the "agent maintains a notebook" pattern

**Mechanism.** A lifelong-learning Minecraft agent with an **ever-growing skill library**:
verified executable-code snippets, each stored with an embedding of its description, so
relevant skills are retrieved as building blocks for new tasks. Plus an automatic
curriculum (what to learn next) and an iterative self-improvement loop (generate → execute
→ observe error → fix). Learns *in-context*, no fine-tuning.

**Citation.** arXiv:2305.16291 — *Voyager: An Open-Ended Embodied Agent with Large
Language Models* (https://arxiv.org/abs/2305.16291).

**Apply to Luna.** Voyager is the closest documented example of an agent that
**accumulates a durable, self-authored, retrievable artifact that compounds capability
over time** — conceptually the same move as Luna building a wiki, but the artifact is
*code skills* instead of *knowledge pages*. Two borrowable ideas:
- The **automatic curriculum** ("what should I learn next?") maps directly to the
  vision's open-questions list and the dream pass deciding tomorrow's research agenda —
  a concrete answer to *how Luna self-directs breadth-then-depth* (vision §4).
- **Verify before you store** (Voyager only saves *verified* skills) → Luna should prefer
  storing *cited* claims and flag unverified inferences (R5).

---

## 3. "Dreaming" / consolidation on a schedule

**Mechanism (documented).** Letta's **sleep-time compute** (April 2025 paper, Packer &
Wooders). A **dual-agent** model: a **primary agent** handles live interaction but cannot
edit its own core memory; a separate **sleep-time agent** runs asynchronously during idle
periods and rewrites the primary's memory blocks. It "transforms **raw context** into
**learned context**" — reasoning over conversation history and uploaded documents in the
background so answers at test time are cheaper and better. Reported figures: ~**1/5 the
tokens** to reach comparable answer quality; ~**15% more correct answers** at a fixed
inference budget; **2–3x** cost reduction when context is reused across follow-up queries.

**Citation.** https://www.letta.com/blog/sleep-time-compute/ ;
https://docs.letta.com/guides/agents/architectures/sleeptime/ ; efficiency numbers via
https://arize.com/blog/sleep-time-compute-beyond-inference-scaling-at-test-time/ .
(The blog is the primary vendor source; the specific benchmark tables live in the paper,
which the blog summarizes — treat the exact percentages as vendor-reported, not
independently replicated.)

**Related framing.** This generalizes the Generative Agents *reflection* idea (§2a) from
"cluster + synthesize" into "**spend idle compute to pre-digest context**." The consensus
framing across sources: shift work from high-latency, in-the-loop moments to idle periods.

**Apply to Luna.** This is the **direct precedent for the "dream" pass** (vision §4.4,
WS2) and it is *strong* — a named, published, numerically-supported pattern.
- Adopt the **dual-agent split**: a background "dreamer" that consolidates the day's raw
  research into distilled wiki edits + thoughts, separate from the live chat Luna. This
  cleanly separates "learn" from "converse."
- The efficiency story is a **spend-transparency asset** (E3, R2): background consolidation
  isn't just aesthetic — it *reduces* downstream token cost, which is a real answer to
  "why are tokens being spent while I sleep."
- **Sober caveat for WS2:** sleep-time compute assumes a **running process during idle**.
  Our biggest architectural unknown (research plan R1/B4) is that hosted Lunas *suspend*
  when idle — so we can't just "run a sleep agent in the background." The *pattern* is
  proven; the *scheduler that wakes a suspended Luna to run it* is the part we must build
  (SP2). Don't let the clean precedent hide that gap.

---

## 4. Proactive-assistant UX prior art (brief)

**Mechanism / principles (documented).** The dominant, repeatedly-stated design constraint
is a **notification budget**: proactive agents hit a hard ceiling of roughly **3–5
notifications per user per day** before they become noise. The recommended reframe: treat
each proactive message as a **withdrawal from a finite attention account** — firing it
costs *future* opportunities, so the agent must judge whether *this* signal outranks other
candidate signals. Other consensus patterns: **preview-before-act** (a deliberate moment
of friction / decision point for high-stakes or irreversible actions); **bounded
autonomy** (initiate work and present results, but require human approval to act); and
surfacing results as **digests** rather than per-event pings.

**Citations.**
- https://tianpan.co/blog/2026-05-13-background-agents-notification-budget-attention-economy
  (the "notification budget" framing)
- https://www.smashingmagazine.com/2026/02/designing-agentic-ai-practical-ux-patterns/
  (control/consent/preview patterns)
- https://arxiv.org/pdf/2410.04596 (*Need Help? Designing Proactive AI Assistants for
  Programming* — academic treatment of *when* to interrupt)

**Sourcing note.** These are design-blog + one academic paper, not hard product telemetry.
The "3–5/day" ceiling is a widely-repeated rule of thumb, not a measured universal — treat
it as a sane default to A/B, not gospel.

**Apply to Luna.** Directly supports vision §8.7 (bounded proactivity) and WS4 (D3 noise
control):
- Implement an explicit **daily notification budget** and **batch** reflections into one
  "morning note" rather than pinging per finding — this *is* the vision's "one great
  morning note beats ten interruptions."
- Use the Generative-Agents **importance score** (§2a) as the ranking function for the
  attention-budget "is this worth a withdrawal" decision.
- **Preview-before-act** maps onto the autonomy ladder: proposals (rung 3) are previews;
  execution (rung 4) requires approval — the UX literature independently arrives at Luna's
  ladder.

---

## 5. Curiosity / active-learning framing for agents

**Mechanism (the RL term of art).** In RL, "curiosity-driven exploration" means an
**intrinsic reward** for visiting states the agent's world-model predicts poorly:
intrinsic reward ∝ **prediction error** ("surprise"). The canonical work (Pathak et al.,
2017) computes curiosity as the error of a self-supervised forward-dynamics model in a
learned feature space, letting agents explore even with sparse/absent external reward.

**Citations.** arXiv:1705.05363 — *Curiosity-driven Exploration by Self-supervised
Prediction* (https://pathak22.github.io/noreward-rl/) ;
overview: https://apxml.com/courses/advanced-reinforcement-learning/chapter-4-advanced-exploration-strategies/intrinsic-motivation-prediction .

**Apply to Luna — with a warning.** This maps **only loosely and by analogy** to the
product. The honest mapping:
- **Analogy that holds:** "reduce prediction error / seek what you understand poorly" ≈
  "prioritize the sub-domains and open questions where Luna's understanding is weakest."
  The **open-questions list** and Voyager's **automatic curriculum** are the practical,
  LLM-native realization of "explore where uncertainty is highest" — no intrinsic-reward
  machinery required.
- **Category error to avoid:** do **not** import literal prediction-error intrinsic
  rewards or an RL training loop. Luna is an in-context LLM agent, not a policy trained on
  reward. "Curiosity" here is a **UX persona and a prioritization heuristic**, not an RL
  algorithm. The RL literature is inspiration and vocabulary, not architecture.
- **Usable heuristic:** let the dream pass tag each wiki page with a confidence /
  "how-well-do-I-understand-this" score; direct the next research session at the
  lowest-confidence, highest-mission-relevance pages. That is "curiosity" made concrete
  and cheap.

---

## Sources

**Karpathy LLM Wiki**
- Karpathy gist `llm-wiki.md` (primary): https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- VentureBeat coverage: https://venturebeat.com/data/karpathy-shares-llm-knowledge-base-architecture-that-bypasses-rag-with-an
- Atlan (LLM Wiki vs RAG, enterprise reality): https://atlan.com/know/llm-wiki-vs-rag-knowledge-base/

**Memory & reflection**
- Generative Agents — arXiv:2304.03442: https://ar5iv.labs.arxiv.org/html/2304.03442
- Reflexion — arXiv:2303.11366: https://arxiv.org/abs/2303.11366
- Letta/MemGPT walkthrough: https://sureprompts.com/blog/letta-memgpt-walkthrough
- Letta docs (sleep-time / architectures): https://docs.letta.com/guides/agents/architectures/sleeptime/
- Voyager — arXiv:2305.16291: https://arxiv.org/abs/2305.16291

**Dreaming / consolidation**
- Letta sleep-time compute (primary): https://www.letta.com/blog/sleep-time-compute/
- Arize summary (efficiency numbers): https://arize.com/blog/sleep-time-compute-beyond-inference-scaling-at-test-time/

**Proactive UX**
- Notification budget: https://tianpan.co/blog/2026-05-13-background-agents-notification-budget-attention-economy
- Smashing Magazine, agentic UX patterns: https://www.smashingmagazine.com/2026/02/designing-agentic-ai-practical-ux-patterns/
- *Need Help? Designing Proactive AI Assistants* — arXiv:2410.04596: https://arxiv.org/pdf/2410.04596

**Curiosity / active learning**
- Pathak et al. 2017 — arXiv:1705.05363: https://pathak22.github.io/noreward-rl/
- Intrinsic motivation via prediction error (overview): https://apxml.com/courses/advanced-reinforcement-learning/chapter-4-advanced-exploration-strategies/intrinsic-motivation-prediction

---

## Implications for Luna Curiosity

1. **The wiki has a real blueprint — adopt Karpathy's structure almost wholesale.**
   `raw/` (immutable, cited) + `wiki/` (LLM-owned pages) + `index.md` (read-first) +
   `log.md`, with ingest/query/lint operations. This answers WS1's storage-shape and
   context-injection questions (A2, A3) with a documented pattern, not a guess.

2. **Index-first navigation is the token-budget answer (R4).** Pin `index.md` +
   one-line summaries in context; fetch full pages on demand via a tool. Mirrors
   MemGPT's core-vs-archival split. Don't try to hold all pages in the prompt.

3. **"Dream" = sleep-time compute + Generative-Agents reflection.** Both are documented
   and one (Letta) reports concrete efficiency gains (~5x fewer tokens, ~15% more correct,
   2–3x on reuse). Implement it as a **separate background "dreamer" agent** that
   consolidates raw research into wiki edits + distilled thoughts, distinct from live chat.

4. **The clock is the real gap, not the dream logic.** The consolidation *pattern* is
   settled prior art; the unsolved part is that hosted Lunas suspend when idle, so
   sleep-time work needs an external waker (research-plan R1/B1/B4, SP2). Prior art
   confirms *what* to run at night but not *how* to run it in our suspend-happy hosting.

5. **Self-editing memory via tools beats regex auto-extraction.** Let Luna decide what to
   persist through `wiki_write_page`/`wiki_read` (MemGPT model), but pair it with a lint/
   dream safety net because memory quality then rides entirely on model judgment.

6. **Citations and raw/wiki separation are the antidote to R5 (confident-but-wrong).**
   Karpathy's immutable-raw + cited-wiki split, plus Voyager's "verify before store," give
   a concrete discipline: distinguish "I read this" from "I inferred this," store the
   former eagerly and flag the latter.

7. **Proactivity needs an explicit attention budget (~3–5/day, batched).** The UX
   literature independently converges on the vision's "bounded proactivity": one batched
   morning note, ranked by an importance score (borrowed from Generative Agents), not
   per-event pings.

8. **The autonomy ladder is validated by UX prior art.** "Preview-before-act" and
   "bounded autonomy — present results, require approval to act" are exactly rungs 3→4.
   Luna's ladder isn't idiosyncratic; it's where good proactive-agent design lands.

9. **"Curiosity" is a persona + prioritization heuristic, not RL.** Do not import
   prediction-error intrinsic rewards or a training loop. Realize curiosity as an
   **open-questions list + per-page confidence scores** driving the next research session
   toward weakest-understood, highest-mission-relevance areas (Voyager's automatic
   curriculum, in LLM-native form).

10. **Scope honesty:** the wiki and dream patterns are documented at *personal-notes /
    single-agent* scale. Extending them to a *living, per-mission, autonomously-maintained,
    multi-tenant* store is our novel engineering — real, but unproven by the prior art.
    Spikes SP1/SP2 exist precisely to de-risk that extension; don't treat the borrowed
    patterns as if they already cover it.
