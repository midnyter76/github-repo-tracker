"""Tests for src/report.py — digest rendering and description sanitization.

Covers:
- SECURITY — newline injection (T-02-07): description with \n renders as single bullet line
- SECURITY — link injection (T-02-08): description with ](url) cannot create clickable link
- SECURITY — control chars + truncation (T-02-09): 500-char desc truncated, control chars gone
- Bullet format (REPORT-02): all required fields present in rendered entry
- Markers (REPORT-04): "returning" -> ↩, absent -> 🆕
- Warming note (D-07): inactive bucket prints header + warming note, never empty/crash
- Fixed order (D-03): Brand New Weekly < Brand New Monthly < Breakthrough 24h Spike < 30-Day Velocity
- File write (REPORT-01): write_digest creates YYYY-MM-DD.md and returns the Path
- Sparse bucket: active bucket with fewer entries than cap renders exactly that many bullets
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.config import DESCRIPTION_MAX_CHARS


# ---------------------------------------------------------------------------
# Helpers — in-memory bucket and entry builders
# ---------------------------------------------------------------------------

def _entry(
    id: str = "123",
    full_name: str = "owner/cool-repo",
    html_url: str = "https://github.com/owner/cool-repo",
    description: str = "A neat AI library",
    created_at: str = "2026-06-01T10:00:00+00:00",
    stars: int = 500,
    velocity_per_day: float = 12.5,
) -> dict:
    """Build a minimal entry matching the rank.compute_buckets contract."""
    return {
        "id": id,
        "full_name": full_name,
        "html_url": html_url,
        "description": description,
        "created_at": created_at,
        "stars": stars,
        "velocity_per_day": velocity_per_day,
    }


def _active_bucket(entries: list[dict], window_target: int = 7, snapshots_available: int = 5) -> dict:
    return {
        "active": True,
        "snapshots_available": snapshots_available,
        "window_target": window_target,
        "entries": entries,
    }


def _inactive_bucket(snapshots_available: int = 1, window_target: int = 2) -> dict:
    return {
        "active": False,
        "snapshots_available": snapshots_available,
        "window_target": window_target,
        "entries": [],
    }


def _make_buckets(
    weekly_entries=None,
    monthly_entries=None,
    spike_active=True,
    spike_entries=None,
    v30d_active=True,
    v30d_entries=None,
) -> dict:
    """Build a complete four-bucket dict matching compute_buckets output."""
    return {
        "brand_new_weekly": _active_bucket(weekly_entries or [_entry()], window_target=7),
        "brand_new_monthly": _active_bucket(monthly_entries or [_entry()], window_target=30),
        "spike_24h": (
            _active_bucket(spike_entries or [_entry()], window_target=2)
            if spike_active
            else _inactive_bucket(snapshots_available=1, window_target=2)
        ),
        "velocity_30d": (
            _active_bucket(v30d_entries or [_entry()], window_target=30)
            if v30d_active
            else _inactive_bucket(snapshots_available=1, window_target=30)
        ),
    }


def _now() -> datetime:
    return datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# TestSanitizeDescription — ASVS V5 / Pitfall 1
# ---------------------------------------------------------------------------

class TestSanitizeDescription:
    def test_newline_injection_rendered_as_single_line(self):
        """SECURITY T-02-07: description with \\n renders with no embedded newline."""
        from src.report import sanitize_description

        result = sanitize_description("first line\nsecond line")
        assert "\n" not in result, "embedded newline must be collapsed to space"

    def test_carriage_return_collapsed(self):
        """SECURITY T-02-07: \\r is also collapsed to a space."""
        from src.report import sanitize_description

        result = sanitize_description("line1\rline2")
        assert "\r" not in result

    def test_tab_collapsed(self):
        """SECURITY T-02-07: \\t is collapsed to a space."""
        from src.report import sanitize_description

        result = sanitize_description("col1\tcol2")
        assert "\t" not in result

    def test_link_injection_no_bracket_paren_sequence(self):
        """SECURITY T-02-08: description with ](url) produces no clickable link."""
        from src.report import sanitize_description

        evil = "check [me](http://evil.com)"
        result = sanitize_description(evil)
        assert "](" not in result, "link-injection vector ]( must be absent from sanitized output"

    def test_link_injection_complex_case(self):
        """SECURITY T-02-08: nested or alternate link syntax neutralized."""
        from src.report import sanitize_description

        evil = "see [here](http://evil.com) and [also](http://other.com)"
        result = sanitize_description(evil)
        assert "](" not in result

    def test_html_angle_brackets_stripped(self):
        """SECURITY T-02-09: < and > characters are stripped."""
        from src.report import sanitize_description

        result = sanitize_description("<script>alert(1)</script>")
        assert "<" not in result
        assert ">" not in result

    def test_backticks_stripped(self):
        """SECURITY T-02-09: backticks are stripped."""
        from src.report import sanitize_description

        result = sanitize_description("run `rm -rf /`")
        assert "`" not in result

    def test_control_chars_stripped(self):
        """SECURITY T-02-09: ASCII control chars (ord < 32) except tab/newline/cr are stripped."""
        from src.report import sanitize_description

        # BEL (0x07) and ESC (0x1B) are control chars
        result = sanitize_description("hello\x07world\x1btest")
        assert "\x07" not in result
        assert "\x1b" not in result

    def test_truncation_at_max_chars(self):
        """SECURITY T-02-09: 500-char description truncated to <= DESCRIPTION_MAX_CHARS + 1."""
        from src.report import sanitize_description

        long_text = "A" * 500
        result = sanitize_description(long_text)
        assert len(result) <= DESCRIPTION_MAX_CHARS + 1  # +1 for the ellipsis char

    def test_truncation_appends_ellipsis(self):
        """SECURITY T-02-09: truncated description ends with ellipsis char (U+2026)."""
        from src.report import sanitize_description

        long_text = "B" * 500
        result = sanitize_description(long_text)
        assert result.endswith("…"), "truncated output must end with U+2026 ellipsis"

    def test_short_description_not_truncated(self):
        """A description shorter than the limit is returned unchanged (modulo sanitization)."""
        from src.report import sanitize_description

        short = "A short description."
        result = sanitize_description(short)
        assert result == short

    def test_none_input_returns_empty_string(self):
        """None description returns empty string without raising."""
        from src.report import sanitize_description

        result = sanitize_description(None)
        assert result == ""

    def test_empty_string_returns_empty(self):
        """Empty string returns empty string."""
        from src.report import sanitize_description

        result = sanitize_description("")
        assert result == ""

    def test_whitespace_only_returns_empty(self):
        """String of only spaces/tabs/newlines returns empty string after stripping."""
        from src.report import sanitize_description

        result = sanitize_description("   \n\t  ")
        assert result == ""


# ---------------------------------------------------------------------------
# TestRenderEntry — bullet line format (REPORT-02)
# ---------------------------------------------------------------------------

class TestRenderEntry:
    def test_bullet_contains_full_name_link(self):
        """REPORT-02: rendered entry contains [full_name](html_url)."""
        from src.report import render_entry

        e = _entry(full_name="owner/cool-repo", html_url="https://github.com/owner/cool-repo")
        result = render_entry(e, markers={})
        assert "[owner/cool-repo](https://github.com/owner/cool-repo)" in result

    def test_bullet_contains_stars(self):
        """REPORT-02: rendered entry contains ★{stars}."""
        from src.report import render_entry

        e = _entry(stars=500)
        result = render_entry(e, markers={})
        assert "★500" in result

    def test_bullet_contains_velocity(self):
        """REPORT-02: rendered entry contains (+{velocity_per_day:.1f}/day)."""
        from src.report import render_entry

        e = _entry(velocity_per_day=12.5)
        result = render_entry(e, markers={})
        assert "(+12.5/day)" in result

    def test_bullet_contains_created_date(self):
        """REPORT-02: rendered entry contains created {YYYY-MM-DD}."""
        from src.report import render_entry

        e = _entry(created_at="2026-06-01T10:00:00+00:00")
        result = render_entry(e, markers={})
        assert "created 2026-06-01" in result

    def test_bullet_contains_description(self):
        """REPORT-02: rendered entry includes (sanitized) description."""
        from src.report import render_entry

        e = _entry(description="A neat AI library")
        result = render_entry(e, markers={})
        assert "A neat AI library" in result

    def test_bullet_is_single_line(self):
        """REPORT-02 / T-02-07: entry rendering produces exactly one line (no embedded newline)."""
        from src.report import render_entry

        e = _entry(description="has\nnewline")
        result = render_entry(e, markers={})
        assert "\n" not in result, "render_entry must produce a single line"

    def test_starts_with_dash(self):
        """Bullet line starts with '- '."""
        from src.report import render_entry

        e = _entry()
        result = render_entry(e, markers={})
        assert result.startswith("- ")


# ---------------------------------------------------------------------------
# TestMarkers — REPORT-04
# ---------------------------------------------------------------------------

class TestMarkers:
    def test_absent_id_renders_new_marker(self):
        """REPORT-04: id absent from markers dict defaults to 🆕."""
        from src.report import render_entry

        e = _entry(id="999")
        result = render_entry(e, markers={})  # id not in markers
        assert "🆕" in result

    def test_new_marker_renders_new_emoji(self):
        """REPORT-04: markers[id]='new' renders 🆕."""
        from src.report import render_entry

        e = _entry(id="42")
        result = render_entry(e, markers={"42": "new"})
        assert "🆕" in result

    def test_returning_marker_renders_return_emoji(self):
        """REPORT-04: markers[id]='returning' renders ↩."""
        from src.report import render_entry

        e = _entry(id="42")
        result = render_entry(e, markers={"42": "returning"})
        assert "↩" in result
        assert "🆕" not in result


# ---------------------------------------------------------------------------
# TestRenderWarmingnote — D-07
# ---------------------------------------------------------------------------

class TestRenderWarmingnote:
    def test_warming_note_exact_text(self):
        """D-07: warming note matches exact required string."""
        from src.report import render_warming_note

        bucket = _inactive_bucket(snapshots_available=1, window_target=2)
        result = render_warming_note(bucket)
        assert result == "_Breakthrough buckets warming up — 1 of 2 days collected._"

    def test_warming_note_uses_bucket_values(self):
        """D-07: warming note uses snapshots_available and window_target from the bucket."""
        from src.report import render_warming_note

        bucket = _inactive_bucket(snapshots_available=3, window_target=7)
        result = render_warming_note(bucket)
        assert "3 of 7" in result


# ---------------------------------------------------------------------------
# TestRenderBucket — section rendering
# ---------------------------------------------------------------------------

class TestRenderBucket:
    def test_inactive_bucket_prints_header(self):
        """D-07: inactive breakthrough bucket ALWAYS prints its ## header."""
        from src.report import render_bucket

        bucket = _inactive_bucket(snapshots_available=1, window_target=2)
        result = render_bucket("Breakthrough 24h Spike", bucket, markers={})
        assert "## Breakthrough 24h Spike" in result

    def test_inactive_bucket_prints_warming_note(self):
        """D-07: inactive bucket renders warming note instead of entries."""
        from src.report import render_bucket

        bucket = _inactive_bucket(snapshots_available=1, window_target=2)
        result = render_bucket("Breakthrough 24h Spike", bucket, markers={})
        assert "warming up" in result

    def test_active_empty_bucket_does_not_crash(self):
        """Active bucket with zero entries renders a 'no qualifying repos' note."""
        from src.report import render_bucket

        bucket = _active_bucket(entries=[], window_target=7)
        result = render_bucket("Brand New Weekly", bucket, markers={})
        assert "## Brand New Weekly" in result
        # Should not crash; optional: may print a note
        assert result is not None

    def test_active_bucket_renders_entries(self):
        """Active bucket with entries renders bullet lines."""
        from src.report import render_bucket

        entries = [_entry(id="1", full_name="a/b"), _entry(id="2", full_name="c/d")]
        bucket = _active_bucket(entries=entries, window_target=7)
        result = render_bucket("Brand New Weekly", bucket, markers={})
        assert "a/b" in result
        assert "c/d" in result

    def test_sparse_bucket_renders_exact_count(self):
        """Sparse bucket (fewer entries than cap) renders exactly that many bullets, no padding."""
        from src.report import render_bucket

        entries = [_entry(id="1"), _entry(id="2")]  # only 2, cap is 10
        bucket = _active_bucket(entries=entries, window_target=7)
        result = render_bucket("Brand New Weekly", bucket, markers={})
        bullet_lines = [ln for ln in result.split("\n") if ln.startswith("- ")]
        assert len(bullet_lines) == 2


# ---------------------------------------------------------------------------
# TestWriteDigest — REPORT-01, D-03, D-05
# ---------------------------------------------------------------------------

class TestWriteDigest:
    def test_creates_file_with_date_filename(self, tmp_path: Path):
        """REPORT-01: write_digest creates reports_dir/YYYY-MM-DD.md."""
        from src.report import write_digest

        now = _now()  # 2026-06-28
        buckets = _make_buckets()
        path = write_digest(buckets, markers={}, now=now, reports_dir=tmp_path)

        assert path.exists(), "digest file must be created"
        assert path.name == "2026-06-28.md", f"filename must be YYYY-MM-DD.md, got {path.name}"

    def test_returns_path_object(self, tmp_path: Path):
        """REPORT-01: write_digest returns the Path of the written file."""
        from src.report import write_digest

        now = _now()
        buckets = _make_buckets()
        result = write_digest(buckets, markers={}, now=now, reports_dir=tmp_path)

        assert isinstance(result, Path)

    def test_all_four_headers_present(self, tmp_path: Path):
        """D-03: all four H2 section headers appear in the digest."""
        from src.report import write_digest

        now = _now()
        buckets = _make_buckets()
        path = write_digest(buckets, markers={}, now=now, reports_dir=tmp_path)
        content = path.read_text()

        assert "## Brand New Weekly" in content
        assert "## Brand New Monthly" in content
        assert "## Breakthrough 24h Spike" in content
        assert "## Breakthrough 30-Day Velocity" in content

    def test_fixed_section_order(self, tmp_path: Path):
        """D-03: section order is Brand New Weekly < Brand New Monthly < 24h Spike < 30-Day Velocity."""
        from src.report import write_digest

        now = _now()
        buckets = _make_buckets()
        path = write_digest(buckets, markers={}, now=now, reports_dir=tmp_path)
        content = path.read_text()

        idx_weekly = content.index("## Brand New Weekly")
        idx_monthly = content.index("## Brand New Monthly")
        idx_spike = content.index("## Breakthrough 24h Spike")
        idx_velocity = content.index("## Breakthrough 30-Day Velocity")

        assert idx_weekly < idx_monthly, "Weekly must precede Monthly"
        assert idx_monthly < idx_spike, "Monthly must precede 24h Spike"
        assert idx_spike < idx_velocity, "24h Spike must precede 30-Day Velocity"

    def test_inactive_spike_bucket_shows_warming_note(self, tmp_path: Path):
        """D-07: inactive spike_24h bucket renders warming note in full digest."""
        from src.report import write_digest

        now = _now()
        buckets = _make_buckets(spike_active=False)
        path = write_digest(buckets, markers={}, now=now, reports_dir=tmp_path)
        content = path.read_text()

        assert "## Breakthrough 24h Spike" in content, "header must always print"
        assert "warming up" in content, "warming note must appear for inactive bucket"

    def test_creates_reports_dir_if_missing(self, tmp_path: Path):
        """REPORT-01: reports_dir is created with mkdir(parents=True, exist_ok=True)."""
        from src.report import write_digest

        nested = tmp_path / "a" / "b" / "reports"
        assert not nested.exists()

        now = _now()
        buckets = _make_buckets()
        write_digest(buckets, markers={}, now=now, reports_dir=nested)

        assert nested.exists()

    def test_marker_returning_in_digest(self, tmp_path: Path):
        """REPORT-04: markers['returning'] renders ↩ in the written file."""
        from src.report import write_digest

        entry = _entry(id="42")
        buckets = _make_buckets(weekly_entries=[entry])
        markers = {"42": "returning"}
        now = _now()
        path = write_digest(buckets, markers=markers, now=now, reports_dir=tmp_path)
        content = path.read_text()

        assert "↩" in content

    def test_link_injection_in_description_not_in_digest(self, tmp_path: Path):
        """SECURITY T-02-08: evil description with inject link does not produce ]( in sanitized output."""
        from src.report import write_digest, sanitize_description

        evil_desc = "check [me](http://evil.com)"
        sanitized = sanitize_description(evil_desc)
        assert "](" not in sanitized, "sanitize_description must remove ]( before writing"

        # Verify the full digest doesn't contain ]( in a way that originates from description
        # (the format itself will have ]( for the repo link, so we check sanitized directly)

    def test_h1_title_contains_date(self, tmp_path: Path):
        """Digest H1 title contains the formatted date."""
        from src.report import write_digest

        now = _now()
        buckets = _make_buckets()
        path = write_digest(buckets, markers={}, now=now, reports_dir=tmp_path)
        content = path.read_text()

        assert "# AI Repo Tracker — 2026-06-28" in content
