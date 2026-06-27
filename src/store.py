"""Persistence layer for GitHub Repo Tracker.

Functions:
  write_snapshot  — idempotent per-date star snapshot (DATA-02, DATA-04, DATA-05)
  write_metadata  — separate, fully-overwritten metadata store (DATA-03)
  load_metadata   — read metadata file, returns {} when absent
  load_metadata_ids — list of str repo-id keys (input to Plan 02 refresh_tracked)

NOTE: run_at MUST be timezone-aware UTC (callers pass datetime.now(timezone.utc)).
All stored timestamps are UTC ISO 8601 per D-07 / DATA-05.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from src.config import METADATA_PATH, SNAPSHOTS_DIR


def write_snapshot(
    repos: dict,
    run_at: datetime,
    snapshots_dir: Path = SNAPSHOTS_DIR,
) -> Path:
    """Write idempotent per-date snapshot of star counts (DATA-02, DATA-04, DATA-05).

    Snapshot schema (Pattern 9):
        {
            "date": "YYYY-MM-DD",
            "captured_at": "<UTC ISO 8601 string>",
            "repos": {"<str repo id>": {"stars": <int>}, ...}
        }

    Idempotency (DATA-04 / Pitfall 5): if a snapshot for this date already exists,
    the existing repos are loaded and merged with the new ones. The new run only
    adds or updates entries — it never drops repos written by a prior same-day run.

    Args:
        repos:        dict mapping str(repo.id) → repo object (with .stargazers_count)
        run_at:       timezone-aware UTC datetime; controls filename and captured_at
        snapshots_dir: injectable for tests (defaults to SNAPSHOTS_DIR from config)

    Returns:
        Path to the written snapshot file.
    """
    date_str = run_at.strftime("%Y-%m-%d")
    snap_path = snapshots_dir / f"{date_str}.json"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    # Load existing snapshot to merge (handles same-day retry — DATA-04 / Pitfall 5)
    existing = {}
    if snap_path.exists():
        existing = json.loads(snap_path.read_text()).get("repos", {})

    # Upsert: existing entries survive; new entries overwrite by id (new value wins)
    stars = {**existing, **{rid: {"stars": r.stargazers_count} for rid, r in repos.items()}}

    snapshot = {
        "date": date_str,
        "captured_at": run_at.isoformat(),
        "repos": stars,
    }
    snap_path.write_text(json.dumps(snapshot, indent=2))
    return snap_path


def write_metadata(
    repos: dict,
    run_at: datetime,
    metadata_path: Path = METADATA_PATH,
) -> Path:
    """Write metadata store — FULL OVERWRITE each run (DATA-03).

    Metadata schema (Pattern 9):
        {
            "updated_at": "<UTC ISO 8601 string>",
            "repos": {
                "<str repo id>": {
                    "full_name": "owner/repo",
                    "description": "<str, never null>",
                    "created_at": "<UTC ISO 8601 string>",
                    "html_url": "https://github.com/owner/repo"
                },
                ...
            }
        }

    Unlike write_snapshot, this is a FULL OVERWRITE — no merging with existing data.
    Writing {"111"} then {"222"} leaves only {"222"} in the file (DATA-03).
    Topics are intentionally omitted (Pitfall 6 — the PyGithub topics accessor
    makes an extra API call per repo; not required for Phase 2 velocity ranking).

    Args:
        repos:         dict mapping str(repo.id) → repo object
        run_at:        timezone-aware UTC datetime; sets updated_at
        metadata_path: injectable for tests (defaults to METADATA_PATH from config)

    Returns:
        Path to the written metadata file.
    """
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "updated_at": run_at.isoformat(),
        "repos": {
            rid: {
                "full_name": r.full_name,
                "description": r.description or "",
                "created_at": r.created_at.isoformat(),
                "html_url": r.html_url,
            }
            for rid, r in repos.items()
        },
    }
    metadata_path.write_text(json.dumps(metadata, indent=2))
    return metadata_path


def load_metadata(metadata_path: Path = METADATA_PATH) -> dict:
    """Load the metadata store. Returns {} when the file is absent.

    Args:
        metadata_path: injectable for tests (defaults to METADATA_PATH from config)

    Returns:
        Parsed metadata dict, or {} if the file does not exist.
    """
    if not metadata_path.exists():
        return {}
    return json.loads(metadata_path.read_text())


def load_metadata_ids(metadata_path: Path = METADATA_PATH) -> list[str]:
    """Return the list of tracked repo-id string keys from the metadata store.

    This is the input consumed by Plan 02's refresh_tracked — it tells the
    refresher which numeric IDs to re-fetch from the GitHub Core API.

    Args:
        metadata_path: injectable for tests (defaults to METADATA_PATH from config)

    Returns:
        List of str repo-id keys (e.g. ["12345678", "87654321"]), empty if absent.
    """
    return list(load_metadata(metadata_path).get("repos", {}).keys())
