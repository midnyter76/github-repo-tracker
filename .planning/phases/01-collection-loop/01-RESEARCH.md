# Phase 1: Collection Loop - Research

**Researched:** 2026-06-27
**Domain:** Python / GitHub Search API / PyGithub / GitHub Actions cron / uv
**Confidence:** HIGH (stack locked in CLAUDE.md; key unknowns verified via Context7 + official docs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01 (FILTER-01, FILTER-03, FILTER-04):** Topic-union half uses 6 LLM-era topics: `topic:llm`, `topic:large-language-models`, `topic:agents`, `topic:rag`, `topic:generative-ai`, `topic:llmops`. No classic-ML topics. No star floor on topic half.
- **D-02 (FILTER-01, FILTER-03):** Keyword-fallback half uses AI terms in name/description with `stars:>=10 fork:false archived:false`. Fresh-friendly low floor. Both halves exclude `fork:false archived:false`.
- **D-03 (FILTER-04):** Topic and keyword lists are configurable constants (not inline). Exact keyword strings, date/star slice boundaries, and idempotency mechanics are Claude's discretion (see below).
- **D-04 (FILTER-02):** Target ~150–300 tracked repos. New-repo discovery via 7d and 30d creation windows. Breakthrough re-fetch ~200 repos/day. All comfortably within GITHUB_TOKEN 1,000 core-req/hr ceiling.
- **D-05 (FILTER-02):** Each search sub-query is date-windowed (and star-banded if needed) to keep `total_count < 1,000`.
- **D-06 (AUTO-01):** Cron fires at `'0 13 * * *'` (13:00 UTC). DST shift accepted.
- **D-07 (DATA-05):** All stored timestamps are UTC ISO 8601.
- **D-08 (AUTO-02, AUTO-03):** Dedicated public GitHub repo (`github-repo-tracker`). Repo is the datastore.
- **D-09 (AUTO-02):** Built-in `GITHUB_TOKEN`. No PAT. Never committed or echoed.
- **D-10 (AUTO-03):** Commit-back via `stefanzweifel/git-auto-commit-action` with `[skip ci]` on commit message.

### Claude's Discretion

- Exact keyword strings in the fallback list
- Precise date/star slice boundaries per sub-query
- Snapshot vs metadata field split (field-level schema)
- Same-day idempotency mechanics (DATA-04)

### Deferred Ideas (OUT OF SCOPE)

- Velocity ranking and 4-bucket scoring (Phase 2)
- Markdown digest formatting (Phase 2)
- Scheduler hardening, gap detection, star-gaming filters, pruning (Phase 3)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-01 | Query GitHub Search API each run via token from env var | PyGithub `Github(auth=Auth.Token(os.environ["GITHUB_TOKEN"]))` constructor; Actions injects via `env:` block |
| DATA-02 | Per-date snapshot of star counts keyed by numeric `repo.id`, committed to repo | `data/snapshots/YYYY-MM-DD.json`, key = `str(repo.id)`, write-then-commit pattern |
| DATA-03 | Current repo metadata stored separately and overwritten each run | `data/metadata.json`, keyed by `str(repo.id)`, full overwrite each run |
| DATA-04 | Idempotent snapshot writes on same-day retry | Atomic write (write-to-temp + rename); upsert-by-id if file exists |
| DATA-05 | All timestamps UTC ISO 8601 | `datetime.now(timezone.utc).isoformat()` throughout |
| FILTER-01 | Combo filter: topic-union query + keyword-in-name/desc fallback, merged by numeric `repo.id` | 6 separate topic queries + 1-2 keyword queries; union via `dict` keyed by `repo.id` |
| FILTER-02 | Each sub-query date-windowed so `total_count < 1,000` | `created:>DATE` qualifier; check `results.totalCount` after first page; add tighter window if needed |
| FILTER-03 | Exclude archived and fork repos; star floor on keyword half | `fork:false archived:false` on both halves; `stars:>=10` on keyword half only |
| FILTER-04 | Topic and keyword lists are configurable constants | Module-level `TOPICS` and `KEYWORDS` lists at top of `collector.py` |
| AUTO-01 | Daily GitHub Actions cron | `schedule: cron: '0 13 * * *'` in workflow YAML |
| AUTO-02 | Token from Actions secret; never committed or echoed | `env: GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}`; secret masked by Actions automatically |
| AUTO-03 | Snapshot + metadata committed back each run | `stefanzweifel/git-auto-commit-action@v5` with `file_pattern: 'data/**'` |
</phase_requirements>

---

## Summary

Phase 1 is a greenfield Python script running on a GitHub Actions cron that (a) discovers AI repos via the GitHub Search API, (b) writes daily snapshot files keyed by numeric `repo.id`, and (c) commits the output back to the repo. The entire stack is pre-locked in CLAUDE.md: Python 3.12, PyGithub 2.9.1, uv via `astral-sh/setup-uv@v8`, `actions/checkout@v4`, and `stefanzweifel/git-auto-commit-action@v5`.

The single most important research finding is that **multiple `topic:` qualifiers in the GitHub REST Search API combine with AND logic — OR between qualifiers is not supported**. This means D-01's 6 LLM-era topics require 6 separate `search_repositories()` calls, with results merged client-side by numeric `repo.id`. Plain keyword OR (`llm OR gpt OR langchain`) within a single query IS supported (max 5 OR/AND/NOT operators per query), enabling the keyword-fallback half to run as 1-2 queries rather than one-per-keyword.

The second important design concern is that Phase 1 has three API paths per run: the **date-windowed search path** (discovery of new repos by creation window, ~22 search page-calls, search rate limit 30/min); the **star-banded established-repo path** (optional Reading B per Open Question #3 — catches old-but-spiking repos, ~12 additional page-calls); and the **core re-fetch path** (refreshing star counts for tracked repos, ~200 `get_repo(id)` calls, core limit 1,000/hr). All paths must be rate-paced; `safe_search` handles the search paths, and PyGithub's built-in `seconds_between_requests=0.5` handles the core path.

**Primary recommendation:** Build one `collector.py` with four functions — `discover_repos()` (date-windowed topic + keyword search path), `discover_established()` (star-banded standing query — Reading B; see Open Question #3), `refresh_tracked()` (core re-fetch path), and `write_snapshot()` (idempotent write). Keep `TOPICS`, `KEYWORDS`, and `BREAKTHROUGH_STAR_BANDS` as module-level constants. Wire up the Actions workflow with a single cron trigger and the auto-commit action.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Repo discovery (search API) | Python script | GitHub Search API | Script issues queries; GitHub evaluates and returns results |
| Star-count re-fetch (tracked repos) | Python script | GitHub Core API | Script calls `get_repo(id)` per tracked repo; different rate limit from search |
| Rate limit pacing (search) | Python script — `safe_search` wrapper | PyGithub `get_rate_limit()` | Search limit (30/min) is stricter than core; needs explicit pre-check before each search call |
| Rate limit pacing (core) | PyGithub built-in | — | `seconds_between_requests=0.5` handles core-API pacing automatically in constructor |
| Snapshot persistence | Python script | Git repo | Script writes JSON; git-auto-commit commits back |
| Scheduling | GitHub Actions cron | — | Fixed UTC cron; no external scheduler needed |
| Secret injection | GitHub Actions | — | Built-in `GITHUB_TOKEN` from Actions context; never touches disk |
| Commit-back | `git-auto-commit-action@v5` | — | Detects changed files; commits as "GitHub Actions" bot |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12 | Runtime | Locked in CLAUDE.md; ships with `ubuntu-latest` Actions runner |
| PyGithub | 2.9.1 | GitHub REST API client | Locked in CLAUDE.md; built-in `GithubRetry`, `seconds_between_requests`, typed objects, numeric-ID `get_repo()` |
| uv | latest via `setup-uv@v8` | Dep management + script runner | Locked in CLAUDE.md; `uv run` needs no venv activation |

[VERIFIED: CLAUDE.md §Technology Stack — all versions locked as authoritative]

### Actions Stack

| Action | Version | Purpose |
|--------|---------|---------|
| `actions/checkout` | v4 | Checkout repo with write credentials |
| `astral-sh/setup-uv` | v8 | Install uv on runner |
| `stefanzweifel/git-auto-commit-action` | v5 | Detect changed files and commit back |

[VERIFIED: CLAUDE.md §Technology Stack]

### Supporting (stdlib only)

| Library | Purpose |
|---------|---------|
| `json` | Read/write snapshot + metadata JSON files |
| `datetime`, `timezone` | UTC timestamp generation and date arithmetic |
| `time` | `time.sleep()` inside `safe_search` rate-limit wait |
| `pathlib` | File path construction for snapshot and metadata files |
| `os` | `os.environ["GITHUB_TOKEN"]` token read |

### Installation

```bash
# Initialize project
uv init github-repo-tracker
cd github-repo-tracker

# Add runtime dependency
uv add "PyGithub==2.9.1"

# Pin Python version
echo "3.12" > .python-version
```

Generates `pyproject.toml`, `uv.lock`, `.python-version`. Run script with:

```bash
uv run src/collector.py
```

[VERIFIED: Context7 /pygithub/pygithub + uv docs]

---

## Architecture Patterns

### System Architecture Diagram

```
GitHub Actions cron (13:00 UTC)
        |
        v
  [checkout@v4]
        |
        v
  [setup-uv@v8]
        |
        v
  [uv run src/collector.py]
        |
        +---> GITHUB_TOKEN (from ${{ secrets.GITHUB_TOKEN }})
        |
        v
  ┌─────────────────────────────────────────────────────┐
  │  collector.py                                       │
  │                                                     │
  │  1. discover_repos()        <---> GitHub Search API │
  │     - 6 topic queries, date-windowed   (30 req/min)  │
  │     - 1-2 keyword queries                          │
  │     - merge by repo.id → candidate set             │
  │                                                     │
  │  1b. discover_established() [Reading B, Open Q#3]  │
  │     - 6 topics x 2 star bands = 12 queries         │
  │     - catches old-but-spiking repos                │
  │     - merge into candidate set                      │
  │                                                     │
  │  2. refresh_tracked()       <---> GitHub Core API  │
  │     - load existing tracked IDs from metadata.json │
  │     - g.get_repo(id) for each    (1,000 req/hr)   │
  │     - union with candidate set                      │
  │                                                     │
  │  3. write_snapshot()                               │
  │     - write data/snapshots/YYYY-MM-DD.json (stars) │
  │     - write data/metadata.json (name, desc, etc.)  │
  └─────────────────────────────────────────────────────┘
        |
        v
  [git-auto-commit-action@v5]
        |
        v
  Commits data/snapshots/ + data/metadata.json
  with message "chore: daily snapshot [skip ci]"
        |
        v
  Repo now has today's snapshot  ← Phase 2 reads these
```

### Recommended Project Structure

```
github-repo-tracker/
├── src/
│   └── collector.py        # single script: discover + refresh + write
├── data/
│   ├── snapshots/          # data/snapshots/YYYY-MM-DD.json (one per day)
│   └── metadata.json       # current repo metadata, overwritten each run
├── .github/
│   └── workflows/
│       └── daily.yml       # cron trigger + uv run + auto-commit
├── pyproject.toml          # uv project config, PyGithub dep
├── uv.lock                 # locked dependency versions
└── .python-version         # "3.12"
```

### Pattern 1: PyGithub Client Construction

```python
# Source: Context7 /pygithub/pygithub changes.md (v2.1.0)
import github
import os

g = github.Github(
    auth=github.Auth.Token(os.environ["GITHUB_TOKEN"]),
    retry=github.GithubRetry(),          # handles 403 + 5xx retries
    seconds_between_requests=0.5,        # ~2 req/sec on core API
)
```

[VERIFIED: Context7 /pygithub/pygithub]

### Pattern 2: safe_search Wrapper

The search API has a separate 30 req/min limit. `safe_search` pre-checks remaining quota before the **first** page of each new query; if exhausted, sleeps to reset. **Subsequent pagination calls** (pages 2-N, fetched lazily during iteration) are NOT pre-checked by this wrapper -- they are protected by PyGithub's built-in `GithubRetry`, which handles 403 rate-limit responses automatically. Each `get_rate_limit()` pre-check uses 1 core API call (negligible).

```python
# Source: CLAUDE.md §Stack Patterns by Variant + Context7 RateLimit docs
import time
from datetime import datetime, timezone

def safe_search(g, query: str, **kwargs):
    """Pre-check search rate limit, sleep to reset if needed, then search."""
    while True:
        rl = g.get_rate_limit()
        if rl.search.remaining > 0:
            break
        reset_utc = rl.search.reset.replace(tzinfo=timezone.utc)
        sleep_sec = (reset_utc - datetime.now(timezone.utc)).total_seconds() + 2
        time.sleep(max(sleep_sec, 2))
    return g.search_repositories(query, **kwargs)
```

[VERIFIED: Context7 /pygithub/pygithub RateLimit.py]

### Pattern 3: get_repo by Numeric ID

`g.get_repo()` accepts either `int` (numeric GitHub repo ID, calls `GET /repositories/{id}`) or `str` (owner/repo, calls `GET /repos/{owner}/{repo}`).

```python
# Source: PyGithub readthedocs (verified: signature is int | str)
repo = g.get_repo(12345678)   # integer → /repositories/12345678
# repo.stargazers_count, repo.full_name, repo.description, etc.
```

[VERIFIED: Context7 /pygithub/pygithub apis.md + PyGithub readthedocs]

### Pattern 4: Topic Query Loop (6 Separate Calls)

Six separate topic queries are issued and merged client-side by `str(repo.id)`. This design is structurally correct for two independent reasons: (1) GitHub's query syntax caps AND/OR/NOT operators at 5 per query -- six topics expressed as `topic:llm OR ... OR topic:llmops` would hit that cap with no room left for `fork:false archived:false` qualifiers; (2) one-query-per-topic keeps each result set visible for individual cap monitoring. [MEDIUM: multiple `topic:` qualifiers likely AND together per community docs; separate-call design is correct regardless of whether qualifier OR is supported]

```python
# Source: GitHub search docs (5-operator cap) + community docs (topic AND-behavior)
TOPICS = [
    "llm",
    "large-language-models",
    "agents",
    "rag",
    "generative-ai",
    "llmops",
]

def discover_via_topics(g, since_date: str) -> dict:
    """Returns dict keyed by str(repo.id)."""
    found = {}
    for topic in TOPICS:
        query = f"topic:{topic} fork:false archived:false created:>{since_date}"
        results = safe_search(g, query)
        # Check cap: log warning if total_count approaches 1,000
        if results.totalCount >= 900:
            # Tighten date window or add star-band split — see Pattern 5a
            pass
        for repo in results:
            found[str(repo.id)] = repo
    return found
```

### Pattern 5: Keyword Fallback Query (1-2 Calls, OR Within Query)

Keyword OR between plain terms IS supported in GitHub REST search (max 5 OR/AND/NOT operators per query). Qualifiers still AND together.

```python
# Source: GitHub search docs (keyword OR syntax verified)
# Configurable constants — adjust after seeing real data
KEYWORDS_SET_A = ["llm", "gpt", "langchain", "transformer", "chatgpt"]
KEYWORDS_SET_B = ["openai", "claude", "gemini", "\"language model\"", "rag"]
KEYWORD_STAR_FLOOR = 10  # stars:>=10 — D-02

def discover_via_keywords(g, since_date: str) -> dict:
    found = {}
    for kw_list in [KEYWORDS_SET_A, KEYWORDS_SET_B]:
        terms = " OR ".join(kw_list)
        query = (
            f"{terms} in:name,description "
            f"stars:>={KEYWORD_STAR_FLOOR} fork:false archived:false "
            f"created:>{since_date}"
        )
        results = safe_search(g, query)
        for repo in results:
            found[str(repo.id)] = repo
    return found
```

Note: If either keyword query's `totalCount >= 900`, tighten `since_date` to a shorter window or add a `stars:<=N` upper band and issue a second call for the upper band.

### Pattern 5a: Established-Repo Discovery (Star-Banded) -- OPEN DESIGN QUESTION

D-04 describes a "breakthrough universe (re-fetched daily) stays ~200." There are two valid readings of how this universe is populated -- see Open Question #3. This pattern implements Reading B (star-banded standing query):

```python
# Star-band constants are configurable (D-03)
# Used only if the planner selects Reading B for breakthrough universe
BREAKTHROUGH_STAR_BANDS = [
    "100..1000",    # emerging -- may start spiking
    "1000..10000",  # established -- large enough to have real velocity signal
]

def discover_established(g) -> dict:
    """Star-banded query for established repos -- no date window needed."""
    found = {}
    for band in BREAKTHROUGH_STAR_BANDS:
        for topic in TOPICS:
            query = f"topic:{topic} stars:{band} fork:false archived:false"
            results = safe_search(g, query)
            for repo in results:
                found[str(repo.id)] = repo
    return found
```

Note: 6 topics x 2 bands = 12 extra search queries (each narrow enough to stay <=1 page). Combined with date-windowed discovery and keyword fallback, total search page-calls remains well within 30 req/min.

### Pattern 6: Core Re-fetch Loop (Tracked Repos)

Phase 2 velocity diffing requires re-fetching star counts for ALL previously tracked repos each day, not just newly discovered ones.

```python
# Source: Context7 /pygithub/pygithub apis.md
def refresh_tracked(g, metadata: dict) -> dict:
    """Re-fetch star counts for all repos already in metadata store."""
    refreshed = {}
    for repo_id_str in metadata.get("repos", {}):
        try:
            repo = g.get_repo(int(repo_id_str))  # core API call
            refreshed[repo_id_str] = repo
        except github.UnknownObjectException:
            # Repo deleted or made private — keep in metadata, mark unavailable
            pass
    return refreshed
```

### Pattern 7: Idempotent Snapshot Write (DATA-04)

```python
# Source: Python docs — pathlib.Path.write_text is a single syscall (atomic on Linux)
import json
from pathlib import Path
from datetime import date, datetime, timezone

SNAPSHOTS_DIR = Path("data/snapshots")
METADATA_PATH = Path("data/metadata.json")

def write_snapshot(repos: dict, run_at: datetime):
    """Write idempotent per-date snapshot and overwrite metadata."""
    date_str = run_at.strftime("%Y-%m-%d")
    snap_path = SNAPSHOTS_DIR / f"{date_str}.json"
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing snapshot to merge (handles same-day retry)
    existing_stars = {}
    if snap_path.exists():
        existing_stars = json.loads(snap_path.read_text()).get("repos", {})

    # Upsert star counts: new run overwrites entries, preserves any not re-fetched
    stars = {**existing_stars, **{rid: {"stars": r.stargazers_count} for rid, r in repos.items()}}

    snapshot = {
        "date": date_str,
        "captured_at": run_at.isoformat(),
        "repos": stars,
    }
    snap_path.write_text(json.dumps(snapshot, indent=2))  # single write = atomic on Linux

    # Metadata: overwrite entirely each run (DATA-03)
    metadata = {
        "updated_at": run_at.isoformat(),
        "repos": {
            rid: {
                "full_name": r.full_name,
                "description": r.description or "",
                "created_at": r.created_at.isoformat(),
                "html_url": r.html_url,
                "topics": r.get_topics(),
            }
            for rid, r in repos.items()
        },
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2))
```

[VERIFIED: Python stdlib pathlib; ASSUMED for atomicity on Linux Actions runner]

### Pattern 8: GitHub Actions Workflow (Complete)

```yaml
# .github/workflows/daily.yml
name: Daily AI Repo Tracker

on:
  schedule:
    - cron: '0 13 * * *'   # D-06: 13:00 UTC = 6am PDT / 5am PST
  workflow_dispatch:        # manual trigger for testing

permissions:
  contents: write           # required by git-auto-commit-action

jobs:
  collect:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4
        # persist-credentials: true is the default — needed for commit-back

      - uses: astral-sh/setup-uv@v8
        with:
          enable-cache: true

      - name: Run collector
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          # Token masked by Actions; never printed by script
        run: uv run src/collector.py

      - name: Commit snapshot
        uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "chore: daily snapshot [skip ci]"
          file_pattern: "data/**"
          # changes_detected output: 'true'/'false' — log in CI if needed
```

**GITHUB_TOKEN self-triggering behavior:** When a workflow pushes using the built-in `GITHUB_TOKEN`, GitHub intentionally does not re-trigger workflows — no infinite loop. The `[skip ci]` commit message is belt-and-suspenders for future PAT upgrade. [VERIFIED: GitHub community docs + WebSearch]

### Pattern 9: Snapshot + Metadata Schema

**`data/snapshots/YYYY-MM-DD.json`** (star counts only, grows 1 file/day):
```json
{
  "date": "2026-06-27",
  "captured_at": "2026-06-27T13:00:05.123456+00:00",
  "repos": {
    "12345678": {"stars": 1500},
    "87654321": {"stars": 234}
  }
}
```

**`data/metadata.json`** (current metadata, full overwrite each run):
```json
{
  "updated_at": "2026-06-27T13:00:05.123456+00:00",
  "repos": {
    "12345678": {
      "full_name": "owner/repo-name",
      "description": "A fast LLM inference engine",
      "created_at": "2024-11-15T10:30:00+00:00",
      "html_url": "https://github.com/owner/repo-name",
      "topics": ["llm", "inference"]
    }
  }
}
```

Key design decisions:
- Star counts are in snapshot (accumulates over days → enables velocity diff in Phase 2)
- Metadata is in separate file (overwritten → always current; Phase 2 joins snapshot + metadata by numeric ID)
- `created_at` in metadata enables RANK-01/02 velocity-by-age calculations in Phase 2
- All timestamps use `datetime.isoformat()` with `timezone.utc` → always UTC ISO 8601

### Anti-Patterns to Avoid

- **Single `topic:llm topic:agents` query:** These AND together — misses repos tagged with only one topic. Must use 6 separate topic queries merged client-side.
- **Keying snapshots by `owner/repo` string:** Repo renames and transfers silently corrupt velocity history. Always key by `str(repo.id)`.
- **Monolithic `snapshots.json`:** Full rewrite on every run, unbounded growth, unreadable git diffs. Use per-date files.
- **`tenacity` for retry:** PyGithub 2.1.0+ ships `GithubRetry` that already handles this. Do not add `tenacity`.
- **`requests` library directly:** Bypasses PyGithub's typed objects, retry, and pagination.
- **Fetching starred paginator for star-count reconstruction:** `repo.get_stargazers()` is prohibitively expensive. Use `repo.stargazers_count` attribute (single API field, no pagination).
- **Unbounded search without `total_count` check:** If `results.totalCount >= 1000`, you are silently missing repos. Always check and add a narrower window.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| API retry on 403/5xx | Custom retry loop with `time.sleep` | `github.GithubRetry()` in constructor | PyGithub handles primary rate limit, secondary rate limit, and 5xx — edge cases are complex |
| HTTP client for GitHub | `requests` / `httpx` session | `PyGithub` | Saves pagination, typed objects, and Auth boilerplate |
| Search rate limit pacing | Fixed `time.sleep(2)` before every search call | `safe_search` pre-check with `g.get_rate_limit().search.remaining` | Fixed sleep wastes time; pre-check is accurate and reactive to actual remaining quota |
| Dependency installation on Actions | Inline pip install / requirements.txt | `uv sync` via `setup-uv@v8` + `pyproject.toml` | 10-100x faster; locked reproducible installs |
| Git commit-back | Manual `git config` + `git commit` shell commands | `stefanzweifel/git-auto-commit-action@v5` | Handles no-op (no changes), bot identity, branch push, and dirty-check gracefully |

---

## Query Rate Budget (Per Run)

| Phase | Call Type | Count | Rate Limit | Time at Limit |
|-------|-----------|-------|------------|---------------|
| Discovery | search page-calls (topic, ~2 pages/query avg) | 6 queries x ~2 = ~12 | 30/min (search) | ~24s pacing |
| Discovery | search page-calls (keyword, ~5 pages/query avg) | 2 queries x ~5 = ~10 | 30/min (search) | ~20s pacing |
| Discovery (Reading B) | search page-calls (star-band, ~1 page/query) | 12 queries x ~1 = ~12 | 30/min (search) | ~24s pacing |
| Discovery | `get_rate_limit()` pre-checks | 8-20 (one per query, not per page) | core (negligible) | -- |
| Re-fetch | `get_repo(id)` x tracked repos | ~200 calls | 1,000/hr (core) | ~100s with 0.5s spacing |
| **Total search page-calls (Reading A)** | -- | **~22** | 30 req/min -> ~44s pacing | Well within budget |
| **Total search page-calls (Reading B)** | -- | **~34** | 30 req/min -> ~68s pacing | Well within budget |
| **Total core calls** | -- | **~208** | 1,000/hr -> 20% used | Well within budget |

**Pagination note:** `search_repositories` returns a `PaginatedList` -- each page of 100 results is a separate search API call counted against the 30 req/min limit. `safe_search` pre-checks the limit only before the first page; `GithubRetry` handles 403s on subsequent pages. Topic queries returning ~200 repos = ~2 pages each; keyword queries returning ~500 repos = ~5 pages each. If any topic's `totalCount >= 900`: add a `created:>DATE` split (2 call-sets instead of 1). Worst case with splits: ~35 search page-calls total -- well within budget.

---

## Common Pitfalls

### Pitfall 1: Combining topic: Qualifiers in One Query
**What goes wrong:** Writing `g.search_repositories("topic:llm topic:agents fork:false")` likely returns only repos tagged with BOTH topics -- shrinks the result set and misses single-topic repos. Even if qualifier OR syntax worked, 6 topics = 5 OR operators = the per-query operator cap, with no room remaining for `fork:false archived:false`.
**Why it happens:** GitHub qualifiers default to AND; the 5-operator-per-query cap makes OR across 6 topics structurally incompatible with other required qualifiers regardless of OR support.
**How to avoid:** One `search_repositories()` call per topic; merge results client-side via `dict` keyed by `str(repo.id)`. This design is correct regardless of whether qualifier OR is supported.
**Warning signs:** Result counts are much smaller than expected; repos with only one LLM topic don't appear.

[MEDIUM: AND-behavior of multiple `topic:` qualifiers from community docs; 5-operator cap from GitHub search docs]

### Pitfall 2: Exceeding 1,000-Result Search Cap
**What goes wrong:** A broad query (e.g., keyword fallback with no date window) returns `total_count = 15000` but GitHub only lets you paginate 1,000 results (10 pages × 100). Repos beyond position 1,000 are silently dropped.
**Why it happens:** GitHub enforces a hard 1,000-item paginator cap per search query regardless of `total_count`.
**How to avoid:** After calling `safe_search()`, check `results.totalCount`. If `>= 900`, log a warning and tighten the `created:` window or add a `stars:<=N` band. Aim for slices of 500–800 results.
**Warning signs:** `results.totalCount` returns a large number; paginating returns exactly 1,000 items and then stops.

[VERIFIED: CLAUDE.md §GitHub API Constraints; GitHub REST docs]

### Pitfall 3: Keying Snapshots by owner/repo String
**What goes wrong:** A repo is renamed or transferred. Its snapshot entries from previous days have key `"old-owner/old-repo"` but today's entry has `"new-owner/new-repo"`. Velocity diff finds no match — the repo appears brand-new every time it is renamed.
**Why it happens:** GitHub repo IDs are permanent; `full_name` is mutable.
**How to avoid:** Always `str(repo.id)` as the snapshot key. Store `full_name` as a display-only field inside the value (in metadata.json).

[VERIFIED: CLAUDE.md §What NOT to Use]

### Pitfall 4: Token Echoed in Logs
**What goes wrong:** `print(f"Using token: {token}")` exposes the token in the Actions log. GitHub Actions masks the literal secret value, but only if the secret was never interpolated into a string or split.
**Why it happens:** Debugging statements, error messages, or CLI args that include the token value.
**How to avoid:** Never reference the token value after reading from env. Pass `github.Auth.Token(os.environ["GITHUB_TOKEN"])` once; never print, log, or format-string the token variable.
**Warning signs:** Actions log shows `***` mask — but some patterns (e.g. base64-encoding) bypass masking.

[VERIFIED: CLAUDE.md §Secrets Policy; GitHub Actions docs]

### Pitfall 5: Same-Day Rerun Truncates Snapshot
**What goes wrong:** Second run writes a fresh empty snapshot (only repos discovered in this run), overwriting the first run's broader result set. Repos discovered in run 1 but missing from run 2's search results (pagination order differs, rate limit throttle, query variance) are lost.
**Why it happens:** Naively doing `snap_path.write_text(json.dumps(fresh_data))` without loading the existing file first.
**How to avoid:** Load existing snapshot → upsert new data on top → write the merged result (Pattern 7). This means run 2 can only ADD or UPDATE entries, never silently delete them.

### Pitfall 6: get_topics() Is a Separate API Call
**What goes wrong:** Calling `repo.get_topics()` inside the per-repo loop makes an extra API call per repo, multiplying core API usage by 2× (200 repos = 200 extra calls).
**Why it happens:** `repo.topics` attribute may not be populated on `RepositorySearchResult` objects; `get_topics()` fetches explicitly.
**How to avoid:** Check if `repo.topics` attribute is available on `RepositorySearchResult` (it may be populated by the search response). If not, defer topic storage or call `get_topics()` only on newly-discovered repos (not in the re-fetch loop). Alternatively, omit topics from Phase 1 — they are not required for velocity computation in Phase 2.

[ASSUMED — behavior of `repo.topics` on RepositorySearchResult objects needs verification at implementation time]

---

## State of the Art

| Old Approach | Current Approach | Impact for This Project |
|--------------|------------------|------------------------|
| `pip install PyGithub` + manual retry | PyGithub 2.9.1 with `GithubRetry` built-in | Zero retry code needed |
| `requirements.txt` + `pip install` in Actions | `uv sync` + `setup-uv@v8` | 10-100x faster CI install |
| Manual `git config + git add + git commit` in shell | `stefanzweifel/git-auto-commit-action@v5` | No-op safety + bot identity built in |
| `PyGithub` < 2.0 untyped API | `from github import Github, Auth` (2.x imports) | Typed objects, named auth, retry support |

**Deprecated patterns (do not use):**
- `from github import Github` with token as positional arg: replaced by `github.Auth.Token` in 2.x
- `GithubRetry` not passed: default retry is enabled in 2.1.0+ but explicitly passing it is clearer
- `time.sleep(2)` between every search call: replaced by `safe_search` pre-check (reactive, not fixed)

---

## Environment Availability

Target execution environment is the **`ubuntu-latest` GitHub Actions runner** (Linux), not the local Windows dev machine. The workflow installs all dependencies at runtime.

| Dependency | Required By | Available on Runner | Notes |
|------------|------------|---------------------|-------|
| Python 3.12 | Runtime | ✓ (installed via uv) | `astral-sh/setup-uv@v8` + `uv python install 3.12` from `.python-version` |
| PyGithub 2.9.1 | GitHub API | ✓ (installed via uv sync) | Listed in `pyproject.toml` |
| uv | Dep management | ✓ (installed by setup-uv@v8) | — |
| GITHUB_TOKEN | Auth + commit-back | ✓ (built-in to every Actions job) | No setup needed; `permissions: contents: write` must be set |
| Git | Commit-back | ✓ (ubuntu-latest ships git) | Used by auto-commit action |

**Local dev note:** Local Windows machine has whatever Python/uv is installed. For local testing: set `GITHUB_TOKEN` env var from a PAT (not the built-in Actions token) and run `uv run src/collector.py`.

**Missing dependencies with no fallback:** None — all dependencies are available on the runner.

---

## Security Domain

Only control that applies: **AUTO-02 (token injection)**. Inputs are entirely public GitHub metadata; no user data, no auth sessions, no encryption needed.

| Control | Implementation |
|---------|---------------|
| Token from secret | `env: GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}` in workflow step — never as a CLI arg or printed |
| No token in committed files | `.gitignore` is moot (no `.env`); token only lives in `os.environ` for script lifetime |
| `permissions: contents: write` | Minimal scope — only what auto-commit-action needs |
| `[skip ci]` on commit message | Prevents commit-back from re-triggering the workflow (belt-and-suspenders; GITHUB_TOKEN already prevents re-trigger) |
| Never echo token | `print` / `logging` calls must not reference the token variable |

ASVS V2/V3/V4/V6 are not applicable — this is a server-side cron with no user sessions, authentication flows, or cryptography.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Keyword OR (`llm OR gpt OR langchain in:name,description`) works in the GitHub REST Search API (not just the web UI) | Pattern 5 / FILTER-01 | If wrong: split into 1 keyword call per term (~5-6 more search calls); still within rate limit |
| A2 | `RepositorySearchResult.topics` attribute is populated from the search response without an extra `get_topics()` call | Pitfall 6 | If wrong: either omit topics from Phase 1 schema or accept the extra API call per newly discovered repo |
| A3 | `pathlib.Path.write_text()` on the Actions runner (Linux) is atomic for the file sizes involved (~50KB) | Pattern 7 / DATA-04 | If wrong: use write-to-temp-then-rename pattern (`Path.rename()` is atomic on same filesystem on Linux) |
| A4 | Popular AI topics (e.g., `agents`, `llm`) with `fork:false archived:false` stay under 1,000 total_count without date windowing | Pattern 4 / FILTER-02 | If wrong: add `created:>DATE` window per topic — need to choose a sensible cutoff (e.g., 2023-01-01) |

---

## Open Questions (RESOLVED)

1. **Does `RepositorySearchResult` include `topics` without a separate `get_topics()` call?**
   - What we know: `repo.get_topics()` always works (extra API call); search result objects may or may not populate `.topics`
   - What's unclear: Search result object attributes vs full Repository object attributes
   - Recommendation: At implementation time, inspect `dir(result)` on first search result, or test with one topic query; if `.topics` is absent, omit from Phase 1 schema (Phase 2 does not require topics for velocity computation)
   - **RESOLVED:** Topics omitted from the Phase 1 snapshot schema entirely (Plan 01-03 Task 2, citing Pitfall 6) — no extra `get_topics()` core call incurred. Phase 2 velocity computation does not require topics.

2. **What are the actual total_count values for the 6 LLM-era topics without date windowing?**
   - What we know: Budget is 1,000 per sub-query; topics like `llm` and `agents` may be popular
   - What's unclear: Whether any topic exceeds 1,000 repos with `fork:false archived:false`
   - Recommendation: First run logs `total_count` for each topic query; if any exceeds 900, add `created:>2023-01-01` window and re-run
   - **RESOLVED:** Resolved at runtime — Plan 01-02's cap-handling logs each `total_count`, warns at the 900 threshold (`TOTAL_COUNT_CAP_WARN`), and narrows the slice automatically. Exact per-topic counts are observed on first run; no hardcoded count is baked into the plan.

3. **Breakthrough Universe: Rolling Accumulation vs Star-Banded Standing Query?**
   - What we know: D-04 says "breakthrough universe (re-fetched daily) stays ~200"; D-05 says sub-queries can be "star-banded where needed." Date-windowed discovery only catches repos within their creation window -- an established repo that starts spiking today is invisible unless it was previously discovered.
   - What's unclear: Whether the ~200-repo breakthrough universe is (A) the rolling accumulation of date-windowed discoveries that age and stay tracked, or (B) a separate star-banded standing query that refreshes the established-repo set each run regardless of creation date
   - Recommendation: Reading (B) aligns better with the "catch exploding repos early" core value and D-05's explicit mention of star-banding as a slicing mechanism. Include the star-banded discovery pass (Pattern 5a) with `BREAKTHROUGH_STAR_BANDS` as a configurable constant. If the user intends Reading (A), explicitly document the cold-start limitation: old-but-spiking repos are invisible until the project has run long enough to have previously discovered them through a creation-date window.
   - **RESOLVED:** User selected Reading (B) — locked as **D-11** in `01-CONTEXT.md`. Implemented as `discover_established()` in Plan 01-02 (star-banded standing query, cap-handled via `split_star_band`), refreshing the established-repo set each run regardless of creation date.

---

## Sources

### Primary (HIGH confidence)
- Context7 `/pygithub/pygithub` — PyGithub `search_repositories` signature, `GithubRetry`, `seconds_between_requests`, `get_rate_limit().search`, `get_repo(int)` via `/repositories/{id}`
- PyGithub readthedocs `github.MainClass.Github.get_repo` — confirmed `int | str` parameter type
- CLAUDE.md §Technology Stack, §GitHub API Constraints, §What NOT to Use — locked stack + constraints (authoritative)

### Secondary (MEDIUM confidence)
- GitHub community discussions (topic qualifier AND-behavior in REST API; GITHUB_TOKEN commits do not self-trigger workflows)
- GitHub search docs `docs.github.com/en/search-github/searching-on-github/searching-for-repositories` — `created:>DATE` qualifier syntax, `topic:` qualifier behavior
- stefanzweifel/git-auto-commit-action README — `permissions: contents: write`, `changes_detected` output, no-op behavior
- uv guides/integration/github — `astral-sh/setup-uv@v8` workflow pattern

### Tertiary (LOW confidence)
- WebSearch claim that "keyword OR is supported in REST API" — mentioned with example `python OR javascript in:name,description`; marked as A1 (assumption) requiring verification at implementation

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — locked in CLAUDE.md with prior research
- Architecture (topic query must be N calls): HIGH — verified via GitHub community docs
- `get_repo(int)` accepting numeric ID: HIGH — verified via Context7 + readthedocs
- Keyword OR support in REST API: MEDIUM/LOW — examples found but not from official REST docs
- Pitfalls: HIGH — derived from locked constraints in CLAUDE.md

**Research date:** 2026-06-27
**Valid until:** 2026-07-27 (stable ecosystem; PyGithub and GitHub API constraints are unlikely to change)
