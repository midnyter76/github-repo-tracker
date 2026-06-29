"""Gap detection for GitHub Repo Tracker (HARD-02).

check_gap() emits a stdout WARNING when the last snapshot's captured_at
field indicates the previous collection run was missed.

First-run safe: returns silently when no snapshots exist.
Does not raise — a corrupt or missing captured_at is silently skipped.
"""
import json
from datetime import datetime
from pathlib import Path

from src.config import GAP_WARN_HOURS, SNAPSHOTS_DIR


def check_gap(
    now: datetime,
    snapshots_dir: Path = SNAPSHOTS_DIR,
    warn_hours: float = GAP_WARN_HOURS,
) -> None:
    """Emit stdout WARNING if last collection gap exceeds warn_hours (HARD-02, D-04/D-05).

    Reads the `captured_at` field from the most recent date-named snapshot JSON.
    Uses lexicographic max over date-parseable stems (ISO 8601 dates sort correctly).
    Ignores non-date files (e.g. backup.json) via strptime stem filter.

    Args:
        now:           Current UTC datetime.
        snapshots_dir: Directory containing per-date snapshot JSON files.
        warn_hours:    Gap threshold in hours; default from config.GAP_WARN_HOURS.
    """
    # Filter to date-parseable stems to avoid non-date files shadowing real snapshots.
    date_files = []
    for p in snapshots_dir.glob("*.json"):
        try:
            datetime.strptime(p.stem, "%Y-%m-%d")
            date_files.append(p)
        except ValueError:
            pass  # skip non-date files (e.g. backup.json)

    if not date_files:
        return  # first run — no prior snapshot exists

    # Lexicographic max is the most-recent date (ISO 8601 sort property).
    latest = max(date_files, key=lambda p: p.stem)
    try:
        data = json.loads(latest.read_text())
        captured_at = datetime.fromisoformat(data["captured_at"])
        delta_hours = (now - captured_at).total_seconds() / 3600
        if delta_hours > warn_hours:
            print(
                f"WARNING: Last snapshot {latest.name} was {delta_hours:.1f}h ago "
                f"(threshold: {warn_hours}h). A collection run may have been missed."
            )
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        pass  # don't crash on malformed/mixed-tz snapshot — gap check is best-effort
