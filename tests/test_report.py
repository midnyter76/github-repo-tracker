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

import re
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
        content = path.read_text(encoding="utf-8")

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
        content = path.read_text(encoding="utf-8")

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
        content = path.read_text(encoding="utf-8")

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
        content = path.read_text(encoding="utf-8")

        assert "↩" in content  # ↩

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
        content = path.read_text(encoding="utf-8")

        assert "# AI Repo Tracker — 2026-06-28" in content  # — is U+2014 em-dash


# ---------------------------------------------------------------------------
# TestHtmlDigest — "4a: The Dispatch, hero edition" (Quick Task 260630-tl4)
# ---------------------------------------------------------------------------
# Security-sensitive (ASVS-aligned; matches TestSanitizeDescription rigor):
# T-TL4-01 (description XSS), T-TL4-02 (full_name XSS), T-TL4-03 (href
# attribute breakout). Plus logic/formatting parity with the ported JS math.

class TestHtmlDigest:
    # -- Security -----------------------------------------------------------

    def test_description_script_tag_never_raw_in_output(self):
        """T-TL4-01: description <script> payload never survives as a raw tag.

        _esc() = html.escape(sanitize_description(text), quote=True). Because
        sanitize_description() already STRIPS < and > (existing markdown-
        injection contract, unmodified), the brackets are removed entirely
        before html.escape runs — a stronger guarantee than mere escaping.
        Assert both halves: no raw tag survives, AND the payload text still
        flowed through (proving it was neutralized, not that the entry was
        simply absent from output).
        """
        from src.report import render_html_row

        e = _entry(id="1", description="<script>alert(1)</script>")
        result = render_html_row(e, markers={}, bucket_max_vel=1.0, now=_now())
        assert "<script" not in result, "raw <script tag must never appear"
        assert "alert(1)" in result, "payload text must still be present (neutralized, not dropped)"

    def test_full_name_img_payload_escaped(self):
        """T-TL4-02: full_name XSS payload is HTML-escaped (not merely stripped).

        full_name is NOT routed through sanitize_description (per design
        spec) — it's html.escape(value, quote=True) directly. So unlike the
        description path, angle brackets here DO survive as escaped entities.
        """
        from src.report import render_html_row

        e = _entry(id="1", full_name='evil"><img src=x onerror=1>/repo')
        result = render_html_row(e, markers={}, bucket_max_vel=1.0, now=_now())
        assert "<img" not in result, "raw <img tag must never appear unescaped"
        assert "&lt;img" in result or "&quot;" in result, "escaped form must be present"

    def test_full_name_img_payload_escaped_in_hero(self):
        """T-TL4-02: same guarantee in the hero card render path."""
        from src.report import render_html_hero

        e = _entry(id="1", full_name='evil"><img src=x onerror=1>/repo')
        result = render_html_hero(e, "Brand New This Week", _now())
        assert "<img" not in result
        assert "&lt;img" in result or "&quot;" in result

    def test_html_url_attribute_breakout_escaped(self):
        """T-TL4-03: html_url is escaped for the href="..." attribute context."""
        from src.report import render_html_row

        e = _entry(id="1", html_url='https://x/repo"><script>alert(1)</script>')
        result = render_html_row(e, markers={}, bucket_max_vel=1.0, now=_now())
        assert '"><script>' not in result
        assert "&quot;&gt;&lt;script&gt;" in result

    def test_description_newline_and_link_injection_neutralized(self):
        """Description with newline / ](url) injection: no raw newline, no '](' in the row."""
        from src.report import render_html_row

        e = _entry(id="1", description="line one\nline two [click](http://evil.com)")
        result = render_html_row(e, markers={}, bucket_max_vel=1.0, now=_now())
        # No embedded raw newline introduced BY the description itself surviving unsanitized.
        assert "line one\nline two" not in result
        assert "](" not in result

    # -- Logic / formatting ---------------------------------------------------

    def test_stars_full_thousands_separator(self):
        from src.report import _stars_full

        assert _stars_full(68693) == "68,693"

    def test_vel_fmt_one_decimal(self):
        from src.report import _vel_fmt

        assert _vel_fmt(12.53) == "12.5"

    def test_age_str_today(self):
        from src.report import _age_str

        now = _now()  # 2026-06-28
        assert _age_str("2026-06-28T10:00:00+00:00", now) == "today"

    def test_age_str_one_day(self):
        from src.report import _age_str

        now = _now()  # 2026-06-28
        assert _age_str("2026-06-27T10:00:00+00:00", now) == "1d old"

    def test_age_str_n_days(self):
        from src.report import _age_str

        now = _now()  # 2026-06-28
        assert _age_str("2026-06-20T10:00:00+00:00", now) == "8d old"

    def test_jsround_half_up(self):
        from src.report import _jsround

        assert _jsround(2.5) == 3

    def test_bar_pct_floors_at_seven(self):
        from src.report import _bar_pct

        assert _bar_pct(0.01, 100.0) == 7

    def test_bar_pct_bucket_max_is_100(self):
        from src.report import _bar_pct

        assert _bar_pct(50.0, 50.0) == 100

    def test_bar_fill_hue_at_pct_100(self):
        from src.report import _bar_fill

        assert "oklch(0.6 0.12 72)" in _bar_fill(100)

    def test_bar_fill_hue_at_pct_seven(self):
        from src.report import _bar_fill

        assert "oklch(0.6 0.12 146)" in _bar_fill(7)

    def test_select_top_mover_picks_global_max_and_carries_bucket_title(self):
        """The highest-velocity entry lives in a DIFFERENT bucket than the first
        one checked; assert both the entry AND its bucket title are returned."""
        from src.report import select_top_mover

        low = _entry(id="1", velocity_per_day=5.0)
        high = _entry(id="2", velocity_per_day=99.0)
        buckets = _make_buckets(
            weekly_entries=[low],
            monthly_entries=[],
            spike_active=False,
            v30d_entries=[high],
        )
        entry, title = select_top_mover(buckets)
        assert entry is high
        assert title == "Breakthrough · 30-Day Velocity"

    def test_select_top_mover_all_empty_returns_none_none(self):
        """All buckets truly empty (active-empty and inactive) -> (None, None).

        _make_buckets' `entries or [_entry()]` fallback treats an empty list
        as falsy, so it must be bypassed here by building buckets directly.
        """
        from src.report import select_top_mover

        buckets = {
            "brand_new_weekly": _active_bucket(entries=[], window_target=7),
            "brand_new_monthly": _active_bucket(entries=[], window_target=30),
            "spike_24h": _inactive_bucket(snapshots_available=1, window_target=2),
            "velocity_30d": _inactive_bucket(snapshots_available=1, window_target=30),
        }
        entry, title = select_top_mover(buckets)
        assert entry is None
        assert title is None

    def test_render_html_digest_contains_masthead_and_titles(self):
        from src.report import render_html_digest

        buckets = _make_buckets()
        result = render_html_digest(buckets, markers={}, now=_now())
        assert "The Dispatch" in result
        assert "Brand New This Week" in result
        assert "Brand New This Month" in result
        assert "Breakthrough · 24h Spike" in result
        assert "Breakthrough · 30-Day Velocity" in result
        assert "Fastest mover" in result
        assert "<script" not in result

    def test_render_html_digest_all_empty_buckets_no_crash(self):
        """All-empty buckets -> valid HTML with placeholder, never raises."""
        from src.report import render_html_digest

        buckets = {
            "brand_new_weekly": _active_bucket(entries=[], window_target=7),
            "brand_new_monthly": _active_bucket(entries=[], window_target=30),
            "spike_24h": _inactive_bucket(snapshots_available=1, window_target=2),
            "velocity_30d": _inactive_bucket(snapshots_available=1, window_target=30),
        }
        result = render_html_digest(buckets, markers={}, now=_now())
        assert result  # non-empty string
        assert "No qualifying repos yet — the radar is still warming up." in result
        assert "<script" not in result

    def test_inactive_bucket_renders_warming_message_no_underscores(self):
        from src.report import render_html_digest

        buckets = _make_buckets(spike_active=False)
        result = render_html_digest(buckets, markers={}, now=_now())
        assert "warming up" in result
        assert "_Breakthrough buckets warming up" not in result

    # -- File write -------------------------------------------------------------

    def test_write_html_digest_creates_html_file_no_md(self, tmp_path: Path):
        from src.report import write_html_digest

        now = _now()  # 2026-06-28
        buckets = _make_buckets()
        path = write_html_digest(buckets, markers={}, now=now, reports_dir=tmp_path)

        assert isinstance(path, Path)
        assert path.exists()
        assert path.name == "2026-06-28.html"
        md_files = list(tmp_path.glob("*.md"))
        assert md_files == [], f"write_html_digest must not write any .md file, found: {md_files}"

    def test_write_html_digest_creates_reports_dir_if_missing(self, tmp_path: Path):
        from src.report import write_html_digest

        nested = tmp_path / "a" / "b" / "reports"
        assert not nested.exists()

        now = _now()
        buckets = _make_buckets()
        write_html_digest(buckets, markers={}, now=now, reports_dir=nested)

        assert nested.exists()

    # -- Gmail rendering fix — gap removed, equivalent margin added (quick task 260701-ibb) --

    def test_masthead_issue_no_and_date_have_explicit_spacing(self):
        """Gmail drops flexbox `gap:`; pre-fix the two bare masthead spans are
        directly adjacent and concatenate ("Issue No. 3Wed..."). Post-fix the
        date span must carry an explicit margin-left so real whitespace exists
        even without gap support."""
        from src.report import render_html_digest

        result = render_html_digest(_make_buckets(), markers={}, now=_now())
        assert re.search(r'Issue No\. \d+</span>\s*<span style="[^"]*margin', result), (
            "date span must be styled with an explicit margin, not bare"
        )
        assert not re.search(r'Issue No\. \d+</span><span>', result), (
            "no bare </span><span> adjacency between issue-no and date "
            "(the pre-fix concatenation signature)"
        )

    def test_bucket_header_kicker_and_count_have_margin_not_gap(self):
        """Bucket header has THREE children (kicker, rule, count) around one
        `gap:12px`; a single margin only covers one side, so both the kicker
        and the count_label span need their own margin."""
        from src.report import render_html_bucket

        result = render_html_bucket(
            "brand_new_weekly",
            "Brand New · Weekly",
            "Brand New This Week",
            _active_bucket([_entry()]),
            {},
            _now(),
        )

        kicker_match = re.search(r'<span style="([^"]*)">Brand New · Weekly</span>', result)
        assert kicker_match is not None, "kicker span not found"
        assert "margin-right:12px" in kicker_match.group(1)

        count_match = re.search(r'<span style="([^"]*)">(?:\d+ repos|warming up)</span>', result)
        assert count_match is not None, "count_label span not found"
        assert "margin-left:12px" in count_match.group(1)

        header_div_match = re.search(
            r'<div style="([^"]*)">\s*<span style="[^"]*">Brand New · Weekly</span>', result
        )
        assert header_div_match is not None, "header row div not found"
        assert "gap:12px" not in header_div_match.group(1), (
            "gap must be REMOVED from the header row, not duplicated alongside margin"
        )

    def test_row_stat_block_has_explicit_margin_not_gap(self):
        """Row outer <a> loses gap:16px; the 78px stat-block div gets an
        equivalent margin-right so it stays separated from the description
        column in Gmail."""
        from src.report import render_html_row

        result = render_html_row(_entry(), markers={}, bucket_max_vel=1.0, now=_now())

        a_tag_match = re.search(r'<a href="[^"]*" style="([^"]*)">', result)
        assert a_tag_match is not None, "outer <a> tag not found"
        assert "gap:16px" not in a_tag_match.group(1)

        stat_div_match = re.search(r'<div style="([^"]*width:78px[^"]*)">', result)
        assert stat_div_match is not None, "78px stat block div not found"
        assert "margin-right:16px" in stat_div_match.group(1)

    def test_hero_stat_row_has_explicit_margin_not_gap(self):
        """Hero stat row loses gap:7px; the 'stars / day' span gets an
        equivalent margin-left so it stays separated from the big velocity
        number in Gmail."""
        from src.report import render_html_hero

        result = render_html_hero(_entry(), "Brand New This Week", _now())

        stat_row_match = re.search(r'<div style="display:flex; align-items:flex-end;([^"]*)">', result)
        assert stat_row_match is not None, "hero stat row div not found"
        assert "gap:7px" not in stat_row_match.group(1)

        stars_day_match = re.search(r'<span style="([^"]*)">stars / day</span>', result)
        assert stars_day_match is not None, "'stars / day' span not found"
        assert "margin-left:7px" in stars_day_match.group(1)

    def test_render_html_digest_has_no_gap_declarations_anywhere(self):
        """Whole-document guard: catches any missed `gap:` token across the
        entire rendered digest, not just the 6 enumerated locations."""
        from src.report import render_html_digest

        result = render_html_digest(_make_buckets(), markers={}, now=_now())
        assert "gap:" not in result, "no email-HTML element may rely on flexbox gap for spacing"


# ---------------------------------------------------------------------------
# TestHtmlLeaders — CATEGORY LEADERS grid + stats strip (Quick Task 260701-j1w)
# ---------------------------------------------------------------------------
# Covers _vel_abbr, _count_tracked, _count_brand_new helpers, render_html_leaders
# grid/strip cells, table-based structural layout (Gmail-safe, no flex stack),
# and repo-name escaping (attacker-influenceable GitHub text).

class TestVelAbbr:
    def test_vel_abbr_thousands(self):
        from src.report import _vel_abbr

        assert _vel_abbr(3692.2) == "3.7k"

    def test_vel_abbr_under_thousand_falls_back_to_vel_fmt(self):
        from src.report import _vel_abbr

        assert _vel_abbr(94.9) == "94.9"

    def test_vel_abbr_boundary_at_1000_uses_k_suffix(self):
        from src.report import _vel_abbr

        assert _vel_abbr(1000.0) == "1.0k"


class TestCountTracked:
    def test_dedupes_same_id_across_buckets(self):
        """The same repo appearing in weekly + spike counts once; a distinct
        id in another bucket adds to the count."""
        from src.report import _count_tracked

        shared_weekly = _entry(id="1")
        shared_spike = _entry(id="1")  # same repo id, different bucket dict
        distinct_monthly = _entry(id="2")
        distinct_v30d = _entry(id="3")
        buckets = _make_buckets(
            weekly_entries=[shared_weekly],
            monthly_entries=[distinct_monthly],
            spike_entries=[shared_spike],
            v30d_entries=[distinct_v30d],
        )
        assert _count_tracked(buckets) == 3  # ids {1, 2, 3} — "1" counted once


class TestCountBrandNew:
    def test_counts_new_only_in_weekly_and_monthly(self):
        """Absent marker defaults to 'new'; explicit 'returning' does not count;
        entries in spike/velocity_30d must NOT count even if marked new."""
        from src.report import _count_brand_new

        new_entry = _entry(id="1")
        returning_entry = _entry(id="2")
        absent_entry = _entry(id="3")  # not in markers -> defaults to "new"
        spike_entry = _entry(id="4")  # must not be counted (wrong bucket)
        buckets = _make_buckets(
            weekly_entries=[new_entry, returning_entry],
            monthly_entries=[absent_entry],
            spike_entries=[spike_entry],
        )
        markers = {"1": "new", "2": "returning", "4": "new"}
        assert _count_brand_new(buckets, markers) == 2


class TestRenderHtmlLeaders:
    def test_grid_and_strip_are_table_based(self):
        """STRUCTURAL guard: exactly four 25%-wide grid cells and three
        33.33%-wide strip cells. This is the check that actually catches a
        Gmail-breaking flex stack — do not replace with a label-only check."""
        from src.report import render_html_leaders

        result = render_html_leaders(_make_buckets(), markers={}, now=_now())
        assert result.count('<td width="25%"') == 4
        assert result.count('<td width="33.33%"') == 3

    def test_active_cell_shows_kicker_leader_name_and_velocity(self):
        from src.report import render_html_leaders

        e = _entry(id="1", full_name="owner/cool-repo", velocity_per_day=42.0)
        buckets = _make_buckets(weekly_entries=[e])
        result = render_html_leaders(buckets, markers={}, now=_now())
        assert "NEW · WEEK" in result
        assert "cool-repo" in result
        assert "42.0" in result

    def test_inactive_cell_shows_warming_up_and_no_number(self):
        from src.report import render_html_leaders

        buckets = _make_buckets(spike_active=False)
        result = render_html_leaders(buckets, markers={}, now=_now())
        cells = result.split('<td width="25%"')[1:5]
        spike_cell = cells[2]  # spike_24h is third in _HTML_SECTIONS order
        assert "24H SPIKE" in spike_cell
        assert "Warming up." in spike_cell
        # "stars / day" + a big velocity number only render for an active
        # leader cell; their absence proves no number is shown here.
        assert "stars / day" not in spike_cell

    def test_repo_name_escaped_not_raw_script_tag(self):
        """SECURITY: repo name is attacker-influenceable GitHub text; must be
        html.escape(quote=True) exactly like render_html_hero."""
        from src.report import render_html_leaders

        e = _entry(id="1", full_name="owner/<script>evil")
        buckets = _make_buckets(weekly_entries=[e])
        result = render_html_leaders(buckets, markers={}, now=_now())
        assert "<script>evil" not in result
        assert "&lt;script&gt;evil" in result

    def test_leaders_block_has_no_gap_declarations(self):
        from src.report import render_html_leaders

        result = render_html_leaders(_make_buckets(), markers={}, now=_now())
        assert "gap:" not in result


class TestHtmlDigestStatsStrip:
    def test_stats_strip_labels_present(self):
        from src.report import render_html_digest

        result = render_html_digest(_make_buckets(), markers={}, now=_now())
        assert "REPOS TRACKED" in result
        assert "BRAND NEW" in result
        assert "TOP */DAY" in result

    def test_top_per_day_shows_abbreviated_global_max(self):
        from src.report import render_html_digest

        high = _entry(id="9", velocity_per_day=3692.2)
        buckets = _make_buckets(v30d_entries=[high])
        result = render_html_digest(buckets, markers={}, now=_now())
        assert "3.7k" in result

    def test_leaders_grid_inserted_between_hero_and_sections(self):
        """Leaders block must appear after the hero ('Fastest mover') and
        before the first bucket section kicker ('Brand New · Weekly' — the
        section-only kicker text; the hero uses the longer title 'Brand New
        This Week', which would give a false-early match via .index())."""
        from src.report import render_html_digest

        result = render_html_digest(_make_buckets(), markers={}, now=_now())
        idx_hero = result.index("Fastest mover")
        idx_leaders = result.index("REPOS TRACKED")
        idx_sections = result.index("Brand New · Weekly")
        assert idx_hero < idx_leaders < idx_sections
