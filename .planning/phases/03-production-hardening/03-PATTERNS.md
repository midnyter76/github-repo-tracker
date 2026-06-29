# Phase 3: Production Hardening - Pattern Map

**Mapped:** 2026-06-28
**Files analyzed:** 12 (7 new/modified source files + 5 test files)
**Analogs found:** 10 / 12 (`.github/keepalive` dummy file has no analog; `tests/test_collector.py` is extended in-place using itself as analog)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/config.py` | config | N/A | itself (lines 83-104) | exact |
| `src/collector.py` | orchestrator | pipeline | itself (lines 40-55, 83-106) | exact |
| `src/gap.py` | utility | file-I/O | `src/rank.py` `load_snapshots` (lines 125-152) | role-match |
| `src/gaming.py` | utility | transform | `src/rank.py` `select_30d_window` + `_sort_entries` (lines 159-205) | role-match |
| `src/prune.py` | utility | file-I/O | `src/rank.py` `load_snapshots` + `select_30d_window` (lines 125-179) | role-match |
| `.github/workflows/keepalive.yml` | config | event-driven | `.github/workflows/daily.yml` | exact |
| `.github/workflows/daily.yml` | config | event-driven | itself | exact |
| `.github/keepalive` | data | N/A | none | no analog |
| `tests/test_gap.py` | test | N/A | `tests/test_store.py` (lines 1-43, 49-74) | role-match |
| `tests/test_gaming.py` | test | N/A | `tests/test_store.py` (lines 20-37) + `tests/test_collector.py` (lines 118-126) | role-match |
| `tests/test_prune.py` | test | N/A | `tests/test_store.py` (lines 49-169) | exact |
| `tests/test_collector.py` (extended) | test | N/A | itself `TestWorkflowYaml` (lines 496-567) | exact |

---

## Planner Decision: Module Placement Fork

RESEARCH.md (lines 163-172) explicitly raises a placement fork the planner must decide:

- **Option A — Separate modules** `src/gap.py`, `src/gaming.py`, `src/prune.py`: each function gets its own file. Consistent with how `src/rank.py`, `src/seen.py` each own a single concern.
- **Option B — Fold into `src/store.py`**: CONTEXT.md canonical refs frame pruning and gap detection as store concerns (store "reads `SNAPSHOTS_DIR`"). `store.py` already contains all snapshot-file I/O; adding `check_gap` and `prune_snapshots` there maintains the single-file-I/O boundary. `filter_gamed` does NOT belong in store.py (it is a pure in-memory transform with no I/O).

Pattern assignments below use Option A naming. If the planner chooses Option B, the import patterns for `gap.py` and `prune.py` shift to `src/store.py`; everything else stays the same.

---

## Pattern Assignments

### `src/config.py` (modified — extend with Phase 3 constants)

**Analog:** itself

**Existing Phase 2 block style to copy** (`src/config.py` lines 83-104):
```python
# ---------------------------------------------------------------------------
# Phase 2 — Ranking + Reporting
# ---------------------------------------------------------------------------

# Phase 2 paths (D-05, D-09)
REPORTS_DIR = Path("reports")
SEEN_PATH = Path("data") / "seen.json"

# Phase 2 ranking tunables (D-02, D-03, D-06)
BRAND_NEW_WEEKLY_DAYS = 7       # RANK-01 creation window
BRAND_NEW_WEEKLY_TOP = 10       # RANK-01 cap
BRAND_NEW_MONTHLY_DAYS = 30     # RANK-02 creation window
BRAND_NEW_MONTHLY_TOP = 5       # RANK-02 cap
SPIKE_TOP = 10                  # RANK-03 cap
VELOCITY_30D_TOP = 10           # RANK-04 cap
VELOCITY_30D_WINDOW_DAYS = 30   # RANK-04 widest window (D-06)
SPIKE_MIN_SNAPSHOTS = 2         # RANK-06: breakthrough activates at >=2 snapshots (D-06)

# Phase 2 safety floors / guards
AGE_HOURS_FLOOR = 1.0           # Pitfall 2: avoid div-by-zero for same-hour creation
STALE_SPIKE_HOURS = 30.0        # Pitfall 7: prior snapshot older than this => 24h bucket warms instead of mislabeling a multi-day delta
DESCRIPTION_MAX_CHARS = 120     # Pitfall 1: bullet-line truncation (used by Plan 03)
```

**Phase 3 block to append** — copy the section header + inline comment style from lines 83-104 exactly:
- Section header: `# Phase 3 — Production Hardening` with `# ---...---` rule above and below
- Each constant gets a `# HARD-NN: short rationale` inline comment explaining the decision reference
- Float literals use `.0` suffix (`26.0`, `50.0`) matching `AGE_HOURS_FLOOR = 1.0` and `STALE_SPIKE_HOURS = 30.0`
- `[ASSUMED]` tag on gaming thresholds (per RESEARCH.md — these are empirically unvalidated)

**New constants from RESEARCH.md (lines 447-469):**
- `GAP_WARN_HOURS: float = 26.0` — HARD-02
- `GAMING_MIN_STARS: int = 200` — HARD-03 `[ASSUMED]`
- `GAMING_STAR_FORK_RATIO: float = 50.0` — HARD-03 `[ASSUMED]`
- `SNAPSHOT_RETENTION_DAYS: int = 90` — HARD-04

---

### `src/collector.py` (modified — wire three new callables into run())

**Analog:** itself

**Injectable-callable signature to follow** (`src/collector.py` lines 40-55):
```python
def run(
    g,
    now: datetime,
    *,
    discover=search.discover_repos,
    established=search.discover_established,
    load_ids=store.load_metadata_ids,
    refresh=search.refresh_tracked,
    write_snap=store.write_snapshot,
    write_meta=store.write_metadata,
    compute_buckets=rank.compute_buckets,
    load_seen_fn=seen.load_seen,
    classify_fn=seen.classify_and_update,
    write_digest=report.write_digest,
    save_seen_fn=seen.save_seen,
):
```

**Three new parameters follow the same keyword-only default pattern:**
```python
    check_gap_fn=gap.check_gap,           # HARD-02: first call in run()
    filter_gamed_fn=gaming.filter_gamed,  # HARD-03: after union, before write_snap
    prune_fn=prune.prune_snapshots,       # HARD-04: last call in run()
```

**Existing step wiring to copy** (`src/collector.py` lines 83-106):
```python
    candidates: dict = {}

    # 1. Date-windowed new-repo discovery (topic + keyword)
    candidates.update(discover(g))

    # 2. Star-banded established-repo discovery (D-11, Reading B)
    candidates.update(established(g))

    # 3. Refresh tracked repos LAST so re-fetched star counts win (DATA-01)
    tracked_ids = load_ids()
    candidates.update(refresh(g, tracked_ids))

    # 4. Persist Phase 1 snapshot + metadata
    write_snap(candidates, now)
    write_meta(candidates, now)

    # 5. Phase 2: rank → classify → report → save seen (D-10 ordering)
    buckets = compute_buckets(SNAPSHOTS_DIR, METADATA_PATH, now)
    reported_ids = [e["id"] for b in buckets.values() for e in b["entries"]]
    current_seen = load_seen_fn(SEEN_PATH)
    markers, updated_seen = classify_fn(current_seen, reported_ids, now.strftime("%Y-%m-%d"))
    write_digest(buckets, markers, now, REPORTS_DIR)   # write report FIRST (D-10)
    save_seen_fn(updated_seen, SEEN_PATH)              # then persist seen-store (D-10)
```

**Wiring positions for Phase 3 calls:**
- `check_gap_fn(now, SNAPSHOTS_DIR)` — insert as step 0, before `candidates: dict = {}` (line 83)
- `candidates = filter_gamed_fn(candidates)` — insert between step 3 (line 92 `candidates.update(refresh(...))`) and step 4 (`write_snap`)
- `prune_fn(now, SNAPSHOTS_DIR, SNAPSHOT_RETENTION_DAYS)` — insert after line 105 `save_seen_fn(...)` as the final line

**Import to add** at top of file alongside existing `from src import rank, report, search, seen, store` (line 17):
```python
from src import gap, gaming, prune
from src.config import METADATA_PATH, REPORTS_DIR, SEEN_PATH, SNAPSHOTS_DIR, SNAPSHOT_RETENTION_DAYS
```

---

### `src/gap.py` (new — HARD-02 check_gap)

**Primary analog:** `src/rank.py` `load_snapshots` function (lines 125-152)

**Directory enumeration with date-stem glob** (`src/rank.py` lines 138-152):
```python
    files = sorted(snapshots_dir.glob("*.json"))
    snapshots = []
    for f in files:
        try:
            snap = json.loads(f.read_text())
        except json.JSONDecodeError:
            warnings.warn(
                f"Corrupt snapshot {f}; skipping for velocity computation.",
                stacklevel=2,
            )
            continue
        if "captured_at" in snap and "repos" in snap and "date" in snap:
            snapshots.append(snap)
    return snapshots
```

**Deviation from rank.py's pattern:** `check_gap` needs to filter to date-parseable stems before taking `max()` (to avoid a non-date file like `backup.json` shadowing real snapshots via lexicographic order). rank.py uses `sorted()` over all `*.json` then validates required keys — a different guard strategy. For `check_gap`, use an explicit `datetime.strptime(p.stem, "%Y-%m-%d")` try/except loop before taking `max(files, key=lambda p: p.stem)`.

**Secondary analog — corrupt-file guard style** (`src/store.py` lines 51-61):
```python
    existing = {}
    if snap_path.exists():
        try:
            existing = json.loads(snap_path.read_text()).get("repos", {})
        except json.JSONDecodeError:
            warnings.warn(
                f"Corrupt snapshot at {snap_path}; starting fresh for this date.",
                stacklevel=2,
            )
            existing = {}
```

**Pattern for check_gap:**
- Signature: `def check_gap(now: datetime, snapshots_dir: Path = SNAPSHOTS_DIR, warn_hours: float = GAP_WARN_HOURS) -> None`
- First-run safe: return immediately when `date_files` is empty (no snapshots yet)
- Errors (missing key, bad JSON, bad ISO string) are silently swallowed via `except (KeyError, ValueError, json.JSONDecodeError): pass` — same style as store.py
- Warning output: `print(f"WARNING: ...")` to stdout (D-04 — Actions log only, no digest)

**Imports to use** (mirror rank.py lines 20-27):
```python
import json
from datetime import datetime
from pathlib import Path

from src.config import GAP_WARN_HOURS, SNAPSHOTS_DIR
```

---

### `src/gaming.py` (new — HARD-03 filter_gamed)

**Primary analog:** `src/rank.py` `select_30d_window` (lines 159-179) — in-memory dict/list filter that iterates candidates and applies a threshold condition

**In-memory filter pattern** (`src/rank.py` lines 172-178):
```python
    in_window = [
        s for s in snapshots
        if date.fromisoformat(s["date"]) >= cutoff
    ]
    if len(in_window) < 2:
        return None
    return in_window[0], in_window[-1]
```

**Secondary analog — candidate dict iteration with skip** (`src/rank.py` lines 262-275):
```python
        for rid, snap_data in current["repos"].items():
            if rid not in meta_repos:
                continue  # Pitfall 4: inner-join; skip if metadata absent
            ...
            if is_new(created_at, run_date, config.BRAND_NEW_WEEKLY_DAYS):
                weekly_entries.append(_build_entry(rid, stars, vel, meta_repos))
```

**Pattern for filter_gamed:**
- Signature: `def filter_gamed(candidates: dict) -> dict`
- Returns a new dict — never mutates `candidates` in place (same as rank.py returning new lists)
- No print/log/warn output whatsoever (D-07: silently excluded)
- Early pass-through for stars below `GAMING_MIN_STARS` (avoids zero-fork false positives on new repos)
- Zero-fork guard: `ratio = stars / forks if forks > 0 else float("inf")`
- Reads only `repo.stargazers_count` and `repo.forks_count` — these are free search-response attributes (see RESEARCH.md Pattern 2 free-attribute whitelist)

**Imports to use:**
```python
from src.config import GAMING_MIN_STARS, GAMING_STAR_FORK_RATIO
```

**No stdlib imports needed** — pure in-memory computation.

---

### `src/prune.py` (new — HARD-04 prune_snapshots)

**Primary analog:** `src/rank.py` `load_snapshots` (lines 125-152) — glob `*.json` over `snapshots_dir`, stem-based parsing

**Directory glob and stem parse** (`src/rank.py` lines 138-141):
```python
    files = sorted(snapshots_dir.glob("*.json"))
    snapshots = []
    for f in files:
        try:
```

**Date cutoff pattern** (`src/rank.py` `select_30d_window` lines 172-173):
```python
    cutoff = run_date - timedelta(days=config.VELOCITY_30D_WINDOW_DAYS)
    in_window = [
        s for s in snapshots
        if date.fromisoformat(s["date"]) >= cutoff
    ]
```

**Pattern for prune_snapshots:**
- Signature: `def prune_snapshots(now: datetime, snapshots_dir: Path = SNAPSHOTS_DIR, retention_days: int = SNAPSHOT_RETENTION_DAYS) -> list[Path]`
- Safe when `snapshots_dir` does not exist: return `[]` immediately (mirrors `load_snapshots` being called on a fresh runner)
- Cutoff: `(now - timedelta(days=retention_days)).date()`
- Parse date from filename stem: `date.fromisoformat(snap_path.stem)` with `except ValueError: pass` to skip non-date files (same ignore-non-date pattern as gap.py)
- Delete: `snap_path.unlink()`
- Returns `list[Path]` of deleted files — enables test assertions without mocking
- No `warnings.warn` needed — pruning is expected behavior, not an error condition

**Imports to use** (mirror rank.py lines 20-27):
```python
from datetime import date, datetime, timedelta
from pathlib import Path

from src.config import SNAPSHOT_RETENTION_DAYS, SNAPSHOTS_DIR
```

---

### `.github/workflows/keepalive.yml` (new — HARD-01)

**Analog:** `.github/workflows/daily.yml` (exact)

**Permissions block** (daily.yml lines 8-9):
```yaml
permissions:
  contents: write           # required by git-auto-commit-action (AUTO-03)
```

**Trigger block structure** (daily.yml lines 3-6):
```yaml
on:
  schedule:
    - cron: '0 13 * * *'
  workflow_dispatch:
```

**checkout SHA-pinned step** (daily.yml line 16):
```yaml
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
        # persist-credentials: true (default) — needed for commit-back
```

**git-auto-commit-action step** (daily.yml lines 29-33):
```yaml
      - name: Commit snapshot
        uses: stefanzweifel/git-auto-commit-action@8621497c8c39c72f3e2a999a26b4ca1b5058a842  # v5.0.1
        with:
          commit_message: "chore: daily snapshot [skip ci]"
          file_pattern: "data/** reports/**"
```

**Keepalive-specific deviations from daily.yml:**
- No `astral-sh/setup-uv` step (no Python code runs)
- No `GITHUB_TOKEN` env injection in run step (no script to pass it to)
- Cron: `'23 4 */10 * *'` (every 10 days, 04:23 UTC — off-peak, non-round minute per RESEARCH.md Pattern 4)
- Commit message: `"chore: keepalive [skip ci]"`
- `file_pattern: ".github/keepalive"` (targets only the dummy file)
- Run step: `echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .github/keepalive`
- Same SHA pins for checkout and git-auto-commit-action as daily.yml

---

### `.github/workflows/daily.yml` (modified — add deletion-staging step for HARD-04)

**Analog:** itself

**Existing "Run collector" and "Commit snapshot" steps** (daily.yml lines 23-33):
```yaml
      - name: Run collector
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: uv run python -m src.collector

      - name: Commit snapshot
        uses: stefanzweifel/git-auto-commit-action@8621497c8c39c72f3e2a999a26b4ca1b5058a842  # v5.0.1
        with:
          commit_message: "chore: daily snapshot [skip ci]"
          file_pattern: "data/** reports/**"
```

**New step to insert** between "Run collector" and "Commit snapshot" (RESEARCH.md Pattern 5):
```yaml
      - name: Stage pruned snapshot deletions
        run: |
          DELETED=$(git ls-files --deleted data/ 2>/dev/null)
          if [ -n "$DELETED" ]; then
            git rm $DELETED
          fi
```

**Why this approach preserves existing tests:** `file_pattern: "data/** reports/**"` stays unchanged. `tests/test_collector.py` `TestWorkflowYaml.test_file_pattern_data` (line 546) and `test_file_pattern_reports` (line 556) assert on this exact value and continue to pass. The deletion staging is a separate explicit step before the auto-commit action.

---

### `.github/keepalive` (new — dummy timestamp file for HARD-01)

**No analog.** This is a single-line plain text file (UTC ISO 8601 timestamp) written by the keepalive.yml `run` step. No pattern extraction possible; the file contains no code. The planner should not model this after any existing file.

---

### `tests/test_gap.py` (new)

**Analog:** `tests/test_store.py` (lines 1-43 imports + helpers, lines 49-74 class structure + `tmp_path: Path`)

**Test file module docstring style** (test_store.py lines 1-9):
```python
"""Tests for src/store.py — persistence layer.

Covers:
- write_snapshot: idempotent per-date star snapshots (DATA-02, DATA-04, DATA-05)
...

All tests inject tmp_path so no writes ever reach the real data/ directory.
"""
```

**tmp_path injection pattern** (test_store.py lines 50-57):
```python
class TestWriteSnapshot:
    def test_creates_file_with_correct_schema(self, tmp_path: Path):
        """write_snapshot creates SNAPSHOTS_DIR/<date>.json with required top-level keys."""
        from src.store import write_snapshot

        run_at = _utc()
        ...
        snap_path = write_snapshot({"111": repo}, run_at, snapshots_dir=tmp_path)
```

**File-absent returns early pattern** (test_store.py `TestLoadMetadata` lines 288-293):
```python
    def test_returns_empty_dict_when_file_absent(self, tmp_path: Path):
        """load_metadata returns {} when the metadata file does not exist."""
        from src.store import load_metadata

        md_path = tmp_path / "nonexistent.json"
        assert load_metadata(metadata_path=md_path) == {}
```

**Key test cases for test_gap.py:**
- No snapshots: `check_gap` returns silently (no exception, no print) when `snapshots_dir` is empty
- No gap: `check_gap` is silent when `captured_at` is within `warn_hours`
- Gap detected: `check_gap` prints `WARNING:` to stdout when `captured_at` is older than `warn_hours` — use `capsys` fixture
- Bad JSON: `check_gap` does not raise when snapshot file is corrupt (swallows exception)
- Non-date `.json` file: does not cause `max()` to pick the wrong file

**Fake snapshot file pattern** (write JSON with `write_text()`, matching test_store.py's direct file manipulation approach):
```python
    (tmp_path / "2026-06-27.json").write_text(
        json.dumps({"date": "2026-06-27", "captured_at": "2026-06-27T13:00:00+00:00", "repos": {}})
    )
```

---

### `tests/test_gaming.py` (new)

**Analog:** `tests/test_store.py` `_make_repo` helper (lines 20-37) + `tests/test_collector.py` `_make_fake_repo` (lines 118-126)

**SimpleNamespace fake repo** (test_store.py lines 20-37):
```python
def _make_repo(
    id: int,
    stargazers_count: int,
    full_name: str = "owner/repo",
    description: str | None = "A test repo",
    html_url: str = "https://github.com/owner/repo",
    created_at: datetime | None = None,
) -> types.SimpleNamespace:
    if created_at is None:
        created_at = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    return types.SimpleNamespace(
        id=id,
        stargazers_count=stargazers_count,
        ...
    )
```

**Critical deviation:** `test_store.py`'s `_make_repo` does NOT include `forks_count` — the gaming filter reads `.forks_count` (a free search-response attribute not stored in snapshots). `test_gaming.py`'s `_make_repo` helper MUST add `forks_count` as a parameter and include it in the `SimpleNamespace`. This is not optional; omitting it causes `AttributeError` in `filter_gamed`.

**MagicMock repo** (test_collector.py lines 118-126):
```python
    def _make_fake_repo(self, repo_id: str, stars: int = 100):
        r = MagicMock()
        r.id = int(repo_id)
        r.stargazers_count = stars
        r.full_name = f"owner/repo-{repo_id}"
        ...
        return r
```

**Key test cases for test_gaming.py:**
- Pass-through below `GAMING_MIN_STARS`: repos with stars < 200 are kept regardless of forks
- Zero-fork suppression: repos with 0 forks AND stars >= GAMING_MIN_STARS are filtered (ratio = inf)
- Low ratio kept: stars/forks <= `GAMING_STAR_FORK_RATIO` → repo kept
- High ratio filtered: stars/forks > `GAMING_STAR_FORK_RATIO` → repo removed
- Empty candidates: `filter_gamed({})` returns `{}`
- Returns new dict: input `candidates` is not mutated
- No output: `filter_gamed` produces no stdout/log (test with `capsys` asserting empty output)

---

### `tests/test_prune.py` (new)

**Analog:** `tests/test_store.py` (exact match — same `tmp_path: Path` injection, file creation, return-value assertions)

**Return Path pattern** (test_store.py lines 161-169):
```python
    def test_returns_path_to_snapshot_file(self, tmp_path: Path):
        """write_snapshot returns the Path of the written file."""
        from src.store import write_snapshot

        run_at = _utc()
        repo = _make_repo(id=555, stargazers_count=20)
        result = write_snapshot({"555": repo}, run_at, snapshots_dir=tmp_path)

        assert isinstance(result, Path)
        assert result.exists()
```

**Missing-dir returns empty** (test_store.py lines 288-293 — missing file pattern, analogous):
```python
        md_path = tmp_path / "nonexistent.json"
        assert load_metadata(metadata_path=md_path) == []
```

**Key test cases for test_prune.py:**
- Non-existent directory: `prune_snapshots` returns `[]` without raising
- No files to prune: all files within retention → returns `[]`
- Old file deleted: file with stem date 91 days ago → deleted, returned in list
- Recent file kept: file with stem date yesterday → not deleted
- Today's file kept: today's snapshot is never deleted (pruning runs after write, cutoff is 90 days past)
- Non-date filename ignored: `backup.json` in the directory is not deleted (stem parse raises `ValueError`)
- Returns list of deleted Paths: enables test assertions via `assert deleted_path in result`
- File actually gone from disk: `assert not deleted_path.exists()`

---

### `tests/test_collector.py` (extended — add `TestKeepaliveYaml` class + daily.yml staging step assertion)

**Analog:** itself — existing `TestWorkflowYaml` class (lines 496-567)

**String-assertion class structure to mirror** (`tests/test_collector.py` lines 496-507):
```python
class TestWorkflowYaml:
    """daily.yml must contain all required strings (AUTO-01, AUTO-02, AUTO-03)."""

    def _get_workflow_text(self) -> str:
        p = Path(__file__).parent.parent / ".github" / "workflows" / "daily.yml"
        assert p.exists(), f"Workflow file not found: {p}"
        return p.read_text()

    def test_cron_schedule(self):
        """Workflow must have the D-06 cron schedule."""
        assert "cron: '0 13 * * *'" in self._get_workflow_text()
```

**New `TestKeepaliveYaml` class** — copy the `TestWorkflowYaml` pattern exactly, changing the `_get_workflow_text` helper to load `keepalive.yml`:
```python
class TestKeepaliveYaml:
    """keepalive.yml must contain all HARD-01 required strings."""

    def _get_workflow_text(self) -> str:
        p = Path(__file__).parent.parent / ".github" / "workflows" / "keepalive.yml"
        assert p.exists(), f"Workflow file not found: {p}"
        return p.read_text()
```

**Key test cases for `TestKeepaliveYaml`:**
- `test_cron_schedule`: asserts `"cron: '23 4 */10 * *'"` is present
- `test_workflow_dispatch_present`: asserts `"workflow_dispatch"` is present
- `test_contents_write_permission`: asserts `"contents: write"` is present
- `test_checkout_action_sha`: asserts the v4.2.2 SHA `"actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683"` is present (same SHA as daily.yml)
- `test_auto_commit_action_version`: mirrors `TestWorkflowYaml.test_auto_commit_action_version` (lines 524-539) — accepts both v5 tag and SHA-pinned form
- `test_skip_ci_in_commit_message`: asserts `"[skip ci]"` is present
- `test_keepalive_file_pattern`: asserts `'file_pattern: ".github/keepalive"'` is present
- `test_keepalive_commit_message`: asserts `"chore: keepalive"` is present
- `test_no_uv_setup`: asserts `"astral-sh/setup-uv"` is NOT in the file (keepalive has no Python step)

**Addition to existing `TestWorkflowYaml`** — new test method for HARD-04 staging step (mirrors test style at lines 541-543):
```python
    def test_deletion_staging_step_present(self):
        """daily.yml must include a step that stages deleted snapshot files (HARD-04)."""
        assert "git ls-files --deleted" in self._get_workflow_text()
```

---

## Shared Patterns

### JSON corrupt-file guard
**Source:** `src/store.py` lines 51-61 (write_snapshot) and lines 137-144 (load_metadata); also `src/seen.py` lines 40-47 (load_seen)
**Apply to:** `src/gap.py`

Standard form used project-wide:
```python
try:
    data = json.loads(path.read_text())
except json.JSONDecodeError:
    warnings.warn(
        f"Corrupt <file> at {path}; <graceful behavior>.",
        stacklevel=2,
    )
    return <safe_default>
```

`check_gap` uses a narrower silent variant (no `warnings.warn` — gap detection swallows corrupt-file errors completely via bare `except (...): pass`). This is intentional: gap detection is a best-effort check, and a warning about a corrupt snapshot would confuse operators expecting a gap warning.

### File-absent returns safe default
**Source:** `src/store.py` lines 135-136 (load_metadata); `src/seen.py` lines 38-39 (load_seen)
**Apply to:** `src/gap.py` (no snapshots → return silently), `src/prune.py` (no dir → return `[]`)

```python
if not path.exists():
    return <safe_default>
```

### Injectable path defaults from config
**Source:** `src/store.py` function signatures (lines 21-24, 75-78, 126); `src/rank.py` (lines 212-215)
**Apply to:** all three new utility modules

Every function that touches the filesystem takes `snapshots_dir: Path = SNAPSHOTS_DIR` (or equivalent) as a keyword argument with a config-sourced default. Tests always pass `tmp_path` explicitly. Production code in collector.py passes the path constants explicitly (consistent with `compute_buckets(SNAPSHOTS_DIR, METADATA_PATH, now)` at collector.py line 100).

### `[skip ci]` in commit messages
**Source:** `.github/workflows/daily.yml` line 32 (`"chore: daily snapshot [skip ci]"`)
**Apply to:** `.github/workflows/keepalive.yml` commit message

Required in both workflows to prevent push-triggered CI from running on automated commits.

### SHA-pinned Actions steps
**Source:** `.github/workflows/daily.yml` lines 16, 19, 30
**Apply to:** `.github/workflows/keepalive.yml`

Use identical SHAs for `actions/checkout` and `stefanzweifel/git-auto-commit-action`:
- `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2`
- `stefanzweifel/git-auto-commit-action@8621497c8c39c72f3e2a999a26b4ca1b5058a842  # v5.0.1`

### `tmp_path` injection in tests
**Source:** `tests/test_store.py` every test method signature; `tests/test_collector.py` (uses MagicMock instead — store-pattern tests prefer `tmp_path`)
**Apply to:** `tests/test_gap.py`, `tests/test_prune.py`

All tests that touch the filesystem receive `tmp_path: Path` as a pytest fixture parameter. No test writes to the real `data/` directory. `test_gaming.py` is purely in-memory (no file I/O in filter_gamed) and does not need `tmp_path`.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `.github/keepalive` | data | N/A | Plain text timestamp file; no code pattern to extract |

---

## Metadata

**Analog search scope:** `src/`, `tests/`, `.github/workflows/`
**Files read:** config.py, collector.py, store.py, rank.py, seen.py (partial), daily.yml, test_collector.py, test_store.py
**Pattern extraction date:** 2026-06-28
