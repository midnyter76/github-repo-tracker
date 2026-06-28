"""Tests for src/rank.py — velocity ranking engine.

Covers:
- creation_velocity: stars/day with age-floor guard (Pitfall 2)
- is_new: inclusive boundary at window_days (Pitfall 5)
- spike_velocity / rolling_velocity: per-hour math, None on missing rid, elapsed floor
- load_snapshots: sorting, skipping .gitkeep, corrupt-file warning
- select_30d_window: inclusive cutoff, None when <2 snapshots in window
- compute_buckets: cold-start (1 snapshot), 2-snapshot activation, staleness guard,
  negative-delta exclusion, missing-metadata exclusion, sorting+cap

All tests inject tmp_path so no reads ever hit the real data/ directory.
Datetimes are always tz-aware UTC (mirrors test_store.py convention).
"""

import json
import warnings
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc(year=2026, month=6, day=28, hour=12) -> datetime:
    """Return a tz-aware UTC datetime."""
    return datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)


def _iso(year=2026, month=6, day=28, hour=12) -> str:
    """Return a tz-aware UTC ISO 8601 string."""
    return _utc(year, month, day, hour).isoformat()


def _write_snapshot(
    tmp_path: Path,
    date_str: str,
    captured_at: str,
    repos: dict,
) -> Path:
    """Write a minimal snapshot file to tmp_path and return its Path."""
    snap = {"date": date_str, "captured_at": captured_at, "repos": repos}
    p = tmp_path / f"{date_str}.json"
    p.write_text(json.dumps(snap))
    return p


def _write_metadata(tmp_path: Path, repos: dict) -> Path:
    """Write a metadata file with the given repos dict."""
    meta = {"updated_at": _iso(), "repos": repos}
    p = tmp_path / "metadata.json"
    p.write_text(json.dumps(meta))
    return p


def _meta_entry(
    full_name: str = "owner/repo",
    description: str = "A repo",
    created_at: str | None = None,
    html_url: str | None = None,
) -> dict:
    if created_at is None:
        created_at = _iso(month=6, day=1)  # 27 days before June 28
    if html_url is None:
        html_url = f"https://github.com/{full_name}"
    return {
        "full_name": full_name,
        "description": description,
        "created_at": created_at,
        "html_url": html_url,
    }


# ---------------------------------------------------------------------------
# TestCreationVelocity
# ---------------------------------------------------------------------------

class TestCreationVelocity:
    def test_basic_velocity_stars_per_day(self):
        """creation_velocity returns stars/day correctly."""
        from src.rank import creation_velocity

        # 240 stars over 10 hours → 240/10 * 24 = 576 stars/day
        created = _iso(hour=0)
        captured = _iso(hour=10)
        result = creation_velocity(240, created, captured)
        assert abs(result - 576.0) < 0.01

    def test_age_floor_prevents_div_by_zero(self):
        """Same-hour repo (age < 1h) is floored at 1h, not zero (Pitfall 2)."""
        from src.rank import creation_velocity
        from src import config

        # Created 12:58, captured 13:00 — 2 minutes elapsed
        created = _iso(hour=12)  # 12:00
        # simulate 2-minute gap: use manually-formed strings
        created_str = "2026-06-28T12:58:00+00:00"
        captured_str = "2026-06-28T13:00:00+00:00"
        result = creation_velocity(100, created_str, captured_str)
        # With 1h floor: 100 / 1.0 * 24 = 2400 stars/day
        expected = (100 / config.AGE_HOURS_FLOOR) * 24
        assert abs(result - expected) < 0.01, f"Expected {expected}, got {result}"

    def test_zero_stars_returns_zero(self):
        """creation_velocity with 0 stars returns 0 regardless of age."""
        from src.rank import creation_velocity

        # 48-hour-old repo: created 2 days ago, captured today
        result = creation_velocity(0, _iso(day=26, hour=12), _iso(day=28, hour=12))
        assert result == 0.0

    def test_24h_age_equals_star_count(self):
        """creation_velocity for a 24h-old repo equals star count directly."""
        from src.rank import creation_velocity

        # 24 hours → age_hours=24; velocity = stars/24*24 = stars
        stars = 500
        created = "2026-06-27T12:00:00+00:00"
        captured = "2026-06-28T12:00:00+00:00"
        result = creation_velocity(stars, created, captured)
        assert abs(result - stars) < 0.01


# ---------------------------------------------------------------------------
# TestIsNew
# ---------------------------------------------------------------------------

class TestIsNew:
    def test_exactly_window_days_is_included(self):
        """Repo created exactly window_days ago is 'new' (inclusive boundary, Pitfall 5)."""
        from src.rank import is_new

        run_date = date(2026, 6, 28)
        created_at = "2026-06-21T00:00:00+00:00"  # 7 days ago
        assert is_new(created_at, run_date, window_days=7) is True

    def test_window_days_plus_one_is_excluded(self):
        """Repo created window_days+1 ago is not 'new'."""
        from src.rank import is_new

        run_date = date(2026, 6, 28)
        created_at = "2026-06-20T00:00:00+00:00"  # 8 days ago
        assert is_new(created_at, run_date, window_days=7) is False

    def test_today_created_is_new(self):
        """Repo created today (0 days ago) is always 'new'."""
        from src.rank import is_new

        run_date = date(2026, 6, 28)
        created_at = "2026-06-28T06:00:00+00:00"
        assert is_new(created_at, run_date, window_days=7) is True


# ---------------------------------------------------------------------------
# TestSpikeVelocity
# ---------------------------------------------------------------------------

class TestSpikeVelocity:
    def test_returns_stars_per_hour(self):
        """spike_velocity returns (delta_stars / elapsed_hours) correctly."""
        from src.rank import spike_velocity

        snap_prev = {"captured_at": "2026-06-27T12:00:00+00:00", "repos": {"1": {"stars": 100}}}
        snap_latest = {"captured_at": "2026-06-28T12:00:00+00:00", "repos": {"1": {"stars": 340}}}
        # delta = 240 stars / 24h = 10 stars/hr
        result = spike_velocity(snap_latest, snap_prev, "1")
        assert abs(result - 10.0) < 0.01

    def test_returns_none_when_rid_missing_in_latest(self):
        """Returns None if rid is absent from the latest snapshot."""
        from src.rank import spike_velocity

        snap_prev = {"captured_at": _iso(day=27), "repos": {"1": {"stars": 100}}}
        snap_latest = {"captured_at": _iso(day=28), "repos": {}}  # rid absent
        assert spike_velocity(snap_latest, snap_prev, "1") is None

    def test_returns_none_when_rid_missing_in_prev(self):
        """Returns None if rid is absent from the previous snapshot."""
        from src.rank import spike_velocity

        snap_prev = {"captured_at": _iso(day=27), "repos": {}}
        snap_latest = {"captured_at": _iso(day=28), "repos": {"1": {"stars": 100}}}
        assert spike_velocity(snap_latest, snap_prev, "1") is None

    def test_elapsed_floor_protects_against_zero(self):
        """Identical captured_at values use the 0.1h elapsed floor, not zero."""
        from src.rank import spike_velocity

        same_ts = _iso()
        snap = {"captured_at": same_ts, "repos": {"1": {"stars": 50}}}
        snap_earlier = {"captured_at": same_ts, "repos": {"1": {"stars": 10}}}
        result = spike_velocity(snap, snap_earlier, "1")
        # delta=40, elapsed=0.1h → 400 stars/hr
        assert result is not None
        assert abs(result - 400.0) < 0.01


# ---------------------------------------------------------------------------
# TestRollingVelocity
# ---------------------------------------------------------------------------

class TestRollingVelocity:
    def test_returns_stars_per_hour(self):
        """rolling_velocity returns (delta / elapsed_hours) correctly."""
        from src.rank import rolling_velocity

        snap_oldest = {"captured_at": "2026-05-29T12:00:00+00:00", "repos": {"1": {"stars": 500}}}
        snap_current = {"captured_at": "2026-06-28T12:00:00+00:00", "repos": {"1": {"stars": 1700}}}
        # delta = 1200 stars / (30d * 24h) = 1200/720 = 1.667 stars/hr
        result = rolling_velocity(snap_current, snap_oldest, "1")
        assert result is not None
        assert abs(result - (1200 / 720)) < 0.01

    def test_returns_none_when_rid_missing(self):
        """Returns None if rid absent in either snapshot."""
        from src.rank import rolling_velocity

        snap_old = {"captured_at": _iso(day=1), "repos": {}}
        snap_cur = {"captured_at": _iso(day=28), "repos": {"1": {"stars": 100}}}
        assert rolling_velocity(snap_cur, snap_old, "1") is None


# ---------------------------------------------------------------------------
# TestLoadSnapshots
# ---------------------------------------------------------------------------

class TestLoadSnapshots:
    def test_sorts_ascending_by_filename(self, tmp_path: Path):
        """load_snapshots returns snapshots sorted ascending by date filename."""
        from src.rank import load_snapshots

        _write_snapshot(tmp_path, "2026-06-28", _iso(day=28), {"1": {"stars": 200}})
        _write_snapshot(tmp_path, "2026-06-26", _iso(day=26), {"1": {"stars": 100}})
        _write_snapshot(tmp_path, "2026-06-27", _iso(day=27), {"1": {"stars": 150}})

        snaps = load_snapshots(tmp_path)
        assert [s["date"] for s in snaps] == ["2026-06-26", "2026-06-27", "2026-06-28"]

    def test_skips_gitkeep_file(self, tmp_path: Path):
        """load_snapshots ignores .gitkeep (glob '*.json' excludes it)."""
        from src.rank import load_snapshots

        (tmp_path / ".gitkeep").write_text("")
        _write_snapshot(tmp_path, "2026-06-28", _iso(), {"1": {"stars": 100}})

        snaps = load_snapshots(tmp_path)
        assert len(snaps) == 1

    def test_skips_corrupt_json_and_warns(self, tmp_path: Path):
        """load_snapshots warns and skips files with invalid JSON."""
        from src.rank import load_snapshots

        (tmp_path / "2026-06-27.json").write_text("{not valid json")
        _write_snapshot(tmp_path, "2026-06-28", _iso(), {"1": {"stars": 100}})

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            snaps = load_snapshots(tmp_path)

        assert len(snaps) == 1
        assert snaps[0]["date"] == "2026-06-28"
        assert any("2026-06-27" in str(warning.message) for warning in w)

    def test_skips_json_without_required_keys(self, tmp_path: Path):
        """load_snapshots skips JSON files missing 'captured_at', 'repos', or 'date'."""
        from src.rank import load_snapshots

        (tmp_path / "2026-06-27.json").write_text('{"only_key": "no required fields"}')
        _write_snapshot(tmp_path, "2026-06-28", _iso(), {"1": {"stars": 100}})

        snaps = load_snapshots(tmp_path)
        assert len(snaps) == 1

    def test_empty_dir_returns_empty_list(self, tmp_path: Path):
        """load_snapshots on an empty directory returns []."""
        from src.rank import load_snapshots

        assert load_snapshots(tmp_path) == []


# ---------------------------------------------------------------------------
# TestSelect30dWindow
# ---------------------------------------------------------------------------

class TestSelect30dWindow:
    def test_returns_oldest_and_newest_in_window(self):
        """select_30d_window returns (oldest_in_window, current) tuple."""
        from src.rank import select_30d_window

        run_date = date(2026, 6, 28)
        snaps = [
            {"date": "2026-05-29", "captured_at": _iso(month=5, day=29), "repos": {}},  # exactly 30d
            {"date": "2026-06-14", "captured_at": _iso(month=6, day=14), "repos": {}},
            {"date": "2026-06-28", "captured_at": _iso(month=6, day=28), "repos": {}},
        ]
        result = select_30d_window(snaps, run_date)
        assert result is not None
        oldest, newest = result
        assert oldest["date"] == "2026-05-29"
        assert newest["date"] == "2026-06-28"

    def test_returns_none_when_less_than_2_in_window(self):
        """select_30d_window returns None when fewer than 2 snapshots are in window."""
        from src.rank import select_30d_window

        run_date = date(2026, 6, 28)
        # Only today's snapshot within the 30d window
        snaps = [
            {"date": "2026-05-20", "captured_at": _iso(month=5, day=20), "repos": {}},  # 39d ago, outside
            {"date": "2026-06-28", "captured_at": _iso(month=6, day=28), "repos": {}},  # today
        ]
        result = select_30d_window(snaps, run_date)
        assert result is None

    def test_inclusive_cutoff_exactly_30d_old(self):
        """Snapshot exactly 30 days old is included (>= cutoff, Pitfall 5)."""
        from src.rank import select_30d_window

        run_date = date(2026, 6, 28)
        snaps = [
            {"date": "2026-05-29", "captured_at": _iso(month=5, day=29), "repos": {}},  # exactly 30d
            {"date": "2026-06-28", "captured_at": _iso(month=6, day=28), "repos": {}},
        ]
        result = select_30d_window(snaps, run_date)
        assert result is not None


# ---------------------------------------------------------------------------
# TestComputeBuckets — cold-start, activation, guards
# ---------------------------------------------------------------------------

class TestComputeBucketsOnSnapshot:
    """Cold-start: compute_buckets with exactly 1 snapshot."""

    def _make_dirs(self, tmp_path: Path) -> tuple[Path, Path]:
        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()
        meta_path = tmp_path / "metadata.json"
        return snaps_dir, meta_path

    def test_new_repo_buckets_populated_from_single_snapshot(self, tmp_path: Path):
        """With 1 snapshot, brand_new_weekly and brand_new_monthly return entries."""
        from src.rank import compute_buckets

        snaps_dir, meta_path = self._make_dirs(tmp_path)
        now = _utc(month=6, day=28)
        # Repo created 3 days ago — qualifies for both weekly and monthly
        created = "2026-06-25T12:00:00+00:00"
        _write_snapshot(snaps_dir, "2026-06-28", now.isoformat(), {"1": {"stars": 100}})
        meta_path.write_text(json.dumps({
            "updated_at": now.isoformat(),
            "repos": {"1": _meta_entry("owner/repo", created_at=created)},
        }))

        buckets = compute_buckets(snaps_dir, meta_path, now)
        assert buckets["brand_new_weekly"]["active"] is True
        assert len(buckets["brand_new_weekly"]["entries"]) == 1
        assert buckets["brand_new_monthly"]["active"] is True
        assert len(buckets["brand_new_monthly"]["entries"]) == 1

    def test_spike_24h_inactive_with_one_snapshot(self, tmp_path: Path):
        """With 1 snapshot spike_24h.active is False and snapshots_available == 1."""
        from src.rank import compute_buckets

        snaps_dir, meta_path = self._make_dirs(tmp_path)
        now = _utc()
        _write_snapshot(snaps_dir, "2026-06-28", now.isoformat(), {"1": {"stars": 100}})
        meta_path.write_text(json.dumps({
            "updated_at": now.isoformat(),
            "repos": {"1": _meta_entry(created_at=_iso(month=6, day=1))},
        }))

        buckets = compute_buckets(snaps_dir, meta_path, now)
        assert buckets["spike_24h"]["active"] is False
        assert buckets["spike_24h"]["entries"] == []
        assert buckets["spike_24h"]["snapshots_available"] == 1

    def test_velocity_30d_inactive_with_one_snapshot(self, tmp_path: Path):
        """With 1 snapshot velocity_30d.active is False."""
        from src.rank import compute_buckets

        snaps_dir, meta_path = self._make_dirs(tmp_path)
        now = _utc()
        _write_snapshot(snaps_dir, "2026-06-28", now.isoformat(), {"1": {"stars": 100}})
        meta_path.write_text(json.dumps({
            "updated_at": now.isoformat(),
            "repos": {"1": _meta_entry(created_at=_iso(month=6, day=1))},
        }))

        buckets = compute_buckets(snaps_dir, meta_path, now)
        assert buckets["velocity_30d"]["active"] is False
        assert buckets["velocity_30d"]["entries"] == []


class TestComputeBucketsTwoSnapshots:
    """2 valid snapshots — breakthrough buckets activate."""

    def _setup(self, tmp_path: Path, gap_hours: int = 24) -> tuple[Path, Path, datetime]:
        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()
        meta_path = tmp_path / "metadata.json"
        now = _utc(month=6, day=28, hour=12)

        prev_at = (now - timedelta(hours=gap_hours)).isoformat()
        _write_snapshot(snaps_dir, "2026-06-27", prev_at, {"1": {"stars": 100}})
        _write_snapshot(snaps_dir, "2026-06-28", now.isoformat(), {"1": {"stars": 340}})
        meta_path.write_text(json.dumps({
            "updated_at": now.isoformat(),
            "repos": {"1": _meta_entry(created_at="2026-01-01T00:00:00+00:00")},  # old repo
        }))
        return snaps_dir, meta_path, now

    def test_spike_24h_active_with_two_snapshots(self, tmp_path: Path):
        """With 2 snapshots within STALE_SPIKE_HOURS, spike_24h.active is True."""
        from src.rank import compute_buckets

        snaps_dir, meta_path, now = self._setup(tmp_path, gap_hours=24)
        buckets = compute_buckets(snaps_dir, meta_path, now)
        assert buckets["spike_24h"]["active"] is True
        assert len(buckets["spike_24h"]["entries"]) == 1

    def test_velocity_30d_active_with_two_snapshots(self, tmp_path: Path):
        """With 2 snapshots in the 30d window, velocity_30d.active is True."""
        from src.rank import compute_buckets

        snaps_dir, meta_path, now = self._setup(tmp_path, gap_hours=24)
        buckets = compute_buckets(snaps_dir, meta_path, now)
        assert buckets["velocity_30d"]["active"] is True
        assert len(buckets["velocity_30d"]["entries"]) == 1

    def test_velocity_per_day_equals_per_hour_times_24(self, tmp_path: Path):
        """velocity_per_day in spike_24h entries == per_hour * 24."""
        from src.rank import compute_buckets, spike_velocity

        snaps_dir, meta_path, now = self._setup(tmp_path, gap_hours=24)
        buckets = compute_buckets(snaps_dir, meta_path, now)
        assert buckets["spike_24h"]["active"] is True
        entry = buckets["spike_24h"]["entries"][0]
        # Manual calculation: 240 stars / 24h = 10 stars/hr; *24 = 240/day
        assert abs(entry["velocity_per_day"] - 240.0) < 0.5

    def test_snapshots_available_set_on_all_buckets(self, tmp_path: Path):
        """snapshots_available is set to len(snaps) on all four buckets."""
        from src.rank import compute_buckets

        snaps_dir, meta_path, now = self._setup(tmp_path, gap_hours=24)
        buckets = compute_buckets(snaps_dir, meta_path, now)
        for key in ("brand_new_weekly", "brand_new_monthly", "spike_24h", "velocity_30d"):
            assert buckets[key]["snapshots_available"] == 2, f"{key} snapshots_available wrong"


class TestComputeBucketsGuards:
    """Edge-case guards: staleness, negative-delta, missing-metadata."""

    def test_stale_prior_snapshot_deactivates_spike(self, tmp_path: Path):
        """Snapshots > STALE_SPIKE_HOURS apart -> spike_24h.active False (Pitfall 7)."""
        from src.rank import compute_buckets

        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()
        meta_path = tmp_path / "metadata.json"
        now = _utc(month=6, day=28, hour=12)

        # Gap = 40 hours > STALE_SPIKE_HOURS (30h)
        prev_at = (now - timedelta(hours=40)).isoformat()
        _write_snapshot(snaps_dir, "2026-06-26", prev_at, {"1": {"stars": 100}})
        _write_snapshot(snaps_dir, "2026-06-28", now.isoformat(), {"1": {"stars": 500}})
        meta_path.write_text(json.dumps({
            "updated_at": now.isoformat(),
            "repos": {"1": _meta_entry(created_at="2026-01-01T00:00:00+00:00")},
        }))

        buckets = compute_buckets(snaps_dir, meta_path, now)
        assert buckets["spike_24h"]["active"] is False, (
            "spike_24h should be inactive when snapshot gap exceeds STALE_SPIKE_HOURS"
        )

    def test_negative_delta_excluded_from_spike(self, tmp_path: Path):
        """Repo that lost stars is excluded from spike_24h entries (Pitfall 3)."""
        from src.rank import compute_buckets

        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()
        meta_path = tmp_path / "metadata.json"
        now = _utc(month=6, day=28, hour=12)

        prev_at = (now - timedelta(hours=24)).isoformat()
        # Stars decreased: 500 -> 300
        _write_snapshot(snaps_dir, "2026-06-27", prev_at, {"1": {"stars": 500}})
        _write_snapshot(snaps_dir, "2026-06-28", now.isoformat(), {"1": {"stars": 300}})
        meta_path.write_text(json.dumps({
            "updated_at": now.isoformat(),
            "repos": {"1": _meta_entry(created_at="2026-01-01T00:00:00+00:00")},
        }))

        buckets = compute_buckets(snaps_dir, meta_path, now)
        assert buckets["spike_24h"]["active"] is True
        # Repo with negative delta must be excluded
        assert len(buckets["spike_24h"]["entries"]) == 0

    def test_missing_metadata_excluded_no_keyerror(self, tmp_path: Path):
        """Rid in snapshot but absent from metadata is excluded, no KeyError (Pitfall 4)."""
        from src.rank import compute_buckets

        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()
        meta_path = tmp_path / "metadata.json"
        now = _utc()

        # Snapshot has repo "1" but metadata has no repos
        _write_snapshot(snaps_dir, "2026-06-28", now.isoformat(), {"1": {"stars": 100}})
        meta_path.write_text(json.dumps({"updated_at": now.isoformat(), "repos": {}}))

        # Must not raise KeyError
        buckets = compute_buckets(snaps_dir, meta_path, now)
        assert buckets["brand_new_weekly"]["entries"] == []
        assert buckets["brand_new_monthly"]["entries"] == []


class TestComputeBucketsSortingAndCap:
    """Sorting by velocity_per_day DESC, stars DESC; cap enforced."""

    def test_top_n_cap_respected(self, tmp_path: Path):
        """When more repos qualify than cap, only top-N returned."""
        from src.rank import compute_buckets
        from src import config

        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()
        meta_path = tmp_path / "metadata.json"
        now = _utc(month=6, day=28)

        # Create 12 repos all created in last 3 days (qualify for weekly cap=10)
        repos_snap = {str(i): {"stars": i * 10} for i in range(1, 13)}
        repos_meta = {
            str(i): _meta_entry(
                full_name=f"owner/repo{i:02d}",
                created_at="2026-06-25T00:00:00+00:00",
            )
            for i in range(1, 13)
        }
        _write_snapshot(snaps_dir, "2026-06-28", now.isoformat(), repos_snap)
        meta_path.write_text(json.dumps({"updated_at": now.isoformat(), "repos": repos_meta}))

        buckets = compute_buckets(snaps_dir, meta_path, now)
        assert len(buckets["brand_new_weekly"]["entries"]) == config.BRAND_NEW_WEEKLY_TOP

    def test_sorted_by_velocity_desc(self, tmp_path: Path):
        """Entries sorted by velocity_per_day DESC — higher velocity first."""
        from src.rank import compute_buckets

        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()
        meta_path = tmp_path / "metadata.json"
        now = _utc(month=6, day=28, hour=12)

        # Two repos created at the same time; repo "2" has more stars = higher velocity
        created = "2026-06-27T12:00:00+00:00"  # 24h old
        repos_snap = {"1": {"stars": 100}, "2": {"stars": 500}}
        repos_meta = {
            "1": _meta_entry("owner/repo1", created_at=created),
            "2": _meta_entry("owner/repo2", created_at=created),
        }
        _write_snapshot(snaps_dir, "2026-06-28", now.isoformat(), repos_snap)
        meta_path.write_text(json.dumps({"updated_at": now.isoformat(), "repos": repos_meta}))

        buckets = compute_buckets(snaps_dir, meta_path, now)
        entries = buckets["brand_new_weekly"]["entries"]
        assert len(entries) == 2
        assert entries[0]["id"] == "2"  # Higher stars / velocity first
        assert entries[1]["id"] == "1"

    def test_entry_shape_has_all_required_fields(self, tmp_path: Path):
        """Each entry dict carries id, full_name, html_url, description, created_at, stars, velocity_per_day."""
        from src.rank import compute_buckets

        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()
        meta_path = tmp_path / "metadata.json"
        now = _utc()

        _write_snapshot(snaps_dir, "2026-06-28", now.isoformat(), {"42": {"stars": 200}})
        meta_path.write_text(json.dumps({
            "updated_at": now.isoformat(),
            "repos": {"42": _meta_entry(
                full_name="owner/nice-repo",
                description="An AI tool",
                created_at="2026-06-25T00:00:00+00:00",
                html_url="https://github.com/owner/nice-repo",
            )},
        }))

        buckets = compute_buckets(snaps_dir, meta_path, now)
        assert len(buckets["brand_new_weekly"]["entries"]) == 1
        entry = buckets["brand_new_weekly"]["entries"][0]
        for field in ("id", "full_name", "html_url", "description", "created_at", "stars", "velocity_per_day"):
            assert field in entry, f"Missing field: {field}"
        assert entry["id"] == "42"
        assert entry["full_name"] == "owner/nice-repo"
        assert entry["stars"] == 200

    def test_window_target_set_on_inactive_bucket(self, tmp_path: Path):
        """Inactive spike_24h has window_target == 2 (the minimum to activate)."""
        from src.rank import compute_buckets

        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()
        meta_path = tmp_path / "metadata.json"
        now = _utc()

        _write_snapshot(snaps_dir, "2026-06-28", now.isoformat(), {"1": {"stars": 50}})
        meta_path.write_text(json.dumps({
            "updated_at": now.isoformat(),
            "repos": {"1": _meta_entry(created_at=_iso(month=6, day=1))},
        }))

        buckets = compute_buckets(snaps_dir, meta_path, now)
        assert buckets["spike_24h"]["window_target"] == 2
