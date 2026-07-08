---
phase: quick-260707-uec
plan: 01
subsystem: data
tags: [python, pytest, json, persistence, seen-store, metadata, pruning]

# Dependency graph
requires:
  - phase: quick-260630-wif
    provides: metadata.json eviction (prune_metadata) and ledger pattern reused here
provides:
  - Corrupt-file abort guard for load_seen and load_metadata (rename to .corrupt, raise RuntimeError)
  - prune_seen() bounding seen.json growth by first_seen retention window
  - collector.py wiring of prune_seen_fn between report writes and save_seen_fn
affects: [collector, seen-store, metadata-store, prune]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Corrupt-file abort guard: JSONDecodeError -> Path.replace() to <name>.corrupt -> raise RuntimeError from exc (primary load paths only, not eviction passes)"
    - "prune_seen mirrors classify_and_update's pure in-memory, non-mutating contract (caller passes result straight to save_seen_fn), unlike prune_metadata's file-path contract"

key-files:
  created: []
  modified:
    - src/seen.py
    - src/store.py
    - src/prune.py
    - src/collector.py
    - tests/test_seen.py
    - tests/test_store.py
    - tests/test_prune.py
    - tests/test_collector.py

key-decisions:
  - "Corrupt seen.json/metadata.json now aborts the run (RuntimeError) instead of silently returning {} - a crashed Actions run is recoverable, a silently wiped history is not"
  - "prune_metadata's own corrupt-JSON tolerance (warn + treat as empty) is intentionally left unchanged - only its docstring was corrected to stop claiming the old shared convention"
  - "prune_seen reuses SNAPSHOT_RETENTION_DAYS (90d) - no new retention constant introduced"

patterns-established:
  - "Primary load paths (load_seen, load_metadata) abort loudly on corruption; secondary eviction-pass reads (prune_metadata) degrade gracefully by design - these are two different, intentionally divergent behaviors for the same corrupt-JSON condition"

requirements-completed: [DATA-06, HARD-04-SEEN]

duration: 5min
completed: 2026-07-07
---

# Quick Task 260707-uec: Fix seen.json data loss and unbounded growth Summary

**Corrupt-file abort guard (rename-then-raise) for load_seen/load_metadata, plus prune_seen() bounding seen.json by the existing 90-day SNAPSHOT_RETENTION_DAYS window, wired into collector.run() before save_seen_fn.**

## Performance

- **Duration:** ~5 min (task commits at 22:03:41 and 22:05:43, base plan commit at 22:00:56)
- **Tasks:** 2 completed
- **Files modified:** 8 (4 source, 4 test)

## Accomplishments
- `load_seen` (src/seen.py) and `load_metadata` (src/store.py) now rename a corrupt file to `<name>.corrupt` via `Path.replace()` and raise `RuntimeError` instead of warning and returning `{}` — stops a mid-run corruption (disk full, Actions runner crash) from silently erasing months of 🆕/↩ history and star-velocity metadata.
- Added `prune_seen(seen, now, retention_days=SNAPSHOT_RETENTION_DAYS)` to src/prune.py — a pure, non-mutating function dropping seen.json entries whose `first_seen` predates the retention window (mirrors `first_seen >= cutoff` keep-rule, malformed-date warn-and-keep guard).
- Wired `prune_seen_fn` into `src/collector.py` `run()` between `write_html_digest` and `save_seen_fn`, so the persisted seen-store is the pruned dict, not the raw `updated_seen`.
- `prune_metadata`'s own corrupt-JSON handling (warn + treat as empty) is untouched — only its docstring was corrected since it no longer shares a convention with the primary load paths.

## Task Commits

1. **Task 1: Corrupt-file abort guard for load_seen and load_metadata** - `48aa00b` (fix)
2. **Task 2: seen.json pruning by first_seen retention window + collector wiring** - `3a22dc9` (feat)

_Both tasks were TDD (test+implementation in the same commit per task, following the plan's task-level grouping rather than separate RED/GREEN commits — plan frontmatter specified `type: execute`, not a plan-level `type: tdd` gate)._

## Files Created/Modified
- `src/seen.py` - `load_seen` renames corrupt file to `.corrupt` and raises `RuntimeError`; dropped now-unused `import warnings`
- `src/store.py` - `load_metadata` renames corrupt file to `.corrupt` and raises `RuntimeError`; kept `import warnings` (still used by `write_snapshot`'s separate same-day-merge handling)
- `src/prune.py` - added `prune_seen()`; corrected `prune_metadata` docstring (no code change to its corrupt-handling)
- `src/collector.py` - added `prune_seen_fn=prune.prune_seen` injectable kwarg + Args docstring line; wired `pruned_seen = prune_seen_fn(updated_seen, now)` between `write_html_digest` and `save_seen_fn`
- `tests/test_seen.py` - replaced `test_corrupt_json_warns_and_returns_empty` with `test_corrupt_json_renamed_and_raises`; dropped unused `import warnings`
- `tests/test_store.py` - added `import pytest`; added `TestLoadMetadata.test_corrupt_json_renamed_and_raises`
- `tests/test_prune.py` - added `TestPruneSeen` (recent/stale/boundary-kept/boundary-pruned/missing/malformed/non-mutation cases)
- `tests/test_collector.py` - added `TestPruneSeenWiring` (ordering after report writes and before save_seen_fn; save_seen_fn receives the pruned result, not `updated_seen`)

## Decisions Made
- Used `Path.replace()` (not `.rename()`) for the corrupt-file move — `.replace()` overwrites cross-platform including Windows, so a second consecutive corruption doesn't crash the rename step itself (accepted as a low-probability edge case in the plan's threat model, T-uec-03: `accept`).
- Ran the full test suite via `uv run pytest` rather than bare `python -m pytest` — the worktree's system Python lacks the `PyGithub` dependency; `uv run` builds/uses the project's `.venv` (gitignored) against this worktree's own modified `src/` and `tests/`, confirmed by fresh `.venv` creation output in the run log.

## Deviations from Plan

None - plan executed exactly as written. The only adjustment was tooling (uv run vs bare python), not code scope, per the orchestrator's explicit instruction to verify against the worktree's actual environment.

## Issues Encountered

`cd /c/dev/github-repo-tracker && python -m pytest ...` (the plan's literal `<verify>` command) fails with `ModuleNotFoundError: No module named 'github'` in this worktree because there is no `.venv` and PyGithub isn't on the system Python path. Switched to `uv run pytest` from the worktree root, which resolves dependencies via `pyproject.toml`/`uv.lock` and imports the worktree's own modified files. Full suite: **309 passed** with `uv run pytest -q`.

## Accepted Ceilings (per plan `<output>` spec)

1. **prune_seen keys off `first_seen`, not a last-active ledger.** A repo reported continuously past the 90-day retention window flips back to "new" (🆕) once its seen.json entry ages out, because there is no companion ledger tracking last-reported date the way `prune_metadata`'s `TRACKED_LEDGER_PATH` does for metadata.json. This is a `# ponytail:` -marked, deliberate simplification in `src/prune.py`; upgrade to a last-active ledger only if the 🆕-flip-back behavior on long-lived repos ever becomes a real problem.
2. **A corrupt-file abort is a loud, manual-recovery failure by design.** After `load_seen`/`load_metadata` raises, `seen.json`/`metadata.json` has already been moved to `<name>.corrupt` and the run fails (Actions run goes red). Recovery is manual: inspect the `.corrupt` file, decide whether to restore it or let the next successful run rebuild fresh. This is intentional — a loud failure is recoverable; the old silent-wipe behavior was not.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Both data-integrity fixes are self-contained within the seen-store/metadata persistence layer and collector wiring; no other in-flight plan depends on the old warn-and-return-`{}` behavior (confirmed via grep of all `load_metadata`/`load_seen` call sites: `src/store.py load_metadata_ids`, `src/rank.py compute_buckets`, `src/collector.py run()` — all now propagate `RuntimeError` on corruption as intended). No blockers for future phases.

## Self-Check

- `src/seen.py`: FOUND (modified, load_seen updated)
- `src/store.py`: FOUND (modified, load_metadata updated)
- `src/prune.py`: FOUND (modified, prune_seen added)
- `src/collector.py`: FOUND (modified, prune_seen_fn wired)
- `tests/test_seen.py`: FOUND (modified)
- `tests/test_store.py`: FOUND (modified)
- `tests/test_prune.py`: FOUND (modified)
- `tests/test_collector.py`: FOUND (modified)
- Commit `48aa00b`: FOUND in `git log --oneline`
- Commit `3a22dc9`: FOUND in `git log --oneline`
- Full suite: 309 passed, 0 failed (`uv run pytest -q`)

## Self-Check: PASSED

---
*Phase: quick-260707-uec*
*Completed: 2026-07-07*
