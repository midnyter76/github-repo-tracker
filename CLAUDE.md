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
## Stack Gotchas (non-derivable)

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `tenacity` for retry | PyGithub 2.1.0+ ships `github.GithubRetry()` that already handles 403 primary/secondary rate limit errors and 5xx responses. Adding tenacity is redundant for PyGithub calls. | `Github(retry=github.GithubRetry(), seconds_between_requests=0.5)` constructor args |
| `requests` directly | Gives you no benefit over PyGithub for this use case; you'd reimplement pagination, typed objects, and rate-limit parsing | `PyGithub` |
| Storing snapshots keyed by `owner/repo` string | Repo renames and transfers silently break velocity continuity and the 🆕 dedup flag — a transferred repo looks brand-new | Key snapshots by the numeric GitHub repo `id` (exposed on every `repo` object as `repo.id`); store `owner/repo` as a display-only field alongside it |
| Monolithic `snapshots.json` | All-history-in-one-file grows unbounded, rewrites entirely each run, and produces noisy git diffs | Per-date files: `data/snapshots/YYYY-MM-DD.json`; velocity = load today's file + file from N days ago |
| `PyGithub` < 2.0 | Pre-2.0 API is untyped, no Auth module, no built-in retry; old tutorials show 1.x patterns | `from github import Github, Auth` (2.x import paths) |
| Fetching all results via a single unbounded search | GitHub search returns at most **1,000 results per query** (10 pages × 100 per page), regardless of `total_count`. AI/ML topics return thousands of matches — you'll miss repos. | Slice queries into windows: per-topic (`topic:llm`, `topic:machine-learning`, `topic:ai`), per-creation-date range, and/or per-star band to stay under the 1,000-result cap per slice |

## GitHub API Constraints (Critical)
| Constraint | Value | Impact |
|------------|-------|--------|
| Search results per query (max retrievable) | **1,000** (10 pages x 100) | Must slice into sub-queries by topic/date/star band |
| Repositories scanned per search | ~4,000 (per GitHub docs; approximate) | GitHub narrows its candidate set before returning results; AI/ML topic pools far exceed this |
| Search rate limit — authenticated (PAT or GITHUB_TOKEN) | 30 req/min | ~2s natural spacing; `safe_search` wrapper checks `rl.search.remaining` before each call |
| Core API rate limit — GITHUB_TOKEN in Actions | 1,000 req/hr | Sufficient for <900 repo refreshes/day; upgrade to PAT beyond that |
| Core API rate limit — PAT | 5,000 req/hr | Handles up to ~4,900 repo refreshes/day |

Token strategy: start with `GITHUB_TOKEN` (built-in Actions secret); upgrade to a PAT (`GITHUB_TOKEN_PAT` secret) only if the 1,000 req/hr core ceiling is hit. Either token gets the same 30 req/min search limit.
<!-- GSD:stack-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->
