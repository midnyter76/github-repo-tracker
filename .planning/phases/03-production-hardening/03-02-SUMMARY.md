---
phase: 03-production-hardening
plan: "02"
subsystem: keepalive-workflow
tags: [github-actions, keepalive, workflow, tests, HARD-01]
dependency_graph:
  requires: []
  provides: [keepalive-workflow, keepalive-tests]
  affects: [.github/workflows/keepalive.yml, .github/keepalive, tests/test_collector.py]
tech_stack:
  added: []
  patterns:
    - "Every-10-days keepalive cron at off-peak non-round minute (23 4 */10 * *)"
    - "SHA-pinned actions mirroring daily.yml (identical SHAs for checkout and git-auto-commit-action)"
    - "[skip ci] in keepalive commit message to prevent self-trigger (D-10)"
    - "Dedicated .github/keepalive placeholder file to scope git-auto-commit-action to dummy file only"
key_files:
  created:
    - .github/workflows/keepalive.yml
    - .github/keepalive
  modified:
    - tests/test_collector.py
decisions:
  - "Cron schedule 23 4 */10 * *: every 10 days at 04:23 UTC — off-peak, non-round minute per RESEARCH Pattern 4 and D-01"
  - "No astral-sh/setup-uv step in keepalive.yml — no Python code in keepalive workflow"
  - "SHA pins identical to daily.yml for consistency and supply-chain safety"
  - "D-02 bot-commit approach used; API escalation path documented in workflow comment if commit mode fails at day 55"
metrics:
  duration: "~10m"
  completed: "2026-06-29T04:41:54Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 3
  files_modified: 1
---

# Phase 3 Plan 02: Keepalive Workflow Summary

**One-liner:** GitHub Actions keepalive workflow running every 10 days with SHA-pinned actions and 9 structural tests covering all HARD-01 requirements.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create .github/workflows/keepalive.yml | 49506c8 | .github/workflows/keepalive.yml (created) |
| 2 | Create .github/keepalive placeholder and TestKeepaliveYaml tests | 200bf58 | .github/keepalive (created), tests/test_collector.py (modified) |

## What Was Built

**keepalive.yml** — A standalone GitHub Actions workflow that runs every 10 days at 04:23 UTC via cron `'23 4 */10 * *'` and can be triggered manually via `workflow_dispatch`. The job writes a UTC ISO 8601 timestamp to `.github/keepalive` and commits it back with message `"chore: keepalive [skip ci]"`. This prevents GitHub from auto-disabling scheduled workflows after 60 days of inactivity (HARD-01).

Key structural properties:
- SHA-pinned `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683` (v4.2.2) — same as daily.yml
- SHA-pinned `stefanzweifel/git-auto-commit-action@8621497c8c39c72f3e2a999a26b4ca1b5058a842` (v5.0.1) — same as daily.yml
- `contents: write` permission for git-auto-commit-action
- No `astral-sh/setup-uv` step — keepalive has no Python code
- `file_pattern: ".github/keepalive"` — scopes commit-back to dummy file only
- `[skip ci]` in commit message — prevents triggering the daily workflow

**`.github/keepalive`** — Placeholder file (`placeholder` content) tracked by git so git-auto-commit-action can target it before the first keepalive run.

**`TestKeepaliveYaml`** — 9-test class appended to `tests/test_collector.py` verifying all structural requirements of `keepalive.yml` via string assertions against the file contents. All 9 tests pass.

## Verification Results

- `keepalive.yml` exists: PASS
- `.github/keepalive` exists: PASS
- Python structural check (9 assertions): ALL CHECKS PASSED
- `pytest tests/test_collector.py::TestKeepaliveYaml -v`: 9 passed
- `pytest tests/test_collector.py::TestWorkflowYaml -v`: 10 passed (no regression)
- `uv run python -m pytest tests/test_collector.py -v`: 37 passed

## Deviations from Plan

None — plan executed exactly as written. The keepalive.yml content matches the plan specification verbatim. TestKeepaliveYaml class was appended following the exact pattern of TestWorkflowYaml.

## Known Issues (Pre-existing, Out of Scope)

One pre-existing test failure exists in `tests/test_search.py::TestDiscoverRepos::test_monthly_cohort_preserved_when_30d_over_cap`. This failure was confirmed to exist before Task 2 changes (verified via `git stash`). It is unrelated to this plan's files. Logged to `deferred-items.md`.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The keepalive.yml run step uses only `date -u` (no external input, no secret references). GITHUB_TOKEN is never referenced in any `run:` command — it is injected automatically by git-auto-commit-action via Actions secrets masking (T-03-04 mitigated as designed).

## Self-Check

Files created/exist:
- `.github/workflows/keepalive.yml`: FOUND
- `.github/keepalive`: FOUND
- `tests/test_collector.py` (modified, TestKeepaliveYaml class appended): VERIFIED

Commits exist:
- `49506c8` feat(03-02): create .github/workflows/keepalive.yml: FOUND
- `200bf58` feat(03-02): add .github/keepalive placeholder and TestKeepaliveYaml tests: FOUND

## Self-Check: PASSED
