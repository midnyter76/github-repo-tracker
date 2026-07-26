---
phase: quick-260726-hf2
plan: 01
subsystem: infra
tags: [pruning, retention, github-actions, reports]

requires:
  - phase: quick-260707-uec
    provides: prune_seen() and the HARD-04-SEEN retention pattern this plan extends
provides:
  - REPORT_HTML_RETENTION_DAYS constant (30 days)
  - prune_reports() sharing prune_snapshots' loop via a new _prune_dated() helper
  - collector.run() wiring that prunes reports/*.html last, after prune_meta_fn
  - daily.yml deletion-staging widened to cover reports/ as well as data/
affects: [reports, collector, github-actions-daily-workflow]

tech-stack:
  added: []
  patterns:
    - "_prune_dated(now, directory, retention_days, pattern) shared helper for
      any future filename-stem-dated retention job"

key-files:
  created: []
  modified:
    - src/config.py
    - src/prune.py
    - src/collector.py
    - tests/test_prune.py
    - tests/test_collector.py
    - .github/workflows/daily.yml

key-decisions:
  - "REPORT_HTML_RETENTION_DAYS=30, deliberately shorter than SNAPSHOT_RETENTION_DAYS=90 — HTML is a delivered email artifact already in the inbox; markdown is the permanent archive and is never pruned"
  - "prune_snapshots' public signature/behavior kept byte-identical by delegating its body to the new _prune_dated() helper — existing tests pass unedited"

patterns-established:
  - "Filename-stem-date retention: _prune_dated(now, dir, retention_days, glob_pattern) — reusable for any future per-date file type"

requirements-completed: [HF2-01]

duration: 25min
completed: 2026-07-26
---

# Phase quick-260726-hf2: Prune reports/*.html at 30 days, keep markdown forever Summary

**`prune_reports()` deletes `reports/*.html` older than 30 days via a shared `_prune_dated()` helper extracted from `prune_snapshots()`; markdown is never touched; wired into `collector.run()` and `daily.yml`'s deletion-staging step.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-26T19:16:00Z
- **Completed:** 2026-07-26T19:41:17Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- `REPORT_HTML_RETENTION_DAYS: int = 30` added to `src/config.py` with rationale comment; `SNAPSHOT_RETENTION_DAYS` untouched
- `_prune_dated()` extracted as the shared body of `prune_snapshots()` and the new `prune_reports()`; `prune_snapshots()`'s def line, defaults, docstring, and behavior are byte-identical
- `prune_reports()` deletes only `reports/*.html` older than 30 days by filename-stem date; `reports/*.md` of the same date and any age survives, proven by test
- `collector.run()` calls `prune_reports_fn(now, REPORTS_DIR, REPORT_HTML_RETENTION_DAYS)` last, after `prune_meta_fn`, injectable and tested for call order + exact args
- `daily.yml`'s deletion-staging step widened from `data/` to `data/ reports/` so pruned HTML deletions actually reach the commit; secrets handling (`GMAIL_APP_PASSWORD` wiring) untouched

## Task Commits

Each task was committed atomically:

1. **Task 1: Extract _prune_dated, add REPORT_HTML_RETENTION_DAYS + prune_reports, with tests** - `6d37c21` (feat)
2. **Task 2: Wire prune_reports into collector.run() and stage the deletions in daily.yml** - `98df212` (feat)

**Plan metadata:** committed separately by the orchestrator (docs commit not made by this executor per task constraints)

## Files Created/Modified
- `src/config.py` - Added `REPORT_HTML_RETENTION_DAYS: int = 30` with rationale comment, directly after `SNAPSHOT_RETENTION_DAYS`
- `src/prune.py` - Added `_prune_dated()` private helper; rewrote `prune_snapshots()` body to delegate to it (signature/docstring unchanged); added `prune_reports()`; updated module docstring
- `src/collector.py` - Added `REPORT_HTML_RETENTION_DAYS` import, `prune_reports_fn` injectable (defaults to `prune.prune_reports`), docstring Args entry, and the call in the prune-LAST section
- `tests/test_prune.py` - New `TestPruneReports` class: old/recent HTML, same-date `.md`/`.html` split (core guarantee), 400-day-old markdown survival, non-date-named files, missing directory, strict-`<` boundary
- `tests/test_collector.py` - All 16 `run()` call sites inject a silent no-op `prune_reports_fn` fake; new `TestPruneReportsWiring` asserts call order (`["prune", "prune_meta", "prune_reports"]`) and exact positional args (`now`, `REPORTS_DIR`, `30`)
- `.github/workflows/daily.yml` - Renamed "Stage pruned snapshot deletions" to "Stage pruned file deletions"; widened `git ls-files --deleted data/` to `git ls-files --deleted data/ reports/`

## Decisions Made
- Followed the plan's explicit interface contracts (helper name, call signature, injectable name) exactly — no deviation needed since the plan's `<interfaces>` section fully specified the shape.
- `prune_reports_fn` fakes in `tests/test_collector.py` are silent no-op lambdas (`lambda *a, **k: []`), never logging spies, to preserve the two pre-existing ordering assertions (`log[-1] == "prune"` and `call_log == ["prune", "prune_meta"]`) exactly as the plan's `<critical_hazard>` required.

## Deviations from Plan

None - plan executed exactly as written. Both tasks' verification gates passed on first attempt with no auto-fixes required.

## Issues Encountered

None. The plan's critical hazard (real `prune_reports` deleting real `reports/*.html` during test runs if any `run()` call site were missed) was avoided by injecting a no-op fake at all 16 sites, confirmed via `git status --porcelain reports/` empty checks after both task runs and the final full-suite run.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

`reports/` growth is now bounded to 30 days of HTML plus the permanent markdown archive. The daily GitHub Actions workflow will stage and commit these HTML deletions on its next scheduled run — no action needed until then; first observable effect is ~31 days after this fix ships, when the oldest HTML file crosses the retention boundary.

---
*Phase: quick-260726-hf2*
*Completed: 2026-07-26*

## Self-Check: PASSED

All 6 modified files verified present on disk (src/config.py, src/prune.py, src/collector.py, tests/test_prune.py, tests/test_collector.py, .github/workflows/daily.yml). Both task commits (6d37c21, 98df212) verified present in git log. Full suite: 363 passed. `git status --porcelain reports/ data/` empty after all runs.
