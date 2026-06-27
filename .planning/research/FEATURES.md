# Feature Research

**Domain:** GitHub trending/velocity tracker — AI repository discovery automation
**Researched:** 2026-06-26
**Confidence:** HIGH (API mechanics HIGH from Context7 + official docs + live API calls; filter strategy HIGH from empirical validation; ecosystem patterns MEDIUM from tool analysis)

---

## GitHub Search API Constraints (Gates Every Feature Decision)

These are hard limits verified against GitHub REST API docs (Context7 /websites/github_en + docs.github.com). All feature choices must fit within them.

| Constraint | Value | Source | Impact |
|------------|-------|--------|--------|
| Search rate limit | 30 req/min (authenticated) | Context7 REST docs | Budget every query; 4-bucket daily run requires ~4–8 calls minimum |
| Core REST rate limit | 5,000 req/hr | Context7 REST docs | Snapshot enrichment stays within budget |
| Result cap per query | 1,000 max (10 pages × 100) | GitHub community discussions, PyGithub issues | `topic:ai` alone matches 144,998+ repos; raw scan is impossible |
| Sort keys available | `stars`, `forks`, `help-wanted-issues`, `updated` | Context7 REST docs | **NO native velocity/trending sort** — velocity must be computed externally |
| Available search qualifiers | `topic:`, `in:name`, `in:description`, `in:readme`, `created:`, `stars:`, `language:`, `archived:` | GitHub docs /searching-for-repositories | Enables windowed date queries and combined signal filters |

The 1,000-result cap and absence of a velocity sort are the two facts that justify the entire architecture: you MUST slice by date window to get manageable result sets, and you MUST compute velocity yourself.

---

## Feature Landscape

### Table Stakes (Users Expect These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| AI-repo filter | Without it the tool is a generic trending tracker, not an AI-specific radar | MEDIUM | Empirically validated combo strategy; see AI Filter Recommendation below |
| Star-velocity ranking | The differentiating metric; raw star count is what every other tool shows | MEDIUM | Two computation paths depending on bucket (see below) |
| Four ranked buckets | Stated in PROJECT.md; maps to the four discovery needs (new-this-week, new-this-month, 24h-spike, 30d-velocity) | LOW (structural) | Bucket definitions drive query design |
| Per-repo output line | Clickable link + creation date + current stars + description + velocity figure | LOW | Single API response contains all fields except velocity delta |
| First-seen marker (🆕) | Users need to know which entries are new discoveries vs. returning entries | LOW | Requires persisted seen-store; key on numeric `repo.id` NOT `full_name` |
| Dated markdown output | Delivery mechanism defined in PROJECT.md | LOW | Standard Python string formatting; no UI needed |
| GitHub Actions cron | Automation; users expect it to run without manual triggers | LOW | `on: schedule: cron:` + commit-back workflow |
| Snapshot persistence | Required to compute non-trivial velocity (24h, 30d) | MEDIUM | JSON file committed back to repo each run; cold-start accepted |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Combo AI filter (topics + keyword description fallback) | Catches brand-new repos that lack topic tags; existing tools (github-ranking-ai, github trending page) miss these | LOW-MEDIUM | Empirically: keyword query returns ~5x more new AI repos than single topic query |
| Velocity-only ranking for new repos (day-1 capable) | New-this-week and new-this-month buckets work on day 1 using `stars ÷ age`; no history needed | LOW | Separates from snapshot-dependent tools that require warm-up time |
| Explicit cold-start transparency | Report clearly labels when spike/velocity buckets have insufficient history | LOW | A note/section in the digest explaining data gap; honest signal vs. silent omission |
| Returning-entry continuity tagging | Shows repos that appeared in previous reports (not just new ones); users see if a trend is sustained vs. one-day spike | LOW | Uses seen-store with first-seen date; renders as "first seen YYYY-MM-DD" |
| Stable ID dedup (repo.id, not full_name) | Repos renamed or transferred are correctly recognized as known, not re-flagged as 🆕 | LOW | One-line implementation; prevents false discovery noise |

### Anti-Features (Deliberately NOT Build)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Full star-history reconstruction (star-history.com approach) | "Wouldn't complete history give more accurate velocity?" | Paginating stargazer timestamps: ~1 API call per 100 stars. A 10k-star repo = 100 calls. Scanning hundreds of repos daily = rate limit exhaustion + hours of runtime | Store daily snapshots forward; velocity = today_stars − yesterday_stars |
| GitHub Archive / GH events stream (ossinsight approach) | "Real-time accuracy" | Requires ingesting 10B+ events into a separate database infrastructure (TiDB/BigQuery). Engineering cost is 100× the use case | Daily snapshot diff from REST API gives equivalent signal for once-daily cadence |
| GitHub trending page scraping | "It's already curated" | HTML scraping breaks on layout changes; not topic-filterable; mixes all domains not just AI | Use Search API with `created:` windowing and topic/keyword filters |
| Web dashboard / UI | "Easier to read" | Explicitly out of scope per PROJECT.md v1; adds frontend infrastructure with no validation benefit | Markdown is scannable; revisit in v2 after validating signal quality |
| Push delivery (Discord/Slack/email) | "Get notified automatically" | Adds external service dependencies; out of scope per PROJECT.md v1 | Markdown file in repo is readable; add delivery after signal quality is proven |
| Cross-bucket dedup (suppress a repo appearing in multiple buckets) | "Avoid repetition in the digest" | A repo can legitimately appear in multiple buckets (e.g., new-this-week AND 24h-spike) — they measure different things | Within each bucket, dedup by repo.id. Cross-bucket overlap is valid and informative |
| LLM-based relevance scoring | "Use AI to judge if a repo is really AI-related" | Adds API cost per repo, latency, and brittleness to LLM availability; overkill for a filter problem that keyword + topic signals solve adequately | Combo filter with explicit topic list + keyword blocklist is deterministic and free |
| Human-curated category tags | ossinsight classifies into "AI Agents", "LLM Tools", "MCP Servers", etc. via manual curation | Requires ongoing manual maintenance; not automatable from metadata | Ship with flat list; add topic-based grouping only if user feedback shows it's needed |

---

## AI Filter Recommendation

**Recommended approach: Combo filter — topic union + keyword-in-description fallback, windowed by `created:`**

**Confidence: HIGH** — empirically validated by live GitHub Search API calls (2026-06-26).

### Empirical Evidence for the Topic-Coverage Gap

Direct API calls on repos created in the last 7 days (2026-06-19 to 2026-06-26):

| Query | Result count |
|-------|-------------|
| `topic:ai created:>2026-06-19` | 2,160 |
| `topic:llm created:>2026-06-19` | 2,639 |
| `topic:machine-learning created:>2026-06-19` | 2,032 |
| `topic:agents created:>2026-06-19` | 247 |
| `llm in:name,description created:>2026-06-19` | **10,546** |

The keyword query (`llm in:name,description`) returns roughly **5x** the repos of the largest single topic query. Even accounting for overlap between topic queries, and even if many keyword hits are noise, the topic-only approach misses a large portion of new AI repos.

Spot-check of 10 brand-new llm-keyword repos (created 2026-06-25/06-26, sorted by stars):
- **5 of 10 had completely empty topics arrays** — discoverable only by keyword, invisible to any topic-only query.
- 2 of 10 had `topic:llm` — caught by topic query.
- 2 of 10 had model-specific topics (`deepseek-*`, `qwen-*`) but not `topic:ai` or `topic:llm` — would require keyword fallback or those specific topics in the list.
- 1 of 10 had both `topic:ai` and `topic:llm`.

**Conclusion:** Topics-only filtering misses ~50–60% of new AI repos created in the last 7 days based on this sample. The keyword fallback is essential for the new-repo buckets (new-this-week, new-this-month), which are the primary value proposition.

### Why Not Topics-Only

- `topic:ai` returns 144,998+ total repos — more than enough signal exists, but only for repos whose creators bothered to add topics.
- 50–60% of brand-new repos (< 7 days) have no topics, as confirmed above.
- github-ranking-ai project uses predefined topic lists and misses anything untagged.

### Why Not Keywords-Only

- Keywords alone have no precision filter: `llm in:description` matches tutorials, "I'm learning LLM", documentation collections, and any repo where the word appears incidentally.
- The `stars:>5` floor and `created:` window help, but topics provide a strong positive signal that keyword alone cannot replicate.

### The Combo Strategy (Recommended)

Run **two separate Search API queries per time window** and merge results client-side:

**Query A — Topic signal (high precision):**

REST API call:
```
GET /search/repositories
  ?q=topic:ai+OR+topic:llm+OR+topic:machine-learning+OR+topic:deep-learning+OR+topic:generative-ai+OR+topic:rag+OR+topic:agents+created:>YYYY-MM-DD
  &sort=stars
  &order=desc
  &per_page=100
```

Note: `sort` and `order` are separate query parameters, NOT part of the `q` string.

**Query B — Keyword fallback (broadens recall for brand-new untagged repos):**

```
GET /search/repositories
  ?q=(llm+OR+%22large+language+model%22+OR+%22ai+agent%22+OR+openai+OR+anthropic+OR+langchain)+in:name,description+created:>YYYY-MM-DD+stars:>5
  &sort=stars
  &order=desc
  &per_page=100
```

The `stars:>5` floor suppresses zero-signal forks and test repos. Both queries must stay within the 1,000-result cap — the `created:` date window ensures this for typical daily volumes.

Merge A ∪ B by `repo.id`, deduplicate, then rank by velocity. Apply a noise blocklist after the first few runs if false positives cluster around specific patterns (e.g., `topic:ai` on blockchain projects using "AI" loosely).

**Rate budget:** 2 queries per time window × 3 windows (7d, 30d, all-time) = 6 queries per run. At 30 req/min, this completes in < 15 seconds including pagination.

**Extended topic list (MEDIUM confidence, from github-ranking-ai categories + github.com/topics inspection):**
`ai`, `llm`, `machine-learning`, `deep-learning`, `agents`, `generative-ai`, `rag`, `chatgpt`, `openai`, `langchain`, `llama`, `mistral`, `claude`, `transformer`, `neural-network`, `gpt`, `diffusion`, `mcp`

GitHub Search API has limits on OR clause depth — test topic-union query length; split into multiple calls if the query exceeds URL limits.

---

## Velocity Computation — Two Tiers

These are NOT equivalent. Understanding the distinction is critical for MVP scope.

### Tier 1: Creation-Date Velocity (Day-1 Capable)

Applies to: new-this-week, new-this-month buckets.

```
velocity = repo.stargazers_count / max(1, days_since(repo.created_at))
```

Available immediately from a single Search API response. No snapshot history needed. Works on day 1.

**Acceleration variant** (if showing star acceleration in the report):
```
acceleration = today_velocity − yesterday_velocity
```
Requires two snapshots (day 0 and day 1) — available after run 2.

### Tier 2: Snapshot-Diff Velocity (Requires History)

Applies to: 24h-spike, 30d-velocity buckets.

```
24h_delta = today_snapshot[repo.id].stars − yesterday_snapshot[repo.id].stars
30d_delta = today_snapshot[repo.id].stars − snapshot_30d_ago[repo.id].stars
```

Sparse on cold start. Buckets stay empty until enough daily snapshots accumulate. **This is an accepted constraint per PROJECT.md.**

Snapshot structure (committed JSON):
```json
{
  "date": "2026-06-26",
  "repos": {
    "12345678": { "stars": 4200, "name": "owner/repo" },
    ...
  }
}
```

Key by numeric `repo.id` (stable across renames/transfers). Store daily files or accumulate in a rolling dict.

---

## Feature Dependencies

```
[Snapshot Store — JSON committed to repo]
    └──required by──> [24h-Spike Bucket]
    └──required by──> [30d-Velocity Bucket]
    └──enhances──> [Star Acceleration Display]

[AI Filter (Combo Query)]
    └──required by──> [All Four Buckets]

[Seen-Store — JSON with repo.id → first_seen_date]
    └──required by──> [🆕 First-Seen Marker]
    └──required by──> [Returning-Entry Tag]

[Creation-Date Velocity Computation]
    └──required by──> [New-This-Week Bucket]
    └──required by──> [New-This-Month Bucket]
    └──day-1 capable — no snapshot needed

[Snapshot-Diff Velocity]
    └──required by──> [24h-Spike Bucket]
    └──required by──> [30d-Velocity Bucket]
    └──blocked until──> [Run N >= 2 for 24h, Run N >= 30 for 30d]
```

### Dependency Notes

- **24h-spike requires snapshot-store:** No historical star count = no delta. Report this bucket as "Insufficient data — warming up" until at least 2 runs complete.
- **Seen-store uses repo.id as key:** repo.id is immutable; full_name changes on rename/transfer. Wrong key = false 🆕 flags on renamed repos.
- **New-this-week and new-this-month are independent of snapshot store:** velocity is computable from `created_at` + current `stargazers_count` in a single API response.

---

## MVP Definition

### Launch With (v1)

- [ ] Combo AI filter (topic union + keyword fallback, date-windowed) — enables all buckets
- [ ] New-this-week bucket (top 10, creation-date velocity, day-1 capable) — validates the core signal
- [ ] New-this-month bucket (top 5, creation-date velocity, day-1 capable) — second bucket, same code path
- [ ] Snapshot store (JSON committed to repo each run) — unlocks spike/velocity buckets over time
- [ ] Seen-store (JSON committed to repo each run, keyed by repo.id) — enables 🆕 and returning-entry tags
- [ ] Per-repo output: link, creation date, current stars, velocity, description, 🆕/returning markers
- [ ] Dated markdown digest output
- [ ] GitHub Actions cron + commit-back workflow

### Add After Validation (v1.x)

- [ ] 24h-spike bucket (top 10) — add when snapshot store has at least 2 days of data (run 2)
- [ ] 30d-velocity bucket (top 10) — add when snapshot store has 30+ days
- [ ] Cold-start transparency note in report (explains empty buckets during warm-up)
- [ ] Star acceleration field (today's velocity − yesterday's velocity; available after run 2)

### Future Consideration (v2+)

- [ ] Keyword blocklist tuning — reduce noise from query B; needs real data to calibrate
- [ ] Topic-based grouping in report (AI Agents / LLM Tools / RAG / etc.) — add if digest length grows
- [ ] Push delivery (Discord webhook or email) — add after signal quality is proven useful
- [ ] Extended topic coverage tuning — monitor false positive / false negative rate after 30 days

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Combo AI filter | HIGH | MEDIUM | P1 |
| New-this-week bucket | HIGH | LOW | P1 |
| New-this-month bucket | HIGH | LOW | P1 |
| Per-repo output line | HIGH | LOW | P1 |
| 🆕 first-seen marker | HIGH | LOW | P1 |
| Snapshot store (JSON) | HIGH | LOW | P1 |
| GitHub Actions cron | HIGH | LOW | P1 |
| Dated markdown output | HIGH | LOW | P1 |
| 24h-spike bucket | HIGH | LOW (once data exists) | P2 |
| 30d-velocity bucket | HIGH | LOW (once data exists) | P2 |
| Cold-start transparency note | MEDIUM | LOW | P2 |
| Star acceleration field | MEDIUM | LOW | P2 |
| Returning-entry tag | MEDIUM | LOW | P2 |
| Topic-based grouping | LOW | MEDIUM | P3 |
| Keyword blocklist | MEDIUM | MEDIUM | P3 |

---

## Competitor Feature Analysis

| Feature | github-ranking-ai | ossinsight trending/ai | github.com/trending | Our Approach |
|---------|------------------|------------------------|---------------------|--------------|
| AI filter strategy | Predefined topic list per category | Human-curated category taxonomy | Language filter only, no AI filter | Combo: topic union + keyword fallback (empirically ~5x more recall on new repos) |
| Velocity metric | Star count only (no velocity) | "Recent star velocity" (GH Archive) | Stars gained this period (scraped) | creation-date velocity (day-1) + snapshot-diff (later) |
| New repo detection | No (ranks established repos) | No explicit new-repo bucket | Day/week/month windows, not AI-specific | Explicit new-this-week and new-this-month buckets |
| Dedup / seen-before | No | No | No | Seen-store keyed by repo.id with 🆕 flag |
| Data source | GitHub Search API | 10B+ GH Archive events (TiDB) | HTML scraping of trending page | GitHub Search API (REST) |
| Output format | Markdown tables (auto-committed) | Web dashboard | Web dashboard | Dated markdown digest |
| Cold-start behavior | N/A (no time-window velocity) | Warm (continuous event stream) | N/A | Transparent: empty buckets labeled during warm-up |
| Infrastructure | GitHub Actions (simple) | Large data pipeline (TiDB cluster) | External scraper | GitHub Actions (simple) |

---

## Sources

- GitHub REST API rate limits and search endpoint: Context7 `/websites/github_en`, docs.github.com/en/rest/search/search
- 1,000-result cap: PyGithub/PyGithub issues #824, #1072; github.com/orgs/community/discussions/64629
- GitHub search qualifiers: docs.github.com/en/search-github/searching-on-github/searching-for-repositories
- topic:ai repo count (144,998) and empirical topic-coverage data: live API calls to api.github.com/search/repositories (2026-06-26)
- github-ranking-ai topic classification approach: yuxiaopeng/Github-Ranking-AI README
- ossinsight methodology: ossinsight.io/blog/introducing-trending-page; ossinsight.io/trending/ai
- star-history.com approach (stargazer pagination, 40k cap): medium.com/@emafuma/how-to-get-full-history-of-github-stars-f03cc93183a7
- vitalets/github-trending-repos (issue-comment tracking approach): github.com/vitalets/github-trending-repos
- star-velocity-db schema (daily snapshot pattern): github.com/halcyon-vortex/star-velocity-db
- GitHub Actions cron commit-back pattern: docs.github.com/actions/using-workflows/workflow-syntax-for-github-actions

---

*Feature research for: GitHub Repo Tracker — AI repository velocity discovery*
*Researched: 2026-06-26*
