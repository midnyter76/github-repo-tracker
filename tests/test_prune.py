"""Tests for src/prune.py — snapshot pruning (HARD-04) + metadata eviction (HARD-04-EXT).

Covers:
- prune_snapshots: non-existent directory → returns [] without raising
- prune_snapshots: empty directory → returns []
- prune_snapshots: old file (91 days) → deleted and returned in list
- prune_snapshots: recent file (yesterday) → kept, not in return list
- prune_snapshots: today's file → not deleted (cutoff is 90 days past)
- prune_snapshots: non-date filename (backup.json) → not deleted
- prune_snapshots: deleted file is actually gone from disk
- prune_snapshots: mixed directory — only old files deleted
- prune_metadata: missing metadata.json → returns [] without raising
- prune_metadata: first run, no ledger → seeds ledger, evicts nothing
- prune_metadata: reported repo never evicted even if ledger date is stale
- prune_metadata: stale non-reported repo evicted
- prune_metadata: within-window non-reported repo kept
- prune_metadata: evicted repo removed from disk; kept repo byte-for-byte preserved
- prune_metadata: ledger self-cleans (drops rids no longer in metadata)
- prune_metadata: corrupt metadata.json / ledger.json → warns, treats as empty
- prune_metadata: reported_ids referencing unknown rid does not crash or resurrect
- prune_seen: recent/stale/boundary first_seen entries, missing/malformed first_seen,
  non-mutation of the input dict (HARD-04-SEEN)

All tests use tmp_path so no writes ever touch the real data/snapshots directory.
"""
import json
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _now() -> datetime:
    """Fixed reference datetime for deterministic tests."""
    return datetime(2026, 6, 28, 13, 0, 0, tzinfo=timezone.utc)


def _snapshot_path(d: Path, days_ago: int, now: datetime = None) -> Path:
    """Create a dummy snapshot file in d with stem = (now - days_ago) date."""
    if now is None:
        now = _now()
    file_date = (now - timedelta(days=days_ago)).date()
    path = d / f"{file_date}.json"
    path.write_text('{"date": "' + str(file_date) + '", "repos": {}}')
    return path


class TestPruneSnapshots:
    def test_nonexistent_directory_returns_empty(self, tmp_path: Path):
        """Returns [] without raising when snapshots_dir does not exist."""
        from src.prune import prune_snapshots

        missing_dir = tmp_path / "nonexistent"
        result = prune_snapshots(_now(), snapshots_dir=missing_dir, retention_days=90)
        assert result == []

    def test_empty_directory_returns_empty(self, tmp_path: Path):
        """Returns [] when directory exists but contains no snapshot files."""
        from src.prune import prune_snapshots

        result = prune_snapshots(_now(), snapshots_dir=tmp_path, retention_days=90)
        assert result == []

    def test_old_file_deleted_and_returned(self, tmp_path: Path):
        """File with stem date 91 days ago is deleted and included in return list."""
        from src.prune import prune_snapshots

        old_file = _snapshot_path(tmp_path, days_ago=91)
        result = prune_snapshots(_now(), snapshots_dir=tmp_path, retention_days=90)
        assert old_file in result, "Old file must be returned in deleted list"

    def test_recent_file_kept(self, tmp_path: Path):
        """File with stem date yesterday is NOT deleted."""
        from src.prune import prune_snapshots

        recent_file = _snapshot_path(tmp_path, days_ago=1)
        result = prune_snapshots(_now(), snapshots_dir=tmp_path, retention_days=90)
        assert recent_file not in result, "Recent file must not be pruned"
        assert recent_file.exists(), "Recent file must still exist on disk"

    def test_todays_file_not_deleted(self, tmp_path: Path):
        """Today's snapshot is never deleted — cutoff is 90 days in the past."""
        from src.prune import prune_snapshots

        todays_file = _snapshot_path(tmp_path, days_ago=0)
        result = prune_snapshots(_now(), snapshots_dir=tmp_path, retention_days=90)
        assert todays_file not in result, "Today's file must not be pruned"
        assert todays_file.exists()

    def test_non_date_filename_not_deleted(self, tmp_path: Path):
        """Non-date-named .json files (e.g. backup.json) are ignored."""
        from src.prune import prune_snapshots

        backup = tmp_path / "backup.json"
        backup.write_text('{"note": "should not be deleted"}')
        result = prune_snapshots(_now(), snapshots_dir=tmp_path, retention_days=90)
        assert backup not in result, "Non-date file must not be pruned"
        assert backup.exists(), "Non-date file must still exist on disk"

    def test_deleted_file_gone_from_disk(self, tmp_path: Path):
        """Pruned files are actually removed from disk, not just returned."""
        from src.prune import prune_snapshots

        old_file = _snapshot_path(tmp_path, days_ago=91)
        assert old_file.exists(), "Setup: file must exist before pruning"
        prune_snapshots(_now(), snapshots_dir=tmp_path, retention_days=90)
        assert not old_file.exists(), "Pruned file must no longer exist on disk"

    def test_mixed_directory_only_old_deleted(self, tmp_path: Path):
        """In a mixed directory, only files outside the retention window are deleted."""
        from src.prune import prune_snapshots

        old_file = _snapshot_path(tmp_path, days_ago=91)
        recent_file = _snapshot_path(tmp_path, days_ago=30)
        todays_file = _snapshot_path(tmp_path, days_ago=0)

        result = prune_snapshots(_now(), snapshots_dir=tmp_path, retention_days=90)

        assert old_file in result, "File 91 days old must be pruned"
        assert recent_file not in result, "File 30 days old must NOT be pruned"
        assert todays_file not in result, "Today's file must NOT be pruned"
        assert not old_file.exists()
        assert recent_file.exists()
        assert todays_file.exists()


def _write_metadata(path: Path, repos: dict, updated_at: str = "2026-06-28T13:00:00+00:00") -> None:
    """Write a minimal metadata.json (mirrors src/store.py write_metadata schema)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"updated_at": updated_at, "repos": repos}, indent=2))


def _repo_entry(suffix: str = "") -> dict:
    return {
        "full_name": f"owner/repo{suffix}",
        "description": f"desc{suffix}",
        "created_at": "2026-01-01T00:00:00+00:00",
        "html_url": f"https://github.com/owner/repo{suffix}",
    }


def _write_ledger(path: Path, entries: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2))


class TestPruneMetadata:
    def test_missing_metadata_returns_empty(self, tmp_path: Path):
        """No metadata.json → returns [] without raising."""
        from src.prune import prune_metadata

        result = prune_metadata(
            _now(), [],
            metadata_path=tmp_path / "metadata.json",
            ledger_path=tmp_path / "ledger.json",
            retention_days=14,
        )
        assert result == []

    def test_first_run_no_ledger_seeds_and_evicts_nothing(self, tmp_path: Path):
        """First run (ledger absent): every tracked repo stamped today; nothing evicted."""
        from src.prune import prune_metadata

        meta_path = tmp_path / "metadata.json"
        ledger_path = tmp_path / "ledger.json"
        _write_metadata(meta_path, {"111": _repo_entry("1"), "222": _repo_entry("2")})

        result = prune_metadata(
            _now(), [],
            metadata_path=meta_path, ledger_path=ledger_path, retention_days=14,
        )

        assert result == []
        assert ledger_path.exists(), "Ledger file must be created on first run"
        ledger = json.loads(ledger_path.read_text())
        assert ledger["111"] == "2026-06-28"
        assert ledger["222"] == "2026-06-28"
        # metadata unchanged — both repos still present
        on_disk = json.loads(meta_path.read_text())
        assert set(on_disk["repos"].keys()) == {"111", "222"}

    def test_reported_repo_never_evicted_even_if_stale(self, tmp_path: Path):
        """A repo id in reported_ids gets stamped today and is never evicted this run."""
        from src.prune import prune_metadata

        meta_path = tmp_path / "metadata.json"
        ledger_path = tmp_path / "ledger.json"
        _write_metadata(meta_path, {"111": _repo_entry("1")})
        # Ledger date far older than the 14-day retention window
        _write_ledger(ledger_path, {"111": "2026-01-01"})

        result = prune_metadata(
            _now(), ["111"],
            metadata_path=meta_path, ledger_path=ledger_path, retention_days=14,
        )

        assert result == [], "Reported repo must not be evicted"
        on_disk = json.loads(meta_path.read_text())
        assert "111" in on_disk["repos"]
        ledger = json.loads(ledger_path.read_text())
        assert ledger["111"] == "2026-06-28", "Reported repo's ledger date must refresh to today"

    def test_stale_non_reported_repo_evicted(self, tmp_path: Path):
        """A tracked repo NOT in reported_ids, with a ledger date older than the cutoff, is evicted."""
        from src.prune import prune_metadata

        meta_path = tmp_path / "metadata.json"
        ledger_path = tmp_path / "ledger.json"
        _write_metadata(meta_path, {"111": _repo_entry("1")})
        _write_ledger(ledger_path, {"111": "2026-01-01"})  # far older than 14d cutoff

        result = prune_metadata(
            _now(), [],
            metadata_path=meta_path, ledger_path=ledger_path, retention_days=14,
        )

        assert result == ["111"]

    def test_within_window_non_reported_repo_kept(self, tmp_path: Path):
        """A tracked repo NOT in reported_ids, ledger date within the retention window, is kept."""
        from src.prune import prune_metadata

        meta_path = tmp_path / "metadata.json"
        ledger_path = tmp_path / "ledger.json"
        _write_metadata(meta_path, {"111": _repo_entry("1")})
        # 5 days ago — within a 14-day retention window
        recent_date = (_now() - timedelta(days=5)).date().isoformat()
        _write_ledger(ledger_path, {"111": recent_date})

        result = prune_metadata(
            _now(), [],
            metadata_path=meta_path, ledger_path=ledger_path, retention_days=14,
        )

        assert result == []
        on_disk = json.loads(meta_path.read_text())
        assert "111" in on_disk["repos"]

    def test_evicted_gone_kept_preserved_byte_for_byte(self, tmp_path: Path):
        """Evicted repo is removed from disk; a kept repo's entry is preserved exactly."""
        from src.prune import prune_metadata

        meta_path = tmp_path / "metadata.json"
        ledger_path = tmp_path / "ledger.json"
        kept_entry = _repo_entry("-kept")
        _write_metadata(meta_path, {"111": _repo_entry("-stale"), "222": kept_entry})
        _write_ledger(ledger_path, {"111": "2026-01-01", "222": "2026-06-27"})

        result = prune_metadata(
            _now(), [],
            metadata_path=meta_path, ledger_path=ledger_path, retention_days=14,
        )

        assert result == ["111"]
        on_disk = json.loads(meta_path.read_text())
        assert "111" not in on_disk["repos"], "Evicted repo must be gone from disk"
        assert on_disk["repos"]["222"] == kept_entry, "Kept repo entry must be byte-for-byte preserved"

    def test_ledger_self_cleans(self, tmp_path: Path):
        """Ledger entries whose rid is no longer in metadata are dropped (no unbounded growth)."""
        from src.prune import prune_metadata

        meta_path = tmp_path / "metadata.json"
        ledger_path = tmp_path / "ledger.json"
        _write_metadata(meta_path, {"111": _repo_entry("1")})
        # Ledger has a stale rid ("999") that no longer exists in metadata.
        _write_ledger(ledger_path, {"111": "2026-06-27", "999": "2020-01-01"})

        prune_metadata(
            _now(), [],
            metadata_path=meta_path, ledger_path=ledger_path, retention_days=14,
        )

        ledger = json.loads(ledger_path.read_text())
        assert "999" not in ledger, "Ledger must self-clean rids no longer tracked in metadata"
        assert "111" in ledger

    def test_corrupt_metadata_treated_as_empty(self, tmp_path: Path):
        """Corrupt metadata.json → warns and treats as empty (no raise)."""
        from src.prune import prune_metadata

        meta_path = tmp_path / "metadata.json"
        ledger_path = tmp_path / "ledger.json"
        meta_path.write_text("{not valid json")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = prune_metadata(
                _now(), [],
                metadata_path=meta_path, ledger_path=ledger_path, retention_days=14,
            )
        assert result == []
        assert any("Corrupt" in str(warning.message) for warning in w)

    def test_corrupt_ledger_treated_as_empty(self, tmp_path: Path):
        """Corrupt tracked_ledger.json → warns and treats as empty (no raise); repo re-seeded today."""
        from src.prune import prune_metadata

        meta_path = tmp_path / "metadata.json"
        ledger_path = tmp_path / "ledger.json"
        _write_metadata(meta_path, {"111": _repo_entry("1")})
        ledger_path.write_text("{not valid json")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = prune_metadata(
                _now(), [],
                metadata_path=meta_path, ledger_path=ledger_path, retention_days=14,
            )
        assert result == [], "Corrupt ledger must be treated as empty (fresh grace), not fatal"
        assert any("Corrupt" in str(warning.message) for warning in w)
        ledger = json.loads(ledger_path.read_text())
        assert ledger["111"] == "2026-06-28"

    def test_reported_id_not_in_metadata_does_not_crash_or_resurrect(self, tmp_path: Path):
        """reported_ids referencing an rid absent from metadata does not crash or resurrect it."""
        from src.prune import prune_metadata

        meta_path = tmp_path / "metadata.json"
        ledger_path = tmp_path / "ledger.json"
        _write_metadata(meta_path, {"111": _repo_entry("1")})

        # "999" is not tracked in metadata at all.
        result = prune_metadata(
            _now(), ["111", "999"],
            metadata_path=meta_path, ledger_path=ledger_path, retention_days=14,
        )

        assert result == []
        on_disk = json.loads(meta_path.read_text())
        assert "999" not in on_disk["repos"], "Untracked rid must not be resurrected into metadata"

    def test_all_prunesnapshots_tests_unaffected(self):
        """Sanity: importing prune_metadata does not break the prune_snapshots namespace."""
        from src.prune import prune_metadata, prune_snapshots

        assert callable(prune_metadata)
        assert callable(prune_snapshots)


class TestPruneSeen:
    """prune_seen() drops seen.json entries whose first_seen predates the
    retention window (HARD-04-SEEN)."""

    def test_recent_entry_kept_unchanged(self):
        """Entry with first_seen 27 days old (retention_days=90) is kept, value unchanged."""
        from src.prune import prune_seen

        now = _now()
        recent_date = (now - timedelta(days=27)).date().isoformat()
        seen = {"111": {"first_seen": recent_date}}

        result = prune_seen(seen, now, retention_days=90)

        assert result == {"111": {"first_seen": recent_date}}

    def test_stale_entry_dropped(self):
        """Entry with first_seen ~178 days old (retention_days=90) is dropped."""
        from src.prune import prune_seen

        now = _now()
        stale_date = (now - timedelta(days=178)).date().isoformat()
        seen = {"111": {"first_seen": stale_date}}

        result = prune_seen(seen, now, retention_days=90)

        assert "111" not in result

    def test_boundary_cutoff_date_kept(self):
        """With retention_days=10, an entry dated exactly at the cutoff is KEPT (>=)."""
        from src.prune import prune_seen

        now = _now()
        cutoff_date = (now - timedelta(days=10)).date().isoformat()
        seen = {"111": {"first_seen": cutoff_date}}

        result = prune_seen(seen, now, retention_days=10)

        assert "111" in result

    def test_boundary_one_day_past_cutoff_pruned(self):
        """With retention_days=10, an entry one day older than the cutoff is PRUNED."""
        from src.prune import prune_seen

        now = _now()
        past_cutoff_date = (now - timedelta(days=11)).date().isoformat()
        seen = {"111": {"first_seen": past_cutoff_date}}

        result = prune_seen(seen, now, retention_days=10)

        assert "111" not in result

    def test_missing_first_seen_kept(self):
        """Entry missing first_seen is kept as-is, no crash."""
        from src.prune import prune_seen

        now = _now()
        seen = {"111": {}}

        result = prune_seen(seen, now, retention_days=90)

        assert result == {"111": {}}

    def test_malformed_first_seen_kept_and_warns(self):
        """Entry with malformed first_seen is kept as-is, warning emitted."""
        from src.prune import prune_seen

        now = _now()
        seen = {"111": {"first_seen": "not-a-date"}}

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = prune_seen(seen, now, retention_days=90)

        assert result == {"111": {"first_seen": "not-a-date"}}
        assert any("first_seen" in str(warning.message) for warning in w)

    def test_input_dict_not_mutated(self):
        """prune_seen must not mutate the input dict."""
        from src.prune import prune_seen

        now = _now()
        stale_date = (now - timedelta(days=178)).date().isoformat()
        seen = {
            "111": {"first_seen": stale_date},
            "222": {"first_seen": now.date().isoformat()},
        }
        original_keys = set(seen.keys())

        prune_seen(seen, now, retention_days=90)

        assert set(seen.keys()) == original_keys, "input dict key set must be unchanged"
