---
phase: quick-260726-gqd
plan: 01
subsystem: api
tags: [pygithub, exception-handling, refresh_tracked, search.py]

requires: []
provides:
  - refresh_tracked broadened to catch all GithubException per-repo, guarded by a max(10, 5%) skip threshold
  - RateLimitExceededException and BadCredentialsException re-raise immediately as systemic failures
affects: [collector-daily-run, snapshot-integrity]

tech-stack:
  added: []
  patterns: ["Threshold-guarded per-repo exception skip with immediate re-raise of systemic exceptions"]

key-files:
  created: []
  modified: [src/search.py, tests/test_search.py]

key-decisions:
  - "max_error_skips made keyword-only with a max(10, 5%) default so the existing positional collector.py call site and ~15 test fakes needed zero changes"
  - "UnknownObjectException (deleted/private repos) never counts toward the error-skip threshold — it is expected, not systemic"
  - "RateLimitExceededException/BadCredentialsException re-raise immediately via bare `raise`, bypassing the threshold entirely — a systemic failure should abort loud and fast, not slowly exhaust the skip budget"

patterns-established:
  - "Subclass-ordered except clauses (specific GithubException subclasses before the generic GithubException) for PyGithub error handling"

requirements-completed: [QUICK-260726-GQD]

duration: 3min
completed: 2026-07-26
---

# Quick Task 260726-gqd: Broaden refresh_tracked Exception Handling Summary

**refresh_tracked now catches all GithubException per-repo (not just UnknownObjectException) with a max(10, 5%) skip threshold, while RateLimitExceededException/BadCredentialsException still abort immediately — one bad repo no longer kills the whole daily run before a snapshot is written.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-07-26T12:05:52-07:00
- **Completed:** 2026-07-26T12:08:17-07:00
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- One bad repo (451 DMCA / 5xx) is now skipped with a warning instead of aborting the whole run — the daily snapshot still gets written
- Rate-limit and bad-credentials failures still abort immediately and loudly (unchanged fail-fast behavior for systemic errors)
- New RuntimeError abort path when unexpected per-repo errors exceed max(10, 5% of tracked ids), preventing a silently gutted snapshot from being written as the day's truth
- Deleted/private repos (UnknownObjectException) confirmed to never contribute to the abort threshold
- 5 new tests added; full suite green at 354 passed (349 pre-existing + 5 new)

## Task Commits

Each task was committed atomically (TDD):

1. **Task 1: Add failing tests for broadened handling and abort threshold** - `7b08884` (test)
2. **Task 2: Implement threshold-guarded exception handling in refresh_tracked** - `e3139e9` (feat)

**Plan metadata:** commit pending (docs, handled by orchestrator)

## Files Created/Modified
- `src/search.py` - `refresh_tracked` signature gains keyword-only `max_error_skips: int | None = None`; except-clause chain broadened from `ValueError` + `UnknownObjectException` to also catch `(RateLimitExceededException, BadCredentialsException)` (bare re-raise) and generic `GithubException` (threshold-counted skip, raises `RuntimeError` on overflow); docstring updated
- `tests/test_search.py` - 5 new methods on `TestRefreshTracked`: non-404 skip, threshold-exceeded RuntimeError, rate-limit immediate propagation, bad-credentials immediate propagation, deleted-repos-do-not-count-toward-threshold regression guard

## Decisions Made
- `max_error_skips` is keyword-only with a computed default (`max(10, len(tracked_ids) // 20)`) so no existing call site (collector.py, ~15 test fakes) needed changes — matches the plan's interface contract exactly
- Subclass ordering enforced: `ValueError` → `UnknownObjectException` → `(RateLimitExceededException, BadCredentialsException)` → generic `GithubException`, since all three specific exceptions are GithubException subclasses in PyGithub 2.9.1

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- The venv (`.venv/Scripts/python.exe`) lives in the main repo checkout, not in this worktree — tests were run by invoking the main-repo interpreter against the worktree's working directory (`PYTHONUTF8=1 /c/dev/github-repo-tracker/.venv/Scripts/python.exe -m pytest`). No files or config were changed to work around this; it's an environment-path note only.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `refresh_tracked` change is self-contained and backward-compatible; `collector.py` untouched as required
- No follow-up work identified; this closes the T-GQD-01 threat register item from the plan

---
*Phase: quick-260726-gqd*
*Completed: 2026-07-26*
