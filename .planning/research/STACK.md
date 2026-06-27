# Stack Research

**Domain:** Daily Python automation — GitHub API velocity tracker / markdown report generator
**Researched:** 2026-06-26
**Confidence:** HIGH (all versions verified against PyPI and official docs)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12 | Runtime | LTS, ships with `ubuntu-latest` Actions runner (Ubuntu 24.04), well-supported by all target libraries; 3.13 available but offers no benefit here |
| PyGithub | 2.9.1 | GitHub REST API client | Typed, object-oriented wrapper around GitHub API v3; built-in `GithubRetry` (since 2.1.0), `seconds_between_requests` throttling, and `get_rate_limit()` — covers search + core API with no additional retry library needed |
| uv | latest (via `astral-sh/setup-uv@v8`) | Dependency management + script runner | Resolves deps 10-100x faster than pip, manages `.python-version`, and `uv run script.py` runs the script without an explicit venv activate step; 2026 greenfield standard |

### Supporting Libraries (stdlib only — no extra installs needed for core logic)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `json` | stdlib | Read/write per-date snapshot files | Always — no third-party dep needed for structured JSON |
| `datetime` | stdlib | Date arithmetic for velocity windows (7d, 30d, 24h) | Always |
| `time` | stdlib | `time.sleep()` between search calls to stay under 30 req/min | Always — pre-check `g.get_rate_limit().search.remaining` and sleep to reset if near 0 |
| `pathlib` | stdlib | File paths for snapshot store and report output | Always |
| `collections` | stdlib | `defaultdict`, `Counter` for aggregating snapshot diffs | Always |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `astral-sh/setup-uv@v8` | GitHub Actions step to install uv | Latest tagged release is v8.2.0; pin to SHA for supply-chain safety in production |
| `actions/checkout@v4` | Checkout repo in Actions | Required with `persist-credentials: true` (default) for the commit-back step |
| `stefanzweifel/git-auto-commit-action@v5` | Commit snapshots + report back to repo | Detects changed files, commits as "GitHub Actions" bot; requires `contents: write` permission on GITHUB_TOKEN |

## Installation

```bash
# Create project with uv
uv init github-repo-tracker
cd github-repo-tracker

# Add runtime dependency
uv add PyGithub==2.9.1

# Run locally
uv run tracker.py
```

```toml
# pyproject.toml — uv manages this
[project]
name = "github-repo-tracker"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "PyGithub==2.9.1",
]
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| PyGithub 2.9.1 | `httpx` + raw REST calls | Only if you need async or want zero abstraction; for a sync daily cron, PyGithub's typed objects and built-in retry save 200+ lines |
| PyGithub 2.9.1 | `gidgethub` 5.4.0 | Only if the script were async (e.g., running in an async web server context); async provides no benefit for a once-daily batch run |
| PyGithub 2.9.1 | GitHub GraphQL v4 | Better for batching star-count refreshes on 1,000+ tracked repos in a single query; use as an optimization later, not as the default |
| Per-date JSON files | SQLite | Use SQLite only if you need SQL filtering across thousands of repos or complex aggregations; per-date JSON keeps git diffs readable and loads in milliseconds for 100–500 repos |
| Per-date JSON files | Monolithic `snapshots.json` (all dates in one file) | Never: rewrites the whole file on every run, produces unreadable git diffs, and loads all history to read two dates |
| `stefanzweifel/git-auto-commit-action` | `actions/cache` | Cache expires in 7 days — breaks velocity windows. Also can't read-then-write in one workflow run. Not suitable for mutable state |
| `stefanzweifel/git-auto-commit-action` | `actions/upload-artifact` / `actions/download-artifact` | Artifacts within a run are fine, but cross-run downloads require the previous run ID via API — operational complexity for no benefit over a commit |
| uv | pip + requirements.txt | pip + `actions/setup-python@v5` is a valid minimal alternative if the team is unfamiliar with uv; switch if CI environment doesn't permit uv |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `tenacity` for retry | PyGithub 2.1.0+ ships `github.GithubRetry()` that already handles 403 primary/secondary rate limit errors and 5xx responses. Adding tenacity is redundant for PyGithub calls. | `Github(retry=github.GithubRetry(), seconds_between_requests=0.5)` constructor args |
| `requests` directly | Gives you no benefit over PyGithub for this use case; you'd reimplement pagination, typed objects, and rate-limit parsing | `PyGithub` |
| Storing snapshots keyed by `owner/repo` string | Repo renames and transfers silently break velocity continuity and the 🆕 dedup flag — a transferred repo looks brand-new | Key snapshots by the numeric GitHub repo `id` (exposed on every `repo` object as `repo.id`); store `owner/repo` as a display-only field alongside it |
| Monolithic `snapshots.json` | All-history-in-one-file grows unbounded, rewrites entirely each run, and produces noisy git diffs | Per-date files: `data/snapshots/YYYY-MM-DD.json`; velocity = load today's file + file from N days ago |
| `PyGithub` < 2.0 | Pre-2.0 API is untyped, no Auth module, no built-in retry; `pip install PyGithub` will give you 2.x today but old tutorials show 1.x patterns | `from github import Github, Auth` (2.x import paths) |
| Fetching all results via a single unbounded search | GitHub search returns at most **1,000 results per query** (10 pages × 100 per page), regardless of `total_count`. AI/ML topics return thousands of matches — you'll miss repos. | Slice queries into windows: per-topic (`topic:llm`, `topic:machine-learning`, `topic:ai`), per-creation-date range, and/or per-star band to stay under the 1,000-result cap per slice |

## Stack Patterns by Variant

**For GitHub Actions — token choice:**
- Start with `GITHUB_TOKEN` (built-in Actions secret, zero setup): gives 1,000 core API req/hr per repo + 30 search req/min — sufficient for daily runs tracking ~200 repos.
- Upgrade to a PAT (`GITHUB_TOKEN_PAT` secret) only if you hit the 1,000 req/hr core ceiling when tracking large repo sets. PAT gets 5,000 core req/hr.
- Either token gets the same search rate limit: 30 req/min.

**For rate-limit safety in search loops:**
```python
import time
import github
from datetime import datetime, timezone
from github import Github, Auth

# seconds_between_requests=0.5 throttles core API calls (~2 req/sec).
# Search has its own stricter limit (30 req/min = 1 per 2s); the safe_search
# wrapper below enforces search-specific pacing via the rate-limit check.
g = Github(
    auth=Auth.Token(token),
    retry=github.GithubRetry(),      # handles 403 + 5xx automatically
    seconds_between_requests=0.5,    # core API baseline throttle
)

def safe_search(g, query, sort="stars", order="desc"):
    rl = g.get_rate_limit()
    if rl.search.remaining < 2:
        reset_seconds = (rl.search.reset - datetime.now(timezone.utc)).total_seconds()
        time.sleep(max(reset_seconds + 1, 0))
    return g.search_repositories(query=query, sort=sort, order=order)
```

**For snapshot storage — per-date JSON pattern:**
```
data/
  snapshots/
    2026-06-25.json   # {"12345678": {"full_name": "owner/repo", "stars": 1200}, ...}
    2026-06-26.json
reports/
  2026-06-26.md
```
Velocity = `today["id"].stars - past_file["id"].stars` where past file is the closest available date at or before the target lookback window.

**For the commit-back workflow (GitHub Actions):**
```yaml
permissions:
  contents: write

steps:
  - uses: actions/checkout@v4

  - uses: astral-sh/setup-uv@v8

  - name: Run tracker
    env:
      GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    run: uv run tracker.py

  - uses: stefanzweifel/git-auto-commit-action@v5
    with:
      commit_message: "chore: daily snapshot and report [skip ci]"
      file_pattern: "data/snapshots/*.json reports/*.md"
```
The `[skip ci]` suffix prevents the bot commit from re-triggering the cron workflow.

**For searching AI repos — query slicing to bypass the 1,000-result cap:**
Run multiple narrow queries and deduplicate by repo `id`:
```
topic:llm created:>2026-06-19                   # brand-new LLM repos (7d)
topic:machine-learning created:>2026-06-19      # brand-new ML repos (7d)
topic:ai created:>2026-05-27                    # brand-new AI repos (30d)
topic:llm stars:>50 pushed:>2026-06-25          # active LLM repos (24h spike / 30d velocity)
```
Deduplicate by `repo.id` after collecting all pages.

**For markdown report generation:**
Use plain Python f-strings and `str.join`. No external library needed:
```python
from pathlib import Path
from datetime import date

def write_report(buckets: dict, path: Path):
    today = date.today().isoformat()
    lines = [f"# AI Repo Velocity Report — {today}\n"]
    for bucket_name, repos in buckets.items():
        lines.append(f"\n## {bucket_name}\n")
        for repo in repos:
            new_flag = " 🆕" if repo["is_new"] else ""
            lines.append(
                f"- [{repo['full_name']}]({repo['html_url']}){new_flag} — "
                f"stars {repo['stars']:,} (+{repo['velocity']:+,} in window) — {repo['description']}\n"
            )
    path.write_text("".join(lines), encoding="utf-8")
```

## Version Compatibility

| Package | Python Version | Notes |
|---------|---------------|-------|
| PyGithub 2.9.1 | >=3.8 | Tested and released against 3.12; no issues |
| tenacity 9.1.4 | >=3.10 | Not in this stack — documented here only to note it requires 3.10+ if ever added |
| astral-sh/setup-uv@v8 | any | Manages Python version via `uv python install` or `.python-version` file |

## GitHub API Constraints (Critical)

| Constraint | Value | Impact |
|------------|-------|--------|
| Search results per query (max retrievable) | **1,000** (10 pages x 100) | Must slice into sub-queries by topic/date/star band |
| Repositories scanned per search | ~4,000 (per GitHub docs; approximate) | GitHub narrows its candidate set before returning results; AI/ML topic pools far exceed this |
| Search rate limit — authenticated (PAT or GITHUB_TOKEN) | 30 req/min | ~2s natural spacing; `safe_search` wrapper checks `rl.search.remaining` before each call |
| Core API rate limit — GITHUB_TOKEN in Actions | 1,000 req/hr | Sufficient for <900 repo refreshes/day; upgrade to PAT beyond that |
| Core API rate limit — PAT | 5,000 req/hr | Handles up to ~4,900 repo refreshes/day |

## Sources

- PyGithub PyPI — version 2.9.1 confirmed as latest on PyPI
- [PyGithub GitHub repo changelog](https://github.com/pygithub/pygithub/blob/main/doc/changes.md) — `GithubRetry`, `seconds_between_requests`, `get_rate_limit()` APIs verified
- [PyGithub RateLimit object docs](https://pygithub.readthedocs.io/en/latest/github_objects/RateLimit.html) — `.search.remaining` / `.search.reset` access confirmed for 2.x
- [GitHub REST API — search repositories](https://docs.github.com/en/rest/search/search?apiVersion=2022-11-28#search-repositories) — 1,000-result cap, ~4,000 scan limit, 30 req/min authenticated confirmed
- [GitHub REST API — rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) — GITHUB_TOKEN 1,000/hr, PAT 5,000/hr confirmed
- [astral-sh/setup-uv GitHub Marketplace](https://github.com/marketplace/actions/astral-sh-setup-uv) — v8.2.0 latest confirmed
- [stefanzweifel/git-auto-commit-action](https://github.com/stefanzweifel/git-auto-commit-action) — v5 current, `contents: write` permission requirement confirmed
- [uv GitHub Actions guide](https://docs.astral.sh/uv/guides/integration/github/) — recommended workflow pattern verified
- gidgethub PyPI — 5.4.0 latest (June 2025)
- tenacity PyPI — 9.1.4 latest (requires Python 3.10+)
- Context7 `/pygithub/pygithub` — search, rate limit, and pagination docs fetched and verified

---
*Stack research for: GitHub AI repo velocity tracker (Python daily cron on GitHub Actions)*
*Researched: 2026-06-26*
