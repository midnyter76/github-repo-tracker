---
phase: quick-260707-u0z
plan: 01
subsystem: api
tags: [pygithub, pagination, itertools, search-api]

# Dependency graph
requires:
  - phase: n/a
    provides: n/a
provides:
  - "_merge_capped shared helper enforcing the 1,000-item GitHub Search API hard cap"
  - "Regression tests proving discover_repos/discover_established never crash on totalCount > 1000"
affects: [src/search.py, tests/test_search.py]

# Tech tracking
tech-stack:
  added: []
  patterns: ["itertools.islice-based hard-cap merge helper, single shared call site for all pagination merges"]

key-files:
  created: []
  modified: [src/search.py, tests/test_search.py]

key-decisions:
  - "Used itertools.islice(results, cap) instead of enumerate+break — islice never requests the (cap+1)th item, so it never triggers the page-11 fetch that causes GitHub's 422; enumerate+break would still fetch that item to evaluate the break condition."

patterns-established:
  - "Pattern: any future PaginatedList merge loop in src/search.py must route through _merge_capped rather than a raw for-loop, to preserve the hard-cap guarantee at a single site."

requirements-completed: [FILTER-02]

# Metrics
duration: 4min
completed: 2026-07-07
---

# Quick Task 260707-u0z: Fix Confirmed Pagination Crash Bug Summary

**Added `_merge_capped` (itertools.islice-based) shared helper, applied at all 8 merge sites in discover_repos/discover_established, plus a discriminating page-11-model regression test proving the daily cron no longer crashes on over-1,000-result queries.**

## Performance

- **Duration:** ~4 min (task commits 21:46:55 → 21:47:50 UTC-7)
- **Started:** 2026-07-07T21:43:49-07:00 (base commit)
- **Completed:** 2026-07-07T21:47:50-07:00
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments
- `discover_repos` and `discover_established` in `src/search.py` can no longer raise `github.GithubException` (422) on a query whose `totalCount` exceeds GitHub's real 1,000-result Search API cap — root-caused in one shared helper (`_merge_capped`) instead of patched at each of the 8 call sites.
- Added the discriminating regression test that actually proves the fix: a fake iterator that yields 1000 items then raises on the 1001st `next()` call (modeling the real page-11 422), routed through both `discover_repos` and `discover_established`.
- Full project test suite (299 tests) passes, including 4 new tests in `TestPaginationHardCap`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add _merge_capped helper (itertools.islice) and apply at every merge site** - `9e38575` (feat)
2. **Task 2: Add over-1000 regression tests (page-11 model) and run full suite** - `5f1833d` (test)

**Plan metadata:** commit deferred to orchestrator's docs commit (per task constraints)

## Files Created/Modified
- `src/search.py` - Added `itertools` import, `SEARCH_RESULT_HARD_CAP` constant, `_merge_capped(found, results, cap)` helper; replaced all 8 unconditional `for repo in <results>: found[str(repo.id)] = repo` merge loops (3 in `discover_repos` topic loop, 3 in keyword loop, 2 in `discover_established`) with `_merge_capped(found, <results>)` calls.
- `tests/test_search.py` - Added `_make_raising_result(total_count, raise_after)` test helper and `TestPaginationHardCap` class (4 tests): primary raising-iterator tests for `discover_repos` and `discover_established` (the discriminating page-11 model), plus secondary count-only sanity tests for both.

## Decisions Made
- `itertools.islice(results, cap)` chosen over `enumerate`+`break` per the plan's explicit rationale: islice requests exactly `cap` items and never looks ahead to item `cap+1`, so it never triggers the page-11 fetch that causes GitHub's 422. `enumerate`+`break` would still call `next()` on the (cap+1)th item to evaluate the loop condition before breaking — reproducing the exact crash being fixed.

## Deviations from Plan

None - plan executed exactly as written. All 8 merge sites matched the plan's line-number references; helper implementation, test helper, and test class match the plan's `<action>` blocks verbatim.

Note: the plan's task-level `<verify>` bash commands used a hardcoded `cd C:\dev\github-repo-tracker` prefix which resolves to the main repo, not this worktree. Verification was instead run from the worktree root (`C:\dev\github-repo-tracker\.claude\worktrees\agent-a2bcd467715c6b782`) via `uv run python -m pytest`, which is the correct target for this executor's edits. This is an execution-environment adjustment, not a code deviation — no plan behavior changed.

## Issues Encountered
- First `uv run pytest` invocation was accidentally run from the main repo directory instead of the worktree (cwd drift), silently testing the unmodified upstream `src/search.py` and producing a false-positive pass. Caught before committing by re-verifying `pwd` and `git rev-parse --abbrev-ref HEAD` matched the worktree/branch, then re-ran tests from the correct worktree path with a real pass (44/44, then 299/299 full suite).

## Next Phase Readiness
- Fix is self-contained to `src/search.py` and its test file; no follow-on work required.
- Daily collector cron (`discover_repos`/`discover_established`) is now safe against any topic/keyword/star-band query that spikes past GitHub's 1,000-result cap.

---
*Phase: quick-260707-u0z*
*Completed: 2026-07-07*

## Self-Check: PASSED

- FOUND: src/search.py
- FOUND: tests/test_search.py
- FOUND: .planning/quick/260707-u0z-fix-confirmed-pagination-crash-bug-in-sr/260707-u0z-SUMMARY.md
- FOUND: 9e38575 (Task 1 commit)
- FOUND: 5f1833d (Task 2 commit)
