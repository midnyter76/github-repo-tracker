"""Digest renderer for GitHub Repo Tracker.

Renders the four-bucket velocity report to reports/YYYY-MM-DD.md.
Implements CONTEXT.md decisions D-03 (fixed section order), D-04 (bullet-line
format), D-05 (reports/YYYY-MM-DD.md path), and D-07 (warming note for inactive
breakthrough buckets).

Security: repo descriptions are attacker-influenceable GitHub API text written
to a public browsable markdown file. sanitize_description() neutralizes
newlines, control chars, HTML, backticks, and markdown-link injection before
any text reaches the output file (ASVS V5, T-02-07/08/09).

Public API:
    sanitize_description(text, max_chars) -> str
    render_warming_note(bucket) -> str
    render_entry(entry, markers) -> str
    render_bucket(title, bucket, markers) -> str
    write_digest(buckets, markers, now, reports_dir) -> Path
"""

import re
from datetime import datetime
from pathlib import Path

from src import config

# ---------------------------------------------------------------------------
# Security: Description Sanitization (ASVS V5, Pitfall 1, T-02-07/08/09)
# ---------------------------------------------------------------------------

# Characters that must be stripped to prevent markdown injection or ambiguity.
# < > stripped per T-02-09; ` stripped per T-02-09.
_STRIP_CHARS_RE = re.compile(r"[<>`]")


def sanitize_description(text: str | None, max_chars: int = config.DESCRIPTION_MAX_CHARS) -> str:
    """Sanitize an untrusted repo description for safe embedding in a markdown bullet line.

    Sanitization steps (applied in order):
    1. Normalize None to "".
    2. Collapse \\n, \\r, \\t to single spaces; collapse runs of whitespace.
    3. Remove ASCII control characters (ord < 32, excluding the already-collapsed
       whitespace chars which are now spaces).
    4. Remove [ and ] characters so that no ]( link-injection vector can form.
    5. Strip < > and backticks (T-02-09).
    6. strip() the result.
    7. Truncate to max_chars; if truncated, append U+2026 ELLIPSIS.

    Args:
        text:      Raw description from GitHub API (may be None).
        max_chars: Maximum character count before truncation (exclusive of ellipsis).
                   Defaults to config.DESCRIPTION_MAX_CHARS (120).

    Returns:
        Sanitized single-line string safe for markdown bullet embedding.
        Guaranteed to contain no embedded newlines and no ]( substring.
    """
    # Step 1: None guard
    if not text:
        return ""

    # Step 2: Collapse whitespace control chars to spaces then squeeze runs
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    text = re.sub(r" {2,}", " ", text)

    # Step 3: Strip remaining ASCII control chars (ord < 32)
    # After step 2, \n/\r/\t are already spaces so only other control chars remain.
    text = re.sub(r"[\x00-\x1f]", "", text)

    # Step 4: Remove [ and ] to prevent markdown-link injection
    # Escaping (e.g. \] ) is NOT sufficient — \](url) still contains ]( and
    # would be rendered as a link by GitHub markdown. Removal is the safe choice.
    text = text.replace("[", "").replace("]", "")

    # Step 5: Strip < > and backticks
    text = _STRIP_CHARS_RE.sub("", text)

    # Step 6: Strip leading/trailing whitespace
    text = text.strip()

    # Step 7: Truncate (sanitize first, truncate last per security ordering)
    if len(text) > max_chars:
        text = text[:max_chars] + "…"  # U+2026 HORIZONTAL ELLIPSIS

    return text


# ---------------------------------------------------------------------------
# Warming Note (D-07)
# ---------------------------------------------------------------------------

def render_warming_note(bucket: dict) -> str:
    """Return the D-07 warming note for an inactive breakthrough bucket.

    The em-dash (—) is U+2014, matching D-07 exactly.

    Args:
        bucket: Bucket dict with 'snapshots_available' and 'window_target'.

    Returns:
        Italicised warming note string.
    """
    n = bucket["snapshots_available"]
    m = bucket["window_target"]
    return f"_Breakthrough buckets warming up — {n} of {m} days collected._"


# ---------------------------------------------------------------------------
# Entry Rendering (D-04, REPORT-02, REPORT-04)
# ---------------------------------------------------------------------------

def render_entry(entry: dict, markers: dict) -> str:
    """Render a single repo as a D-04 bullet line.

    Format:
        - {marker} [{full_name}]({html_url}) — ★{stars} (+{velocity:.1f}/day) · created {date} · {desc}

    The description is sanitized before rendering. No embedded newline can appear
    in the result because sanitize_description() guarantees a single-line string.

    Args:
        entry:   Entry dict from compute_buckets (id, full_name, html_url,
                 description, created_at, stars, velocity_per_day).
        markers: Dict mapping str(repo_id) -> "new" | "returning".
                 Absent key defaults to "new" (🆕).

    Returns:
        Single-line bullet string (no trailing newline).
    """
    rid = entry["id"]
    marker = "\U0001f195" if markers.get(rid, "new") == "new" else "↩"  # 🆕 or ↩
    full_name = entry["full_name"]
    html_url = entry["html_url"]
    stars = entry["stars"]
    velocity = entry["velocity_per_day"]
    created_date = entry["created_at"][:10]  # YYYY-MM-DD
    description = sanitize_description(entry.get("description", ""))

    return (
        f"- {marker} [{full_name}]({html_url}) — "
        f"★{stars} (+{velocity:.1f}/day) · "
        f"created {created_date} · {description}"
    )


# ---------------------------------------------------------------------------
# Bucket Rendering (D-03, D-07)
# ---------------------------------------------------------------------------

def render_bucket(title: str, bucket: dict, markers: dict) -> str:
    """Render one digest section (H2 header + content).

    Always emits the ## header. Content rules:
    - Inactive bucket (active=False): warming note (D-07).
    - Active bucket, no entries:      italic "no qualifying repos" note (sparse).
    - Active bucket, has entries:     one bullet line per entry (D-04).

    Args:
        title:   Section title (e.g. "Brand New Weekly"). The ## is prepended here.
        bucket:  Bucket dict from compute_buckets.
        markers: Markers dict passed through to render_entry.

    Returns:
        Multi-line string for this section (no trailing newline).
    """
    lines = [f"## {title}"]

    if not bucket["active"]:
        lines.append(render_warming_note(bucket))
    elif not bucket["entries"]:
        lines.append("_No qualifying repos yet._")
    else:
        for entry in bucket["entries"]:
            lines.append(render_entry(entry, markers))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Digest Writer (REPORT-01, D-05)
# ---------------------------------------------------------------------------

# Fixed section order and titles (D-03)
_SECTIONS = [
    ("Brand New Weekly",       "brand_new_weekly"),
    ("Brand New Monthly",      "brand_new_monthly"),
    ("Breakthrough 24h Spike", "spike_24h"),
    ("Breakthrough 30-Day Velocity", "velocity_30d"),
]


def write_digest(
    buckets: dict,
    markers: dict,
    now: datetime,
    reports_dir: Path = config.REPORTS_DIR,
) -> Path:
    """Render the four-bucket digest and write it to reports/YYYY-MM-DD.md.

    Section order is fixed per D-03: Brand New Weekly → Brand New Monthly →
    Breakthrough 24h Spike → Breakthrough 30-Day Velocity.

    Args:
        buckets:     Dict from rank.compute_buckets (four-bucket contract).
        markers:     Dict from seen.classify_and_update mapping str(id) -> "new"|"returning".
        now:         UTC datetime for the run; used to derive the date filename.
        reports_dir: Directory for output files. Created if absent.

    Returns:
        Path of the written digest file.
    """
    date_str = now.strftime("%Y-%m-%d")

    # Build document: H1 title then four ordered sections separated by blank lines
    parts = [f"# AI Repo Tracker — {date_str}"]
    for title, key in _SECTIONS:
        parts.append(render_bucket(title, buckets[key], markers))

    document = "\n\n".join(parts) + "\n"

    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{date_str}.md"
    path.write_text(document, encoding="utf-8")
    return path
