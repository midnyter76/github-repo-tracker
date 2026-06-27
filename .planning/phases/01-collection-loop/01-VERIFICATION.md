---
phase: 01-collection-loop
verified: 2026-06-27T22:10:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Trigger workflow_dispatch (or wait for 13:00 UTC cron). Confirm data/snapshots/YYYY-MM-DD.json is committed by the github-actions bot. Confirm file is keyed by numeric repo IDs (not owner/repo strings)."
    expected: "A new dated snapshot JSON appears in the repo, committed by the GitHub Actions bot with message 'chore: daily snapshot [skip ci]'."
    why_human: "SC-1 runtime: requires the actual GitHub Actions environment and remote repo — not executable in-plan. First real run establishes history accumulation."
  - test: "After a real workflow run, open the Actions log for the 'Run collector' step. Confirm GITHUB_TOKEN value is masked as *** in the log output. Confirm no token string appears in any committed file under data/."
    expected: "Actions log shows *** wherever the token would appear. No token value in data/snapshots/ or data/metadata.json."
    why_human: "SC-2 runtime: token masking by GitHub Actions runner cannot be verified from the local codebase — requires an actual workflow execution."
---

# Phase 1: Collection Loop Verification Report

**Phase Goal:** Daily star-count snapshots are committed to the repo each morning via GitHub Actions; history accumulation begins on day 1.
**Verified:** 2026-06-27T22:10:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A new `data/snapshots/YYYY-MM-DD.json` file is produced after each run, keyed by numeric `repo.id` | VERIFIED (code) | `write_snapshot` creates `snapshots_dir / f"{date_str}.json"`; key = `str(repo.id)` (not owner/repo); cron `0 13 * * *` triggers daily; git-auto-commit-action commits `data/**`. Runtime confirmation: see Human Verification #1. |
| 2 | Workflow runs with token from secrets, no credentials exposed in logs or committed files | VERIFIED (code) | `GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}` in env block; `build_client()` reads via `os.environ.get("GITHUB_TOKEN")` — never printed. Token scan: only `ghp_fake_token` in test fixtures (correct — tests assert the error message does NOT contain a token). All action SHAs confirmed via `gh api` (see Anti-Patterns). Runtime log-masking confirmation: see Human Verification #2. |
| 3 | Combo AI filter (topic-union + keyword-fallback, date-windowed) fetches candidates; every sub-query's `total_count` stays under 1,000 via over-cap handling | VERIFIED | `discover_repos` merges topic queries (6 topics × 2 windows) + keyword queries via `safe_search`; `over_cap()` called on every result set; over-cap path issues complementary date-range query (WR-02) or star-band split (WR-04). `discover_established` adds D-11 star-banded queries (no `created:` window). 96/96 tests pass, including `test_monthly_cohort_preserved_when_30d_over_cap`. |
| 4 | Re-running the workflow on the same day does not corrupt or duplicate the existing snapshot | VERIFIED | `write_snapshot` loads existing file via `json.loads` then merges `{**existing, **new}` — new values win, old entries survive. `json.JSONDecodeError` guard (CR-01) prevents corrupt-file abort. `test_store.py` idempotency test covers write-twice-both-ids-present. |
| 5 | All timestamps in snapshot and metadata files are UTC ISO 8601 strings | VERIFIED | `main()` stamps `datetime.now(timezone.utc)`; `run_at.isoformat()` used for `captured_at` and `updated_at`; `r.created_at.isoformat()` used for repo `created_at` in metadata. `test_store.py` asserts UTC-aware isoformat on all timestamp fields. |

**Score:** 5/5 truths verified (code side complete; 2 require runtime confirmation)

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/config.py` | All FILTER-04 tunable constants | VERIFIED | 8 constants present: `TOPICS` (6 items, D-01), `KEYWORD_SETS`, `KEYWORD_STAR_FLOOR=10` (D-02), `QUALIFIER_EXCLUSIONS`, `BREAKTHROUGH_STAR_BANDS` (D-11), `NEW_REPO_WINDOWS`, `TOTAL_COUNT_CAP_WARN=900`, `SNAPSHOTS_DIR`, `METADATA_PATH`. `test_config.py` 8/8 pass. |
| `src/search.py` | Discovery + refresh logic with cap handling | VERIFIED | `discover_repos`, `discover_established`, `refresh_tracked`, `safe_search`, `over_cap`, `split_star_band`, query builders all present and substantive. No stub returns. |
| `src/store.py` | Idempotent write_snapshot, write_metadata, load functions | VERIFIED | `write_snapshot` upserts via `{**existing, **new}` with JSONDecodeError guard; `write_metadata` full overwrite; `load_metadata` returns `{}` on absent/corrupt; `load_metadata_ids` chains correctly. |
| `src/collector.py` | build_client, run (injectable), main entry point | VERIFIED | `build_client` reads token from env, raises `RuntimeError("GITHUB_TOKEN not set")` (no value echoed); `run` accepts all deps as params for zero-network testing; `main` stamps UTC; `if __name__` guard present. |
| `.github/workflows/daily.yml` | Cron trigger, token env, uv run, commit-back | VERIFIED | `cron: '0 13 * * *'`, `workflow_dispatch`, `permissions: contents: write`, `GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}`, `uv run python -m src.collector`, git-auto-commit-action `file_pattern: data/**`. All three actions SHA-pinned (SHAs confirmed — see Anti-Patterns). |
| `tests/` (4 files) | Full suite green, no hollow tests | VERIFIED | 96/96 pass (`uv run pytest -q`). Test files: `test_config.py` (8), `test_search.py` (42+), `test_store.py` (20+), `test_collector.py` (24). WR-08 hollow test replaced with genuine static-analysis gate (T-01-04). |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `collector.py:main` | `store.write_snapshot` | `run(…, write_snap=write_snapshot)` default | WIRED | `main()` calls `run(build_client(), …)` with default injected deps; `run` calls `write_snap(repos, now)` |
| `collector.py:main` | `store.write_metadata` | `run(…, write_meta=write_metadata)` default | WIRED | Same injection pattern; `run` calls `write_meta(repos, now)` |
| `collector.py:run` | `search.discover_repos` | `discover(g)` parameter | WIRED | `run` calls `discover(g)` → merges into combined dict |
| `collector.py:run` | `search.discover_established` | `established(g)` parameter | WIRED | `run` calls `established(g)` → merges into combined dict |
| `collector.py:run` | `search.refresh_tracked` | `refresh(g, load_ids())` parameter | WIRED | `run` calls `refresh(g, load_ids())` LAST so re-fetched counts win |
| `daily.yml:Run collector` | `src.collector:main` | `uv run python -m src.collector` | WIRED | Module invocation (not path) ensures correct import resolution |
| `daily.yml:Commit snapshot` | `data/snapshots/` | `file_pattern: data/**` | WIRED | git-auto-commit-action stages any new/changed file under `data/` |
| `search.py:discover_repos` | `config.TOPICS` | direct import | WIRED | `from src.config import TOPICS` used in loop |
| `search.py:safe_search` | rate-limit pre-check | `g.get_rate_limit().search.remaining` | WIRED | Checks remaining before call; sleeps until reset if near zero |

---

### Data-Flow Trace (Level 4)

Not applicable — Phase 1 produces file outputs (JSON snapshots), not rendered components. Data flows from GitHub API → `discover_repos`/`discover_established`/`refresh_tracked` → `write_snapshot`/`write_metadata` → `data/snapshots/YYYY-MM-DD.json` and `data/metadata.json`. This chain is wired (see Key Link table). The actual data population requires a live GitHub API call — inherently runtime-only.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Entry point exits with clear error when token missing | `GITHUB_TOKEN="" uv run python -m src.collector 2>&1` | `RuntimeError: GITHUB_TOKEN not set` (no token value echoed) | PASS |
| Entry point importable (no ModuleNotFoundError) | Subprocess test in `test_collector.py::test_entry_point_no_import_error` | Passes (confirmed by 96/96 suite) | PASS |
| Full test suite | `uv run pytest -q` | `96 passed, 0 failed` | PASS |

Live GitHub API call: SKIPPED (requires network + real token; inherently out-of-band per plan design).

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DATA-01 | 01-01-PLAN, 01-02-PLAN | Snapshots keyed by numeric repo.id (not owner/repo string) | SATISFIED | `str(repo.id)` used as dict key throughout `search.py` and `store.py`; no `owner/repo` string keys |
| DATA-02 | 01-03-PLAN | Per-date JSON files: `data/snapshots/YYYY-MM-DD.json` | SATISFIED | `write_snapshot` creates `snapshots_dir / f"{date_str}.json"`; `SNAPSHOTS_DIR = Path("data/snapshots")` in config |
| DATA-03 | 01-03-PLAN | Separate `data/metadata.json`, full overwrite each run | SATISFIED | `write_metadata` performs full overwrite with no merge; separate path `METADATA_PATH = Path("data/metadata.json")` |
| DATA-04 | 01-03-PLAN | Idempotent same-day upsert: `{**existing, **new}` | SATISFIED | `write_snapshot` load-then-merge pattern; existing entries survive; JSONDecodeError guarded |
| DATA-05 | 01-03-PLAN | All timestamps UTC ISO 8601 | SATISFIED | `datetime.now(timezone.utc).isoformat()` for run stamps; `r.created_at.isoformat()` for repo dates |
| FILTER-01 | 01-02-PLAN | Topic-union + keyword-fallback combo filter, date-windowed | SATISFIED | `discover_repos` runs 6 topics × 2 windows + keyword sets; `discover_established` adds D-11 star-banded queries |
| FILTER-02 | 01-02-PLAN | `over_cap` detection + complementary queries on cap breach | SATISFIED | `over_cap()` called after every search; WR-02 complementary date-range query; WR-04 sub-band cap check in `discover_established` |
| FILTER-03 | 01-02-PLAN | Deduplicate merged results by numeric repo.id | SATISFIED | All merge operations use `str(repo.id)` as key; later writes overwrite earlier (refresh last wins) |
| FILTER-04 | 01-01-PLAN | All thresholds tunable via `src/config.py` | SATISFIED | `TOPICS`, `KEYWORD_SETS`, `KEYWORD_STAR_FLOOR`, `TOTAL_COUNT_CAP_WARN`, `BREAKTHROUGH_STAR_BANDS`, `NEW_REPO_WINDOWS` all in config |
| AUTO-01 | 01-04-PLAN | GitHub Actions cron schedule at 13:00 UTC | SATISFIED | `cron: '0 13 * * *'` in `daily.yml`; `workflow_dispatch` for manual trigger |
| AUTO-02 | 01-04-PLAN | Token from Actions secret; never echoed in logs or code | SATISFIED | `GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}`; `os.environ.get("GITHUB_TOKEN")` read-only; zero print/log of token value |
| AUTO-03 | 01-04-PLAN | Commit-back snapshot and metadata to repo | SATISFIED | `git-auto-commit-action` with `file_pattern: data/**` and `permissions: contents: write` |

All 12 Phase 1 requirements: SATISFIED.

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `tests/test_collector.py` | `ghp_fake_token` literal | Info | Test fixture only — used as dummy value; assertions verify it does NOT appear in error messages. Not a leaked credential. |

No stub implementations, no placeholder returns, no `TODO`/`FIXME` in production code.

**SHA verification (WR-05):** All three action SHAs confirmed live via `gh api repos/{owner}/{repo}/commits/{sha}`:

| Action | On-disk SHA | Resolved |
|--------|------------|---------|
| `actions/checkout` | `11bd71901bbe5b1630ceea73d27597364c9af683` | `11bd71901bbe5b1630ceea73d27597364c9af683` (v4.2.2) |
| `astral-sh/setup-uv` | `fac544c07dec837d0ccb6301d7b5580bf5edae39` | `fac544c07dec837d0ccb6301d7b5580bf5edae39` (v8.2.0) |
| `stefanzweifel/git-auto-commit-action` | `8621497c8c39c72f3e2a999a26b4ca1b5058a842` | `8621497c8c39c72f3e2a999a26b4ca1b5058a842` (v5.0.1) |

All three resolve. No 404s. Supply-chain integrity confirmed.

---

### Human Verification Required

#### 1. Live Snapshot Commit (SC-1 runtime)

**Test:** Push the branch to the remote. Trigger `workflow_dispatch` from the GitHub Actions UI (or wait for the 13:00 UTC cron). After the run completes, confirm a file matching `data/snapshots/YYYY-MM-DD.json` was committed by the `github-actions` bot.

**Expected:** A dated snapshot file appears in the repo, committed with message `"chore: daily snapshot [skip ci]"`. Opening the file shows a top-level `"repos"` object whose keys are all-numeric strings (e.g. `"12345678"`), not `"owner/repo"` strings.

**Why human:** Requires the GitHub Actions runner environment and remote repo write access — not runnable locally. First real run marks day 1 of history accumulation.

#### 2. Token Masking in Actions Log (SC-2 runtime)

**Test:** After the live workflow run from #1, open the Actions log for the `"Run collector"` step. Search for any occurrence of the literal token value.

**Expected:** The token value is masked as `***`. No substring of the actual token appears in the log output. No credential appears in any committed file under `data/`.

**Why human:** GitHub Actions token masking is a runner-side behavior — the local codebase can only guarantee the script never prints it (confirmed by code scan), not that the runner masks it correctly. This is a runtime/environment verification.

---

### Gaps Summary

No gaps. All code-verifiable must-haves are satisfied. Phase 1 is ready to merge pending human confirmation of the live workflow run (Steps 1 and 2 above).

The two human verification items are inherently out-of-band: they require the GitHub remote and a real Actions run. This was acknowledged explicitly in `01-04-PLAN.md` and `01-04-SUMMARY.md` as post-merge verification.

---

_Verified: 2026-06-27T22:10:00Z_
_Verifier: Claude (gsd-verifier)_
