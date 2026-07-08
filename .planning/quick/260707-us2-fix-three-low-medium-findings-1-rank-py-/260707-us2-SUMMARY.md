---
phase: quick-260707-us2
plan: 01
subsystem: rank-engine, ci-workflow
tags: [datetime, timezone, github-actions, workflow-yaml, email]

# Dependency graph
requires: []
provides:
  - "creation_velocity normalizes naive (no-tzinfo) datetimes to UTC before subtraction, closing a crash risk on untested PyGithub tz-naive paths"
  - "daily.yml passes the collector's actual report path forward via $GITHUB_OUTPUT instead of recomputing today's date in the email step, closing a UTC-midnight silent-skip race"
  - "daily.yml email recipient sourced from vars.REPORT_TO_EMAIL repo variable instead of hardcoded address"
affects: [collector, report-emailing, rank-engine]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "tzinfo-is-None normalization guard for any datetime parsed from external/untested metadata before subtraction with a known-aware datetime"
    - "GitHub Actions cross-step data passing via $GITHUB_OUTPUT instead of re-deriving in a later step (avoids time-of-check/time-of-use races across steps that can straddle a day boundary)"

key-files:
  created: []
  modified:
    - src/rank.py
    - tests/test_rank.py
    - .github/workflows/daily.yml

key-decisions:
  - "Guard applied only to creation_velocity (the sole site subtracting a metadata-sourced possibly-naive datetime from a snapshot-sourced always-aware one); spike_velocity/rolling_velocity/is_new were left untouched per plan's interface analysis — they never encounter a naive/aware mismatch"
  - "Report path captured via ls -t reports/*.md immediately after the collector step (before the slower commit step), relying on write_digest always running unconditionally in src/collector.py"
  - "REPORT_TO_EMAIL repo variable value is NOT set by this task — deferred to human action (mutating live repo state is out of scope for the executor)"

patterns-established:
  - "TDD RED/GREEN gate for the tzinfo guard: failing regression test committed first (725a40e), then the fix (f8d9689)"

requirements-completed: [AUDIT-RANK-TZ, AUDIT-WF-RACE, AUDIT-WF-EMAIL]

# Metrics
duration: ~15min
completed: 2026-07-08
---

# Quick Task 260707-us2: Fix Three Low/Medium Audit Findings Summary

**Naive-datetime tzinfo guard in creation_velocity, plus race-free report-path passing and repo-variable email recipient in daily.yml**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-08T05:20:44Z
- **Tasks:** 2 completed
- **Files modified:** 3

## Accomplishments
- `creation_velocity` no longer raises `TypeError` if `created_at_iso` is ever a naive ISO string from an untested PyGithub path — normalized to UTC via a `tzinfo is None` guard on both operands.
- `.github/workflows/daily.yml` email step now consumes the collector's actual report path (`steps.report.outputs.md`, captured via a new "Determine report path" step immediately after the collector runs) instead of independently recomputing "today" — closes a UTC-midnight silent-skip race.
- `.github/workflows/daily.yml` has zero hardcoded email addresses; recipient now sourced from the `vars.REPORT_TO_EMAIL` repository variable.
- Full test suite: 310 passed, 0 failed, 0 regressions.

## Task Commits

Each task was committed atomically:

1. **Task 1a: Add failing regression test (RED)** - `725a40e` (test)
2. **Task 1b: Normalize naive created_at_iso to UTC (GREEN)** - `f8d9689` (feat)
3. **Task 2: Race-free report path + repo-variable recipient in daily.yml** - `c6344e6` (fix)

_TDD gate sequence verified in git log: test(725a40e) -> feat(f8d9689) -> fix(c6344e6)._

## Files Created/Modified
- `src/rank.py` - `creation_velocity`: added `tzinfo is None` guard on `created` and `captured` before subtraction
- `tests/test_rank.py` - Added `test_naive_created_at_normalized_to_utc` regression test to `TestCreationVelocity`
- `.github/workflows/daily.yml` - Added "Determine report path" step (`id: report`); email step now reads `steps.report.outputs.md` + `vars.REPORT_TO_EMAIL` instead of recomputing today's date and hardcoding the recipient

## Decisions Made
- Followed the plan's TDD flow for Task 1: wrote the failing test against the pre-fix `creation_velocity` (confirmed `TypeError`), committed it, then applied the fix and confirmed green before committing.
- No architectural changes; both fixes are surgical, matching the plan's `<action>` blocks verbatim.

## Deviations from Plan

None - plan executed exactly as written. Verification for Task 2 used the system `python` (which has `pyyaml` installed) rather than `uv run python`, since `pyyaml` is not a project dependency and the plan's verify step only needed it for a one-off structural check of the YAML, not for the shipped code — no dependency was added to the project.

## Issues Encountered
None.

## Action Required (flagged per plan `<output>`)

1. **Set the `REPORT_TO_EMAIL` repository variable before the next scheduled run (13:00 UTC daily).** This task's workflow change only *references* `vars.REPORT_TO_EMAIL` — it does not and must not set its value (mutating live GitHub repo settings is outside the executor's scope). Until set, `vars.REPORT_TO_EMAIL` resolves empty and the email step will send with a missing/blank recipient. Set it via GitHub repo Settings -> Secrets and variables -> Actions -> Variables tab (New repository variable), or run `gh variable set REPORT_TO_EMAIL --body "midnyter@gmail.com"` locally.
2. **The report-path fix depends on `write_digest` always running unconditionally in `src/collector.py`** (verified during planning, not re-verified at execution time). If a future change makes report-writing conditional, the "newest `reports/*.md`" glob in the "Determine report path" step would need revisiting.

## User Setup Required

External: the `REPORT_TO_EMAIL` GitHub repository variable must be set by a human (see Action Required #1 above). This executor did not and must not mutate live repo settings.

## Next Phase Readiness
Both fixes are self-contained and merge-ready. No blockers. The `REPORT_TO_EMAIL` variable setup (human action) should happen before the next scheduled 13:00 UTC run to avoid a blank-recipient email send.

---
*Phase: quick-260707-us2*
*Completed: 2026-07-08*

## Self-Check: PASSED

All 3 commits (725a40e, f8d9689, c6344e6) found in git log. All modified/created files (src/rank.py, tests/test_rank.py, .github/workflows/daily.yml, SUMMARY.md) confirmed present on disk.
