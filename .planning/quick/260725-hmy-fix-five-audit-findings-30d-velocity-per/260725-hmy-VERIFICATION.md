---
phase: quick-260725-hmy
verified: 2026-07-25T00:00:00Z
status: passed
score: 11/11 must-haves verified
overrides_applied: 0
---

# Quick Task 260725-hmy: Fix Five Audit Findings Verification Report

**Task Goal:** fix five audit findings: 30d velocity per-repo join, metadata retention, filter ordering, snapshot captured_at, CI workflow
**Verified:** 2026-07-25
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A repo present in today's snapshot and ANY older in-window snapshot is eligible for velocity_30d, even if absent from the globally-oldest snapshot | VERIFIED | `src/rank.py:370-374` — `snap_oldest = next((s for s in in_window[:-1] if rid in s["repos"]), None)`. Empirically confirmed against real data (see Finding 1 below): eligible repos rose from 450 (old global-oldest join) to 1981 (new per-repo join), pre-cap. |
| 2 | A repo present only in the newest snapshot still produces no velocity_30d entry | VERIFIED | `src/rank.py:373-374` — `if snap_oldest is None: continue`. Confirmed 84 of 2211 real repos hit this path (`no_history=84` in empirical run). |
| 3 | velocity_30d keeps its >=2-in-window gate, negative-delta exclusion, entry shape, sort order, VELOCITY_30D_TOP cap | VERIFIED | `src/rank.py:204-206` (gate), `380-382` (negative-delta), `384-386` (`_build_entry`), `387` (`_sort_entries` + `[:config.VELOCITY_30D_TOP]`). Empirical run: cap of 10 applied correctly (1981 eligible -> 10 returned). |
| 4 | write_metadata preserves entries for tracked repos absent from this run's candidates; eviction only via prune_metadata's ledger | VERIFIED | `src/store.py:127,139` — `existing = load_metadata(...).get("repos", {})`; `"repos": {**existing, **new_entries}`. Docstring updated; `src/config.py:170-172` comment corrected to match. |
| 5 | Repos dropped by filter_gamed/filter_junk still receive a snapshot row and metadata entry | VERIFIED | `src/collector.py:156-161` — `write_snap(candidates, now)` / `write_meta(candidates, now)` use the FULL `candidates` dict, not the filtered `kept` set. |
| 6 | Filtered repos never appear in any ranked bucket; filtering stays silent | VERIFIED | `src/collector.py:157` — `exclude_ids = set(candidates) - set(kept)`, passed to `compute_buckets(..., exclude_ids=exclude_ids)` at line 164. `src/rank.py` applies `if rid in exclude_ids: continue` in all three ranking loops (lines 301-302, 335-336, 364-365). No print/stdout in the filter path. |
| 7 | Same-day retry: carried-forward repo keeps ORIGINAL captured_at; file-level captured_at advances | VERIFIED | `src/store.py:71-77` — upsert `{**existing, **{new-stamped}}`; only ids present in this call's `repos` get restamped, existing carried-forward entries keep their original per-repo `captured_at` untouched. Covered by `tests/test_store.py` retry-carry-forward test (in full suite, passing). |
| 8 | The 26 existing legacy snapshot files (no per-repo captured_at) still rank correctly via file-level fallback | VERIFIED | Empirically confirmed: all 26 real files on disk have zero per-repo `captured_at` keys; `compute_buckets` ran against them with no exception, `velocity_30d.active=True`; `entry_captured_at` on a real legacy entry resolved to the file-level `captured_at` exactly. |
| 9 | Pushes and PRs run the pytest suite in CI | VERIFIED | `.github/workflows/ci.yml` — `on: [push, pull_request]`, step `run: uv run pytest -q`. Valid YAML (parsed with PyYAML). |
| 10 | daily.yml and keepalive.yml cannot run concurrently (shared group); daily has timeout-minutes | VERIFIED | Both files contain `concurrency: {group: repo-writes, cancel-in-progress: false}` (identical group name, confirmed by direct file read). `daily.yml`'s `collect` job has `timeout-minutes: 60`. |
| 11 | Full pytest suite passes before every commit / currently | VERIFIED | `PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q` → **339 passed**, 2 warnings (expected, from intentional test-triggered UserWarning paths), 6.79s. Matches SUMMARY's claimed count exactly. |

**Score:** 11/11 truths verified

### Empirical Data-Flow Verification (Finding 1 — required by task instructions)

Ran a throwaway script (`scratchpad/verify_finding1.py`) against the REAL `data/snapshots/` (26 files) and `data/metadata.json` (2,132 repos), calling `rank.compute_buckets` directly. No files under `data/` were modified (confirmed via `git status --porcelain data/` — clean before and after).

Results:
- Newest snapshot (2026-07-24): 2,211 repos.
- Globally-oldest in-window snapshot (2026-06-29): 11,645 repos.
- **OLD behavior** (join against globally-oldest only): 450 of 2,211 repos eligible → matches the audit's cited defect exactly (2,211 − 450 = 1,761 ineligible).
- **NEW behavior** (join against oldest snapshot containing each repo): 1,981 of 2,211 repos eligible pre-cap (84 no-history/newest-only, 79 no-metadata, 67 excluded by negative-delta rule).
- `compute_buckets()` end-to-end: `velocity_30d.active=True`, 10 entries returned after `VELOCITY_30D_TOP` cap — cap logic intact.

This confirms the fix raises real-data eligibility from 450 to 1,981 — well over the "substantially more than 450" bar set by the task instructions, using production data, not synthetic fixtures.

### Backward Compatibility (required by task instructions)

- All 26 files in `data/snapshots/` were confirmed (by direct inspection) to have **zero** per-repo `captured_at` keys — pure legacy schema.
- `compute_buckets()` ran against them with no exception and produced a valid, active `velocity_30d` bucket.
- `rank.entry_captured_at()` called on a real legacy entry returned exactly the file-level `captured_at` value (fallback path exercised and confirmed, not just present in code).

### Scope (required by task instructions)

- `git diff f1d2f58..HEAD -- src/report.py` → empty (byte-identical, untouched).
- `git status --porcelain data/` → clean; `git diff --stat f1d2f58..HEAD -- data/` → empty (no data files touched).
- `git diff --stat f1d2f58..HEAD` shows changes confined to the plan's `files_modified` set (rank.py, store.py, collector.py, config.py, three test files, three workflow files) plus the plan doc itself — no stray files, no `pyproject.toml` changes, no new dependencies.

### CI Workflow (required by task instructions)

- `.github/workflows/ci.yml`, `daily.yml`, `keepalive.yml` all parsed successfully with PyYAML (`safe_load`) — valid YAML syntax (the `on:` key parsing as the boolean `True` is the well-known PyYAML 1.1 quirk for GitHub Actions files, not a syntax error).
- `ci.yml` triggers on `[push, pull_request]` and its only step that matters runs `uv run pytest -q` — actually invokes the real test suite, not a stub.
- `daily.yml` and `keepalive.yml` both declare `concurrency: {group: repo-writes, cancel-in-progress: false}` — identical group, confirmed by direct read of both files.
- `daily.yml`'s `collect` job declares `timeout-minutes: 60`.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/rank.py` | per-repo oldest-containing join, `entry_captured_at`, `exclude_ids` | VERIFIED | All present, wired, and behaviorally confirmed against real data. |
| `src/store.py` | `write_metadata` merge, per-repo `captured_at` stamping | VERIFIED | Both present; merge confirmed via `{**existing, **new_entries}`; stamping confirmed via `{**existing, **{...captured_at: run_at...}}` upsert. |
| `src/collector.py` | full candidate set to write_snap/write_meta; `exclude_ids` wiring | VERIFIED | Lines 156-164 confirm both. |
| `.github/workflows/ci.yml` | pytest on push/PR, SHA-pinned actions | VERIFIED | Present, valid YAML, correct triggers, pinned SHAs matching daily.yml's convention. |
| `tests/test_rank.py`, `test_store.py`, `test_collector.py` | new test classes proving each finding | VERIFIED | `TestVelocity30dOldestContainingSnapshot`, `TestComputeBucketsExcludeIds`, `TestEntryCapturedAt`, `TestVelocityUsesPerRepoCapturedAt`, `TestFilterRetainsHistory`, `TestCiYaml`, `TestSharedConcurrencyGroup` all present and included in the 339 passing tests. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `compute_buckets` velocity_30d loop | oldest in-window snapshot containing rid | `next((s for s in in_window[:-1] if rid in s["repos"]), None)` | WIRED | Confirmed at `src/rank.py:370-374`, exercised empirically against real data. |
| `collector.run()` | `compute_buckets` | `exclude_ids` keyword | WIRED | `src/collector.py:157,164`. |
| `store.write_metadata` | existing `metadata.json` | `load_metadata` merge | WIRED | `src/store.py:127,139`; corrupt-file abort semantics preserved (unmodified `load_metadata`). |
| `rank.entry_captured_at` | snapshot file-level `captured_at` | `.get('captured_at') or snap['captured_at']` | WIRED | `src/rank.py:94`; empirically confirmed to resolve correctly on real legacy data. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full suite passes | `pytest -q` | 339 passed, 2 warnings, 6.79s | PASS |
| velocity_30d eligibility on real data | throwaway script calling `compute_buckets` on `data/` | 1,981 eligible (vs 450 old-behavior) | PASS |
| Legacy snapshot fallback | `entry_captured_at` on real legacy entry | resolved to file-level `captured_at` exactly | PASS |
| CI workflow YAML validity | PyYAML `safe_load` on all three workflow files | all parse without error | PASS |

### Anti-Patterns Found

None. Scanned `src/rank.py`, `src/store.py`, `src/collector.py`, `src/config.py` for TODO/FIXME/placeholder/stub patterns — no matches.

### Human Verification Required

None. All must-haves were verifiable programmatically against real production data and the actual codebase.

### Gaps Summary

No gaps. All five findings are implemented with substance (not stubs), correctly wired end-to-end, and confirmed against real on-disk data rather than synthetic fixtures alone. Scope was respected: `src/report.py` is byte-identical, `data/` is untouched, no new dependencies or stray files were introduced.

---

_Verified: 2026-07-25_
_Verifier: Claude (gsd-verifier)_
