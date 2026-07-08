"""Seen-store for GitHub Repo Tracker.

Tracks which repos have been reported so they can be classified as new (🆕)
or returning (↩) in the digest. Keyed by numeric repo id (as a string key),
never by owner/name slug — this survives repo renames and transfers (D-09).

Functions:
  load_seen            — read data/seen.json; returns {} when absent, aborts on corrupt
  save_seen            — write data/seen.json with indent=2; creates parent dir
  classify_and_update  — produce {rid: "new"|"returning"} markers + updated dict
                         WITHOUT mutating the input or writing to disk (D-10)

Decision references:
  D-08: 🆕 new / ↩ returning markers
  D-09: data/seen.json keyed by str(repo.id), first_seen date per entry
  D-10: caller writes the updated store AFTER the report file is written
"""

import json
from pathlib import Path

from src import config


def load_seen(seen_path: Path = config.SEEN_PATH) -> dict:
    """Load the seen-store. Returns {} when the file is absent.

    Aborts the run on corrupt JSON (T-uec-01): the corrupt file is renamed to
    `<name>.corrupt` (preserved for manual inspection) and a RuntimeError is
    raised. This is a primary load path — a downstream write would otherwise
    silently overwrite it with only this run's results, permanently erasing
    prior 🆕/↩ history. A crashed Actions run is recoverable; a silent wipe
    is not.

    Args:
        seen_path: path to data/seen.json (injectable for tests).

    Returns:
        Parsed seen dict, or {} if the file does not exist.

    Raises:
        RuntimeError: if the file contains invalid JSON.
    """
    if not seen_path.exists():
        return {}
    try:
        return json.loads(seen_path.read_text())
    except json.JSONDecodeError as exc:
        corrupt_path = seen_path.with_name(seen_path.name + ".corrupt")
        seen_path.replace(corrupt_path)
        raise RuntimeError(
            f"Corrupt seen-store at {seen_path}; moved to {corrupt_path} for inspection."
        ) from exc


def save_seen(seen: dict, seen_path: Path = config.SEEN_PATH) -> None:
    """Write the seen-store to disk with indent=2 JSON, creating parent dirs.

    Args:
        seen:      dict mapping str(repo.id) -> {"first_seen": "YYYY-MM-DD"}
        seen_path: path to data/seen.json (injectable for tests).
    """
    seen_path.parent.mkdir(parents=True, exist_ok=True)
    seen_path.write_text(json.dumps(seen, indent=2))


def classify_and_update(
    seen: dict,
    reported_ids: list[str],
    report_date: str,
) -> tuple[dict, dict]:
    """Classify reported repo IDs as new or returning, and return an updated store.

    Reads the input `seen` dict but does NOT mutate it and does NOT write to disk.
    The caller must write `updated_seen` AFTER the report file is written (D-10),
    so a same-day retry re-reads the pre-write state and classifies correctly.

    Args:
        seen:         current seen-store (str repo id -> {"first_seen": "YYYY-MM-DD"})
        reported_ids: list of str(repo.id) values that appeared in rendered buckets
        report_date:  today's date as "YYYY-MM-DD" (used for first_seen on new repos)

    Returns:
        (markers, updated_seen) where:
          markers[rid]     == "new"       for repo ids not yet in seen
          markers[rid]     == "returning" for repo ids already in seen
          updated_seen     == copy of seen + new entries for each "new" rid
    """
    markers: dict[str, str] = {}
    updated: dict = dict(seen)  # shallow copy — do NOT mutate input (T-02-06)
    for rid in reported_ids:
        if rid in seen:
            markers[rid] = "returning"
        else:
            markers[rid] = "new"
            updated[rid] = {"first_seen": report_date}
    return markers, updated
