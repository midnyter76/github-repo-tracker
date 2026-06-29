---
phase: 03-production-hardening
plan: "05"
subsystem: collector-orchestration
tags:
  - wiring
  - integration
  - gap-detection
  - gaming-filter
  - snapshot-pruning
  - workflow
dependency_graph:
  requires:
    - "03-01"  # gap.py (check_gap function)
    - "03-02"  # keepalive.yml (HARD-01)
    - "03-03"  # gaming.py (filter_gamed function)
    - "03-04"  # prune.py (prune_snapshots function)
  provides:
    - "collector.run() with all Phase 3 callables wired in correct positions"
    - "daily.yml with deletion-staging step for pruned snapshots"
    - "Integration test asserting Phase 3 call ordering"
  affects:
    - "src/collector.py"
    - ".github/workflows/daily.yml"
    - "tests/test_collector.py"
tech_stack:
  added: []
  patterns:
    - "Injectable keyword parameters extended with 3 Phase 3 callables"
    - "No-op lambda isolation in existing tests (Rule 1 fix for MagicMock comparison bug)"
    - "Call-log pattern in TestRunPhase3CallOrder (SimpleNamespace fake repos)"
key_files:
  created: []
  modified:
    - src/collector.py
    - .github/workflows/daily.yml
    - tests/test_collector.py
decisions:
  - "Added no-op lambdas (check_gap_fn, filter_gamed_fn, prune_fn) to all pre-existing run() test call sites to isolate them from Phase 3 real implementations (Rule 1 auto-fix: MagicMock.__gt__ raises TypeError when real filter_gamed evaluates forks_count > 0)"
  - "Positioned deletion-staging step between Run collector and Commit snapshot in daily.yml; file_pattern unchanged to preserve existing test assertions"
metrics:
  duration: "~25 minutes"
  completed: "2026-06-29"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
requirements:
  - HARD-01
  - HARD-02
  - HARD-03
  - HARD-04
---

# Phase 3 Plan 05: Collector Wiring + Workflow Fix Summary

Phase 3 wiring complete: check_gap + filter_gamed + prune_snapshots injected into collector.run() at their required call-order positions, daily.yml deletion-staging step added, and integration test asserting call ordering committed.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Wire Phase 3 callables into collector.run() | 647bdc8 | src/collector.py, tests/test_collector.py |
| 2 | Fix daily.yml deletion staging + integration tests | ea9c005 | .github/workflows/daily.yml, tests/test_collector.py |

## What Was Built

### Task 1: collector.py Phase 3 Wiring

Three surgical edits to `src/collector.py`:

1. **Import extension:** `from src import gap, gaming, prune, rank, report, search, seen, store` and `SNAPSHOT_RETENTION_DAYS` added to config import.

2. **Signature extension:** Three new injectable keyword parameters appended after `save_seen_fn`:
   - `check_gap_fn=gap.check_gap` (HARD-02)
   - `filter_gamed_fn=gaming.filter_gamed` (HARD-03)
   - `prune_fn=prune.prune_snapshots` (HARD-04)

3. **Call sites:** Three new call sites inserted at exact positions in run() body:
   - Step 0: `check_gap_fn(now, SNAPSHOTS_DIR)` — before `candidates: dict = {}` (fires before any API call, D-05)
   - Step 3.5: `candidates = filter_gamed_fn(candidates)` — after `candidates.update(refresh(...))`, before `write_snap` (prevents gamed data entering snapshots, Pitfall 5)
   - Step 6: `prune_fn(now, SNAPSHOTS_DIR, SNAPSHOT_RETENTION_DAYS)` — after `save_seen_fn(...)` as last line (LAST position required by D-09)

Final execution order verified:
```
check_gap → discover → established → load_ids → refresh → filter_gamed →
write_snap → write_meta → compute_buckets → load_seen → classify →
write_digest → save_seen → prune
```

### Task 2: daily.yml Deletion Staging Step

Inserted between "Run collector" and "Commit snapshot":
```yaml
- name: Stage pruned snapshot deletions
  run: |
    DELETED=$(git ls-files --deleted data/ 2>/dev/null)
    if [ -n "$DELETED" ]; then
      git rm $DELETED
    fi
```

`file_pattern: "data/** reports/**"` in the Commit snapshot step is unchanged (existing tests assert on this exact string).

### Task 2: New Tests

- **`TestWorkflowYaml.test_deletion_staging_step_present`**: asserts `git ls-files --deleted` is present in daily.yml (HARD-04)
- **`TestRunPhase3CallOrder.test_phase3_call_order`**: uses call-log pattern with `types.SimpleNamespace` fake repos to assert:
  - `check_gap` index < `discover` index (D-05)
  - `filter_gamed` index > `refresh` index AND < `write_snap` index (Pitfall 5)
  - `log[-1] == "prune"` (D-09: prune is absolutely last)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed MagicMock TypeError in pre-existing run() tests**

- **Found during:** Task 1 (after wiring filter_gamed_fn default to real `gaming.filter_gamed`)
- **Issue:** `filter_gamed()` calls `forks_count > 0` where `forks_count` is an unconfigured `MagicMock` attribute. `MagicMock.__gt__()` raises `TypeError` in Python's unittest.mock — it does NOT return a truthy value. This caused 2 pre-existing tests to fail: `TestRun.test_calls_all_discovery_and_persistence_functions` (repo_d with stars=200, which is exactly at the `GAMING_MIN_STARS` boundary so the ratio check runs) and `TestRun.test_refresh_overrides_earlier_discovery` (repo_refresh with stars=999).
- **Fix:** Added `check_gap_fn=lambda *a, **k: None`, `filter_gamed_fn=lambda c: c`, `prune_fn=lambda *a, **k: []` to all 7 pre-existing `run()` call sites in `TestRun` and `TestPhase2Wiring` classes. Pass-through lambdas preserve all existing test assertions while isolating tests from Phase 3 real implementations.
- **Files modified:** tests/test_collector.py
- **Commits:** 647bdc8 (included in Task 1 commit)

## Pre-existing Issues (Out of Scope)

One pre-existing test failure exists in `tests/test_search.py` unrelated to Plan 03-05:
- `TestDiscoverRepos::test_monthly_cohort_preserved_when_30d_over_cap` — fails before and after my changes; logged to deferred-items.

## Test Results

| Suite | Before | After |
|-------|--------|-------|
| `tests/test_collector.py` | 37 passed | 39 passed |
| `tests/` (full suite) | 179 passed, 1 failed (pre-existing) | 179 passed, 1 failed (pre-existing, out-of-scope) |

## Acceptance Criteria Verification

- [x] `from src import gap, gaming, prune, rank, report, search, seen, store` — present
- [x] `SNAPSHOT_RETENTION_DAYS` in config import — present
- [x] `check_gap_fn=gap.check_gap,` in run() signature — present
- [x] `filter_gamed_fn=gaming.filter_gamed,` in run() signature — present
- [x] `prune_fn=prune.prune_snapshots,` in run() signature — present
- [x] `check_gap_fn(now, SNAPSHOTS_DIR)` in function body (before candidates dict) — present
- [x] `candidates = filter_gamed_fn(candidates)` in function body (after refresh, before write_snap) — present
- [x] `prune_fn(now, SNAPSHOTS_DIR, SNAPSHOT_RETENTION_DAYS)` in function body (last line) — present
- [x] `python -c "from src.collector import run, build_client, main"` exits 0
- [x] daily.yml contains `git ls-files --deleted` — present
- [x] daily.yml still contains `file_pattern: "data/** reports/**"` — unchanged
- [x] "Stage pruned snapshot deletions" step appears BEFORE "Commit snapshot" — verified (line 28 vs 35)
- [x] `test_deletion_staging_step_present` — passes
- [x] `TestRunPhase3CallOrder` + `test_phase3_call_order` — passes
- [x] All 39 `test_collector.py` tests pass

## HARD Requirements Wired

| Requirement | Status | How |
|-------------|--------|-----|
| HARD-01 | Wired in Plan 03-02 (keepalive.yml) | — |
| HARD-02 | Wired here — check_gap_fn first in run() | check_gap_fn(now, SNAPSHOTS_DIR) before candidates dict |
| HARD-03 | Wired here — filter_gamed_fn after union before write | candidates = filter_gamed_fn(candidates) |
| HARD-04 | Wired here — prune_fn last + daily.yml staging fix | prune_fn last + git ls-files --deleted step |

## Self-Check: PASSED

Files verified:
- `src/collector.py` — FOUND (647bdc8)
- `.github/workflows/daily.yml` — FOUND (ea9c005)
- `tests/test_collector.py` — FOUND (ea9c005)

Commits verified:
- 647bdc8 — FOUND
- ea9c005 — FOUND
