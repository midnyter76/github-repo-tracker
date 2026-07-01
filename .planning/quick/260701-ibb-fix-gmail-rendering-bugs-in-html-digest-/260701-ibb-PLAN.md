---
phase: quick-260701-ibb
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/report.py
  - tests/test_report.py
autonomous: true
requirements: [QUICK-260701-ibb]

must_haves:
  truths:
    - "Masthead issue-no and date do not concatenate (explicit spacing between them)"
    - "Bucket header kicker and repo-count do not concatenate (explicit spacing both sides of the rule)"
    - "Row stat block and description column are separated by an explicit margin, not only a flex gap"
    - "No email-HTML element relies solely on `gap:` for spacing — every gap is replaced by an equivalent margin"
    - "Browser render stays visually equivalent (gap removed AND margin added — never both, no double-spacing)"
    - "Full pytest suite passes"
  artifacts:
    - path: "src/report.py"
      provides: "gap-free HTML email renderers (hero, row, bucket, masthead)"
      contains: "margin-"
    - path: "tests/test_report.py"
      provides: "Location-scoped regression assertions in TestHtmlDigest"
      contains: "margin"
  key_links:
    - from: "tests/test_report.py::TestHtmlDigest"
      to: "src/report.py render_html_* functions"
      via: "location-scoped regex on rendered HTML"
      pattern: "Issue No\\. .*margin"
---

<objective>
Fix Gmail rendering bugs in the HTML email digest caused by reliance on CSS
flexbox `gap` for spacing, which Gmail's webmail client drops entirely. Labels
concatenate ("ISSUE NO. 3WED..."), bucket headers run together
("BRAND NEW · WEEKLY10 repos"), and row stat blocks overlap the description.

Root fix: in the HTML-email render functions in `src/report.py`, REMOVE every
`gap:Npx` declaration and add an equivalent `margin` on the appropriate child
element. This is the box-model property Gmail/Outlook/Apple Mail respect, and it
degrades safely without flexbox. Preserve the existing numeric spacing values.

Purpose: The daily digest email is the product's only delivery surface — it must
render legibly in Gmail webmail (the confirmed-broken client).
Output: gap-free HTML renderers + location-scoped regression tests.

Non-goals (explicit — do NOT touch):
- The markdown path (`sanitize_description`, `render_entry`, `render_bucket`,
  `write_digest`) — working and out of scope.
- A full table-based layout rewrite — bigger change, out of scope.
- `src/report.py:534` `justify-content:center` (no gap, not an enumerated bug).
- `src/collector.py`, `src/prune.py`, prior quick-task 260630-wif code.
- The `justify-content:space-between` right-alignment on the masthead: once flex
  is dropped, the date no longer right-aligns. Per the no-table constraint this
  right-alignment is an ACCEPTED tradeoff — do not float/table it back.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md
@src/report.py
@tests/test_report.py

<interfaces>
<!-- Test helpers already in tests/test_report.py — reuse, do not redefine. -->
_entry(...) -> dict            # full_name="owner/cool-repo", velocity_per_day=12.5
_make_buckets(...) -> dict     # complete four-bucket dict
_now() -> datetime            # 2026-06-28 12:00 UTC  → date_label "Sun · 28 Jun 2026"
render_html_digest(buckets, markers, now) -> str
render_html_hero(top_mover, bucket_title, now) -> str
render_html_row(entry, markers, bucket_max_vel, now) -> str
render_html_bucket(bucket_key, kicker, title, bucket, markers, now) -> str
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Replace all flexbox gap spacing with margins in HTML email renderers</name>
  <files>src/report.py</files>
  <behavior>
    For each of the 6 locations below, the rendered HTML must (a) no longer
    contain the `gap:Npx` declaration for that element, and (b) carry an
    explicit equivalent `margin` on a child so the browser render is unchanged
    while Gmail gets real spacing. Every child that had a gap-derived neighbor
    must be reachable via a location-scoped regex (Task 2 asserts these).
  </behavior>
  <action>
Edit ONLY the HTML-email render functions. For EACH location: delete the
`gap:Npx` token from the flex parent's style AND add the equivalent margin on the
named child. Do NOT keep both gap and margin (gap-supporting clients would render
gap+margin = double spacing — a regression in the currently-working browser view).

1. `render_html_hero` stat row (line ~367-370):
   - Remove `gap:7px` from the flex `<div>` (~367).
   - Add `margin-left:7px;` to the "stars / day" `<span>` (~369).
   - Leave the third span's `margin-left:auto` as-is (harmless without flex).

2. `render_html_row` outer `<a>` (line ~409-410):
   - Remove `gap:16px` from the `<a>` style (~409).
   - Add `margin-right:16px;` to the 78px stat-block `<div>` (~410).

3. `render_html_row` name/badge row (line ~415-417):
   - Remove `gap:9px` from the flex `<div>` (~415).
   - Add `margin-left:9px;` to the `new_badge` span's inline style (the
     hardcoded `new_badge` string, ~402-404). When the badge is empty ("") this
     is inert; when present it restores the 9px separation.

4. `render_html_row` bar/stars row (line ~420-424):
   - Remove `gap:12px` from the flex `<div>` (~420).
   - Add `margin-left:12px;` to the star-count `<span>` (~424).

5. `render_html_bucket` header row (line ~478-481) — THREE children with a
   `flex:1` invisible rule between kicker and count; a single margin only
   reproduces ONE of the two gaps and leaves a browser regression on the other
   side. Add BOTH:
   - Remove `gap:12px` from the flex `<div>` (~478).
   - Add `margin-right:12px;` to the kicker `<span>` (~479).
   - Add `margin-left:12px;` to the count_label `<span>` (~481).

6. `render_html_digest` masthead (line ~537-538) — `space-between` with two
   directly-adjacent bare `<span>`s that concatenate ("Issue No. 3" + date):
   - Add `margin-left:16px;` (as an inline `style="..."`) to the date `<span>`
     so it no longer touches the issue-no span. The issue-no span may stay bare.
   - Accepted tradeoff: the date will no longer right-align (see non-goals).

Preserve every other style property, class of design, and the numeric values.
Do not alter any markdown-path function.
  </action>
  <verify>
    <automated>uv run pytest tests/test_report.py::TestHtmlDigest -x</automated>
  </verify>
  <done>All 6 `gap:Npx` tokens removed from HTML render functions; equivalent margins added on the named children; no markdown-path change.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add location-scoped regression tests and verify sample output</name>
  <files>tests/test_report.py</files>
  <behavior>
    Each assertion must be scoped to its specific location so it FAILS on the
    pre-fix code and PASSES post-fix. A bare "margin is present somewhere" check
    is too weak — `margin-top`/`margin-left:auto` already exist file-wide.
  </behavior>
  <action>
Add tests to the existing `TestHtmlDigest` class (reuse `_make_buckets`,
`_entry`, `_now`, `import re`). Each must be location-scoped:

1. Masthead: render `render_html_digest(_make_buckets(), markers={}, now=_now())`
   and assert `re.search(r'Issue No\. \d+</span>\s*<span style="[^"]*margin', result)`
   — pre-fix the date span is a bare `<span>` (no style), so this fails RED.
   Also assert the literal concatenation signature is gone in the masthead
   region: no bare `</span><span>` adjacency between issue-no and the date
   (assert the styled-span form above is what appears).

2. Bucket header: render a bucket via `render_html_bucket("brand_new_weekly",
   "Brand New · Weekly", "Brand New This Week", _active_bucket([_entry()]), {}, _now())`
   and assert the kicker span carries `margin-right:12px` AND the count_label
   span carries `margin-left:12px`, and that `gap:12px` is NOT in the header row.

3. Row stat block: render `render_html_row(_entry(), {}, 1.0, _now())` and assert
   the 78px stat block div carries `margin-right:16px` and the `<a>` no longer
   contains `gap:16px`.

4. Hero stat row: render `render_html_hero(_entry(), "Brand New This Week", _now())`
   and assert the "stars / day" span carries `margin-left:7px` and the stat row
   div no longer contains `gap:7px`.

5. Guard: assert `render_html_digest(_make_buckets(), {}, _now())` output contains
   no `gap:` substring at all (whole-document check — catches any missed gap).

After tests pass, run the full suite, then regenerate a sample by calling
`render_html_digest(_make_buckets(), {}, _now())` in a throwaway `uv run python -c`
snippet and visually confirm the masthead shows "Issue No. N" and the date as
two separated spans (no `}}{{`/`</span><span>` concatenation).
  </action>
  <verify>
    <automated>uv run pytest</automated>
  </verify>
  <done>New location-scoped tests pass; whole-document `gap:` guard passes; full suite green; sample HTML source shows separated masthead spans.</done>
</task>

</tasks>

<threat_model>
No new trust boundary. Description/full_name/html_url remain attacker-influenceable
GitHub text, but this change only alters CSS spacing tokens — the existing
`_esc()` / `html.escape(..., quote=True)` sanitization on all interpolated values
is untouched. No STRIDE disposition change; existing T-TL4-01/02/03 mitigations
remain in force (verified by the unchanged escaping tests in TestHtmlDigest).
</threat_model>

<verification>
- `uv run pytest` — full suite green (workspace CLAUDE.md: full suite before commit).
- No `gap:` substring remains in `render_html_digest` output.
- Existing escaping/security tests in TestHtmlDigest still pass (no regression).
- Markdown-path tests (TestWriteDigest, TestRenderEntry) unchanged and passing.
</verification>

<success_criteria>
- All 6 flexbox `gap` declarations in the HTML email renderers replaced by
  equivalent margins on children (gap removed, not duplicated).
- Location-scoped regression tests fail on pre-fix code, pass after fix.
- Full pytest suite green.
- Masthead, bucket headers, and rows render with real spacing in a gap-free
  (Gmail-equivalent) rendering context.
</success_criteria>

<output>
After completion, create `.planning/quick/260701-ibb-fix-gmail-rendering-bugs-in-html-digest-/260701-ibb-SUMMARY.md`
</output>
