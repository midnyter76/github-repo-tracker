"""Tests for src/prune.py — snapshot pruning (HARD-04).

Covers:
- prune_snapshots: non-existent directory → returns [] without raising
- prune_snapshots: empty directory → returns []
- prune_snapshots: old file (91 days) → deleted and returned in list
- prune_snapshots: recent file (yesterday) → kept, not in return list
- prune_snapshots: today's file → not deleted (cutoff is 90 days past)
- prune_snapshots: non-date filename (backup.json) → not deleted
- prune_snapshots: deleted file is actually gone from disk
- prune_snapshots: mixed directory — only old files deleted

All tests use tmp_path so no writes ever touch the real data/snapshots directory.
"""
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
