---
phase: 02-velocity-ranking-full-reporting
plan: "03"
subsystem: report
tags: [rendering, sanitization, security, markdown, digest]
dependency_graph:
  requires: ["02-01"]
  provides: ["write_digest", "sanitize_description", "render_bucket"]
  affects: ["02-04"]
tech_stack:
  added: []
  patterns:
    - "Remove brackets (not escape) to neutralize markdown-link injection — escaping still leaves ]( in output"
    - "Sanitize-first-truncate-last ordering for correct security semantics"
    - "Fixed section order via _SECTIONS constant list (not dict key order)"
    - "UTF-8 explicit encoding on write_text/read_text for Windows portability"
key_files:
  created:
    - src/report.py
    - tests/test_report.py
  modified: []
decisions:
  - "Remove [ and ] instead of escaping them: escaping produces \\](url) which still contains ]( and renders as a link in GitHub markdown"
  - "Sanitize before truncating: ensures security properties are not bypassed by truncation edge cases"
  - "TDD order: tests written first (RED), implementation second (GREEN) per D-08 advisor recommendation"
  - "Explicit encoding='utf-8' in path.read_text() required on Windows for Unicode emoji (↩, 🆕, —, ★)"
metrics:
  duration_minutes: 25
  completed_date: "2026-06-28"
  tasks_completed: 2
  files_created: 2
  tests_added: 40
---

# Phase 02 Plan 03: Digest Renderer (report.py) Summary

Four-bucket markdown digest renderer with security-critical description sanitization: removes link-injection vector `](`, collapses whitespace, strips control chars/HTML/backticks, truncates with ellipsis — all before writing to the public `reports/YYYY-MM-DD.md` file.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Write failing tests for report rendering | 2a1e07b | tests/test_report.py |
| 2 (GREEN) | Implement src/report.py | fc24341 | src/report.py, tests/test_report.py |

## What Was Built

### `src/report.py`

Five public functions implementing the rendering pipeline:

**`sanitize_description(text, max_chars=120) -> str`** (ASVS V5 / T-02-07/08/09)
- Collapses `\n`, `\r`, `\t` to single spaces; squeezes whitespace runs
- Strips ASCII control chars (ord < 32)
- Removes `[` and `]` (not escapes) — critical security decision: escaping `\]` still produces `](` which GitHub renders as a link
- Strips `<`, `>`, and backticks
- Truncates to `DESCRIPTION_MAX_CHARS` (120) then appends `…` (U+2026)
- Guarantees: no `](` substring, no embedded newlines

**`render_warming_note(bucket) -> str`** (D-07)
- Returns exact D-07 string: `_Breakthrough buckets warming up — N of M days collected._`
- Em-dash `—` (U+2014) as required by spec

**`render_entry(entry, markers) -> str`** (D-04, REPORT-02, REPORT-04)
- Bullet: `- {marker} [{full_name}]({html_url}) — ★{stars} (+{vel:.1f}/day) · created {YYYY-MM-DD} · {desc}`
- marker: `🆕` (default, "new") or `↩` ("returning")
- Description sanitized inline

**`render_bucket(title, bucket, markers) -> str`** (D-03, D-07)
- Always prints `## {title}`
- Inactive bucket → warming note; active+empty → `_No qualifying repos yet._`; active+entries → bullet lines

**`write_digest(buckets, markers, now, reports_dir) -> Path`** (REPORT-01, D-03, D-05)
- Fixed section order via `_SECTIONS` constant: Weekly → Monthly → 24h Spike → 30-Day Velocity
- Creates `reports_dir` with `mkdir(parents=True, exist_ok=True)`
- Writes `reports/YYYY-MM-DD.md` with explicit `encoding="utf-8"`
- Returns the `Path` of the written file

### `tests/test_report.py`

40 tests across 8 test classes:

| Class | Tests | Coverage |
|-------|-------|----------|
| TestSanitizeDescription | 14 | newline/CR/tab injection; link injection; HTML/backticks/control chars; truncation; None/empty/whitespace |
| TestRenderEntry | 7 | all REPORT-02 bullet fields; single-line invariant; dash prefix |
| TestMarkers | 3 | absent→🆕; "new"→🆕; "returning"→↩ |
| TestRenderWarmingnote | 2 | exact D-07 string; parametric bucket values |
| TestRenderBucket | 5 | inactive header+note; empty active; active entries; sparse count |
| TestWriteDigest | 9 | filename; Path return; four headers; fixed order; warming note; dir creation; marker; link injection; H1 title |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test encoding on Windows**
- **Found during:** Task 2 GREEN (2 tests failed)
- **Issue:** `path.read_text()` without encoding uses Windows system default (cp1252), producing garbled UTF-8 content; emoji characters (↩, —) decoded incorrectly
- **Fix:** All `path.read_text()` calls in test file use `encoding="utf-8"` explicitly
- **Files modified:** tests/test_report.py
- **Commit:** fc24341

### Implementation Choice: Remove vs. Escape Brackets

Advisor flag: escaping `[` → `\[` and `]` → `\]` does NOT satisfy the `](` invariant — the escaped form `\](url)` still contains `](` and GitHub renders it as a clickable link. The plan offered "or remove" as an alternative; the remove approach was chosen as it is the only provably-safe option. This is noted in the plan's acceptance one-liner.

### TDD Order

The plan lists Task 1 (implementation) before Task 2 (tests) but marks both `tdd="true"`. Per advisor recommendation, tests were written first (RED commit 2a1e07b) then implementation (GREEN commit fc24341), which is the correct TDD ordering. The plan is `type: execute` not `type: tdd` so there is no plan-level gate conflict.

## Known Stubs

None. All four section types render correctly:
- Active buckets with entries → bullet lines
- Active buckets with no entries → `_No qualifying repos yet._`
- Inactive buckets → warming note

## Threat Flags

No new threat surface introduced. This plan is the mitigation implementation for T-02-07, T-02-08, T-02-09 already registered in the plan's threat model. The `write_digest` function writes to `reports/YYYY-MM-DD.md` (the planned output path per D-05). No new network endpoints or auth paths.

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED (test) | 2a1e07b | PASS — all 40 tests fail before implementation |
| GREEN (feat) | fc24341 | PASS — all 40 tests pass after implementation |
| REFACTOR | N/A | Not needed — implementation is clean |

## Self-Check: PASSED

- `src/report.py` exists and contains all 5 required function definitions
- `tests/test_report.py` exists with 40 test functions
- Commit 2a1e07b (RED) exists in git log
- Commit fc24341 (GREEN) exists in git log
- Security invariant: `sanitize_description("see [here](http://evil.com)")` → `"see here(http://evil.com)"` (no `](`)
- Security invariant: `sanitize_description("a\nb")` → `"a b"` (no newline)
- `pytest tests/test_report.py -q` → 40 passed
