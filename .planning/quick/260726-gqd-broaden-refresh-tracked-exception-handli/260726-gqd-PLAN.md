---
phase: quick-260726-gqd
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/search.py
  - tests/test_search.py
autonomous: true
requirements: [QUICK-260726-GQD]
must_haves:
  truths:
    - "A non-404 GithubException on one tracked repo skips that repo; the rest of the run still completes and writes a snapshot"
    - "RateLimitExceededException and BadCredentialsException abort the run immediately, without waiting for the skip threshold"
    - "Deleted/private repos (UnknownObjectException) skip silently-with-warning and never push the run toward abort"
    - "Once unexpected per-repo errors exceed max(10, 5% of tracked ids), refresh_tracked raises instead of returning a gutted dict"
    - "No warning message in refresh_tracked contains the exception object or the client variable g"
  artifacts:
    - path: "src/search.py"
      provides: "refresh_tracked with ordered except clauses + skip threshold"
      contains: "except github.GithubException"
    - path: "tests/test_search.py"
      provides: "5 new TestRefreshTracked cases covering skip/abort/systemic paths"
      contains: "RateLimitExceededException"
  key_links:
    - from: "src/collector.py"
      to: "search.refresh_tracked"
      via: "refresh= injectable param (positional call, new arg is keyword-only)"
      pattern: "refresh=search\\.refresh_tracked"
---

<objective>
Broaden `refresh_tracked` per-repo exception handling from `ValueError` + `UnknownObjectException` to all `GithubException`, guarded by a skip threshold and immediate re-raise of systemic errors.

Purpose: today one 451/5xx repo out of ~2,300 aborts the whole daily run before any snapshot is written — a permanent, unbackfillable history gap. Blanket swallowing is the opposite failure (a gutted snapshot written as the day's truth), so the threshold + systemic re-raises preserve fail-loud behavior.
Output: modified `refresh_tracked` + 5 new tests, full suite green.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@src/search.py
@tests/test_search.py
@src/collector.py

<interfaces>
Current signature (src/search.py:402), and the only production caller
(src/collector.py:48 `refresh=search.refresh_tracked`, invoked positionally as
`refresh(g, ids)`), plus ~15 test fakes shaped `lambda _g, _ids: {...}`:

```python
def refresh_tracked(g, tracked_ids: list) -> dict:
    # returns {str(repo.id): repo}, skipped repos omitted
```

Therefore the new threshold parameter MUST be keyword-only with a default —
`def refresh_tracked(g, tracked_ids: list, *, max_error_skips: int | None = None) -> dict:`
— so every existing positional call site and every `lambda _g, _ids` fake keeps working
untouched. Do NOT change collector.py.

Verified in the project venv (python 3.12.10, PyGithub 2.9.1): all three of
`RateLimitExceededException`, `BadCredentialsException`, `UnknownObjectException`
are subclasses of `github.GithubException`; constructors take `(status, data, headers)`.
Subclass ordering therefore matters — every specific clause must precede the
generic `except github.GithubException`.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add failing tests for broadened handling and abort threshold</name>
  <files>tests/test_search.py</files>
  <behavior>
    Five new methods on the existing `TestRefreshTracked` class (after
    `test_skips_malformed_metadata_key_with_warning`, before
    `test_exception_handler_only_references_rid`), matching existing style:
    `MagicMock()` client, `_make_repo(id)` helper, `warnings.catch_warnings(record=True)`,
    `import github` inside the test method (as `test_skips_deleted_repos` does).
    Zero network calls.

    1. test_skips_repo_on_non_404_github_exception:
       get_repo side_effect raises `github.GithubException(451, "DMCA", None)` for id 999,
       returns `_make_repo(100)` otherwise. Call `refresh_tracked(g, ["100", "999"])`.
       Assert: "100" in result, "999" not in result, no exception raised, and some
       recorded warning message contains "999".
    2. test_raises_when_error_skips_exceed_threshold:
       every get_repo call raises `github.GithubException(500, "boom", None)`.
       Call `refresh_tracked(g, [str(i) for i in range(5)], max_error_skips=2)`
       inside `pytest.raises(RuntimeError)`. (Use the keyword arg so the abort
       path is driven without simulating hundreds of failures.)
    3. test_rate_limit_propagates_immediately:
       first get_repo call raises `github.RateLimitExceededException(403, "rate", None)`.
       Call with a generous threshold (`max_error_skips=100`) inside
       `pytest.raises(github.RateLimitExceededException)` — proves it does not
       need the threshold to be reached.
    4. test_bad_credentials_propagates_immediately:
       same shape with `github.BadCredentialsException(401, "bad", None)` and
       `pytest.raises(github.BadCredentialsException)`.
    5. test_deleted_repos_do_not_count_toward_threshold:
       every get_repo call raises `github.UnknownObjectException(404, "Not Found", None)`
       for ids 0..9 except id "42" which returns `_make_repo(42)`.
       Call `refresh_tracked(g, [...ten 404 ids..., "42"], max_error_skips=2)`.
       Assert: returns normally (no raise) and "42" in result.

    Note: `pytest` must be imported in tests/test_search.py — check the file header
    and add the import only if it is not already there.
  </behavior>
  <action>Append the five tests described above. Run them and confirm they FAIL against the current implementation (tests 1, 2, 3, 4 fail because the un-caught GithubException propagates or nothing raises; test 5 may already pass — that is fine, it is a regression guard).</action>
  <verify>
    <automated>PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_search.py::TestRefreshTracked -x -q</automated>
  </verify>
  <done>Five new tests exist and at least tests 1-4 fail with the current `refresh_tracked` implementation (RED confirmed).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement threshold-guarded exception handling in refresh_tracked</name>
  <files>src/search.py</files>
  <action>
Modify `refresh_tracked` (src/search.py:402) only. Smallest correct diff — no new
module, no exception hierarchy, no retry wrapper (PyGithub's `GithubRetry` in
`collector.build_client` already retries; see CLAUDE.md stack gotchas), no config
file / env var / settings object for the threshold.

Signature becomes:
`def refresh_tracked(g, tracked_ids: list, *, max_error_skips: int | None = None) -> dict:`

Before the loop, resolve the threshold when not supplied:
`max_error_skips = max(10, len(tracked_ids) // 20)`  (5% with an absolute floor of 10 —
a fixed absolute number is wrong at both ends of the ~2,300-repo range). Initialise
`error_skips = 0`.

Except-clause order inside the loop (subclass ordering is load-bearing — all three
specific GithubException subclasses MUST precede the generic clause):
  1. `except ValueError:` — UNCHANGED body and UNCHANGED warning text
     (`f"Repo id {rid!r} is not a valid integer; skipping"`); does not count as a skip.
  2. `except github.UnknownObjectException:` — UNCHANGED body and warning text; deleted/
     private repos are normal and expected, so this does NOT increment `error_skips`.
  3. `except (github.RateLimitExceededException, github.BadCredentialsException):` —
     bare `raise`. Systemic: the rest of the run is doomed. Does NOT increment
     `error_skips` and does not warn.
  4. `except github.GithubException:` — increment `error_skips`; if
     `error_skips > max_error_skips`, `raise RuntimeError(...)` naming the counts only
     (e.g. `f"refresh_tracked aborted: {error_skips} repo errors exceeded threshold {max_error_skips}"`);
     otherwise `warnings.warn(f"Repo id {rid} refresh failed; skipping")` and `continue`.

SECURITY — T-01-04 / WR-08, enforced statically by
`test_exception_handler_only_references_rid`: do not bind the exception with `as e`
anywhere whose name then appears in a `warnings.warn(...)` call, and never put
`e`, `e.status`, `str(e)`, or the client variable `g` in any warning message in this
function. Warning messages reference `rid` only. Do not use a bare-word `g` anywhere
inside a warn string.

Return contract is unchanged: dict keyed by `str(repo.id)` → repo object, skipped
repos omitted. Do not call `repo.get_topics()` (Pitfall 6 — there is a test for it).
Do not touch src/collector.py.

Update the docstring: describe the broadened catch, the systemic re-raises, that
deleted repos do not count toward the threshold, the `max_error_skips` argument and
its `max(10, 5%)` default, and the `RuntimeError` abort. Keep the existing
"only rid is referenced in exception handling (T-01-04)" note.
  </action>
  <verify>
    <automated>PYTHONUTF8=1 .venv/Scripts/python -m pytest -q</automated>
  </verify>
  <done>Full suite green (349 pre-existing + 5 new tests), including `test_exception_handler_only_references_rid` and `test_no_get_topics_call`.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| GitHub API → collector | Exception objects returned across this boundary may carry auth headers and connection detail |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-04 | Information disclosure | `refresh_tracked` warning messages | mitigate | Warnings reference `rid` only; no `as e` variable and no `g` in any warn call. Enforced by existing static test `test_exception_handler_only_references_rid`. |
| T-GQD-01 | Denial of service (data integrity) | Snapshot write after a gutted refresh | mitigate | `max(10, 5%)` skip threshold plus immediate re-raise of `RateLimitExceededException` / `BadCredentialsException` — a systemic failure aborts before a partial snapshot is written. |
</threat_model>

<verification>
- `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q` — all tests pass.
- `git diff --stat` shows only `src/search.py` and `tests/test_search.py` modified.
</verification>

<success_criteria>
- One bad repo (451/5xx) no longer aborts the daily run; the snapshot is still written.
- Rate-limit and bad-credentials failures still abort immediately and loudly.
- More unexpected errors than `max(10, 5% of tracked ids)` aborts with a `RuntimeError` naming the counts.
- Deleted/private repos never contribute to the abort threshold.
- No exception object or client variable reaches any warning message.
- Full suite green; no new dependency; `collector.py` untouched.
</success_criteria>

<output>
After completion, create `.planning/quick/260726-gqd-broaden-refresh-tracked-exception-handli/260726-gqd-SUMMARY.md`
</output>
