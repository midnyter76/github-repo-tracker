# Phase 2: Velocity Ranking + Full Reporting - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Turn the Phase-1 data substrate (per-date star snapshots + repo metadata) into a **complete, dated markdown digest** ranking AI repos across four velocity buckets, plus the **seen-store** that flags new vs returning repos. Scope: compute per-repo velocity, rank into the four buckets, render the digest file, and persist/update the seen-store keyed by numeric `repo.id`.

In scope: RANK-01..06, REPORT-01..05.
Out of scope (later phases): acceleration (2nd-derivative) metric, scheduler hardening / gap detection / star-gaming filters / snapshot pruning, any "latest pointer / README dashboard / index of digests" (Phase 3+).

</domain>

<decisions>
## Implementation Decisions

### Metrics shown (RANK-01..05, REPORT-02)
- **D-01:** Display **velocity only this phase; acceleration is deferred** to Phase 3. The `velocity/acceleration` wording in REPORT-02 / ROADMAP success-criterion 4 is satisfied for now by velocity. Rationale: acceleration is a 2nd derivative needing 3+ snapshots, the most cold-start-fragile metric — not worth blocking day-1 value.
- **D-02:** Velocity is **bucket-specific**, all hour-normalized (RANK-05) so a skipped/delayed run never inflates the number:
  - New-repo buckets (RANK-01/02): **creation velocity** = `stars / age_days`, computed from metadata `created_at` + current snapshot stars. Works from day 1 — no history needed.
  - 24h spike (RANK-03): **star delta** between the two most recent snapshots, normalized by actual elapsed hours.
  - 30-day velocity (RANK-04): **sustained growth** = star delta over the rolling 30-day window (or widest window available), normalized per hour/day.

### Digest layout (REPORT-01, REPORT-02)
- **D-03:** **Four H2 sections, one per bucket**, fixed order: Brand New Weekly (top 10) → Brand New Monthly (top 5) → Breakthrough 24h Spike (top 10) → Breakthrough 30-Day Velocity (top 10).
- **D-04:** Each repo rendered as a **single bullet line** (not a table — cleaner git diffs, better on mobile): marker + `[full_name](html_url)` — ★stars (+velocity/day) · created DATE · description. All fields come from Phase-1 metadata + snapshot — **no schema backfill required**.
- **D-05:** Digest file path is **`reports/YYYY-MM-DD.md`** (new top-level `reports/` dir, dated filename mirroring the snapshot convention).

### Cold-start handling (RANK-06)
- **D-06:** A history-dependent bucket **activates when its window has ≥2 snapshots**; the 30-day bucket uses the widest window available (≥2 snapshots) rather than waiting for a full 30. New-repo buckets (creation velocity) work day 1 and never warm up.
- **D-07:** Until a breakthrough bucket can compute, it is **rendered with a transparent note, never silently empty and never crash-inducing**: `_Breakthrough buckets warming up — N of M days collected._` (N = snapshots available, M = window target). Bucket section header still prints.

### New / returning markers + seen-store (REPORT-03, REPORT-04, REPORT-05)
- **D-08:** Never-before-reported repos flagged **🆕**; previously-reported repos tagged **↩**.
- **D-09:** Seen-store at **`data/seen.json`, keyed by numeric `repo.id`** (string keys, matching snapshot/metadata convention), storing **first-seen date** per repo so entries can optionally show "tracked Nd". Renames/transfers don't break continuity (id, never `owner/repo`).
- **D-10:** Seen-store is **updated AFTER the report is written** (REPORT-05) so a same-day retry re-reads the pre-write state and still flags 🆕/↩ correctly — a repo first reported this morning stays 🆕 within the same run only, ↩ on later runs.

### Claude's Discretion
- Tie-break rule within a bucket (default: higher current star count wins, then lexical `full_name`).
- Sparse buckets (fewer qualifying repos than the top-N cap): render however many qualify, no padding.
- Exact velocity rounding/format (e.g., `+12.4/day`), description truncation length, and whether "tracked Nd" is shown inline — left to planning.
- Module layout (e.g., `src/rank.py`, `src/report.py`, `src/seen.py`) and how the digest step wires into `collector.run()` after persistence.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project planning docs
- `.planning/PROJECT.md` — core value (velocity not raw stars), constraints, Key Decisions table.
- `.planning/REQUIREMENTS.md` §Ranking, §Reporting — the RANK-01..06 / REPORT-01..05 text this phase implements.
- `.planning/ROADMAP.md` §"Phase 2: Velocity Ranking + Full Reporting" — goal + the 5 success criteria that must be TRUE.
- `.planning/phases/01-collection-loop/01-CONTEXT.md` — Phase-1 locked decisions (D-07 UTC timestamps, numeric-id keying, breakthrough universe D-11) that this phase consumes.

### Phase-1 code this phase reads/extends (source of truth for schemas)
- `src/store.py` — snapshot schema `{date, captured_at, repos:{"<id>":{stars}}}` and metadata schema `{updated_at, repos:{"<id>":{full_name, description, created_at, html_url}}}`; `load_metadata` / `load_metadata_ids` helpers. Phase 2 adds seen-store read/write here or in a sibling module.
- `src/collector.py` — `run()` orchestration; the digest + seen-store steps wire in AFTER `write_snap` / `write_meta`.
- `src/config.py` — `SNAPSHOTS_DIR`, `METADATA_PATH` constants; Phase 2 adds `REPORTS_DIR`, `SEEN_PATH`.

### Tech stack (already researched — authoritative)
- `CLAUDE.md` §Technology Stack / §"What NOT to Use" — stdlib `json`/`datetime`/`pathlib`; per-date files not monolithic; key by numeric `repo.id`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/store.py` `load_metadata()` / `load_metadata_ids()` — already return the metadata dict; velocity ranking reads `created_at`, snapshot stars from here. Mirror its corrupt-file `warnings.warn` + `{}`/JSONDecodeError guard pattern for the seen-store loader.
- `src/config.py` constants pattern — add `REPORTS_DIR` and `SEEN_PATH` alongside `SNAPSHOTS_DIR` / `METADATA_PATH`.

### Established Patterns
- Keyword-injectable dependencies in `collector.run()` (`discover=`, `write_snap=`, …) so tests pass fakes — new ranking/report/seen functions should follow the same injectable-callable signature.
- Per-date JSON files, string repo-id keys, UTC ISO 8601 timestamps (D-07). Idempotent same-day writes (snapshot merges; seen-store must be retry-safe per D-10).

### Integration Points
- `collector.run()` step 4 (persist) is where the new digest + seen-store steps attach, reading the snapshot just written plus prior-date snapshots for the diff windows.
- Cold start: `data/snapshots/` currently holds only `.gitkeep` — Phase 2 logic must behave correctly with 0/1 snapshot (new-repo buckets populate; breakthrough buckets show the warming note per D-07).

</code_context>

<specifics>
## Specific Ideas

- Digest tone/shape concept source (carried from Phase 1): YouTube walkthrough https://www.youtube.com/watch?v=0k8rJseHQTA — 4-bucket velocity tracking, daily markdown digest.
- Bullet-per-repo over tables was a deliberate choice for clean git diffs + mobile readability (the digest lives in a public browsable repo, D-08 of Phase 1).

</specifics>

<deferred>
## Deferred Ideas

- **Acceleration metric** (2nd-derivative star growth) — deferred to Phase 3; needs 3+ snapshots, most cold-start-fragile (D-01).
- **"Latest" pointer / README dashboard / index of all digests** — a new presentation capability, its own phase if wanted later. Not raised by user; flagged as scope-watch.
- Star-gaming / fake-velocity filters — already roadmapped to Phase 3 (hardening).

</deferred>

---

*Phase: 2-Velocity Ranking + Full Reporting*
*Context gathered: 2026-06-28*
