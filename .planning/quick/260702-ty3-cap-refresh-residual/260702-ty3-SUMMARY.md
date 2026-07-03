---
phase: quick-260702-ty3
plan: 01
subsystem: collector
tags: [rate-limit, github-api, residual-refresh, config]
requires: []
provides:
  - REFRESH_RESIDUAL_CAP config tunable
  - star-prioritized residual cap in collector.run()
  - stage-count stdout print for Actions-log observability
affects:
  - src/collector.py run() step 3 (residual refresh)
tech-stack:
  added: []
  patterns:
    - "Sort-only-when-over-cap: avoid disk read (load_snapshots) and reorder unless residual exceeds the cap"
    - "Missing-key defaults to 0 via dict.get(rid, {}).get('stars', 0) for stable last-known-star lookup"
key-files:
  created: []
  modified:
    - src/config.py
    - src/collector.py
    - tests/test_collector.py
decisions:
  - "Cap default set to 500 (not configurable via env) — tunable directly in config.py per existing HARD-0x pattern"
  - "Sort by last-known stars descending, stable sort preserves original residual order for ties/zero-star ids"
metrics:
  duration: "~1 min (3 task commits)"
  completed: 2026-07-02
---

# Phase quick-260702-ty3 Plan 01: Cap Refresh Residual Summary

Bounded collector's per-run core-API residual refresh to REFRESH_RESIDUAL_CAP (500) ids, prioritized by last-known star count, preventing the GITHUB_TOKEN 1,000 req/hr quota trip that forced a ~40 min GithubRetry sleep on high-residual runs.

## What Was Built

1. **`src/config.py`** — Added `REFRESH_RESIDUAL_CAP: int = 500` in the HARD-05 region, documented with the quota-math rationale (500 get_repo calls at ~2 req/s finish in ~4 min, staying under the 1,000 req/hr core quota).

2. **`src/collector.py`** — `run()` step 3 now:
   - Computes `residual` (tracked ids discovery missed this run) as before.
   - If `len(residual) > residual_cap`: loads the latest snapshot via injectable `load_snaps` (defaults to `rank.load_snapshots`), looks up each residual id's last-known star count (missing ids default to 0), and stable-sorts residual descending by stars. Slices to the first `residual_cap` ids.
   - If `len(residual) <= residual_cap`: residual passes through unchanged — `load_snaps` is never called, preserving the original order and avoiding an unnecessary disk read.
   - Prints one plain stdout stage-count line (`collector: discovered=N tracked=N residual=N refreshing=N`) before calling `refresh(g, capped)` — no token/client/auth reference, per Pitfall 4 convention.
   - Two new keyword-injectable params added: `load_snaps=rank.load_snapshots` and `residual_cap=REFRESH_RESIDUAL_CAP`, matching the file's existing DI style.

3. **`tests/test_collector.py`** — New `TestResidualCap` class with 4 tests, all offline/DI-based (no monkeypatching):
   - `test_residual_over_cap_keeps_top_cap_by_stars` — 4 ids capped to 2, top-2 by stars kept.
   - `test_residual_at_or_under_cap_passes_through_unchanged` — under-cap residual unchanged, `load_snaps` spy asserts NOT called.
   - `test_id_missing_from_snapshot_sorts_as_zero` — id absent from snapshot sorts last, cut first.
   - `test_empty_snapshots_dir_still_bounds_residual` — empty snapshot list (`[]`) still bounds and preserves stable order.

## Deviations from Plan

None - plan executed exactly as written. Code matched the plan's prescribed implementation verbatim (task 2's `<action>` block); tests matched task 3's prescribed test bodies verbatim.

## Verification

- `uv run python -m pytest -q` → **290 passed** (286 existing + 4 new `TestResidualCap` tests), 0 failures.
- All pre-existing `TestRun` tests (`test_refresh_receives_only_discovery_missed_ids` → `["333"]`, `test_calls_all_discovery_and_persistence_functions` → `refresh(g, ["333","444"])`) pass unchanged — both stay under the default 500 cap so the sort branch never fires.
- `uv run python -c "from src.config import REFRESH_RESIDUAL_CAP; assert REFRESH_RESIDUAL_CAP == 500"` → OK.
- Manual source check confirms `load_snaps` and `refresh(g, capped)` patterns present in `src/collector.py` (plan `key_links`).

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, or trust-boundary changes. The change only reorders/bounds an existing internal id list before the existing `refresh()` call.

## Self-Check: PASSED

- FOUND: src/config.py (REFRESH_RESIDUAL_CAP present, verified via python import)
- FOUND: src/collector.py (load_snaps, residual_cap, capped, print stage-count line all present)
- FOUND: tests/test_collector.py (TestResidualCap class with 4 tests, all passing)
- FOUND: commit e654c92 (feat: add REFRESH_RESIDUAL_CAP tunable)
- FOUND: commit 3045eb6 (feat: cap residual refresh by star priority + stage-count print)
- FOUND: commit 69f4cec (test: add residual cap behavior tests)
