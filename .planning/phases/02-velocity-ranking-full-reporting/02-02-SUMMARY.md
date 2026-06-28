---
phase: 02-velocity-ranking-full-reporting
plan: "02"
subsystem: seen-store
tags: [tdd, stdlib, persistence, classification]
dependency_graph:
  requires: ["02-01"]
  provides: ["seen-store load/save", "classify_and_update", "new/returning markers"]
  affects: ["02-03 (report renderer consumes markers)", "02-04 (collector wiring writes updated store)"]
tech_stack:
  added: []
  patterns: ["corrupt-file guard (mirrors store.py)", "shallow-copy non-mutation", "injectable path args"]
key_files:
  created:
    - src/seen.py
    - tests/test_seen.py
  modified: []
decisions:
  - "Implemented exactly the RESEARCH.md reference implementation — no variation; D-08/D-09/D-10 satisfied"
  - "Combined Task 1 RED + Task 2 comprehensive tests into a single tests/test_seen.py in the TDD RED commit — avoids a double rewrite of the same file"
  - "All 10 tests committed before implementation per TDD RED gate"
metrics:
  duration: "~2 minutes"
  completed: "2026-06-28"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 02 Plan 02: Seen-Store Module Summary

Implemented `src/seen.py` — id-keyed seen-store with corrupt-file guard, indent-2 JSON persistence, and a pure `classify_and_update` that produces new/returning markers without mutating the input dict or writing to disk.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 RED | Failing tests for seen-store | f43cb78 | tests/test_seen.py (10 tests, all failing) |
| 1 GREEN | Implement src/seen.py | 37478c2 | src/seen.py (91 lines) |
| 2 | Comprehensive test coverage | — (included in RED commit) | tests/test_seen.py |

## What Was Built

**`src/seen.py`** — three exported functions:

- `load_seen(seen_path=SEEN_PATH)` — returns `{}` on absent file; catches `json.JSONDecodeError`, emits `warnings.warn(stacklevel=2)`, returns `{}` on corrupt file (T-02-04 mitigated).
- `save_seen(seen, seen_path=SEEN_PATH)` — creates parent directories, writes indent-2 JSON.
- `classify_and_update(seen, reported_ids, report_date)` — iterates `reported_ids`; marks each as `"new"` (adds `first_seen`) or `"returning"` (preserves existing `first_seen`). Uses `dict(seen)` shallow copy — never mutates the input (T-02-06 mitigated). Returns `(markers, updated_seen)` — disk write is the caller's responsibility after the report is written (D-10).

**`tests/test_seen.py`** — 10 pytest tests across 5 classes:

- `TestLoadSeen` (3 tests): absent file, corrupt JSON warn, valid round-trip
- `TestClassifyAndUpdate` (2 tests): new marker + first_seen, returning marker
- `TestSaveSeen` (2 tests): missing parent dir creation, load/save round-trip
- `TestClassifyAndUpdateComprehensive` (2 tests): non-mutation assertion, mixed new+returning
- `TestSameDayRetry` (1 test): D-10 same-day retry — run 1 saves, run 2 reads and classifies as returning

## Verification

All plan-level gates passed:

```
pytest tests/test_seen.py -q   → 10 passed
grep -c "full_name" src/seen.py → 0
grep -c "import github" src/seen.py → 0
from src import seen           → import OK
python -c "import src.seen; m,u=src.seen.classify_and_update({'1':{'first_seen':'2026-06-01'}},['1','2'],'2026-06-28'); assert m=={'1':'returning','2':'new'}" → OK
```

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Out-of-Scope Discovery (Deferred)

**Pre-existing test failure in test_search.py:**
`tests/test_search.py::TestDiscoverRepos::test_monthly_cohort_preserved_when_30d_over_cap` was already failing before this plan's changes (confirmed by reverting changes and re-running). Unrelated to seen-store; not caused by or fixable within this plan's scope. Deferred to owner of search module.

## TDD Gate Compliance

- RED gate: commit `f43cb78` — `test(02-02): add failing tests for seen-store module` — all 10 tests fail with `ModuleNotFoundError: No module named 'src.seen'`
- GREEN gate: commit `37478c2` — `feat(02-02): implement seen-store load/save/classify` — all 10 tests pass

## Known Stubs

None — all three functions are fully implemented with real behavior. No placeholders, TODO, or hardcoded empty returns.

## Threat Surface Scan

No new network endpoints, auth paths, or trust boundaries introduced. `src/seen.py` reads and writes `data/seen.json` (local filesystem only). All STRIDE threats in the plan's threat model were mitigated:

| Threat | Mitigation |
|--------|-----------|
| T-02-04 (DoS: corrupt JSON) | `except json.JSONDecodeError` → warn + {} |
| T-02-05 (Spoofing: repo rename) | Keys are `str(repo.id)`, never `full_name` |
| T-02-06 (Tampering: premature write) | `classify_and_update` never writes; returns `updated` for caller |

## Self-Check: PASSED

- `src/seen.py` exists and has 91 lines
- `tests/test_seen.py` exists and has 10 test functions
- RED commit `f43cb78` exists in git log
- GREEN commit `37478c2` exists in git log
- All acceptance criteria verified above
