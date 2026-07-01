---
status: complete
---

# Quick Task 260630-wif: Fix unbounded growth of tracked-repo set — Summary

**Plan:** quick-260630-wif-01
**Tasks:** 2/2 complete

## Commits

- `9b36dd2` — test(260630-wif-01): add failing TestPruneMetadata tests for eviction (RED)
- `7061fbb` — feat(260630-wif-01): add prune_metadata() eviction + config constants (GREEN)
- `3ff421c` — feat(260630-wif-02): wire prune_metadata into collector.run() step 6

## What shipped

- `src/prune.py` — new `prune_metadata()` alongside unmodified `prune_snapshots()`; evicts tracked repos absent from every ranked bucket for `METADATA_TRACKED_RETENTION_DAYS` (14d), using a new self-cleaning `data/tracked_ledger.json` ledger. Reported repos are always refreshed to today and never evicted that run.
- `src/config.py` — added `TRACKED_LEDGER_PATH` and `METADATA_TRACKED_RETENTION_DAYS: int = 14`.
- `src/collector.py` — `run()` now calls `prune_meta_fn(now, reported_ids)` immediately after `prune_fn` at step 6b.
- `tests/test_prune.py` — 11 new `TestPruneMetadata` tests (19 total in file, all green).
- `tests/test_collector.py` — `prune_meta_fn` no-op injected into all 8 existing `run()` calls, plus a new `TestPruneMetaWiring` spy test.

## Verification

- `PYTHONUTF8=1 uv run pytest tests/test_prune.py tests/test_collector.py -q` → 63 passed.
- `PYTHONUTF8=1 uv run pytest -q` → 260 passed, 1 pre-existing unrelated failure (`tests/test_search.py::TestDiscoverRepos::test_monthly_cohort_preserved_when_30d_over_cap`) — pre-existing, out of this plan's `files_modified` scope. See `deferred-items.md`.
- `src/report.py` and `data/snapshots/` untouched, matching plan constraints.

## Deviations

None — plan executed exactly as written.

## Scope honesty (carried from plan)

This bounds tracked-repo growth (roughly halves refresh volume, ~7,258 → ~3,400 repos/run) but does not by itself guarantee runs fit inside GITHUB_TOKEN's 1,000 req/hr core budget. Runs will still hit primary-rate-limit backoff, just recover faster and finish well inside the Actions job timeout instead of requiring multi-hour waits. If runs still approach the timeout after this ships, a follow-up (GraphQL batch star-refresh, or a hard per-run refresh cap) is the next lever — deliberately out of scope for this quick task.
