# Roadmap: GitHub Repo Tracker

## Overview

Three phases deliver a complete daily velocity tracker for emerging AI repos. Phase 1 deploys the collection loop to GitHub Actions immediately — snapshot history is non-recoverable, so accumulation starts on day 1. Phase 2 builds the full ranking and reporting pipeline on top of accumulating data. Phase 3 hardens the scheduler and filters once real data exists to calibrate against.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Collection Loop** - Daily fetch→snapshot→commit-back loop running in GitHub Actions; history accumulation starts day 1
- [ ] **Phase 2: Velocity Ranking + Full Reporting** - Complete four-bucket ranking with graceful cold-start degradation and dated markdown digest
- [ ] **Phase 3: Production Hardening** - Scheduler resilience, gap detection, star-gaming filters, and snapshot pruning calibrated on real data

## Phase Details

### Phase 1: Collection Loop
**Goal**: Daily star-count snapshots are committed to the repo each morning via GitHub Actions; history accumulation begins on day 1
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, FILTER-01, FILTER-02, FILTER-03, FILTER-04, AUTO-01, AUTO-02, AUTO-03
**Success Criteria** (what must be TRUE):
  1. A new `data/snapshots/YYYY-MM-DD.json` file appears in the repo after each scheduled morning run, keyed by numeric repo.id
  2. The GitHub Actions workflow completes with the token injected from a secret and no credentials exposed in logs or committed files
  3. The combo AI filter (topic-union query + keyword fallback, date-windowed, deduped by numeric repo.id) fetches candidate repos and each sub-query's total_count stays under 1,000
  4. Re-running the workflow on the same day does not corrupt or duplicate the existing snapshot (idempotent write)
  5. All timestamps stored in snapshot and metadata files are UTC ISO 8601 strings
**Plans**: 4 plans (3 waves)
- [x] 01-01-PLAN.md — Project scaffold + config constants (FILTER-04) [wave 1]
- [x] 01-02-PLAN.md — Search/discovery layer: combo filter, cap-slicing, D-11 star-band pass (DATA-01, FILTER-01/02/03) [wave 2]
- [x] 01-03-PLAN.md — Persistence layer: idempotent snapshots + metadata (DATA-02/03/04/05) [wave 2]
- [x] 01-04-PLAN.md — Main wiring + GitHub Actions workflow (DATA-01, AUTO-01/02/03) [wave 3]

### Phase 2: Velocity Ranking + Full Reporting
**Goal**: Each run produces a complete dated markdown digest with all four velocity buckets; new-repo buckets are fully populated from day 1; spike/velocity buckets show transparent cold-start notes until sufficient history exists
**Depends on**: Phase 1
**Requirements**: RANK-01, RANK-02, RANK-03, RANK-04, RANK-05, RANK-06, REPORT-01, REPORT-02, REPORT-03, REPORT-04, REPORT-05
**Success Criteria** (what must be TRUE):
  1. A dated markdown digest file is committed to the repo after each run, containing entries for all four ranking buckets
  2. Brand New Weekly (top 10) and Brand New Monthly (top 5) sections are populated with real repos and velocity numbers from the very first report
  3. Breakthrough 24h Spike and 30-Day Velocity sections display "building history (N of M days collected)" and are never silently empty or crash-inducing before sufficient snapshots exist
  4. Each repo entry in the digest shows a clickable link, creation date, current star count, velocity/acceleration, and description
  5. Never-before-seen repos are flagged with a marker; returning repos are tagged; same-day retries do not incorrectly re-flag returning repos as new
**Plans**: 4 plans (3 waves)
- [x] 02-01-PLAN.md — Config constants + rank.py velocity engine + compute_buckets (RANK-01/02/03/04/05/06) [wave 1]
- [x] 02-02-PLAN.md — Seen-store: load/save/classify new-vs-returning, id-keyed (REPORT-03/04/05) [wave 2]
- [x] 02-03-PLAN.md — Report rendering + description sanitization, four fixed sections (REPORT-01/02/04) [wave 2]
- [x] 02-04-PLAN.md — collector.run() wiring (D-10 order) + daily.yml reports/** commit (REPORT-01/04/05) [wave 3]

### Phase 3: Production Hardening
**Goal**: The tracker runs reliably for months without manual intervention; scheduling risks, data noise, and unbounded repo growth are all mitigated by configurable safeguards calibrated on real data
**Depends on**: Phase 2
**Requirements**: HARD-01, HARD-02, HARD-03, HARD-04
**Success Criteria** (what must be TRUE):
  1. The scheduled workflow remains active after 60 days (keepalive mechanism verified; workflow_dispatch trigger present)
  2. Any run where the previous snapshot is older than 26 hours emits a visible warning, making collection gaps detectable
  3. Repos that match configurable star-gaming heuristics are excluded from rankings before the digest is written
  4. Snapshot files older than the configured retention window are automatically pruned, keeping repo size growth bounded
**Plans**: 5 plans (3 waves)
- [x] 03-01-PLAN.md — config.py Phase 3 constants + gap.py check_gap + test_gap.py (HARD-02) [wave 1]
- [x] 03-02-PLAN.md — keepalive.yml workflow + .github/keepalive placeholder + TestKeepaliveYaml (HARD-01) [wave 1]
- [x] 03-03-PLAN.md — gaming.py filter_gamed + test_gaming.py (HARD-03) [wave 2]
- [x] 03-04-PLAN.md — prune.py prune_snapshots + test_prune.py (HARD-04) [wave 2]
- [ ] 03-05-PLAN.md — collector.run() wiring + daily.yml deletion staging + integration test (HARD-01/02/03/04) [wave 3]

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Collection Loop | 0/4 | Planned | - |
| 2. Velocity Ranking + Full Reporting | 0/4 | Planned | - |
| 3. Production Hardening | 4/5 | In Progress | - |
