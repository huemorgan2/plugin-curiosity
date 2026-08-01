# Phase 07 — The automation loop (11.006 / M5)

Build → sample sign-off → hypercare → run. Every automation a first-class
object the owner can see; the catalog section goes live.

## Changes

- **models.py:** `Automation` — what/state {building, awaiting_your_signoff,
  hypercare, running, paused, retired}/scope/target/signoff_at (approval or
  explicit waiver)/clean_runs/override+ignore counters/value_refs.
- **automations.py (new):** `automation_register`,
  `automation_signoff_request` (N real inputs + would-have outputs),
  `automation_pause` (kill switch), `automation_state`. Grep all plugins for
  tool-name collisions first.
- **Go-live gate in code:** cannot leave `building` without kill switch +
  measurable target + failure detection.
- **Hypercare:** second-pass self-check, daily one-liner; exit only on
  `clean_runs ≥ N` + full weekly cycle + zero corrections; correction resets;
  auto-promote announced with numbers.
- **Adoption alarm:** override/ignore telemetry pages Luna → fix or propose
  retiring.
- **overview.py:** "What I run for you" section renders (plain state words:
  waiting for your OK / extra watch / running).

## Testable units

| # | Unit | Test |
|---|---|---|
| 1 | State machine | unit: all legal/illegal transitions; go-live gate refuses incomplete automations |
| 2 | Sign-off | unit: no autonomous run before signoff_at; waiver recorded distinctly |
| 3 | Hypercare exit | unit: counter math, correction reset, announce payload |
| 4 | Alarm | unit: override threshold fires page; retire proposal path |
| 5 | Catalog | unit: overview state words correct per state |
| 6 | Live | dojo: sign-off request → button approve (phase05) → hypercare → simulated corrections → stays; clean runs → promote announced |

## Regression gate

Full suite; tool-name collision grep clean; real-Luna catalog render.

## Version

plugin-curiosity 0.17.0.

## Exit

`execution_summary.md`; learned N (clean-runs threshold) recorded for
phase08 policy defaults.
