# Project Research Summary

**Project:** GitHub AI Repo Velocity Tracker
**Domain:** Daily batch data pipeline — GitHub Search API → snapshot store → velocity ranking → markdown digest
**Researched:** 2026-06-26
**Confidence:** HIGH

## Executive Summary

This is a once-daily Python batch pipeline that queries the GitHub Search API, stores star-count snapshots in git, computes velocity deltas, and renders a dated markdown digest. All four researchers converged on the same architecture: the GitHub Search API's hard **1,000-result cap per query** is the defining constraint — it forces every design decision from query slicing to persistence strategy. A naive single query over `topic:ai` returns the 1,000 most-popular repos (not the fastest-rising new ones), so the entire fetcher must be built around date-windowed sub-queries merged client-side by numeric repo ID.

The recommended approach is a six-module Python pipeline running on GitHub Actions cron: Fetcher (combo topic + keyword queries), SnapshotStore (per-date JSON committed back to the repo), MetadataStore (display fields overwritten each run), VelocityEngine (snapshot diffs), Ranker (four buckets with graceful cold-start degradation), and Renderer (dated markdown). The only external dependency is `PyGithub 2.9.1` — everything else is stdlib and GitHub Actions built-ins. Start with `GITHUB_TOKEN` (1,000 req/hr); upgrade to a PAT only when approaching ~900 repo refreshes per day.

The single highest-stakes risk is **delay**: snapshot history cannot be backfilled. Every day the collection loop is not running in production is a permanent gap in the 24h-spike and 30-day-velocity data. A second structural risk is **topic coverage**: empirical API calls show topics-only filtering misses ~50–60% of brand-new AI repos (50% of new repos have zero topics). The validated mitigation is a combo query strategy — topic union + keyword-in-name/description fallback — merged by `repo.id`, yielding ~6 API calls per run. Both risks are fully solvable with the patterns documented in this research.

---

## Key Findings

### Recommended Stack

PyGithub 2.9.1 is the clear choice: typed GitHub REST API v3 wrapper with built-in `GithubRetry` (handles 403/secondary-rate-limit backoff automatically) and `seconds_between_requests` throttling — no third-party retry library needed. `uv` replaces pip for dependency management and removes the explicit venv-activate step from CI. All storage, date arithmetic, and file I/O use Python stdlib. The dependency graph is `PyGithub` and nothing else.

**Core technologies:**
- **Python 3.12** — ships on `ubuntu-latest` Actions runner, all libraries support it
- **PyGithub 2.9.1** — typed GitHub REST client with built-in retry and rate-limit helpers; use 2.x import paths (`from github import Github, Auth`)
- **uv (astral-sh/setup-uv@v8)** — 10–100x faster than pip; `uv run tracker.py` works without explicit venv activation
- **stefanzweifel/git-auto-commit-action@v5** — commit-back mechanism for snapshots and reports; requires `contents: write` permission on GITHUB_TOKEN
- **stdlib only** for everything else: `json`, `datetime`, `pathlib`, `time`, `collections`

**Critical version notes:** PyGithub < 2.0 lacks `Auth` module and built-in retry; `GITHUB_TOKEN` rate limit is 1,000 req/hr (not 5,000 — this is buried in docs and causes silent failures at scale); `actions/cache` has ~7-day eviction and must never be used for snapshot persistence.

---

### Expected Features

The four buckets in PROJECT.md map to two velocity tiers with different cold-start behaviors. New-repo buckets (weekly, monthly) use `stars / age_days` and are **day-1 capable**. Spike/velocity buckets (24h, 30d) use snapshot diffs and need 2 and 30 days of history respectively. The seen-store (keyed on numeric `repo.id`) enables the 🆕 flag from day 1.

**Must have (table stakes):**
- Combo AI filter (topic union + keyword fallback per time window) — topic-only misses ~50–60% of new repos; keyword-only has too much noise; both are required together
- Brand New Weekly bucket (top 10, creation-date velocity) — day-1 capable; validates core signal immediately
- Brand New Monthly bucket (top 5, creation-date velocity) — same code path as weekly, day-1 capable
- Snapshot store committed back to repo each run — per-date JSON keyed by numeric `repo.id`; lean time-series (star count only); split from metadata
- Seen-store (`data/seen.json`, keyed by numeric `repo.id`) — powers 🆕 flag; wrong key (`full_name`) causes false-new flags on renames
- Per-repo output line: link, creation date, current stars, velocity, description, 🆕/returning markers
- Dated markdown digest output; GitHub Actions cron with commit-back workflow

**Should have (competitive):**
- Breakthrough 24h Spike bucket (top 10) — add at run 2 when delta data exists; omit with "warming up" note until then
- Breakthrough 30d Velocity bucket (top 10) — add at run 30; same graceful degradation
- Cold-start transparency note — explicitly label unavailable buckets with "N of 30 days collected"; never show empty sections silently
- Velocity normalization: `(new_stars - old_stars) / hours_elapsed × 24` — raw delta inflates velocity 2x when a cron run is skipped

**Defer (v2+):**
- Topic-based grouping in report, push delivery (Discord/email), LLM-based relevance scoring, web dashboard/UI — all explicitly deferred per PROJECT.md or anti-feature analysis

---

### Architecture Approach

A linear stage graph: Fetcher → SnapshotStore (write) → MetadataStore (write) → SnapshotStore (read history) → VelocityEngine → Ranker → SeenStore (read) → Renderer → SeenStore (write) → git commit-back. Each stage is a separate Python module; `main.py` wires them. State lives in the repo itself — no external services, no database. The critical structural split is lean snapshots (`{id: star_count}` only) versus metadata (`current.json` with display fields, overwritten each run), which prevents the snapshot directory from bloating as months accumulate.

**Major components:**
1. `fetcher.py` — combo query strategy (2 queries × 3 time windows = ~6 API calls); handles pagination, rate-limit pre-checks, multi-query dedup by numeric `repo.id`
2. `snapshot_store.py` + `metadata_store.py` — snapshot stores only `{id: star_count}` per day; metadata stores display fields and is overwritten each run
3. `velocity.py` + `ranker.py` — velocity engine computes 24h_delta, 30d_delta, and age-proxy fallback; ranker skips buckets where required history is absent (`None` sentinel, not zero)
4. `seen_store.py` + `renderer.py` — 🆕 condition is `first_reported == today` (not `is None`) to handle same-day retries correctly; renderer writes cold-start notes when buckets are unavailable
5. `main.py` + `.github/workflows/tracker.yml` — orchestrator owns `git diff --quiet || git commit` + `git pull --rebase && git push`; `[skip ci]` suffix prevents self-triggering loop

---

### Critical Pitfalls

1. **Search 1,000-result cap silently truncates results** — `topic:ai` matches 144,998+ repos; a single query returns only the top 1,000. Slice every query by `created:>DATE` window; verify each slice's `total_count` is under 1,000. Architecture-defining, not an edge case.

2. **60-day scheduled-workflow auto-disable kills the tracker silently** — GitHub disables scheduled workflows after 60 days of repository inactivity with no error notification. Mitigation: `gautamkrishnar/keepalive-workflow` action + `workflow_dispatch` trigger + validate whether PAT-authored commits (vs. GITHUB_TOKEN commits) reset the inactivity timer.

3. **Keying snapshots by `owner/repo` string breaks velocity history on rename/transfer** — a renamed repo looks like a new repo; velocity history is permanently lost. Key every snapshot and seen-store entry by numeric `repo.id`. One-time design decision, painful to migrate after data accumulates.

4. **GITHUB_TOKEN rate limit (1,000 req/hr) starves scans at scale** — the auto-provisioned Actions token has 5× lower limits than a PAT. Sufficient for the initial phase; switch to `secrets.GH_PAT` when approaching 900+ repo refreshes per day.

5. **Timezone-naive datetimes silently corrupt velocity windows** — `datetime.now()` returns a naive datetime; GitHub API timestamps are UTC-aware ISO 8601. Use `datetime.now(timezone.utc)` everywhere; store snapshot timestamps as ISO 8601 UTC strings.

---

## Implications for Roadmap

### Phase 1: Collection Loop — Deploy First, Non-Negotiable

**Rationale:** Snapshot history cannot be backfilled. Every day without a running collection loop is a permanent gap in 24h-spike and 30d-velocity data. Deploy to production before any other work begins. A trivial "N repos fetched" report is acceptable output at this stage.

**Delivers:** Daily snapshot collection running in GitHub Actions; `data/snapshots/YYYY-MM-DD.json` and `data/metadata/current.json` committed to the repo each morning. History accumulation begins on day 1.

**Addresses:** `config.py` + data models; `fetcher.py` with combo AI filter (topic union + keyword fallback, date-windowed, deduped by numeric `repo.id`); `snapshot_store.py` + `metadata_store.py`; `main.py` skeleton (fetch → write snapshot → write metadata → commit-back); `.github/workflows/tracker.yml` (cron, secret injection, `contents: write`, commit-back with `[skip ci]`).

**Research flag:** Validate the combo query set (topic list, keyword list, star floor, date window boundaries) against live API output on day 1. Verify each sub-query's `total_count` stays under 1,000.

---

### Phase 2: Velocity Ranking + Full Reporting

**Rationale:** Build the full pipeline while history accumulates. New-repo buckets (weekly, monthly) use creation-date velocity and are day-1 capable — immediate value from the first report. Spike/velocity buckets gracefully degrade until data exists.

**Delivers:** Complete dated markdown digest. New-repo buckets produce real rankings from day 1. Spike/velocity buckets show "building history (N of 30 days)" until data is available. Seen-store enables 🆕 first-seen markers and returning-entry tags from the first report.

**Addresses:** `velocity.py` (creation-date proxy `stars / max(age_days,1)`, 24h delta, 30d delta, elapsed-hours normalization); `ranker.py` (four buckets, skip on `None`, explanatory notes); `seen_store.py` (`first_reported == today`); `renderer.py` (markdown + cold-start notes); fully wired `main.py` with `git diff --quiet` no-op guard.

---

### Phase 3: Production Hardening

**Rationale:** After 30+ days of history the 30d-velocity bucket activates and the tracker reaches steady-state. Phase 3 locks down reliability, noise filtering, and security. Several items (keepalive validation, gaming thresholds) require real data from prior runs.

**Delivers:** Full 4-bucket reporting; resilient scheduling with verified 60-day keepalive; star gaming filters calibrated on real output; query tuning informed by 30+ days of observation; snapshot pruning to bound repo growth.

**Addresses:** 60-day keepalive (`gautamkrishnar/keepalive-workflow` + `workflow_dispatch`; validate PAT-commit timer reset); gap detection (warn when last snapshot >26h old; normalize by `hours_elapsed`); star gaming filters (`archived:false fork:false`, `stars:>5` keyword floor, star:fork ratio anomalies); snapshot pruning (>90 days); timezone audit (zero naive `datetime.now()`); query tuning on false-positive/negative rates.

**Research flag:** Star gaming threshold calibration requires real data from Phase 1–2 runs. Use configurable `config.py` constants with conservative defaults; tune in Phase 3.

---

### Phase Ordering Rationale

- **Phase 1 is unconditionally first** — history loss is permanent and unrecoverable.
- **Phase 2 starts immediately after Phase 1 deploys** — new-repo buckets need no historical data; spike/velocity buckets warm up automatically.
- **Phase 3 is deferred until data exists** — gaming thresholds, false-positive patterns, and query calibration all require real output to tune.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | PyGithub 2.9.1 verified on PyPI; API constraints verified against official GitHub REST docs; Action versions confirmed |
| Features | HIGH | API mechanics verified with live API calls (2026-06-26); combo filter empirically validated with real result counts |
| Architecture | HIGH | Pipeline pattern, commit-back, data models, module boundaries fully specified with concrete contracts |
| Pitfalls | HIGH | Rate limits and search cap from official docs; 60-day disable from Actions docs; all pitfalls have concrete mitigations |

**Overall confidence:** HIGH

### Gaps to Address

- **AI filter topic list completeness (MEDIUM):** 18-topic list derived from github-ranking-ai + github.com/topics. Design as a configurable constant, not hardcoded.
- **60-day keepalive via GITHUB_TOKEN commits (MEDIUM):** Community reports conflict on whether bot commits reset the timer. Validate within first 60 days; fall back to PAT-authored commits.
- **Star gaming filter thresholds (LOW):** No verified ratio data for this corpus. Defer to Phase 3 with conservative `config.py` defaults.
- **Secondary rate limit behavior under combo budget:** `GithubRetry` handles primary limits; add a `safe_search` pre-check wrapper for secondary limits.

---

## Sources

### Primary (HIGH confidence)
- GitHub REST API rate limits — docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- GitHub Search API — docs.github.com/en/rest/search/search (1,000-result cap, 30 req/min, `archived:false fork:false`)
- PyGithub 2.9.1 PyPI + changelog (`GithubRetry`, `seconds_between_requests`, 2.x imports)
- astral-sh/setup-uv@v8; stefanzweifel/git-auto-commit-action@v5 (`contents: write`)
- GitHub Actions scheduled-workflow 60-day disable docs
- Live GitHub Search API calls (2026-06-26): combo-filter validation (topic 247–2,639; keyword 10,546; ~50% topic-null on spot check)

### Secondary (MEDIUM)
- gautamkrishnar/keepalive-workflow; community discussion on GITHUB_TOKEN commits + inactivity timer; github-ranking-ai topic classification

### Tertiary (LOW)
- ossinsight trending methodology, star-history.com — anti-feature analysis only

---
*Research completed: 2026-06-26 · Ready for roadmap: yes*
