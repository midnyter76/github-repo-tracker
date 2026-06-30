"""Tests for src/store.py — persistence layer.

Covers:
- write_snapshot: idempotent per-date star snapshots (DATA-02, DATA-04, DATA-05)
- write_metadata: separate, fully-overwritten metadata store (DATA-03)
- load_metadata / load_metadata_ids: read helpers for refresh_tracked (Plan 02)

All tests inject tmp_path so no writes ever reach the real data/ directory.
"""

import json
import types
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers — minimal fake repo objects (no PyGithub dependency)
# ---------------------------------------------------------------------------

def _make_repo(
    id: int,
    stargazers_count: int,
    full_name: str = "owner/repo",
    description: str | None = "A test repo",
    html_url: str = "https://github.com/owner/repo",
    created_at: datetime | None = None,
) -> types.SimpleNamespace:
    if created_at is None:
        created_at = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    return types.SimpleNamespace(
        id=id,
        stargazers_count=stargazers_count,
        full_name=full_name,
        description=description,
        html_url=html_url,
        created_at=created_at,
    )


def _utc(year=2026, month=6, day=27, hour=13) -> datetime:
    """Return a UTC-aware datetime for use as run_at."""
    return datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Task 1 — write_snapshot (DATA-02, DATA-04, DATA-05)
# ---------------------------------------------------------------------------

class TestWriteSnapshot:
    def test_creates_file_with_correct_schema(self, tmp_path: Path):
        """write_snapshot creates SNAPSHOTS_DIR/<date>.json with required top-level keys."""
        from src.store import write_snapshot

        run_at = _utc()
        repo = _make_repo(id=111, stargazers_count=50)
        snap_path = write_snapshot({"111": repo}, run_at, snapshots_dir=tmp_path)

        assert snap_path.exists(), "snapshot file must be created"
        data = json.loads(snap_path.read_text())
        assert data["date"] == "2026-06-27"
        assert data["captured_at"] == run_at.isoformat()
        assert "repos" in data

    def test_repos_keyed_by_str_id_with_star_count(self, tmp_path: Path):
        """repos dict is keyed by str(repo.id) and contains star count only (DATA-02)."""
        from src.store import write_snapshot

        run_at = _utc()
        repo = _make_repo(id=111, stargazers_count=50)
        snap_path = write_snapshot({"111": repo}, run_at, snapshots_dir=tmp_path)

        data = json.loads(snap_path.read_text())
        assert "111" in data["repos"]
        assert data["repos"]["111"] == {"stars": 50}

    def test_filename_derived_from_run_at_date(self, tmp_path: Path):
        """Snapshot filename is YYYY-MM-DD.json derived from run_at (DATA-05)."""
        from src.store import write_snapshot

        run_at = _utc(year=2026, month=6, day=27)
        repo = _make_repo(id=222, stargazers_count=99)
        snap_path = write_snapshot({"222": repo}, run_at, snapshots_dir=tmp_path)

        assert snap_path.name == "2026-06-27.json"

    def test_captured_at_is_utc_isoformat(self, tmp_path: Path):
        """captured_at is run_at.isoformat() — a timezone-aware UTC ISO 8601 string (DATA-05)."""
        from src.store import write_snapshot

        run_at = _utc()
        repo = _make_repo(id=333, stargazers_count=10)
        snap_path = write_snapshot({"333": repo}, run_at, snapshots_dir=tmp_path)

        data = json.loads(snap_path.read_text())
        # Must be parseable as an ISO 8601 datetime with timezone info
        parsed = datetime.fromisoformat(data["captured_at"])
        assert parsed.tzinfo is not None, "captured_at must be timezone-aware"

    def test_idempotency_second_run_adds_not_drops(self, tmp_path: Path):
        """Same-day second run merges, never drops entries written by first run (DATA-04)."""
        from src.store import write_snapshot

        run_at = _utc()
        repo_111 = _make_repo(id=111, stargazers_count=50)
        repo_222 = _make_repo(id=222, stargazers_count=99)

        # First write: only repo 111
        write_snapshot({"111": repo_111}, run_at, snapshots_dir=tmp_path)
        # Second write: only repo 222 (same date)
        write_snapshot({"222": repo_222}, run_at, snapshots_dir=tmp_path)

        data = json.loads((tmp_path / "2026-06-27.json").read_text())
        # Both repos must be present — second write must NOT drop repo 111
        assert "111" in data["repos"], "first-run entry must survive second write"
        assert "222" in data["repos"], "second-run entry must be present"

    def test_upsert_updates_star_count_for_same_id(self, tmp_path: Path):
        """Re-running same date with updated star count overwrites the entry (upsert)."""
        from src.store import write_snapshot

        run_at = _utc()
        repo_v1 = _make_repo(id=111, stargazers_count=50)
        repo_v2 = _make_repo(id=111, stargazers_count=75)

        write_snapshot({"111": repo_v1}, run_at, snapshots_dir=tmp_path)
        write_snapshot({"111": repo_v2}, run_at, snapshots_dir=tmp_path)

        data = json.loads((tmp_path / "2026-06-27.json").read_text())
        assert data["repos"]["111"]["stars"] == 75, "upsert must update to new value"

    def test_idempotency_preserves_other_ids_on_upsert(self, tmp_path: Path):
        """Updating one repo's stars in a second run must not drop other repos."""
        from src.store import write_snapshot

        run_at = _utc()
        repo_111 = _make_repo(id=111, stargazers_count=50)
        repo_222 = _make_repo(id=222, stargazers_count=99)
        repo_111_v2 = _make_repo(id=111, stargazers_count=75)

        write_snapshot({"111": repo_111, "222": repo_222}, run_at, snapshots_dir=tmp_path)
        write_snapshot({"111": repo_111_v2}, run_at, snapshots_dir=tmp_path)

        data = json.loads((tmp_path / "2026-06-27.json").read_text())
        assert data["repos"]["111"]["stars"] == 75
        assert "222" in data["repos"], "repo 222 must not be dropped when updating 111"

    def test_creates_snapshots_dir_if_missing(self, tmp_path: Path):
        """SNAPSHOTS_DIR is created with mkdir parents/exist_ok if it doesn't exist."""
        from src.store import write_snapshot

        nested = tmp_path / "a" / "b" / "c"
        assert not nested.exists()

        run_at = _utc()
        repo = _make_repo(id=444, stargazers_count=5)
        snap_path = write_snapshot({"444": repo}, run_at, snapshots_dir=nested)

        assert nested.exists()
        assert snap_path.exists()

    def test_returns_path_to_snapshot_file(self, tmp_path: Path):
        """write_snapshot returns the Path of the written file."""
        from src.store import write_snapshot

        run_at = _utc()
        repo = _make_repo(id=555, stargazers_count=20)
        result = write_snapshot({"555": repo}, run_at, snapshots_dir=tmp_path)

        assert isinstance(result, Path)
        assert result.exists()


# ---------------------------------------------------------------------------
# Task 2 — write_metadata, load_metadata, load_metadata_ids (DATA-03)
# ---------------------------------------------------------------------------

class TestWriteMetadata:
    def test_creates_file_with_updated_at_and_repos(self, tmp_path: Path):
        """write_metadata creates a file with updated_at and repos top-level keys."""
        from src.store import write_metadata

        run_at = _utc()
        repo = _make_repo(id=111, stargazers_count=50)
        md_path = tmp_path / "metadata.json"
        write_metadata({"111": repo}, run_at, metadata_path=md_path)

        assert md_path.exists()
        data = json.loads(md_path.read_text())
        assert "updated_at" in data
        assert "repos" in data
        assert data["updated_at"] == run_at.isoformat()

    def test_repos_contains_required_fields(self, tmp_path: Path):
        """Metadata repos entry has full_name, description, created_at, html_url."""
        from src.store import write_metadata

        run_at = _utc()
        repo = _make_repo(
            id=111,
            stargazers_count=50,
            full_name="owner/my-repo",
            description="An LLM tool",
            html_url="https://github.com/owner/my-repo",
            created_at=datetime(2024, 11, 15, 10, 0, 0, tzinfo=timezone.utc),
        )
        md_path = tmp_path / "metadata.json"
        write_metadata({"111": repo}, run_at, metadata_path=md_path)

        data = json.loads(md_path.read_text())
        entry = data["repos"]["111"]
        assert entry["full_name"] == "owner/my-repo"
        assert entry["description"] == "An LLM tool"
        assert entry["html_url"] == "https://github.com/owner/my-repo"
        assert "created_at" in entry

    def test_none_description_stored_as_empty_string(self, tmp_path: Path):
        """description=None is stored as '' not null (RESEARCH Pattern 7)."""
        from src.store import write_metadata

        run_at = _utc()
        repo = _make_repo(id=111, stargazers_count=50, description=None)
        md_path = tmp_path / "metadata.json"
        write_metadata({"111": repo}, run_at, metadata_path=md_path)

        data = json.loads(md_path.read_text())
        assert data["repos"]["111"]["description"] == ""

    def test_created_at_is_utc_isoformat(self, tmp_path: Path):
        """created_at field is serialized via .isoformat() — UTC ISO 8601 (DATA-05)."""
        from src.store import write_metadata

        run_at = _utc()
        created = datetime(2024, 11, 15, 10, 0, 0, tzinfo=timezone.utc)
        repo = _make_repo(id=111, stargazers_count=50, created_at=created)
        md_path = tmp_path / "metadata.json"
        write_metadata({"111": repo}, run_at, metadata_path=md_path)

        data = json.loads(md_path.read_text())
        stored_created_at = data["repos"]["111"]["created_at"]
        parsed = datetime.fromisoformat(stored_created_at)
        assert parsed.tzinfo is not None, "created_at must be timezone-aware"
        assert parsed == created

    def test_full_overwrite_not_merge(self, tmp_path: Path):
        """write_metadata OVERWRITES the file — second call with different ids replaces, not merges (DATA-03)."""
        from src.store import write_metadata

        run_at = _utc()
        repo_111 = _make_repo(id=111, stargazers_count=50)
        repo_222 = _make_repo(id=222, stargazers_count=99)
        md_path = tmp_path / "metadata.json"

        # First write: repo 111
        write_metadata({"111": repo_111}, run_at, metadata_path=md_path)
        # Second write: repo 222 only
        write_metadata({"222": repo_222}, run_at, metadata_path=md_path)

        data = json.loads(md_path.read_text())
        assert "222" in data["repos"], "second write must be present"
        assert "111" not in data["repos"], "first write must be replaced (full overwrite, not merge)"

    def test_no_topics_field_in_metadata(self, tmp_path: Path):
        """write_metadata must NOT include a 'topics' field (Pitfall 6 — avoid get_topics())."""
        from src.store import write_metadata

        run_at = _utc()
        repo = _make_repo(id=111, stargazers_count=50)
        md_path = tmp_path / "metadata.json"
        write_metadata({"111": repo}, run_at, metadata_path=md_path)

        data = json.loads(md_path.read_text())
        assert "topics" not in data["repos"]["111"], "topics must be omitted (Pitfall 6)"

    def test_returns_path_to_metadata_file(self, tmp_path: Path):
        """write_metadata returns the Path of the written file."""
        from src.store import write_metadata

        run_at = _utc()
        repo = _make_repo(id=111, stargazers_count=50)
        md_path = tmp_path / "metadata.json"
        result = write_metadata({"111": repo}, run_at, metadata_path=md_path)

        assert isinstance(result, Path)
        assert result.exists()


class TestLoadMetadata:
    def test_returns_empty_dict_when_file_absent(self, tmp_path: Path):
        """load_metadata returns {} when the metadata file does not exist."""
        from src.store import load_metadata

        md_path = tmp_path / "nonexistent.json"
        assert load_metadata(metadata_path=md_path) == {}

    def test_returns_parsed_dict_when_file_present(self, tmp_path: Path):
        """load_metadata returns the full parsed dict when the file exists."""
        from src.store import load_metadata, write_metadata

        run_at = _utc()
        repo = _make_repo(id=111, stargazers_count=50)
        md_path = tmp_path / "metadata.json"
        write_metadata({"111": repo}, run_at, metadata_path=md_path)

        result = load_metadata(metadata_path=md_path)
        assert "repos" in result
        assert "111" in result["repos"]


class TestLoadMetadataIds:
    def test_returns_empty_list_when_file_absent(self, tmp_path: Path):
        """load_metadata_ids returns [] when the metadata file does not exist."""
        from src.store import load_metadata_ids

        md_path = tmp_path / "nonexistent.json"
        assert load_metadata_ids(metadata_path=md_path) == []

    def test_returns_list_of_str_keys(self, tmp_path: Path):
        """load_metadata_ids returns list of str repo-id keys from metadata repos."""
        from src.store import load_metadata_ids, write_metadata

        run_at = _utc()
        repo_111 = _make_repo(id=111, stargazers_count=50)
        repo_222 = _make_repo(id=222, stargazers_count=99)
        md_path = tmp_path / "metadata.json"
        write_metadata({"111": repo_111, "222": repo_222}, run_at, metadata_path=md_path)

        ids = load_metadata_ids(metadata_path=md_path, max_age_days=None)
        assert isinstance(ids, list)
        assert set(ids) == {"111", "222"}

    def test_max_age_days_filters_old_repos(self, tmp_path: Path):
        """max_age_days excludes repos whose created_at is older than the cutoff."""
        from datetime import timedelta
        from src.store import load_metadata_ids, write_metadata

        run_at = _utc()
        recent = _make_repo(id=111, stargazers_count=10, created_at=run_at - timedelta(days=10))
        old = _make_repo(id=222, stargazers_count=99, created_at=datetime(2024, 1, 15, tzinfo=timezone.utc))
        md_path = tmp_path / "metadata.json"
        write_metadata({"111": recent, "222": old}, run_at, metadata_path=md_path)

        ids = load_metadata_ids(metadata_path=md_path, max_age_days=45)
        assert set(ids) == {"111"}
