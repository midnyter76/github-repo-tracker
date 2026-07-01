# Deferred Items — quick-260630-wif

## Pre-existing test failure (not caused by this plan)

`tests/test_search.py::TestDiscoverRepos::test_monthly_cohort_preserved_when_30d_over_cap` fails
on `main` independent of this change — `src/search.py` and `tests/test_search.py` are not in
this plan's `files_modified` list and were not touched by any of the three commits in this task.
Out of scope; not fixed here.

## Follow-up (explicitly out of scope per plan's SCOPE HONESTY note)

`prune_metadata()` bounds tracked-repo growth but does not guarantee collector runs fit inside
`GITHUB_TOKEN`'s 1,000 req/hr core budget — refresh volume drops from ~7,258 to ~3,400 repos/run,
still above the hourly ceiling. If runs continue to approach the Actions job timeout after this
ships, consider:
- GraphQL batch star-refresh (fetch many repos per request instead of one `get_repo()` call each)
- A hard per-run cap on refresh calls, with overflow deferred to the next run
