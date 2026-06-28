# Phase 2: Velocity Ranking + Full Reporting - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-28
**Phase:** 2-velocity-ranking-full-reporting
**Areas discussed:** Metrics (velocity vs acceleration), Digest format, Cold-start handling, New/returning markers + seen-store

---

## Metrics — velocity vs acceleration

| Option | Description | Selected |
|--------|-------------|----------|
| Velocity now, acceleration deferred | Velocity only (stars/day, hour-normalized); defer 2nd-derivative acceleration to Phase 3 | ✓ |
| Both velocity + acceleration | Compute acceleration too; richer but longer warm-up + more complexity | |
| Discuss the formulas | Talk through exact per-bucket math | |

**User's choice:** Velocity now, acceleration deferred (recommended default).
**Notes:** Acceleration needs 3+ snapshots and is the most cold-start-fragile metric. The `velocity/acceleration` wording in REPORT-02 is satisfied by velocity for this phase.

---

## Digest format

| Option | Description | Selected |
|--------|-------------|----------|
| 4 sections, bullet-per-repo, `reports/YYYY-MM-DD.md` | One H2 per bucket; each repo a bullet line; dated file in new `reports/` dir | ✓ |
| Table-per-section | Markdown tables; denser but noisier diffs, worse on mobile | |
| Discuss layout | Talk through order, shape, path, tone | |

**User's choice:** 4 sections, bullet-per-repo (recommended default).
**Notes:** Bullet lines chosen for clean git diffs + mobile readability in the public browsable repo.

---

## Cold-start handling (RANK-06)

| Option | Description | Selected |
|--------|-------------|----------|
| Activate at ≥2 snapshots; else warming note | 24h-spike needs 2 snapshots; 30d uses widest window available; new-repo buckets work day 1 | ✓ |
| Hold bucket until FULL window | 30d stays warming until all 30 snapshots — shows nothing for a month | |
| Discuss thresholds + wording | Talk through per-bucket rules + note text | |

**User's choice:** Activate at ≥2 snapshots; else warming note (recommended default).
**Notes:** Note text: "Breakthrough buckets warming up — N of M days collected." Section header still prints; never silently empty or crash-inducing.

---

## New/returning markers + seen-store (REPORT-03/04/05)

| Option | Description | Selected |
|--------|-------------|----------|
| 🆕 new, ↩ returning, seen-store tracks first-seen date | seen-store at `data/seen.json` keyed by repo.id with first-seen date; written after report | ✓ |
| 🆕 only, plain returning, seen-store = id set | Flag new only; minimal id→date map | |
| Discuss markers + store | Talk through glyphs, store contents, retry semantics | |

**User's choice:** 🆕 new, ↩ returning, first-seen-date seen-store (recommended default).
**Notes:** Store written AFTER the report (REPORT-05) so same-day retries flag correctly. Keyed by numeric repo.id (rename-safe).

---

## Claude's Discretion

- Tie-break within a bucket (default: higher current stars, then lexical full_name).
- Sparse buckets render however many qualify, no padding.
- Velocity rounding/format, description truncation length, "tracked Nd" inline display.
- Module layout and how the digest step wires into `collector.run()`.

## Deferred Ideas

- Acceleration (2nd-derivative) metric → Phase 3.
- "Latest" pointer / README dashboard / digest index → future phase if wanted (scope-watch).
- Star-gaming / fake-velocity filters → already roadmapped to Phase 3.
