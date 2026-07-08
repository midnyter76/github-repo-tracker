---
phase: quick-260707-uec
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/seen.py
  - src/store.py
  - src/prune.py
  - src/collector.py
  - tests/test_seen.py
  - tests/test_store.py
  - tests/test_prune.py
  - tests/test_collector.py
autonomous: true
requirements: [DATA-06, HARD-04-SEEN]
must_haves:
  truths:
    - "A corrupt seen.json or metadata.json aborts the run (raises RuntimeError) instead of silently continuing with empty state"
    - "The corrupt file is preserved at <name>.corrupt for manual inspection, not deleted or silently overwritten"
    - "seen.json entries whose first_seen is older than the retention window are pruned before save"
    - "seen.json entries within the retention window (including the boundary date) survive pruning unchanged"
    - "Valid seen.json/metadata.json load/save/prune exactly as before (no regression to the normal path)"
  artifacts:
    - path: "src/seen.py"
      provides: "load_seen renames+raises on corrupt JSON instead of returning {}"
      exports: ["load_seen", "save_seen", "classify_and_update"]
    - path: "src/store.py"
      provides: "load_metadata renames+raises on corrupt JSON, symmetric with load_seen"
      exports: ["load_metadata", "write_metadata", "write_snapshot", "load_metadata_ids"]
    - path: "src/prune.py"
      provides: "prune_seen(seen, now, retention_days=SNAPSHOT_RETENTION_DAYS) -> dict"
      exports: ["prune_snapshots", "prune_metadata", "prune_seen"]
    - path: "src/collector.py"
      provides: "prune_seen_fn wired into run() between report writes and save_seen_fn"
  key_links:
    - from: "src/seen.py load_seen / src/store.py load_metadata"
      to: "RuntimeError"
      via: "JSONDecodeError except branch: seen_path.replace(corrupt_path) then raise"
      pattern: "\\.replace\\(corrupt_path\\)"
    - from: "src/collector.py run()"
      to: "src/prune.py prune_seen"
      via: "prune_seen_fn injectable kwarg, called on updated_seen after write_html_digest, before save_seen_fn"
      pattern: "prune_seen_fn\\("
---

<objective>
Fix two data-integrity bugs in the seen-store / metadata persistence layer, confirmed by
independent code audit:

1. **Silent data loss on corruption**: `seen.load_seen` and `store.load_metadata` catch
   `JSONDecodeError`, warn, and return `{}`. The collector then writes that empty dict back
   populated with only this run's results — permanently destroying prior history with no
   recovery path. Fix: rename the corrupt file to `<name>.corrupt` (preserved for manual
   inspection) and raise `RuntimeError` to abort the run. A crashed Actions run is
   recoverable (rerun, inspect the `.corrupt` file); a silently wiped history is not.

2. **Unbounded growth**: unlike `data/snapshots/` (pruned by `prune_snapshots`) and
   `metadata.json` (evicted by `prune_metadata`), `seen.json` has no eviction and grows
   forever. Fix: add `prune_seen()` to `src/prune.py`, reusing `SNAPSHOT_RETENTION_DAYS`
   from `src/config.py` (no new retention constant) to drop entries whose `first_seen`
   predates the retention window.

Purpose: stop a corrupted-write mid-run (disk full, Actions runner crash) from silently
erasing months of 🆕/↩ history and star-velocity metadata, and stop seen.json from growing
without bound the way metadata.json did before Quick Task 260630-wif.

Output: `src/seen.py`, `src/store.py` corrupt-abort guard; `src/prune.py` `prune_seen()`;
`src/collector.py` wiring; tests for both.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md

<interfaces>
<!-- Executor: current load_seen / load_metadata (BEFORE this plan) — the pattern being replaced -->

src/seen.py (current):
```python
def load_seen(seen_path: Path = config.SEEN_PATH) -> dict:
    if not seen_path.exists():
        return {}
    try:
        return json.loads(seen_path.read_text())
    except json.JSONDecodeError:
        warnings.warn(f"Corrupt seen-store at {seen_path}; treating as empty.", stacklevel=2)
        return {}
```

src/store.py (current, same pattern):
```python
def load_metadata(metadata_path: Path = METADATA_PATH) -> dict:
    if not metadata_path.exists():
        return {}
    try:
        return json.loads(metadata_path.read_text())
    except json.JSONDecodeError:
        warnings.warn(f"Corrupt metadata at {metadata_path}; treating as empty.", stacklevel=2)
        return {}
```

Both call sites feed straight into a downstream full/partial overwrite with no other
guard: `store.load_metadata_ids` -> `collector.run` step 3 (`tracked_ids = load_ids()`,
BEFORE `write_meta` overwrites at step 4) and `seen.load_seen` -> `collector.run` step 5
(`current_seen = load_seen_fn(SEEN_PATH)`, BEFORE `save_seen_fn` overwrites). Note
`rank.compute_buckets` also calls `load_metadata` at step 5, but by then `write_meta` has
already run this cycle so that particular call site can't observe a stale corrupt file —
the meaningful abort point is the step-3 `load_ids()` call.

src/prune.py `prune_metadata` (KEEP THIS AS-IS — do not change its corrupt-JSON handling;
test_prune.py:275-310 lock warn-and-continue-as-empty for this eviction pass):
```python
try:
    metadata = json.loads(metadata_path.read_text())
except json.JSONDecodeError:
    warnings.warn(f"Corrupt metadata at {metadata_path}; treating as empty.", stacklevel=2)
    return []
```
This is intentionally NOT touched by this plan. `prune_metadata`'s corrupt-JSON tolerance
is a *different* read of metadata.json (the eviction ledger pass, which degrades gracefully
by design) from `store.load_metadata` (the primary load path, which now aborts). Only
`prune_metadata`'s docstring needs a one-line correction (Task 1) since it currently claims
to "mirror the store.py/seen.py corrupt-file guard convention" — that convention just
changed for the primary load functions, not for this eviction pass.

src/collector.py (current Phase 2 block — Task 2 wires prune_seen_fn into this):
```python
buckets = compute_buckets(SNAPSHOTS_DIR, METADATA_PATH, now)
reported_ids = [e["id"] for b in buckets.values() for e in b["entries"]]
current_seen = load_seen_fn(SEEN_PATH)
markers, updated_seen = classify_fn(current_seen, reported_ids, now.strftime("%Y-%m-%d"))
write_digest(buckets, markers, now, REPORTS_DIR)      # write report FIRST (D-10)
write_html_digest(buckets, markers, now, REPORTS_DIR)  # NEW — HTML digest for email
save_seen_fn(updated_seen, SEEN_PATH)                 # then persist seen-store (D-10)
```

src/prune.py `prune_metadata` signature — the pattern `prune_seen` should read for its own
signature shape (injectable paths, `now` first, returns affected-ids-or-similar for test
assertions):
```python
def prune_metadata(
    now: datetime,
    reported_ids: list[str],
    *,
    metadata_path: Path = METADATA_PATH,
    ledger_path: Path = TRACKED_LEDGER_PATH,
    retention_days: int = METADATA_TRACKED_RETENTION_DAYS,
) -> list[str]:
```
`prune_seen` differs: it operates on an in-memory dict (matching `seen.classify_and_update`'s
pure, no-disk-I/O convention), not a file path — the caller already has `updated_seen` in
hand from `classify_fn` and will pass the pruned result straight to `save_seen_fn`.

src/config.py — constant to reuse (do NOT invent a new retention window):
```python
SNAPSHOT_RETENTION_DAYS: int = 90    # D-08 — HARD-04
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Corrupt-file abort guard for load_seen and load_metadata</name>
  <files>src/seen.py, src/store.py, src/prune.py, tests/test_seen.py, tests/test_store.py</files>
  <behavior>
    tests/test_seen.py: REPLACE `TestLoadSeen.test_corrupt_json_warns_and_returns_empty`
    (it currently asserts the old warn+`{}` behavior and will fail after this change — do
    not leave it in place alongside a new test, replace its body/name) with:
    - `test_corrupt_json_renamed_and_raises`: write invalid JSON to `seen.json`, call
      `load_seen`, assert it raises `RuntimeError` (match "Corrupt seen-store"), assert the
      original path no longer exists, assert `seen.json.corrupt` exists with the original
      corrupt bytes preserved verbatim.

    tests/test_store.py: ADD (no existing corrupt-load test here) a new test in
    `TestLoadMetadata` — `test_corrupt_json_renamed_and_raises`, same shape as above but for
    `load_metadata`/`metadata.json`/`match="Corrupt metadata"`. Add `import pytest` to the
    file's imports (not currently imported).
  </behavior>
  <action>
    1. In src/seen.py `load_seen`: on `json.JSONDecodeError`, rename the corrupt file to
       `seen_path.with_name(seen_path.name + ".corrupt")` using `Path.replace()` (not
       `.rename()` — `.replace()` overwrites cross-platform including Windows, so a
       second consecutive corruption doesn't crash the rename itself), then `raise
       RuntimeError(...) from exc` naming both the original and `.corrupt` paths. Remove
       the now-unused `warnings.warn` call and the `import warnings` line (drop the whole
       "silent {} on corrupt" path — there is no longer a warn-and-continue branch here).
       Update the docstring: no more "Mirrors the corrupt-file guard in store.load_metadata"
       comment about degrading to empty — state it aborts instead, and why (T-02-04 no
       longer applies to this path).

    2. In src/store.py `load_metadata`: identical treatment, symmetric with load_seen —
       same rename-then-raise, same `RuntimeError` pattern, message says "Corrupt metadata
       at {path}". Keep `import warnings` (still used by `write_snapshot`'s separate
       same-day-merge corrupt-snapshot handling, which this plan does NOT touch).

    3. In src/prune.py, fix ONE line in `prune_metadata`'s docstring (do not touch its
       code): replace "mirroring the store.py/seen.py corrupt-file guard convention" with
       a note that this eviction pass intentionally degrades gracefully (warn + treat as
       empty), unlike `store.load_metadata` / `seen.load_seen` (the primary load paths),
       which now abort the run on corruption to avoid silently wiping history.
  </action>
  <verify>
    <automated>cd /c/dev/github-repo-tracker && PYTHONUTF8=1 python -m pytest tests/test_seen.py tests/test_store.py tests/test_prune.py -x -q</automated>
  </verify>
  <done>
    load_seen and load_metadata both raise RuntimeError on corrupt JSON, after moving the
    corrupt file to `<name>.corrupt` via Path.replace(). Valid-JSON round-trip tests (already
    in both files) still pass unchanged. prune_metadata's corrupt-JSON behavior and its
    tests are untouched. prune.py docstring no longer claims a convention that changed.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: seen.json pruning by first_seen retention window + collector wiring</name>
  <files>src/prune.py, src/collector.py, tests/test_prune.py, tests/test_collector.py</files>
  <behavior>
    tests/test_prune.py: add `TestPruneSeen` covering:
    - entry with `first_seen` well within the window (e.g. 27 days old, retention_days=90)
      is kept, value unchanged.
    - entry with `first_seen` well outside the window (e.g. ~178 days old) is dropped.
    - boundary: with retention_days=10, an entry dated exactly at the cutoff date is KEPT
      (same `>=` convention as prune_snapshots' `<` delete rule) and an entry one day older
      than the cutoff is PRUNED.
    - entry missing `first_seen` is kept as-is (no crash).
    - entry with a malformed `first_seen` string is kept as-is and a warning is emitted
      (mirrors prune_metadata's malformed-ledger-date guard).
    - input dict is not mutated (assert key set unchanged after calling prune_seen).

    tests/test_collector.py: add a wiring test (new class `TestPruneSeenWiring`) asserting
    `prune_seen_fn` is called on `updated_seen` (the dict returned by `classify_fn`) AFTER
    `write_digest`/`write_html_digest` and BEFORE `save_seen_fn`, and that `save_seen_fn`
    receives whatever `prune_seen_fn` returns (not the unpruned `updated_seen`).
  </behavior>
  <action>
    1. In src/prune.py, add `prune_seen(seen: dict, now: datetime, retention_days: int =
       SNAPSHOT_RETENTION_DAYS) -> dict`. Pure function — no disk I/O, does not mutate
       `seen` — mirrors `seen.classify_and_update`'s contract, not `prune_metadata`'s
       file-path contract (this is intentional: the caller already holds `updated_seen` in
       memory from `classify_fn` and hands the pruned result straight to `save_seen_fn`,
       same D-10 shape as classify_and_update -> save_seen). Cutoff = `(now -
       timedelta(days=retention_days)).date()`; keep entries where
       `date.fromisoformat(entry["first_seen"]) >= cutoff`. Entries with missing/malformed
       `first_seen` are kept (warn on malformed, matching prune_metadata's guard). No new
       imports needed — `date`, `timedelta`, `warnings`, `SNAPSHOT_RETENTION_DAYS` are
       already imported in prune.py.
       Add a `# ponytail:` comment noting the accepted ceiling: pruning by first_seen means
       a repo reported continuously past the retention window flips back to "new" (🆕) once
       its entry ages out (no last-active ledger like prune_metadata's TRACKED_LEDGER_PATH
       — upgrade to that if it ever matters).

    2. In src/collector.py `run()`: add `prune_seen_fn=prune.prune_seen,` to the
       keyword-injectable signature (group it with `load_seen_fn` / `classify_fn` /
       `save_seen_fn`) plus a matching Args docstring line. In the Phase 2 body, insert
       between `write_html_digest(...)` and `save_seen_fn(...)`:
       ```python
       pruned_seen = prune_seen_fn(updated_seen, now)  # HARD-04-SEEN: bound seen.json growth
       save_seen_fn(pruned_seen, SEEN_PATH)            # then persist seen-store (D-10)
       ```
       Do not reorder `write_digest`/`write_html_digest`/`save_seen_fn` relative to each
       other — D-10 ordering (report written before seen-store persisted) is unchanged,
       pruning only happens to the dict about to be written.
  </action>
  <verify>
    <automated>cd /c/dev/github-repo-tracker && PYTHONUTF8=1 python -m pytest tests/test_prune.py tests/test_collector.py -x -q</automated>
  </verify>
  <done>
    prune_seen() correctly drops stale entries and keeps recent/boundary/malformed ones per
    the tests above. collector.run() calls prune_seen_fn on updated_seen between the report
    writes and save_seen_fn, and save_seen_fn persists the pruned result. Existing
    test_collector.py tests (which pass classify_fn returning `({}, {})`) still pass
    unchanged since prune_seen({}, now) is a no-op.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|--------------|
| Filesystem (data/seen.json, data/metadata.json) -> collector process | Files are written only by this repo's own automation, but can arrive corrupted (disk full mid-write, Actions runner crash) — the load path must not treat that as "empty" |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|------------------|
| T-uec-01 | Repudiation / Integrity | src/seen.py load_seen, src/store.py load_metadata | mitigate | Corrupt JSON renames the file to `.corrupt` (preserved for inspection) and raises RuntimeError, aborting the run instead of silently returning `{}` and letting the next write permanently erase history |
| T-uec-02 | Denial of Service (resource growth) | data/seen.json | mitigate | prune_seen() evicts entries whose first_seen predates SNAPSHOT_RETENTION_DAYS (90d), reusing the existing retention constant — no unbounded growth |
| T-uec-03 | Tampering (accidental overwrite of `.corrupt` backup) | src/seen.py, src/store.py rename step | accept | A second consecutive corruption before the first `.corrupt` file is manually inspected overwrites it (Path.replace semantics); low-probability (requires two back-to-back corrupted runs) and the failed-Actions-run signal fires on both, prompting manual intervention |
</threat_model>

<verification>
Full-suite regression after both tasks:
```
cd /c/dev/github-repo-tracker && PYTHONUTF8=1 python -m pytest -q
```
Per CLAUDE.md "Verification Before Commit": run the full suite before committing.
</verification>

<success_criteria>
- Corrupt seen.json or metadata.json aborts the run (RuntimeError) and preserves the bad
  file at `<name>.corrupt` — never silently returns `{}` and lets the next write erase
  history.
- Valid JSON continues to load/save/prune exactly as before (no regression).
- seen.json entries older than SNAPSHOT_RETENTION_DAYS (90d, reused — no new constant) are
  pruned before each save; entries within the window (including the boundary date) survive.
- Full test suite green.
</success_criteria>

<output>
After completion, create
`.planning/quick/260707-uec-fix-seen-json-data-loss-and-unbounded-gr/260707-uec-SUMMARY.md`.
In the SUMMARY, flag two accepted ceilings for future reference:
1. prune_seen keys off first_seen (not a last-active ledger), so a repo reported
   continuously past the retention window flips back to "new" (🆕) once its entry ages out.
2. After an abort, seen.json is moved to `.corrupt` and the run fails loudly (Actions run
   goes red) — recovery is manual (inspect `.corrupt`, decide whether to restore or let the
   next successful run rebuild fresh). This is intentional: a loud failure is recoverable, a
   silent wipe is not.
</output>
