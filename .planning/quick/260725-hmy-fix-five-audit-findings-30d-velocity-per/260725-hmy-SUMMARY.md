---
phase: quick-260725-hmy
plan: 01
subsystem: velocity-ranking, persistence, ci
tags: [rank, store, collector, github-actions, pytest]

# Dependency graph
requires: []
provides:
  - velocity_30d joins each repo against the oldest in-window snapshot containing it (not the globally-oldest snapshot)
  - write_metadata merges instead of full-overwriting, so tracked repos survive the residual refresh cap
  - collector persists the full candidate set (gamed/junk repos included) and gates only the digest via exclude_ids
  - per-repo captured_at on snapshot entries, with file-level fallback for legacy files
  - CI workflow running pytest on push/PR; shared concurrency group + timeout on the two writer workflows
affects: [rank, store, collector, ci]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-rid oldest-containing-snapshot join (rolling 30d velocity) instead of a fixed (oldest, newest) tuple"
    - "Digest-selection filtering via exclude_ids keyword, decoupled from persistence"
    - "Per-entry timestamp with file-level fallback for backward-compatible schema evolution"

key-files:
  created:
    - .github/workflows/ci.yml
  modified:
    - src/rank.py
    - src/store.py
    - src/collector.py
    - src/config.py
    - tests/test_rank.py
    - tests/test_store.py
    - tests/test_collector.py
    - .github/workflows/daily.yml
    - .github/workflows/keepalive.yml

key-decisions:
  - "select_30d_window now returns the full in-window snapshot list (not a 2-tuple); compute_buckets does the per-repo oldest-containing join with next((s for s in in_window[:-1] if rid in s['repos']), None)"
  - "write_metadata merges via load_metadata (reusing its corrupt-file abort semantics) instead of re-implementing JSON read/write"
  - "collector.run() computes exclude_ids = set(candidates) - set(kept) and passes the FULL candidate set to write_snap/write_meta; filters no longer rebind candidates"
  - "entry_captured_at(snap, rid) centralizes the per-repo-with-file-level-fallback read, used by spike_velocity, rolling_velocity, and the creation_velocity call site"
  - "ci.yml has no concurrency group (read-only, no repo writes); daily.yml and keepalive.yml share group: repo-writes"

requirements-completed: [AUDIT-30D-JOIN, AUDIT-META-AMNESIA, AUDIT-FILTER-ORDER, AUDIT-SNAP-TS, AUDIT-CI]

# Metrics
duration: 55min
completed: 2026-07-25
---

# Quick Task 260725-hmy: Fix Five Audit Findings Summary

**Fixed five joint Claude+Codex audit findings as five atomic commits: the 30d velocity bucket now joins each repo against the oldest snapshot that actually contains it instead of the globally-oldest one, metadata.json merges instead of full-overwriting, gamed/junk repos keep accumulating history while still being excluded from the digest, snapshot entries carry their own capture timestamp to survive same-day retries, and a CI workflow plus a shared concurrency group now guard the two writer workflows.**

## Performance

- **Duration:** ~55 min
- **Started:** 2026-07-25T19:07:00Z (approx, based on session start)
- **Completed:** 2026-07-25T20:02:38Z
- **Tasks:** 5/5
- **Files modified:** 9 (matches plan's files_modified) + src/config.py (one-line comment fix, in scope of Task 2)

## Accomplishments
- velocity_30d no longer structurally blind to repos absent from the globally-oldest snapshot — it now joins per-repo against the oldest snapshot that actually contains that repo
- metadata.json stops silently amnesiac-ing tracked repos cut by the residual refresh cap; eviction is now solely owned by prune_metadata's ledger
- Gamed/junk repos are persisted (retaining velocity history) but still never reach any ranked bucket or the digest
- Same-day collector retries no longer corrupt the elapsed-hours denominator for carried-forward repos
- New ci.yml runs the full pytest suite on every push and PR; daily.yml + keepalive.yml share a concurrency group so they can't race on `main`, and daily.yml's collect job is time-bounded

## Task Commits

1. **Task 1: Per-repo oldest-containing snapshot for the 30d velocity join** - `c2759a3` (fix)
2. **Task 2: write_metadata merges instead of full-overwrite** - `6d77ba0` (fix)
3. **Task 3: Snapshot the full candidate set; filter at digest-selection time** - `ce91e23` (fix)
4. **Task 4: Per-repo captured_at so same-day retries stop corrupting elapsed hours** - `9a7ad4e` (fix)
5. **Task 5: CI workflow, shared concurrency group, daily job timeout** - `0e7fd2a` (ci)

_No TDD RED-only or REFACTOR-only commits were needed — each task's test additions and implementation landed together in one commit per the plan's single-commit-per-finding structure._

## Files Created/Modified
- `src/rank.py` - select_30d_window returns full in-window list; compute_buckets per-repo oldest-containing join; exclude_ids param; entry_captured_at reader with file-level fallback
- `src/store.py` - write_metadata merges via load_metadata; write_snapshot stamps per-repo captured_at
- `src/collector.py` - filters compute exclude_ids instead of rebinding candidates; full candidate set reaches write_snap/write_meta
- `src/config.py` - corrected stale comment above REFRESH_RESIDUAL_CAP (no longer claims full-overwrite drops repos from metadata)
- `tests/test_rank.py` - updated TestSelect30dWindow for list return type; added TestVelocity30dOldestContainingSnapshot, TestComputeBucketsExcludeIds, TestEntryCapturedAt, TestVelocityUsesPerRepoCapturedAt
- `tests/test_store.py` - updated DATA-03 test to assert merge (not overwrite); added fresh-fields-win, absent-file, corrupt-file-abort, and retry-carry-forward tests
- `tests/test_collector.py` - added TestFilterRetainsHistory (3 tests), TestCiYaml (9 tests), concurrency-group assertions on TestWorkflowYaml/TestKeepaliveYaml, TestSharedConcurrencyGroup; updated TestRunPhase3CallOrder docstring/comment per plan-checker note
- `.github/workflows/ci.yml` - new: pytest on push/PR, contents: read, SHA-pinned actions, timeout-minutes: 10
- `.github/workflows/daily.yml` - added concurrency: group: repo-writes; collect job timeout-minutes: 60
- `.github/workflows/keepalive.yml` - added concurrency: group: repo-writes

## Decisions Made
- Reused `load_metadata` inside `write_metadata` for the merge read, rather than re-implementing JSON parsing — preserves the existing corrupt-file-abort security property without duplicating logic (per plan instruction and Rule 1/2 discipline).
- Kept `rolling_velocity`/`spike_velocity` as pure two-snapshot primitives; all per-repo timestamp logic is centralized in the new `entry_captured_at` helper rather than duplicated across callers.
- No new config knobs, modules, or abstractions were introduced anywhere in the five tasks — every fix is a same-file, minimum-diff change plus tests.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] No .venv existed in this worktree**
- **Found during:** pre-Task-1 baseline verification
- **Issue:** The worktree checkout at `.claude/worktrees/agent-a30b104810185c61a` had no `.venv/`, so the plan's verify command (`PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest`) would fail immediately.
- **Fix:** Ran `uv sync` in the worktree to create a local `.venv` matching `uv.lock` (18 packages, including pygithub, pytest). This is a local dev-environment artifact (gitignored), not a source change.
- **Files modified:** none (`.venv/` is gitignored)
- **Verification:** `PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q` → 310 passed (baseline), matching the plan's stated baseline.

**2. [Plan-checker note] Stale comments in TestRunPhase3CallOrder describing pre-fix design intent**
- **Found during:** Task 3
- **Issue:** The class docstring and an inline comment in `tests/test_collector.py::TestRunPhase3CallOrder` described filter_gamed/filter_junk as gating persistence ("BEFORE write_snap (Pitfall 5)"), which Finding 3 deliberately reverses. Assertions still passed mechanically but the prose was now backwards.
- **Fix:** Reworded both the class docstring and the inline comment to state that filter_gamed/filter_junk now compute `exclude_ids` for `compute_buckets` only, and no longer gate persistence — matching the plan-checker's explicit instruction.
- **Files modified:** `tests/test_collector.py`
- **Commit:** `ce91e23` (part of Task 3)

No other deviations. All five tasks were implemented exactly as specified in the plan's `<action>` blocks; no architectural changes (Rule 4) were needed.

## Known Stubs

None — this plan touches only ranking/persistence/CI logic, no UI or rendering paths (src/report.py was explicitly untouched, verified via `git diff --name-only` against the base commit).

## Threat Flags

None — all five tasks map directly to `mitigate` dispositions already documented in the plan's `<threat_model>` (T-hmy-01 through T-hmy-05); no new trust-boundary-crossing surface was introduced beyond what the threat register anticipated. T-hmy-06 (accept) required no code change.

## Self-Check: PASSED

- FOUND: src/rank.py (select_30d_window, entry_captured_at, exclude_ids present)
- FOUND: src/store.py (write_metadata merge, write_snapshot per-repo captured_at present)
- FOUND: src/collector.py (exclude_ids wiring present)
- FOUND: src/config.py (updated comment present)
- FOUND: .github/workflows/ci.yml
- FOUND: .github/workflows/daily.yml (concurrency + timeout present)
- FOUND: .github/workflows/keepalive.yml (concurrency present)
- FOUND commit c2759a3, 6d77ba0, ce91e23, 9a7ad4e, 0e7fd2a in `git log --oneline --all`
- Full suite: 339 passed (baseline 310 + 29 new tests across five tasks)
- `git diff --name-only 7e65a8a6..HEAD -- src/report.py` returns nothing (untouched, as required)
- `git status --porcelain data/` is clean (no data migration/rewrite)
