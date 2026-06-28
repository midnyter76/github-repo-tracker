"""Tests for src/seen.py — seen-store module.

Covers:
- load_seen: absent file, corrupt JSON (warns), valid round-trip
- save_seen: creates missing parent directory, writes indent-2 JSON
- classify_and_update: new marker + first_seen, returning marker, non-mutation, same-day retry
"""

import json
import warnings
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Task 1 minimal tests (RED phase) — expanded in Task 2
# ---------------------------------------------------------------------------


class TestLoadSeen:
    def test_absent_file_returns_empty_dict(self, tmp_path: Path):
        """load_seen returns {} when the file does not exist."""
        from src.seen import load_seen

        result = load_seen(tmp_path / "no_such_file.json")
        assert result == {}

    def test_corrupt_json_warns_and_returns_empty(self, tmp_path: Path):
        """load_seen warns (UserWarning) and returns {} on corrupt JSON."""
        from src.seen import load_seen

        corrupt = tmp_path / "seen.json"
        corrupt.write_text("not valid json {{{")

        with pytest.warns(UserWarning, match="Corrupt seen-store"):
            result = load_seen(corrupt)
        assert result == {}

    def test_valid_file_returns_parsed_dict(self, tmp_path: Path):
        """load_seen returns the parsed dict from a valid seen.json."""
        from src.seen import load_seen

        data = {"123": {"first_seen": "2026-06-01"}}
        p = tmp_path / "seen.json"
        p.write_text(json.dumps(data))

        assert load_seen(p) == data


class TestClassifyAndUpdate:
    def test_unseen_repo_marked_new(self):
        """New repo gets marker 'new' and first_seen in updated_seen."""
        from src.seen import classify_and_update

        markers, updated = classify_and_update({}, ["42"], "2026-06-28")

        assert markers["42"] == "new"
        assert updated["42"] == {"first_seen": "2026-06-28"}

    def test_seen_repo_marked_returning(self):
        """Known repo gets marker 'returning'; its first_seen is preserved."""
        from src.seen import classify_and_update

        seen = {"99": {"first_seen": "2026-06-01"}}
        markers, updated = classify_and_update(seen, ["99"], "2026-06-28")

        assert markers["99"] == "returning"
        assert updated["99"]["first_seen"] == "2026-06-01"


# ---------------------------------------------------------------------------
# Task 2 comprehensive tests
# ---------------------------------------------------------------------------


class TestSaveSeen:
    def test_creates_missing_parent_directory(self, tmp_path: Path):
        """save_seen creates parent dirs and writes indent-2 JSON."""
        from src.seen import save_seen

        nested = tmp_path / "some" / "nested" / "seen.json"
        data = {"1": {"first_seen": "2026-06-28"}}
        save_seen(data, nested)

        assert nested.exists()
        on_disk = json.loads(nested.read_text())
        assert on_disk == data
        # Confirm indent=2 formatting
        assert "  " in nested.read_text()

    def test_roundtrip_with_load_seen(self, tmp_path: Path):
        """save_seen + load_seen round-trips a dict exactly."""
        from src.seen import load_seen, save_seen

        p = tmp_path / "seen.json"
        data = {"101": {"first_seen": "2026-06-01"}, "202": {"first_seen": "2026-06-15"}}
        save_seen(data, p)
        assert load_seen(p) == data


class TestClassifyAndUpdateComprehensive:
    def test_input_dict_not_mutated(self):
        """classify_and_update must not mutate the input seen dict."""
        from src.seen import classify_and_update

        seen = {"55": {"first_seen": "2026-06-01"}}
        original_keys = set(seen.keys())
        classify_and_update(seen, ["55", "999"], "2026-06-28")

        assert set(seen.keys()) == original_keys
        assert "999" not in seen

    def test_mixed_new_and_returning(self):
        """Both new and returning repos classified correctly in one call."""
        from src.seen import classify_and_update

        seen = {"1": {"first_seen": "2026-06-01"}}
        markers, updated = classify_and_update(seen, ["1", "2"], "2026-06-28")

        assert markers == {"1": "returning", "2": "new"}
        assert "2" in updated
        assert updated["1"]["first_seen"] == "2026-06-01"


class TestSameDayRetry:
    def test_same_day_retry_classifies_returning(self, tmp_path: Path):
        """D-10: simulate run 1 -> save -> run 2 same day; run 2 sees 'returning'."""
        from src.seen import classify_and_update, load_seen, save_seen

        seen_path = tmp_path / "seen.json"

        # Run 1: new repo
        seen1 = load_seen(seen_path)
        markers1, updated1 = classify_and_update(seen1, ["7"], "2026-06-28")
        assert markers1["7"] == "new"
        save_seen(updated1, seen_path)

        # Run 2 (same day): re-classify the same repo
        seen2 = load_seen(seen_path)
        markers2, _ = classify_and_update(seen2, ["7"], "2026-06-28")
        assert markers2["7"] == "returning", (
            "Same-day retry must classify a previously-saved repo as returning"
        )
