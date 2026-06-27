<!-- GSD:project-start source:PROJECT.md -->
## Project

**GitHub Repo Tracker**

A daily automation that surfaces brand-new and fast-rising AI repositories on GitHub before they hit mainstream social media. It queries the GitHub API every morning, ranks repos by star velocity across four buckets, and writes a clean, scannable markdown digest. Built as a Python script run on a schedule — an early-filtering radar for AI tooling.

**Core Value:** Catch exploding AI repos early — surface the right repositories, ranked by *velocity* (not raw star totals), before they trend elsewhere.

### Constraints

- **Tech stack**: Python — strong GitHub API libraries, easy JSON/data handling, standard for this kind of script.
- **Runtime**: GitHub Actions cron — runs in the cloud for free, no always-on machine needed.
- **Delivery**: Dated markdown file — no UI, no external services in v1.
- **Data**: Velocity requires self-stored daily snapshots; spike/velocity buckets stay empty until enough history accumulates (cold start accepted).
- **Security**: GitHub token via Actions secret / env var only — never echoed or committed.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

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
# Create project with uv
# Add runtime dependency
# Run locally
# pyproject.toml — uv manages this
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
- Start with `GITHUB_TOKEN` (built-in Actions secret, zero setup): gives 1,000 core API req/hr per repo + 30 search req/min — sufficient for daily runs tracking ~200 repos.
- Upgrade to a PAT (`GITHUB_TOKEN_PAT` secret) only if you hit the 1,000 req/hr core ceiling when tracking large repo sets. PAT gets 5,000 core req/hr.
- Either token gets the same search rate limit: 30 req/min.
# seconds_between_requests=0.5 throttles core API calls (~2 req/sec).
# Search has its own stricter limit (30 req/min = 1 per 2s); the safe_search
# wrapper below enforces search-specific pacing via the rate-limit check.
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
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
