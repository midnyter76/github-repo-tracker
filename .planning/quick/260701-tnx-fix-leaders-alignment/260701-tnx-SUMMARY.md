---
phase: quick-260701-tnx
plan: 01
subsystem: reporting
tags: [html-email, digest-renderer, css-fix]

requires:
  - phase: quick-260701-j1w
    provides: render_html_leaders / _render_leader_cell CATEGORY LEADERS grid
provides:
  - "_render_leader_cell card wrapper gets min-height:96px, shared by active and empty-state branches"
affects: [reporting, html-digest]

tech-stack:
  added: []
  patterns:
    - "Shared min-height on a card wrapper used by multiple content-length branches, instead of per-branch spacer markup, to keep a table-based grid row visually flush"

key-files:
  created: []
  modified:
    - src/report.py
    - tests/test_report.py

key-decisions:
  - "Single-line CSS fix (min-height:96px on the existing shared card div) rather than restructuring the empty-state markup with spacer lines — the wrapper div is already shared by both branches at _render_leader_cell's return statement, so one change fixes both without touching kicker/value/name markup"

patterns-established: []

requirements-completed: [QUICK-TNX]

duration: ~10min
completed: 2026-07-02
---

# Phase quick-260701-tnx: Fix CATEGORY LEADERS grid alignment Summary

**User-reported screenshot showed the "24H SPIKE" empty-state card ("Warming up.") rendering shorter than its 3 siblings (which show a velocity number + "stars / day" + repo name), breaking the grid row's flush bottom edge. Fixed with `min-height:96px` on the shared card wrapper div in `_render_leader_cell`.**

## Accomplishments
- Added `min-height:96px` to the card wrapper div in `_render_leader_cell` (src/report.py), applied identically to both the active-leader branch and the empty/"Warming up." branch since they share one wrapper.
- No markup restructuring: kicker/value/unit/name lines (active) and the "Warming up." text (empty) are byte-for-byte unchanged.
- Added regression test `test_active_and_empty_cards_share_min_height` in `TestRenderHtmlLeaders` asserting both an active cell and an empty cell contain the identical `min-height:96px` token.
- Verified existing invariant still holds: empty cell shows no `"stars / day"` text and no velocity number.

## Verification
- `uv run pytest tests/test_report.py -q` — 83 passed.
- `uv run pytest tests/ -q` — 281 passed, 1 pre-existing failure (`tests/test_search.py::TestDiscoverRepos::test_monthly_cohort_preserved_when_30d_over_cap`), confirmed via `git stash` to exist independently of this change (already logged in prior quick task `260701-j1w`'s deferred items; unrelated `src/search.py` bug, out of scope here).

## Files Modified
- `src/report.py` — `_render_leader_cell`: added `min-height:96px;` to the shared card div's inline style.
- `tests/test_report.py` — added `test_active_and_empty_cards_share_min_height` regression test.

## User Setup Required
None.

## Next Phase Readiness
- CATEGORY LEADERS grid cards now render at consistent height across active/empty states.
- Pre-existing `test_search.py` failure remains open, unrelated to reporting — carried forward from prior quick task.

---
*Phase: quick-260701-tnx*
*Completed: 2026-07-02*
