# Architecture Research

**Domain:** Daily batch data pipeline — GitHub API → snapshot store → velocity ranking → markdown report
**Researched:** 2026-06-26
**Confidence:** HIGH (pipeline architecture, Python module design); MEDIUM (GitHub Actions TTL figures)

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     GitHub Actions Cron                          │
│  Triggers once daily — stateless runner, no persistent FS       │
├─────────────────────────────────────────────────────────────────┤
│                    Orchestrator (main.py)                        │
│  1. Pull persisted data from repo (git pull already done)        │
│  2. Run pipeline stages in order                                 │
│  3. Commit + push updated data back to repo                      │
├───────────────┬─────────────────┬──────────────┬────────────────┤
│   Fetcher     │ Velocity Engine │   Ranker     │   Renderer     │
│ (github API)  │ (diff snapshots)│ (4 buckets)  │ (markdown)     │
├───────────────┴─────────────────┴──────────────┴────────────────┤
│                      Data Layer (repo files)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  Snapshot    │  │   Metadata   │  │     Seen Store       │   │
│  │  Store       │  │   Store      │  │  (dedup / 🆕 flag)   │   │
│  │ data/snaps/  │  │ data/meta/   │  │  data/seen.json      │   │
│  │ YYYY-MM-DD   │  │ current.json │  │                      │   │
│  │ .json        │  │              │  │                      │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Module |
|-----------|----------------|--------|
| Fetcher | Query GitHub Search API for AI repos; handle pagination and rate limits | `fetcher.py` |
| Snapshot Store | Read/write daily star count files; key on numeric repo ID | `snapshot_store.py` |
| Metadata Store | Overwrite current display metadata (name, description, topics) each run | `metadata_store.py` |
| Velocity Engine | Diff today's snapshot against prior snapshots to compute deltas | `velocity.py` |
| Ranker | Apply 4-bucket logic; gracefully degrade if history is missing | `ranker.py` |
| Seen Store | Track which repo IDs have been reported; power the 🆕 flag | `seen_store.py` |
| Renderer | Format ranked buckets + seen-store state into dated markdown | `renderer.py` |
| Orchestrator | Wire all stages; owns the git commit-back at the end | `main.py` |
| Scheduler | GitHub Actions workflow YAML; sets secrets, cron, permissions | `.github/workflows/tracker.yml` |

## Recommended Project Structure

```
github_tracker/
├── __init__.py
├── config.py           # Constants, env vars (GITHUB_TOKEN, DATA_DIR, etc.)
├── fetcher.py          # GitHub Search API; returns list of repo dicts
├── snapshot_store.py   # Read/write data/snapshots/YYYY-MM-DD.json
├── metadata_store.py   # Read/write data/metadata/current.json
├── velocity.py         # Compute 24h delta, 30d delta, age-proxy fallback
├── ranker.py           # 4-bucket sort; skip buckets when history absent
├── seen_store.py       # Load/update data/seen.json; idempotent 🆕 logic
├── renderer.py         # Produce reports/YYYY-MM-DD.md string
└── main.py             # Orchestrator: run pipeline, then git commit-back

data/
├── snapshots/          # One file per day — append-only time series
│   └── 2026-06-26.json
├── metadata/
│   └── current.json    # Overwritten each run — display fields only
└── seen.json           # Cumulative seen-repo registry

reports/
└── 2026-06-26.md       # One dated report per run

.github/
└── workflows/
    └── tracker.yml     # Cron schedule, secret injection, permissions
```

### Structure Rationale

- **data/snapshots/**: One file per run date keeps files small, eliminates merge conflicts (each run creates a new file), and produces clean git diffs. No historical files are ever rewritten.
- **data/metadata/current.json**: Separates mutable display fields (name, description, topics) from the immutable time-series. Current metadata is overwritten every run, keeping the snapshot store lean.
- **Flat data/ directory in the repo root**: Co-locates code and data for simplicity in phase 1. Migrate to an orphan `data` branch later if commit history becomes noisy.
- **reports/ at repo root**: Makes daily outputs discoverable in the GitHub UI without navigating into source.

## Data Models

### Snapshot File — `data/snapshots/YYYY-MM-DD.json`

```json
{
  "schema_version": 1,
  "date": "2026-06-26",
  "repos": {
    "12345678": 4201,
    "87654321": 892
  }
}
```

Key: numeric GitHub repository `id` (integer, cast to string for JSON). Value: star count at time of fetch.

**Why numeric ID, not `owner/repo`:** GitHub repo `full_name` changes on rename or ownership transfer. If you key on `owner/repo`, a rename silently creates a gap in the time-series (old key disappears, new key starts from zero stars). The numeric `id` is permanent. Store `full_name` only in the metadata store as a display field that gets updated each run.

### Metadata File — `data/metadata/current.json`

```json
{
  "schema_version": 1,
  "updated": "2026-06-26",
  "repos": {
    "12345678": {
      "full_name": "owner/repo",
      "description": "Fast LLM inference engine",
      "topics": ["llm", "inference"],
      "created_at": "2026-06-20T00:00:00Z",
      "language": "Python"
    }
  }
}
```

Overwritten each run. Velocity engine joins this with snapshot diffs to produce enriched repo records.

### Seen Store — `data/seen.json`

```json
{
  "schema_version": 1,
  "repos": {
    "12345678": {
      "first_reported": "2026-06-26",
      "report_count": 1
    }
  }
}
```

Updated at the end of each run, after the report is written. This ordering is important for idempotency (see below).

## Architectural Patterns

### Pattern 1: Lean Time-Series, Separate Metadata

**What:** The snapshot store records only `{id: star_count}` per day. All display metadata lives in a separate file overwritten each run.

**When to use:** Whenever a store grows incrementally over months/years. Duplicating description and topics into every daily snapshot would bloat the repo and make schema changes painful.

**Trade-offs:** Requires a join at read time (snapshot + metadata). Trivial in Python (`dict.get(repo_id)`). No downside for this scale.

### Pattern 2: Graceful Degradation for Cold Start

**What:** Each velocity bucket requires a specific amount of history. The system checks whether the required prior snapshot exists before computing a bucket; if absent, it either falls back to a proxy or omits the bucket with an explanatory note.

**Cold-start rules per bucket:**

| Bucket | Requires | Day 1 Fallback |
|--------|----------|----------------|
| Brand New Weekly (top 10) | `created_at` only | Full — stars divided by `age_in_days` as velocity proxy |
| Brand New Monthly (top 5) | `created_at` only | Full — same proxy |
| Breakthrough 24h Spike (top 10) | Yesterday's snapshot | Omit bucket; note "Available after 2 days of data" |
| Breakthrough 30d Velocity (top 10) | Snapshot from 30 days prior | Omit bucket; note "Available after 30 days of data" |

The "velocity proxy" for brand-new repos on day 1: `velocity_proxy = current_stars / max(age_days, 1)`. This is a reasonable stand-in until true deltas are available.

**Trade-offs:** Reports are thinner in the first 30 days. Acceptable and expected per PROJECT.md.

### Pattern 3: Idempotent Runs

**What:** Re-running the pipeline on the same date produces the same output. Two sources of non-idempotency to handle:

**Snapshot file:** If `data/snapshots/YYYY-MM-DD.json` already exists, overwrite it with a fresh fetch. Star counts may have changed slightly intra-day, but the overwrite is safe and produces a consistent final state.

**Report file:** Overwrite `reports/YYYY-MM-DD.md` unconditionally. Same-day retries regenerate the same content.

**Seen store — the subtle case:** If run 1 marks a batch of repos as `first_reported: today` and flags them 🆕, then run 2 (same day) must also flag them 🆕 — not treat them as "already seen and therefore returning." Rule: **a repo with `first_reported == today` is still 🆕 regardless of retry count.** Concretely: when the renderer checks "is this new?", the condition is `first_reported == today`, not `report_count == 1`. This ensures same-day retries produce identical reports.

**Git commit:** Check whether data files actually changed before committing. Use `git diff --quiet` and skip the commit if there is nothing to push. This prevents noise commits and avoids issues if the Actions runner is ever triggered twice.

### Pattern 4: Commit-Back Persistence

**What:** After each pipeline run, the orchestrator commits updated `data/` and `reports/` files back to the repository and pushes.

**Why commit-back, not Actions cache or artifacts:**

| Strategy | TTL | Reliability | Complexity |
|----------|-----|-------------|------------|
| **Commit-back (recommended)** | Permanent | High — ordinary git | Low — standard git ops |
| `actions/cache` | ~7 days no-access eviction (MEDIUM confidence) | Low — eviction is non-deterministic; cache is designed for build artifacts, not persistent user data | Low setup, but dangerous for data you cannot afford to lose |
| `actions/upload-artifact` | 90 days default | Medium — but requires an API call to find the latest artifact ID each run; adds complexity and a failure mode | Higher — must implement artifact lookup logic |

Commit-back wins on every axis for this use case: permanent retention, no extra API calls, transparent in the GitHub UI, full audit trail in git history.

**Required workflow permissions:**

```yaml
permissions:
  contents: write
```

**Retry safety:** Before pushing, do `git pull --rebase origin main` to handle the case where two runs overlap (unlikely on cron, but safe practice).

**Self-trigger loop:** Cron-triggered workflows that commit back do NOT re-trigger the workflow, because GitHub Actions does not re-trigger on commits made by `GITHUB_TOKEN` by default. No loop risk.

## Data Flow

### Full Pipeline Execution

```
GitHub Search API
       ↓
  [Fetcher]
  Handles pagination (Search API caps at 1000 results).
  Returns: list of {id, full_name, description, stars, created_at, topics}
       ↓
  [Snapshot Store — write]
  Writes data/snapshots/YYYY-MM-DD.json: {id: star_count, ...}
       ↓
  [Metadata Store — write]
  Overwrites data/metadata/current.json with display fields
       ↓
  [Snapshot Store — read history]
  Loads YYYY-MM-DD_minus_1.json and YYYY-MM-DD_minus_30.json (if they exist)
       ↓
  [Velocity Engine]
  For each repo:
    - 24h_delta  = today_stars - yesterday_stars  (None if no yesterday snapshot)
    - 30d_delta  = today_stars - day30_stars       (None if no day-30 snapshot)
    - age_days   = (today - created_at).days
    - proxy_velocity = today_stars / max(age_days, 1)
       ↓
  [Ranker]
  Applies 4-bucket logic; skips buckets where required deltas are None
  Returns: {brand_new_weekly, brand_new_monthly, spike_24h, velocity_30d}
       ↓           ↓
       │     [Seen Store — read]
       │     Loads data/seen.json
       ↓           ↓
  [Renderer]
  Joins ranked buckets with seen-store to set 🆕 flag
  Writes reports/YYYY-MM-DD.md
       ↓
  [Seen Store — write]
  Updates data/seen.json: adds new repos with first_reported=today,
  increments report_count for returning repos
       ↓
  [Orchestrator — commit-back]
  git add data/ reports/
  git diff --quiet || git commit -m "tracker: YYYY-MM-DD"
  git pull --rebase && git push
```

### State Transitions

```
No data files (cold start)
    ↓ (run 1)
data/snapshots/2026-06-26.json  ← first snapshot
data/metadata/current.json
reports/2026-06-26.md           ← brand-new buckets only; spike/velocity omitted
data/seen.json                  ← all today's repos marked first_reported=today
    ↓ (run 2, next day)
data/snapshots/2026-06-27.json  ← second snapshot
reports/2026-06-27.md           ← 24h spike bucket now available
    ...
    ↓ (run 31)
reports/2026-07-26.md           ← all 4 buckets now fully populated
```

## Build Order and Dependencies

Build in this sequence. The critical domain constraint is that **snapshot history cannot be backfilled** — every day without a running collection loop is a day of lost velocity data. Get the collection pipeline into production as early as possible, even before rendering is complete.

| Order | Component | Depends On | Why This Position |
|-------|-----------|------------|-------------------|
| 1 | `config.py` + data models | Nothing | All other modules need constants and type shapes |
| 2 | `snapshot_store.py` + `metadata_store.py` | config | Core persistence; testable in isolation with mock data |
| 3 | `fetcher.py` | config, GitHub API token | Independent of data layer; can be developed and tested in parallel with store |
| 4 | `main.py` skeleton (fetch → store → commit-back) | fetcher, snapshot_store, metadata_store | **Deploy to production here.** Accumulation starts. Report output can be trivial ("N repos fetched") at this stage. |
| 5 | `velocity.py` | snapshot_store | Needs real snapshot files to test against; can mock with synthetic files |
| 6 | `ranker.py` | velocity | Pure function over velocity engine output; easily unit-tested |
| 7 | `seen_store.py` | config | Independent of velocity; can develop in parallel with steps 5-6 |
| 8 | `renderer.py` | ranker, seen_store | Final assembly; needs ranked output and seen-store state |
| 9 | Wire `main.py` fully | all above | Assemble all stages in the orchestrator |
| 10 | GitHub Actions workflow | main.py, secrets configured | Validate end-to-end in the Actions environment |

**The non-negotiable rule:** Step 4 (deploy the collect loop) must go live before any other work. If steps 5-9 take 2 weeks to build, you lose 2 weeks of velocity history. Ship a minimal collection-only version first; velocity computation improves over subsequent iterations while history accumulates.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| GitHub Search API | REST via `PyGitHub` or `httpx` + manual pagination | Search API caps at 1000 results per query; fetcher must handle pagination up to this cap. AI repo filter strategy (topics vs keywords vs combo) is deferred to separate research per PROJECT.md. |
| GitHub API rate limits | Authenticated requests: 5000/hr (personal token) | Supply token via `GITHUB_TOKEN` Actions secret; never committed. Check `X-RateLimit-Remaining` header; add backoff if low. |

### Internal Module Boundaries

| Boundary | Communication | Contract |
|----------|---------------|----------|
| fetcher → snapshot_store | Direct call; fetcher returns list of dicts | Fetcher returns `[{id: int, full_name: str, stars: int, created_at: str, ...}]` |
| snapshot_store → velocity | File read; velocity calls `load_snapshot(date)` | Returns `{str(id): int}` — numeric ID as string key |
| velocity → ranker | In-memory list of enriched repo records | `[{id, full_name, stars, 24h_delta, 30d_delta, age_days, proxy_velocity}]` |
| ranker → renderer | Dict of 4 named lists | `{brand_new_weekly: [...], brand_new_monthly: [...], spike_24h: [...], velocity_30d: [...]}` |
| seen_store → renderer | `load_seen()` returns dict keyed on numeric ID | `{id: {first_reported: date, report_count: int}}` |
| renderer → seen_store | Renderer reads; seen_store writes AFTER report is generated | Ordering matters for idempotency — mark seen after report is written |

## Anti-Patterns

### Anti-Pattern 1: Keying Snapshots on `owner/repo` Instead of Numeric ID

**What people do:** Use `owner/repo` as the dict key because it's readable and the default in GitHub API responses.

**Why it's wrong:** GitHub repos can be renamed or transferred. When `owner/repo` changes, the old key in the snapshot store appears to be a deleted repo and the new key appears to be a brand-new repo with no history. Velocity computation silently breaks. The seen-store dedup also breaks (the repo appears 🆕 again after a rename).

**Do this instead:** Key on numeric `id` (integer from API response, stored as string in JSON). Store `full_name` as a display field in the metadata store, updated each run.

### Anti-Pattern 2: Treating `first_reported != None` as "Not New" on Same-Day Retry

**What people do:** Set `first_reported = today` on the first run, then check `first_reported is not None` to decide whether to show 🆕. On a same-day retry, repos that should still show 🆕 lose the flag.

**Why it's wrong:** Retried reports differ from original reports. The 🆕 flag becomes unreliable and confusing.

**Do this instead:** The 🆕 condition is `first_reported == today` (not `first_reported is None`). Repos seen for the first time today always show 🆕 on every run of that same date.

### Anti-Pattern 3: Using `actions/cache` as Persistent Data Storage

**What people do:** Store snapshot JSON in the Actions cache keyed on a fixed name (e.g., `tracker-data-v1`).

**Why it's wrong:** The cache has a ~7-day no-access eviction policy (MEDIUM confidence on exact TTL). Cache entries are also subject to size-based eviction non-deterministically. If the cron pauses (holiday, rate limit, repo archived briefly), the cache can be evicted and all snapshot history is permanently lost. There is no recovery path.

**Do this instead:** Commit data files back to the repository. Git is permanent storage with audit trail.

### Anti-Pattern 4: Storing Full Metadata in Every Snapshot

**What people do:** Store `description`, `topics`, `full_name`, `language` alongside `star_count` in each daily snapshot file.

**Why it's wrong:** As months of snapshots accumulate, the data directory balloons unnecessarily. Updating a description field in old snapshot files requires a migration script. The time-series only needs one value: `stars`.

**Do this instead:** Snapshot files store only `{id: star_count}`. All display metadata lives in `data/metadata/current.json`, overwritten each run.

## Schema Evolution

Because the snapshot time-series stores only `{id: star_count}`, schema evolution is nearly a non-issue — the only required historical field is `stars`, and that never changes meaning.

- **Adding fields to metadata** (e.g., `forks`, `open_issues`): update `current.json` schema; old metadata files are overwritten anyway.
- **Adding fields to the seen store** (e.g., `last_reported`): add with `dict.get(key, default)` fallback reads; old entries simply lack the field until they appear in a new run.
- **Adding fields to snapshots** (e.g., a second metric like `forks` alongside `stars`): bump `schema_version` in new snapshot files; velocity engine checks `schema_version` and handles both shapes.
- **No migration scripts needed for day-to-day changes.** If a breaking change is ever required, a one-time migration script over `data/snapshots/` is straightforward since all files are small, self-describing JSON.

## Sources

- GitHub REST API documentation: https://docs.github.com/en/rest/search/search
- GitHub Actions caching docs: https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/caching-dependencies-to-speed-up-workflows
- GitHub Actions artifacts docs: https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/storing-workflow-data-as-artifacts
- GitHub Actions permissions: https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/controlling-permissions-for-github_token
- PROJECT.md context: `C:\dev\github-repo-tracker\.planning\PROJECT.md`

---
*Architecture research for: GitHub AI Repo Velocity Tracker*
*Researched: 2026-06-26*
