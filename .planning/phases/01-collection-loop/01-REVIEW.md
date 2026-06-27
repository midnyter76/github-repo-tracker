---
phase: 01-collection-loop
reviewed: 2026-06-27T21:35:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - src/config.py
  - src/search.py
  - src/store.py
  - src/collector.py
  - .github/workflows/daily.yml
  - tests/test_config.py
  - tests/test_search.py
  - tests/test_store.py
  - tests/test_collector.py
findings:
  critical: 1
  warning: 8
  info: 2
  total: 11
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-06-27T21:35:00Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Reviewed the full Phase 01 collection-loop implementation: configuration constants, GitHub search/discovery layer, persistence layer, orchestrator, GitHub Actions workflow, and the complete test suite. The core architecture is sound — dedup by numeric `repo.id`, injectable dependencies, rate-limit pre-check, idempotent snapshot merge, and full-overwrite metadata store are all implemented correctly.

Three clusters of defects emerged:

1. **Cap-handling logic in `search.py`** has three related bugs: a no-op narrowing when the tightest window is the current window, silent data loss for the middle date range when the 30-day query is over cap, and absent cap-checks on re-issued queries (narrow pass and sub-band split).
2. **Unhandled `JSONDecodeError`** in `store.py` can permanently brick the pipeline if a snapshot or metadata file is corrupted by an interrupted write.
3. **Supply-chain security**: Actions are pinned to mutable version tags, not SHA hashes, violating the project's own CLAUDE.md security requirement.

One test is a guaranteed pass that asserts nothing, creating false assurance around a T-01-04 security property.

---

## Critical Issues

### CR-01: Unhandled `JSONDecodeError` on Corrupted Snapshot File Permanently Breaks All Future Runs

**File:** `src/store.py:53`

**Issue:** `write_snapshot` reads an existing snapshot before merging with `json.loads(snap_path.read_text()).get("repos", {})`. If the file on disk is malformed JSON — a realistic scenario when an earlier run was interrupted mid-write by a signal, OOM, or Actions job timeout — `json.loads` raises `json.JSONDecodeError` which is unhandled. The entire run crashes, the corrupt file is never repaired, and every subsequent run crashes at the same line. The `data/` directory is also committed back to the repo via `git-auto-commit-action`, so the corrupt file persists across restarts.

**Fix:**
```python
existing = {}
if snap_path.exists():
    try:
        existing = json.loads(snap_path.read_text()).get("repos", {})
    except json.JSONDecodeError:
        warnings.warn(
            f"Corrupt snapshot at {snap_path}; starting fresh for this date.",
            stacklevel=2,
        )
        existing = {}
```

---

## Warnings

### WR-01: `discover_repos` Re-Issues Identical Query When Current Window Is the Tightest Window

**File:** `src/search.py:195-212`

**Issue:** `tightest_window = min(windows)`. With the default `NEW_REPO_WINDOWS = [7, 30]`, iteration processes `window=7` first. If that query is over cap, `tight_since = since_date_for(tightest_window)` computes the same date as `since`, producing an **identical query**. The second `search()` call returns the same over-cap result, wastes one search API credit (2 of 30/min budget), and emits a warning claiming it "narrowed to 7d window" when it performed no narrowing. There is no tighter window available, so the re-issue is always pointless when `window == tightest_window`.

**Fix:** Skip the re-issue when the current window is already the tightest:
```python
if over_cap(results):
    if window == tightest_window:
        warnings.warn(
            f"topic query for '{topic}' totalCount={results.totalCount} "
            f">= {TOTAL_COUNT_CAP_WARN}; already at tightest window ({tightest_window}d), "
            "consider adding a star-floor or per-star-band slice",
            stacklevel=2,
        )
    else:
        warnings.warn(...)
        tight_since = since_date_for(tightest_window)
        results = search(g, build_topic_query(topic, since_date=tight_since))
```

---

### WR-02: Narrowing Drops All Repos from the Middle Date Range

**File:** `src/search.py:205-212` (topic path) and `src/search.py:219-226` (keyword path)

**Issue:** When the 30-day topic or keyword query is over cap, the code replaces `results` with the 7-day window result. Every repo created 8–30 days ago is silently discarded for that topic/keyword combination. The 30-day bucket exists explicitly to surface "monthly" discoveries (per the `NEW_REPO_WINDOWS` comment: `30 = monthly (Brand New Top 5)`). The narrowing defeats that purpose at the moment activity is highest — exactly when over-cap conditions arise. There is no secondary query that captures the 8–30 day range.

**Fix (short-term):** Add a targeted warning that names the lost date range:
```python
warnings.warn(
    f"topic query for '{topic}' totalCount={results.totalCount} "
    f">= {TOTAL_COUNT_CAP_WARN}; narrowing to {tightest_window}d window — "
    f"repos created {tightest_window+1}–{window}d ago will be missed for this topic",
    stacklevel=2,
)
```

**Fix (structural):** Replace the monolithic window queries with per-star-band slices (same technique used in `discover_established`) to keep each slice under 1,000 results without dropping any date range.

---

### WR-03: No Cap Check on Re-Issued Narrow Query in `discover_repos`

**File:** `src/search.py:210-212` (topic) and `src/search.py:224-226` (keyword)

**Issue:** After re-issuing with the tighter window, `over_cap` is never called on the new `results`. If the 7-day window for a very active topic also returns ≥900 results, the data is silently truncated at GitHub's hard 1,000-result cap with no warning emitted and no further action taken.

**Fix:**
```python
results = search(g, build_topic_query(topic, since_date=tight_since))
if over_cap(results):
    warnings.warn(
        f"topic query for '{topic}' STILL over cap after narrowing to "
        f"{tightest_window}d window (totalCount={results.totalCount}); "
        "results will be truncated",
        stacklevel=2,
    )
```
Apply the same pattern to the keyword path.

---

### WR-04: No Cap Check on Sub-Band Queries in `discover_established`

**File:** `src/search.py:268-271`

**Issue:** After splitting an over-cap band into two sub-bands and re-querying, `over_cap` is never called on the sub-band results. If a sub-band (e.g., "100..550") also returns ≥900 results, the results are silently truncated at GitHub's 1,000-result cap without any warning.

**Fix:**
```python
for sub_band in split_star_band(band):
    sub_results = search(g, build_established_query(topic, sub_band))
    if over_cap(sub_results):
        warnings.warn(
            f"sub-band query topic='{topic}' band='{sub_band}' "
            f"totalCount={sub_results.totalCount} >= {TOTAL_COUNT_CAP_WARN}; "
            "results will be truncated — consider further splitting",
            stacklevel=2,
        )
    for repo in sub_results:
        found[str(repo.id)] = repo
```

---

### WR-05: GitHub Actions Not Pinned to SHA — Supply-Chain Risk with `contents: write`

**File:** `.github/workflows/daily.yml:16,19,30`

**Issue:** All three actions use mutable version tags, not immutable SHA hashes:
```yaml
uses: actions/checkout@v4
uses: astral-sh/setup-uv@v8
uses: stefanzweifel/git-auto-commit-action@v5
```
CLAUDE.md explicitly documents: "pin to SHA for supply-chain safety in production" for `setup-uv`. With `permissions: contents: write` granted at the job level and `GITHUB_TOKEN` in scope, a tag redirect on any of these three actions could silently execute arbitrary code that exfiltrates the token or corrupts committed data. `git-auto-commit-action` in particular has write access to the repository.

**Fix:**
```yaml
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
- uses: astral-sh/setup-uv@6b9c6063abd725038ca8b9b8613c07fea48b3f7d  # v8.2.0
- uses: stefanzweifel/git-auto-commit-action@8621497c8c39c72f3e2a999a26b4ca1b5590a6cf  # v5.0.1
```
Pin each action to a verified SHA. Update SHAs when upgrading action versions intentionally.

---

### WR-06: `refresh_tracked` Raises Unhandled `ValueError` on Non-Integer Metadata Key

**File:** `src/search.py:306`

**Issue:**
```python
repo = g.get_repo(int(rid))
```
Only `github.UnknownObjectException` is caught. If any metadata key is not a valid decimal integer string (malformed metadata file, manual edit, future schema change), `int(rid)` raises `ValueError` which propagates uncaught and crashes the entire run. In failure modes, a single invalid key aborts the refresh of all subsequent tracked repos.

**Fix:**
```python
try:
    repo = g.get_repo(int(rid))
    refreshed[str(repo.id)] = repo
except ValueError:
    warnings.warn(f"Repo id {rid!r} is not a valid integer; skipping")
    continue
except github.UnknownObjectException:
    warnings.warn(f"Repo id {rid} unavailable (deleted or private); skipping")
    continue
```

---

### WR-07: `load_metadata` Raises Unhandled `JSONDecodeError` on Corrupt Metadata File

**File:** `src/store.py:129`

**Issue:**
```python
return json.loads(metadata_path.read_text())
```
No exception handling on JSON parsing. A corrupt `data/metadata.json` (e.g., from an interrupted write) raises `json.JSONDecodeError`, crashing the run before discovery begins. Unlike the snapshot case, a corrupt metadata file blocks the refresh step entirely since `load_metadata_ids` calls `load_metadata`.

**Fix:**
```python
try:
    return json.loads(metadata_path.read_text())
except json.JSONDecodeError:
    warnings.warn(
        f"Corrupt metadata at {metadata_path}; treating as empty.",
        stacklevel=2,
    )
    return {}
```

---

### WR-08: `test_exception_handler_only_references_rid` Asserts Nothing — Hollow T-01-04 Gate

**File:** `tests/test_search.py:535-552`

**Issue:** The test claims to guard the T-01-04 security property (exception handler must not log the client `g` or exception repr). The loop body under the `if re.search(...)` block computes `exc_var` and then hits `pass` — no `assert`, no `pytest.fail`. Furthermore, `refresh_tracked` uses `except github.UnknownObjectException:` with **no `as` clause**, so the regex `except.*Exception\s+as\s+(\w+)` never matches and the conditional body is never entered. The test is a guaranteed pass that performs zero verification. The comment "covered by grep gate at commit time" references an external gate not present in the repository, making this test the only automated safeguard that turns out to be absent.

**Fix:** Replace with a static-analysis assertion over the actual source:
```python
def test_exception_handler_only_references_rid(self):
    import inspect, re
    import src.search as search_module

    source = inspect.getsource(search_module.refresh_tracked)
    # Exception block must not reference the exception variable or g
    # (The except clause must NOT use "as <var>"; if it does, that var must
    #  not appear in any format string, repr(), or str() call)
    if "except" in source and "as e" in source:
        # Check that 'e' doesn't appear in warnings.warn or format strings
        assert not re.search(r'warn.*\be\b|f".*\be\b|str\(e\)|repr\(e\)', source), \
            "Exception variable 'e' must not be logged (T-01-04)"
    # Also verify the token / auth variable 'g' is not present in the except block
    except_block = source[source.find("except"):]
    assert "warnings.warn" not in except_block or "g" not in except_block.split("warnings.warn")[1].split("\n")[0], \
        "Client 'g' must not appear in warn message (T-01-04)"
```

---

## Info

### IN-01: `SNAPSHOTS_DIR` and `METADATA_PATH` Are Relative to CWD

**File:** `src/config.py:78-81`

**Issue:** Both paths are bare relative paths (`Path("data/snapshots")`, `Path("data/metadata.json")`). If the script is invoked from any directory other than the project root — e.g., `cd src && python -m collector` or an IDE run configuration with a different CWD — files are written to unexpected locations without any error. The GitHub Actions workflow always runs from the checkout root, so this works correctly in CI; local development is fragile.

**Fix (lightweight):** Document the CWD dependency in a module docstring or raise an explicit error if the expected `data/` ancestor is not present. A more robust fix anchors paths to the project root using `Path(__file__)`:
```python
# In config.py
_PROJECT_ROOT = Path(__file__).parent.parent
SNAPSHOTS_DIR = _PROJECT_ROOT / "data" / "snapshots"
METADATA_PATH = _PROJECT_ROOT / "data" / "metadata.json"
```

---

### IN-02: One-Shot Iterator in `_make_result` Test Helper Can Mask Coverage Gaps

**File:** `tests/test_search.py:37`

**Issue:**
```python
result.__iter__ = MagicMock(return_value=iter(repos))
```
`iter(repos)` creates a single-use iterator. If any code path under test iterates the mock result twice — e.g., due to a future refactor that re-scans results — the second iteration silently yields nothing. The test will pass while the production behavior is broken.

**Fix:** Use a repeatable approach instead:
```python
result.__iter__ = MagicMock(side_effect=lambda: iter(repos))
```

---

_Reviewed: 2026-06-27T21:35:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
