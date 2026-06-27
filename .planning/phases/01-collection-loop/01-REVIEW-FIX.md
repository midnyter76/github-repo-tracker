---
phase: 01-collection-loop
fixed_at: 2026-06-27T21:55:00Z
review_path: .planning/phases/01-collection-loop/01-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 01: Code Review Fix Report

**Fixed at:** 2026-06-27T21:55:00Z
**Source review:** .planning/phases/01-collection-loop/01-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 9 (1 Critical + 8 Warning; Info findings skipped per scope)
- Fixed: 9
- Skipped: 0

Final test count: **96 passed, 0 failed**

---

## Fixed Issues

### CR-01: Unhandled JSONDecodeError on Corrupted Snapshot File

**Files modified:** `src/store.py`
**Commit:** `3741a15`
**Applied fix:** Added `import warnings`. In `write_snapshot`, wrapped
`json.loads(snap_path.read_text())` in `try/except json.JSONDecodeError` —
on decode error, warns and treats the date as fresh (`existing = {}`). Also
fixes WR-07 in the same commit.

---

### WR-01: No-Op Re-Issue at Tightest Window

**Files modified:** `src/search.py`
**Commit:** `a9000d9`
**Applied fix:** Restructured the over-cap branch in `discover_repos` for both
the topic and keyword paths. When `window == tightest_window`, emits a targeted
"already at tightest window — consider per-star-band slice" warning and keeps
the (possibly truncated) results, with no extra search query issued. This
eliminates the wasted API credit and the misleading "narrowing" message.

---

### WR-02: Narrowing Drops All Repos from the Middle Date Range

**Files modified:** `src/search.py`
**Commit:** `a9000d9`
**Applied fix:** Implemented Option B (structural fix): when `window !=
tightest_window` and over-cap, a **complementary date-range query** is issued
using `created:{since_wide}..{since_tight}` to give the 8–30 day cohort its
own 1000-result budget. `build_topic_query` and `build_keyword_query` gained
an optional `until_date` parameter (default `None`) that produces this closed
range form. The wide window's over-cap results are not iterated — only the
complementary middle-band results are merged, which together with the already-
collected tightest-window results give complete coverage with no truncation
overlap.

New test `test_monthly_cohort_preserved_when_30d_over_cap` proves that repo_id
1 (in the 8–30d band) is present when the 30d query is over-cap.

---

### WR-03: No Cap Check on Re-Issued Narrow Query in discover_repos

**Files modified:** `src/search.py`
**Commit:** `a9000d9`
**Applied fix:** After issuing the complementary middle-band query (WR-02 path),
an `over_cap` check is now applied to `mid_results`. If still over-cap, warns
"STILL over cap … consider per-star-band slicing". Applied symmetrically to
both the topic and keyword paths.

---

### WR-04: No Cap Check on Sub-Band Queries in discover_established

**Files modified:** `src/search.py`
**Commit:** `a9000d9`
**Applied fix:** After each sub-band `search()` call inside `discover_established`,
an `over_cap` check is applied. If the sub-band result is still over-cap, warns
"results will be truncated — consider further splitting". The iteration and
merge logic is unchanged.

---

### WR-05: GitHub Actions Not Pinned to SHA

**Files modified:** `.github/workflows/daily.yml`
**Commit:** `e92462f`
**Applied fix:** All three actions replaced with verified commit SHAs resolved
via `gh api repos/{owner}/{repo}/git/ref/tags/{tag}`. The reviewer's suggested
SHAs for setup-uv and git-auto-commit-action were WRONG (differed from actual
tag targets) — the SHAs used here were independently verified:

| Action | SHA (verified) | Version |
|--------|---------------|---------|
| `actions/checkout` | `11bd71901bbe5b1630ceea73d27597364c9af683` | v4.2.2 |
| `astral-sh/setup-uv` | `fac544c07dec837d0ccb6301d7b5580bf5edae39` | v8.2.0 |
| `stefanzweifel/git-auto-commit-action` | `8621497c8c39c72f3e2a999a26b4ca1b5058a842` | v5.0.1 |

`test_auto_commit_action_version` in `test_collector.py` was updated to accept
the SHA-pinned form (with `# v5` comment) in addition to the `@v5` tag form.

---

### WR-06: refresh_tracked Raises Unhandled ValueError on Non-Integer Key

**Files modified:** `src/search.py`
**Commit:** `a9000d9`
**Applied fix:** Added `except ValueError` before `except github.UnknownObjectException`
in `refresh_tracked`. On ValueError, warns `"Repo id {rid!r} is not a valid
integer; skipping"` and continues to the next key. One malformed metadata key
no longer aborts the entire refresh pass.

New test `test_skips_malformed_metadata_key_with_warning` verifies that `"abc"`
is skipped with a warning and `"111"` is still refreshed.

---

### WR-07: load_metadata Raises Unhandled JSONDecodeError

**Files modified:** `src/store.py`
**Commit:** `3741a15`
**Applied fix:** Wrapped `json.loads(metadata_path.read_text())` in `load_metadata`
with `try/except json.JSONDecodeError`. On decode error, warns "Corrupt metadata
at …; treating as empty." and returns `{}`. This means a corrupt metadata.json
does not block the discovery step.

---

### WR-08: test_exception_handler_only_references_rid Asserts Nothing

**Files modified:** `tests/test_search.py`
**Commit:** `9358570`
**Applied fix:** Replaced the hollow test (loop body hit `pass`, no assertions)
with two real static-analysis checks against the `refresh_tracked` source:
1. Any captured exception variable (from `except X as var`) must not appear in
   any `warnings.warn()` call.
2. The GitHub client variable `g` must not appear in any `warnings.warn()` call
   inside the function.
Both properties currently hold and will fail if a future change introduces
leakage. The test is now a genuine T-01-04 gate.

---

## Skipped Issues

None.

---

_Fixed: 2026-06-27T21:55:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
