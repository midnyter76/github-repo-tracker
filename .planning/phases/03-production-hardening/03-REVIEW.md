---
phase: 03-production-hardening
reviewed: 2026-06-28T00:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - src/config.py
  - src/gap.py
  - src/gaming.py
  - src/prune.py
  - src/collector.py
  - .github/workflows/keepalive.yml
  - .github/workflows/daily.yml
  - tests/test_gap.py
  - tests/test_gaming.py
  - tests/test_prune.py
  - tests/test_collector.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: fixed
---

# Phase 03: Code Review Report

**Reviewed:** 2026-06-28
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Reviewed all five Phase 3 source files (`config.py`, `gap.py`, `gaming.py`, `prune.py`, `collector.py`), both workflow YAML files, and all four test modules. The implementation is generally solid: gaming filter logic is correct, prune logic and boundary handling are correct, the collector call-order wiring is correct, and token safety is well-implemented throughout.

Two warnings surfaced: a robustness gap in `gap.py`'s exception handler that excludes `TypeError` despite claiming "Does not raise" in its module docstring, and an unquoted shell variable in `daily.yml` that is safe in practice but violates shell best practices. Three info items address a misleading cron comment, undifferentiated inline TODO-tracking, and two test boundary coverage gaps.

No security vulnerabilities were found. No hardcoded secrets. No logic errors in the ranking or filtering code paths.

---

## Warnings

### WR-01: `gap.py` — `TypeError` excluded from defensive exception handler

**File:** `src/gap.py:49-55`

**Issue:** The module-level docstring states "Does not raise — a corrupt or missing `captured_at` is silently skipped." The `except` clause on line 55 catches `(KeyError, ValueError, json.JSONDecodeError)` but omits `TypeError`. If `now` is timezone-aware (as it always is — `datetime.now(timezone.utc)` in `main()`) and `captured_at` parses to a timezone-naive datetime (e.g., a snapshot file written without a UTC offset), the subtraction `now - captured_at` raises `TypeError: can't subtract offset-naive and offset-aware datetimes`. This `TypeError` propagates uncaught out of `check_gap`, through `run()`, and crashes the collector process instead of silently continuing as documented.

Normal production flow always writes UTC-aware timestamps, so this is not reachable under current operation. It becomes reachable if a snapshot file is manually edited, written by a legacy version, or if the `store` module ever changes to emit naive timestamps. The risk is latent but the defensive-catch contract is broken.

**Fix:**
```python
# Line 55 — add TypeError to the exception tuple
except (KeyError, ValueError, TypeError, json.JSONDecodeError):
    pass  # don't crash on malformed/mixed-tz snapshot — gap check is best-effort
```

---

### WR-02: `daily.yml` — unquoted `$DELETED` variable in `git rm`

**File:** `.github/workflows/daily.yml:33`

**Issue:** The deletion-staging step uses:
```bash
git rm $DELETED
```
The variable `$DELETED` is unquoted. Under default `IFS`, word-splitting occurs on newlines and spaces. For the expected `YYYY-MM-DD.json` filenames this is harmless, but it is a shell coding defect: if filename conventions ever change to include spaces, or if `git ls-files` output format changes between Git versions, the command would silently mis-split filenames. Unquoted multi-word variable expansion is also flagged by `shellcheck` and common linters.

**Fix:**
```yaml
- name: Stage pruned snapshot deletions
  run: |
    DELETED=$(git ls-files --deleted data/ 2>/dev/null)
    if [ -n "$DELETED" ]; then
      echo "$DELETED" | xargs git rm --
    fi
```
Using `xargs` with `echo "$DELETED" | xargs git rm --` correctly handles newline-separated paths without risk from word splitting. The `--` separator guards against filenames that could be mistaken for flags.

---

## Info

### IN-01: `config.py` — `[ASSUMED]` inline tags belong in a tracking issue, not source

**File:** `src/config.py:119,121`

**Issue:** Two tunable constants carry `[ASSUMED]` inline comments indicating they need calibration after 30 days of data:
```python
GAMING_MIN_STARS: int = 200           # [ASSUMED] — tune after first 30 days of data
GAMING_STAR_FORK_RATIO: float = 50.0  # [ASSUMED] — tune after first 30 days of data
```
Embedding future-work tracking in source comments couples the reminder to the constant's line, but the comment will not produce a test failure or workflow alert. A tracking issue or `ROADMAP.md` entry is the appropriate home for time-gated follow-up work.

**Fix:** Remove the `[ASSUMED]` inline annotations once values have been empirically validated, or create a tracking issue and reference it by number (e.g., `# Tune after 30 days of data — see issue #XX`).

---

### IN-02: `keepalive.yml` — cron comment says "every 10 days" but runs on fixed days-of-month

**File:** `.github/workflows/keepalive.yml:5`

**Issue:** The inline comment reads `# every 10 days, 04:23 UTC`. The expression `*/10` in the day-of-month field means "on the 1st, 11th, 21st, and 31st of each month," not "every 10 calendar days." In months with fewer than 31 days the 31st is skipped; the gap from the 21st to the 1st of the following month can be 8–11 days depending on month length. The workflow still runs well within the 60-day GitHub inactivity threshold, so there is no functional problem — the comment is simply imprecise.

**Fix:**
```yaml
- cron: '23 4 */10 * *'  # on the 1st/11th/21st/31st of each month, 04:23 UTC (HARD-01)
```

---

### IN-03: Test coverage gaps — boundary conditions not exercised

**Files:** `tests/test_gap.py`, `tests/test_prune.py`

**Issue:** Two boundary conditions are untested:

1. **`test_gap.py`** — `test_no_snapshots_returns_silently` passes `tmp_path` (a directory that exists but is empty). There is no test for the "snapshots directory does not exist" case. While empirically `Path.glob()` returns `[]` for missing directories on Python 3.12, this is not in the Python language reference and is not guaranteed across versions. A test would lock in the expected behavior and detect a regression if `glob` behavior changes.

2. **`test_prune.py`** — The test suite checks files 91 days old (deleted) and 1 day old (kept), but not a file exactly 90 days old (at the cutoff boundary). The code uses `snap_date < cutoff` (strict less-than), so a 90-day-old file should be kept. A `test_file_at_exact_retention_boundary_kept` test would explicitly document and enforce this boundary decision.

**Fix (test_gap.py addition):**
```python
def test_nonexistent_snapshots_dir_returns_silently(self):
    """Returns silently when snapshots_dir itself does not exist."""
    from src.gap import check_gap
    now = datetime(2026, 6, 28, 13, 0, 0, tzinfo=timezone.utc)
    check_gap(now, snapshots_dir=Path("/tmp/definitely_does_not_exist_xyzzy"))
```

**Fix (test_prune.py addition):**
```python
def test_file_at_exact_retention_boundary_kept(self, tmp_path: Path):
    """File with stem date exactly retention_days ago is NOT deleted (strict < cutoff)."""
    from src.prune import prune_snapshots
    boundary_file = _snapshot_path(tmp_path, days_ago=90)
    result = prune_snapshots(_now(), snapshots_dir=tmp_path, retention_days=90)
    assert boundary_file not in result, "File at exact boundary must be kept"
    assert boundary_file.exists()
```

---

_Reviewed: 2026-06-28_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
