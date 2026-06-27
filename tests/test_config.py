"""Tests for src/config.py — FILTER-04 configurable constants (D-01/02/03/04/11)."""


def test_topics_exact_six_llm_era():
    """D-01: TOPICS equals exactly the 6 LLM-era topics in order."""
    from src.config import TOPICS

    assert TOPICS == [
        "llm",
        "large-language-models",
        "agents",
        "rag",
        "generative-ai",
        "llmops",
    ]
    assert len(TOPICS) == 6


def test_keyword_star_floor():
    """D-02: KEYWORD_STAR_FLOOR == 10."""
    from src.config import KEYWORD_STAR_FLOOR

    assert KEYWORD_STAR_FLOOR == 10


def test_breakthrough_star_bands():
    """D-11 / Pattern 5a: BREAKTHROUGH_STAR_BANDS == ["100..1000", "1000..10000"] and length 2."""
    from src.config import BREAKTHROUGH_STAR_BANDS

    assert BREAKTHROUGH_STAR_BANDS == ["100..1000", "1000..10000"]
    assert len(BREAKTHROUGH_STAR_BANDS) == 2


def test_new_repo_windows_contains_7_and_30():
    """D-04: NEW_REPO_WINDOWS contains both 7 (weekly) and 30 (monthly) creation windows."""
    from src.config import NEW_REPO_WINDOWS

    assert 7 in NEW_REPO_WINDOWS
    assert 30 in NEW_REPO_WINDOWS


def test_total_count_cap_warn():
    """FILTER-02 / Pitfall 2: TOTAL_COUNT_CAP_WARN == 900 and is < 1000."""
    from src.config import TOTAL_COUNT_CAP_WARN

    assert TOTAL_COUNT_CAP_WARN == 900
    assert TOTAL_COUNT_CAP_WARN < 1000


def test_qualifier_exclusions():
    """D-02/D-03/FILTER-03: QUALIFIER_EXCLUSIONS == "fork:false archived:false"."""
    from src.config import QUALIFIER_EXCLUSIONS

    assert QUALIFIER_EXCLUSIONS == "fork:false archived:false"


def test_snapshots_dir_path():
    """Pattern 9: SNAPSHOTS_DIR is a Path ending in data/snapshots."""
    from src.config import SNAPSHOTS_DIR
    from pathlib import Path

    assert isinstance(SNAPSHOTS_DIR, Path)
    # Use .as_posix() to avoid Windows backslash vs forward-slash mismatch
    assert SNAPSHOTS_DIR.as_posix().endswith("data/snapshots")


def test_metadata_path():
    """Pattern 9: METADATA_PATH ends in data/metadata.json."""
    from src.config import METADATA_PATH
    from pathlib import Path

    assert isinstance(METADATA_PATH, Path)
    assert METADATA_PATH.as_posix().endswith("data/metadata.json")
