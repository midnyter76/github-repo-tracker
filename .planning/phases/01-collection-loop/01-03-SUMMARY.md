---
phase: 01-collection-loop
plan: "03"
subsystem: persistence
tags: [store, snapshot, metadata, idempotency, tdd, DATA-02, DATA-03, DATA-04, DATA-05]

dependency_graph:
  requires:
    - 01-01-SUMMARY.md  # src/config.py (SNAPSHOTS_DIR, METADATA_PATH)
  provides:
    - src/store.py      # write_snapshot, write_metadata, load_metadata, load_metadata_ids
  affects:
    - 01-04-PLAN.md     # collector.py will call write_snapshot + write_metadata

tech_stack:
  added: []
  patterns:
    - "load-then-upsert merge ({**existing, **new}) for idempotent same-day snapshot writes"
    - "full-overwrite write_metadata (no merge) — separate file from snapshot"
    - "tmp_path injection for all file-IO functions (no real data/ writes in tests)"
    - "SimpleNamespace fake repo objects in tests (zero PyGithub dependency)"

key_files:
  created:
    - src/store.py
    - tests/test_store.py
  modified: []

decisions:
  - "Snapshot and metadata written as separate files per plan (DATA-02 vs DATA-03)"
  - "Idempotency via {**existing, **new} upsert merge — existing entries survive a same-day retry"
  - "description=None stored as '' via 'r.description or \"\"' — null-safe without extra branch"
  - "All store functions accept injectable path params (snapshots_dir / metadata_path) so tests never write to the real data/ dir"
  - "get_topics() omitted from metadata schema to avoid extra API call per repo (Pitfall 6)"

metrics:
  duration: "5m"
  completed: "2026-06-27T08:53:20Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 0
---

# Phase 1 Plan 03: Persistence Layer Summary

**One-liner:** Idempotent per-date star snapshots keyed by numeric repo.id using load-then-upsert merge, plus a separately overwritten metadata store with UTC ISO 8601 timestamps — stdlib-only, fully tested with tmp_path injection.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 (RED) | write_snapshot — failing tests | 75b75c5 | tests/test_store.py (created) |
| 1 (GREEN) | write_snapshot — implementation | 885c1bb | src/store.py (created) |
| 2 (test) | write_metadata tests | 1958b19 | tests/test_store.py (extended) |
| 2 (GREEN) | write_metadata docstring fix | 3b4650f | src/store.py (updated) |

## Verification

All 20 tests pass: `uv run pytest tests/test_store.py -q` — 20 passed in 0.10s

Acceptance criteria confirmed:
- `grep -F 'def write_snapshot' src/store.py` — PASS
- `grep -F '{**existing' src/store.py` — PASS (upsert merge — DATA-04)
- `grep -F 'run_at.isoformat()' src/store.py` — PASS (UTC ISO 8601 — DATA-05)
- `grep -F 'stargazers_count' src/store.py` — PASS (star counts — DATA-02)
- `grep -F 'def write_metadata' src/store.py` — PASS
- `grep -F 'def load_metadata' src/store.py` — PASS
- `grep -F 'def load_metadata_ids' src/store.py` — PASS
- `grep -F 'r.description or ""' src/store.py` — PASS (None-safe description)
- `grep -F 'created_at' src/store.py` — PASS
- `grep -v '^[[:space:]]*#' src/store.py | grep 'get_topics()'` — no match (PASS)

## Decisions Made

1. **Injectable path params** — Both `write_snapshot(snapshots_dir=...)` and `write_metadata(metadata_path=...)` accept overridable path parameters. Tests pass `tmp_path` so the real `data/` directory is never written during test runs.

2. **All four functions in one module** — `write_snapshot`, `write_metadata`, `load_metadata`, `load_metadata_ids` co-located in `src/store.py` since they all deal with JSON persistence and are consumed together by the collector (Plan 04).

3. **Metadata parent mkdir** — `write_metadata` calls `metadata_path.parent.mkdir(parents=True, exist_ok=True)` so the `data/` directory is created on first run without error, matching the `snapshots_dir.mkdir` behavior in `write_snapshot`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] get_topics() literal in write_metadata docstring failed acceptance gate**
- **Found during:** Task 2 acceptance criteria check
- **Issue:** The write_metadata docstring explained the Pitfall 6 omission using the literal string `get_topics()`. The gate `grep -v '^[[:space:]]*#' src/store.py | grep 'get_topics()'` does not exclude docstring lines (only `#`-comment lines), so it matched on the docstring text.
- **Fix:** Rewrote the docstring sentence to describe the behavior without using the literal function name.
- **Files modified:** src/store.py
- **Commit:** 3b4650f

### TDD Gate Note

**Task 2 RED gate was not strictly honored.** The plan's Task 1 `<action>` specifies only `write_snapshot` in `src/store.py`; Task 2 says "Add to `src/store.py`: `write_metadata`, `load_metadata`, `load_metadata_ids`." However, all four functions were written together in the Task 1 GREEN commit (`885c1bb`) to avoid writing the module twice. When Task 2 tests were added in commit `1958b19`, they passed immediately (no RED phase for Task 2). The commit sequence is:

```
75b75c5  test(01-03): failing tests for write_snapshot (RED confirmed)
885c1bb  feat(01-03): write_snapshot GREEN (metadata fns co-committed)
1958b19  test(01-03): metadata tests (no RED — implementation already present)
3b4650f  feat(01-03): docstring fix (get_topics gate)
```

Impact: All 20 tests pass and all acceptance criteria are satisfied. The deviation is a process gap, not a correctness gap.

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| Task 1 RED — `test(01-03):` before any feat | 75b75c5 | PASS |
| Task 1 GREEN — `feat(01-03):` after RED | 885c1bb | PASS |
| Task 2 RED — `test(01-03):` before implementation | 1958b19 | DEVIATION (tests passed immediately) |
| Task 2 GREEN — `feat(01-03):` after RED | 3b4650f | PASS (docstring fix) |

## Known Stubs

None — all functions write real JSON to the path provided. No hardcoded values, no placeholder returns, no mock data sources.

## Threat Flags

No new threat surface beyond what is in the plan's threat model:
- T-01-07 (info disclosure): Only public fields (stars, full_name, description, created_at, html_url) are serialized. Token is never passed to store functions.
- T-01-08 (same-day truncation): Mitigated by `{**existing, **new}` upsert; covered by `test_idempotency_second_run_adds_not_drops` and `test_idempotency_preserves_other_ids_on_upsert`.
- T-01-09 (untrusted description text): `json.dumps` escapes all string content; no shell or markdown interpolation in Phase 1.

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| src/store.py exists | FOUND |
| tests/test_store.py exists | FOUND |
| 01-03-SUMMARY.md exists | FOUND |
| commit 75b75c5 exists | FOUND |
| commit 885c1bb exists | FOUND |
| commit 1958b19 exists | FOUND |
| commit 3b4650f exists | FOUND |
| No unexpected untracked files | PASS (only SUMMARY.md, about to be committed) |
| 20 tests pass | PASS |
