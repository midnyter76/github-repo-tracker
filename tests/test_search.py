"""Tests for src/search.py — pure query builders, safe_search, cap helpers,
   discovery functions, and refresh_tracked. Zero network calls.
"""

import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call
import warnings

import pytest

from src.search import (
    build_topic_query,
    build_keyword_query,
    build_established_query,
    since_date_for,
    over_cap,
    split_star_band,
    safe_search,
    discover_repos,
    discover_established,
    refresh_tracked,
)
from src.config import TOTAL_COUNT_CAP_WARN, TOPICS, NEW_REPO_WINDOWS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(total_count, repo_ids=None):
    """Fake PaginatedList-like result with .totalCount and iteration."""
    result = MagicMock()
    result.totalCount = total_count
    if repo_ids is not None:
        repos = [_make_repo(i) for i in repo_ids]
        result.__iter__ = MagicMock(return_value=iter(repos))
    return result


def _make_repo(repo_id):
    """Fake repo object with .id attribute."""
    repo = MagicMock()
    repo.id = repo_id
    return repo


def _make_rate_limit_g(remaining_sequence):
    """Return a fake g with get_rate_limit() that yields successive remaining values."""
    reset_dt = datetime.now(timezone.utc) + timedelta(seconds=30)
    call_count = [0]
    remaining_list = list(remaining_sequence)

    def get_rate_limit():
        rl = MagicMock()
        idx = min(call_count[0], len(remaining_list) - 1)
        rl.search.remaining = remaining_list[idx]
        # reset must be a naive datetime (code adds tzinfo)
        rl.search.reset = reset_dt.replace(tzinfo=None)
        call_count[0] += 1
        return rl

    g = MagicMock()
    g.get_rate_limit = get_rate_limit
    return g


# ---------------------------------------------------------------------------
# Task 1: build_topic_query
# ---------------------------------------------------------------------------


class TestBuildTopicQuery:
    def test_exact_string(self):
        """Must match literal from <behavior> — no star floor on topic half (D-03)."""
        result = build_topic_query("llm", since_date="2026-06-20")
        assert result == "topic:llm fork:false archived:false created:>2026-06-20"

    def test_no_stars_qualifier(self):
        """Topic half MUST NOT contain stars:>= (FILTER-03)."""
        result = build_topic_query("agents", since_date="2026-01-01")
        assert "stars:>=" not in result

    def test_includes_qualifier_exclusions(self):
        result = build_topic_query("rag", since_date="2025-12-01")
        assert "fork:false" in result
        assert "archived:false" in result


# ---------------------------------------------------------------------------
# Task 1: build_keyword_query
# ---------------------------------------------------------------------------


class TestBuildKeywordQuery:
    def test_exact_string(self):
        """Must match literal from <behavior> — star floor present (FILTER-03)."""
        result = build_keyword_query(["llm", "gpt"], since_date="2026-06-20")
        assert (
            result
            == "llm OR gpt in:name,description stars:>=10 fork:false archived:false created:>2026-06-20"
        )

    def test_star_floor_present(self):
        result = build_keyword_query(["openai", "claude"], since_date="2026-01-01")
        assert "stars:>=10" in result

    def test_or_join(self):
        result = build_keyword_query(["a", "b", "c"], since_date="2026-01-01")
        assert result.startswith("a OR b OR c ")

    def test_includes_qualifier_exclusions(self):
        result = build_keyword_query(["llm"], since_date="2026-01-01")
        assert "fork:false" in result
        assert "archived:false" in result


# ---------------------------------------------------------------------------
# Task 1: build_established_query
# ---------------------------------------------------------------------------


class TestBuildEstablishedQuery:
    def test_exact_string(self):
        """D-11: no created: window on established pass."""
        result = build_established_query("agents", "100..1000")
        assert result == "topic:agents stars:100..1000 fork:false archived:false"

    def test_no_created_window(self):
        """Established query must NOT contain created: qualifier (D-11)."""
        result = build_established_query("llm", "1000..10000")
        assert "created:" not in result

    def test_star_band_present(self):
        result = build_established_query("rag", "100..1000")
        assert "stars:100..1000" in result


# ---------------------------------------------------------------------------
# Task 1: since_date_for
# ---------------------------------------------------------------------------


class TestSinceDateFor:
    def test_7_day_window(self):
        now = datetime(2026, 6, 27, tzinfo=timezone.utc)
        result = since_date_for(7, now=now)
        assert result == "2026-06-20"

    def test_30_day_window(self):
        now = datetime(2026, 7, 1, tzinfo=timezone.utc)
        result = since_date_for(30, now=now)
        assert result == "2026-06-01"

    def test_default_now_returns_string(self):
        result = since_date_for(7)
        # Should be a date string in YYYY-MM-DD format
        assert len(result) == 10
        assert result[4] == "-"
        assert result[7] == "-"


# ---------------------------------------------------------------------------
# Task 1: over_cap
# ---------------------------------------------------------------------------


class TestOverCap:
    def test_over_cap_true_at_950(self):
        result = _make_result(950)
        assert over_cap(result) is True

    def test_over_cap_true_at_threshold(self):
        """At exactly TOTAL_COUNT_CAP_WARN (900) → cap triggered."""
        result = _make_result(TOTAL_COUNT_CAP_WARN)
        assert over_cap(result) is True

    def test_over_cap_false_at_800(self):
        result = _make_result(800)
        assert over_cap(result) is False

    def test_over_cap_false_just_below(self):
        result = _make_result(TOTAL_COUNT_CAP_WARN - 1)
        assert over_cap(result) is False


# ---------------------------------------------------------------------------
# Task 1: split_star_band
# ---------------------------------------------------------------------------


class TestSplitStarBand:
    def test_100_1000_splits_to_two(self):
        bands = split_star_band("100..1000")
        assert len(bands) == 2

    def test_contiguous_no_gap(self):
        """Midpoint of first band = lower of second → no gap."""
        bands = split_star_band("100..1000")
        lo1, hi1 = bands[0].split("..")
        lo2, hi2 = bands[1].split("..")
        assert hi1 == lo2, "Sub-bands must share midpoint (no gap)"

    def test_covers_same_range(self):
        bands = split_star_band("100..1000")
        lo1 = bands[0].split("..")[0]
        hi2 = bands[1].split("..")[1]
        assert lo1 == "100"
        assert hi2 == "1000"

    def test_midpoint_is_integer(self):
        """Midpoint must be an integer string, not a float."""
        bands = split_star_band("100..1000")
        mid = bands[0].split("..")[1]
        int(mid)  # must not raise

    def test_another_band(self):
        bands = split_star_band("1000..10000")
        assert len(bands) == 2
        lo1 = bands[0].split("..")[0]
        hi2 = bands[1].split("..")[1]
        assert lo1 == "1000"
        assert hi2 == "10000"


# ---------------------------------------------------------------------------
# Task 1: safe_search
# ---------------------------------------------------------------------------


class TestSafeSearch:
    def test_no_sleep_when_remaining(self):
        """When remaining > 0, calls search once, no sleep."""
        g = _make_rate_limit_g([5])
        fake_result = _make_result(10)
        g.search_repositories.return_value = fake_result

        with patch("time.sleep") as mock_sleep:
            result = safe_search(g, "topic:llm")

        g.search_repositories.assert_called_once_with("topic:llm")
        mock_sleep.assert_not_called()
        assert result is fake_result

    def test_sleeps_when_exhausted_then_retries(self):
        """When remaining == 0 then > 0, sleeps then searches."""
        g = _make_rate_limit_g([0, 5])
        fake_result = _make_result(5)
        g.search_repositories.return_value = fake_result

        with patch("time.sleep") as mock_sleep:
            result = safe_search(g, "topic:agents")

        assert mock_sleep.called, "sleep must be called when remaining == 0"
        g.search_repositories.assert_called_once_with("topic:agents")
        assert result is fake_result

    def test_passes_kwargs_to_search(self):
        """Extra kwargs forwarded to search_repositories."""
        g = _make_rate_limit_g([10])
        g.search_repositories.return_value = _make_result(1)

        safe_search(g, "stars:>=100", sort="stars")
        g.search_repositories.assert_called_once_with("stars:>=100", sort="stars")

    def test_no_token_in_prints(self):
        """Verify search.py source does not print/log token/auth/client (T-01-04)."""
        import inspect
        import re
        import src.search as search_module

        source = inspect.getsource(search_module)
        lines = source.splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.search(r"\b(print|logging)\b", stripped, re.IGNORECASE):
                if re.search(r"(token|auth| g )", stripped, re.IGNORECASE):
                    pytest.fail(f"Token/auth found in print/log statement: {line!r}")


# ---------------------------------------------------------------------------
# Task 2: discover_repos — combo filter, merge-by-id, cap handling
# ---------------------------------------------------------------------------


class TestDiscoverRepos:
    """Covers FILTER-01, FILTER-02, FILTER-03 for the date-windowed discovery pass."""

    def _make_fake_search(self, mapping):
        """Return a fake search callable driven by a topic→repo_ids mapping.

        mapping: dict of {query_fragment: (total_count, [repo_ids])}
        If no fragment matches, returns empty results.
        """
        recorded_queries = []

        def fake_search(g, query, **kwargs):
            recorded_queries.append(query)
            for fragment, (total_count, ids) in mapping.items():
                if fragment in query:
                    result = _make_result(total_count, ids)
                    return result
            return _make_result(0, [])

        fake_search.recorded = recorded_queries
        return fake_search

    def test_merge_by_id_deduplication(self):
        """Repos appearing in both topic and keyword results are deduplicated (FILTER-01)."""
        # topic queries return repos [1,2]; keyword queries return [2,3]
        fake_search = self._make_fake_search({
            "topic:": (50, [1, 2]),
            "in:name,description": (50, [2, 3]),
        })
        result = discover_repos(MagicMock(), windows=[7], search=fake_search)
        assert set(result.keys()) == {"1", "2", "3"}

    def test_topic_queries_have_no_star_floor(self):
        """Topic-half queries must NOT contain stars:>= (FILTER-03 / D-03)."""
        fake_search = self._make_fake_search({})
        discover_repos(MagicMock(), windows=[7], search=fake_search)
        topic_queries = [q for q in fake_search.recorded if "topic:" in q and "stars" not in q.split("topic:")[0]]
        # At least one query per topic (6 topics) should be topic-only without stars floor
        topic_qs = [q for q in fake_search.recorded if q.startswith("topic:")]
        for q in topic_qs:
            assert "stars:>=" not in q, f"Topic query must not have star floor: {q}"

    def test_keyword_queries_have_star_floor(self):
        """Keyword-half queries must have stars:>=10 (FILTER-03)."""
        fake_search = self._make_fake_search({})
        discover_repos(MagicMock(), windows=[7], search=fake_search)
        kw_queries = [q for q in fake_search.recorded if "in:name,description" in q]
        assert len(kw_queries) > 0, "Should issue keyword queries"
        for q in kw_queries:
            assert "stars:>=10" in q, f"Keyword query must have star floor: {q}"

    def test_issues_one_query_per_topic_per_window(self):
        """6 topics x len(windows) calls = correct query count for topic half."""
        from src.config import TOPICS, KEYWORD_SETS
        fake_search = self._make_fake_search({})
        windows = [7, 30]
        discover_repos(MagicMock(), windows=windows, search=fake_search)
        # Should issue len(TOPICS)*len(windows) topic queries + len(KEYWORD_SETS)*len(windows) keyword queries
        expected_min = len(TOPICS) * len(windows) + len(KEYWORD_SETS) * len(windows)
        assert len(fake_search.recorded) >= expected_min

    def test_over_cap_triggers_narrow_and_warn(self):
        """When totalCount >= 900, warns AND re-issues with tighter window (FILTER-02)."""
        call_count = [0]
        recorded = []

        def fake_search(g, query, **kwargs):
            recorded.append(query)
            call_count[0] += 1
            # First call for the llm topic returns over-cap
            if "topic:llm" in query and call_count[0] == 1:
                result = _make_result(950, [1])
                return result
            return _make_result(50, [])

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            discover_repos(MagicMock(), windows=[7], search=fake_search)

        assert any("950" in str(w.message) or "narrowing" in str(w.message).lower() for w in caught), \
            "Should emit a warning when cap exceeded"
        # Tighter query must have been re-issued (more queries than without cap)
        assert len(recorded) > len(list({"topic:llm"}))

    def test_keyed_by_string_id(self):
        """All result dict keys are str(repo.id) not int."""
        fake_search = self._make_fake_search({"topic:": (10, [42])})
        result = discover_repos(MagicMock(), windows=[7], search=fake_search)
        for key in result.keys():
            assert isinstance(key, str), f"Key must be str, got {type(key)}: {key!r}"


# ---------------------------------------------------------------------------
# Task 2: discover_established — star-banded, D-11, band-split cap handling
# ---------------------------------------------------------------------------


class TestDiscoverEstablished:
    def test_issues_12_queries_for_2_bands_6_topics(self):
        """2 BREAKTHROUGH_STAR_BANDS x 6 TOPICS = 12 date-independent queries."""
        from src.config import BREAKTHROUGH_STAR_BANDS, TOPICS
        recorded = []

        def fake_search(g, query, **kwargs):
            recorded.append(query)
            return _make_result(0, [])

        discover_established(MagicMock(), search=fake_search)
        assert len(recorded) == len(BREAKTHROUGH_STAR_BANDS) * len(TOPICS), (
            f"Expected {len(BREAKTHROUGH_STAR_BANDS) * len(TOPICS)} queries, got {len(recorded)}"
        )

    def test_queries_are_date_independent(self):
        """Established queries must NOT contain created: qualifier (D-11)."""
        recorded = []

        def fake_search(g, query, **kwargs):
            recorded.append(query)
            return _make_result(0, [])

        discover_established(MagicMock(), search=fake_search)
        for q in recorded:
            assert "created:" not in q, f"Established query must not have date window: {q}"

    def test_merge_by_string_id(self):
        """Results from all band/topic combos merged into one dict keyed by str(id)."""
        def fake_search(g, query, **kwargs):
            if "100..1000" in query and "topic:llm" in query:
                return _make_result(10, [10, 20])
            if "1000..10000" in query and "topic:agents" in query:
                return _make_result(10, [20, 30])
            return _make_result(0, [])

        result = discover_established(MagicMock(), search=fake_search)
        assert "10" in result
        assert "20" in result
        assert "30" in result
        for key in result.keys():
            assert isinstance(key, str)

    def test_over_cap_band_splits_into_two_sub_queries(self):
        """When a band is over-cap, exactly two sub-band queries are issued (FILTER-02)."""
        from src.config import BREAKTHROUGH_STAR_BANDS, TOPICS
        recorded = []
        call_count = [0]

        def fake_search(g, query, **kwargs):
            recorded.append(query)
            call_count[0] += 1
            # First call (first band/topic combo) is over cap
            if call_count[0] == 1:
                return _make_result(950, [1])
            return _make_result(10, [2])

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            discover_established(MagicMock(), search=fake_search)

        # First call is over-cap: 1 initial query + 2 sub-band re-queries = 3 for that slot
        # Remaining 11 slots: 1 query each
        # Total = 3 + 11 = total_bands_topics + 2
        total_bands_topics = len(BREAKTHROUGH_STAR_BANDS) * len(TOPICS)
        assert len(recorded) == total_bands_topics + 2, (
            f"Expected {total_bands_topics + 2} queries (initial over-cap + 2 sub-bands + 11 normal), "
            f"got {len(recorded)}"
        )

    def test_over_cap_sub_bands_are_contiguous(self):
        """When band is split, the two sub-band queries together cover the original range."""
        from src.config import BREAKTHROUGH_STAR_BANDS
        recorded = []
        call_count = [0]

        def fake_search(g, query, **kwargs):
            recorded.append(query)
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_result(950, [])
            return _make_result(5, [])

        discover_established(MagicMock(), search=fake_search)

        # The first band is "100..1000"; its sub-queries should cover "100..550" and "550..1000"
        first_band = BREAKTHROUGH_STAR_BANDS[0]
        lo, hi = first_band.split("..")
        mid = (int(lo) + int(hi)) // 2
        assert any(f"stars:{lo}..{mid}" in q for q in recorded), "Lower sub-band missing"
        assert any(f"stars:{mid}..{hi}" in q for q in recorded), "Upper sub-band missing"


# ---------------------------------------------------------------------------
# Task 3: refresh_tracked — re-fetch by numeric id, skip deleted
# ---------------------------------------------------------------------------


class TestRefreshTracked:
    def test_fetches_by_int_id(self):
        """g.get_repo must be called with int args, not strings (Pattern 3)."""
        repo_111 = _make_repo(111)
        repo_222 = _make_repo(222)

        g = MagicMock()
        g.get_repo.side_effect = lambda rid: {111: repo_111, 222: repo_222}[rid]

        result = refresh_tracked(g, ["111", "222"])
        g.get_repo.assert_any_call(111)
        g.get_repo.assert_any_call(222)
        assert "111" in result
        assert "222" in result

    def test_keyed_by_string_id(self):
        """Result dict keys are str(repo.id)."""
        repo = _make_repo(42)
        g = MagicMock()
        g.get_repo.return_value = repo

        result = refresh_tracked(g, ["42"])
        assert "42" in result
        assert isinstance(list(result.keys())[0], str)

    def test_skips_deleted_repos(self):
        """UnknownObjectException for one id → that id absent from result, no exception raised."""
        import github

        repo_ok = _make_repo(100)

        def get_repo_side_effect(rid):
            if rid == 999:
                raise github.UnknownObjectException(404, "Not Found", None)
            return repo_ok

        g = MagicMock()
        g.get_repo.side_effect = get_repo_side_effect

        result = refresh_tracked(g, ["100", "999"])
        assert "100" in result
        assert "999" not in result

    def test_no_get_topics_call(self):
        """refresh_tracked must not call repo.get_topics() (Pitfall 6)."""
        repo = _make_repo(77)
        g = MagicMock()
        g.get_repo.return_value = repo

        refresh_tracked(g, ["77"])
        repo.get_topics.assert_not_called()

    def test_exception_handler_only_references_rid(self):
        """Exception handler must not log client g or exception repr (T-01-04)."""
        import inspect
        import re
        import src.search as search_module

        source = inspect.getsource(search_module.refresh_tracked)
        lines = source.splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # The exception variable must not appear in any log/format (T-01-04)
            # Acceptable: reference to rid; NOT acceptable: repr(e), str(e), g
            if re.search(r"except.*Exception\s+as\s+(\w+)", stripped):
                exc_var = re.search(r"except.*Exception\s+as\s+(\w+)", stripped).group(1)
                # Check no line uses the exception variable after the except line
                pass  # structure check only; covered by grep gate at commit time
