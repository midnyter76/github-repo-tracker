# Phase 3: Production Hardening - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-28
**Phase:** 3-Production Hardening
**Areas discussed:** Keepalive strategy, Gap detection output, Star-gaming heuristics, Snapshot retention window

---

## Keepalive strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Separate keepalive job | A second workflow (keepalive.yml) runs monthly via cron, does a dummy commit or workflow_dispatch self-trigger. Bulletproof — doesn't depend on whether data commits count. | ✓ |
| Rely on data commits | Assume the daily snapshot commits reset the timer. Accept the risk. | |
| Manual re-enable + alert | No automated keepalive — just document that a human must re-enable if it disables. | |

**Q2 — What should the keepalive job do?**

| Option | Description | Selected |
|--------|-------------|----------|
| Dummy commit to repo | Writes a timestamp to a keepalive file and commits it. Definitely counts as repo activity. | ✓ |
| workflow_dispatch self-trigger | Uses the GitHub API to trigger the main daily.yml workflow_dispatch. No new commits. | |

**Q3 — Where does the keepalive commit land?**

| Option | Description | Selected |
|--------|-------------|----------|
| .github/keepalive | A dedicated file updated with a timestamp each month. Clear purpose. | ✓ |
| README.md last-active badge | Updates a 'last active' timestamp in README.md. | |

**Notes:** STATE.md had an active blocker flagging uncertainty about whether bot commits reset the 60-day timer. User chose the bulletproof path — a separate monthly keepalive workflow — rather than relying on ambiguous behavior.

---

## Gap detection output

| Option | Description | Selected |
|--------|-------------|----------|
| Actions log only | Print a warning to stdout (visible in the GitHub Actions run log). Simple, matches the tool's operator-facing nature. | ✓ |
| Both: log + digest header note | Print to stdout AND prepend a warning note to that day's markdown digest. | |
| Fail the run | Raise an exception — the workflow exits non-zero. Stops the report from being produced. | |

**Q2 — Where in the run does gap detection happen?**

| Option | Description | Selected |
|--------|-------------|----------|
| Start of collector.run() before discovery | Check snapshot age as the very first step. Warning fires early, before spending API quota. | ✓ |
| After write_snap, compare new vs previous | Check after the new snapshot is written. Later but more precise. | |

**Notes:** User preferred keeping the digest clean (reader-facing) and the warning in the operator-facing log. Early check placement was chosen to surface the alert before consuming API quota.

---

## Star-gaming heuristics

| Option | Description | Selected |
|--------|-------------|----------|
| Star:fork ratio threshold | Repos with extremely high stars but near-zero forks. Classic spam signal. | |
| Zero-engagement filter | High stars but 0 open issues AND 0 pull requests AND 0 watchers. | |
| Sudden round-number jump | Star count is a suspiciously round number. Harder to compute from snapshot diffs. | |
| You decide the list | Leave heuristic selection entirely to planning/research. Phase 3 implements the filter mechanism. | ✓ |

**Q2 — What happens when a repo is filtered?**

| Option | Description | Selected |
|--------|-------------|----------|
| Silent exclude from rankings | Gamed repos excluded before any bucket is populated. Filter configurable. | ✓ |
| Exclude but log which repos were filtered | Same exclusion, plus log repo name + triggered heuristic to Actions log. | |
| Mark in digest instead of exclude | Flag with ⚠️ marker but keep visible. Adds complexity to report rendering. | |

**Notes:** User deferred the specific heuristic list to research/planning — the filter mechanism and configurability pattern matter; the exact thresholds calibrate on real data. Silent exclusion was preferred over logging or marking (clean output).

---

## Snapshot retention window

| Option | Description | Selected |
|--------|-------------|----------|
| 90 days | 3× the widest velocity window. Headroom for missed days + debugging. ~90 small JSON files. | ✓ |
| 60 days | 2× the widest window. Tighter if minimal repo growth desired. | |
| You decide | Leave retention window size to planning. | |

**Q2 — When does pruning run?**

| Option | Description | Selected |
|--------|-------------|----------|
| Every run, end of collector.run() | Prune at the end of each daily run after snapshot + report are written. | ✓ |
| Separate weekly cleanup job | A second workflow runs weekly and prunes. | |
| Manual / ad hoc only | No automated pruning — document the command to run manually. | |

**Notes:** User chose 90 days for comfortable headroom. End-of-run pruning keeps it integrated without a second workflow to maintain.

---

## Claude's Discretion

- Exact keepalive cron schedule (monthly intent; exact date/time left to planning)
- Whether pruning deletes oldest file or all files outside window (same steady-state behavior)
- Whether gap-detection threshold (26h per HARD-02) becomes a configurable constant in config.py or is hardcoded
- Star-gaming heuristic list, thresholds, and whether they apply to full candidate set or only ranked entries

## Deferred Ideas

- Acceleration metric (2nd-derivative star growth) — carried forward from Phase 2 deferred; not in scope for Phase 3
