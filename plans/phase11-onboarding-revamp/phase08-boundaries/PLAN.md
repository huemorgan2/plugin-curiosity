# Phase 08 — Boundaries & recovery (11.007 / M6)

Policy object in plugin-goalseek, enforced at tool-execution — never prompt
discipline. Incident protocol in curiosity prompts. The midnight-call example
becomes a regression test.

## Changes

**plugin-goalseek 2.4.0:**
- `Policy` model per considerations 11.007 (plain_text + machine rule:
  action_class/channels/window with tz_source/limits/default deny/
  fail_mode closed/scope/origin/status/test_ref/confirmed_at).
- Tools `policy_propose` (Luna) / `policy_confirm` / `policy_suspend`
  (owner-only) / `policy_list`. Deny events surfaced, never silent.
- Enforcement hook wrapping action execution: unknown tz → refuse; novel
  action class → deny; every check counted (the "212 actions checked").
- Seed set proposed at Agree stage: quiet hours, spend cap, phone approval.

**plugin-curiosity:**
- Incident protocol prompts: kill-switch first · self-report before
  discovery · owner-approved customer recovery · blameless postmortem to
  wiki · fixes = policy diffs + tests · announced freeze with exit criteria ·
  earn-back small-slice; advice-only action items invalid; recovery and
  proposals never share a turn.
- "My rules" strip reads `policy_list` (graceful when goalseek absent).

## Testable units

| # | Unit | Test |
|---|---|---|
| 1 | Deny/allow matrix | goalseek unit: window×tz_source×channel×limits; fail-closed on unknown tz |
| 2 | Owner-only confirm | unit: agent cannot confirm/suspend; owner tools work |
| 3 | Deny surfacing | unit: denied action produces owner-visible event |
| 4 | Midnight-call regression | dry-run attempting 23:40 recipient-time call → denied; the shipped test_ref |
| 5 | Seed at Agree | curiosity unit: Agree stage proposes 3 defaults, status proposed |
| 6 | Rules strip | unit: strip hidden with no policies; counters correct |
| 7 | Live incident | dojo: simulated midnight-call incident → full protocol order verified (kill, self-report, postmortem, policy diff, freeze note) |

## Regression gate

Both plugin suites green; goalseek delegation regressions
(`test_goals_delegation.py`) green; dojo unit 7.

## Versions

plugin-goalseek 2.4.0, plugin-curiosity 0.18.0.

## Exit

`execution_summary.md`; enforcement-hook friction learnings → phase09
weekly-note wording.
