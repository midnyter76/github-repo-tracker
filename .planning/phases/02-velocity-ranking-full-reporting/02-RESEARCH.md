# Phase 2: Velocity Ranking + Full Reporting - Research

**Researched:** 2026-06-28
**Domain:** Pure-Python velocity computation + markdown report generation (stdlib only)
**Confidence:** HIGH — all findings derived from verified source code and locked CONTEXT.md decisions, not from external library research.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Velocity only this phase; acceleration deferred to Phase 3.
- **D-02:** Bucket-specific, hour-normalized velocity:
  - New-repo (RANK-01/02): `stars / age_hours * 24` (creation velocity, works day 1 — no history needed)
  - 24h spike (RANK-03): star delta between two most recent snapshots, normalized by actual `captured_at` elapsed hours
  - 30-day (RANK-04): star delta over rolling 30-day window (or widest window ≥2 snapshots), normalized by actual `captured_at` elapsed hours
- **D-03:** Four H2 sections, fixed order: Brand New Weekly (top 10) → Brand New Monthly (top 5) → Breakthrough 24h Spike (top 10) → Breakthrough 30-Day Velocity (top 10).
- **D-04:** Single bullet per repo: `marker + [full_name](html_url) — ★stars (+velocity/day) · created DATE · description`. No tables.
- **D-05:** Digest file path is `reports/YYYY-MM-DD.md`.
- **D-06:** Breakthrough buckets activate when ≥2 snapshots are available; 30d uses widest available window (≥2 snapshots), not a full 30-day wait.
- **D-07:** Inactive breakthrough bucket renders its H2 header plus: `_Breakthrough buckets warming up — N of M days collected._` (N = snapshots available, M = window target). Never silently empty.
- **D-08:** 🆕 for never-before-reported repos; ↩ for returning repos.
- **D-09:** Seen-store at `data/seen.json`, keyed by numeric `repo.id` as string keys, storing `first_seen` date per repo.
- **D-10:** Seen-store written AFTER the report, so a same-day retry re-reads the pre-write state.

### Claude's Discretion

- Tie-break rule within a bucket: higher current star count wins, then lexical `full_name`.
- Sparse buckets: render however many qualify — no padding.
- Exact velocity rounding/format (e.g., `+12.4/day`), description truncation length, and whether "tracked Nd" is shown inline.
- Module layout (e.g., `src/rank.py`, `src/report.py`, `src/seen.py`) and how steps wire into `collector.run()`.

### Deferred Ideas (OUT OF SCOPE)

- Acceleration metric (2nd-derivative) — Phase 3.
- "Latest" pointer / README dashboard / index of all digests — future phase.
- Star-gaming / fake-velocity filters — Phase 3 hardening.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RANK-01 | Brand New Weekly — top 10 repos created in last 7 days, ranked by creation-date star velocity | Creation velocity formula; new-repo filter using metadata `created_at`; no history required |
| RANK-02 | Brand New Monthly — top 5 repos created in last 30 days, ranked by velocity | Same formula as RANK-01, wider time window; see Open Q #1 re: overlap with RANK-01 |
| RANK-03 | Breakthrough 24h Spike — top 10 repos by star delta over last 24h from snapshot diff | Two-snapshot diff; elapsed hours from `captured_at` delta; ≥2 snapshots to activate |
| RANK-04 | Breakthrough 30-Day Velocity — top 10 repos by sustained growth over rolling 30 days | Multi-snapshot load; widest available window ≤30d; ≥2 snapshots to activate |
| RANK-05 | Velocity normalized by elapsed hours so skipped/delayed runs don't inflate numbers | Divide by actual `captured_at` delta (hours), not nominal 24h/30d — critical for diff buckets |
| RANK-06 | Buckets needing unavailable history degrade gracefully with warming-up note, never crash | Cold-start handling: 0/1 snapshot paths; D-07 warming note format |
| REPORT-01 | Each run writes a dated markdown digest file | `reports/YYYY-MM-DD.md` path; `reports/` dir auto-created |
| REPORT-02 | Each repo line shows clickable link, creation date, current stars + velocity, description | D-04 bullet format; velocity display matches ranking metric |
| REPORT-03 | Previously-reported repos tracked in seen-store keyed by numeric `repo.id` | `data/seen.json`; load/save helpers mirroring `store.py` corrupt-file guard pattern |
| REPORT-04 | Never-before-reported repos flagged 🆕; returning repos tagged ↩ | Load seen-store before report; classify each repo in rendered buckets; update after |
| REPORT-05 | Seen-store updated after report is written; same-day retry flags correctly | Write ordering: render → write report → update and write seen-store |

</phase_requirements>

---

## Summary

Phase 2 reads the per-date snapshot files and metadata written by Phase 1, computes bucket-specific velocities, and produces a dated markdown digest plus a persistent seen-store. All logic is pure Python stdlib — no new dependencies.

The implementation adds three logical modules wired into `collector.run()` after persistence: a ranking module that loads snapshots and computes velocities per bucket, a report module that renders the markdown digest, and a seen-store module that loads/saves the `data/seen.json` file. Each follows the same keyword-injectable-dependency pattern already established by `store.py` and `collector.run()`.

The hardest mechanics are (1) correct hour-normalization using actual `captured_at` timestamps rather than nominal date differences, (2) robust snapshot discovery that handles gaps and the cold-start period gracefully, and (3) description sanitization before markdown output to prevent single-bullet-line breakage.

**Primary recommendation:** Build `src/rank.py`, `src/report.py`, `src/seen.py` as thin, injectable modules. Keep velocity computation pure functions that accept plain dicts (snapshot data, metadata dict) so they can be unit-tested without any file I/O.

---

## Architectural Responsibility Map

This is a single-process CLI invoked by GitHub Actions cron. There are no tiers in the traditional web sense — all work happens in one Python process. The mapping below reflects logical processing stages, not deployment tiers.

| Capability | Primary Stage | Secondary Stage | Rationale |
|------------|--------------|-----------------|-----------|
| Snapshot loading | `src/rank.py` | `src/store.py` (SNAPSHOTS_DIR constant) | Ranking reads multiple files; store.py only writes/loads metadata |
| Velocity computation | `src/rank.py` | — | Pure math on dicts; no I/O |
| Bucket population + ranking | `src/rank.py` | — | Applies creation window filter, computes per-bucket top-N lists |
| Markdown rendering | `src/report.py` | — | Formats bullets, headers, warming notes; returns string |
| Digest file write | `src/report.py` | `src/config.py` (REPORTS_DIR) | Owns the `reports/YYYY-MM-DD.md` path |
| Seen-store load/save | `src/seen.py` | `src/config.py` (SEEN_PATH) | Load → classify 🆕/↩ → write after report |
| Run orchestration | `src/collector.run()` | — | Calls rank+report+seen callables as injectable steps after write_snap/write_meta |

---

## Standard Stack

**No new dependencies.** All Phase 2 logic uses Python 3.12 stdlib. The locked stack from `CLAUDE.md` is complete.

| Library | Source | Purpose |
|---------|--------|---------|
| `json` | stdlib | Load snapshot files, metadata, seen-store |
| `datetime` | stdlib | `captured_at` timestamp parsing, age computation, date arithmetic |
| `pathlib` | stdlib | Snapshot file discovery (`glob`), `reports/` path construction |
| `warnings` | stdlib | Corrupt-file guard (mirrors `store.py` pattern) |

PyGithub 2.9.1 is already installed (see pyproject.toml) — no imports needed in Phase 2 modules since they consume already-written files, not the live API.

---

## Architecture Patterns

### System Architecture: Phase 2 Data Flow

```
collector.run(g, now)
  │
  ├─ [Phase 1 steps: discover → established → refresh]
  │
  ├─ write_snapshot(candidates, now)  ← data/snapshots/YYYY-MM-DD.json
  ├─ write_metadata(candidates, now)  ← data/metadata.json
  │
  ├─ rank.compute_buckets(snapshots_dir, metadata_path, now)
  │     ├─ load all *.json from SNAPSHOTS_DIR (glob + sort)
  │     ├─ load data/metadata.json
  │     ├─ new-repo filter: created_at within 7d / 30d windows
  │     ├─ creation velocity: stars / max(age_hours, 1.0) * 24  [RANK-01, RANK-02]
  │     ├─ 24h delta: snap[-1] - snap[-2] / elapsed_hours  [RANK-03]  ← ≥2 snaps
  │     └─ 30d delta: snap[-1] - oldest_in_30d / elapsed_hours  [RANK-04]  ← ≥2 snaps
  │
  ├─ seen.load_seen(seen_path)  ← data/seen.json  [REPORT-03]
  │
  ├─ report.write_digest(buckets, seen, now, reports_dir)
  │     ├─ classify each repo → 🆕 or ↩
  │     ├─ render 4 H2 sections with bullet lines or warming note
  │     └─ write reports/YYYY-MM-DD.md  [REPORT-01, D-05]
  │
  └─ seen.save_seen(updated_seen, seen_path)  ← AFTER report  [REPORT-05, D-10]
```

### Velocity Math — Exact Formulas

**RANK-01/02: Creation velocity (new-repo buckets)**

```python
# Source: derived from D-02, D-07, RANK-05 (CONTEXT.md)
from datetime import datetime, timezone

def creation_velocity(stars: int, created_at_iso: str, captured_at_iso: str) -> float:
    """Stars per day, normalized by actual elapsed hours since repo creation."""
    created = datetime.fromisoformat(created_at_iso)
    captured = datetime.fromisoformat(captured_at_iso)
    age_hours = (captured - created).total_seconds() / 3600
    age_hours = max(age_hours, 1.0)  # floor: avoid divide-by-zero for same-hour creation
    return (stars / age_hours) * 24  # → stars/day
```

New-repo filter (for a given window_days):
```python
# Source: RANK-01 / RANK-02 definitions, CONTEXT.md D-02
from datetime import date, timedelta

def is_new(created_at_iso: str, run_date: date, window_days: int) -> bool:
    created = datetime.fromisoformat(created_at_iso).date()
    return (run_date - created).days <= window_days
```

Note on RANK-05 for new-repo buckets: creation velocity is time-normalized by construction (stars / age_hours). The "skipped run" concern in RANK-05 applies mainly to the diff buckets below. No extra normalization needed here.

**RANK-03: 24h spike (snapshot diff)**

```python
# Source: D-02, RANK-03, RANK-05 (CONTEXT.md); verified against snapshot schema in store.py
def spike_velocity(snap_latest: dict, snap_prev: dict, rid: str) -> float | None:
    """Stars per hour between the two most recent snapshots. Returns None if repo absent."""
    if rid not in snap_latest["repos"] or rid not in snap_prev["repos"]:
        return None
    delta = snap_latest["repos"][rid]["stars"] - snap_prev["repos"][rid]["stars"]
    t_latest = datetime.fromisoformat(snap_latest["captured_at"])
    t_prev = datetime.fromisoformat(snap_prev["captured_at"])
    elapsed_hours = (t_latest - t_prev).total_seconds() / 3600
    elapsed_hours = max(elapsed_hours, 0.1)  # guard against identical captured_at
    return delta / elapsed_hours  # → stars/hour
```

Selects the two most recent files by sorting `SNAPSHOTS_DIR.glob("*.json")` lexicographically — ISO date filenames sort correctly.

**Stale-prior-snapshot guard (see also Pitfall 7):** Before computing the 24h spike, check the elapsed hours between `snap[-2]["captured_at"]` and `snap[-1]["captured_at"]`. If the gap exceeds ~30h, the prior snapshot is stale and the delta no longer represents a "24h" spike. In that case, apply the same RANK-06 graceful-degradation path — render the bucket header with a warming/unavailable note rather than emit a mislabeled rate. Whether the threshold is 30h, 48h, or "defer to HARD-02 in Phase 3" is a planner decision; the document flags the case.

**RANK-04: 30-day sustained velocity (rolling window)**

```python
# Source: D-02, D-06, RANK-04 (CONTEXT.md)
def rolling_velocity(snap_current: dict, snap_oldest: dict, rid: str) -> float | None:
    """Stars per hour over the widest available window up to 30 days."""
    if rid not in snap_current["repos"] or rid not in snap_oldest["repos"]:
        return None
    delta = snap_current["repos"][rid]["stars"] - snap_oldest["repos"][rid]["stars"]
    t_current = datetime.fromisoformat(snap_current["captured_at"])
    t_oldest = datetime.fromisoformat(snap_oldest["captured_at"])
    elapsed_hours = (t_current - t_oldest).total_seconds() / 3600
    elapsed_hours = max(elapsed_hours, 0.1)
    return delta / elapsed_hours  # → stars/hour (convert to /day for display)
```

"Widest available window up to 30 days" selection:
```python
# Source: D-06 (CONTEXT.md), per-date file convention (store.py / config.py)
from datetime import date, timedelta

def select_30d_window(snapshots: list[dict], run_date: date) -> tuple[dict, dict] | None:
    """Return (oldest_in_window, current) or None if <2 snapshots in 30d."""
    cutoff = run_date - timedelta(days=30)
    in_window = [
        s for s in snapshots
        if datetime.fromisoformat(s["date"]).date() >= cutoff
    ]
    if len(in_window) < 2:
        return None
    return in_window[0], in_window[-1]  # oldest, newest (already sorted by date)
```

### Snapshot Loading Pattern

```python
# Source: per-date file convention from store.py / config.py; corrupt-file guard mirrors store.py
import json
import warnings
from pathlib import Path

def load_snapshots(snapshots_dir: Path) -> list[dict]:
    """Load all valid per-date snapshot files, sorted ascending by filename date."""
    files = sorted(snapshots_dir.glob("*.json"))  # ISO names sort lexicographically
    snapshots = []
    for f in files:
        try:
            snap = json.loads(f.read_text())
            if "captured_at" in snap and "repos" in snap and "date" in snap:
                snapshots.append(snap)
        except json.JSONDecodeError:
            warnings.warn(f"Corrupt snapshot {f}; skipping for velocity computation.", stacklevel=2)
    return snapshots
```

Note: the `.gitkeep` file in `data/snapshots/` is not a `.json` file, so `glob("*.json")` safely excludes it.

### Cold-Start States

| Snapshots available | New-repo buckets | Breakthrough 24h | Breakthrough 30d |
|--------------------|-----------------|-----------------|-----------------|
| 0 (pre-first-run) | — (report not generated yet; ranking runs after write_snap, so minimum is 1) | — | — |
| 1 (first run) | Fully populated — uses metadata `created_at` + today's stars | Warming note: `_Breakthrough buckets warming up — 1 of 2 days collected._` | Warming note: `_Breakthrough buckets warming up — 1 of 30 days collected._` |
| 2 | Fully populated | Active | Active (1-day window) |
| 30+ | Fully populated | Active | Active (full 30-day window) |

**Key insight:** The report is generated after `write_snapshot` in `collector.run()`. So the minimum snapshot count when ranking executes is always 1 (today's). The "0 snapshots" case is unreachable at report time.

**Cold-start for new-repo buckets:** No history required. Uses `metadata["repos"][rid]["created_at"]` + `snap["repos"][rid]["stars"]` from today's snapshot. If metadata is absent (first-ever run edge case), return empty list — no crash.

### Seen-Store Module

```python
# Source: D-09, D-10, REPORT-03..05 (CONTEXT.md); mirrors store.py corrupt-file guard
# Schema: {"<str_repo_id>": {"first_seen": "YYYY-MM-DD"}, ...}

def load_seen(seen_path: Path) -> dict:
    if not seen_path.exists():
        return {}
    try:
        return json.loads(seen_path.read_text())
    except json.JSONDecodeError:
        warnings.warn(f"Corrupt seen-store at {seen_path}; treating as empty.", stacklevel=2)
        return {}

def save_seen(seen: dict, seen_path: Path) -> None:
    seen_path.parent.mkdir(parents=True, exist_ok=True)
    seen_path.write_text(json.dumps(seen, indent=2))

def classify_and_update(seen: dict, reported_ids: list[str], report_date: str) -> tuple[dict, dict]:
    """
    Returns:
        markers: {rid: "new" | "returning"}  — for use during rendering
        updated_seen: seen dict with new entries added (do NOT write until after report)
    """
    markers = {}
    updated = dict(seen)  # copy — don't mutate in place until after report written
    for rid in reported_ids:
        if rid in seen:
            markers[rid] = "returning"
        else:
            markers[rid] = "new"
            updated[rid] = {"first_seen": report_date}
    return markers, updated
```

**"Seen" means:** A repo ID is recorded in seen.json only when it appears in a *rendered bucket*, not merely when it is collected/tracked. The `reported_ids` list is the union of repo IDs that appear in any of the four rendered buckets.

**Same-day retry safety (D-10):** Load seen → classify → render report → save seen. On second run same day, the seen-store already has this morning's repos → they appear as ↩. This is correct per D-10.

### Digest Bullet Format (D-04)

```
{marker} [{full_name}]({html_url}) — ★{stars} (+{velocity:.1f}/day) · created {created_date} · {description}
```

- `{marker}`: `🆕` or `↩`
- `{created_date}`: `YYYY-MM-DD` (first 10 chars of `created_at` ISO string)
- `{velocity:.1f}/day`: for new-repo and 30d buckets; for 24h spike, use `/hr` since D-02 computes stars/hour for that bucket — velocity unit shown should match the ranking metric to keep ordering legible
- `{description}`: sanitized (see Pitfall 1 below); truncate to ~120 chars

**Warming-up note format (D-07):**
```markdown
_Breakthrough buckets warming up — N of M days collected._
```
Where N = len(snapshots), M = 2 for 24h spike (needs two snapshots), M = 30 for 30d bucket (full window target).

### Wiring into collector.run()

Extend the injectable signature after write_meta:

```python
# Source: existing pattern from collector.py (verified)
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
    # Phase 2 additions:
    rank_report=report.write_digest,   # (buckets, seen, now, reports_dir) -> Path
    load_seen_fn=seen.load_seen,       # (seen_path) -> dict
    save_seen_fn=seen.save_seen,       # (seen, seen_path) -> None
    compute_buckets=rank.compute_buckets,  # (snapshots_dir, metadata_path, now) -> dict
):
    ...
    write_snap(candidates, now)
    write_meta(candidates, now)
    # Phase 2 steps:
    buckets = compute_buckets(SNAPSHOTS_DIR, METADATA_PATH, now)
    current_seen = load_seen_fn(SEEN_PATH)
    markers, updated_seen = rank.classify(current_seen, buckets, now.strftime("%Y-%m-%d"))
    rank_report(buckets, markers, now, REPORTS_DIR)
    save_seen_fn(updated_seen, SEEN_PATH)
```

The existing `TestRun` in `tests/test_collector.py` injects all callables as kwargs — Phase 2 tests follow the same pattern with fakes for the new steps.

### Config Additions

Add to `src/config.py`:

```python
# Phase 2 paths
REPORTS_DIR = Path("reports")
SEEN_PATH = Path("data") / "seen.json"
```

### Recommended Project Structure

```
src/
├── config.py        # Add REPORTS_DIR, SEEN_PATH
├── collector.py     # Extend run() with injectable Phase 2 steps
├── rank.py          # compute_buckets(), creation_velocity(), spike_velocity(), rolling_velocity()
├── report.py        # write_digest(), render_bucket(), render_warming_note()
├── seen.py          # load_seen(), save_seen(), classify_and_update()
├── search.py        # Phase 1 — unchanged
└── store.py         # Phase 1 — unchanged
tests/
├── test_rank.py     # velocity math unit tests (pure functions, no I/O)
├── test_report.py   # markdown rendering; verify sanitization, warming note, bullet format
├── test_seen.py     # load/save/classify; corrupt-file guard; same-day retry ordering
└── test_collector.py # Extend TestRun with Phase 2 injectable fakes
```

### Anti-Patterns to Avoid

- **Keying seen-store by `full_name`:** Repo renames break continuity. Always `str(repo.id)`. [VERIFIED: CLAUDE.md §What NOT to Use]
- **Using nominal 24h / 720h for elapsed time:** If the runner is delayed by 6h, stars/24h inflates the rate. Always use `captured_at` delta. [VERIFIED: RANK-05, CONTEXT.md D-02]
- **Writing seen-store before the report:** If the process crashes between writing seen and writing the report, repos are marked seen without ever appearing in a digest. Write report first. [VERIFIED: D-10, REPORT-05]
- **Loading all snapshots into memory for 30d:** Only need two (oldest-in-window + current). Load lazily: current = snapshots[-1], scan backwards for oldest within 30d. [ASSUMED]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ISO timestamp parsing | Custom string slicing | `datetime.fromisoformat()` (stdlib, Python 3.7+) | Handles `+00:00`, `Z`, and naive formats; `captured_at` in snapshots uses `isoformat()` output which `.fromisoformat()` round-trips exactly |
| File sorting by date | Manual regex extraction | `sorted(path.glob("*.json"))` | ISO-format filenames (`YYYY-MM-DD.json`) sort lexicographically = chronologically |
| Rate-limit retry | tenacity / custom loop | Already in Phase 1 (`GithubRetry`) | Phase 2 makes no API calls — pure file I/O |

---

## Common Pitfalls

### Pitfall 1: Repo description breaks single-bullet-line invariant

**What goes wrong:** GitHub repo descriptions are attacker-influenceable. A description containing a newline, backtick, `[`, `](`, or angle bracket breaks the D-04 "single bullet line" format in the public markdown file.

**Why it happens:** `description` from metadata is stored verbatim (`r.description or ""`). Markdown renderers interpret `\n` as a line break; `[text](url)` in a description creates an unintended link; control characters cause rendering artifacts.

**How to avoid:** Sanitize before inserting into the bullet:
1. Strip leading/trailing whitespace; replace `\n`, `\r`, `\t` with a space.
2. Truncate to a fixed length (120 chars + `…` is a reasonable default — Claude's Discretion).
3. Escape or strip markdown-significant characters inside the description string: `[`, `]`, `` ` ``, `<`, `>`. At minimum strip angle brackets; escaping brackets prevents unintended links.

**Warning signs:** A digest line that spans multiple lines in the output file; a description that hyperlinks to an external URL.

### Pitfall 2: `age_hours = 0` divide-by-zero for same-hour repos

**What goes wrong:** A repo created at 12:58 UTC is captured at 13:00 UTC → `age_hours = 0.033`. Division yields an astronomically high velocity that dominates the new-repo bucket.

**Why it happens:** `(captured - created).total_seconds() / 3600` returns a very small positive number; no floor is applied.

**How to avoid:** `age_hours = max(age_hours, 1.0)`. A 1-hour floor gives a maximum creation velocity of `stars * 24` per day for a repo captured in its first hour — still large but bounded. [ASSUMED: floor value; planner may choose 0.5h or similar]

### Pitfall 3: Negative velocity in breakthrough buckets

**What goes wrong:** Stars can decrease (star-gaming cleanup, bot removal by GitHub). A repo with delta = -500 stars over 30d appears in the sort with a large negative velocity.

**Why it happens:** No floor on the delta before ranking.

**How to avoid:** Filter `delta >= 0` before ranking in breakthrough buckets. Repos with negative growth are not "breakthroughs." Include them as `delta = 0` or exclude entirely. Star-gaming detection is Phase 3 (HARD-03), but negative-delta exclusion is a basic sanity guard Phase 2 should apply.

**Warning signs:** Negative `+velocity/day` in the output digest.

### Pitfall 4: Repo in snapshot but missing from metadata (or vice versa)

**What goes wrong:** Metadata is a full overwrite each run (DATA-03). If a repo was collected on day 1 and dropped from discovery on day 5, it's in old snapshots but NOT in current metadata. Accessing `meta["repos"][rid]` raises `KeyError`.

**Why it happens:** Snapshot merges accumulate all-time repos; metadata only reflects the current run's candidates.

**How to avoid:** Inner join on snapshot ∩ metadata. For any velocity computation that also needs display fields (full_name, description, html_url), skip repos missing from metadata. For ranking-only operations (spike delta), metadata absence is only a problem at render time — check at render.

**Warning signs:** `KeyError` on `rid` when accessing metadata fields during report rendering.

### Pitfall 5: Snapshots list empty after filtering by 30-day window (wrong cutoff logic)

**What goes wrong:** Using `(run_date - snap_date).days > 30` includes snapshots exactly 30 days old, depending on Python's `timedelta` behavior. Or: using string comparison `snap["date"] < cutoff_str` with a naive cutoff.

**Why it happens:** Off-by-one on inclusive/exclusive boundary.

**How to avoid:** Use `>= cutoff` (inclusive) where `cutoff = run_date - timedelta(days=30)`, comparing `datetime.fromisoformat(snap["date"]).date()` values. This gives the widest correct 30d window.

### Pitfall 6: Workflow never commits reports/ — digest is generated but invisible

**What goes wrong:** Phase 1 workflow has `file_pattern: "data/**"`. `reports/YYYY-MM-DD.md` is NOT under `data/`. AUTO-03 requires the digest be committed. Without updating `file_pattern`, every digest is generated, not committed, and silently discarded.

**Why it happens:** AUTO-03 was implemented in Phase 1 with only the data-store paths in scope.

**How to avoid:** Phase 2 must update `.github/workflows/daily.yml` to add `reports/**` to the `file_pattern` for `stefanzweifel/git-auto-commit-action`. E.g.:
```yaml
file_pattern: "data/** reports/**"
```

**Warning signs:** Workflow runs succeed, `reports/` exists locally, but the remote repo never receives a `reports/YYYY-MM-DD.md` commit.

### Pitfall 7: 24h spike bucket uses a stale prior snapshot (gap in collection)

**What goes wrong:** `snapshots[-2]` is selected as the "prior" snapshot by recency, but if collection had a gap (e.g., the previous successful run was 5 days ago), the delta covers 5 days, not 24 hours. RANK-05 normalization keeps the *rate* mathematically correct, but RANK-03 is titled "24h Spike" — emitting a 5-day-delta bucket mislabels the signal.

**Why it happens:** The 30-day bucket is designed for variable windows (D-06) and degrades gracefully; the 24h bucket has no equivalent "window too wide" guard in the locked decisions.

**How to avoid:** Before computing the spike, check `(captured_at_latest - captured_at_prev).total_seconds() / 3600`. If the elapsed time exceeds a staleness threshold (e.g., ~30h), treat the 24h bucket as warming/unavailable and render the D-07 note instead. Exact threshold is a planner decision (30h / 48h / "defer to HARD-02"). At minimum, never silently emit a multi-day delta labeled as a 24h spike.

**Warning signs:** The 24h bucket shows a massive delta that the user hasn't noticed recently; inspecting the two snapshot timestamps reveals they are days apart.

---

## State of the Art

| Old Approach | Current Approach | Notes |
|--------------|------------------|-------|
| `datetime.utcnow()` (naive) | `datetime.now(timezone.utc)` (aware) | Phase 1 established UTC-aware; Phase 2 inherits — use `fromisoformat()` for parsing |
| Key by `owner/repo` | Key by `str(repo.id)` | Already enforced in Phase 1 — Phase 2 seen-store must follow the same rule |
| Monolithic JSON | Per-date files | Already enforced in Phase 1 — do not aggregate snapshots into one file |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Module names `src/rank.py`, `src/report.py`, `src/seen.py` | Architecture Patterns | Planner may choose different names — names are discretionary, pattern is locked |
| A2 | `max(age_hours, 1.0)` as the floor for creation velocity | Velocity Math | A different floor (e.g., 0.5h) changes the max reported velocity for same-hour repos; cosmetic impact only |
| A3 | Display velocity as `+N.N/day` for new-repo and 30d buckets; `/hr` for 24h spike bucket | Digest Bullet Format | If planner unifies all to `/day`, 24h spike values will be 24× larger — still correct math but different UX |
| A4 | Negative delta repos excluded from breakthrough buckets | Pitfall 3 | If planner allows negatives, the digest could show repos that lost stars as "breakthroughs" — probably a bug |
| A5 | `reported_ids` = union across all four rendered buckets | Seen-Store Module | If "seen" means something broader (e.g., tracked/collected), seen.json bloats and markers lose meaning |
| A6 | Description truncation at ~120 chars | Pitfall 1 / Bullet Format | Longer descriptions make diffs noisy and bullet lines hard to scan; exact value is cosmetic |

---

## Open Questions

### Q1: Weekly bucket ⊆ Monthly bucket overlap (RANK-01 vs RANK-02)

**What we know:** RANK-01 = repos created in last 7 days. RANK-02 = repos created in last 30 days. Face-value reading: a 3-day-old repo qualifies for BOTH.

**What's unclear:** Is the Brand New Monthly bucket intended to show "8–30 day" repos (i.e., Monthly = Monthly minus Weekly) or "all repos within 30 days" (overlap allowed, different caps)?

**Recommendation:** Default to face-value (overlap allowed, different caps). A 3-day rocket appearing in both Weekly (top 10) and Monthly (top 5) is useful signal, not a bug. Document the interpretation; planner confirms or overrides.

### Q2: Workflow `file_pattern` — is updating it in scope for Phase 2?

**What we know:** `file_pattern: "data/**"` in Phase 1 workflow. `reports/YYYY-MM-DD.md` is not under `data/`. AUTO-03 requires the digest be committed.

**What's unclear:** Phase 2 scope says "RANK-01..06, REPORT-01..05" — the workflow file is Phase 1 infra. Is updating `daily.yml` in scope for Phase 2?

**Recommendation:** Yes — updating `file_pattern` in `daily.yml` is a required Phase 2 deliverable. Without it, REPORT-01 (digest file) is never committed, making the entire phase invisible in production. This is an integration task, not scope creep.

### Q3: Which repos are eligible for breakthrough buckets?

**What we know:** Phase 1's `discover_established()` uses `BREAKTHROUGH_STAR_BANDS = ["100..1000", "1000..10000"]` to ensure established repos are in the snapshot universe. New repos (0–100 stars) are discovered via date-windowed queries.

**What's unclear:** Should 24h spike and 30d velocity buckets be limited to repos *not* in the new-repo time windows (i.e., "established" only), or can a brand-new repo also spike into the breakthrough bucket?

**Recommendation:** Allow any repo in the snapshot/metadata universe to qualify for any bucket — the buckets are metric-based, not universe-based. A 5-day-old repo that spikes 500 stars in 24h is genuinely a breakthrough. Mention in the plan as an explicit decision point.

---

## Security Domain

`security_enforcement` is absent in `.planning/config.json` — treated as enabled per research instructions.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Token handling is Phase 1 — not in Phase 2 scope |
| V3 Session Management | No | No sessions; single-process CLI |
| V4 Access Control | No | No multi-user context |
| V5 Input Validation | **Yes** | Sanitize repo descriptions before markdown output (see Pitfall 1) |
| V6 Cryptography | No | No crypto; no new secret handling in Phase 2 |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malicious repo description with embedded markdown/newlines breaks digest format | Tampering | Strip control characters, escape or remove markdown-significant chars (`[`, `]`, `<`, `>`), truncate before inserting into bullet template |
| Repo name containing markdown link syntax (e.g., `](evil.com`) | Tampering | `full_name` is used as the link *label*, not raw text — `[{full_name}](html_url)` where `full_name` itself is trusted GitHub API output and is not re-parsed as markdown. Only description needs sanitization. |

**Scope note:** Token handling (AUTO-02), no-echo policy (Pitfall 4 in Phase 1 research), and rate-limiting are all Phase 1 concerns carried by the existing code. Phase 2 adds no new secrets, API calls, or authentication paths.

---

## Sources

### Primary (HIGH confidence — verified in this session)

- `src/store.py` (read) — snapshot schema `{date, captured_at, repos:{str_id:{stars}}}` and metadata schema `{updated_at, repos:{str_id:{full_name,description,created_at,html_url}}}` confirmed; `load_metadata` corrupt-file guard pattern confirmed
- `src/collector.py` (read) — `run()` injectable-keyword signature confirmed; Phase 2 wiring pattern derived from existing structure
- `src/config.py` (read) — `SNAPSHOTS_DIR`, `METADATA_PATH` constants confirmed; `REPORTS_DIR`, `SEEN_PATH` additions derived from D-05/D-09
- `tests/test_collector.py` (read) — injectable-fake test pattern for `run()` confirmed; test structure for Phase 2 modules should mirror this
- `tests/test_store.py` (read) — `_make_repo` helper, `tmp_path` injection, class-per-module test structure confirmed as project convention
- `pyproject.toml` (read) — pytest≥9.1.1 confirmed as test runner; no new deps needed
- `.planning/config.json` (read) — `nyquist_validation: false` confirmed (Validation Architecture section omitted); `security_enforcement` absent = enabled
- `.planning/phases/02-velocity-ranking-full-reporting/02-CONTEXT.md` — all locked decisions D-01..D-10 read and incorporated verbatim
- `CLAUDE.md` §Technology Stack, §What NOT to Use — stdlib-only constraint, numeric-id keying, per-date files confirmed

### Secondary (MEDIUM confidence)

- `.planning/REQUIREMENTS.md` — RANK-01..06, REPORT-01..05 requirement text cross-referenced against CONTEXT.md decisions
- `.planning/phases/01-collection-loop/01-CONTEXT.md` — Phase 1 locked decisions (UTC timestamps D-07, numeric-id keying, breakthrough universe D-11) confirmed as upstream constraints

---

## Metadata

**Confidence breakdown:**
- Velocity math per bucket: HIGH — formulas derived directly from CONTEXT.md D-02 and verified snapshot schema
- Snapshot loading/selection: HIGH — pattern derived from store.py conventions
- Cold-start states: HIGH — mechanically follows from "ranking runs after write_snap"
- Seen-store: HIGH — schema and ordering specified in D-09/D-10
- Module names / display format / age floor: LOW — marked ASSUMED; Claude's Discretion items
- Security / sanitization: MEDIUM — standard web input validation practice applied to this context

**Research date:** 2026-06-28
**Valid until:** 2026-09-28 (stable domain — stdlib + locked decisions; changes only if CONTEXT.md is revisited)
