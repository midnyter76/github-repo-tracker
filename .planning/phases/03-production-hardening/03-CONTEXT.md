# Phase 3: Production Hardening - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Harden the tracker so it runs reliably for months without manual intervention. Four safeguards: (1) a keepalive mechanism that prevents GitHub's 60-day auto-disable; (2) gap detection that warns when a collection run was missed; (3) configurable star-gaming filters that exclude inflated repos before ranking; (4) snapshot pruning that keeps repo size growth bounded.

In scope: HARD-01, HARD-02, HARD-03, HARD-04.
Out of scope: acceleration metric (deferred from Phase 2), any new reporting features, changes to the ranking buckets or digest format.

</domain>

<decisions>
## Implementation Decisions

### Keepalive (HARD-01)
- **D-01:** A **separate `keepalive.yml` workflow** runs monthly via cron — does not rely on daily data commits resetting the 60-day timer (community behavior is ambiguous per STATE.md blocker).
- **D-02:** The keepalive job **writes a dummy commit** to the repo (a timestamp update) — definitively counts as repo activity, no ambiguity.
- **D-03:** Dummy commit target is **`.github/keepalive`** — a dedicated file that makes the purpose clear, doesn't pollute `data/` or `reports/`.

### Gap Detection (HARD-02)
- **D-04:** Warning is emitted to **stdout (Actions log) only** — not added to the digest. The digest is a reader-facing artifact; gap alerts are operator-facing.
- **D-05:** Gap check runs at the **start of `collector.run()`, before any discovery** — fires early before spending API quota, makes the warning appear at the top of the Actions log for easy diagnosis.

### Star-Gaming Filters (HARD-03)
- **D-06:** The **specific heuristics and thresholds are left to planning/research** to determine — Phase 3 implements the filter mechanism and makes heuristics configurable constants in `config.py`; the exact list (star:fork ratio, engagement floors, etc.) is a tuning detail for research to ground in real data.
- **D-07:** Gamed repos are **silently excluded from rankings** before any bucket is populated — no log output, no digest markers. Filter is configurable so false positives can be tuned without code changes.

### Snapshot Pruning (HARD-04)
- **D-08:** Retention window is **90 days** — 3× the widest velocity window (30d), giving headroom for missed days and velocity anomaly debugging with negligible repo size impact.
- **D-09:** Pruning runs **at the end of every `collector.run()`** after snapshot + report are written — integrated into the main run (no separate workflow), deletes 0 or 1 file per run at steady state.

### Claude's Discretion
- Exact keepalive cron schedule (monthly: first of month, last day, weekly? — within "monthly" intent).
- Whether pruning deletes the oldest file or all files outside the window (on a 90d retention, both produce the same steady-state result).
- Whether the gap-detection threshold (26 hours per HARD-02) is a configurable constant or hardcoded — lean toward configurable per `config.py` pattern.
- Star-gaming heuristic list, thresholds, and whether they apply to the full candidate set or only to ranked entries.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project planning docs
- `.planning/PROJECT.md` — core value, constraints, Key Decisions table.
- `.planning/REQUIREMENTS.md` §"Reliability & Hardening" — the HARD-01..04 requirement text this phase implements.
- `.planning/ROADMAP.md` §"Phase 3: Production Hardening" — goal + the 4 success criteria that must be TRUE.
- `.planning/STATE.md` — active blocker: "MEDIUM: 60-day keepalive via GITHUB_TOKEN commits — community conflict on whether bot commits reset the timer; validate within first 60 days (HARD-01, Phase 3)".

### Prior phase context (locked decisions this phase consumes)
- `.planning/phases/01-collection-loop/01-CONTEXT.md` — D-09 (GITHUB_TOKEN, `contents: write`), D-10 (commit-back via `stefanzweifel/git-auto-commit-action`), D-07 (UTC ISO 8601 timestamps).
- `.planning/phases/02-velocity-ranking-full-reporting/02-CONTEXT.md` — D-01 (acceleration deferred to Phase 3, but moved to deferred), D-06/D-07 (cold-start snapshot counting pattern for gap detection context).

### Existing code this phase reads/extends
- `src/config.py` — constants pattern; Phase 3 adds `SNAPSHOT_RETENTION_DAYS`, `GAP_WARN_HOURS`, and gaming-filter threshold constants here.
- `src/collector.run()` in `src/collector.py` — injectable-callable orchestration; gap detection wires in at the top, pruning wires in at the bottom.
- `src/store.py` — snapshot file management; pruning reads `SNAPSHOTS_DIR` to find and delete old files.
- `.github/workflows/daily.yml` — already has `workflow_dispatch` trigger and `stefanzweifel/git-auto-commit-action`; keepalive.yml mirrors the commit-back pattern.

### Tech stack (authoritative)
- `CLAUDE.md` §Technology Stack — `actions/checkout@v4`, `stefanzweifel/git-auto-commit-action@v5`, `contents: write` permission pattern.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/config.py` constants pattern — add `SNAPSHOT_RETENTION_DAYS = 90`, `GAP_WARN_HOURS = 26`, and gaming-filter thresholds following the existing grouped-with-comments style.
- `stefanzweifel/git-auto-commit-action` step in `daily.yml` — keepalive.yml uses the same action pinned to the same SHA for the dummy commit; `file_pattern: ".github/keepalive"`.
- `src/store.py` `SNAPSHOTS_DIR` path — pruning iterates this directory for `*.json` files sorted by date.

### Established Patterns
- **Injectable callables in `collector.run()`** — gap-detection function and pruning function follow the same `keyword-injectable` signature; tests pass fakes without monkeypatching.
- **Configurable constants in `config.py`** (D-03, Phase 1) — all new thresholds (retention days, gap hours, gaming filters) land here, never inlined.
- **`[skip ci]` commit messages** (D-10, Phase 1) — keepalive commit should also use `[skip ci]` to avoid triggering the main daily workflow.

### Integration Points
- Gap detection: new `check_gap(now, snapshots_dir)` function called as the **first step** in `collector.run()` before `discover()`.
- Gaming filter: new `filter_gamed(candidates)` function called after candidate union (step 4 in `collector.run()`) before `write_snap` / `rank.compute_buckets`.
- Pruning: new `prune_snapshots(snapshots_dir, retention_days, now)` call as the **last step** in `collector.run()` after `save_seen_fn`.
- Keepalive: standalone `keepalive.yml` workflow — no integration with `collector.py` or `src/`.

</code_context>

<specifics>
## Specific Ideas

- STATE.md blocker on keepalive (HARD-01): the 60-day timer uncertainty was explicitly flagged during Phase 1 discussion — D-01 (separate keepalive workflow) directly resolves it without relying on the ambiguous bot-commit behavior.
- Acceleration metric was deferred from Phase 2 (Phase 2 D-01); it is NOT being added here. Phase 3 is reliability only.

</specifics>

<deferred>
## Deferred Ideas

- **Acceleration metric** (2nd-derivative star growth) — carried forward from Phase 2 D-01 deferred list. Still not in scope; needs 3+ snapshots and is the most cold-start-fragile metric. Future phase if wanted.
- None raised during Phase 3 discussion — all topics stayed within hardening scope.

</deferred>

---

*Phase: 3-Production Hardening*
*Context gathered: 2026-06-28*
