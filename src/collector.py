"""Collector orchestration for GitHub Repo Tracker (Plan 01-04).

Responsibilities:
  build_client() — build an authenticated Github client from the GITHUB_TOKEN env var.
  run()          — orchestrate discovery + refresh + persistence.
  main()         — entry point called by `python -m src.collector`.

Security: GITHUB_TOKEN is read exactly once in build_client and is never printed,
logged, or referenced elsewhere (AUTO-02, Pitfall 4, T-01-10).
"""

import os
from datetime import datetime, timezone

import github

from src import gap, gaming, prune, rank, report, search, seen, store
from src.config import METADATA_PATH, REFRESH_RESIDUAL_CAP, REPORTS_DIR, SEEN_PATH, SNAPSHOT_RETENTION_DAYS, SNAPSHOTS_DIR


def build_client():
    """Construct an authenticated Github client from the GITHUB_TOKEN environment variable.

    Raises:
        RuntimeError: If GITHUB_TOKEN is not set (message does NOT echo the value).

    Returns:
        Authenticated github.Github instance (Pattern 1).
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set")
    return github.Github(
        auth=github.Auth.Token(token),
        retry=github.GithubRetry(),
        seconds_between_requests=0.5,
        per_page=100,
    )


def run(
    g,
    now: datetime,
    *,
    discover=search.discover_repos,
    established=search.discover_established,
    load_ids=store.load_metadata_ids,
    refresh=search.refresh_tracked,
    load_snaps=rank.load_snapshots,
    residual_cap=REFRESH_RESIDUAL_CAP,
    write_snap=store.write_snapshot,
    write_meta=store.write_metadata,
    compute_buckets=rank.compute_buckets,
    load_seen_fn=seen.load_seen,
    classify_fn=seen.classify_and_update,
    write_digest=report.write_digest,
    write_html_digest=report.write_html_digest,
    save_seen_fn=seen.save_seen,
    check_gap_fn=gap.check_gap,           # HARD-02: gap detection (D-05)
    filter_gamed_fn=gaming.filter_gamed,  # HARD-03: gaming filter (D-07)
    prune_fn=prune.prune_snapshots,       # HARD-04: snapshot pruning (D-09)
    prune_meta_fn=prune.prune_metadata,   # HARD-04-EXT: tracked-repo eviction
):
    """Orchestrate the full collection loop for one run.

    Execution order (see §System Architecture Diagram in RESEARCH.md):
      1. discover_repos(g)       — date-windowed topic + keyword discovery
      2. discover_established(g) — star-banded standing query (D-11)
      3. refresh_tracked(g, ids) — re-fetch star counts only for tracked repos
         discovery MISSED this run (ids discovery already returned keep this
         run's fresh search data — see Quick Task 260702-ihe)
      4. union all three into candidates (refresh still runs LAST, but no
         longer overrides discovery for overlapping ids — those are skipped
         since discovery's data is equally fresh; DATA-01 freshest-wins still
         holds because every id in candidates carries this run's data)
      5. write_snapshot + write_metadata

    All dependency functions are keyword-injectable so tests can pass fakes
    without monkeypatching module-level names.

    Args:
        g:               Authenticated Github client.
        now:             UTC datetime for snapshot filename and timestamps (D-07).
        discover:        Callable matching search.discover_repos signature.
        established:     Callable matching search.discover_established signature.
        load_ids:        Callable matching store.load_metadata_ids signature.
        refresh:         Callable matching search.refresh_tracked signature.
        load_snaps:      Callable matching rank.load_snapshots signature. (HARD-05-CAP)
        residual_cap:    Max residual ids refreshed per run. (HARD-05-CAP)
        write_snap:      Callable matching store.write_snapshot signature.
        write_meta:      Callable matching store.write_metadata signature.
        compute_buckets: Callable matching rank.compute_buckets signature.
        load_seen_fn:    Callable matching seen.load_seen signature.
        classify_fn:     Callable matching seen.classify_and_update signature.
        write_digest:      Callable matching report.write_digest signature.
        write_html_digest: Callable matching report.write_html_digest signature
                           (Quick Task 260630-tl4 — HTML digest for email).
        save_seen_fn:    Callable matching seen.save_seen signature.
        check_gap_fn:    Callable matching gap.check_gap signature. (HARD-02)
        filter_gamed_fn: Callable matching gaming.filter_gamed signature. (HARD-03)
        prune_fn:        Callable matching prune.prune_snapshots signature. (HARD-04)
        prune_meta_fn:   Callable matching prune.prune_metadata signature. (HARD-04-EXT)
    """
    # 0. Gap detection — fires before any API quota is spent (HARD-02, D-05)
    check_gap_fn(now, SNAPSHOTS_DIR)

    candidates: dict = {}

    # 1. Date-windowed new-repo discovery (topic + keyword)
    candidates.update(discover(g))

    # 2. Star-banded established-repo discovery (D-11, Reading B)
    # Skipped until 30+ days of snapshot history exist — spike detection requires
    # >=2 snapshots (SPIKE_MIN_SNAPSHOTS) and the established pass burns ~60% of
    # search quota for zero ranking benefit in the first month.
    # candidates.update(established(g))

    # 3. Refresh only tracked repos discovery MISSED this run — ids discovery
    # already returned carry this run's equally-fresh search data, so
    # re-fetching them via a core-API get_repo call is redundant quota spend
    # (DATA-01 freshest-wins still holds; Quick Task 260702-ihe).
    tracked_ids = load_ids()
    residual = [rid for rid in tracked_ids if rid not in candidates]
    # HARD-05-CAP: bound the residual refresh set to residual_cap ids, keeping the
    # highest-signal repos by last-known stars. Only sort when over the cap so the
    # under-cap path preserves residual order exactly (no disk read, no reorder).
    if len(residual) > residual_cap:
        snaps = load_snaps(SNAPSHOTS_DIR)
        latest_repos = snaps[-1]["repos"] if snaps else {}
        # sorted() is stable: equal-star ids retain original residual order.
        residual = sorted(
            residual,
            key=lambda rid: -latest_repos.get(rid, {}).get("stars", 0),
        )
    capped = residual[:residual_cap]
    # Stage counts for the Actions log (plain stdout, gap.py convention).
    # NEVER print the token or client object.
    print(
        f"collector: discovered={len(candidates)} tracked={len(tracked_ids)} "
        f"residual={len(residual)} refreshing={len(capped)}"
    )
    candidates.update(refresh(g, capped))

    # 3.5. Filter likely-gamed repos before snapshot write (HARD-03, D-07, Pitfall 5)
    candidates = filter_gamed_fn(candidates)

    # 4. Persist Phase 1 snapshot + metadata
    write_snap(candidates, now)
    write_meta(candidates, now)

    # 5. Phase 2: rank → classify → report → save seen (D-10 ordering)
    buckets = compute_buckets(SNAPSHOTS_DIR, METADATA_PATH, now)
    reported_ids = [e["id"] for b in buckets.values() for e in b["entries"]]
    current_seen = load_seen_fn(SEEN_PATH)
    markers, updated_seen = classify_fn(current_seen, reported_ids, now.strftime("%Y-%m-%d"))
    write_digest(buckets, markers, now, REPORTS_DIR)      # write report FIRST (D-10)
    write_html_digest(buckets, markers, now, REPORTS_DIR)  # NEW — HTML digest for email
    save_seen_fn(updated_seen, SEEN_PATH)                 # then persist seen-store (D-10)

    # 6. Prune old snapshots — LAST, after all writes (HARD-04, D-09)
    prune_fn(now, SNAPSHOTS_DIR, SNAPSHOT_RETENTION_DAYS)
    # 6b. Evict stale tracked repos from metadata.json — after prune_fn, using
    # this run's final reported_ids (HARD-04-EXT). metadata_path/ledger_path/
    # retention_days all default from config.
    prune_meta_fn(now, reported_ids)


def main():
    """Entry point for `python -m src.collector`."""
    run(build_client(), datetime.now(timezone.utc))


if __name__ == "__main__":
    main()
