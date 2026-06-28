---
phase: 02-velocity-ranking-full-reporting
plan: "04"
subsystem: collector-integration
tags: [integration, wiring, d10-ordering, workflow, testing]
dependency_graph:
  requires: ["02-01", "02-02", "02-03"]
  provides: ["full-pipeline-integration", "reports-committed"]
  affects: ["src/collector.py", ".github/workflows/daily.yml", "tests/test_collector.py"]
tech_stack:
  added: []
  patterns:
    - "D-10 ordering: write_digest called before save_seen to prevent silent-seen on crash"
    - "Keyword-injectable defaults pattern extended to Phase 2 callables"
    - "Four-bucket fake helper (_empty_buckets) for Phase 2 test isolation"
key_files:
  created: []
  modified:
    - src/collector.py
    - .github/workflows/daily.yml
    - tests/test_collector.py
decisions:
  - "Appended Phase 2 steps after Phase 1 persist block (not rewritten) to minimize diff and reduce risk"
  - "Used _empty_buckets() helper in tests to avoid repetition across all four updated TestRun calls"
  - "test_file_pattern_data changed from exact-match to substring check to support combined pattern"
metrics:
  duration: "~10 minutes"
  completed: "2026-06-28T23:01:10Z"
  tasks_completed: 3
  tasks_total: 3
  files_changed: 3
---

# Phase 02 Plan 04: Collector Integration Summary

**One-liner:** Wired Phase 2 rank/seen/report pipeline into `collector.run()` in D-10 order (write_digest before save_seen), extended the daily workflow to commit `reports/**`, and updated all collector tests to inject Phase 2 fakes.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Extend collector.run() with Phase 2 steps (D-10 order) | a7c4338 | src/collector.py |
| 2 | Add reports/** to daily workflow commit pattern | db5e8dd | .github/workflows/daily.yml |
| 3 | Extend tests/test_collector.py (Phase 2 ordering + updated fakes + workflow assertion) | 01286e1 | tests/test_collector.py |

## What Was Built

**Task 1 — collector.py Phase 2 wiring:**
- Added `from src import rank, report, seen` and config path imports (`METADATA_PATH`, `REPORTS_DIR`, `SEEN_PATH`, `SNAPSHOTS_DIR`)
- Extended `run()` keyword-only params with five new injectable defaults: `compute_buckets=rank.compute_buckets`, `load_seen_fn=seen.load_seen`, `classify_fn=seen.classify_and_update`, `write_digest=report.write_digest`, `save_seen_fn=seen.save_seen`
- Appended Phase 2 pipeline block in D-10 order: compute buckets → build reported_ids union across all four buckets → load seen → classify → write_digest FIRST → save_seen
- `main()` unchanged — calls `run(build_client(), datetime.now(timezone.utc))` with no kwargs; all defaults wire through to real production code
- `os.environ` count stays at 1 (T-02-11 token-read invariant)

**Task 2 — daily.yml:**
- Changed `file_pattern: "data/**"` to `file_pattern: "data/** reports/**"` in the `Commit snapshot` step
- Resolves Pitfall 6 (digest generated but never committed) and satisfies REPORT-01 in production
- All other settings unchanged: SHA pin, cron, [skip ci], permissions

**Task 3 — test_collector.py:**
- Added `_empty_buckets()` module-level helper (four-bucket minimal structure with empty entries)
- Injected all five Phase 2 fakes into all four existing `TestRun` tests — no real rank/report/seen runs during tests, no real artifacts written
- Added `TestPhase2Wiring` class with three tests:
  - `test_phase2_steps_called`: each of the five Phase 2 callables invoked exactly once
  - `test_report_written_before_seen_saved`: D-10 ordering via shared `calls=[]` list; asserts `calls.index("write_digest") < calls.index("save_seen")`
  - `test_reported_ids_union_across_buckets`: feeds entries in two different buckets, captures ids passed to classify_fn, asserts both present
- Added `test_file_pattern_reports` asserting `"reports/**"` in workflow text
- Fixed `test_file_pattern_data` to substring-check `data/**` rather than exact-match the full `file_pattern` value (which is now `"data/** reports/**"`)

## Verification Results

| Check | Result |
|-------|--------|
| `pytest tests/test_collector.py -q` | 28 passed |
| D-10 ordering regex assertion | OK |
| `reports/**` in daily.yml | OK |
| `os.environ` count in collector.py | 1 |
| `git status --porcelain reports/ data/seen.json` after suite | empty (no real artifacts) |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. All Phase 2 callables are wired to real production defaults; `main()` runs the full pipeline with no kwargs.

## Deferred Issues

**Pre-existing test failure (out of scope):** `tests/test_search.py::TestDiscoverRepos::test_monthly_cohort_preserved_when_30d_over_cap` — WR-02 complementary range query for monthly cohort. Failure confirmed pre-existing before this plan's changes (verified via `git stash`). Logged to `deferred-items.md`. Scope belongs to Wave 2 sibling agents (02-02/03) or a future bug-fix plan.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The only new file-system access patterns are:
- `REPORTS_DIR` (reports/) — written by report.write_digest, committed by daily.yml file_pattern (existing T-02-12 mitigation)
- `SEEN_PATH` (data/seen.json) — read/written by seen module (T-02-10 D-10 mitigation applied)
Both surfaces were planned and addressed in the plan's threat model. No new threat flags.

## Self-Check

Checking created/modified files and commits exist:

| Item | Status |
|------|--------|
| src/collector.py | FOUND |
| .github/workflows/daily.yml | FOUND |
| tests/test_collector.py | FOUND |
| 02-04-SUMMARY.md | FOUND |
| commit a7c4338 (Task 1) | FOUND |
| commit db5e8dd (Task 2) | FOUND |
| commit 01286e1 (Task 3) | FOUND |

## Self-Check: PASSED
