---
phase: quick-260725-hmy
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/rank.py
  - src/store.py
  - src/collector.py
  - tests/test_rank.py
  - tests/test_store.py
  - tests/test_collector.py
  - .github/workflows/ci.yml
  - .github/workflows/daily.yml
  - .github/workflows/keepalive.yml
autonomous: true
requirements: [AUDIT-30D-JOIN, AUDIT-META-AMNESIA, AUDIT-FILTER-ORDER, AUDIT-SNAP-TS, AUDIT-CI]
must_haves:
  truths:
    - "A repo present in today's snapshot and in ANY older in-window snapshot is eligible for the velocity_30d bucket, even when it is absent from the globally-oldest in-window snapshot"
    - "A repo present in only the newest snapshot still produces no velocity_30d entry"
    - "velocity_30d keeps its >=2-in-window activation gate, negative-delta exclusion, entry shape, sort order, and VELOCITY_30D_TOP cap"
    - "write_metadata preserves metadata entries for tracked repos absent from this run's candidates, so repo eviction happens only via prune.prune_metadata's ledger"
    - "Repos dropped by filter_gamed / filter_junk still receive a snapshot row and a metadata entry, so they accumulate velocity history"
    - "Repos dropped by filter_gamed / filter_junk never appear in any ranked bucket, and filtering stays silent (no stdout/stderr)"
    - "On a same-day retry, a repo carried forward from the earlier write keeps its ORIGINAL capture timestamp instead of inheriting the retry's file-level captured_at"
    - "The 27 existing snapshot files in data/snapshots/ (no per-repo captured_at) still rank correctly via file-level fallback"
    - "Pushes and pull requests run the pytest suite in CI"
    - "daily.yml and keepalive.yml cannot run concurrently (shared concurrency group), and the daily collect job is bounded by timeout-minutes"
    - "Full pytest suite passes before every commit"
  artifacts:
    - path: "src/rank.py"
      provides: "select_30d_window returns the full in-window snapshot list; compute_buckets picks the oldest snapshot CONTAINING each rid; entry_captured_at per-repo timestamp reader with file-level fallback; exclude_ids digest-selection filter"
      contains: "exclude_ids"
    - path: "src/store.py"
      provides: "write_metadata merges existing entries instead of full-overwrite; write_snapshot stamps per-repo captured_at and carries existing entries forward untouched"
      contains: "captured_at"
    - path: "src/collector.py"
      provides: "snapshot/metadata written from the FULL candidate set; gaming/junk filters used to build an exclude_ids set passed to compute_buckets"
      contains: "exclude_ids"
    - path: ".github/workflows/ci.yml"
      provides: "pytest suite on push + pull_request, third-party actions pinned to full commit SHAs"
      contains: "pull_request"
    - path: "tests/test_rank.py"
      provides: "New tests: per-repo oldest-containing-snapshot join, single-snapshot repo yields no entry, exclude_ids suppression, per-repo captured_at fallback"
    - path: "tests/test_store.py"
      provides: "New tests: write_metadata merge preserves absent-repo entries, write_snapshot carry-forward keeps original per-repo timestamp"
    - path: "tests/test_collector.py"
      provides: "New tests: full candidate set reaches write_snap/write_meta despite filters, exclude_ids reaches compute_buckets, ci.yml + concurrency + timeout assertions"
  key_links:
    - from: "src/rank.py compute_buckets velocity_30d loop"
      to: "the oldest in-window snapshot containing each rid"
      via: "next((s for s in in_window[:-1] if rid in s['repos']), None) then rolling_velocity"
      pattern: "in_window"
    - from: "src/collector.py run()"
      to: "src/rank.py compute_buckets"
      via: "exclude_ids keyword built from set(candidates) - set(filtered)"
      pattern: "exclude_ids"
    - from: "src/store.py write_metadata"
      to: "existing data/metadata.json contents"
      via: "load existing repos dict and merge this run's entries over it"
      pattern: "load_metadata|read_text"
    - from: "src/rank.py entry_captured_at"
      to: "snapshot file-level captured_at"
      via: "per-repo .get('captured_at') with file-level fallback for legacy snapshots"
      pattern: "captured_at"
---

<objective>
Fix five findings from the joint Claude + Codex audit, each as an independent atomic commit, in the order given.

Purpose: the 30d velocity bucket is structurally blind to ~80% of tracked repos, metadata is silently amnesiac (11,645 -> 2,211 repos), filters permanently destroy history instead of filtering per-run, same-day retries corrupt the elapsed-hours denominator, and there is no CI or concurrency guard on two independent writers that push to main.

Output: minimum-diff fixes in src/rank.py, src/store.py, src/collector.py; updated + new tests in tests/; a new .github/workflows/ci.yml plus concurrency/timeout edits to the two existing workflows.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.planning/STATE.md
@src/rank.py
@src/store.py
@src/collector.py
@src/gaming.py
@src/junk.py
@src/prune.py
@src/config.py
@.github/workflows/daily.yml
@.github/workflows/keepalive.yml

<interfaces>
<!-- Current contracts the executor works against. No codebase exploration needed. -->

src/rank.py (current):
```python
def spike_velocity(snap_latest: dict, snap_prev: dict, rid: str) -> float | None
def rolling_velocity(snap_current: dict, snap_oldest: dict, rid: str) -> float | None
def load_snapshots(snapshots_dir: Path) -> list[dict]          # ascending by filename date
def select_30d_window(snapshots, run_date) -> tuple[dict, dict] | None   # (oldest, newest)
def compute_buckets(snapshots_dir=..., metadata_path=..., now=None) -> dict
```

Snapshot file schema (27 existing files on disk use this exact shape):
```json
{"date": "YYYY-MM-DD", "captured_at": "<UTC ISO>", "repos": {"<id>": {"stars": 123}}}
```

src/store.py (current):
```python
def write_snapshot(repos: dict, run_at: datetime, snapshots_dir=...) -> Path   # merges same-date file
def write_metadata(repos: dict, run_at: datetime, metadata_path=...) -> Path   # FULL OVERWRITE
def load_metadata(metadata_path=...) -> dict     # {} when absent; RuntimeError on corrupt JSON
def load_metadata_ids(metadata_path=..., max_age_days=METADATA_REFRESH_MAX_AGE_DAYS) -> list[str]
```

src/collector.py run() call site (current, lines 148-157):
```python
candidates = filter_gamed_fn(candidates)
candidates = filter_junk_fn(candidates)
write_snap(candidates, now)
write_meta(candidates, now)
buckets = compute_buckets(SNAPSHOTS_DIR, METADATA_PATH, now)
```

Filters operate on PyGithub repo OBJECTS and may only read the free attributes
`stargazers_count`, `forks_count`, `description` (any other attribute triggers a
per-repo lazy-fetch and blows the 30 req/min limit). `forks_count` is NOT stored
in the snapshot or metadata — that is why filtering must stay on the candidate
objects in the collector and be surfaced to rank as an id set, not re-derived from disk.

Existing pinned action SHAs to reuse in ci.yml (no new third-party actions needed):
```
actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683   # v4.2.2
astral-sh/setup-uv@fac544c07dec837d0ccb6301d7b5580bf5edae39 # v8.2.0
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Per-repo oldest-containing snapshot for the 30d velocity join (FINDING 1, HIGH)</name>
  <files>src/rank.py, tests/test_rank.py</files>
  <behavior>
    - Repo present in newest + a MIDDLE in-window snapshot but ABSENT from the globally-oldest one: produces a velocity_30d entry computed against that middle snapshot (today: 0 entries; after fix: entry present).
    - Repo present in newest ONLY: still produces no entry.
    - Fewer than 2 in-window snapshots: velocity_30d active=False, entries=[] (unchanged gate).
    - Repo whose stars DECREASED versus its oldest-containing snapshot: excluded (negative-delta rule preserved).
    - Entry shape, velocity_per_day = per_hour * 24, sort order, and VELOCITY_30D_TOP cap unchanged.
  </behavior>
  <action>
Change `select_30d_window(snapshots, run_date)` to return `list[dict] | None` — the full in-window snapshot list, ascending, or None when fewer than `config.SPIKE_MIN_SNAPSHOTS`-equivalent (i.e. fewer than 2) snapshots fall in the window. Keep the inclusive `>= cutoff` boundary exactly as-is. Update its docstring and the module-header Public API line (`select_30d_window(snapshots, run_date) -> list[dict] | None`).

In `compute_buckets`, replace the velocity_30d block: take `in_window = select_30d_window(snaps, run_date)`; when not None set `v30d_active = True` and `snap_newest = in_window[-1]`; for each rid in `snap_newest["repos"]` (after the existing `meta_repos` inner-join guard) find the oldest in-window snapshot that CONTAINS that rid with
`snap_oldest = next((s for s in in_window[:-1] if rid in s["repos"]), None)`
and `continue` when it is None (repo present in only the newest snapshot -> no history). Then call `rolling_velocity(snap_newest, snap_oldest, rid)` and keep the existing None check, negative-delta exclusion, `_build_entry`, `_sort_entries`, and cap logic verbatim.

Leave `rolling_velocity` itself unchanged (it stays a two-snapshot primitive). Do not add a config knob, a new module, or a cache — the scan is O(repos x snapshots) ~= 2.2k x 30 and runs once per day.

Update the existing `select_30d_window` tests in tests/test_rank.py to the new list return type, and add the new-behavior tests from <behavior> above in that file's existing class/style.

Commit: `fix(rank): join 30d velocity against oldest snapshot containing each repo`
  </action>
  <verify>
    <automated>cd /c/dev/github-repo-tracker &amp;&amp; PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/test_rank.py -q &amp;&amp; PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q</automated>
  </verify>
  <done>Full suite green. A repo absent from the globally-oldest in-window snapshot but present in a middle one produces a velocity_30d entry; a repo present only in the newest snapshot produces none; activation gate, negative-delta exclusion, sort and cap are unchanged.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: write_metadata merges instead of full-overwrite (FINDING 2, HIGH)</name>
  <files>src/store.py, tests/test_store.py</files>
  <behavior>
    - write_metadata({"111"}) then write_metadata({"222"}) leaves BOTH ids in the file, with "222"'s fields fresh.
    - Re-writing an existing id overwrites that id's fields (this run's data wins).
    - updated_at is always set to the current run's run_at.
    - A corrupt/absent metadata file behaves as before (absent -> writes fresh; corrupt -> existing load_metadata abort semantics are NOT weakened).
  </behavior>
  <action>
In `src/store.py write_metadata`, load the existing metadata via the existing `load_metadata(metadata_path)` helper (reuse it — do not re-implement JSON reading, and do not soften its corrupt-file RuntimeError abort), take `existing = load_metadata(metadata_path).get("repos", {})`, and write `{"updated_at": run_at.isoformat(), "repos": {**existing, **this_run_entries}}`. Keep the entry shape (full_name / description / created_at / html_url) and the deliberate omission of `topics` exactly as-is.

Update the module docstring and the function docstring: metadata is now a MERGE, and eviction is owned solely by `prune.prune_metadata`'s ledger (METADATA_TRACKED_RETENTION_DAYS). Update the stale comment block in src/config.py above `REFRESH_RESIDUAL_CAP` that claims repos cut by the cap "drop from metadata via the existing full-overwrite write_metadata semantics" — that is now false; they are carried forward and evicted only by the ledger.

Do NOT add a new module, a carry-forward helper, or a collector-side merge — the one-line merge in write_metadata covers the residual-cap case and every other candidate-set gap. Growth stays bounded by prune_metadata (14d) plus load_metadata_ids' METADATA_REFRESH_MAX_AGE_DAYS filter and REFRESH_RESIDUAL_CAP.

Update the existing DATA-03 full-overwrite test in tests/test_store.py (currently asserts {"111"} then {"222"} leaves only {"222"}) to assert the merge contract, and add the fresh-fields-win test.

Commit: `fix(store): merge metadata instead of overwriting so tracked repos survive the residual cap`
  </action>
  <verify>
    <automated>cd /c/dev/github-repo-tracker &amp;&amp; PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/test_store.py tests/test_prune.py -q &amp;&amp; PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q</automated>
  </verify>
  <done>Full suite green. Writing metadata for a disjoint id set preserves prior entries; re-written ids get this run's fields; prune_metadata remains the only eviction path.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Snapshot the full candidate set; filter at digest-selection time (FINDING 3, MEDIUM)</name>
  <files>src/collector.py, src/rank.py, tests/test_collector.py, tests/test_rank.py</files>
  <behavior>
    - collector.run passes the FULL candidate set (pre-filter) to both write_snap and write_meta.
    - collector.run passes exclude_ids = set(candidates) - set(filtered) to compute_buckets.
    - compute_buckets with exclude_ids={"7"} omits id 7 from all four buckets (brand_new_weekly, brand_new_monthly, spike_24h, velocity_30d) while ranking everything else normally.
    - compute_buckets with exclude_ids omitted/None behaves exactly as before.
    - Filtering remains silent: no stdout/stderr from the filter path (D-07).
  </behavior>
  <action>
In `src/rank.py compute_buckets`, add a keyword-only parameter `exclude_ids: set[str] | None = None`, normalize with `exclude_ids = exclude_ids or set()`, and skip excluded rids alongside the existing `meta_repos` inner-join guard in each of the three ranking loops (brand-new weekly/monthly shared loop, spike_24h loop, velocity_30d loop). Document it in the docstring as the digest-selection filter for gamed/junk repos.

In `src/collector.py run()`, replace lines 148-153 so the filters no longer rebind `candidates`:
```python
# 3.5. Gaming/junk repos still get snapshot + metadata rows (history is retained);
# they are excluded at digest-selection time only (HARD-03, D-07, FILTER-JUNK-01).
kept = filter_junk_fn(filter_gamed_fn(candidates))
exclude_ids = set(candidates) - set(kept)

# 4. Persist Phase 1 snapshot + metadata — FULL candidate set
write_snap(candidates, now)
write_meta(candidates, now)
```
and pass the set through: `buckets = compute_buckets(SNAPSHOTS_DIR, METADATA_PATH, now, exclude_ids=exclude_ids)`. Update the `run()` docstring execution-order block and the `filter_gamed_fn` / `filter_junk_fn` arg descriptions to say the filters now gate the digest, not persistence.

Keep the filters themselves (src/gaming.py, src/junk.py) completely untouched — they must keep operating on repo objects because `forks_count` is not persisted anywhere. Do NOT touch src/report.py.

Add the <behavior> tests: collector-level (full set to write_snap/write_meta, exclude_ids reaches compute_buckets) in tests/test_collector.py, and rank-level (exclude_ids suppresses across all four buckets, default None unchanged) in tests/test_rank.py.

Commit: `fix(collector): retain history for filtered repos by excluding them at digest selection`
  </action>
  <verify>
    <automated>cd /c/dev/github-repo-tracker &amp;&amp; PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/test_collector.py tests/test_rank.py tests/test_gaming.py tests/test_junk.py -q &amp;&amp; PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q</automated>
  </verify>
  <done>Full suite green. Filtered repos appear in the snapshot and metadata but in no bucket; unfiltered ranking output is byte-identical to before; no filter-path output on stdout/stderr; src/report.py untouched.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Per-repo captured_at so same-day retries stop corrupting elapsed hours (FINDING 4, MEDIUM)</name>
  <files>src/store.py, src/rank.py, tests/test_store.py, tests/test_rank.py</files>
  <behavior>
    - write_snapshot writes {"stars": n, "captured_at": run_at.isoformat()} for every repo in this run.
    - A same-day retry carries forward absent repos with their ORIGINAL per-repo captured_at while the file-level captured_at advances to the retry time.
    - A legacy snapshot entry with no per-repo captured_at falls back to the file-level captured_at (the 27 files in data/snapshots/ must still rank).
    - spike_velocity / rolling_velocity divide by per-repo elapsed hours (0.1h floor preserved); creation_velocity uses the repo's own capture time.
  </behavior>
  <action>
In `src/store.py write_snapshot`, stamp this run's entries as `{"stars": r.stargazers_count, "captured_at": run_at.isoformat()}`. The existing `{**existing, **new}` upsert already carries prior same-day entries forward verbatim, so a carried-forward repo keeps its original stamp — no extra branch needed. Keep the file-level `captured_at` as-is (it stays the run timestamp). Update the schema block in the docstring.

In `src/rank.py`, add one small reader and use it everywhere a capture time is read:
```python
def entry_captured_at(snap: dict, rid: str) -> str:
    """Per-repo capture time, falling back to the file-level value (legacy snapshots)."""
    return snap["repos"][rid].get("captured_at") or snap["captured_at"]
```
Use it for both sides in `spike_velocity` and `rolling_velocity`, and for the `creation_velocity(...)` call inside `compute_buckets` (replace `current["captured_at"]` with `entry_captured_at(current, rid)`). Keep the 0.1h elapsed floor and the AGE_HOURS_FLOOR. Add it to the module-header Public API list.

No migration script, no data rewrite, no new config value — the `.get(...) or file-level` fallback is the entire backward-compatibility story.

Add the <behavior> tests: store-level retry carry-forward in tests/test_store.py, legacy-fallback + per-repo-timestamp math in tests/test_rank.py. Existing rank tests that hand-build snapshot dicts without per-repo timestamps are themselves the legacy-fallback coverage — they must keep passing unmodified.

Commit: `fix(store): stamp captured_at per repo so retry merges keep original timestamps`
  </action>
  <verify>
    <automated>cd /c/dev/github-repo-tracker &amp;&amp; PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/test_store.py tests/test_rank.py -q &amp;&amp; PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q</automated>
  </verify>
  <done>Full suite green with pre-existing timestamp-less rank tests unmodified. A same-day retry leaves carried-forward repos with their original captured_at; velocity math for those repos uses the original elapsed window.</done>
</task>

<task type="auto">
  <name>Task 5: CI workflow, shared concurrency group, daily job timeout (FINDING 5, MEDIUM)</name>
  <files>.github/workflows/ci.yml, .github/workflows/daily.yml, .github/workflows/keepalive.yml, tests/test_collector.py</files>
  <action>
(a) Create `.github/workflows/ci.yml`: triggers `on: [push, pull_request]`, `permissions: contents: read`, one `test` job on `ubuntu-latest` with `timeout-minutes: 10`, steps = checkout + setup-uv (reuse the exact pinned SHAs already in daily.yml: `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2` and `astral-sh/setup-uv@fac544c07dec837d0ccb6301d7b5580bf5edae39  # v8.2.0` with `enable-cache: true`) + `run: uv run pytest -q`. No matrix, no coverage upload, no extra actions.

(b) Add the SAME workflow-level concurrency block to both `.github/workflows/daily.yml` and `.github/workflows/keepalive.yml` (both push to main and can race):
```yaml
concurrency:
  group: repo-writes
  cancel-in-progress: false
```
Do NOT add it to ci.yml — CI does not write to the repo.

(c) Add `timeout-minutes: 60` to the daily.yml `collect` job (headroom above the measured ~8-15 min run plus a possible GithubRetry rate-limit sleep, while still bounding a hung job well under the 6h default).

Add assertions to the existing workflow-file test class in tests/test_collector.py (the class that already reads daily.yml): ci.yml exists and contains `pull_request` + a `pytest` invocation, daily.yml and keepalive.yml share an identical concurrency group name, and daily.yml's collect job sets timeout-minutes. Follow that class's existing plain file-read + substring style — no YAML parser dependency.

Commit: `ci: add test workflow, shared concurrency group, and daily job timeout`
  </action>
  <verify>
    <automated>cd /c/dev/github-repo-tracker &amp;&amp; PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/test_collector.py -q &amp;&amp; PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q &amp;&amp; grep -c 'group: repo-writes' .github/workflows/daily.yml .github/workflows/keepalive.yml</automated>
  </verify>
  <done>Full suite green. ci.yml exists with push + pull_request triggers and SHA-pinned actions; both writer workflows declare `group: repo-writes`; daily.yml's collect job has timeout-minutes: 60.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| GitHub API -> collector | Untrusted repo `description` / `full_name` strings enter candidates and are persisted to metadata.json and rendered into the digest |
| data/*.json -> rank/prune | On-disk state re-read each run; corruption or schema drift changes ranking output |
| Actions runner -> main branch | daily.yml and keepalive.yml both push commits with `contents: write` |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-hmy-01 | Tampering | store.write_metadata merge (Task 2) | mitigate | Merge reads through existing `load_metadata`, which renames corrupt files to `.corrupt` and raises RuntimeError — a corrupt file aborts the run instead of being merged into (no silent history wipe). Do not weaken that path. |
| T-hmy-02 | Denial of Service | metadata.json growth after the merge change (Task 2) | mitigate | Growth bounded by `prune_metadata` (METADATA_TRACKED_RETENTION_DAYS=14 ledger eviction) plus `load_metadata_ids` age filter (45d) and `REFRESH_RESIDUAL_CAP=500` on the refresh set — API quota per run is unchanged by metadata size. |
| T-hmy-03 | Tampering | filtered repos now persisted to snapshots/metadata (Task 3) | mitigate | Gamed/junk repos are excluded from every ranked bucket via `exclude_ids`, so they never reach the digest or email; persistence carries no rendering path. |
| T-hmy-04 | Denial of Service | concurrent daily.yml + keepalive.yml pushes to main (Task 5) | mitigate | Shared `concurrency: group: repo-writes, cancel-in-progress: false` serializes the two writers; `timeout-minutes: 60` bounds a hung collect job. |
| T-hmy-05 | Elevation of Privilege | new ci.yml runs on pull_request from forks | mitigate | `permissions: contents: read` only; no secrets referenced in ci.yml; third-party actions pinned to full commit SHAs. |
| T-hmy-06 | Information Disclosure | GITHUB_TOKEN / Gmail secrets in workflow edits (Task 5) | accept | No task reads, prints, or moves a secret; ci.yml references none. Existing AUTO-02 no-token-echo tests remain in force. |
</threat_model>

<verification>
1. `cd /c/dev/github-repo-tracker && PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q` — full suite green (310 pre-existing tests plus new ones, zero regressions).
2. No new files under `src/`, no new entries in `pyproject.toml` dependencies (`git diff --stat` shows only the nine files in `files_modified`).
3. `src/report.py` shows zero changes: `git diff --name-only HEAD~5 -- src/report.py` returns nothing.
4. Existing on-disk data is untouched: `git status --porcelain data/` is clean (no migration, no rewrite).
5. Five separate commits, one per finding, in finding order.
</verification>

<success_criteria>
- All five findings fixed with the minimum diff that works; no new modules, dependencies, config frameworks, or abstractions.
- Full pytest suite passes before EACH of the five commits.
- Every finding has at least one new test proving the fix, in the existing per-module test file and style.
- Backward compatible with data/snapshots/*.json, data/metadata.json, data/seen.json, data/tracked_ledger.json — no migration, no rewrite.
- src/report.py untouched (email/HTML rendering is a separate follow-up).
- New workflow actions pinned to full commit SHAs, matching daily.yml's convention.
</success_criteria>

<output>
After completion, create `.planning/quick/260725-hmy-fix-five-audit-findings-30d-velocity-per/260725-hmy-SUMMARY.md`
</output>
