"""Pruning for GitHub Repo Tracker (HARD-04, HARD-04-EXT).

prune_snapshots() deletes per-date snapshot JSON files older than retention_days
to bound repository size growth. Uses filename-date comparison (not mtime — mtime
is unreliable in GitHub Actions due to checkout resetting all timestamps).

prune_metadata() bounds the tracked-id set in metadata.json (companion to
prune_snapshots, which bounds snapshot files). It evicts repos that have not
appeared in a ranked bucket for METADATA_TRACKED_RETENTION_DAYS, using a small
additive ledger file (data/tracked_ledger.json) to track each repo's last-active
date — see PLAN <why_a_separate_ledger> for why this can't live in seen.json or
metadata.json itself.

Both functions return their affected ids/paths for test assertions without mocking.
"""
import json
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path

from src.config import (
    METADATA_PATH,
    METADATA_TRACKED_RETENTION_DAYS,
    SNAPSHOT_RETENTION_DAYS,
    SNAPSHOTS_DIR,
    TRACKED_LEDGER_PATH,
)


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


def prune_metadata(
    now: datetime,
    reported_ids: list[str],
    *,
    metadata_path: Path = METADATA_PATH,
    ledger_path: Path = TRACKED_LEDGER_PATH,
    retention_days: int = METADATA_TRACKED_RETENTION_DAYS,
) -> list[str]:
    """Evict tracked repos absent from every ranked bucket for retention_days (HARD-04-EXT).

    Single-clock ledger design: a small additive file (ledger_path) tracks each
    tracked repo's last-active date. Any rid in reported_ids is stamped today and
    is never evicted this run (T-wif-02 grace). A repo new to metadata.json (not
    yet in the ledger) is granted a full retention_days grace window starting
    today. A repo absent from reported_ids whose ledger date is older than
    (now - retention_days) is evicted from metadata.json.

    Safe to call when metadata_path does not exist — returns [] without raising.
    Corrupt metadata.json or ledger JSON is treated as empty (warns, no raise) —
    this eviction pass intentionally degrades gracefully, unlike the primary
    load paths (store.load_metadata / seen.load_seen), which now abort the run
    on corruption to avoid silently wiping history (T-uec-01).

    Args:
        now:            Current UTC datetime (used to compute cutoff date + stamps).
        reported_ids:   Repo ids that appeared in a ranked bucket this run.
        metadata_path:  Injectable for tests (defaults to METADATA_PATH from config).
        ledger_path:    Injectable for tests (defaults to TRACKED_LEDGER_PATH from config).
        retention_days: Repos absent from reported_ids for longer than this are evicted.

    Returns:
        List of evicted str repo-ids (empty if nothing evicted).
    """
    if not metadata_path.exists():
        return []

    try:
        metadata = json.loads(metadata_path.read_text())
    except json.JSONDecodeError:
        warnings.warn(
            f"Corrupt metadata at {metadata_path}; treating as empty.",
            stacklevel=2,
        )
        return []

    repos = metadata.get("repos", {})

    ledger: dict = {}
    if ledger_path.exists():
        try:
            ledger = json.loads(ledger_path.read_text())
        except json.JSONDecodeError:
            warnings.warn(
                f"Corrupt tracked ledger at {ledger_path}; treating as empty.",
                stacklevel=2,
            )
            ledger = {}

    today = now.date().isoformat()

    # Any repo that appeared in a ranked bucket this run is refreshed to today
    # and is never evicted this run (T-wif-02 grace).
    for rid in reported_ids:
        ledger[str(rid)] = today

    # A repo new to metadata (not yet in the ledger) gets a fresh grace window.
    for rid in repos:
        if rid not in ledger:
            ledger[rid] = today

    cutoff = (now - timedelta(days=retention_days)).date()
    evicted: list[str] = []
    for rid in list(repos):
        raw_date = ledger.get(rid, today)
        try:
            ledger_date = date.fromisoformat(raw_date)
        except ValueError:
            warnings.warn(
                f"Malformed ledger date for repo {rid!r} ({raw_date!r}); treating as today (kept).",
                stacklevel=2,
            )
            ledger_date = date.fromisoformat(today)
        if ledger_date < cutoff:
            evicted.append(rid)

    if evicted:
        for rid in evicted:
            del repos[rid]
        metadata_path.write_text(json.dumps(metadata, indent=2))

    # Self-clean: ledger only tracks rids still present in metadata (no
    # unbounded ledger growth as repos come and go over time).
    ledger = {rid: d for rid, d in ledger.items() if rid in repos}
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=2))

    return evicted
