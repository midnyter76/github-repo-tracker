"""Velocity ranking engine for GitHub Repo Tracker.

Loads per-date snapshot files, joins with metadata, computes bucket-specific
hour-normalized velocity, and produces the four-bucket contract that Plan 03
(report rendering) consumes verbatim.

Public API:
    compute_buckets(snapshots_dir, metadata_path, now) -> dict
    creation_velocity(stars, created_at_iso, captured_at_iso) -> float
    is_new(created_at_iso, run_date, window_days) -> bool
    spike_velocity(snap_latest, snap_prev, rid) -> float | None
    rolling_velocity(snap_current, snap_oldest, rid) -> float | None
    load_snapshots(snapshots_dir) -> list[dict]
    select_30d_window(snapshots, run_date) -> tuple[dict, dict] | None

All functions are pure (no side effects outside warnings.warn) and take
injectable paths so they can be unit-tested without real file I/O.
"""

import json
import warnings
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src import config
from src.store import load_metadata


# ---------------------------------------------------------------------------
# Velocity Primitives
# ---------------------------------------------------------------------------

def creation_velocity(stars: int, created_at_iso: str, captured_at_iso: str) -> float:
    """Stars per day, normalized by actual elapsed hours since repo creation.

    Uses an age floor of config.AGE_HOURS_FLOOR (default 1.0h) to prevent
    divide-by-zero for repos captured in their first hour (Pitfall 2).

    Args:
        stars:           Current star count from the snapshot.
        created_at_iso:  ISO 8601 string of repo creation time (from metadata).
        captured_at_iso: ISO 8601 string of snapshot capture time.

    Returns:
        Stars per day (float).
    """
    created = datetime.fromisoformat(created_at_iso)
    captured = datetime.fromisoformat(captured_at_iso)
    age_hours = (captured - created).total_seconds() / 3600
    age_hours = max(age_hours, config.AGE_HOURS_FLOOR)  # floor: avoid div-by-zero
    return (stars / age_hours) * 24  # → stars/day


def is_new(created_at_iso: str, run_date: date, window_days: int) -> bool:
    """Return True iff the repo was created within window_days of run_date (inclusive).

    Boundary is inclusive: a repo created exactly window_days ago qualifies.
    This matches the RANK-01/02 requirement and Pitfall 5 off-by-one guard.

    Args:
        created_at_iso: ISO 8601 string of repo creation time (from metadata).
        run_date:       The date on which ranking is being computed.
        window_days:    The creation window in days (7 for weekly, 30 for monthly).

    Returns:
        True if (run_date - created.date()).days <= window_days.
    """
    created = datetime.fromisoformat(created_at_iso).date()
    return (run_date - created).days <= window_days


def spike_velocity(snap_latest: dict, snap_prev: dict, rid: str) -> float | None:
    """Stars per hour between the two most recent snapshots.

    Returns None if the repo ID is absent from either snapshot — the caller
    must handle None before using the result (Pitfall 4 inner-join).
    Elapsed time is floored at 0.1h to guard against identical captured_at values.

    Args:
        snap_latest: The most recent snapshot dict (has "repos", "captured_at").
        snap_prev:   The prior snapshot dict.
        rid:         Numeric repo ID as string key.

    Returns:
        Stars per hour (float), or None if rid is missing from either snapshot.
    """
    if rid not in snap_latest["repos"] or rid not in snap_prev["repos"]:
        return None
    delta = snap_latest["repos"][rid]["stars"] - snap_prev["repos"][rid]["stars"]
    t_latest = datetime.fromisoformat(snap_latest["captured_at"])
    t_prev = datetime.fromisoformat(snap_prev["captured_at"])
    elapsed_hours = (t_latest - t_prev).total_seconds() / 3600
    elapsed_hours = max(elapsed_hours, 0.1)  # guard against identical captured_at
    return delta / elapsed_hours  # → stars/hour


def rolling_velocity(snap_current: dict, snap_oldest: dict, rid: str) -> float | None:
    """Stars per hour over the widest available window up to 30 days.

    Returns None if the repo ID is absent from either snapshot.
    Elapsed time is floored at 0.1h.

    Args:
        snap_current: The most recent snapshot dict.
        snap_oldest:  The oldest snapshot in the 30-day window.
        rid:          Numeric repo ID as string key.

    Returns:
        Stars per hour (float), or None if rid is missing from either snapshot.
    """
    if rid not in snap_current["repos"] or rid not in snap_oldest["repos"]:
        return None
    delta = snap_current["repos"][rid]["stars"] - snap_oldest["repos"][rid]["stars"]
    t_current = datetime.fromisoformat(snap_current["captured_at"])
    t_oldest = datetime.fromisoformat(snap_oldest["captured_at"])
    elapsed_hours = (t_current - t_oldest).total_seconds() / 3600
    elapsed_hours = max(elapsed_hours, 0.1)
    return delta / elapsed_hours  # → stars/hour


# ---------------------------------------------------------------------------
# Snapshot Loading
# ---------------------------------------------------------------------------

def load_snapshots(snapshots_dir: Path) -> list[dict]:
    """Load all valid per-date snapshot files, sorted ascending by filename date.

    ISO-format filenames (YYYY-MM-DD.json) sort lexicographically = chronologically.
    Skips .gitkeep (glob excludes non-.json). Skips files with invalid JSON or
    missing required keys ("captured_at", "repos", "date"), issuing warnings.warn
    per file (mirrors store.py corrupt-file guard, Pitfall T-02-02).

    Args:
        snapshots_dir: Directory containing per-date snapshot JSON files.

    Returns:
        List of snapshot dicts sorted oldest-first.
    """
    files = sorted(snapshots_dir.glob("*.json"))
    snapshots = []
    for f in files:
        try:
            snap = json.loads(f.read_text())
        except json.JSONDecodeError:
            warnings.warn(
                f"Corrupt snapshot {f}; skipping for velocity computation.",
                stacklevel=2,
            )
            continue
        if "captured_at" in snap and "repos" in snap and "date" in snap:
            snapshots.append(snap)
    return snapshots


# ---------------------------------------------------------------------------
# Window Selection
# ---------------------------------------------------------------------------

def select_30d_window(snapshots: list[dict], run_date: date) -> tuple[dict, dict] | None:
    """Return (oldest_in_window, current) or None if <2 snapshots in the 30d window.

    Window is inclusive: a snapshot exactly 30 days old qualifies (>= cutoff).
    "Current" is the last snapshot in the list (already sorted ascending).

    Args:
        snapshots: List of snapshot dicts sorted ascending by date.
        run_date:  The date on which ranking is computed.

    Returns:
        (oldest_in_window, current) tuple, or None if fewer than 2 qualify.
    """
    cutoff = run_date - timedelta(days=config.VELOCITY_30D_WINDOW_DAYS)
    in_window = [
        s for s in snapshots
        if date.fromisoformat(s["date"]) >= cutoff
    ]
    if len(in_window) < 2:
        return None
    return in_window[0], in_window[-1]  # oldest, newest (list is sorted ascending)


# ---------------------------------------------------------------------------
# Entry Builder
# ---------------------------------------------------------------------------

def _build_entry(rid: str, stars: int, velocity_per_day: float, meta_repos: dict) -> dict:
    """Build a uniform entry dict from snapshot + metadata. meta_repos[rid] must exist."""
    m = meta_repos[rid]
    return {
        "id": rid,
        "full_name": m["full_name"],
        "html_url": m["html_url"],
        "description": m.get("description", ""),
        "created_at": m["created_at"],
        "stars": stars,
        "velocity_per_day": velocity_per_day,
    }


def _sort_entries(entries: list[dict]) -> list[dict]:
    """Sort entries by velocity_per_day DESC, stars DESC, full_name ASC (tie-break)."""
    return sorted(
        entries,
        key=lambda e: (-e["velocity_per_day"], -e["stars"], e["full_name"]),
    )


# ---------------------------------------------------------------------------
# compute_buckets — main entry point
# ---------------------------------------------------------------------------

def compute_buckets(
    snapshots_dir: Path = config.SNAPSHOTS_DIR,
    metadata_path: Path = config.METADATA_PATH,
    now: datetime = None,
) -> dict:
    """Load snapshots + metadata and produce the four-bucket ranking structure.

    Bucket contract (Plan 03 renders this exact shape):
    {
      "brand_new_weekly":  {"active": True,  "snapshots_available": N, "window_target": 7,  "entries": [...]},
      "brand_new_monthly": {"active": True,  "snapshots_available": N, "window_target": 30, "entries": [...]},
      "spike_24h":         {"active": bool,  "snapshots_available": N, "window_target": 2,  "entries": [...]},
      "velocity_30d":      {"active": bool,  "snapshots_available": N, "window_target": 30, "entries": [...]},
    }

    Each entry carries: id, full_name, html_url, description, created_at, stars,
    velocity_per_day.

    Graceful degradation (RANK-06 / D-06 / D-07):
    - Breakthrough buckets require >= SPIKE_MIN_SNAPSHOTS (2) snapshots to activate.
    - spike_24h additionally requires the two most recent snapshots to be within
      STALE_SPIKE_HOURS of each other (Pitfall 7).
    - When inactive: active=False, entries=[], snapshots_available=len(snaps).

    Args:
        snapshots_dir:  Path to directory of per-date snapshot JSON files.
        metadata_path:  Path to metadata.json written by store.write_metadata.
        now:            UTC datetime for run_date. Defaults to datetime.now(UTC).

    Returns:
        Dict with four fixed keys as above.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    run_date = now.date()
    meta = load_metadata(metadata_path)
    meta_repos = meta.get("repos", {})

    snaps = load_snapshots(snapshots_dir)
    n_snaps = len(snaps)
    current = snaps[-1] if snaps else None

    # -----------------------------------------------------------------------
    # Brand New Weekly (RANK-01) and Brand New Monthly (RANK-02)
    # Both use creation velocity; active=True always; overlap is ALLOWED (Q1).
    # -----------------------------------------------------------------------
    weekly_entries: list[dict] = []
    monthly_entries: list[dict] = []

    if current is not None:
        for rid, snap_data in current["repos"].items():
            if rid not in meta_repos:
                continue  # Pitfall 4: inner-join; skip if metadata absent

            created_at = meta_repos[rid]["created_at"]
            stars = snap_data["stars"]
            vel = creation_velocity(stars, created_at, current["captured_at"])

            if is_new(created_at, run_date, config.BRAND_NEW_WEEKLY_DAYS):
                weekly_entries.append(_build_entry(rid, stars, vel, meta_repos))

            if is_new(created_at, run_date, config.BRAND_NEW_MONTHLY_DAYS):
                monthly_entries.append(_build_entry(rid, stars, vel, meta_repos))

    weekly_entries = _sort_entries(weekly_entries)[: config.BRAND_NEW_WEEKLY_TOP]
    monthly_entries = _sort_entries(monthly_entries)[: config.BRAND_NEW_MONTHLY_TOP]

    # -----------------------------------------------------------------------
    # Breakthrough: 24h Spike (RANK-03)
    # -----------------------------------------------------------------------
    spike_active = False
    spike_entries: list[dict] = []

    if n_snaps >= config.SPIKE_MIN_SNAPSHOTS:
        snap_latest = snaps[-1]
        snap_prev = snaps[-2]
        t_latest = datetime.fromisoformat(snap_latest["captured_at"])
        t_prev = datetime.fromisoformat(snap_prev["captured_at"])
        elapsed_hours = (t_latest - t_prev).total_seconds() / 3600

        if elapsed_hours <= config.STALE_SPIKE_HOURS:  # Pitfall 7: staleness guard
            spike_active = True
            for rid in snap_latest["repos"]:
                if rid not in meta_repos:
                    continue  # Pitfall 4
                per_hour = spike_velocity(snap_latest, snap_prev, rid)
                if per_hour is None:
                    continue
                # Pitfall 3: exclude negative deltas (star losses)
                stars_latest = snap_latest["repos"][rid]["stars"]
                stars_prev = snap_prev["repos"].get(rid, {}).get("stars", stars_latest)
                if stars_latest - stars_prev < 0:
                    continue
                velocity_per_day = per_hour * 24
                spike_entries.append(
                    _build_entry(rid, stars_latest, velocity_per_day, meta_repos)
                )
            spike_entries = _sort_entries(spike_entries)[: config.SPIKE_TOP]

    # -----------------------------------------------------------------------
    # Breakthrough: 30-Day Velocity (RANK-04)
    # -----------------------------------------------------------------------
    v30d_active = False
    v30d_entries: list[dict] = []

    window = select_30d_window(snaps, run_date)
    if window is not None:
        snap_oldest, snap_newest = window
        v30d_active = True
        for rid in snap_newest["repos"]:
            if rid not in meta_repos:
                continue  # Pitfall 4
            per_hour = rolling_velocity(snap_newest, snap_oldest, rid)
            if per_hour is None:
                continue
            # Pitfall 3: exclude negative deltas
            stars_now = snap_newest["repos"][rid]["stars"]
            stars_old = snap_oldest["repos"].get(rid, {}).get("stars", stars_now)
            if stars_now - stars_old < 0:
                continue
            velocity_per_day = per_hour * 24
            v30d_entries.append(
                _build_entry(rid, stars_now, velocity_per_day, meta_repos)
            )
        v30d_entries = _sort_entries(v30d_entries)[: config.VELOCITY_30D_TOP]

    # -----------------------------------------------------------------------
    # Assemble and return the four-bucket contract
    # -----------------------------------------------------------------------
    return {
        "brand_new_weekly": {
            "active": True,
            "snapshots_available": n_snaps,
            "window_target": config.BRAND_NEW_WEEKLY_DAYS,
            "entries": weekly_entries,
        },
        "brand_new_monthly": {
            "active": True,
            "snapshots_available": n_snaps,
            "window_target": config.BRAND_NEW_MONTHLY_DAYS,
            "entries": monthly_entries,
        },
        "spike_24h": {
            "active": spike_active,
            "snapshots_available": n_snaps,
            "window_target": config.SPIKE_MIN_SNAPSHOTS,
            "entries": spike_entries,
        },
        "velocity_30d": {
            "active": v30d_active,
            "snapshots_available": n_snaps,
            "window_target": config.VELOCITY_30D_WINDOW_DAYS,
            "entries": v30d_entries,
        },
    }
