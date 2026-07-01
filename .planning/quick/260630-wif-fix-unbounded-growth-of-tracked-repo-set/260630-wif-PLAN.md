---
phase: quick-260630-wif
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/config.py
  - src/prune.py
  - tests/test_prune.py
  - src/collector.py
  - tests/test_collector.py
autonomous: true
requirements: [HARD-04-EXT]

must_haves:
  truths:
    - "data/metadata.json's tracked-repo count is bounded going forward (reaches a steady state instead of growing unbounded)"
    - "A repo that has not appeared in any ranked bucket for the retention window is evicted from metadata.json"
    - "A repo that appears in a ranked bucket has its ledger date refreshed and is never evicted that run"
    - "A newly-tracked repo is granted the full retention window of grace before it can be evicted"
    - "collector.run() calls prune_metadata AFTER prune_snapshots (step 6), passing the run's reported_ids"
    - "Snapshot files under data/snapshots/ are never touched by this change (no schema migration)"
  artifacts:
    - path: "src/prune.py"
      provides: "prune_metadata() eviction function alongside prune_snapshots()"
      contains: "def prune_metadata"
    - path: "src/config.py"
      provides: "TRACKED_LEDGER_PATH + METADATA_TRACKED_RETENTION_DAYS constants"
      contains: "METADATA_TRACKED_RETENTION_DAYS"
    - path: "tests/test_prune.py"
      provides: "TestPruneMetadata unit-test class"
      contains: "class TestPruneMetadata"
    - path: "src/collector.py"
      provides: "prune_meta_fn injectable wired into run() step 6"
      contains: "prune_meta_fn"
    - path: "data/tracked_ledger.json"
      provides: "runtime ledger {str(repo_id): last-active YYYY-MM-DD}; created on first run"
  key_links:
    - from: "src/collector.py run()"
      to: "src/prune.py prune_metadata"
      via: "prune_meta_fn(now, reported_ids) after prune_fn"
      pattern: "prune_meta_fn\\("
    - from: "src/prune.py prune_metadata"
      to: "data/metadata.json"
      via: "rewrite with evicted repo ids removed"
      pattern: "metadata_path"
    - from: "src/prune.py prune_metadata"
      to: "data/tracked_ledger.json"
      via: "read + stamp + write ledger dates"
      pattern: "ledger_path"
---

<objective>
Bound the unbounded growth of the tracked-repo set in `data/metadata.json`. Every collector
run currently refreshes ~7,258 repos (all repos in metadata created within 45 days, per
`store.load_metadata_ids`'s HARD-05 filter) via one core-API `get_repo()` call each — roughly
7x the `GITHUB_TOKEN` 1,000 req/hr budget — forcing multi-hour `GithubRetry` backoff and the
1h16m stall on run 28494812391. Nothing evicts stale entries: `prune_snapshots` only trims
snapshot *files*, never the tracked-id list.

This plan adds a `prune_metadata()` eviction step (mirroring the existing `prune_snapshots`
pattern) that removes from `data/metadata.json` any repo that has not appeared in a ranked
bucket for a retention window, using a small separate ledger file to track each repo's
last-active date. This reaches a bounded steady state (roughly the volume of repos created /
ranked within the retention window) instead of unbounded accumulation.

Purpose: Stop metadata growth from stalling daily runs.
Output: `prune_metadata()` in `src/prune.py`, two config constants, a `TestPruneMetadata`
test class, and collector wiring at step 6.

SCOPE HONESTY (read before assuming this eliminates rate-limit stalls):
- This does NOT guarantee runs fit inside 1,000 req/hr. Eviction cannot drop the set below the
  count of repos created/tracked within the retention window (~3,400 at 14 days). It roughly
  HALVES refresh volume (~7,258 → ~3,400) and stops unbounded growth — that is the stated goal
  ("bound the tracked-repo count going forward").
- The operational bar is "runs COMPLETE" (bounded by the Actions job timeout, not the hourly
  quota — `GithubRetry` waits for reset and continues). Metadata's `updated_at` is currently
  today, so runs already complete, just painfully; halving the refresh set buys comfortable
  margin.
- If, after this ships, runs still approach the job timeout, a FOLLOW-UP is needed (GraphQL
  batch star-refresh, or a hard per-run cap on refresh calls). That is deliberately OUT OF
  SCOPE here — the root-cause investigation explicitly chose eviction with a 1-3 task budget.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@C:\dev\github-repo-tracker\CLAUDE.md

<interfaces>
<!-- Existing pattern to mirror (src/prune.py — DO NOT delete prune_snapshots; add alongside it): -->
```python
def prune_snapshots(now: datetime, snapshots_dir: Path = SNAPSHOTS_DIR,
                    retention_days: int = SNAPSHOT_RETENTION_DAYS) -> list[Path]:
    if not snapshots_dir.exists():
        return []
    cutoff = (now - timedelta(days=retention_days)).date()
    pruned: list[Path] = []
    for snap_path in snapshots_dir.glob("*.json"):
        try:
            snap_date = date.fromisoformat(snap_path.stem)
        except ValueError:
            continue
        if snap_date < cutoff:
            snap_path.unlink()
            pruned.append(snap_path)
    return pruned
```

<!-- metadata.json schema (src/store.py write_metadata — DO NOT change this writer or its DATA-03
     full-overwrite semantics; test_store.py asserts exact-overwrite behavior): -->
{
  "updated_at": "<UTC ISO 8601>",
  "repos": {
    "<str repo id>": {"full_name": "owner/repo", "description": "...",
                       "created_at": "<ISO>", "html_url": "..."}
  }
}

<!-- reported_ids as computed in collector.run() (list of str repo-id keys already in scope
     at step 5, line ~120): -->
reported_ids = [e["id"] for b in buckets.values() for e in b["entries"]]

<!-- collector.run() step 5 → step 6 tail (insertion point for the new call): -->
    save_seen_fn(updated_seen, SEEN_PATH)                 # step 5 ends
    # 6. Prune old snapshots — LAST, after all writes (HARD-04, D-09)
    prune_fn(now, SNAPSHOTS_DIR, SNAPSHOT_RETENTION_DAYS)
    # <-- new prune_metadata call goes here

<!-- Corrupt-file guard convention used everywhere (mirror it): -->
try:
    data = json.loads(path.read_text())
except json.JSONDecodeError:
    warnings.warn(f"Corrupt ... at {path}; treating as empty.", stacklevel=2)
    data = {}
</interfaces>

<why_a_separate_ledger>
seen.json (the existing "appeared in a bucket" store) holds ONLY {rid: {"first_seen": date}}
and is NOT bumped on return. It CANNOT be extended in place: tests/test_seen.py asserts exact
dict equality on entries (e.g. line 59 `assert updated["42"] == {"first_seen": "2026-06-28"}`,
line 88 `assert on_disk == data`). Adding a field would break those tests and expand blast
radius. metadata.json's writer is a contracted full-overwrite (test_store.py asserts it), so a
preserved field there is also off-limits. Therefore last-active state lives in a NEW, additive
ledger file `data/tracked_ledger.json` — it touches nothing already tested.
</why_a_separate_ledger>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add prune_metadata() eviction + config constants + unit tests</name>
  <files>src/config.py, src/prune.py, tests/test_prune.py</files>
  <behavior>
    prune_metadata(now, reported_ids, *, metadata_path, ledger_path, retention_days) -> list[str]
    (returns list of evicted str repo-ids). Single-clock ledger design:
    - Test: metadata_path does not exist → returns [] without raising (mirror prune_snapshots).
    - Test: first run, ledger absent → every repo currently in metadata gets stamped today in a
      new ledger; nothing is evicted; returns []. (ledger file is created on disk.)
    - Test: repo id present in reported_ids → its ledger date is set to today, and it is NOT
      evicted even if its prior ledger date was older than the cutoff.
    - Test: repo tracked but NOT in reported_ids, ledger date older than (now - retention_days)
      → evicted (removed from metadata.json repos AND returned in the list).
    - Test: repo tracked but NOT in reported_ids, ledger date within the window → kept.
    - Test: evicted repo is actually gone from metadata.json on disk after the call; a KEPT
      repo's entry (full_name/description/created_at/html_url) is byte-for-byte preserved.
    - Test: ledger entries whose rid is no longer in metadata are dropped (ledger self-cleans,
      does not grow unbounded).
    - Test: corrupt metadata.json OR corrupt ledger JSON → warns and treats as empty (no raise).
    - Test: reported_ids referencing a rid NOT in metadata does not crash and does not resurrect
      a metadata entry (only stamps the ledger, which self-cleans next run).
  </behavior>
  <action>
    1. src/config.py — add under the HARD-05 block:
       `TRACKED_LEDGER_PATH = Path("data/tracked_ledger.json")` and
       `METADATA_TRACKED_RETENTION_DAYS: int = 14` with a comment: repos absent from every
       ranked bucket for this many days are evicted from metadata; 14 gives a fresh repo two
       weeks to prove velocity, and discover_repos' 30d window re-finds any evicted repo that
       later spikes, so eviction never permanently loses a spike candidate.
    2. src/prune.py — add `prune_metadata()` ALONGSIDE `prune_snapshots` (do NOT modify or remove
       prune_snapshots). Import date/datetime/timedelta (already imported), json, warnings, and
       the two new config constants + METADATA_PATH. Signature:
       `def prune_metadata(now: datetime, reported_ids: list[str], *, metadata_path: Path = METADATA_PATH, ledger_path: Path = TRACKED_LEDGER_PATH, retention_days: int = METADATA_TRACKED_RETENTION_DAYS) -> list[str]:`
       Logic:
         a. If metadata_path missing → return []. Load metadata (corrupt → warn+treat empty →
            return []). repos = metadata.get("repos", {}).
         b. Load ledger dict {rid: "YYYY-MM-DD"} (absent → {}; corrupt → warn + {}).
         c. today = now.date().isoformat(). For rid in reported_ids: ledger[rid] = today.
         d. For rid in repos not yet in ledger: ledger[rid] = today (grace start = first tracked).
         e. cutoff = (now - timedelta(days=retention_days)).date(). evicted = [rid for rid in
            list(repos) if date.fromisoformat(ledger[rid]) < cutoff]. Guard a malformed ledger
            date the same way (bad value → warn, treat as today/keep, do not crash).
         f. Delete each evicted rid from repos. Rewrite metadata_path (json.dumps(indent=2),
            preserving updated_at). Only rewrite the file if something changed OR ledger was
            newly created, to avoid noisy no-op git diffs.
         g. Rebuild ledger to only rids still in repos (self-clean), write ledger_path
            (mkdir parents, indent=2).
         h. Return evicted (list of str ids).
       Add a module docstring update noting prune_metadata bounds the tracked-id set (companion
       to prune_snapshots which bounds snapshot files).
    3. tests/test_prune.py — add a `class TestPruneMetadata:` following the existing tmp_path /
       fixed-`_now()` conventions. Use tmp_path for metadata_path and ledger_path so no test
       ever writes real data/. Build a tiny metadata dict via a helper. Cover every case in
       <behavior> above. Reuse the `datetime(2026, 6, 28, ...)` fixed-now style already in file.
  </action>
  <verify>
    <automated>cd /c/dev/github-repo-tracker && PYTHONUTF8=1 uv run pytest tests/test_prune.py -x -q</automated>
  </verify>
  <done>All TestPruneSnapshots tests still pass unchanged; new TestPruneMetadata tests pass; prune_metadata evicts only stale non-reported repos, preserves kept-entry schema, self-cleans the ledger, and never touches data/snapshots/.</done>
</task>

<task type="auto">
  <name>Task 2: Wire prune_metadata into collector.run() step 6</name>
  <files>src/collector.py, tests/test_collector.py</files>
  <action>
    1. src/collector.py — add injectable keyword arg `prune_meta_fn=prune.prune_metadata` to
       run()'s signature (next to the existing `prune_fn=prune.prune_snapshots`), and document
       it in the docstring. Immediately AFTER the existing `prune_fn(now, SNAPSHOTS_DIR, SNAPSHOT_RETENTION_DAYS)`
       call at step 6, add: `prune_meta_fn(now, reported_ids)`.
       `reported_ids` is already computed at step 5 (line ~120) and in scope. prune_metadata's
       metadata_path / ledger_path / retention_days all default from config, so collector passes
       only (now, reported_ids). Do NOT reorder step 5/step 6 — eviction must run AFTER buckets
       are computed and the report + seen-store are written (reported_ids must be final).
    2. tests/test_collector.py — CRITICAL: every existing run() invocation that does not inject
       prune_meta_fn will otherwise call the real prune.prune_metadata against real data/. Add
       `prune_meta_fn=lambda *a, **k: []` to EVERY existing run(...) call in the file (they
       already inject `prune_fn=lambda *a, **k: []` — add the sibling right beside it).
    3. tests/test_collector.py — add one test that injects a spy for prune_meta_fn and asserts:
       (a) it is called exactly once per run(), and (b) it is called with the run's reported_ids
       (the same union `[e["id"] for b in buckets.values() for e in b["entries"]]`), following
       the existing "each Phase 2 injectable called exactly once" / reported_ids-union test
       style already in the file.
  </action>
  <verify>
    <automated>cd /c/dev/github-repo-tracker && PYTHONUTF8=1 uv run pytest tests/test_collector.py -x -q</automated>
  </verify>
  <done>run() calls prune_meta_fn(now, reported_ids) after prune_fn; the new spy test confirms one call with the correct reported_ids; all pre-existing collector tests pass with prune_meta_fn injected as a no-op fake (no real data/ writes).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| ranked buckets → prune_metadata | reported_ids is internally-derived (from own snapshots/metadata), not untrusted external input |
| ledger/metadata files → prune_metadata | on-disk JSON the tool itself wrote; may be corrupt/absent |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-wif-01 | Denial of Service | prune_metadata reading corrupt tracked_ledger.json / metadata.json | mitigate | Wrap json.loads in try/except json.JSONDecodeError → warn + treat as empty (no raise), mirroring existing store.py/seen.py guards; malformed per-entry ledger dates are guarded, not fatal |
| T-wif-02 | Tampering (data loss) | over-eager eviction removing an active repo | mitigate | Single-clock grace: any rid in reported_ids is stamped today and never evicted that run; new repos get full retention_days grace; discover_repos' 30d window re-finds evicted repos that later spike |
| T-wif-03 | Information Disclosure | GITHUB_TOKEN | accept | This change reads/writes only local JSON; no token access, no network calls added |
</threat_model>

<verification>
- `PYTHONUTF8=1 uv run pytest tests/test_prune.py tests/test_collector.py -q` — all pass.
- `PYTHONUTF8=1 uv run pytest -q` — full suite green (no regression in test_store / test_seen).
- Manual sanity (optional, offline): run `prune_metadata(datetime.now(timezone.utc), [], metadata_path=Path("data/metadata.json"), ledger_path=Path("/tmp/led.json"), retention_days=14)` in a scratch REPL against a COPY of data/metadata.json → first call evicts nothing (ledger seeded today) and creates the ledger; confirms no exception at 11,734-repo scale.
- src/report.py is NOT in files_modified (out of scope per background — hero-edition digest untouched).
- data/snapshots/ files are NOT read or written by prune_metadata (no snapshot schema migration).
</verification>

<success_criteria>
- `prune_metadata()` exists in src/prune.py beside an unmodified `prune_snapshots()`.
- collector.run() invokes `prune_meta_fn(now, reported_ids)` at step 6, after `prune_fn`.
- A repo absent from ranked buckets for `METADATA_TRACKED_RETENTION_DAYS` is removed from
  data/metadata.json; a repo in reported_ids is never evicted that run.
- The tracked-id set reaches a bounded steady state instead of growing unbounded (refresh volume
  drops from ~7,258 toward ~3,400 — HALVED, not necessarily under 1,000 req/hr; see objective
  SCOPE HONESTY note).
- data/tracked_ledger.json is created at runtime and self-cleans (no unbounded ledger growth).
- Full pytest suite passes; store.py, seen.py, report.py, and data/snapshots/ untouched.
</success_criteria>

<output>
After completion, create `.planning/quick/260630-wif-fix-unbounded-growth-of-tracked-repo-set/260630-wif-SUMMARY.md`
</output>
