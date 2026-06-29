# Phase 3: Production Hardening - Research

**Researched:** 2026-06-28
**Domain:** GitHub Actions scheduler resilience, Python datetime/file operations, star-gaming detection heuristics, git workflow automation
**Confidence:** MEDIUM — all four requirements are well-understood technically; HARD-01 has an unresolved community question that introduces MEDIUM uncertainty in the implementation mechanism

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Keepalive (HARD-01)**
- D-01: A **separate `keepalive.yml` workflow** runs monthly via cron — does not rely on daily data commits resetting the 60-day timer (community behavior is ambiguous per STATE.md blocker).
- D-02: The keepalive job **writes a dummy commit** to the repo (a timestamp update) — definitively counts as repo activity, no ambiguity.
- D-03: Dummy commit target is **`.github/keepalive`** — a dedicated file that makes the purpose clear, doesn't pollute `data/` or `reports/`.

**Gap Detection (HARD-02)**
- D-04: Warning is emitted to **stdout (Actions log) only** — not added to the digest.
- D-05: Gap check runs at the **start of `collector.run()`, before any discovery**.

**Star-Gaming Filters (HARD-03)**
- D-06: Specific heuristics and thresholds are **left to planning/research** to determine.
- D-07: Gamed repos are **silently excluded from rankings** before any bucket is populated — no log output, no digest markers.

**Snapshot Pruning (HARD-04)**
- D-08: Retention window is **90 days**.
- D-09: Pruning runs **at the end of every `collector.run()`** after snapshot + report are written.

### Claude's Discretion
- Exact keepalive cron schedule (monthly: first of month, last day, weekly? — within "monthly" intent).
- Whether pruning deletes the oldest file or all files outside the window (on a 90d retention, both produce the same steady-state result).
- Whether the gap-detection threshold (26 hours per HARD-02) is a configurable constant or hardcoded — lean toward configurable per `config.py` pattern.
- Star-gaming heuristic list, thresholds, and whether they apply to the full candidate set or only to ranked entries.

### Deferred Ideas (OUT OF SCOPE)
- Acceleration metric (2nd-derivative star growth) — still not in scope; future phase.
- None raised during Phase 3 discussion — all topics stayed within hardening scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HARD-01 | Scheduled workflow protected against 60-day auto-disable (keepalive + `workflow_dispatch`) | keepalive.yml with every-10-days cron (off-peak, non-round minute) + dummy commit via git-auto-commit-action; `workflow_dispatch` already in daily.yml |
| HARD-02 | Collection gaps detected and warned on (last snapshot older than 26 hours) | `check_gap()` reads `captured_at` from most-recent snapshot JSON; injectable into `collector.run()` as first step |
| HARD-03 | Likely star-gamed repos filtered via configurable heuristics | `filter_gamed()` uses `stargazers_count`/`forks_count` (free from search response, not in snapshots — must read from live object); thresholds in `config.py` |
| HARD-04 | Snapshot files older than retention window pruned to bound repo size | `prune_snapshots()` deletes by filename date; daily.yml must stage deletions (critical gap — see Pitfall 3) |
</phase_requirements>

---

## Summary

Phase 3 adds four orthogonal hardening safeguards to the existing Phase 1+2 pipeline. None require new Python dependencies — all use stdlib, existing PyGithub objects, and the existing GitHub Actions stack.

The most technically subtle requirement is HARD-01. GitHub's 60-day auto-disable triggers when "no repository activity has occurred" in a public repo for 60 days. Commits count as activity; releases and tags do not. Whether commits authored by `GITHUB_TOKEN` (the `github-actions[bot]`) count is **not definitively resolved** by official documentation or community consensus. D-02's dummy-commit approach is the locked decision and plausibly works (bot commits are still commits), but carries MEDIUM confidence. The alternative mechanism — calling the GitHub workflow enable REST API with `permissions: actions: write` — definitively resets the timer and works with GITHUB_TOKEN, and is the approach the current `keepalive-workflow` Marketplace action uses as its default (API mode, not commit mode, since v2). Both mechanisms are documented below; the plan should implement D-02 and note the API approach as an escalation if bot commits prove insufficient after the first 60-day validation window. **The user should confirm the D-02-vs-API choice during planning rather than waiting for a 60-day gamble** — the evidence leans against commit mode (keepalive-workflow v2 abandoned it).

The keepalive cron is set to **every 10 days at 04:23 UTC** (`'23 4 */10 * *'`), not monthly midnight-on-the-1st. Monthly cron at a round minute is the single highest-risk timing choice on GitHub Actions: the platform explicitly documents that scheduled workflows may be delayed or dropped under high load, and top-of-hour runs on common dates (1st of month, midnight) are the most congested. A monthly keepalive has only 12 shots/year; one dropped run eats most of the 60-day budget. Every-10-days at an off-peak, non-round minute gives ~36 runs/year and materially reduces both drop risk and bot-commit ambiguity (more frequent activity events).

HARD-02 has a significant implementation pitfall: GitHub Actions `actions/checkout` sets every file's mtime to the checkout timestamp, making filesystem mtime useless for gap detection. The correct approach reads the `captured_at` field from the most recent snapshot JSON file, with filename sorting (ISO dates are lexicographically comparable) to identify the most recent snapshot without opening every file.

HARD-04 has a critical workflow gap: `stefanzweifel/git-auto-commit-action` with `file_pattern: "data/**"` does NOT stage file deletions. The glob expansion happens at the shell level; deleted files are not in the expanded list. Pruning will delete files in the runner but they will persist in git forever unless the workflow is updated to stage deletions.

**Primary recommendation:** Four new pure-Python functions + one new YAML file; no new dependencies. Fix the daily.yml staging gap before implementing pruning.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Keepalive scheduling (HARD-01) | GitHub Actions (cron) | — | Scheduler lives in the CI platform; Python code has no role |
| Keepalive commit | GitHub Actions (git-auto-commit-action) | — | Same pattern as daily.yml; no Python involvement |
| Gap detection (HARD-02) | Python (collector.run) | — | Must fire before any API quota is spent; reads local filesystem |
| Gaming filter (HARD-03) | Python (collector.run) | — | Operates on in-memory candidate dict; no I/O at filter time |
| Snapshot pruning (HARD-04) | Python (collector.run) | GitHub Actions (staging fix) | Python deletes files; Actions workflow must stage those deletions for git commit |

---

## Standard Stack

No new Python packages are introduced in Phase 3. All implementation uses stdlib and the existing PyGithub install.

### Core (already installed)
| Library | Version | Purpose | Role in Phase 3 |
|---------|---------|---------|-----------------|
| Python stdlib: `pathlib`, `json`, `datetime`, `timedelta` | 3.12 stdlib | File/date operations | Gap detection, pruning, gaming filter |
| `PyGithub` | 2.9.1 | Repo object source | `filter_gamed()` reads `.stargazers_count`, `.forks_count` off existing candidate objects |

### GitHub Actions (existing, mirrored for keepalive.yml)
| Action | SHA | Purpose | Notes |
|--------|-----|---------|-------|
| `actions/checkout@v4` | `11bd71901bbe5b1630ceea73d27597364c9af683` | Checkout for commit-back | Same SHA as daily.yml |
| `astral-sh/setup-uv@v8` | `fac544c07dec837d0ccb6301d7b5580bf5edae39` | Not needed in keepalive.yml | Only daily.yml needs uv |
| `stefanzweifel/git-auto-commit-action@v5` | `8621497c8c39c72f3e2a999a26b4ca1b5058a842` | Dummy commit for keepalive | Same SHA as daily.yml; `file_pattern: ".github/keepalive"` |

### Alternatives Considered

| Approach | Why Not Default |
|----------|----------------|
| GitHub workflow enable REST API (`PUT /repos/{owner}/{repo}/actions/workflows/{id}/enable`, `permissions: actions: write`) | More reliable for HARD-01 (bypasses the bot-commit ambiguity); but D-02 is the locked decision — use commit approach first, escalate to API if 60-day validation fails |
| File mtime for gap detection | Unreliable in GitHub Actions — checkout sets mtime to checkout time, not original file write time |
| `os.remove()` + `add_options: -A` on daily.yml | Valid but requires changing file_pattern from glob to directory path to catch deletions |
| Monthly cron at `'0 0 1 * *'` | Worst-case timing for GitHub scheduled workflow reliability — peak congestion slot with no redundancy (see Pitfall 6) |

---

## Architecture Patterns

### System Architecture Diagram

```
collector.run()
│
├── [NEW] check_gap(now, SNAPSHOTS_DIR)           ← FIRST, before any API call
│     └── reads captured_at from latest *.json (date-parseable stems only)
│         prints WARNING to stdout if delta > GAP_WARN_HOURS
│
├── discover(g)                                    ← unchanged
├── established(g)                                 ← unchanged
├── refresh(g, ids)                                ← unchanged
│
├── union → candidates dict (str id → repo object)
│
├── [NEW] filter_gamed(candidates)                 ← silently removes gamed repos
│     └── compares stargazers_count / forks_count against thresholds
│         (free search-response fields only — see free-attribute whitelist)
│         returns filtered dict (no logging)
│
├── write_snap(filtered_candidates, now)           ← receives filtered set
├── write_meta(filtered_candidates, now)
│
├── compute_buckets(...)                           ← ranks filtered repos
├── classify_and_update(...)
├── write_digest(...)
├── save_seen(...)
│
└── [NEW] prune_snapshots(SNAPSHOTS_DIR, 90, now)  ← LAST, after all writes
      └── deletes *.json files with stem date < cutoff
          caller: git-auto-commit-action must stage the deletions

keepalive.yml (separate workflow)
├── schedule: '23 4 */10 * *'  (every 10 days, 04:23 UTC — off-peak, non-round)
├── run: echo timestamp > .github/keepalive
└── stefanzweifel/git-auto-commit-action
      file_pattern: ".github/keepalive"
      commit_message: "chore: keepalive [skip ci]"
```

### Recommended Project Structure

No new directories required. New files:

```
.github/
├── workflows/
│   ├── daily.yml          # existing — update file staging for deletions (HARD-04)
│   └── keepalive.yml      # NEW — HARD-01

src/
├── config.py              # extend — add HARD-02/03/04 constants
├── collector.py           # extend — wire check_gap, filter_gamed, prune_snapshots
├── gap.py                 # NEW — check_gap function (HARD-02)
│                          # NOTE: planner may prefer folding into store.py
│                          # (CONTEXT.md canonical_refs frame pruning as a store concern)
├── gaming.py              # NEW — filter_gamed function (HARD-03)
└── prune.py               # NEW — prune_snapshots function (HARD-04)
                           # NOTE: planner may prefer folding into store.py

.github/
└── keepalive              # NEW — dummy file updated by keepalive.yml (HARD-01)
```

### Pattern 1: Gap Detection (HARD-02) — Read `captured_at`, Not mtime

**What:** Compare `captured_at` field in latest snapshot vs. wall-clock `now`.
**Why `captured_at` not mtime:** GitHub Actions checkout sets every file's mtime to checkout time; mtime is useless post-checkout. `captured_at` is the authoritative timestamp. [VERIFIED: advisor verification + Actions checkout behavior]
**Why filename sort not `os.listdir` + mtime:** ISO date filenames sort lexicographically; `max(stems)` is O(n) with no I/O until the file is opened.
**Stem filter required:** `max(files, key=lambda p: p.stem)` over `*.json` would pick a non-date file like `backup.json` (`'b' > '2'`), then silently swallow it in the `except` — suppressing real gap warnings. Filter to date-parseable stems first.

```python
# Source: stdlib pattern; [ASSUMED] implementation below
import json
from datetime import datetime
from pathlib import Path

def check_gap(now: datetime, snapshots_dir: Path, warn_hours: float = GAP_WARN_HOURS) -> None:
    """Emit a stdout warning if last collection gap exceeds warn_hours (HARD-02).

    First-run safe: returns silently when no snapshots exist.
    Does not raise — a corrupt/missing captured_at is silently skipped.
    """
    # Filter to date-parseable stems only — avoids non-date files like backup.json
    # shadowing real snapshots when lexicographic max is taken.
    date_files = []
    for p in snapshots_dir.glob("*.json"):
        try:
            datetime.strptime(p.stem, "%Y-%m-%d")
            date_files.append(p)
        except ValueError:
            pass

    if not date_files:
        return  # first run — no prior snapshot exists

    latest = max(date_files, key=lambda p: p.stem)  # lexicographic max is most-recent date
    try:
        data = json.loads(latest.read_text())
        captured_at = datetime.fromisoformat(data["captured_at"])
        delta_hours = (now - captured_at).total_seconds() / 3600
        if delta_hours > warn_hours:
            print(
                f"WARNING: Last snapshot {latest.name} was {delta_hours:.1f}h ago "
                f"(threshold: {warn_hours}h). A collection run may have been missed."
            )
    except (KeyError, ValueError, json.JSONDecodeError):
        pass  # don't crash on malformed snapshot
```

### Pattern 2: Star-Gaming Filter (HARD-03) — Use Free Attributes Only

**What:** Filter `candidates` dict before write/rank, removing repos matching gaming heuristics.

**Free-attribute whitelist — HARD CONSTRAINT for HARD-03 and any future heuristic tuning (D-06):**
Gaming heuristics may ONLY read attributes present in the GitHub search-response JSON. Reading any other attribute triggers a per-repo API call via PyGithub's lazy-fetch, which blows the 30 req/min search limit across 100–500 candidates.

| Attribute | Free from search response | Notes |
|-----------|--------------------------|-------|
| `stargazers_count` | YES [VERIFIED: docs.github.com REST API] | Primary heuristic input |
| `forks_count` | YES [VERIFIED: docs.github.com REST API] | Primary heuristic input |
| `open_issues_count` | YES | Available if future heuristics need it |
| `watchers_count` | YES | Available if future heuristics need it |
| `created_at` | YES | Available for age-based heuristics |
| `pushed_at` | YES | Available for recency heuristics |
| `updated_at` | YES | Available for recency heuristics |
| `topics` | NO — extra API call per repo | Never use in filter_gamed |
| `subscribers_count` | NO — extra API call per repo | Never use in filter_gamed |
| `contributors` | NO — separate API endpoint | Never use in filter_gamed |

**`forks_count` is NOT persisted in snapshots or metadata** (store.py schema stores only `{"stars": ...}`). The filter MUST read it from the live candidate object — there is no stored fallback. This means the filter can only run during the live collection pass (enforced by the integration point: after candidate union, before write_snap).

[VERIFIED: GitHub REST API search response spec includes `forks_count` and `stargazers_count` as required fields — no extra API call]

```python
# Source: [ASSUMED] thresholds; API fields [VERIFIED: docs.github.com REST API search response]
from src.config import (
    GAMING_MIN_STARS,
    GAMING_STAR_FORK_RATIO,
)

def filter_gamed(candidates: dict) -> dict:
    """Silently remove likely-gamed repos from candidate set (HARD-03, D-07).

    Applies only to repos above GAMING_MIN_STARS to avoid false-positives on
    legitimate small repos that haven't attracted forks yet.
    Filter is silent — no print, no log, no digest marker (D-07).

    IMPORTANT: Only reads free search-response attributes (see free-attribute whitelist
    in RESEARCH.md Pattern 2). Never add attributes that trigger PyGithub lazy-fetch.
    """
    clean = {}
    for rid, repo in candidates.items():
        stars = repo.stargazers_count
        forks = repo.forks_count
        if stars < GAMING_MIN_STARS:
            clean[rid] = repo
            continue
        ratio = stars / forks if forks > 0 else float("inf")
        if ratio <= GAMING_STAR_FORK_RATIO:
            clean[rid] = repo
    return clean
```

### Pattern 3: Snapshot Pruning (HARD-04) — Delete by Filename Date

**What:** Delete snapshot files with filename date older than `now - retention_days`.
**Why filename date not mtime:** Same reason as gap detection — mtime is unreliable in Actions.
**Edge case — today's snapshot:** Pruning runs LAST (D-09), after `write_snap`. The cutoff is `now - 90 days`; today's file cannot be pruned by its own run.

```python
# Source: stdlib pattern; [ASSUMED] implementation below
from datetime import date, timedelta
from pathlib import Path

def prune_snapshots(
    snapshots_dir: Path,
    retention_days: int,
    now: datetime,
) -> list[Path]:
    """Delete snapshot files older than retention_days (HARD-04, D-08/D-09).

    Safe to run even when snapshots_dir does not exist (returns []).
    Deletes by filename date — not mtime.
    Returns list of deleted paths (for test assertions).
    """
    if not snapshots_dir.exists():
        return []
    cutoff = (now - timedelta(days=retention_days)).date()
    pruned = []
    for snap_path in snapshots_dir.glob("*.json"):
        try:
            snap_date = date.fromisoformat(snap_path.stem)
            if snap_date < cutoff:
                snap_path.unlink()
                pruned.append(snap_path)
        except ValueError:
            pass  # ignore non-date-named files
    return pruned
```

### Pattern 4: Keepalive Workflow (HARD-01) — Every-10-Days Cron at Off-Peak Time

**What:** Standalone `keepalive.yml` that writes a UTC timestamp to `.github/keepalive` and commits it every 10 days.
**Cron schedule:** `'23 4 */10 * *'` — 04:23 UTC every 10 days. Off-peak time, non-round minute. Gives ~36 runs/year vs. 12 for monthly; if GitHub drops one run, the next fires within 10 days — well inside the 60-day budget. Also increases the frequency of activity events, partially neutralizing the bot-commit-timer ambiguity. (CONTEXT.md discretion: "monthly: first of month, last day, weekly?" — every 10 days is within the spirit of "periodic but not daily".)
**`[skip ci]`:** Required in the commit message. The keepalive commit is a push event; `[skip ci]` prevents any push-triggered CI workflows from running. (daily.yml is schedule-triggered, so it won't trigger on push regardless — but `[skip ci]` is forward-compatible with any future push-triggered workflows.)

```yaml
# Source: mirrors daily.yml pattern; [CITED: stefanzweifel/git-auto-commit-action docs]
name: Keepalive

on:
  schedule:
    - cron: '23 4 */10 * *'  # every 10 days, 04:23 UTC — off-peak, non-round minute
  workflow_dispatch:           # manual trigger for immediate keepalive if needed

permissions:
  contents: write              # required by git-auto-commit-action

jobs:
  keepalive:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2

      - name: Update keepalive timestamp
        run: echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .github/keepalive

      - name: Commit keepalive
        uses: stefanzweifel/git-auto-commit-action@8621497c8c39c72f3e2a999a26b4ca1b5058a842  # v5.0.1
        with:
          commit_message: "chore: keepalive [skip ci]"
          file_pattern: ".github/keepalive"
```

### Pattern 5: daily.yml Deletion Staging Fix (HARD-04 prerequisite)

**The gap:** `stefanzweifel/git-auto-commit-action` with `file_pattern: "data/**"` does NOT stage file deletions. The glob `data/**` expands at the shell level; deleted files are absent from the expanded list. Pruned snapshots vanish from the runner but persist in git. [VERIFIED: git-auto-commit-action entrypoint.sh analysis + git-add documentation]

**The fix (PRIMARY — use this):** Add a shell step between "Run collector" and "Commit snapshot" to explicitly stage deletions:

```yaml
# Insert between "Run collector" and "Commit snapshot" steps in daily.yml
- name: Stage pruned snapshot deletions
  run: |
    DELETED=$(git ls-files --deleted data/ 2>/dev/null)
    if [ -n "$DELETED" ]; then
      git rm $DELETED
    fi
```

`git ls-files --deleted data/` lists tracked files under `data/` that are no longer on disk (i.e., pruned snapshots). `git rm` stages their removal. The subsequent `git-auto-commit-action` step then commits both new files and the staged deletions in one commit.

**Test compatibility:** This primary fix leaves `file_pattern: "data/**"` unchanged. Existing tests that assert on `file_pattern` (e.g., `test_file_pattern_data`, `test_file_pattern_reports` in test_collector.py) continue to pass.

**Alternative (simpler but incompatible with existing tests):** Change `add_options: '-u'` on the auto-commit step AND change `file_pattern` from glob `"data/**"` to directory `"data/ reports/"`. With `-u` and directory paths (not globs), git traverses the index and stages tracked deletions. However, this changes `file_pattern` semantics and **would break existing test assertions on `file_pattern`** — use only if tests are also updated.

### Anti-Patterns to Avoid

- **Using `repo.topics` in filter_gamed:** Each `.topics` access is an extra API call per repo (PyGithub lazy-fetch). With 100–500 candidates, this blows the 30 req/min search limit. Stick to the free-attribute whitelist. [VERIFIED: store.py docstring Pitfall 6]
- **Using file mtime for gap detection:** GitHub Actions `actions/checkout` sets every file's mtime to checkout time. All snapshot files appear identically fresh. [VERIFIED: Actions checkout behavior]
- **Pruning before write_snap:** The 90-day cutoff could in theory match today's date. Pruning must run LAST (D-09) to avoid deleting the current run's fresh snapshot.
- **Hardcoding thresholds inline:** All gaming thresholds, GAP_WARN_HOURS, and SNAPSHOT_RETENTION_DAYS must land in `config.py` per D-03 (Phase 1). The planner must never inline these constants in function bodies.
- **Monthly keepalive at round times:** `'0 0 1 * *'` (midnight, 1st of month) is the worst-case timing for GitHub scheduled reliability. See Pitfall 6.
- **Future heuristics reading non-whitelisted attributes:** Any new gaming heuristic that accesses `topics`, `subscribers_count`, or other lazy-loaded fields triggers per-repo API calls. The whitelist in Pattern 2 is the guard.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Keepalive commit | Custom git Python script | `stefanzweifel/git-auto-commit-action` (already in stack) | Same action already used in daily.yml; zero new complexity |
| Date comparison for pruning | String parsing, timestamp math | `date.fromisoformat(path.stem)` + `timedelta` | ISO date filenames parse directly; stdlib covers all edge cases |
| Retry logic for API keepalive | Custom backoff | GITHUB_TOKEN + `permissions: actions: write` (if escalated) | Built-in GitHub token, no library needed |
| Gaming score ML model | Learned anomaly detector | Simple ratio threshold | False-positive risk is high; configurable constants are tunable without model retraining |

**Key insight:** This entire phase uses zero new dependencies. The hardening is in configuration, function composition, and workflow orchestration — not in new libraries.

---

## Common Pitfalls

### Pitfall 1: Bot-Commit Timer Ambiguity (HARD-01)
**What goes wrong:** D-02's dummy commit uses `GITHUB_TOKEN` (the `github-actions[bot]` committer). Community reports conflict on whether bot commits count as "repository activity" for the 60-day timer. If they don't count, the keepalive.yml provides no protection.
**Why it happens:** GitHub's official docs define inactivity as "no repository activity" but do not specify whether automated commits qualify. [CITED: docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-workflow-runs/disabling-and-enabling-a-workflow] The `gautamkrishnar/keepalive-workflow` repo was disabled by GitHub, eliminating the canonical reference. Community workarounds use both commit-based and API-based approaches.
**How to avoid:** Implement D-02 (dummy commit) as designed. The user should confirm D-02-vs-API during planning, not after a 60-day gamble — the evidence leans toward API mode being more reliable (keepalive-workflow v2 abandoned commit mode). If using commit approach: within the first 60 days of production, verify the workflow remains active. If auto-disabled, escalate to the API approach: `PUT /repos/{owner}/{repo}/actions/workflows/{workflow_id}/enable` with `permissions: actions: write` — this definitively re-enables the workflow and works with GITHUB_TOKEN. [CITED: github.com/marketplace/actions/keep-scheduled-workflow-activity]
**Warning signs:** GitHub sends an email 7 days before disabling. If that email arrives after the first 30 days of production, the commit-based approach is failing and must be replaced.

### Pitfall 2: Gaming Filter Causes Zero-Fork False Positives (HARD-03)
**What goes wrong:** New legitimate repos (day 1–7) naturally have 0 forks. A ratio-based filter with `forks == 0` would exclude all new repos with any significant stars.
**Why it happens:** Star-to-fork ratio is undefined (infinity) for `forks == 0`; a naive implementation `stars / forks` raises ZeroDivisionError, and a guarded `float("inf")` comparison flags every zero-fork repo.
**How to avoid:** Apply the ratio check only when `stars >= GAMING_MIN_STARS`. For repos below that threshold, pass through unconditionally. If `forks == 0 AND stars >= GAMING_MIN_STARS`, the ratio is infinity → gamed. But GAMING_MIN_STARS (default: 200) should be set high enough that a legitimate day-1 repo wouldn't reach it organically within hours. [ASSUMED threshold]

### Pitfall 3: Snapshot Deletions Not Committed to Git (HARD-04)
**What goes wrong:** Python deletes pruned `.json` files from disk. git-auto-commit-action stages `data/**` but the glob excludes deleted files (they don't exist at expansion time). The runner's working tree has the deletions but the commit does not. Next run re-downloads nothing (files aren't in git anyway), but the git history retains every old snapshot file indefinitely.
**Why it happens:** Shell glob expansion is performed before git sees the pathspec. Deleted files are not matched by `data/**`. This is a well-known git-add behavior, not a bug in git-auto-commit-action.
**How to avoid:** Add an explicit deletion-staging step in daily.yml (see Pattern 5 above) BEFORE the git-auto-commit-action step. [VERIFIED: git-auto-commit-action entrypoint.sh + git docs]

### Pitfall 4: Keepalive/Daily Cron Race on Overlapping Days (HARD-01)
**What goes wrong:** On any day where both daily.yml (`'0 13 * * *'`) and keepalive.yml (`'23 4 */10 * *'`) run, both attempt to commit back to the default branch. If they run simultaneously, one will fail with a non-fast-forward push error.
**Why it happens:** `git-auto-commit-action` does a `git push` to the default branch; if another push lands in the same window, the second push fails.
**How to avoid:** The schedules are far enough apart (keepalive at 04:23, daily at 13:00) that same-day race conditions are very unlikely. git-auto-commit-action logs the failure without crashing the workflow. This is an acceptable low-probability failure mode at a every-10-day cadence.

### Pitfall 5: HARD-03 Filter Applied AFTER Snapshot Write (HARD-04 interaction)
**What goes wrong:** If `filter_gamed()` is called after `write_snap`, gamed repos are already persisted to the snapshot. Future velocity calculations (Phase 2 ranking) will include their star history even after they're filtered from rankings. The filter loses its protective effect on historical velocity data.
**Why it happens:** Misplacing the filter call relative to `write_snap` in `collector.run()`.
**How to avoid:** `filter_gamed()` must be called BEFORE `write_snap`, on the unified candidates dict (per CONTEXT.md integration spec: "called after candidate union, before write_snap / rank.compute_buckets"). The code order in `collector.run()` is: discover → union → filter_gamed → write_snap.

### Pitfall 6: Monthly Keepalive Cron at Peak Load Times (HARD-01)
**What goes wrong:** A keepalive cron at `'0 0 1 * *'` (midnight UTC, 1st of month) is the worst-case combination for GitHub Actions scheduling reliability. GitHub explicitly documents that scheduled workflows may be delayed or dropped during high load. Top-of-hour times on common calendar dates (midnight, noon; 1st/15th of month) are the most congested slots. A monthly keepalive has only 12 shots/year; one dropped run means the next fires 30+ days later — leaving as few as ~20 days of margin before the 60-day threshold.
**Why it happens:** It's the most "readable" cron expression, which makes it the most commonly chosen, which makes it the most congested.
**How to avoid:** Use an off-peak, non-round minute on a sub-monthly interval. `'23 4 */10 * *'` (04:23 UTC every 10 days) avoids peak congestion and provides ~36 runs/year. Any single dropped run still leaves 10 days until the next attempt — well inside the 60-day budget. [CITED: GitHub Actions documentation on scheduled workflow delays under high load]

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `gautamkrishnar/keepalive-workflow` commit mode | Separate keepalive.yml with direct commit | Action disabled by GitHub | Implement pattern directly; don't depend on the disabled third-party action |
| Keepalive via commit only | Keepalive via GitHub workflow-enable REST API (API mode) | keepalive-workflow v2 | API approach is more reliable; available as escalation if commit approach fails |

**Deprecated/outdated:**
- `gautamkrishnar/keepalive-workflow` GitHub Action: repo disabled by GitHub Staff (ToS violation); don't reference it in plans. Implement the pattern directly.

---

## Config.py Constants to Add

The following constants must be added to `src/config.py` following the existing grouped-with-comments style. All are Phase 3.

```python
# ---------------------------------------------------------------------------
# Phase 3 — Production Hardening
# ---------------------------------------------------------------------------

# HARD-02: Gap detection
# Gap check fires when the last snapshot's captured_at is older than this.
# 26h gives 2h slack relative to the 24h run interval (D-05, CONTEXT.md).
GAP_WARN_HOURS: float = 26.0

# HARD-03: Star-gaming filters
# Only apply the ratio filter above GAMING_MIN_STARS.
# Repos below this threshold pass through unconditionally (avoids false positives
# on legitimate day-1 rockets with organic traction but no forks yet).
GAMING_MIN_STARS: int = 200          # [ASSUMED] — tune after first 30 days of data
# Stars-to-forks ratio above which a repo is flagged as likely gamed.
GAMING_STAR_FORK_RATIO: float = 50.0 # [ASSUMED] — tune after first 30 days of data

# HARD-04: Snapshot retention
# Files older than this are pruned by prune_snapshots(). 90 days = 3× the
# widest velocity window (30d), providing headroom for missed days + debugging.
SNAPSHOT_RETENTION_DAYS: int = 90    # D-08
```

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `GAMING_MIN_STARS = 200` — repos below this skip the ratio filter | Config constants | Too low: false-positives on legitimate small rockets; too high: gamed large repos slip through. Tune after first 30 days. |
| A2 | `GAMING_STAR_FORK_RATIO = 50.0` — stars/forks ratio above which repo is filtered | Config constants | Too low: some legitimate viral repos filtered; too high: gamed repos slip through. Configurable constant minimizes code-change cost of retuning. |
| A3 | GITHUB_TOKEN (github-actions[bot]) commits count as "repository activity" for the 60-day timer | Pitfall 1 / HARD-01 | If wrong: keepalive.yml provides no protection; must escalate to API approach. Validate within first 60 days. |
| A4 | `keepalive.yml` cron at `'23 4 */10 * *'` does not race with `daily.yml` at `'0 13 * * *'` on the same day | Pattern 4 | If both land at same minute: one push fails. Very unlikely given 8h40m gap; both workflows log cleanly on failure. |
| A5 (prescriptive constraint) | Gaming heuristics may ONLY use search-response-free attributes (whitelist in Pattern 2). `forks_count` and `stargazers_count` are confirmed free [VERIFIED]; all others require explicit verification before adding to filter_gamed. `forks_count` is NOT in snapshot JSON — must read from live candidate object. | Pattern 2 / HARD-03 | If a future heuristic reads a non-whitelisted attribute: triggers per-repo API calls across 100–500 candidates, potentially blowing the 30 req/min search limit. |

---

## Open Questions (RESOLVED)

1. **Does GITHUB_TOKEN (bot) commit count as "repository activity" for the 60-day timer?** (A3 above)
   - What we know: Human commits count. Tags/releases do not. Community conflict on bot commits. The `keepalive-workflow` action moved to API mode (not commit mode) as its v2 default, suggesting commit mode has reliability issues.
   - What's unclear: Official GitHub documentation does not define "repository activity" with enough specificity to settle the question.
   - **RESOLVED:** D-02 (dummy commit approach) is accepted knowingly. The design locks in the dummy-commit implementation (`keepalive.yml` writes a UTC timestamp to `.github/keepalive` and commits it every 10 days). If commit mode fails to reset the timer, the API escalation path documented below is the confirmed fallback. **Day-55 monitoring reminder:** GitHub emails 7 days before auto-disabling a workflow — monitor at day 55 of production. If disabled, apply the API escalation immediately.

   **Escalation pattern (API approach, if commit approach fails at day 55):**
   ```yaml
   # Replace the "Update keepalive timestamp" + "Commit keepalive" steps with:
   - name: Keep workflow alive via API
     uses: actions/github-script@v7
     with:
       script: |
         await github.rest.actions.enableWorkflow({
           owner: context.repo.owner,
           repo: context.repo.repo,
           workflow_id: 'daily.yml',
         });
   ```
   Requires `permissions: actions: write` (already in the locked decision). No commit, no ambiguity.

2. **Is the repo public or private?**
   - What we know: Repo has no remote configured yet (local-only). The 60-day auto-disable only affects public repos per GitHub docs.
   - What's unclear: The repo's eventual visibility on GitHub.
   - **RESOLVED:** Implementing keepalive regardless is harmless and forward-compatible with a future visibility change. No action required — 03-02 proceeds as planned.

---

## Environment Availability

Step 2.6: SKIPPED — Phase 3 adds Python functions and one YAML file. No external tools beyond the existing GitHub Actions stack (checkout, uv, git-auto-commit-action) are needed. No new services or databases.

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | — |
| V3 Session Management | No | — |
| V4 Access Control | No | — |
| V5 Input Validation | Yes (low severity) | `date.fromisoformat(path.stem)` with `try/except ValueError` in pruning; JSON parse with `try/except` in gap detection |
| V6 Cryptography | No | — |

### Known Threat Patterns for Phase 3 Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Keepalive commit echoes GITHUB_TOKEN in workflow logs | Information Disclosure | Do not reference `secrets.*` in `run:` steps; timestamp echo has no token reference |
| Gaming filter thresholds manipulated via config.py PR | Tampering | Thresholds are code-reviewed like any other constant; no special concern |
| Pruning deletes today's snapshot | Denial of Service | Pruning runs LAST (D-09); cutoff date is 90 days in the past; today's file cannot be matched |

---

## Sources

### Primary (HIGH confidence)
- `src/collector.py` (project codebase) — injectable callable pattern for check_gap, filter_gamed, prune_snapshots integration points
- `src/config.py` (project codebase) — grouped-with-comments constant style, existing constants to extend
- `.github/workflows/daily.yml` (project codebase) — SHA-pinned action versions for keepalive.yml to mirror
- `src/store.py` (project codebase) — snapshot schema (`captured_at` field), `SNAPSHOTS_DIR` path constant; confirmed `forks_count` NOT stored in snapshot JSON
- [VERIFIED: docs.github.com REST API] — `forks_count` and `stargazers_count` are required fields in the search repositories response (no extra API call required)
- [CITED: stefanzweifel/git-auto-commit-action entrypoint.sh] — `git add ${INPUT_ADD_OPTIONS} ${INPUT_FILE_PATTERN_EXPANDED[@]}` confirms glob expansion excludes deleted files

### Secondary (MEDIUM confidence)
- [CITED: docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-workflow-runs/disabling-and-enabling-a-workflow] — "scheduled workflows are automatically disabled when no repository activity has occurred in 60 days"; commits count, tags do not; scheduled workflows may be delayed or dropped under high load
- [CITED: github.com/marketplace/actions/keep-scheduled-workflow-activity] — `permissions: actions: write` + `${{ github.token }}` confirms GITHUB_TOKEN can call the workflow-enable API; API approach is the reliable alternative to commits
- [CITED: github.com/marketplace/actions/keepalive-workflow] — v2 switched from commit mode to API mode as default, suggesting commit mode has reliability issues

### Tertiary (LOW confidence — see Assumptions Log)
- Community discussion: github.com/orgs/community/discussions/57858 — "only new commits qualify as 'activity'; creating release tags does not" — but does not address bot vs human commits
- Community discussion: github.com/orgs/community/discussions/184653 — workflow-generated commits used as workaround by some users, but no authoritative confirmation
- Gaming heuristic thresholds (GAMING_MIN_STARS = 200, GAMING_STAR_FORK_RATIO = 50.0) — domain judgment, not empirically validated; tagged [ASSUMED] throughout

---

## Metadata

**Confidence breakdown:**
- HARD-01 (keepalive mechanism): MEDIUM — implementation pattern is clear; whether bot commits reset the timer is genuinely unresolved; every-10-days cron reduces (but doesn't eliminate) the risk of dropped runs
- HARD-02 (gap detection): HIGH — `captured_at` + filename sort (with stem filter) is unambiguous; mtime pitfall is verified
- HARD-03 (gaming filter): MEDIUM-HIGH for implementation pattern (free attributes confirmed, whitelist documented); LOW for threshold values (assumed, not empirically calibrated)
- HARD-04 (pruning): HIGH for Python logic; HIGH for the deletion-staging gap (verified through git-add docs)

**Research date:** 2026-06-28
**Valid until:** 2026-09-28 (90 days — all stable stdlib/Actions patterns; GitHub inactivity policy wording unlikely to change)
