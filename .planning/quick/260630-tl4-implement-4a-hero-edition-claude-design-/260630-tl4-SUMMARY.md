---
phase: quick-260630-tl4
plan: 01
subsystem: reporting
tags: [html-email, mime-multipart, github-repo-tracker, xss-escaping]

# Dependency graph
requires:
  - phase: 02-reporting
    provides: buckets/markers data contract (rank.compute_buckets, seen.classify_and_update),
      existing write_digest markdown pipeline
provides:
  - "render_html_digest/write_html_digest — 4a hero-edition inline-CSS HTML email renderer"
  - "select_top_mover — global-max velocity_per_day entry across all buckets, with bucket title"
  - "collector.run() writes reports/YYYY-MM-DD.html alongside the existing .md"
  - "daily.yml sends multipart/alternative email (markdown + HTML parts)"
affects: [email-delivery, report-rendering]

# Tech tracking
tech-stack:
  added: []  # stdlib only (html, math) — no new dependencies
  patterns:
    - "Parallel renderer pattern: HTML renderer added alongside markdown renderer without
      touching the markdown code path (write_digest untouched)"
    - "Two-stage escaping for descriptions: sanitize_description() (markdown-injection) then
      html.escape(..., quote=True) (HTML/attribute injection) — _esc() helper"
    - "Direct html.escape(..., quote=True) for full_name/html_url (not routed through
      sanitize_description, since that function strips rather than escapes)"

key-files:
  created: []
  modified:
    - src/report.py
    - tests/test_report.py
    - src/collector.py
    - tests/test_collector.py
    - .github/workflows/daily.yml

key-decisions:
  - "sanitize_description() strips (not escapes) < > chars — description-path XSS test
    asserts no-raw-tag + payload-neutralized, not the literal '&lt;script&gt;' substring
    the plan bullet described (see Deviations)"
  - "full_name/html_url escaped directly via html.escape(quote=True), bypassing
    sanitize_description entirely, per design spec"
  - "bucket_max_vel computed only inside the entries-present branch of render_html_bucket
    to avoid max(1.0) crashing on an empty iterable"

requirements-completed: []

# Metrics
duration: ~35min
completed: 2026-06-30
---

# Quick Task 260630-tl4: 4a Hero-Edition HTML Email Digest Summary

**Self-contained inline-CSS HTML renderer ("The Dispatch" dark editorial design with a
fastest-mover hero card) added alongside the untouched markdown digest, wired into the
collector, and sent via multipart/alternative email.**

## Performance

- **Duration:** ~35 min
- **Tasks:** 3/3 completed
- **Files modified:** 5 (src/report.py, tests/test_report.py, src/collector.py,
  tests/test_collector.py, .github/workflows/daily.yml)

## Accomplishments
- `render_html_digest`/`write_html_digest` reproduce the 4a mockup verbatim (masthead,
  fastest-mover hero, four dark/serif bucket sections) as a self-contained HTML string —
  inline CSS only, Google Fonts `<link>`, no JavaScript.
- `select_top_mover` finds the global-max `velocity_per_day` entry across all four buckets
  without a fragile identity back-search, carrying the bucket title through the flatten.
- Every attacker-influenceable string (description, full_name, html_url) is sanitized
  and/or HTML-escaped before reaching the output; explicit security tests cover
  T-TL4-01/02/03 (script-tag description, `<img>` full_name, href attribute breakout).
- `collector.run()` now writes `reports/YYYY-MM-DD.html` immediately after the existing
  `.md` write, before `save_seen_fn` (preserves D-10 ordering); `write_html_digest` is a
  keyword-injectable dependency stubbed at all 8 `run()` call sites in tests.
- `.github/workflows/daily.yml` email step now sends `multipart/alternative`: the existing
  markdown body as `text/plain` (attached first), the new HTML digest as `text/html`
  (attached last, with a graceful skip if the `.html` file is missing).
- Markdown path (`sanitize_description`, `render_warming_note`, `render_entry`,
  `render_bucket`, `write_digest`) left byte-for-byte unmodified — verified by re-running
  the full pre-existing `tests/test_report.py` suite unchanged (all 40 original tests pass).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the 4a HTML renderer + writer to src/report.py** - `49dbe7f` (feat)
2. **Task 2: Add security + logic tests for the HTML renderer** - `8f480d8` (test)
3. **Task 3: Wire write_html_digest into collector + multipart email** - `00a8800` (feat)

**Plan metadata:** committed separately by the orchestrator (docs commit, not included here).

## Files Created/Modified
- `src/report.py` - Added `_HTML_SECTIONS`, `_jsround`, `_vel_fmt`, `_stars_full`,
  `_age_str`, `_bar_pct`, `_bar_fill`, `_esc`, `select_top_mover`, `render_html_hero`,
  `render_html_row`, `render_html_bucket`, `render_html_digest`, `write_html_digest`.
  Markdown functions untouched.
- `tests/test_report.py` - New `class TestHtmlDigest` (22 tests): security (description
  script-tag, full_name `<img>` payload in row + hero, href attribute breakout, newline/
  link injection), logic/formatting (`_stars_full`, `_vel_fmt`, `_age_str`, `_jsround`,
  `_bar_pct`, `_bar_fill`), `select_top_mover` (global max + tie/bucket-title carry,
  all-empty), `render_html_digest` (masthead/titles/hero/no-script, all-empty placeholder,
  inactive-bucket warming message), `write_html_digest` (file creation, no stray `.md`,
  reports_dir auto-creation).
- `src/collector.py` - `write_html_digest=report.write_html_digest` added as an injectable
  keyword dependency to `run()`; called right after `write_digest` and before
  `save_seen_fn`. Docstring updated.
- `tests/test_collector.py` - `write_html_digest=` stub added at all 8 `run()` call sites
  (TestRun x4, TestPhase2Wiring x3, TestRunPhase3CallOrder x1); new assertions for
  call-once (Phase 2 wiring) and call-order (after write_digest, before save_seen); 4 new
  `TestWorkflowYaml` tests for the multipart/HTML email assertions.
- `.github/workflows/daily.yml` - Email step rebuilt to use `email.mime.multipart.
  MIMEMultipart("alternative")` + `email.mime.text.MIMEText`, attaching the markdown body
  as `text/plain` first and (if present) `reports/{today}.html` as `text/html` last.

## Decisions Made
- **Description-path XSS test wording deviates from the literal plan bullet.** The plan's
  Task 1 `<behavior>` said a `<script>alert(1)</script>` description should "appear
  HTML-escaped (`&lt;script&gt;`)". The plan's own locked `_esc()` definition —
  `html.escape(sanitize_description(text), quote=True)` — makes this impossible: the
  existing (untouched) `sanitize_description()` already **strips** `<`/`>` chars entirely
  (step 5 of its documented sanitization order), so by the time `html.escape` runs there
  are no angle brackets left to escape. Verified empirically:
  `report._esc('<script>alert(1)</script>')` → `'scriptalert(1)/script'` (no brackets at
  all — a stronger security guarantee than mere escaping, not a weaker one). Since
  `sanitize_description` and `_esc()`'s formula are both locked by the plan (do-not-modify
  markdown path; `_esc` construction specified verbatim in Task 1's `<action>`), the test
  written in Task 2 asserts the true, achievable, and stronger guarantee instead: no raw
  `<script` tag ever appears (`assert "<script" not in result`) AND the payload text still
  flows through neutralized (`assert "alert(1)" in result`) — proving the entry wasn't
  simply dropped, just safely stripped. The `full_name`/`html_url` paths (which do NOT go
  through `sanitize_description`) match the plan's literal expectation exactly — those
  tests assert the escaped form (`&lt;img`, `&quot;`) is present, as specified.
- `bucket_max_vel = max(1.0, *velocities)` is computed only inside `render_html_bucket`'s
  entries-present branch, never unconditionally, since `max(1.0)` on an empty spread
  raises `TypeError` — an empty/inactive bucket renders its `emptyMsg` block instead and
  never reaches that line.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test assertion adjusted for description-path XSS test (see Decisions above)**
- **Found during:** Task 2 (writing TestHtmlDigest)
- **Issue:** Plan's Task 1 `<behavior>` bullet expected a `<script>` description to render
  as the literal substring `&lt;script&gt;`, but the plan's own locked `_esc()` formula
  (built on the existing, unmodified `sanitize_description()`, which strips rather than
  escapes angle brackets) makes that substring unreachable.
- **Fix:** Implemented `_esc()` exactly as locked in the plan. Wrote the corresponding
  Task 2 test to assert the actual (stronger) security property — no raw tag, payload
  neutralized — instead of the impossible literal substring. No production code changed
  to work around this; it was purely a test-assertion correction to match verified,
  intentional (and stricter) behavior.
- **Files modified:** tests/test_report.py
- **Verification:** `uv run pytest tests/test_report.py::TestHtmlDigest -q` passes (22/22);
  full `tests/test_report.py` suite passes (62/62), including all 40 pre-existing markdown
  tests unchanged.
- **Committed in:** 8f480d8 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug-class test-assertion correction, Rule 1)
**Impact on plan:** No production-code scope creep; the fix only corrected a test
assertion to match the plan's own locked implementation formula, and the resulting
security guarantee is strictly stronger than what the plan's literal wording described.

## Issues Encountered
- Pre-existing failing test discovered during full-suite verification:
  `tests/test_search.py::TestDiscoverRepos::test_monthly_cohort_preserved_when_30d_over_cap`.
  Confirmed pre-existing by reproducing it with this plan's changes stashed (clean base
  commit `9d8208a`) — identical failure. `src/search.py`/`tests/test_search.py` are not in
  this plan's `files_modified` scope, so per the scope-boundary rule this was NOT fixed;
  logged to `.planning/quick/260630-tl4-implement-4a-hero-edition-claude-design-/deferred-items.md`
  for separate follow-up. All other tests pass: `248 passed, 1 deselected`.

## Known Stubs
None — every code path is wired to real data; no hardcoded empty/placeholder values were
introduced. The hero placeholder ("No qualifying repos yet — the radar is still warming
up.") is an intentional, tested fallback for the genuine all-buckets-empty state, not a stub.

## Threat Flags

None beyond what the plan's own `<threat_model>` already covers (T-TL4-01/02/03 mitigated
via `_esc()`/`html.escape(quote=True)`, T-TL4-04 accepted per existing secret-handling
pattern). No new network endpoints, auth paths, or schema changes were introduced.

## User Setup Required
None - no external service configuration required. `GMAIL_USER`/`GMAIL_APP_PASSWORD`
secrets already existed prior to this task; the email step's MIME construction changed,
not its credential sourcing.

## Next Phase Readiness
- The HTML digest is fully wired end-to-end: collector writes it, workflow emails it.
- First live run will confirm the rendered email in an actual Gmail client (fonts/dark
  background rendering can vary by client — not automatable, and out of scope per the
  plan's `<verification>` block, which only requires the automated test suite).
- Pre-existing `test_search.py` failure (see Issues Encountered) is a candidate for a
  follow-up `/gsd-debug` session; unrelated to this task's deliverable.

---
*Phase: quick-260630-tl4*
*Completed: 2026-06-30*

## Self-Check: PASSED

- FOUND: commit 49dbe7f (Task 1)
- FOUND: commit 8f480d8 (Task 2)
- FOUND: commit 00a8800 (Task 3)
- FOUND: src/report.py
- FOUND: tests/test_report.py
- FOUND: src/collector.py
- FOUND: tests/test_collector.py
- FOUND: .github/workflows/daily.yml
- FOUND: .planning/quick/260630-tl4-implement-4a-hero-edition-claude-design-/260630-tl4-SUMMARY.md
