---
phase: quick-260701-ibb
plan: 01
subsystem: report-rendering
tags: [html-email, gmail-compat, css, regression-tests]
requires: []
provides:
  - "Gap-free HTML email renderers (hero, row, bucket, masthead) compatible with Gmail webmail"
affects:
  - src/report.py
  - tests/test_report.py
tech-stack:
  added: []
  patterns:
    - "CSS box-model margin (not flexbox gap) for spacing in HTML-email renderers, since Gmail webmail strips `gap:` entirely"
key-files:
  created: []
  modified:
    - src/report.py
    - tests/test_report.py
decisions:
  - "Gap removed (not duplicated) at all 6 locations to avoid double-spacing in gap-supporting clients"
  - "Masthead date span no longer right-aligns once flex space-between drops away — accepted tradeoff per plan non-goals"
metrics:
  duration: "~25 min"
  completed: "2026-07-01"
---

# Phase quick-260701-ibb Plan 01: Fix Gmail rendering bugs in HTML digest Summary

Replaced all 6 flexbox `gap:Npx` spacing declarations in the HTML email
renderers (`src/report.py`) with equivalent box-model `margin` on the
adjacent child element, since Gmail's webmail client silently drops CSS
`gap` — causing the masthead issue-no/date, bucket header kicker/count, and
row stat-block/description to visually concatenate.

## What Was Built

- `render_html_hero`: stat row `gap:7px` removed; `margin-left:7px` added to
  the "stars / day" span.
- `render_html_row`: outer `<a>` `gap:16px` removed, `margin-right:16px`
  added to the 78px stat block; name/badge row `gap:9px` removed,
  `margin-left:9px` added to the NEW badge span (inert when badge absent);
  bar/stars row `gap:12px` removed, `margin-left:12px` added to the
  star-count span.
- `render_html_bucket`: header row `gap:12px` removed; `margin-right:12px`
  added to the kicker span AND `margin-left:12px` added to the count_label
  span (both sides of the invisible `flex:1` rule needed their own margin).
- `render_html_digest`: masthead date span given `margin-left:16px` inline
  style so it no longer touches the issue-no span (accepted tradeoff: date
  no longer right-aligns without flex `space-between`).
- `tests/test_report.py::TestHtmlDigest`: 5 new location-scoped regression
  tests (masthead, bucket header, row stat block, hero stat row, plus a
  whole-document `gap:` guard) that fail on pre-fix code and pass post-fix.

Markdown-path renderers (`sanitize_description`, `render_entry`,
`render_bucket`, `write_digest`) were not touched — out of scope per plan.

## TDD Gate Compliance

- RED: `8e0a691` — 4 location-scoped tests added, confirmed failing against
  pre-fix code (verified via `pytest -k "gap or margin or masthead..."`,
  4 failed / 1 passed).
- GREEN: `5cca881` — all 6 gap declarations replaced with margins; all 4 RED
  tests now pass; `grep -n "gap:" src/report.py` returns no matches.
- Follow-up guard test: `368083c` — whole-document `gap:` guard test added
  (passes immediately since the fix already landed in the GREEN commit —
  this is a lock-in guard, not a new RED/GREEN cycle).
- Plan-fidelity follow-up: `4bd432a` — added the second half of plan item 1's
  masthead assertion (explicit "no bare `</span><span>` adjacency" check,
  in addition to the positive margin-styling assertion already in place).

All gate commits present and in the correct order.

## Verification

- `uv run pytest tests/test_report.py::TestHtmlDigest -v` — 26/26 passed.
- `grep -n "gap:" src/report.py` — no matches (all 6 locations fixed, none
  duplicated alongside margin).
- Full suite (`PYTHONUTF8=1 uv run pytest -q`): 265 passed, 1 pre-existing
  failure (see Deferred Issues below), 2 warnings (both pre-existing,
  unrelated to this change).
- **Success criterion "full pytest suite green" is NOT fully met** — see
  Deferred Issues for the one pre-existing, out-of-scope failure and the
  proof that this plan did not touch its code path.
- Sample render (`render_html_digest` via throwaway `uv run python -c`):
  masthead confirmed as `<span>Issue No. 3</span><span style="margin-left:16px;">Sun · 28 Jun 2026</span>` —
  two visually separated spans, no concatenation. Whole-document `"gap:" in html_out` == `False`.

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written (all 6 enumerated locations fixed,
margins added not duplicated, markdown path untouched, masthead
right-alignment tradeoff accepted as specified).

### Deferred Issues (out of scope, not fixed)

**1. Pre-existing failing test unrelated to this plan — full-suite success criterion not met**
- **File:** `tests/test_search.py::TestDiscoverRepos::test_monthly_cohort_preserved_when_30d_over_cap`
- **Found during:** Full-suite verification after Task 2.
- **Proof this plan did not cause it:** `git diff 7f85b9f HEAD --stat` (base
  commit → tip of this plan's work) shows only `src/report.py` and
  `tests/test_report.py` changed (24 lines changed / 90 lines added,
  2 files total) — this plan's commits never touched `src/search.py` or
  `tests/test_search.py`, so the failure is provably identical to the
  pre-plan base state, not a regression introduced here. (An earlier
  stash-based check was insufficient — it ran after `src/report.py` was
  already committed and so did not isolate this plan's changes; the
  diff-stat check above is the definitive proof.)
- **Why deferred:** Lives entirely in `src/search.py`/`tests/test_search.py`,
  explicitly out of scope for this plan (non-goals list `src/search.py` and
  prior quick-task code as untouched). Fixing it would violate the plan's
  scope boundary and the CLAUDE.md "authorized additive changes only" rule.
- **Impact:** The plan's stated success criterion "Full pytest suite passes"
  and verification bullet "uv run pytest — full suite green" are **not
  fully satisfied** (265 passed / 1 failed). This is a pre-existing,
  out-of-scope condition, not introduced by this plan — orchestrator/user
  should decide whether to accept as-is or dispatch a separate fix task for
  `test_search.py`.
- **Action:** Not fixed. Left for a separate quick task or debug session.

## Known Stubs

None.

## Threat Flags

None — no new trust boundary introduced; only CSS spacing tokens changed.
Existing `_esc()` / `html.escape(..., quote=True)` sanitization on all
interpolated values is untouched (confirmed by the unchanged, still-passing
`test_description_script_tag_never_raw_in_output`,
`test_full_name_img_payload_escaped`, `test_html_url_attribute_breakout_escaped`,
and `test_description_newline_and_link_injection_neutralized` tests).

## Self-Check: PASSED

- FOUND: src/report.py (modified, gap: removed, margins added — verified via grep)
- FOUND: tests/test_report.py (modified, 5 new tests added + 1 assertion added to an existing test)
- FOUND commit 8e0a691 (test: RED)
- FOUND commit 5cca881 (feat: GREEN)
- FOUND commit 368083c (test: guard)
- FOUND commit 4bd432a (test: plan-fidelity follow-up)
