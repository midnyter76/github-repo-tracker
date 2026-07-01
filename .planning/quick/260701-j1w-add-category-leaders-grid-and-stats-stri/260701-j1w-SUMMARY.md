---
phase: quick-260701-j1w
plan: 01
subsystem: reporting
tags: [html-email, gmail-compatibility, digest-renderer, tables-layout]

# Dependency graph
requires:
  - phase: quick-260630-tl4
    provides: render_html_digest hero-edition renderer, render_html_hero/row/bucket helpers, _esc/_vel_fmt/select_top_mover
  - phase: quick-260701-ibb
    provides: Gmail flexbox-gap fix pattern (table/margin over display:flex/gap) reused here
provides:
  - "render_html_leaders() — 4-cell CATEGORY LEADERS grid + 3-cell footer stats strip, table-based (Gmail-safe)"
  - "_vel_abbr, _count_tracked, _count_brand_new, _LEADER_KICKERS helpers"
  - "leaders block wired into render_html_digest between hero and per-bucket sections"
affects: [reporting, html-digest]

tech-stack:
  added: []
  patterns:
    - "HTML email multi-column layout via <table role=\"presentation\"> + border-spacing, never display:flex/gap: (Gmail collapses flex to a vertical stack)"
    - "Structural table-cell-count assertions (count of <td width=\"X%\">) as the real regression guard against Gmail flex breakage — label-only assertions are insufficient"

key-files:
  created: []
  modified:
    - src/report.py
    - tests/test_report.py

key-decisions:
  - "Consolidated TDD sequence: wrote all tests first (RED, ImportError-driven failures), committed test(...), then implemented src/report.py to green, committed feat(...) — satisfies the RED-before-GREEN gate check while directly exercising the structural table-cell-count test against a not-yet-existing implementation"
  - "Two of the newly-written tests had test-design bugs (not implementation bugs): a regex checking for 'no velocity number' matched an unrelated CSS font-size decimal (9.5px), and an ordering assertion using result.index('Brand New This Week') found a false-early match because that exact string also appears inside the hero card's 'Fastest mover · {title}' line. Both fixed by tightening assertions (absence of 'stars / day' sublabel; ordering against the section-only kicker 'Brand New · Weekly' instead) rather than weakening the underlying guarantee being tested."

patterns-established:
  - "Leader-cell short kickers live in a separate _LEADER_KICKERS dict, not folded into _HTML_SECTIONS (whose 3-tuple arity is unpacked in several other call sites and must not change)"

requirements-completed: [QUICK-J1W]

duration: 7min
completed: 2026-07-01
---

# Phase quick-260701-j1w: Add CATEGORY LEADERS grid and stats strip Summary

**Table-based 4-cell CATEGORY LEADERS grid + 3-cell stats strip (REPOS TRACKED / BRAND NEW / TOP */DAY) inserted between the hero card and bucket sections in the HTML digest, using `<table>`+`border-spacing` (not flexbox) to stay Gmail-safe.**

## Performance

- **Duration:** ~8 min (13:50 plan commit → 13:58 final test commit)
- **Started:** 2026-07-01T13:50:09-07:00
- **Completed:** 2026-07-01T13:58:00-07:00 (approx.)
- **Tasks:** 2 (consolidated into test-first → implement sequence per advisor guidance) + 1 post-review test addition
- **Files modified:** 2

## Accomplishments
- 4-cell CATEGORY LEADERS grid: one cell per bucket (`brand_new_weekly`, `brand_new_monthly`, `spike_24h`, `velocity_30d`), short green uppercase kicker, active-bucket leader shown as big green velocity + bold white repo name (owner stripped), inactive/empty buckets show italic gray "Warming up." with no number
- 3-cell footer stats strip: REPOS TRACKED (green, deduped repo count across all buckets), BRAND NEW (white, count of `marker == "new"` entries in the two brand-new buckets only), TOP */DAY (green, abbreviated global-max velocity via `_vel_abbr`, e.g. `3692.2` → `3.7k`)
- Both blocks render as real HTML `<table>` columns (`<td width="25%">` × 4, `<td width="33.33%">` × 3) with `border-spacing` gutters — no `display:flex`/`gap:` anywhere, matching the project's prior Gmail-rendering fix (260701-ibb)
- Markdown digest path (`write_digest`, `render_entry`, `render_bucket`) and existing hero/bucket/row HTML renderers are byte-for-byte unchanged — verified via `git diff src/report.py` showing a pure-addition diff plus two one-line insertion points

## Task Commits

Test-first TDD sequence (consolidated per advisor recommendation — RED before GREEN, watching the structural table-cell test go from ImportError to green):

1. **RED — add failing tests for leaders grid/strip/helpers** - `68c9f83` (test)
2. **GREEN — implement render_html_leaders + helpers, wire into render_html_digest** - `bcfe9b3` (feat)
3. **Belt-and-suspenders — pin BRAND NEW stat color as white, not green** - `910ee7c` (test)

_No refactor commit needed — implementation was clean on first pass; only the newly-written test assertions needed two fixes, which were folded into the feat commit alongside the implementation. Commit 3 was added post-review to explicitly guard a plan requirement ("BRAND NEW ... WHITE, NOT green") that had no dedicated test._

## TDD Gate Compliance

Both gates present in git log, in correct order:
1. `test(260701-j1w): add failing tests ...` (RED) — `68c9f83`
2. `feat(260701-j1w): add CATEGORY LEADERS grid ...` (GREEN) — `bcfe9b3`

RED-phase verification: 13 new tests failed (ImportError for `render_html_leaders`/`_vel_abbr`/`_count_tracked`/`_count_brand_new`, `AssertionError`/`ValueError` for content not yet present); all 67 pre-existing `test_report.py` tests still passed unchanged.

## Files Created/Modified
- `src/report.py` — added `_vel_abbr`, `_count_tracked`, `_count_brand_new`, `_LEADER_KICKERS`, `_render_leader_cell`, `_render_strip_cell`, `render_html_leaders`; wired `leaders_html` into `render_html_digest` between hero and `sections_html`
- `tests/test_report.py` — added `TestVelAbbr`, `TestCountTracked`, `TestCountBrandNew`, `TestRenderHtmlLeaders`, `TestHtmlDigestStatsStrip` (13 new tests covering helpers, structural table-cell counts, active/warming cell content, repo-name escaping, no-gap guard, and insertion-order between hero and sections)

## Decisions Made
- Consolidated the plan's two tasks (Task 1 `tdd="true"` src implementation, Task 2 separate test-authoring task) into a single test-first → implement sequence, per advisor recommendation, to satisfy the TDD RED/GREEN gate check while actually exercising the structural regression guard (table `<td>` count) against a real ImportError before the implementation existed.
- Fixed two test-design bugs discovered during the RED→GREEN transition rather than weakening the assertions: (1) the "no velocity number in a warming cell" check originally used a raw `\d+\.\d` regex that matched the kicker's `font-size:9.5px` CSS value — replaced with an assertion that the active-only `"stars / day"` sublabel is absent; (2) the hero-vs-sections ordering check originally searched for `"Brand New This Week"`, which also appears inside the hero's `"Fastest mover · Brand New This Week"` line and produced a false-early match — replaced with the section-only kicker string `"Brand New · Weekly"`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Two self-authored test assertions had incorrect isolation logic**
- **Found during:** first full-suite run after implementing `render_html_leaders` (GREEN attempt)
- **Issue:** `test_inactive_cell_shows_warming_up_and_no_number` used `re.search(r"\d+\.\d", spike_cell)` which matched the unrelated `font-size:9.5px` value inside the same cell's kicker `<div>` style attribute, not an actual velocity number. `test_leaders_grid_inserted_between_hero_and_sections` used `result.index("Brand New This Week")` to locate the first bucket section, but that exact string also appears inside the hero card's kicker line (`"● Fastest mover · Brand New This Week"`), which renders earlier in the document — giving a false-early index and an inverted ordering assertion.
- **Fix:** Replaced the regex check with an assertion that `"stars / day"` (only rendered for active leader cells) is absent from the warming cell. Replaced the ordering marker with `"Brand New · Weekly"` (the bucket kicker string, which only appears in the section header, not the hero).
- **Files modified:** tests/test_report.py
- **Commit:** bcfe9b3 (bundled with the feat commit since both the implementation and its test-verification landed together)

---

**Total deviations:** 1 auto-fixed (1 bug — self-authored test correctness, not an implementation defect)
**Impact on plan:** No scope creep; both fixes tightened test precision without weakening the underlying guarantees (Gmail-safe table structure, no-number-on-warming-cell).

## Issues Encountered
- Initial `uv run pytest` invocations were accidentally run from the main repo checkout path (`C:/dev/github-repo-tracker`) rather than the worktree root (`.../.claude/worktrees/agent-a17bf88c11dae9cad`), which silently ran against the pre-edit file and showed 67/67 passing with none of the new tests collected. Caught by comparing collected test counts before/after the edit; resolved by always `cd`-ing into `git rev-parse --show-toplevel` before running `uv run pytest`.
- One pre-existing failure unrelated to this task: `tests/test_search.py::TestDiscoverRepos::test_monthly_cohort_preserved_when_30d_over_cap`. Confirmed via `git stash` (removing this task's changes) that the failure exists independent of this plan — `src/search.py`/`tests/test_search.py` are not in this plan's `files_modified` and were not touched. Already logged in a prior quick task's deferred-items.md; re-logged in this task's `deferred-items.md` for traceability. Out of scope per the deviation rules' scope boundary (only fix issues directly caused by this task's changes).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- HTML digest now has an at-a-glance scoreboard (leaders grid + stats strip) matching the reference layout, ahead of the detailed per-bucket sections.
- Markdown digest path fully untouched; no follow-up required there.
- The pre-existing `test_search.py` failure (monthly cohort / 30d-over-cap complementary query) remains open and unrelated to reporting — a future quick task or phase should address `src/search.py` directly.

---
*Phase: quick-260701-j1w*
*Completed: 2026-07-01*

## Self-Check: PASSED

- FOUND: src/report.py
- FOUND: tests/test_report.py
- FOUND: .planning/quick/260701-j1w-add-category-leaders-grid-and-stats-stri/260701-j1w-SUMMARY.md
- FOUND: .planning/quick/260701-j1w-add-category-leaders-grid-and-stats-stri/deferred-items.md
- FOUND commit: 68c9f83 (test)
- FOUND commit: bcfe9b3 (feat)
- FOUND commit: 910ee7c (test)
