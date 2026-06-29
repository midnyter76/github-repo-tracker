---
phase: 03-production-hardening
plan: "01"
subsystem: config-and-gap-detection
tags: [config, gap-detection, HARD-02, tdd]
dependency_graph:
  requires: []
  provides: [GAP_WARN_HOURS, GAMING_MIN_STARS, GAMING_STAR_FORK_RATIO, SNAPSHOT_RETENTION_DAYS, check_gap]
  affects: [src/gap.py, src/config.py]
tech_stack:
  added: []
  patterns: [injectable-defaults, silent-corrupt-file-guard, lexicographic-date-sort]
key_files:
  created:
    - src/gap.py
    - tests/test_gap.py
  modified:
    - src/config.py
decisions:
  - "Used lexicographic max over date-parseable stems to find most-recent snapshot (ISO 8601 sort property ensures correctness)"
  - "strptime stem filter on '%Y-%m-%d' excludes non-date files like backup.json from gap detection"
  - "Silent corrupt-file guard via except (KeyError, ValueError, json.JSONDecodeError) — matches store.py pattern"
metrics:
  duration: "~5 minutes"
  completed: "2026-06-29"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 3
---

# Phase 03 Plan 01: Config Extension + Gap Detection (HARD-02) Summary

**One-liner:** Phase 3 constants added to config.py and gap detection implemented via check_gap() using lexicographic date-stem filtering and silent corrupt-file guard.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Extend config.py with Phase 3 constants | 97f2875 | src/config.py |
| 2 (RED) | Failing tests for gap detection | 1e593d2 | tests/test_gap.py |
| 2 (GREEN) | Implement check_gap() | 5c69190 | src/gap.py |

## What Was Built

### Task 1: Phase 3 Constants in config.py

Appended a new `# Phase 3 — Production Hardening` block to `src/config.py` with four constants:

- `GAP_WARN_HOURS: float = 26.0` — HARD-02 gap threshold (2h slack over 24h cadence)
- `GAMING_MIN_STARS: int = 200` — HARD-03 minimum star floor before ratio filter applies
- `GAMING_STAR_FORK_RATIO: float = 50.0` — HARD-03 star-to-fork ratio threshold
- `SNAPSHOT_RETENTION_DAYS: int = 90` — HARD-04 pruning window (3x the widest velocity window)

All existing Phase 2 constants remain unchanged.

### Task 2: Gap Detection (HARD-02) — TDD

**RED commit:** 5 failing tests in `tests/test_gap.py` (class `TestCheckGap`) covering:
1. First-run safe — no snapshots, no exception, no output
2. Recent snapshot silence — delta < 26h produces no stdout
3. Old snapshot warning — delta > 26h prints `WARNING: Last snapshot ... was 30.0h ago (threshold: 26.0h). A collection run may have been missed.`
4. Corrupt JSON guard — malformed JSON does not raise
5. Non-date file exclusion — `backup.json` does not shadow dated snapshots

**GREEN commit:** `src/gap.py` with `check_gap(now, snapshots_dir, warn_hours)`:
- Filters snapshot files to date-parseable stems via `datetime.strptime(p.stem, "%Y-%m-%d")`
- Picks most-recent via `max(date_files, key=lambda p: p.stem)` (ISO 8601 lexicographic order)
- Prints `WARNING:` message when `delta_hours > warn_hours`
- Wraps parse path in `except (KeyError, ValueError, json.JSONDecodeError): pass`

## Verification Results

```
python -c "from src.config import GAP_WARN_HOURS, ..."  → OK
python -c "from src.gap import check_gap; print('gap OK')"  → gap OK
pytest tests/test_gap.py -v  → 5 passed
pytest tests/ (excl. PyGithub deps)  → 124 passed, 0 failed
```

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

T-03-02 mitigated as planned: `except (KeyError, ValueError, json.JSONDecodeError): pass` guards all parse paths in `check_gap()` — a corrupt snapshot file cannot crash the run.

## TDD Gate Compliance

- RED gate: commit `1e593d2` — `test(03-01): add failing tests for gap detection (HARD-02)` — 5 failures confirmed before implementation
- GREEN gate: commit `5c69190` — `feat(03-01): implement check_gap() for gap detection (HARD-02)` — 5 passes confirmed

## Self-Check: PASSED

Files created/exist:
- src/config.py (modified) — FOUND
- src/gap.py (created) — FOUND
- tests/test_gap.py (created) — FOUND

Commits exist:
- 97f2875 (feat: config.py constants) — FOUND
- 1e593d2 (test: failing gap tests) — FOUND
- 5c69190 (feat: gap.py implementation) — FOUND
