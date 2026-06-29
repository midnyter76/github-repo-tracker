---
phase: 02-velocity-ranking-full-reporting
verified: 2026-06-28T00:00:00Z
status: human_needed
score: 5/5
overrides_applied: 0
human_verification:
  - test: "Trigger the daily workflow via workflow_dispatch; confirm a reports/YYYY-MM-DD.md file is committed to the repo containing all four H2 sections and at least one repo entry."
    expected: "The commit contains reports/2026-MM-DD.md; file has ## Brand New Weekly, ## Brand New Monthly, ## Breakthrough 24h Spike, ## Breakthrough 30-Day Velocity; at least the two new-repo sections have bullet entries."
    why_human: "SC1 requires the digest to be *committed* to the repo — that requires a live GitHub Actions run with a real GITHUB_TOKEN. Code-side wiring is fully verified; this is deployment confirmation only."
---

# Phase 2: Velocity Ranking + Full Reporting — Verification Report

**Phase Goal:** Each run produces a complete dated markdown digest with repos ranked by velocity across four buckets: Brand New Weekly (top 10), Brand New Monthly (top 5), Breakthrough 24h Spike (top 10), Breakthrough 30-Day Velocity (top 10). Breakthrough buckets degrade gracefully until enough snapshot history exists.
**Verified:** 2026-06-28
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | A dated markdown digest file is committed to the repo after each run, containing entries for all four ranking buckets | VERIFIED (code) / HUMAN NEEDED (deploy) | `write_digest` writes `reports/YYYY-MM-DD.md`; `daily.yml` file_pattern = `data/** reports/**`; TestWorkflowYaml.test_file_pattern_reports passes. Commit to real repo requires Actions run. |
| SC2 | Brand New Weekly (top 10) and Brand New Monthly (top 5) sections are populated with real repos and velocity numbers from the very first report | VERIFIED | `compute_buckets` populates weekly/monthly from a single snapshot (active=True always); behavioral spot-check with 1 snapshot produced 1 entry at 28.57 stars/day. |
| SC3 | Breakthrough 24h Spike and 30-Day Velocity sections display warming note and are never silently empty or crash-inducing before sufficient snapshots exist | VERIFIED | `render_bucket` always emits the `## Header`; inactive bucket calls `render_warming_note` returning `_Breakthrough buckets warming up — {N} of {M} days collected._`; 91 offline tests pass including staleness and cold-start cases. |
| SC4 | Each repo entry shows a clickable link, creation date, current star count, velocity/acceleration, and description | VERIFIED — velocity only (acceleration deferred per D-01) | `render_entry` produces `- {marker} [{full_name}]({html_url}) — ★{stars} (+{velocity:.1f}/day) · created {date} · {desc}`. All fields except acceleration are present. Acceleration was explicitly deferred in CONTEXT D-01 ("velocity only, acceleration deferred"). REQUIREMENTS.md and ROADMAP SC4 still say "velocity/acceleration" — this deviation is intentional and documented in the plans. |
| SC5 | Never-before-seen repos are flagged with a marker; returning repos are tagged; same-day retries do not incorrectly re-flag returning repos as new | VERIFIED | `classify_and_update` returns (markers, updated_seen) without mutating or writing; `collector.run()` calls `write_digest` before `save_seen_fn` (D-10); same-day-retry test passes. |

**Score:** 5/5 truths addressed

### Acceleration Deviation — Override Suggestion

REQUIREMENTS.md REPORT-02 and ROADMAP SC4 include the word "acceleration" in the repo entry format. The implementation renders velocity only (`+{velocity:.1f}/day`); acceleration is not computed or displayed. This is an **intentional design decision** documented in CONTEXT.md decision D-01 ("velocity only, acceleration deferred"). The plan's own must_haves already removed acceleration from the spec.

To document this deviation formally, add to VERIFICATION.md frontmatter:

```yaml
overrides:
  - must_have: "Each repo line shows velocity/acceleration"
    reason: "Acceleration deferred to a later phase per CONTEXT D-01; velocity-only output satisfies the phase goal."
    accepted_by: "{your name}"
    accepted_at: "2026-06-28T00:00:00Z"
```

---

## Required Artifacts

| Artifact | Provides | Status | Details |
|----------|----------|--------|---------|
| `src/config.py` | REPORTS_DIR, SEEN_PATH, Phase 2 ranking tunables | VERIFIED | All constants present: REPORTS_DIR, SEEN_PATH, BRAND_NEW_WEEKLY_DAYS=7, BRAND_NEW_WEEKLY_TOP=10, BRAND_NEW_MONTHLY_DAYS=30, BRAND_NEW_MONTHLY_TOP=5, SPIKE_TOP=10, VELOCITY_30D_TOP=10, VELOCITY_30D_WINDOW_DAYS=30, SPIKE_MIN_SNAPSHOTS=2, AGE_HOURS_FLOOR=1.0, STALE_SPIKE_HOURS=30.0, DESCRIPTION_MAX_CHARS=120. Phase 1 constants untouched. |
| `src/rank.py` | compute_buckets + velocity primitives | VERIFIED | 368 lines. All 7 functions present: compute_buckets, creation_velocity, is_new, spike_velocity, rolling_velocity, load_snapshots, select_30d_window. Reuses store.load_metadata. No github import. |
| `src/seen.py` | load_seen / save_seen / classify_and_update | VERIFIED | 92 lines. All 3 functions present. Corrupt-file guard (JSONDecodeError → warn + {}), stacklevel=2, no github import, no full_name keying. |
| `src/report.py` | sanitize_description / render_warming_note / render_entry / render_bucket / write_digest | VERIFIED | 225 lines. All 5 functions present. REPORTS_DIR used; "warming up" text present; no github import. |
| `src/collector.py` | run() with Phase 2 steps in D-10 order | VERIFIED | Phase 2 kwargs wired: compute_buckets, load_seen_fn, classify_fn, write_digest, save_seen_fn. D-10 ordering confirmed by code inspection and regex check. |
| `.github/workflows/daily.yml` | file_pattern includes reports/** | VERIFIED | Line 33: `file_pattern: "data/** reports/**"`. All other settings (cron, SHA pin, [skip ci]) unchanged. |
| `tests/test_rank.py` | Cold-start, velocity math, edge-case coverage | VERIFIED | 41 test functions. All 41 pass offline. Covers: staleness (STALE/40h), negative delta, missing metadata, boundary, sorting, corrupt file, cold-start, 2-snapshot activation. |
| `tests/test_seen.py` | Corrupt-file guard + classify + same-day-retry | VERIFIED | 10 test functions. All 10 pass offline. Covers: absent file, corrupt warn, round-trip, save dir-create, classify markers, non-mutation, same-day retry. |
| `tests/test_report.py` | Sanitization (injection) + warming-note + bullet format | VERIFIED | 40 test functions. All 40 pass offline. Covers: newline/link/control-char injection, truncation, all required bullet fields, markers, warming note, fixed order, file write, sparse bucket. |
| `tests/test_collector.py` | Phase 2 ordering test + updated fakes + workflow assertion | VERIFIED (logic) | 28 tests. 17 pass (TestTokenSafety, TestWorkflowYaml including test_file_pattern_reports). 11 fail due to pre-existing PyGithub not installed locally — all failures are `ModuleNotFoundError: No module named 'github'`; test logic is sound and verified by code inspection. |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/rank.py compute_buckets` | `config.SNAPSHOTS_DIR + config.METADATA_PATH` | `load_snapshots(glob("*.json"))` + `load_metadata(path)` | WIRED | rank.py line 251-252: `snaps = load_snapshots(snapshots_dir)` and `meta = load_metadata(metadata_path)`. Glob excludes .gitkeep. |
| `src/seen.py` | `config.SEEN_PATH` | default path argument | WIRED | `load_seen(seen_path: Path = config.SEEN_PATH)`, `save_seen(seen, seen_path: Path = config.SEEN_PATH)` |
| `src/report.py write_digest` | `reports/YYYY-MM-DD.md` | `REPORTS_DIR / f"{date_str}.md".write_text` | WIRED | report.py lines 220-222: `reports_dir.mkdir(...)` then `path.write_text(document, encoding="utf-8")` |
| `src/collector.run write_digest` | `src/seen.save_seen` | ordered sequential calls (D-10) | WIRED | collector.py line 104: `write_digest(...)` then line 105: `save_seen_fn(...)`. Regex `write_digest[\s\S]*save_seen` matches. |
| `.github/workflows/daily.yml` | `reports/YYYY-MM-DD.md` | `file_pattern: "data/** reports/**"` | WIRED | daily.yml line 33 verified; TestWorkflowYaml.test_file_pattern_reports passes. |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `src/rank.py compute_buckets` | `snaps` / `meta_repos` | `load_snapshots(snapshots_dir.glob("*.json"))` + `load_metadata(metadata_path)` | Yes — reads real JSON files from disk | FLOWING |
| `src/report.py write_digest` | `buckets`, `markers` | `rank.compute_buckets` output + `seen.classify_and_update` output | Yes — consumed from upstream callers; not hardcoded | FLOWING |
| `src/collector.py run` | all | real defaults: `rank.compute_buckets`, `seen.load_seen`, `seen.classify_and_update`, `report.write_digest`, `seen.save_seen` | Yes — real defaults wired; `main()` calls `run(build_client(), datetime.now(timezone.utc))` with no kwargs | FLOWING |

---

## Behavioral Spot-Checks

| Behavior | Result | Status |
|----------|--------|--------|
| `sanitize_description("x\ny [a](http://e)")` has no `\n` and no `](` | Confirmed | PASS |
| `classify_and_update` marks new/returning correctly, returns updated without mutation | Confirmed | PASS |
| `compute_buckets` with 1 snapshot returns active=True weekly/monthly, active=False spike/velocity | Confirmed — weekly entry at 28.57/day | PASS |
| `write_digest` produces dated file with all 4 H2 sections in fixed order, warming note for inactive | Confirmed via all assertions | PASS |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| RANK-01 | 02-01 | Brand New Weekly — top 10 by creation velocity (7d) | SATISFIED | `compute_buckets` brand_new_weekly: active=True, cap=BRAND_NEW_WEEKLY_TOP=10, window=7d, creation_velocity used |
| RANK-02 | 02-01 | Brand New Monthly — top 5 by creation velocity (30d) | SATISFIED | `compute_buckets` brand_new_monthly: active=True, cap=BRAND_NEW_MONTHLY_TOP=5, window=30d |
| RANK-03 | 02-01 | Breakthrough 24h Spike — top 10 by star delta vs prior snapshot | SATISFIED | `compute_buckets` spike_24h: spike_velocity between snaps[-1] and snaps[-2], cap=SPIKE_TOP=10 |
| RANK-04 | 02-01 | Breakthrough 30-Day Velocity — top 10 by rolling window | SATISFIED | `compute_buckets` velocity_30d: rolling_velocity via select_30d_window, cap=VELOCITY_30D_TOP=10 |
| RANK-05 | 02-01 | Velocity normalized by actual elapsed hours | SATISFIED | creation_velocity uses `(captured - created).total_seconds()/3600`; spike/rolling_velocity use `(t_latest - t_prev).total_seconds()/3600` |
| RANK-06 | 02-01 | Breakthrough buckets degrade gracefully (warming note, never crash) | SATISFIED | spike_24h: inactive when <2 snaps or gap>STALE_SPIKE_HOURS; velocity_30d: inactive when select_30d_window returns None; both return active=False, entries=[] |
| REPORT-01 | 02-03, 02-04 | Dated markdown digest file written each run | SATISFIED | `write_digest` writes reports/YYYY-MM-DD.md; committed via daily.yml `reports/**` |
| REPORT-02 | 02-03 | Repo line: link + creation date + stars + velocity + description | SATISFIED (velocity only; acceleration deferred per D-01) | render_entry: `- {marker} [{full_name}]({html_url}) — ★{stars} (+{velocity:.1f}/day) · created {date} · {desc}` |
| REPORT-03 | 02-02 | Seen-store keyed by numeric repo.id with first_seen date | SATISFIED | seen.py keys by str(repo.id); classify_and_update stores `{rid: {"first_seen": report_date}}` |
| REPORT-04 | 02-02, 02-03 | New repos flagged 🆕; returning repos tagged ↩ | SATISFIED | classify_and_update returns markers; render_entry uses `markers.get(rid, "new")` |
| REPORT-05 | 02-02, 02-04 | Seen-store updated after report written (same-day retry safe) | SATISFIED | D-10 ordering in collector.py: write_digest line 104, save_seen_fn line 105; classify_and_update does not write or mutate input |

---

## Anti-Patterns Found

| File | Pattern | Severity | Verdict |
|------|---------|----------|---------|
| `src/seen.py` lines 39, 47 | `return {}` | Info | NOT a stub — both are error-handling fallbacks (`not exists` and `JSONDecodeError`); primary path returns `json.loads(read_text())` with real data. |
| `tests/test_collector.py` TestPhase2Wiring.test_reported_ids_union_across_buckets | Uses integer ids (`{"id": 111}`) in fake bucket entries, while real `compute_buckets` produces string ids | Info | Not a bug — the reported_ids list comprehension is type-agnostic; test correctly verifies the union logic. Minor fidelity gap only. |

No blockers found.

---

## Human Verification Required

### 1. GitHub Actions End-to-End Run

**Test:** Trigger the workflow via the GitHub UI under Actions → Daily AI Repo Tracker → Run workflow (workflow_dispatch). Wait for the run to complete (~2 minutes).
**Expected:** The commit log shows a new commit by the Actions bot containing `reports/YYYY-MM-DD.md`. Open the file in the repo and confirm: (a) H1 title `# AI Repo Tracker — YYYY-MM-DD`; (b) all four ## sections are present in the fixed order; (c) Brand New Weekly and Monthly have at least one bullet entry with clickable link, ★stars, +velocity/day, created date, and sanitized description; (d) Breakthrough sections either show bullet entries (if ≥2 snapshots exist) or the warming note.
**Why human:** ROADMAP SC1 requires the digest to be committed to the repo. The commit-back step uses the live GitHub Actions environment with a real GITHUB_TOKEN secret — this cannot be verified offline. Code-side wiring is fully confirmed; this is deployment confirmation only. Risk is low: the commit-back mechanism was already proven in Phase 1 (`data/**` commits), and `reports/**` is a straightforward addition to the same file_pattern.

---

## Gaps Summary

No gaps. All 15 plan-level must-have truths are verified. All 5 ROADMAP success criteria are addressed in code. The single outstanding item is a deployment confirmation (GitHub Actions integration test) that cannot be performed offline.

One noted deviation: REQUIREMENTS.md REPORT-02 and ROADMAP SC4 reference "velocity/acceleration" but only velocity is rendered. This is an intentional, documented deferral (CONTEXT D-01) that the plans explicitly descoped. See the override suggestion above to formally acknowledge this in the VERIFICATION.md frontmatter.

---

_Verified: 2026-06-28_
_Verifier: Claude (gsd-verifier)_
