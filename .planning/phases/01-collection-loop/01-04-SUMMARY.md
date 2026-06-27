---
phase: 01-collection-loop
plan: 04
subsystem: collector-orchestration-and-ci
tags: [orchestration, github-actions, cron, security, entry-point]
requires:
  - "src/config.py (TOPICS, KEYWORD_SETS, paths) — Plan 01-01"
  - "src/search.py (discover_repos, discover_established, refresh_tracked) — Plan 01-02"
  - "src/store.py (load_metadata_ids, write_snapshot, write_metadata) — Plan 01-03"
provides:
  - "src/collector.py: build_client (env-token Github client), run (orchestration), main, __main__ entry"
  - ".github/workflows/daily.yml: daily cron + workflow_dispatch + commit-back"
affects:
  - "Closes the fetch→snapshot→commit loop; produces data/** committed each run for Phase 2 to read"
tech-stack:
  added: []
  patterns:
    - "Keyword-injectable dependencies on run() so tests pass fakes without monkeypatching module names"
    - "Single token read in build_client; never referenced elsewhere (Pitfall 4 / T-01-10)"
    - "Module invocation python -m src.collector so imports resolve identically in tests and CI"
key-files:
  created:
    - "src/collector.py"
    - "tests/test_collector.py"
    - ".github/workflows/daily.yml"
  modified: []
decisions:
  - "D-06: cron '0 13 * * *' (13:00 UTC) in daily.yml"
  - "D-07: run_at stamped via datetime.now(timezone.utc) in main()"
  - "D-08: public repo is the datastore; commit-back targets data/**"
  - "D-09: built-in GITHUB_TOKEN with contents:write, injected from secret, never echoed (no PAT)"
  - "D-10: commit-back via stefanzweifel/git-auto-commit-action@v5 with [skip ci]"
metrics:
  duration: "~1 session (interrupted + resumed)"
  completed: "2026-06-27"
  tasks: 2
  files: 3
---

# Phase 1 Plan 04: Collector Orchestration + GitHub Actions Loop Summary

Wired the discovery + refresh + persistence layers into a single token-authenticated collector (`src/collector.py`) and shipped it to a daily GitHub Actions cron (`.github/workflows/daily.yml`) with secret injection and commit-back — closing the fetch→snapshot→commit loop that makes "a snapshot appears in the repo every morning" true.

## What Was Built

### Task 1 — `src/collector.py` (TDD: RED → GREEN)
- **`build_client()`** reads `GITHUB_TOKEN` exactly once via `os.environ.get`, raises `RuntimeError("GITHUB_TOKEN not set")` (no value echoed) when absent, and returns `github.Github(auth=github.Auth.Token(token), retry=github.GithubRetry(), seconds_between_requests=0.5)` (Pattern 1, D-09).
- **`run(g, now, *, discover, established, load_ids, refresh, write_snap, write_meta)`** builds a `candidates` dict by unioning `discover(g)` → `established(g)` → `refresh(g, load_ids())` in that order. Refresh runs **last** so re-fetched star counts override discovery stubs (DATA-01). Then calls `write_snap(candidates, now)` and `write_meta(candidates, now)`. All deps are keyword-injectable for testing.
- **`main()`** calls `run(build_client(), datetime.now(timezone.utc))` (UTC per D-07).
- **`if __name__ == "__main__": main()`** module entry point.
- `github` imported as a module (not `from github import ...`) so `github.Github`/`github.Auth.Token` resolve at call time — required for the patched-client test.

### Task 2 — `.github/workflows/daily.yml`
- `schedule.cron: '0 13 * * *'` (D-06) + `workflow_dispatch` manual trigger (AUTO-01).
- Top-level `permissions: contents: write` — minimal scope for commit-back (AUTO-03, T-01-12).
- Job `collect` on `ubuntu-latest`: `actions/checkout@v4` → `astral-sh/setup-uv@v8` (enable-cache) → Run collector (`env: GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}`, `run: uv run python -m src.collector`) → `stefanzweifel/git-auto-commit-action@v5` (`commit_message: "chore: daily snapshot [skip ci]"`, `file_pattern: "data/**"`).
- The token is referenced ONLY as the env mapping — never echoed in a `run:` step (AUTO-02, T-01-10/T-01-11).

### Tests — `tests/test_collector.py` (24 tests)
- `build_client`: env-token injection (patched `github.Github`/`github.Auth.Token`), missing-token `RuntimeError`, no-value-echo in the message.
- `run`: orchestration calls + order, union of all three sources, refresh-wins-over-discovery, timestamp pass-through.
- Token-safety static gates: `os.environ` appears exactly once; no `print` referencing token/auth/env; required Pattern-1 strings present.
- Entry-point subprocess gate: `python -m src.collector` with `GITHUB_TOKEN` cleared (PATH preserved) emits "GITHUB_TOKEN not set" and NOT "ModuleNotFoundError" — proving the runtime import path matches the test path.
- Workflow YAML content assertions: all required substrings present, no token echo.

## Verification

- `uv run pytest -q` → **94 passed** (70 pre-existing + 24 new), 2 unrelated warnings from Plan 01-02 tests.
- All Task 1 acceptance grep gates pass: single `os.environ` read, `github.Auth.Token`, `seconds_between_requests=0.5`, `GithubRetry`, `datetime.now(timezone.utc)`, `__main__` guard, zero token-print matches.
- `env -u GITHUB_TOKEN uv run python -m src.collector` prints "GITHUB_TOKEN not set" with no "ModuleNotFoundError".
- All Task 2 acceptance grep gates pass: cron, workflow_dispatch, contents:write, secret injection, module invocation, auto-commit@v5, `[skip ci]`, `file_pattern: "data/**"`, zero token-echo matches.

**Out-of-band (post-merge, requires the GitHub remote — NOT runnable in-plan):** trigger `workflow_dispatch` or wait for the 13:00 UTC cron, confirm a new `data/snapshots/YYYY-MM-DD.json` is committed by the github-actions bot with the token masked as `***`. Satisfies Phase 1 Success Criteria 1–2; recorded in phase verification, not this plan's automated gate.

## Deviations from Plan

None — plan executed exactly as written. The plan's CRITICAL entry-point guidance (module invocation `python -m src.collector`, overriding RESEARCH Pattern 8's path form) was followed in both `daily.yml` and the subprocess test.

## TDD Gate Compliance

- RED: `test(01-04)` commit `68eae59` — 24 tests written, all failing (collector.py + daily.yml absent).
- GREEN (collector): `feat(01-04)` commit `67a6b2c` — 15 collector tests pass.
- GREEN (workflow): `ci(01-04)` commit `90aacea` — remaining 9 workflow tests pass; full suite green.

## Known Stubs

None — no placeholder values, empty returns flowing to output, or TODO markers introduced. The collector wires real discovery/refresh/persistence functions; `data/**` files are produced only at runtime against the live API (correctly absent from the repo until the first scheduled run).

## Self-Check: PASSED

- FOUND: src/collector.py
- FOUND: tests/test_collector.py
- FOUND: .github/workflows/daily.yml
- FOUND: .planning/phases/01-collection-loop/01-04-SUMMARY.md
- FOUND commit 68eae59 (test RED)
- FOUND commit 67a6b2c (feat collector GREEN)
- FOUND commit 90aacea (ci workflow GREEN)
