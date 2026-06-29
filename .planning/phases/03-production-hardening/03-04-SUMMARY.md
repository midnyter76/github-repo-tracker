---
phase: 03-production-hardening
plan: "04"
subsystem: pruning
tags: [snapshot-pruning, retention, hard-04, python, pytest]
dependency_graph:
  requires: [03-01]
  provides: [src/prune.py]
  affects: []
tech_stack:
  added: []
  patterns: [filename-date-pruning, injectable-defaults, tmp_path-testing]
key_files:
  created:
    - src/prune.py
    - tests/test_prune.py
  modified: []
key_decisions:
  - "Pruning compares filename stems (YYYY-MM-DD) against cutoff date rather than mtime — mtime is unreliable in GitHub Actions (checkout resets all timestamps)"
  - "Returns list[Path] of deleted files rather than a count — enables test assertion without mocking filesystem calls"
  - "Non-date-named files (e.g. backup.json) are skipped via ValueError catch on date.fromisoformat() — zero-injection filesystem input handling (T-03-11)"
  - "snapshots_dir absence is handled gracefully (returns []) — mirrors store.py safe-return pattern"
metrics:
  duration: "~8 minutes"
  completed: "2026-06-28"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 0
---

# Phase 3 Plan 4: Snapshot Pruning Module Summary

**One-liner:** `prune_snapshots()` deletes YYYY-MM-DD snapshot files older than 90 days by filename-date comparison (not mtime), with 8 passing pytest cases covering all edge cases.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create src/prune.py with prune_snapshots() | 737f0d4 | src/prune.py |
| 2 | Create tests/test_prune.py with 8 test cases | 8ff5b00 | tests/test_prune.py |

## What Was Built

### src/prune.py
Implements `prune_snapshots(now, snapshots_dir, retention_days)` with:
- Filename-date comparison via `date.fromisoformat(snap_path.stem)` — avoids mtime unreliability in GitHub Actions
- Cutoff computed as `(now - timedelta(days=retention_days)).date()` — strictly less than cutoff triggers deletion
- Non-date files silently skipped via `except ValueError: continue`
- Missing `snapshots_dir` returns `[]` immediately
- Returns `list[Path]` of deleted files for test assertions without mocking
- Imports `SNAPSHOT_RETENTION_DAYS = 90` and `SNAPSHOTS_DIR` from `src/config.py` (HARD-04, D-08)

### tests/test_prune.py
8 `TestPruneSnapshots` pytest cases covering:
1. Non-existent directory returns `[]` without raising
2. Empty directory returns `[]`
3. Old file (91 days ago) deleted and returned in list
4. Recent file (yesterday) NOT deleted
5. Today's file NOT deleted (cutoff is 90 days in past)
6. Non-date filename (`backup.json`) NOT deleted
7. Deleted file is actually gone from disk (not just in return value)
8. Mixed directory: only old file deleted, recent and today's files preserved

All tests use `tmp_path` fixture — no writes ever touch `data/snapshots/`.

## Verification Results

```
pytest tests/test_prune.py -v → 8 passed in 0.04s
python -c "from src.prune import prune_snapshots" → OK
pytest tests/ (excluding pre-existing test_search failure) → 169 passed
```

## Deviations from Plan

None — plan executed exactly as written. Both files match the exact content specified in the plan's `<action>` sections.

## Known Stubs

None. `prune_snapshots()` is fully functional — it deletes files by filename date and returns the deleted paths. No placeholder logic.

## Pre-existing Failures (Out of Scope)

`tests/test_search.py::TestDiscoverRepos::test_monthly_cohort_preserved_when_30d_over_cap` fails on the base commit before any changes from this plan. Already logged in `deferred-items.md`. Not caused by this plan's changes (`src/prune.py` and `tests/test_prune.py` do not touch `src/search.py` or `tests/test_search.py`).

## Threat Surface Scan

No new trust boundaries introduced beyond those analyzed in the plan's `<threat_model>`:

| Flag | File | Description |
|------|------|-------------|
| T-03-10 (mitigated) | src/prune.py | DoS via today's snapshot deletion — mitigated: cutoff is 90 days past; today's stem can never be < cutoff |
| T-03-11 (mitigated) | src/prune.py | Non-date filename injection — mitigated: `except ValueError: continue` skips all non-YYYY-MM-DD stems |

No new network endpoints, auth paths, file access patterns, or schema changes introduced.

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| `src/prune.py` exists | FOUND |
| `tests/test_prune.py` exists | FOUND |
| `03-04-SUMMARY.md` exists | FOUND |
| Commit `737f0d4` (feat prune.py) exists | FOUND |
| Commit `8ff5b00` (test test_prune.py) exists | FOUND |
