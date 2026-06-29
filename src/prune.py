"""Snapshot pruning for GitHub Repo Tracker (HARD-04).

prune_snapshots() deletes per-date snapshot JSON files older than retention_days
to bound repository size growth. Uses filename-date comparison (not mtime — mtime
is unreliable in GitHub Actions due to checkout resetting all timestamps).

Returns list of deleted Paths for test assertions without mocking.
"""
from datetime import date, datetime, timedelta
from pathlib import Path

from src.config import SNAPSHOT_RETENTION_DAYS, SNAPSHOTS_DIR


def prune_snapshots(
    now: datetime,
    snapshots_dir: Path = SNAPSHOTS_DIR,
    retention_days: int = SNAPSHOT_RETENTION_DAYS,
) -> list[Path]:
    """Delete snapshot files older than retention_days (HARD-04, D-08/D-09).

    Pruning is by filename date (YYYY-MM-DD.json stem), not mtime.
    Non-date-named files are silently ignored.
    Safe to call when snapshots_dir does not exist — returns [].

    Args:
        now:            Current UTC datetime (used to compute cutoff date).
        snapshots_dir:  Directory containing per-date snapshot files.
        retention_days: Files with stem date older than this are deleted.

    Returns:
        List of deleted file Paths (empty if nothing pruned).
    """
    if not snapshots_dir.exists():
        return []

    cutoff = (now - timedelta(days=retention_days)).date()
    pruned: list[Path] = []

    for snap_path in snapshots_dir.glob("*.json"):
        try:
            snap_date = date.fromisoformat(snap_path.stem)
        except ValueError:
            continue  # ignore non-date-named files (e.g. backup.json)

        if snap_date < cutoff:
            snap_path.unlink()
            pruned.append(snap_path)

    return pruned
