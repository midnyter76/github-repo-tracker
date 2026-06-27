# GitHub Repo Tracker

## What This Is

A daily automation that surfaces brand-new and fast-rising AI repositories on GitHub before they hit mainstream social media. It queries the GitHub API every morning, ranks repos by star velocity across four buckets, and writes a clean, scannable markdown digest. Built as a Python script run on a schedule — an early-filtering radar for AI tooling.

## Core Value

Catch exploding AI repos early — surface the right repositories, ranked by *velocity* (not raw star totals), before they trend elsewhere.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Query the GitHub API daily and filter for AI-related repositories
- [ ] **Brand New — Top 10 weekly**: repos created in last 7 days, ranked by star velocity
- [ ] **Brand New — Top 5 monthly**: repos created in last 30 days, ranked by star velocity
- [ ] **Breakthrough — Top 10 24h spike**: existing repos with a sudden star surge in the last 24h
- [ ] **Breakthrough — Top 10 30-day velocity**: existing repos with sustained star growth over a rolling month
- [ ] Store a daily snapshot of star counts so velocity can be computed as a diff over time
- [ ] Per-repo report line: clickable link, creation date, current stars + star acceleration, primary description
- [ ] Track which repos have already been reported; flag never-before-seen repos with a 🆕 marker, tag returning ones
- [ ] Write each run's output as a dated markdown report file
- [ ] Run automatically every morning via GitHub Actions cron
- [ ] Persist the snapshot store across scheduled runs (e.g. commit back to repo)

### Out of Scope

- Web dashboard / UI — markdown report is the deliverable; no frontend in v1
- Tracking non-AI repos — scope is deliberately AI tooling only
- Realtime / intraday polling — once-daily cadence is sufficient for early discovery
- Push delivery (Discord/Slack/email) — file output chosen for v1; revisit later
- Auto-acting on results (starring, posting, DMs) — read-and-report only

## Context

- Concept comes from a YouTube walkthrough of a Claude Code automation that does exactly this (4-bucket velocity tracking, daily markdown digest). Source: https://www.youtube.com/watch?v=0k8rJseHQTA
- The hard problem is historical star data: the GitHub API returns *current* star counts, not history. True 24h-spike and 30-day-velocity numbers require accumulating our own daily snapshots — so the velocity buckets are sparse on a cold start and fill in as snapshots build up.
- GitHub API rate limits apply; a personal access token is required for reasonable quotas. Token supplied via GitHub Actions secret, never committed.
- Snapshot persistence in a stateless Actions runner means the snapshot store must be committed back to the repo (or cached) each run.

## Constraints

- **Tech stack**: Python — strong GitHub API libraries, easy JSON/data handling, standard for this kind of script.
- **Runtime**: GitHub Actions cron — runs in the cloud for free, no always-on machine needed.
- **Delivery**: Dated markdown file — no UI, no external services in v1.
- **Data**: Velocity requires self-stored daily snapshots; spike/velocity buckets stay empty until enough history accumulates (cold start accepted).
- **Security**: GitHub token via Actions secret / env var only — never echoed or committed.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python for the script | Best GitHub API + data ecosystem fit | — Pending |
| Store daily star snapshots | Only way to compute true 24h/30d velocity; API gives no history | — Pending |
| Markdown file output | Simplest high-signal deliverable; no UI needed in v1 | — Pending |
| GitHub Actions cron scheduler | Free cloud run, no local machine dependency | — Pending |
| AI-repo filter strategy deferred to research | Best GitHub Search query (topics vs keyword vs combo) is a research question | — Pending |
| Dedup = mark seen, 🆕 flag new | Keeps sustained risers visible while highlighting fresh discoveries | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-26 after initialization*
