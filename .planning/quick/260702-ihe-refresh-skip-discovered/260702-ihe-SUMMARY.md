---
phase: quick-260702-ihe
plan: 01
subsystem: collector
tags: [python, pytest, github-api, rate-limiting, performance]

# Dependency graph
requires: []
provides:
  - "run() step 3 refreshes only tracked ids discovery did NOT return this run"
  - "test_monthly_cohort_preserved_when_30d_over_cap passes at any run date"
affects: [collector, search]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Skip redundant core-API refresh for ids already present in this run's candidates dict (freshest-wins via search data, not re-fetch)"
    - "Compute test date fixtures without pinning `now` when the production code under test also uses real-today internally"

key-files:
  created: []
  modified:
    - src/collector.py
    - tests/test_collector.py
    - tests/test_search.py

key-decisions:
  - "Filter tracked_ids to `[rid for rid in tracked_ids if rid not in candidates]` before calling refresh — cuts ~7,300 serial get_repo core-API calls to only the ids discovery missed"
  - "DATA-01 freshest-wins semantics preserved without code change to the freshness rule itself: ids discovery already returned already carry this run's fresh search data, so skipping their refresh call does not stale-fy them"
  - "Removed hardcoded `now = datetime(2026, 6, 27, ...)` from test_monthly_cohort_preserved_when_30d_over_cap; since_date_for() is now called with no now arg to mirror discover_repos' real production call"

patterns-established: []

requirements-completed: [PERF-refresh-skip, TEST-date-unpin]

# Metrics
duration: 3min
completed: 2026-07-02
---

# Quick Task 260702-ihe: Refresh Skip Discovered + Date Unpin Summary

**Trimmed `run()`'s refresh step to skip tracked ids already returned by discovery (cutting redundant core-API calls from ~7,300/run) and unpinned a calendar-date-dependent test so it passes on any run date.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-07-02T20:23:48Z
- **Completed:** 2026-07-02T20:26:08Z
- **Tasks:** 2 completed
- **Files modified:** 3

## Accomplishments
- `run()` step 3 in `src/collector.py` now calls `refresh(g, [rid for rid in tracked_ids if rid not in candidates])` instead of refreshing all tracked ids — most tracked ids are already returned by discovery in the same run (they still match the `created:>30d` topic/keyword queries), so re-fetching them via a serial `get_repo` call was pure wasted quota against the 1,000 req/hr GITHUB_TOKEN core-API limit.
- Updated the `run()` docstring ("Execution order" steps 3 and 4) and the inline comment above step 3 to drop the now-inaccurate "refresh wins / re-fetch all" framing and describe the discovery-missed-only behavior.
- Added `test_refresh_receives_only_discovery_missed_ids` to `tests/test_collector.py`, asserting refresh is called with exactly the ids discovery missed (not the overlapping ones).
- Unpinned `test_monthly_cohort_preserved_when_30d_over_cap` in `tests/test_search.py`: it previously computed expected query date strings using a hardcoded `now = datetime(2026, 6, 27, ...)`, but `discover_repos` calls `since_date_for()` internally with the real current date — so the fake match strings only matched on the day the test was written. Now both call `since_date_for()` with no `now` argument, matching production's real-today behavior at any run date.
- Full suite: 286 passed, 0 failed (previously 1 failed / 284 passed before this task).

## Task Commits

Each task was committed atomically:

1. **Task 1: Refresh only discovery-missed ids + docstring + test** - `243e1fe` (feat)
2. **Task 2: Un-pin the date in test_monthly_cohort_preserved_when_30d_over_cap** - `b380354` (test)

**Plan metadata:** committed separately by orchestrator (docs commit not included here per constraints)

## Files Created/Modified
- `src/collector.py` - `run()` step 3 filters tracked_ids to discovery-missed ids only before calling refresh; docstring/comments updated to match
- `tests/test_collector.py` - new `test_refresh_receives_only_discovery_missed_ids` in `TestRun` proving the filter behavior
- `tests/test_search.py` - `test_monthly_cohort_preserved_when_30d_over_cap` no longer pins `now` to a hardcoded calendar date

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

- `uv run python -m pytest tests/test_collector.py -q` → 45 passed
- `uv run python -m pytest "tests/test_search.py::TestDiscoverRepos::test_monthly_cohort_preserved_when_30d_over_cap" -q` → 1 passed
- `uv run python -m pytest -q` (full suite, CLAUDE.md verification gate) → 286 passed, 0 failed
- `src/search.py` confirmed unchanged (`git diff --stat src/search.py` empty)
- Token-safety grep gate (`test_os_environ_referenced_exactly_once`) still passes — no new `os.environ` references added

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced. This change only narrows an existing core-API call's input list; no new surface area.

## Self-Check: PASSED
