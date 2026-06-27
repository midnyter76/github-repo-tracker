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
