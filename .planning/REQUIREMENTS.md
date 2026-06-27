# Requirements: GitHub Repo Tracker

**Defined:** 2026-06-26
**Core Value:** Catch exploding AI repos early — surface the right repositories, ranked by velocity (not raw star totals), before they trend elsewhere.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Data Collection & Storage

- [ ] **DATA-01**: Script queries the GitHub Search API for candidate AI repos on each run, authenticated via a token read from an environment variable
- [ ] **DATA-02**: Each run stores a per-date snapshot of star counts keyed by numeric `repo.id`, as JSON committed back to the repo
- [ ] **DATA-03**: Current repo metadata (name, description, creation date, URL) is stored separately and overwritten each run
- [ ] **DATA-04**: Snapshot writes are idempotent on same-day retry — re-running the same day does not corrupt history
- [ ] **DATA-05**: All stored timestamps use UTC ISO 8601

### AI Repo Filtering

- [ ] **FILTER-01**: Combo filter — a topic-union query plus a keyword-in-name/description fallback query, merged client-side by numeric `repo.id`
- [ ] **FILTER-02**: Each search sub-query is date-windowed so its `total_count` stays under the GitHub Search 1,000-result cap
- [ ] **FILTER-03**: Queries exclude archived and fork repos, with a star floor applied to keyword queries to cut noise
- [ ] **FILTER-04**: The AI topic list and keyword list are configurable constants, not hardcoded inline

### Velocity Ranking

- [ ] **RANK-01**: Brand New Weekly — top 10 repos created in the last 7 days, ranked by creation-date star velocity (`stars / age_days`)
- [ ] **RANK-02**: Brand New Monthly — top 5 repos created in the last 30 days, ranked by velocity
- [ ] **RANK-03**: Breakthrough 24h Spike — top 10 existing repos by star delta over the last 24h, computed from snapshot diff
- [ ] **RANK-04**: Breakthrough 30-Day Velocity — top 10 existing repos by sustained star growth over a rolling 30 days
- [ ] **RANK-05**: Velocity is normalized by elapsed hours so a skipped or delayed run does not inflate the number
- [ ] **RANK-06**: Buckets that require unavailable history degrade gracefully — omitted with a "warming up / N of M days collected" note, never crashing or showing an empty section silently

### Reporting

- [ ] **REPORT-01**: Each run writes a dated markdown digest file
- [ ] **REPORT-02**: Each repo line shows a clickable link, creation date, current stars plus velocity/acceleration, and the primary description
- [ ] **REPORT-03**: Previously-reported repos are tracked in a seen-store keyed by numeric `repo.id`
- [ ] **REPORT-04**: Never-before-reported repos are flagged with 🆕; returning repos are tagged
- [ ] **REPORT-05**: The seen-store is updated after the report is written, so a same-day retry still flags repos correctly

### Automation

- [ ] **AUTO-01**: Runs daily via GitHub Actions cron
- [ ] **AUTO-02**: The workflow injects the GitHub token from an Actions secret; the token is never committed or echoed
- [ ] **AUTO-03**: Snapshot store, metadata, seen-store, and report are committed back to the repo each run (commit-back with `[skip ci]` to avoid self-triggering)

### Reliability & Hardening

- [ ] **HARD-01**: The scheduled workflow is protected against GitHub's 60-day auto-disable (keepalive + `workflow_dispatch` trigger)
- [ ] **HARD-02**: Collection gaps are detected and warned on (e.g. last snapshot older than 26 hours)
- [ ] **HARD-03**: Likely star-gamed / spam repos are filtered via configurable heuristics (e.g. star-to-fork ratio anomalies)
- [ ] **HARD-04**: Snapshot entries older than a retention window are pruned to bound repo size growth

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Delivery

- **DELIV-01**: Push delivery of the digest to Discord/Slack via webhook
- **DELIV-02**: Email delivery of the digest

### Reporting Enhancements

- **RENH-01**: Topic-based grouping of repos within the report
- **RENH-02**: LLM-based relevance scoring to refine the AI-repo filter

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Web dashboard / UI | Markdown report is the v1 deliverable; no frontend |
| Tracking non-AI repos | Scope is deliberately AI tooling only |
| Realtime / intraday polling | Once-daily cadence is sufficient for early discovery |
| Auto-acting on results (starring, posting, DMs) | Read-and-report only |
| Star-history reconstruction via stargazer pagination | Prohibitively expensive at scale (anti-feature) |
| GH Archive / ossinsight-style ingestion | Requires TiDB-scale infrastructure; overkill |
| Trending-page scraping | Fragile; API + own snapshots is the robust path |

## Traceability

Populated during roadmap creation. Each v1 requirement maps to exactly one phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| (pending roadmap) | — | Pending |

**Coverage:**
- v1 requirements: 25 total
- Mapped to phases: 0 (pending roadmap)
- Unmapped: 25 ⚠️

---
*Requirements defined: 2026-06-26*
*Last updated: 2026-06-26 after initial definition*
