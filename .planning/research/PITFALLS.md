# Pitfalls Research

**Domain:** GitHub trending/velocity tracker — AI repo discovery, daily Python script, GitHub Actions cron, daily star snapshots
**Researched:** 2026-06-26
**Confidence:** HIGH (GitHub API rate limits and search behavior verified against official docs; Actions inactivity behavior verified against community reports; all qualifiers confirmed against official search documentation)

---

## Critical Pitfalls

### Pitfall 1: Using the Built-in GITHUB_TOKEN When You Need High Request Volume

**What goes wrong:**
The workflow uses `secrets.GITHUB_TOKEN` (the auto-provisioned Actions token) because it requires no setup. Runs hit the rate limit long before finishing the repo scan. The REST API limit for GITHUB_TOKEN is 1,000 requests/hour per repository — not 5,000. A scan touching 500+ repos burns through this in minutes. Jobs fail silently or return partial data, and the report looks complete.

**Why it happens:**
The GitHub Actions security guidance says "prefer GITHUB_TOKEN over PATs" and developers follow it without checking that the two tokens have different rate limits. The 1,000/hr limit is buried in rate-limit docs, not in the Actions setup guides.

**How to avoid:**
Use a Personal Access Token stored as a repository secret (`secrets.GH_PAT`) for the actual API calls. The PAT gets the standard 5,000 req/hr. GITHUB_TOKEN is still fine for the commit-back step (pushing snapshot data). Scope the PAT to `public_repo` only — read-only access to public repos is all this script needs.

**Warning signs:**
- `X-RateLimit-Remaining` header near zero early in a run
- HTTP 403 responses with `rate limit exceeded` in body
- Reports that are truncated or show fewer repos than expected
- Run time significantly shorter than previous runs (short-circuits on limit hit)

**Phase to address:** API integration

---

### Pitfall 2: Hitting the Search API 1,000-Result Cap and Not Knowing It

**What goes wrong:**
The GitHub Search API returns at most 1,000 results regardless of how many repos match the query. If your AI-repo query matches 10,000 repos, you see only the first 1,000 ordered by GitHub's ranking (relevance or star count depending on your `sort` parameter). Fast-rising repos that haven't yet accumulated mass stars are invisible — exactly the ones this tool exists to find.

**Why it happens:**
The 1,000-result limit is not a pagination limit. Adding more pages past result 1,000 returns an error. Developers assume pagination gives full coverage and don't notice they're only seeing the popular tail.

**How to avoid:**
Break the search into multiple narrower time-windowed queries: one for repos created in the last 7 days, one for repos 8–30 days old, one for repos 31–90 days old. Each sub-query returns at most 1,000 results but covers a smaller population, so fast-risers in each window surface. Merge results by repo ID and deduplicate. Sort each sub-query by `stars` ascending occasionally to catch low-star risers, not just by default relevance.

**Warning signs:**
- A single search query used for all repos with no date-range partitioning
- Response total_count significantly higher than 1,000 but only 1,000 repos in snapshot store
- New repos known to be fast-rising that never appear in reports

**Phase to address:** AI-filter/ranking

---

### Pitfall 3: Star Gaming and Spam Repos Polluting Velocity Rankings

**What goes wrong:**
The AI space has purchased-star campaigns, viral marketing repos with no real code, and ChatGPT-wrapper repos that appear in search results and look like fast risers. A repo that acquired 500 stars via a paid service looks identical to one that earned them organically in a velocity metric. The tracker surfaces noise as signal.

**Why it happens:**
Star velocity is a lagging indicator of community interest but is trivially gamed. There's no official GitHub spam-detection API. The metric that makes this tool valuable is the same metric that's easiest to manipulate.

**How to avoid:**
Add secondary signal filters alongside star velocity. Require a minimum fork count relative to stars (a 500:1 star-to-fork ratio is a red flag). Filter repos with zero commits after the initial push. Require at least 2 non-star watchers. Include the fork count, watcher count, and open-issue count in the snapshot so you can filter retroactively as you refine thresholds. Add `archived:false` and `fork:false` to all search queries to at minimum exclude forks and archived repos from results.

**Warning signs:**
- A repo with thousands of stars but zero forks appearing in top velocity slots
- Repos where star count spikes on a single day and then flatlines forever
- Descriptions that are pure buzzword soup with no linked code or paper

**Phase to address:** AI-filter/ranking

---

### Pitfall 4: Cold-Start Leaves Velocity Buckets Empty and the Report Looks Broken

**What goes wrong:**
The 24h-spike and 30-day-velocity buckets require historical snapshots that don't exist on day 1. With no prior star counts to diff against, these buckets are empty. The report shipped on day 1 shows nothing in 2 of 4 sections. If there's no explicit "building history" message, users assume the tool is broken.

**Why it happens:**
Developers focus on the steady-state case and don't design the early-history case. The 24h bucket needing only 2 snapshots means it works on day 2, but the 30-day bucket is sparse for a month.

**How to avoid:**
Never show empty sections — show a "building history (N of 30 days collected)" progress message in the velocity buckets during the warmup period. For brand-new repos (< 7 days old), their current star count IS their velocity — all stars arrived since creation — so the weekly brand-new bucket works correctly from day 1. Document the cold-start period in the first report's header. For 24h spike bucket, compute delta from whatever the oldest available snapshot is and normalize to per-day rate rather than skipping the bucket entirely.

**Warning signs:**
- Report sections that are simply empty with no explanatory text
- No mechanism in the code to handle missing prior snapshot for a given repo
- Users reporting the tool "isn't working" in the first week

**Phase to address:** Snapshot storage, AI-filter/ranking

---

### Pitfall 5: Snapshot Store Growing Unbounded Until Git Breaks

**What goes wrong:**
Each daily run appends data for every tracked repo. After a year of tracking 2,000 repos, the snapshot JSON is hundreds of megabytes. Git diffs become noise. The commit push times out on the Actions runner. Eventually the file hits GitHub's 100 MB file-size limit and pushes are rejected outright.

**Why it happens:**
"Store daily snapshots" sounds simple; it's easy to store everything and prune later. But "later" never comes, and the runner has no disk space warnings until it fails.

**How to avoid:**
Design pruning in from the start. Only store what velocity computation requires: repo ID (numeric), snapshot date, and star count. Prune entries older than 90 days every run (velocity calculations need at most 30 days; 90 days gives buffer). Key the store by numeric repo ID, not owner/repo-name string — repos can be renamed or transferred, which would create duplicate entries under a name-based key and lose velocity history. Consider NDJSON (one line per snapshot event) rather than a single large JSON object, which keeps git diffs meaningful and makes pruning a line filter operation.

**Warning signs:**
- Snapshot file size growing monotonically with no pruning step
- Git push step slowing down over weeks
- Snapshot file over 10 MB (extrapolate the growth trajectory)
- Snapshots keyed by `owner/repo` string instead of numeric ID

**Phase to address:** Snapshot storage

---

### Pitfall 6: GitHub Actions Cron Unreliability Creating Gaps in Velocity History

**What goes wrong:**
GitHub's scheduled workflows run late (15–60 minutes), occasionally skip entirely, and — critically for public repos — are disabled after 60 days of no "repository activity." A skipped run means no snapshot for that day. The next day's velocity diff covers 48 hours but is attributed to 24 hours, doubling the apparent velocity. A 60-day silent disable means the tracker stops entirely with no error.

**Why it happens:**
Developers assume cron triggers like wall-clock crons. GitHub's documentation notes that scheduled workflows may be delayed during high load. The 60-day disable only applies to public repos and is easy to miss if the project is set up and forgotten.

**How to avoid:**
Store the actual UTC timestamp with every snapshot, not just the date. Compute velocity as `(new_stars - old_stars) / hours_elapsed * 24` to normalize gaps to per-day rates. Log a warning in the report if the elapsed time since the last snapshot is more than 26 hours. For the 60-day disable: use `gautamkrishnar/keepalive-workflow` or ensure the snapshot commit is authored via a PAT (not GITHUB_TOKEN) — commits from GITHUB_TOKEN have uncertain behavior for resetting the inactivity timer according to community reports. Add a `workflow_dispatch` trigger so runs can be manually kicked off after a gap. Keep the repo active with at least one human commit every 50 days.

**Warning signs:**
- Consecutive snapshot timestamps more than 25 hours apart
- Reports stop generating entirely with no error notification
- Last-run timestamp in the Actions UI is more than 2 days ago

**Phase to address:** Scheduling/automation

---

### Pitfall 7: Committing the GitHub Token to the Repository

**What goes wrong:**
The token is hardcoded in the Python script, committed to the repo, or accidentally printed in a log statement. At minimum, the token is exposed in the public repo. At worst, GitHub's secret scanning catches it and revokes it — leaving the workflow broken until a new token is created and the secret is updated.

**Why it happens:**
Developers test locally with a hardcoded token and forget to clean it up before committing. Debug `print(os.environ)` statements leak all env vars. The `.env` file is not in `.gitignore`.

**How to avoid:**
Source the token exclusively from environment variables: `os.environ["GH_PAT"]` — never from a config file, never from a function argument that might get logged. Add `.env` to `.gitignore` before writing the first line of code. In the GitHub Actions workflow YAML, reference the secret by name only (`${{ secrets.GH_PAT }}`): never echo it, never pass it as a positional argument that appears in process listings. Enable GitHub's push protection (secret scanning) on the repo so accidental commits are blocked at push time.

**Warning signs:**
- Token string visible in any committed file
- `print(os.environ)` or equivalent anywhere in the codebase
- `.env` file not listed in `.gitignore`
- Actions workflow YAML that sets `GH_PAT: hardcoded_value`

**Phase to address:** Scheduling/automation (initial setup), Security/hardening

---

### Pitfall 8: Timezone Confusion in "24h" and "Daily" Window Calculations

**What goes wrong:**
"Repos created in the last 7 days" and "24h star spike" are computed differently depending on where timezone awareness is dropped. Common failure: snapshot dates stored as `YYYY-MM-DD` strings (no timezone), then compared against UTC "today" from the API — resulting in a 12-hour window or 36-hour window masquerading as "24h." Repos created at 23:30 UTC appear in a different weekly bucket than repos created at 00:30 UTC the next day even though they're 1 hour apart.

**Why it happens:**
Python's `datetime.now()` returns a naive datetime (no timezone info). Mixing naive and aware datetimes raises no error in older Python patterns and silently computes wrong values. GitHub API timestamps are always UTC-aware ISO 8601.

**How to avoid:**
Use `datetime.now(timezone.utc)` everywhere. Store all snapshot timestamps as ISO 8601 with explicit UTC offset (`2024-01-15T08:00:00Z`), never as bare date strings. All window comparisons (`created_at > now - timedelta(days=7)`) use aware datetime arithmetic. "24h spike" means "since the previous snapshot," not "since midnight UTC" — compute it as the diff between two timestamped snapshots, then normalize by elapsed hours. Treat the cron-run UTC timestamp as the canonical "now" for every calculation in that run.

**Warning signs:**
- Snapshot timestamps stored as date strings (`2024-01-15`) with no time component
- `datetime.now()` without `timezone.utc` anywhere in the codebase
- Repos disappearing and reappearing in weekly buckets near midnight UTC
- 24h velocity numbers that are consistently too high or too low by roughly 2x

**Phase to address:** Snapshot storage, AI-filter/ranking

---

### Pitfall 9: AI Repo Definition Too Broad (Noise) or Too Narrow (Misses)

**What goes wrong:**
**Too broad** — querying `topic:machine-learning OR "AI" in description` returns: productivity apps that say "AI-powered," policy/ethics papers about AI, every research course repo, non-English repos with unrelated AI acronyms. The report is dominated by noise; high-velocity signal repos get buried.

**Too narrow** — querying only `topic:llm` misses: new diffusion model repos before maintainers add topics, robotics/embodied AI, Rust inference engines, RL libraries, new papers that use "foundation model" not "LLM." GitHub topics are user-applied and lag actual repo creation by days or weeks.

**Why it happens:**
There's no ground truth for "AI repo." Teams pick a single query and never revisit it. Topic-only queries rely on maintainer tagging; keyword-only queries get too much noise from marketing copy.

**How to avoid:**
Use a multi-query strategy: run 3–5 narrow queries and merge by repo ID. Combine topic-based queries (`topic:llm`, `topic:diffusion-models`, `topic:computer-vision`, `topic:reinforcement-learning`) with keyword queries scoped to repo names and descriptions. Add a minimum star floor (e.g., 10 stars) to filter obvious noise. Include the `language:Python OR language:Rust OR language:C++` filter for the inference-engine space where Python misses important repos. Treat the query set as a tunable parameter: log how many results each sub-query returns and iterate. The AI-filter strategy is the highest-uncertainty design decision in the project and deserves its own research phase.

**Warning signs:**
- A single search query covering all AI repos
- Results that include non-code repos (papers, course syllabi, policy docs) regularly
- Known fast-rising AI repos that never appear in results
- All results are Python (missing inference engines in other languages)

**Phase to address:** AI-filter/ranking (requires dedicated research before implementation)

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Use GITHUB_TOKEN instead of PAT | Zero secret management | 1,000/hr limit starves scans; breaks at ~200 repos | Never — PAT with `public_repo` scope is low risk and required |
| Key snapshots by `owner/repo` string | Human-readable JSON | Repo renames/transfers silently break velocity history | Never — always key by numeric repo ID |
| Store full API response in snapshot | No schema decisions upfront | File grows 10–50x larger than needed; pruning is harder | Never — store only ID + date + star count |
| Single broad search query | Simple implementation | 1,000-cap cuts off rising repos; noisy results | Acceptable in spike prototype only, not in any committed phase |
| Bare date strings in snapshots | Easy to read | Silent timezone errors; can't normalize multi-day gaps | Never — always use ISO 8601 with UTC offset |
| Compute velocity as raw star delta | Simple math | Skipped runs inflate velocity 2x; misleads rankings | Never — always normalize by hours elapsed |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| GitHub REST API | Using GITHUB_TOKEN (1,000/hr) for bulk repo scans | Use a PAT with `public_repo` scope (5,000/hr) stored as `secrets.GH_PAT` |
| GitHub Search API | Treating pagination as full coverage past 1,000 results | Partition by date range; treat each sub-query as ≤1,000 results; merge by numeric ID |
| GitHub Search API | Using `is:not-archived` (issue/PR syntax) | Use `archived:false fork:false` — the correct repository search qualifiers |
| GitHub Actions cron | Assuming the job runs at exactly the specified time | Store actual UTC timestamp per snapshot; normalize velocity by elapsed hours |
| GitHub Actions scheduled workflows | Assuming the workflow stays enabled indefinitely | Add `keepalive-workflow` action or PAT-authored commits; add `workflow_dispatch` |
| Snapshot git commit-back | Committing while developer also pushes (push conflict) | Add `git pull --rebase` before the snapshot commit step in the workflow |
| PyGitHub library | Library silently retries on rate limit without surfacing the delay | Check `gh.get_rate_limit()` before bulk calls; log remaining quota each run |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| One REST call per tracked repo to refresh star counts | Run time grows linearly; rate limit hit before all repos refreshed | Use GraphQL to batch 50–100 repos per request | ~200 repos on a 1,000/hr GITHUB_TOKEN; ~800 repos on a 5,000/hr PAT |
| Loading entire snapshot JSON into memory on every run | RAM usage grows with file size; eventually OOMs on Actions runner | Prune to 90-day window on every write; use NDJSON for streaming access | ~5,000 repos × 90 days × 50 bytes ≈ 22 MB (manageable but watch the trajectory) |
| Fetching full commit history to compute "new repo" status | Extremely slow; each repo = N API calls | Use repo `created_at` field from search result; no commit fetching needed | Immediately — never needed at all |
| Search API: sorting by `stars` desc always | Only finds already-popular repos; misses fast risers with lower absolute counts | Alternate sort strategies across sub-queries; use date-range partitioning | From day 1 — structural bias, not a scale issue |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Hardcoding PAT in script or config file | Token exposed in public repo; GitHub scans and revokes it | `os.environ["GH_PAT"]` only; `.env` in `.gitignore`; enable push protection |
| Logging environment variables in debug output | Token visible in Actions run logs (public for public repos) | Never log `os.environ`; use structured logging that excludes env vars |
| Using an overly-scoped PAT (`repo` scope instead of `public_repo`) | If token leaks, attacker has write access to private repos | Scope PAT to `public_repo` only — read-only access to public repos |
| PAT with no expiration | Leaked token is valid indefinitely | Set 90-day expiration on the PAT; add workflow step that warns when expiry is near |
| Storing token in workflow YAML as literal value | Secret visible in repo history forever, even if deleted | Always use `${{ secrets.GH_PAT }}` — never inline values |

---

## "Looks Done But Isn't" Checklist

- [ ] **Rate limit handling:** Script checks `X-RateLimit-Remaining` before bulk calls and backs off — not just catches 403 errors after they happen
- [ ] **Search completeness:** Query returns total_count; verify it is under 1,000; if over, the query needs partitioning
- [ ] **Snapshot keying:** Every snapshot entry uses numeric repo ID as the key, not `owner/repo` string
- [ ] **Pruning:** Snapshot store prunes entries older than 90 days on every write — verify file size is bounded
- [ ] **Timezone safety:** Every `datetime` object in the codebase has explicit UTC awareness — no naive datetimes
- [ ] **Velocity normalization:** Velocity is `(new_stars - old_stars) / hours_elapsed * 24`, not a raw star delta
- [ ] **Cold-start messaging:** Report sections show "building history (N/30 days)" when history is incomplete, never empty
- [ ] **60-day keepalive:** A keepalive mechanism is present and tested (not just added to the workflow YAML)
- [ ] **Archived/fork filter:** All search queries include `archived:false fork:false`
- [ ] **Gap detection:** Report logs a warning when last snapshot is more than 26 hours old

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Rate limit exhaustion mid-run | LOW | Wait for reset window (check `X-RateLimit-Reset` header); re-run via `workflow_dispatch` |
| 60-day workflow disable | LOW | Re-enable via GitHub Actions UI; investigate keepalive gap; push a commit to reset timer |
| Token leaked and revoked | MEDIUM | Revoke token immediately; create new PAT; update repository secret; audit logs for unauthorized use |
| Snapshot store too large to push | HIGH | Prune all entries older than 90 days; rewrite history if file was committed at large size; implement NDJSON going forward |
| Snapshot keyed by name (renames lost history) | HIGH | Backfill by fetching current numeric IDs for all tracked names; re-key the store; no way to recover gaps |
| Week of skipped runs (Actions gap) | MEDIUM | Trigger manual runs via `workflow_dispatch` for each missed day; velocity data for that week will be normalized by elapsed time rather than perfect |
| Search query returning only 1,000 of N repos | MEDIUM | Partition existing query by date range; backfill missed repos from their first appearance; accept history loss before the fix |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| GITHUB_TOKEN rate limit (1,000/hr) | API integration | Confirm `GH_PAT` secret exists in workflow; verify `X-RateLimit-Limit` header shows 5,000 in test run |
| Search 1,000-result cap | AI-filter/ranking | Verify all queries return `total_count < 1,000`; confirm date-range partitioning in place |
| Star gaming / spam repos | AI-filter/ranking | Review top velocity slots for repos with >500:1 star-to-fork ratio; confirm secondary signal filters exist |
| Cold-start empty buckets | Snapshot storage | Verify report shows progress messages on first run; no empty sections without explanation |
| Snapshot store growth | Snapshot storage | Confirm pruning step removes entries older than 90 days; check file size after 7 days of runs |
| Actions cron unreliability / 60-day disable | Scheduling/automation | Verify keepalive mechanism; check timestamp normalization in velocity calc; verify `workflow_dispatch` trigger exists |
| Secrets committed | Scheduling/automation | `.env` in `.gitignore`; no hardcoded token strings in any file; push protection enabled |
| Timezone errors | Snapshot storage | Confirm all stored timestamps are ISO 8601 UTC; no `datetime.now()` without `timezone.utc` |
| AI repo definition scope | AI-filter/ranking | Manual spot-check: are known fast-rising AI repos appearing? Are non-code repos appearing? Tune query set |
| Archived/fork pollution | AI-filter/ranking | Confirm `archived:false fork:false` in all search queries |
| Repo rename breaks keying | Snapshot storage | Confirm snapshot store keys are numeric GitHub repo IDs, not owner/repo strings |

---

## Sources

- GitHub REST API Rate Limits (official): https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api — confirms GITHUB_TOKEN = 1,000 req/hr per repo; PAT = 5,000 req/hr
- GitHub Search API: https://docs.github.com/en/rest/search/search — 1,000-result cap, 30 req/min for authenticated search
- GitHub repository search qualifiers: https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories — confirms `archived:false` and `fork:false` syntax
- GitHub Actions scheduled workflow disable (60 days): https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#schedule
- Keepalive Workflow action: https://github.com/marketplace/actions/keepalive-workflow — community solution for 60-day disable
- Community discussion on GITHUB_TOKEN commits not resetting inactivity timer: https://github.com/orgs/community/discussions/184653

---
*Pitfalls research for: GitHub trending/velocity tracker — AI repo discovery*
*Researched: 2026-06-26*
