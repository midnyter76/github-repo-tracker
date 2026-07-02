---
phase: quick-260702-ihe
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/collector.py
  - tests/test_collector.py
  - tests/test_search.py
autonomous: true
requirements: [PERF-refresh-skip, TEST-date-unpin]
must_haves:
  truths:
    - "refresh() is called only with tracked ids that discovery did NOT already return this run"
    - "Repos discovery already returned keep their fresh search-result data (DATA-01 freshest-wins preserved)"
    - "Full test suite passes: 0 failures"
    - "test_monthly_cohort_preserved_when_30d_over_cap passes at any run date, not just 2026-06-27"
  artifacts:
    - path: "src/collector.py"
      provides: "run() step 3 refreshes only discovery-missed ids"
      contains: "if rid not in candidates"
    - path: "tests/test_collector.py"
      provides: "Test asserting refresh receives only ids discovery missed"
    - path: "tests/test_search.py"
      provides: "Date-unpinned cohort test"
  key_links:
    - from: "src/collector.py run() step 3"
      to: "refresh callable"
      via: "list comprehension filtering out ids already in candidates"
      pattern: "refresh\\(g, \\[rid for rid in tracked_ids if rid not in candidates\\]\\)"
---

<objective>
Two independent, small fixes.

1. Runtime blowout: `run()` step 3 currently refreshes ALL tracked ids via a
   serial core-API `get_repo` per id (~7,300 calls ≈ 1h+, straining the 1,000
   req/hr GITHUB_TOKEN limit; prod runs 1h33m vs 15-20min target). Most tracked
   ids were already returned this same run by discovery (they still match the
   created:>30d topic/keyword queries), so re-fetching them is wasted quota.
   Fix: refresh only the ids discovery MISSED. Freshest-wins semantics (DATA-01)
   still hold — skipped ids carry this run's equally-fresh search data.

2. Date-pinned failing test: `test_monthly_cohort_preserved_when_30d_over_cap`
   in test_search.py computes expected query dates with a hardcoded
   `now = datetime(2026, 6, 27, ...)`, but `discover_repos` internally calls
   `since_date_for(window)` with real today. The fake match strings only matched
   on the day the test was written. Fix: compute the dates with no `now` arg.

Purpose: Cut run time to target and get the suite green (currently 1 failed, 284 passed).
Output: Modified collector.py + two tests updated/added; suite passes.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md

<interfaces>
<!-- run() in src/collector.py — step 3 (lines ~109-111 pre-fix): -->
```python
# 3. Refresh tracked repos LAST so re-fetched star counts win (DATA-01)
tracked_ids = load_ids()
candidates.update(refresh(g, tracked_ids))
```
run() takes keyword-injectable fakes: discover, established, load_ids, refresh,
write_snap, write_meta, compute_buckets, load_seen_fn, classify_fn,
write_digest, write_html_digest, save_seen_fn, check_gap_fn, filter_gamed_fn,
prune_fn, prune_meta_fn. Candidate keys are string repo ids (e.g. "111").
load_ids returns a list of string ids. No monkeypatching needed — pass fakes.

<!-- src/search.py — DO NOT MODIFY -->
def since_date_for(window_days: int, now: datetime | None = None) -> str

<!-- tests/test_search.py current failing lines (~387-389): -->
now = datetime(2026, 6, 27, tzinfo=timezone.utc)
date_7d = since_date_for(7, now=now)
date_30d = since_date_for(30, now=now)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Refresh only discovery-missed ids + docstring + test</name>
  <files>src/collector.py, tests/test_collector.py</files>
  <behavior>
    - When discovery returns an id that is ALSO in tracked_ids, refresh receives
      a list WITHOUT that id (only the ids discovery missed).
    - When tracked_ids contains ids discovery did NOT return, refresh receives
      exactly those missed ids.
    - Existing run() tests still pass (freshest-wins / union unchanged for the
      ids that ARE refreshed).
  </behavior>
  <action>
    In src/collector.py run() step 3, change:
      `candidates.update(refresh(g, tracked_ids))`
    to filter out ids discovery already produced this run:
      `candidates.update(refresh(g, [rid for rid in tracked_ids if rid not in candidates]))`
    Keep `tracked_ids = load_ids()` on the line above. Semantics: skipped ids
    already have equally-fresh data from this run's search results (DATA-01
    freshest-wins preserved); we only spend a core-API get_repo on ids discovery
    did NOT return.

    Update the run() docstring/comments to reflect the new behavior. THREE spots
    still carry the now-misleading "refresh wins / re-fetch all" framing — update
    all three:
    - The step-3 line in the "Execution order" docstring block (currently
      "refresh_tracked(g, ids) — re-fetch star counts for all tracked repos")
      → change to note it re-fetches only tracked ids discovery MISSED this run.
    - The step-4 line in that same "Execution order" block (currently
      "union all three into candidates (refresh LAST so it wins — DATA-01)")
      → refresh still runs LAST but no longer overrides discovery for overlapping
      ids (those are skipped); reword so the "so it wins" claim doesn't survive.
    - The inline comment above step 3 (currently "# 3. Refresh tracked repos LAST
      so re-fetched star counts win (DATA-01)") → clarify it now refreshes only
      discovery-missed ids to avoid redundant core-API calls, DATA-01 still holds
      because discovered ids already carry this run's fresh data.

    IMPORTANT — token-safety grep gate: test_os_environ_referenced_exactly_once
    asserts `os.environ` appears exactly once in collector.py. Do NOT add the
    string `os.environ` anywhere. Do NOT add any print of token/auth/env.

    NOTE for the executor (no action, just context): the existing test
    test_refresh_overrides_earlier_discovery will still PASS after this change,
    even though production now skips the overlapping id — its refresh fake
    (`lambda _g, _ids: {"111": repo_refresh}`) ignores its input and returns the
    fresher repo unconditionally, so `candidates.update(...)` still happens in the
    test. Don't be confused by a test named "refresh_overrides" passing while prod
    no longer refreshes overlapping ids. The NEW test below is what guards the
    actual filter behavior. Do NOT rewrite or delete the existing test.

    Add a test to tests/test_collector.py (class TestRun, following the existing
    fake/DI patterns — pass keyword fakes, no monkeypatching). The test must:
    - Provide a discovery fake returning a repo id that is ALSO in load_ids
      (e.g. discover returns {"111": repo, "222": repo}; load_ids returns
      ["222", "333"] so "222" overlaps, "333" is missed).
    - Capture the ids list passed to the refresh fake.
    - Assert the refresh fake received a list WITHOUT the overlapping id "222"
      and WITH the missed id "333" (i.e. refresh got ["333"] only).
    Wire the Phase 2/3 no-op fakes exactly as the other TestRun tests do
    (compute_buckets=lambda: _empty_buckets(), classify_fn=lambda ...: ({}, {}),
    check_gap_fn / filter_gamed_fn / prune_fn / prune_meta_fn no-ops, etc.).
  </action>
  <verify>
    <automated>uv run python -m pytest tests/test_collector.py -q</automated>
  </verify>
  <done>New test passes asserting refresh receives only discovery-missed ids; all existing test_collector.py tests still pass; token-safety grep gate (os.environ count == 1) unbroken.</done>
</task>

<task type="auto">
  <name>Task 2: Un-pin the date in test_monthly_cohort_preserved_when_30d_over_cap</name>
  <files>tests/test_search.py</files>
  <action>
    In tests/test_search.py, in
    TestDiscoverRepos::test_monthly_cohort_preserved_when_30d_over_cap
    (~lines 387-389), change the date computation so it matches at any run date.
    Replace:
      now = datetime(2026, 6, 27, tzinfo=timezone.utc)
      date_7d = since_date_for(7, now=now)
      date_30d = since_date_for(30, now=now)
    with (no `now` argument — mirrors discover_repos' internal real-today call):
      date_7d = since_date_for(7)
      date_30d = since_date_for(30)
    Remove the `now = datetime(2026, 6, 27, ...)` binding ONLY IF `now` is not
    referenced elsewhere in this test method; if it is still used, leave that
    line but ensure date_7d/date_30d no longer pass `now`. Do NOT touch
    src/search.py. Do NOT alter the unrelated TestSinceDateFor tests
    (lines ~144-159) which legitimately pass explicit `now`.
  </action>
  <verify>
    <automated>uv run python -m pytest "tests/test_search.py::TestDiscoverRepos::test_monthly_cohort_preserved_when_30d_over_cap" -q</automated>
  </verify>
  <done>The previously-failing test passes; it no longer depends on a hardcoded calendar date.</done>
</task>

</tasks>

<verification>
Full suite must pass before commit (CLAUDE.md gate):
`uv run python -m pytest -q` → 0 failures (expect 285+ passed, 0 failed).
</verification>

<success_criteria>
- src/collector.py run() step 3 refreshes only `[rid for rid in tracked_ids if rid not in candidates]`.
- run() docstring (steps 3 and 4) + step-3 inline comment reflect the new discovery-missed-only behavior.
- New test_collector.py test proves refresh receives only discovery-missed ids.
- test_monthly_cohort_preserved_when_30d_over_cap passes date-independently.
- `uv run python -m pytest -q` reports 0 failures.
- src/search.py unchanged.
</success_criteria>

<output>
After completion, create `.planning/quick/260702-ihe-refresh-skip-discovered/260702-ihe-SUMMARY.md`
</output>
