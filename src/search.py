"""GitHub API discovery layer for the GitHub Repo Tracker.

Provides pure query builders, rate-paced search wrapper, combo-filter discovery,
star-banded established-repo discovery, and tracked-repo refresh.

All constants are imported from src.config — never inline filter values here.
"""

import time
import warnings
from datetime import datetime, timezone, timedelta

import github

from src.config import (
    TOPICS,
    KEYWORD_SETS,
    KEYWORD_STAR_FLOOR,
    KEYWORD_IN_QUALIFIER,
    QUALIFIER_EXCLUSIONS,
    BREAKTHROUGH_STAR_BANDS,
    NEW_REPO_WINDOWS,
    TOTAL_COUNT_CAP_WARN,
)

# ---------------------------------------------------------------------------
# Pure query builders (no network)
# ---------------------------------------------------------------------------


def build_topic_query(topic: str, since_date: str) -> str:
    """Build a topic-half search query.

    No star floor — fresh topiced repos must not be suppressed (D-03, FILTER-03).

    Args:
        topic: GitHub topic string (e.g. "llm").
        since_date: ISO date string for the created:>DATE qualifier.

    Returns:
        Query string for g.search_repositories().
    """
    return f"topic:{topic} {QUALIFIER_EXCLUSIONS} created:>{since_date}"


def build_keyword_query(keywords: list, since_date: str) -> str:
    """Build a keyword-fallback search query.

    Star floor applied on the keyword half only (FILTER-03, D-02).

    Args:
        keywords: List of keyword terms joined with OR.
        since_date: ISO date string for the created:>DATE qualifier.

    Returns:
        Query string for g.search_repositories().
    """
    terms = " OR ".join(keywords)
    return (
        f"{terms} {KEYWORD_IN_QUALIFIER}"
        f" stars:>={KEYWORD_STAR_FLOOR}"
        f" {QUALIFIER_EXCLUSIONS}"
        f" created:>{since_date}"
    )


def build_established_query(topic: str, band: str) -> str:
    """Build a star-banded established-repo query (D-11).

    No created: window — catches old repos spiking regardless of age.

    Args:
        topic: GitHub topic string.
        band: Star band string e.g. "100..1000".

    Returns:
        Query string for g.search_repositories().
    """
    return f"topic:{topic} stars:{band} {QUALIFIER_EXCLUSIONS}"


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def since_date_for(window_days: int, now: datetime | None = None) -> str:
    """Compute the cutoff date for a creation-window query.

    Args:
        window_days: Number of days back from now.
        now: Optional datetime for deterministic tests; defaults to UTC now.

    Returns:
        Date string in "YYYY-MM-DD" format.
    """
    base = now if now is not None else datetime.now(timezone.utc)
    cutoff = base - timedelta(days=window_days)
    return cutoff.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Cap helpers
# ---------------------------------------------------------------------------


def over_cap(results) -> bool:
    """Return True when total_count meets or exceeds the warning threshold (FILTER-02).

    Threshold is TOTAL_COUNT_CAP_WARN (900), below the hard GitHub 1,000-result cap.
    """
    return results.totalCount >= TOTAL_COUNT_CAP_WARN


def split_star_band(band: str) -> list:
    """Split a star band into two contiguous sub-bands at the midpoint.

    Used when a band's total_count exceeds the cap (FILTER-02).

    Args:
        band: Star band string "LO..HI".

    Returns:
        ["LO..MID", "MID..HI"] — same combined range, two narrower slices.
    """
    lo_str, hi_str = band.split("..")
    lo = int(lo_str)
    hi = int(hi_str)
    mid = (lo + hi) // 2
    return [f"{lo}..{mid}", f"{mid}..{hi}"]


# ---------------------------------------------------------------------------
# Rate-paced search wrapper (Pattern 2, DATA-01)
# ---------------------------------------------------------------------------


def safe_search(g, query: str, **kwargs):
    """Pre-check search rate limit, sleep to reset if needed, then search.

    Only pre-checks before the FIRST page of each new query.
    Subsequent pagination pages are protected by PyGithub's GithubRetry.

    Never references the auth token or the client object in any output.

    Args:
        g: Authenticated Github client.
        query: Search query string.
        **kwargs: Forwarded to g.search_repositories().

    Returns:
        PaginatedList of RepositorySearchResult objects.
    """
    while True:
        rl = g.get_rate_limit()
        if rl.search.remaining > 0:
            break
        reset_utc = rl.search.reset.replace(tzinfo=timezone.utc)
        sleep_sec = (reset_utc - datetime.now(timezone.utc)).total_seconds() + 2
        time.sleep(max(sleep_sec, 2))
    return g.search_repositories(query, **kwargs)


# ---------------------------------------------------------------------------
# Discovery: date-windowed new repos (FILTER-01, D-04)
# ---------------------------------------------------------------------------


def discover_repos(g, windows=None, search=None) -> dict:
    """Discover new repos via topic-union + keyword-fallback queries (FILTER-01).

    For each window in NEW_REPO_WINDOWS:
      - Issues one query per topic (6 topics → 6 calls).
      - Issues one query per KEYWORD_SET (2 sets → 2 calls).
      - Merges all results by str(repo.id).

    When a result's totalCount >= TOTAL_COUNT_CAP_WARN, emits a warning AND
    re-issues with the smallest window (tighter created: window) to stay under
    the 1,000-result cap (FILTER-02 / Pitfall 2).

    Args:
        g: Authenticated Github client.
        windows: Day windows for created: qualifier; defaults to NEW_REPO_WINDOWS.
        search: Injected callable for tests; defaults to safe_search.

    Returns:
        dict keyed by str(repo.id) → repo object.
    """
    if windows is None:
        windows = NEW_REPO_WINDOWS
    if search is None:
        search = safe_search

    found: dict = {}
    tightest_window = min(windows)

    for window in windows:
        since = since_date_for(window)

        for topic in TOPICS:
            query = build_topic_query(topic, since_date=since)
            results = search(g, query)
            if over_cap(results):
                warnings.warn(
                    f"topic query for '{topic}' totalCount={results.totalCount} "
                    f">= {TOTAL_COUNT_CAP_WARN}; narrowing to {tightest_window}d window",
                    stacklevel=2,
                )
                tight_since = since_date_for(tightest_window)
                results = search(g, build_topic_query(topic, since_date=tight_since))
            for repo in results:
                found[str(repo.id)] = repo

        for kw_set in KEYWORD_SETS:
            query = build_keyword_query(kw_set, since_date=since)
            results = search(g, query)
            if over_cap(results):
                warnings.warn(
                    f"keyword query totalCount={results.totalCount} "
                    f">= {TOTAL_COUNT_CAP_WARN}; narrowing to {tightest_window}d window",
                    stacklevel=2,
                )
                tight_since = since_date_for(tightest_window)
                results = search(g, build_keyword_query(kw_set, since_date=tight_since))
            for repo in results:
                found[str(repo.id)] = repo

    return found


# ---------------------------------------------------------------------------
# Discovery: star-banded established repos (D-11, FILTER-02)
# ---------------------------------------------------------------------------


def discover_established(g, search=None) -> dict:
    """Star-banded pass to catch old-but-spiking repos (D-11, Reading B).

    Queries every combination of BREAKTHROUGH_STAR_BANDS x TOPICS without a
    created: window, so established repos spiking today are always visible.

    When a band+topic combination's totalCount >= TOTAL_COUNT_CAP_WARN, splits
    the band in two and re-issues both sub-band queries (FILTER-02 / Pitfall 2).

    Args:
        g: Authenticated Github client.
        search: Injected callable for tests; defaults to safe_search.

    Returns:
        dict keyed by str(repo.id) → repo object.
    """
    if search is None:
        search = safe_search

    found: dict = {}

    for band in BREAKTHROUGH_STAR_BANDS:
        for topic in TOPICS:
            query = build_established_query(topic, band)
            results = search(g, query)
            if over_cap(results):
                warnings.warn(
                    f"established query topic='{topic}' band='{band}' "
                    f"totalCount={results.totalCount} >= {TOTAL_COUNT_CAP_WARN}; "
                    "splitting band",
                    stacklevel=2,
                )
                for sub_band in split_star_band(band):
                    sub_results = search(g, build_established_query(topic, sub_band))
                    for repo in sub_results:
                        found[str(repo.id)] = repo
            else:
                for repo in results:
                    found[str(repo.id)] = repo

    return found


# ---------------------------------------------------------------------------
# Refresh: re-fetch tracked repos by numeric id (Pattern 6, DATA-01)
# ---------------------------------------------------------------------------


def refresh_tracked(g, tracked_ids: list) -> dict:
    """Re-fetch current star counts for all previously tracked repos.

    Uses numeric ID lookup (Pattern 3) — survives renames and transfers.
    Skips repos that have been deleted or made private (UnknownObjectException).

    Does NOT call repo.get_topics() — that is a separate API call per repo
    and would double core API usage (Pitfall 6).

    Only the repo id string (rid) is referenced in exception handling — the
    exception object itself is never logged (T-01-04).

    Args:
        g: Authenticated Github client.
        tracked_ids: List of str repo ids from the metadata store.

    Returns:
        dict keyed by str(repo.id) → repo object (deleted/private repos omitted).
    """
    refreshed: dict = {}
    for rid in tracked_ids:
        try:
            repo = g.get_repo(int(rid))
            refreshed[str(repo.id)] = repo
        except github.UnknownObjectException:
            warnings.warn(f"Repo id {rid} unavailable (deleted or private); skipping")
            continue
    return refreshed
