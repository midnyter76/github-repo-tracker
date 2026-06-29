
## Pre-existing failure: test_monthly_cohort_preserved_when_30d_over_cap (2026-06-28)

**Discovered during:** 03-02 plan execution (full test suite run)
**Test:** `tests/test_search.py::TestDiscoverRepos::test_monthly_cohort_preserved_when_30d_over_cap`
**Error:** `AssertionError: Monthly cohort repo (8-30d old) must be preserved via complementary range query when 30d window is over-cap (WR-02 / D-04)` — `assert '1' in {}`
**Status:** Pre-existing; also fails without Task 2 changes (confirmed via git stash).
**Out of scope:** This plan modifies only `.github/workflows/keepalive.yml`, `.github/keepalive`, and `tests/test_collector.py`.
