# Phase 01 — first contact: execution summary

**Status: shipped.** Luna core minor (plan 037) + curiosity 0.12.1.

## What changed

### A. Core fresh-boot self-intro (luna repo, plan 037)
- New `luna/onboarding/boot.py`: evidence-based once-ever intro — skip if the agent
  ever spoke or the owner ever sent a real message; retry cap 3 counted by the
  intro's own muted rows; reuses/creates a "Welcome" conversation; posts a muted
  moment so the intro is a normal agent bubble. Skip/sent/failure all logged.
- `cli.py` serve startup hook (not plugin on_load — those die with the bootstrap
  loop) with a 20 s settle so the intro turn sees the full toolset + prompt overlays.
- Content contract: warm one-liner, 2–3 before→after examples, plain words, no
  tool/plugin/feature names, ends with exactly ONE question — and defers that
  question to setup instructions, which is the hook curiosity's `core.onboarding`
  claim rides to own the first direction.

### B. Curiosity intro dominance (curiosity 0.12.1)
- `research.py` INSTALL_KICKOFF_CONTENT rewritten: teach possibility with 2–3 tiny
  concrete before/after examples (inquiries overnight → drafts in minutes; unknown ad
  spend → weekly one-pager; "we should follow up" → warm nudge), plain words, no tool
  or plugin names, "starting small and earning more"; keeps the no-mission/NOW/
  QUALIFIED/end-on-question contracts.
- `mission.py`: step 1 of MISSION_GATE_FLOW and MISSION_FIRST_FLOW folds ONE tiny
  before/after example into the very first ask.
- Version stamps agree at 0.12.1 (manifest / pyproject / luna-plugin.toml);
  `test_phase_10006` version test rewritten to treat the in-code manifest as
  authoritative instead of hardcoding.

## Test results

- Curiosity suite: **334/334 pass** (incl. 3 new tests: kickoff teaches possibility,
  both gate flows fold an example into the first ask, version stamps agree).
- Luna 037 suite: **6/6 pass**. Pre-existing unrelated failure in 004.1
  (`test_finalize_generates_persona_and_completes`) confirmed broken at HEAD.
- Live QA on a fresh isolated Luna (port 8767, fresh postgres DB, isolated
  LUNA_MANAGED_DIR with wiki + scheduler + curiosity 0.12.1):
  - intro arrived unprompted ~20 s after boot;
  - intro was mission-first with before→after examples and a single closing
    question (the mission ask) — curiosity dominance confirmed;
  - failed model turn → logged, retried on later boots, delivered on attempt 3,
    cap of 3 held;
  - restart after success → no duplicate.

## Learnings → adjust later phases

1. **LLM provider fragility is the top live-QA risk.** The luna/.env Anthropic key is
   out of credits; openai/openrouter keys empty; only gemini works, and it needs a
   temporary models.yaml override (`google:gemini-flash-latest`) + `google-genai`
   installed in luna/.venv. Later phases with dojo runs (02, 03, 05, 07, 08) must
   budget for this same setup, or Roy tops up the Anthropic key.
2. **DB rows are the assertion, logs are garnish** — muted rows + assistant rows in
   postgres were reliable ground truth; log lines flushed late or not at all. Live
   checks in later phases should query the DB, not grep logs.
3. **The defer-to-setup-instructions clause worked exactly as designed** — core never
   mentions curiosity, yet the first question came out as the mission ask. Phase 02's
   MissionDraft flow can rely on this hand-off point.
4. Gemini's intro output was on-contract (shape held across models) — the content
   contracts in prompts are model-portable; phase 02+ prompt work can keep relying on
   contract-style instructions.
