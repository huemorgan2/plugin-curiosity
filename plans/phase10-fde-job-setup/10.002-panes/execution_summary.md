# 10.002 Execution Summary — Missions pane rebuild + NOC pane

**Shipped:** plugin-curiosity **0.9.1** (commit `3dd7c91`, pushed huemorgan2, published to marketplaces.com.ai/mp/official) on top of luna core **031** (`SidebarSection.path`, luna commit `12c4658`, pushed huemorgan/luna).

## What was built

- **Luna 031 seam** — `SidebarSection.path: str = "ui/"` in `luna/plugins/base.py`; plugin_webui registry payload carries the path; the shell keys the plugin iframe by section id so same-plugin section switches remount to the right pane. Old hosts drop the kwarg (pydantic ignores it) — a path-shipping plugin degrades to its classic single pane, nothing breaks.
- **Missions pane rebuilt** to the four-section grammar (owner-facing, calm):
  1. **ACTIVE MISSION** hero — statement, phase in plain words, feeling chip (her own words), win/thread counts
  2. **WAITING ON YOU** needs strip — questions / waiting_on / ratify / pivot cards
  3. **JOB DESCRIPTION** — the living draft verbatim with `Living draft vN · revised <date>` stamp; pivot rides a "Big change" card
  4. **SETUP** ring + ability ladder and **GOALS** timeline with readiness dots
- **NOC pane** split out at `ui/noc/` — role wall, heartbeat pulse, gap board, what-happens-next, activity, shelf, history, autonomy/risk/pace chips. The machinery view; Missions stays the owner view.
- **esc() fix on both panes** — strips `[[wiki-link]]` markup before HTML-escaping so agent notes read as plain words on screen (found via screenshot inspection, not by any assertion — screenshots earn their keep).

## Verification record

| Pass | Scope | Result |
|---|---|---|
| unit | `pytest plugins/plugin-curiosity` | 187 passed |
| `panes-e2e.mjs` | 42-check local contract vs live :8001 — registry, serving, data shape, wiring | **42/42** |
| `panes-screens.mjs` | real browser through the shell (playwright): both panes, 031 remount both directions, JD stamp, no-jargon; screenshots | **9/9** |
| `panes-prod.mjs` | fresh Luna :8002, empty managed dir, **marketplace-installed 0.9.1**, prod scheduler (Render) via cloudflared tunnel, disposable HMAC account, dog-grooming-salon mission | **19/20** — check 15 ("dated goals") was a kickoff race: abilities land before goals. Verified post-hoc: 9 dated goals with readiness, abilities re-scored by the heartbeat fire (setup 4%→7%). |
| `panes-prod-pivot.mjs` | owner pivots the job itself ("booked solid — growth is off the table; pricing, no-shows, subscriptions") | **5/5** — role_version 1→2, plan_change `role_pivot`, JD `latest_pivot`, pivot card in needs, mission row survived |
| prod screenshots | shell pass re-run against :8002 post-pivot | **8/9** — see finding below; screenshots captured with the pivot card + JD v2 on screen |

Key prod proof: both panes were advertised and served **without a Luna restart** after runtime marketplace install — the 031 seam works through a real artifact, not just the symlinked tree.

Artifacts: `luna/dojo/results/curiosity-phase10/panes-prod/{checks.json, pivot-checks.json, overview-setup.json, overview-final.json, overview-pivot.json, 01-missions-pane.png, 02-noc-pane.png}` and `.../panes-e2e/` (local screenshots).

## Finding carried to 0.9.2 (jargon leak on prod data)

The prod screenshot pass failed its no-`S\d` check — on **data**, not chrome:

1. **Plugin-generated:** `overview.py:392` builds the next_up title as `f"Earn {nxt} ({label})"` → "Earn S3 (ratified)" renders on both panes. Fix: title from the label word only.
2. **Agent-authored:** the heartbeat agent writes stage codes into owner-visible free text — goal titles ("reach stage S3"), heartbeat notes ("Advanced S0→S2"). Fix: heartbeat prompt gets an owner-visible-words rule (codes are internal; owners see "posted", "ratified", …).

Both are queued for 0.9.2 (10.003 adoption release).

## UX guidelines checklist (vision/ux_guidelines.md §§1–7)

- §1 hierarchy — every section: eyebrow → bottom-line headline → one-line support → collapsed detail. Hero leads with the mission statement, NOC leads with the status bottom line. ✅
- §2 plain words — phase said in words ("Onboarding — I'm setting myself up to do this job well"); no S\d in chrome or served HTML/JS (asserted, 42-check pass B4). Prod data leak logged above for 0.9.2. ⚠️ (chrome ✅, data → 0.9.2)
- §3 one-line bullets — needs strip, gap board, next strip all single-line entries with kind chips. ✅
- §4 tooltips only behind (i) — `data-tip` only on (i) affordances (asserted, B5: every data-tip node has the help class). ✅
- §5 one gradient per page — hero card only (Missions), status card only (NOC). ✅
- §6 tokens — --bg #0b0e14, --panel #11151f, --line #232a3a, --violet accent, ok/amber/red semantics; Inter 15px; 11px uppercase 0.16em eyebrows. ✅
- §7 owner's own words — feeling chip quotes her verbatim ("digging in"), JD shown verbatim with the honesty line when it doesn't follow the four-block shape. ✅

## Cleanup

Disposable scheduler account `curiosity-10002-e2e` deleted from prod (verified: only the two hosted vaselin-test accounts remain). Cloudflared tunnel and :8002 Luna killed; DB `luna_prod10002` dropped.
