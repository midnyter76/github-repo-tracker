"""Tests for src/gap.py — gap detection (HARD-02).

Covers:
- check_gap: first-run safe (no snapshots)
- check_gap: silent when snapshot is recent
- check_gap: prints WARNING when snapshot older than threshold
- check_gap: safe when snapshot JSON is corrupt
- check_gap: non-date .json files don't shadow real dated snapshots
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


class TestCheckGap:
    def test_no_snapshots_returns_silently(self, tmp_path: Path):
        """Returns silently (no print, no exception) when snapshots_dir is empty."""
        from src.gap import check_gap

        now = datetime(2026, 6, 28, 13, 0, 0, tzinfo=timezone.utc)
        check_gap(now, snapshots_dir=tmp_path)  # must not raise

    def test_recent_snapshot_is_silent(self, tmp_path: Path, capsys):
        """Silent when captured_at is within warn_hours."""
        from src.gap import check_gap

        now = datetime(2026, 6, 28, 13, 0, 0, tzinfo=timezone.utc)
        one_hour_ago = now - timedelta(hours=1)
        (tmp_path / "2026-06-28.json").write_text(
            json.dumps({"captured_at": one_hour_ago.isoformat(), "repos": {}})
        )
        check_gap(now, snapshots_dir=tmp_path, warn_hours=26.0)
        assert capsys.readouterr().out == ""

    def test_old_snapshot_prints_warning(self, tmp_path: Path, capsys):
        """Prints WARNING when captured_at is older than warn_hours."""
        from src.gap import check_gap

        now = datetime(2026, 6, 28, 13, 0, 0, tzinfo=timezone.utc)
        thirty_hours_ago = now - timedelta(hours=30)
        (tmp_path / "2026-06-27.json").write_text(
            json.dumps({"captured_at": thirty_hours_ago.isoformat(), "repos": {}})
        )
        check_gap(now, snapshots_dir=tmp_path, warn_hours=26.0)
        out = capsys.readouterr().out
        assert "WARNING:" in out
        assert "2026-06-27.json" in out
        assert "30.0h ago" in out

    def test_corrupt_json_does_not_raise(self, tmp_path: Path):
        """Swallows corrupt JSON without raising."""
        from src.gap import check_gap

        now = datetime(2026, 6, 28, 13, 0, 0, tzinfo=timezone.utc)
        (tmp_path / "2026-06-27.json").write_text("{not valid json}")
        check_gap(now, snapshots_dir=tmp_path)  # must not raise

    def test_non_date_json_file_not_picked_as_latest(self, tmp_path: Path, capsys):
        """Non-date .json files (e.g. backup.json) don't prevent real gap detection."""
        from src.gap import check_gap

        now = datetime(2026, 6, 28, 13, 0, 0, tzinfo=timezone.utc)
        thirty_hours_ago = now - timedelta(hours=30)
        # Old dated snapshot — should trigger WARNING
        (tmp_path / "2026-06-27.json").write_text(
            json.dumps({"captured_at": thirty_hours_ago.isoformat(), "repos": {}})
        )
        # Non-date file with a recent timestamp — must be ignored
        (tmp_path / "backup.json").write_text(
            json.dumps({"captured_at": now.isoformat()})
        )
        check_gap(now, snapshots_dir=tmp_path, warn_hours=26.0)
        out = capsys.readouterr().out
        assert "WARNING:" in out, "Old dated snapshot should trigger warning even with backup.json present"
