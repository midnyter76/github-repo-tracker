---
phase: quick-260725-u4s
verified: 2026-07-25T22:30:00Z
status: passed
score: 8/8 must-haves verified
overrides_applied: 0
---

# Quick Task 260725-u4s: Fix Email Digest Rendering (Gmail-Safe Tables) Verification Report

**Task Goal:** Fix email digest rendering: gmail-safe tables, true tracked count, dedupe brand new, star glyph
**Verified:** 2026-07-25T22:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Method

Not a SUMMARY-trust exercise. Rendered the actual production digest via
`rank.compute_buckets(now=...)` + `report.render_html_digest(...)` against the
real `data/snapshots/2026-07-24.json` (2211 repos) + `data/metadata.json`, then:

1. Scanned the real rendered HTML string (not source code) for flex/grid/gap tokens.
2. Checked out baseline commit `fe99446` in a disposable `git worktree`, rendered the
   same input data with the pre-fix code, and diffed style-attribute (prop,value)
   pairs plus stripped-tag text content against the HEAD rendering.
3. Diffed `write_digest`'s markdown output (baseline vs HEAD) byte-for-byte via
   `diff -q`.
4. Ran `git diff fe99446 -- src/report.py src/rank.py src/collector.py data/
   .github/workflows/daily.yml` to inspect exact hunk boundaries.
5. Ran the full pytest suite.

All scratch scripts/output lived under the session scratchpad; the `git worktree`
was removed afterward; nothing under `data/` was touched.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Rendered HTML digest contains zero flexbox declarations | VERIFIED | Real render of 2211-repo dataset: `display:flex`→0, `justify-content`→0, `align-items`→0, `margin-left:auto`→0, `display:grid`→0, `gap:`→0, `flex:1`→0, `flex-shrink`→0. Two `display:flex`/`display:grid`/`gap:` substrings exist only in `src/report.py` docstrings (lines 553, 606) — confirmed prose-only by re-reading surrounding text and by their absence from the actual rendered output. |
| 2 | Hero stats line renders one horizontal table row, star/age cell right-aligned | VERIFIED | `render_html_hero` (report.py:378-384): one `<table role="presentation">` row, 3 `<td>`s, third carries `align="right"`. |
| 3 | Repo row renders 78px velocity gutter + name/desc/bar as two cells of one table | VERIFIED | `render_html_row` (report.py:423-449): `<td width="78" ... align="right" style="width:78px;...">` + `<td valign="top">`; nested bar table has `<td width="1" align="right" ...>★ {stars} · {age}</td>`. |
| 4 | REPOS TRACKED shows true tracked total (thousands), not <=35 rendered-bucket count | VERIFIED | Real render: `2211` present in output (matches `len(data/snapshots/2026-07-24.json repos)` == 2211). Baseline render of same data showed `23` (bucket-entry-count artifact) at the same stats-strip position — confirmed by structural diff. |
| 5 | `compute_buckets` returns exactly four top-level keys; collector.py iteration unbroken | VERIFIED | `set(compute_buckets(now=...).keys())` == `{brand_new_weekly, brand_new_monthly, spike_24h, velocity_30d}` on real data. `[e["id"] for b in buckets.values() for e in b["entries"]]` executed without error (35 ids). `git diff fe99446 -- src/collector.py` is empty (zero changes). |
| 6 | Repo in both brand_new_weekly and brand_new_monthly contributes 1, not 2, to BRAND NEW | VERIFIED | `_count_brand_new` (report.py:532-545) builds a `set` of ids across both buckets before counting. Real-data render: BRAND NEW dropped from baseline's `15` to HEAD's `14` for the same input (the expected direction of an overlap-dedupe fix, confirmed via text-content diff). |
| 7 | Third stats-strip label reads "TOP ★/DAY" with U+2605 | VERIFIED | Real render contains `TOP ★/DAY` (`True`); `TOP */DAY` absent (`False`). Text-diff vs baseline shows the label changed from `TOP */DAY` to `TOP ★/DAY` with no other change at that position. |
| 8 | Markdown digest output byte-for-byte unchanged | VERIFIED | `write_digest` invoked with identical buckets/markers/now against both baseline (fe99446, via worktree) and HEAD code; `diff -q` on the two `.md` outputs produced zero differences ("MD IDENTICAL"). `git diff fe99446 -- src/report.py` hunks touch only `render_html_hero`, `render_html_row`, `render_html_bucket`, `_count_tracked`/`_count_brand_new`/`_LEADER_KICKERS` region, `render_html_leaders`, `render_html_digest` — zero hunks in `sanitize_description`, `render_warming_note`, `render_entry`, `render_bucket`, `write_digest`, `_SECTIONS`. |

**Score:** 8/8 truths verified

### Visual Fidelity Check (task-specific requirement 2)

Diffed the real rendered HTML (baseline `fe99446` vs HEAD, same 2211-repo input)
at three levels:

1. **Style-attribute (property, value) pair counts** for color/font-family/font-size/
   font-weight/letter-spacing/line-height/border/border-radius/box-shadow/background/
   text-transform/white-space/width — 124 distinct pairs compared, 11 mismatched.
   Every mismatch traces to a plan-documented, layout-mechanism-only change:
   - `background:#d8dadc` +1: new outer `<table style="background:#d8dadc;">` wrapper
     duplicates the existing `<body>` background for email-client compatibility
     (plan Task 4, explicit instruction).
   - `color:#5b6573` / `font-family:'IBM Plex Mono', monospace` / `font-size:11px` /
     `letter-spacing:0.14em` / `text-transform:uppercase` all +1: masthead date/issue
     spans split into two `<td>`s, each now carries the full existing declaration
     string (plan Task 4, explicit instruction: "put the full existing declaration
     string on BOTH cells").
   - `font-size:0` / `line-height:0` 0→4: added only to the empty bucket-header rule
     `<div>` to stop email clients inflating it (plan Task 4, explicit instruction).
   - `text-align:right` 35→0, offset by `align="right"` HTML attribute 0→76: the
     documented mechanism swap (style property → table attribute).
   - `white-space:nowrap` 35→45: added to new table cells to preserve one-line
     layout that flex previously guaranteed (plan-documented per-cell additions).
   - `width:100%` 5→39: `flex:1` on ~34 bar-container divs replaced 1:1 with
     `width:100%` (plan Task 3, explicit instruction) — count delta matches repo-row
     count.
2. **Stripped-tag text content diff** (all HTML tags removed, whitespace collapsed):
   exactly 3 diff blocks, all expected stat/glyph fixes — `23`→`2211` (REPOS TRACKED),
   `15`→`14` (BRAND NEW dedupe), `TOP */DAY`→`TOP ★/DAY`. No other visible text changed
   anywhere in the ~87KB document.

No color, font, unintended spacing, or content change found beyond the four
in-scope fixes.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/report.py` | Table-based hero/row/bucket/digest renderers; tracked_total-aware `_count_tracked`; set-based `_count_brand_new`; ★ glyph | VERIFIED | All four functions converted per plan; verified by direct code read and real-render diff. |
| `src/rank.py` | `tracked_total` on each of the four bucket dicts | VERIFIED | `compute_buckets` line 292/401/408/415/~423: `tracked_total = len(current["repos"])`, present on all four returned dicts. |
| `tests/test_report.py` | Updated HTML markup assertions + new tests | VERIFIED | New tests exist and pass individually (6/6 targeted new tests green). |
| `tests/test_rank.py` | `tracked_total` contract test + four-key guard | VERIFIED | Full suite includes these; 349 passed overall. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `src/rank.py compute_buckets` | `src/report.py _count_tracked` | `tracked_total` key on each bucket dict | WIRED | `_count_tracked` reads `buckets["brand_new_weekly"].get("tracked_total")`; real render returns `2211`. |
| `src/report.py render_html_leaders` | `_render_strip_cell REPOS TRACKED` | `str(_count_tracked(buckets))` | WIRED | Confirmed `2211` appears in rendered strip cell adjacent to "REPOS TRACKED" text. |
| `src/collector.py:165` | `buckets.values()` | unchanged four-key iteration | WIRED / UNCHANGED | `git diff fe99446 -- src/collector.py` empty; live iteration executed without error against real `compute_buckets` output. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Real digest renders with zero flex tokens | Render `data/snapshots/2026-07-24.json` + `data/metadata.json` through `rank.compute_buckets` → `report.render_html_digest`, grep 8 flex/grid/gap tokens | All 8 tokens count 0 | PASS |
| Markdown path byte-identical | `write_digest` at fe99446 vs HEAD, same buckets/markers/now, `diff -q` | "MD IDENTICAL" | PASS |
| Collector iteration contract | `[e["id"] for b in buckets.values() for e in b["entries"]]` on real data | 35 ids, no error | PASS |
| Four-key bucket contract | `set(buckets.keys())` | `{brand_new_weekly, brand_new_monthly, spike_24h, velocity_30d}` | PASS |
| Full test suite | `pytest -q` | 349 passed, 2 warnings (pre-existing, unrelated) | PASS |
| `data/` and workflow untouched | `git diff fe99446 -- data/ .github/workflows/daily.yml` | empty | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| F1-gmail-flex | 260725-u4s-PLAN.md | Convert flex layouts to Gmail-safe tables | SATISFIED | Zero flex/grid/gap tokens in real rendered output; visual fidelity preserved. |
| F2-tracked-count | 260725-u4s-PLAN.md | REPOS TRACKED shows true count | SATISFIED | `2211` renders for the 2026-07-24 dataset (matches actual snapshot repo count). |
| F3-brand-new-dedupe | 260725-u4s-PLAN.md | Overlap dedup for BRAND NEW | SATISFIED | Set-based `_count_brand_new`; real-data count dropped from 15 (double-counted) to 14 (deduped). |
| F4-star-glyph | 260725-u4s-PLAN.md | Restore ★ (U+2605) in TOP */DAY label | SATISFIED | `TOP ★/DAY` renders; `TOP */DAY` gone. |

No orphaned requirements — all four IDs declared in the plan's `requirements` field
match REQUIREMENTS scope for this quick task (ad hoc quick-task requirements, not
tracked in a milestone REQUIREMENTS.md).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| src/report.py | 553, 606 | `display:flex`/`display:grid`/`gap:` substrings in docstrings | Info | Prose only — describes what the code no longer does / explicitly avoids. Confirmed never reaches rendered output (0 occurrences of these tokens in the real 87KB rendered digest). Not a defect. |

No blockers found. No stub patterns, no empty-return handlers, no TODO/FIXME/placeholder
comments in the modified files.

### Human Verification Required

None required for goal achievement — the plan explicitly locked "no test email
sent, no browser screenshot taken" as an out-of-scope decision, with real-Gmail
confirmation deferred to the next scheduled 13:00 UTC send. That deferred
confirmation is a live-environment sanity check, not a gap in this phase's
verifiable goal: the rendered HTML has been proven token-for-token free of
Gmail-stripped CSS constructs and structurally table-based, which is the
verifiable proxy for "renders correctly in Gmail" available without sending mail.

### Gaps Summary

None. All 8 must-haves verified against real rendered output (not just source code
presence), all 349 tests pass, markdown output is byte-identical to baseline, and
the visual-fidelity diff confirms no unintended color/font/spacing/content changes
— only the four in-scope fixes (flex→table mechanism swap, true tracked count,
brand-new dedupe, star glyph) changed anything observable.

---

_Verified: 2026-07-25T22:30:00Z_
_Verifier: Claude (gsd-verifier)_
