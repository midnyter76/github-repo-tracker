---
phase: quick-260725-u4s
plan: 01
subsystem: reporting

tags: [html-email, gmail-rendering, table-layout, digest]

requires:
  - phase: quick-260701-ibb
    provides: table-based Gmail-safe idiom (_render_leader_cell / _render_strip_cell) reused verbatim in this plan
provides:
  - Gmail-safe table-based HTML digest (zero display:flex/grid/gap anywhere in the rendered document)
  - tracked_total surfaced on rank.compute_buckets' four bucket dicts, threaded to the REPOS TRACKED stat
  - Deduped BRAND NEW count across brand_new_weekly/brand_new_monthly overlap
  - Restored ★ (U+2605) glyph in the TOP ★/DAY stats-strip label
affects: [reporting, email-delivery]

tech-stack:
  added: []
  patterns:
    - "Gmail-safe layout idiom: <table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\">, valign= instead of align-items, width=/align=\"right\" instead of flex:1/margin-left:auto"

key-files:
  created: []
  modified:
    - src/rank.py
    - src/report.py
    - tests/test_rank.py
    - tests/test_report.py

key-decisions:
  - "tracked_total placed INSIDE each of the four bucket dicts (never as a new top-level key) so src/collector.py's `for b in buckets.values()` iteration stays unbroken"
  - "align-items:baseline in the bucket header has no exact table equivalent; used valign=\"middle\" (up to ~2px off baseline) per plan's accepted deviation — strictly closer to design intent than Gmail's current flex-collapse"
  - "margin:0 auto added to the 620px card div alongside align=\"center\" on its wrapping <td> — belt-and-suspenders centering since not every client honors align alone on a fixed-width block child"

patterns-established:
  - "Reuse _render_leader_cell/_render_strip_cell's table idiom for any future Gmail-rendering fix in src/report.py — do not invent a second pattern"

requirements-completed: [F1-gmail-flex, F2-tracked-count, F3-brand-new-dedupe, F4-star-glyph]

duration: ~15min
completed: 2026-07-25
---

# Phase quick-260725-u4s: Fix Email Digest Rendering (Gmail-Safe Tables) Summary

**Converted the HTML email digest's flexbox layouts to Gmail-safe tables, fixed a two-orders-of-magnitude wrong REPOS TRACKED stat, deduped a double-counted BRAND NEW stat, and restored a stray `*` to `★`.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-25T21:53Z (approx, first task commit e39f226 at 21:54:24)
- **Completed:** 2026-07-25T21:59:13Z (last task commit eb97b3b)
- **Tasks:** 4/4
- **Files modified:** 4 (src/rank.py, src/report.py, tests/test_rank.py, tests/test_report.py)

## Accomplishments

- `render_html_hero`, `render_html_row`, `render_html_bucket`, and `render_html_digest`'s outer wrapper/masthead all converted from `display:flex`/`justify-content`/`align-items`/`flex:1`/`flex-shrink`/`margin-left:auto` to the `<table role="presentation">` idiom already proven elsewhere in this file — zero flex/grid/gap tokens remain anywhere in the rendered document (verified by a whole-document guard test and an inline render check).
- `rank.compute_buckets` now surfaces `tracked_total` (today's snapshot repo count) on all four bucket dicts; `report._count_tracked` uses it with a fallback to the old distinct-id count, fixing REPOS TRACKED showing a <=35-entry count instead of the true thousands-scale total.
- `_count_brand_new` now dedupes by repo id across `brand_new_weekly`/`brand_new_monthly` (intentional overlap for repos created 3-7 days ago), fixing a double-count.
- `TOP */DAY` label restored to `TOP ★/DAY` (U+2605).
- Markdown digest path (`sanitize_description`, `render_warming_note`, `render_entry`, `render_bucket`, `_SECTIONS`, `write_digest`) confirmed byte-for-byte untouched via `git diff HEAD~4 -- src/report.py` hunk inspection.

## Task Commits

Each task was committed atomically:

1. **Task 1: Thread the true tracked count from rank.compute_buckets to the stats strip (F2)** - `e39f226` (fix)
2. **Task 2: Dedupe BRAND NEW across the two brand-new buckets, fix the star glyph (F3, F4)** - `d2abd38` (fix)
3. **Task 3: Convert hero card and repo rows from flex to tables (F1, part 1)** - `3df0acb` (fix)
4. **Task 4: Convert bucket header, page wrapper and masthead to tables; add whole-document flex guard (F1, part 2)** - `eb97b3b` (fix)

_No TDD RED/GREEN split was used — each task was implemented and tested together per plan (tdd="true" markers in the plan describe behavior-first test authoring, not strict commit-per-phase RED/GREEN)._

## Files Created/Modified

- `src/rank.py` - `compute_buckets` adds `tracked_total = len(current["repos"])` to all four bucket dicts (never a top-level key); docstring updated.
- `src/report.py` - `_count_tracked` prefers `tracked_total`, falls back to distinct-id count; `_count_brand_new` dedupes by id; `TOP */DAY` -> `TOP ★/DAY`; `render_html_hero`, `render_html_row`, `render_html_bucket`, `render_html_digest` converted from flex divs to `<table role="presentation">` layouts.
- `tests/test_rank.py` - `_active_bucket`/`_inactive_bucket`/`_make_buckets` test helpers gain optional `tracked_total`; new tests for tracked_total on all buckets (zero-snapshot and populated cases) and the four-top-level-keys collector-iteration guard.
- `tests/test_report.py` - New/updated tests: `test_uses_tracked_total_when_present`, `test_repos_tracked_shows_true_total_not_bucket_count`, `test_repo_in_both_brand_new_buckets_counts_once`, `TOP ★/DAY` label assertions, `test_hero_has_no_flex_declarations`, `test_row_has_no_flex_declarations`, `test_hero_star_age_cell_is_right_aligned`, `test_render_html_digest_has_no_flex_declarations_anywhere`, `test_card_is_centered_by_table_cell_not_flex`; existing gap-regression guards (`test_row_stat_block_has_explicit_margin_not_gap`, `test_hero_stat_row_has_explicit_margin_not_gap`, masthead spacing, bucket header margin) rewritten for the new table markup while preserving their original intent.

## Decisions Made

- `tracked_total` lives inside each bucket dict, not as a new top-level key — verified against `src/collector.py:165`'s `for b in buckets.values() for e in b["entries"]` iteration contract, which would raise `TypeError` on an int top-level value.
- `align-items:baseline` (bucket header) has no table equivalent; `valign="middle"` accepted per plan (up to ~2px baseline drift, strictly better than Gmail's current full flex-collapse).
- `margin:0 auto` added to the 620px card div in addition to `align="center"` on its `<td>`, since not all email clients honor `align` alone for centering a fixed-width block child.

## Deviations from Plan

None - plan executed exactly as written. All four tasks, their file scopes, and their test additions match the plan's `<action>` blocks. The only interpretive choices were within the plan's own explicitly-permitted flexibility (e.g., "Flex-gap margins... become cell padding or stay as span margins — either is fine as long as the pixel value is preserved").

## Issues Encountered

None. All verification commands (full suite, targeted `-k` filters, the inline flex-token render check, and the `git diff HEAD~4` markdown-path guard) passed on first attempt for every task.

## User Setup Required

None - no external service configuration required. Per the plan's locked decision, no test email was sent and no browser screenshot was taken; correctness is established by unit tests plus the already-proven table pattern reused from quick tasks 260701-ibb/j1w/u16. The user confirms Gmail rendering on the next scheduled 13:00 UTC send.

## Next Phase Readiness

- The HTML digest's rendering path is now fully table-based and Gmail-safe; no further flex-conversion work is outstanding in `src/report.py`.
- REPOS TRACKED, BRAND NEW, and TOP ★/DAY stats are all correct; next scheduled run's email should be visually verified once by the user against real Gmail rendering (out of scope for this plan per locked user decision).

---
*Phase: quick-260725-u4s*
*Completed: 2026-07-25*

## Self-Check: PASSED

- FOUND: src/rank.py
- FOUND: src/report.py
- FOUND: tests/test_rank.py
- FOUND: tests/test_report.py
- FOUND: .planning/quick/260725-u4s-fix-email-digest-rendering-gmail-safe-ta/260725-u4s-SUMMARY.md
- FOUND commit: e39f226 (fix(report): show true tracked-repo count in HTML digest stats strip)
- FOUND commit: d2abd38 (fix(report): dedupe BRAND NEW count and restore star glyph in stats strip)
- FOUND commit: 3df0acb (fix(report): convert hero card and repo rows to Gmail-safe table layout)
- FOUND commit: eb97b3b (fix(report): convert digest wrapper, masthead and bucket headers to tables)
