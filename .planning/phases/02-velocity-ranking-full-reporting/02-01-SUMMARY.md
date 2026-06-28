---
phase: 02-velocity-ranking-full-reporting
plan: "01"
subsystem: ranking-engine
tags: [python, velocity, ranking, snapshots, cold-start, tdd]
dependency_graph:
  requires: [src/config.py, src/store.py, data/snapshots/, data/metadata.json]
  provides: [src/rank.py, src/config.py (Phase 2 constants)]
  affects: [02-02-PLAN.md (seen.py), 02-03-PLAN.md (report.py), 02-04-PLAN.md (collector wiring)]
tech_stack:
  added: []
  patterns:
    - pure-function velocity primitives (injectable paths, no side effects)
    - four-bucket contract dict (uniform entry shape consumed by Plan 03)
    - TDD RED/GREEN cycle with fixture builders and tz-aware UTC datetimes
key_files:
  created:
    - src/rank.py
    - tests/test_rank.py
  modified:
    - src/config.py
decisions:
  - Q1 resolved: weekly/monthly overlap allowed (a 3-day repo appears in both buckets)
  - Q3 resolved: any repo in current∩metadata is eligible for breakthrough buckets (metric-based, not universe-based)
  - Staleness threshold 30h (STALE_SPIKE_HOURS) baked into config; spike_24h degrades gracefully above threshold
  - velocity_per_day = per_hour * 24 for ALL buckets for uniform display semantics
metrics:
  duration: ~35 minutes
  completed: "2026-06-28T22:40:51Z"
  tasks_completed: 3
  files_changed: 3
---

# Phase 2 Plan 01: Velocity Ranking Engine Summary

**One-liner:** Hour-normalized four-bucket velocity engine with cold-start degradation, staleness guard, and negative-delta exclusion — pure stdlib, injectable paths, 41 tests green.

## What Was Built

`src/rank.py` implements the analytical core of Phase 2. It loads per-date snapshots from disk, inner-joins with metadata, and produces the four-bucket contract that `src/report.py` (Plan 03) renders verbatim.

### Files

| File | Action | Purpose |
|------|--------|---------|
| `src/config.py` | Modified | Added 14 Phase 2 constants: REPORTS_DIR, SEEN_PATH, ranking tunables (top-N caps, windows), and safety floors (AGE_HOURS_FLOOR=1.0, STALE_SPIKE_HOURS=30.0, DESCRIPTION_MAX_CHARS=120) |
| `src/rank.py` | Created (367 lines) | Seven public functions: creation_velocity, is_new, spike_velocity, rolling_velocity, load_snapshots, select_30d_window, compute_buckets |
| `tests/test_rank.py` | Created (41 tests) | Full TDD coverage: cold-start, activation, staleness, negative-delta, missing-metadata, boundary, sorting, cap, corrupt-file |

### Bucket Contract (Plan 03 reads this shape exactly)

```python
{
  "brand_new_weekly":  {"active": True,  "snapshots_available": N, "window_target": 7,  "entries": [...]},  # <= 10
  "brand_new_monthly": {"active": True,  "snapshots_available": N, "window_target": 30, "entries": [...]},  # <= 5
  "spike_24h":         {"active": bool,  "snapshots_available": N, "window_target": 2,  "entries": [...]},  # <= 10
  "velocity_30d":      {"active": bool,  "snapshots_available": N, "window_target": 30, "entries": [...]},  # <= 10
}
```

Each entry: `{id, full_name, html_url, description, created_at, stars, velocity_per_day}`.

## Commits

| Task | Hash | Message |
|------|------|---------|
| Task 1: config.py Phase 2 constants | adaf7dd | feat(02-01): add Phase 2 constants to config.py |
| Task 2 RED: failing tests | 682332b | test(02-01): add failing tests for rank.py velocity engine |
| Task 2 GREEN: rank.py implementation | dca098a | feat(02-01): implement rank.py velocity engine + compute_buckets |
| Task 3: comprehensive test suite | ee71255 | test(02-01): expand test_rank.py with comprehensive edge-case coverage |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed invalid datetime in test_zero_stars_returns_zero**
- **Found during:** Task 2 GREEN (test run revealed `ValueError: hour must be in 0..23`)
- **Issue:** Test helper `_iso(hour=48)` creates invalid datetime; `hour` must be 0-23
- **Fix:** Changed to `_iso(day=26, hour=12)` / `_iso(day=28, hour=12)` to represent 48-hour age
- **Files modified:** tests/test_rank.py
- **Commit:** dca098a

### TDD Note

Task 2 (tdd="true") and Task 3 (tdd="true") share the same test file `tests/test_rank.py`. The TDD cycle was: RED phase (Task 2) created the initial test file; GREEN phase (Task 2) implemented rank.py and fixed one test bug; Task 3 added 6 more targeted tests (overlap coverage, velocity_30d negative-delta, window_target assertions, monthly cap). Total: 41 tests.

### Pre-existing Out-of-Scope Issue

- `tests/test_search.py` fails on import (`No module named 'github'`) because PyGithub is not installed in the current execution environment. This pre-existed before this plan's changes and is logged to deferred-items. Not related to this plan.

## Known Stubs

None. `compute_buckets` computes real velocity from real snapshot data; no placeholders.

## Threat Surface Scan

No new network endpoints, auth paths, or trust boundaries introduced. `rank.py` makes no API calls. Description text is carried through raw (sanitization deferred to Plan 03 render boundary per T-02-01 disposition). `load_snapshots` wraps JSONDecodeError per T-02-02 mitigation. Negative-delta filter implements T-02-03 mitigation.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| src/rank.py created | FOUND |
| src/config.py modified | FOUND |
| tests/test_rank.py created | FOUND |
| 02-01-SUMMARY.md created | FOUND |
| adaf7dd commit (feat: config constants) | FOUND |
| 682332b commit (test: RED phase) | FOUND |
| dca098a commit (feat: rank.py GREEN) | FOUND |
| ee71255 commit (test: Task 3 expansion) | FOUND |
