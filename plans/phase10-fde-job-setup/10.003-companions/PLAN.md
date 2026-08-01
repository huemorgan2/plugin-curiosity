# 10.003 — Companion upgrades: plugin-wiki + plugin-scheduler (+ adoption)

**Ships:** plugin-wiki **x.+1**, plugin-scheduler **x.+1** (each its own
repo/version/tests), then plugin-curiosity **0.9.2** (adoption patch).
Independent of 10.001/10.002 — can run in parallel or after; curiosity
feature-detects everything here (marketplace index lists latest only, so no
min-version pins) and keeps its fallbacks forever.

**Parent:** [../PLAN.md](../PLAN.md) §6. Every change below is GENERIC —
justified for the plugin on its own terms; nothing curiosity-specific.

---

## 1. plugin-wiki

1. **Provider extraction API** — `get_section(page, header, wiki=?)` →
   parsed bullets/numbered items; `get_table(page, header, wiki=?)` →
   header row + rows. Markdown-only parsing, no LLM. Unit-tested against
   messy pages (prose between blocks, duplicate headers → first wins).
2. **Page revisions** — `wiki_write` gains optional `reason` (one line);
   store (page, ts, reason, author-turn) per write; provider
   `revisions(page, wiki=?)` newest-first; UI: small "history" affordance in
   the wiki pane. Additive table; no behavior change without `reason`.
3. **Multi-wiki alignment** (owner's in-flight change): whatever ships must
   expose — create/list named wikis with descriptions, wiki-scoped provider
   reads, wiki-scoped `wiki_links`. This sub-phase only VERIFIES the seams
   curiosity needs and adds them if the in-flight change lacks them.

## 2. plugin-scheduler

1. **Named-unique triggers** — `trigger_create(..., unique_name=…)` →
   server-side upsert (update-in-place on name collision within the
   account); returns which happened. Kills duplicate-cadence TOCTOU at the
   source — invariants live in code, not prompt discipline. Applies to
   scheduler-service (prod on Render — enumerate/admin-key per runbook) +
   plugin tool schema.
2. **Trigger provenance** — `created_by` (plugin id / turn kind) + free
   `purpose` label; both returned by `trigger_list`. Additive columns.

## 3. plugin-curiosity 0.9.2 — adoption (feature-detect, fallback kept)

- JD/success parsing → provider `get_section`/`get_table` when present;
  bespoke parser stays as fallback.
- JD living-draft stamp prefers real `revisions()` history over
  role_version+plan-change join when present.
- Mission adoption binds a wiki: create named wiki
  (`mission: <slug>`, description = mission statement) when multi-wiki is
  present; store `missions.wiki_id`; page shelf + shelf rendering read
  wiki-scoped; re-mission archives (old wiki untouched, history shelf links
  it). Without multi-wiki: current global-namespace behavior unchanged.
- Heartbeat creation passes `unique_name=curiosity-setup-heartbeat` when
  supported; the 0.8.1 reaper stays (defense in depth), and its "raced
  duplicates" path should become unreachable — assert that in prod e2e.
- NOC "what happens next" renders provenance labels when present.

## 4. Verify

- Per-plugin unit suites (wiki parsing/revisions; scheduler upsert under
  concurrent create — two racing creates converge to one row).
- **Local dojo:** curiosity 0.9.2 + upgraded wiki/scheduler: mission
  adoption creates+binds a wiki; shelf reads scoped; JD stamp from
  revisions; two concurrent adoption-ish turns → exactly one heartbeat
  (upsert, no reaper involvement — check reaper log empty).
- **Downgrade leg:** curiosity 0.9.2 against OLD wiki/scheduler → all
  fallbacks hold (this is the feature-detect contract).
- **Production e2e:** upgrade path on a live prod-scheduler account;
  disposable accounts deleted after.
- Each repo: three version stamps where applicable, push (huemorgan2),
  publish to marketplaces.com.ai, `execution_summary.md` here covering all
  three ships.
