---
phase: "01-collection-loop"
plan: "02"
subsystem: "search"
tags: ["api", "search", "rate-limiting", "tdd", "github-api"]
dependency_graph:
  requires: ["01-01"]
  provides: ["src/search.py"]
  affects: ["01-03", "01-04"]
tech_stack:
  added: []
  patterns:
    - "safe_search pre-checks search.remaining before each new query (Pattern 2)"
    - "Injected search= parameter for zero-network unit testing"
    - "str(repo.id) keying throughout for rename/transfer safety"
    - "warnings.warn for cap events (no token/client in any output)"
    - "split_star_band integer midpoint → two contiguous sub-bands"
key_files:
  created:
    - "src/search.py"
    - "tests/test_search.py"
  modified: []
decisions:
  - "D-04 implemented: NEW_REPO_WINDOWS=[7,30] drives create-windowed discover_repos"
  - "D-05 implemented: both discover passes cap-check at 900 threshold"
  - "D-11 implemented: discover_established issues star-banded queries with no created: window"
metrics:
  duration: "~25 minutes"
  completed: "2026-06-27"
  tasks_completed: 3
  files_count: 2
---

# Phase 01 Plan 02: API Discovery Layer Summary

**One-liner:** Search layer with topic-union + keyword-fallback discovery, 900-threshold cap handling on both passes, and rate-paced safe_search — all via injectable search parameter for zero-network tests.

## Tasks Completed

| Task | Name | RED Commit | GREEN Commit | Tests |
|------|------|------------|--------------|-------|
| 1 | Pure query builders + safe_search + cap helpers | 0db38dd | 9811a87 | 26 |
| 2 | discover_repos + discover_established | 7d7fba3 | 86606fc | 10 |
| 3 | refresh_tracked | 7d7fba3 | 86606fc | 6 |

**Total tests:** 42 new (50 overall including test_config.py). Zero network calls.

## Decisions Made

- **D-04:** `discover_repos` issues queries for each window in `NEW_REPO_WINDOWS = [7, 30]`, generating the focused ~150–300 tracked universe.
- **D-05:** Cap check (`over_cap`) runs after every `safe_search` call in both `discover_repos` and `discover_established`; threshold = 900 (`TOTAL_COUNT_CAP_WARN`).
- **D-11:** `discover_established` issues 2 bands × 6 topics = 12 date-independent queries, catching old-but-spiking repos that date-windowed discovery can't see.

## Verification Gates Passed

```
uv run pytest tests/ -q   → 50 passed, 0 failed
grep QUALIFIER_EXCLUSIONS src/search.py  → 4 matches (all query builders)
grep stars:>= src/search.py              → 1 match (keyword builder only, line 61)
grep .totalCount src/search.py           → 4 matches (cap checks in both passes)
grep def split_star_band src/search.py   → 1 match
grep -Eic '(print|logging).*(token|auth| g )' src/search.py → 0
grep -v comment | grep -c get_topics()   → 0
grep get_repo(int( src/search.py         → 1 match (refresh_tracked)
grep UnknownObjectException src/search.py → 1 match
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added `timedelta` to datetime imports**
- **Found during:** Task 1 implementation
- **Issue:** Plan's `<action>` listed `from datetime import datetime, timezone` but `since_date_for` requires `timedelta` for date subtraction.
- **Fix:** Added `timedelta` to the import: `from datetime import datetime, timezone, timedelta`
- **Files modified:** `src/search.py`
- **Commit:** 9811a87

**2. [Rule 1 - Bug] Fixed test assertion for band-split query count**
- **Found during:** Task 2 GREEN verification
- **Issue:** Test `test_over_cap_band_splits_into_two_sub_queries` expected 13 queries (total_bands_topics + 1), but the correct count is 14 (initial over-cap query + 2 sub-band re-queries + 11 normal = total_bands_topics + 2). The initial over-cap query is still recorded.
- **Fix:** Changed assertion to `total_bands_topics + 2`.
- **Files modified:** `tests/test_search.py`
- **Commit:** 86606fc

**3. [Rule 1 - Bug] Removed `get_topics()` from docstring**
- **Found during:** Task 3 acceptance grep
- **Issue:** Docstring text "Does NOT call repo.get_topics()" caused the acceptance grep `grep -v '^[[:space:]]*#' src/search.py | grep -c 'get_topics()'` to return 1 instead of 0. Docstring lines are not comment lines (`#`) so the grep matched them.
- **Fix:** Rephrased to "Does NOT call the repo.get_topics method".
- **Files modified:** `src/search.py`
- **Commit:** 86606fc

### TDD Gate Note

Tasks 2 and 3 were initially included in the Task 1 GREEN implementation commit (9811a87). To maintain proper TDD gate compliance, the implementations were stripped from `src/search.py` in the Task 2/3 RED commit (7d7fba3) and restored in the GREEN commit (86606fc). The RED commit correctly shows `ImportError: cannot import name 'discover_repos'`.

## Known Stubs

None. All functions are fully implemented with correct behavior.

## Threat Surface Scan

No new trust boundaries introduced beyond those in the plan's threat model:
- T-01-04 (token disclosure): mitigated — zero `print`/`logging` referencing client, token, or exception repr; grep gate returns 0.
- T-01-05 (rate-limit DoS): mitigated — `safe_search` pre-checks `search.remaining`; `over_cap` fires on both discovery passes at threshold 900.
- T-01-06 (malicious repo data): accepted per plan — data stays in-memory dicts until Plan 03 serializes via `json.dumps`.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| src/search.py | FOUND |
| tests/test_search.py | FOUND |
| 01-02-SUMMARY.md | FOUND |
| commit 0db38dd (Task 1 RED) | FOUND |
| commit 9811a87 (Task 1 GREEN) | FOUND |
| commit 7d7fba3 (Tasks 2+3 RED) | FOUND |
| commit 86606fc (Tasks 2+3 GREEN) | FOUND |
| 50 tests pass, 0 failures | PASSED |
