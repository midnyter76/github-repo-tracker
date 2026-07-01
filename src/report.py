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
    select_top_mover(buckets) -> (entry|None, bucket_title|None)
    render_html_hero(top_mover, bucket_title, now) -> str
    render_html_row(entry, markers, bucket_max_vel, now) -> str
    render_html_bucket(bucket_key, kicker, title, bucket, markers, now) -> str
    render_html_digest(buckets, markers, now) -> str
    write_html_digest(buckets, markers, now, reports_dir) -> Path
"""

import html
import math
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


# ---------------------------------------------------------------------------
# HTML Digest — "4a: The Dispatch, hero edition" (Quick Task 260630-tl4)
# ---------------------------------------------------------------------------
# Self-contained inline-CSS HTML renderer, parallel to the markdown path
# above. Does NOT modify sanitize_description/render_warming_note/
# render_entry/render_bucket/write_digest — the markdown output stays
# byte-for-byte identical.
#
# Security: description, full_name, and html_url are attacker-influenceable
# GitHub API text rendered into an HTML email (see threat_model in the plan:
# T-TL4-01/02/03). _esc() sanitizes+escapes descriptions; full_name/html_url
# are html.escape(..., quote=True) directly (covers both text and attribute
# breakout contexts).

_HTML_SECTIONS = [
    ("brand_new_weekly", "Brand New · Weekly", "Brand New This Week"),
    ("brand_new_monthly", "Brand New · Monthly", "Brand New This Month"),
    ("spike_24h", "Breakthrough · 24h Spike", "Breakthrough · 24h Spike"),
    ("velocity_30d", "Breakthrough · 30-Day Velocity", "Breakthrough · 30-Day Velocity"),
]


def _jsround(x: float) -> int:
    """JS Math.round parity (half-up), unlike Python's banker's-rounding round()."""
    return math.floor(x + 0.5)


def _vel_fmt(v: float) -> str:
    """Format velocity_per_day as one decimal place, e.g. 12.53 -> '12.5'."""
    return f"{v:.1f}"


def _stars_full(n: int) -> str:
    """Format a star count with en-US thousands separators, e.g. 68693 -> '68,693'."""
    return f"{n:,}"


def _age_str(created_at: str, now: datetime) -> str:
    """Format repo age relative to `now`: 'today' / '1d old' / 'Nd old'."""
    days = (now.date() - datetime.fromisoformat(created_at).date()).days
    if days <= 0:
        return "today"
    if days == 1:
        return "1d old"
    return f"{days}d old"


def _bar_pct(v: float, bucket_max_vel: float) -> int:
    """Velocity bar fill percentage, floored at 7 so small bars stay visible."""
    return max(7, _jsround((v / bucket_max_vel) * 100))


def _bar_fill(pct: int) -> str:
    """CSS gradient for the velocity bar; hue slides green(152)->amber(72) with pct."""
    hue = _jsround(152 - (pct / 100) * 80)
    return f"linear-gradient(90deg, oklch(0.6 0.12 {hue}), oklch(0.82 0.17 {hue}))"


def _esc(text: str | None) -> str:
    """Sanitize (markdown-injection) then HTML-escape (quote=True) a description.

    Two distinct concerns: sanitize_description() neutralizes markdown-link
    injection / control chars; html.escape(..., quote=True) neutralizes HTML
    tag/attribute breakout. Both are required for HTML output (T-TL4-01).
    """
    return html.escape(sanitize_description(text), quote=True)


def select_top_mover(buckets: dict) -> tuple[dict | None, str | None]:
    """Return (entry, bucket_title) for the global-max velocity_per_day entry.

    Flattens every bucket's entries, in fixed _HTML_SECTIONS order, carrying
    the bucket title through the flatten so no fragile back-search is needed
    (the same repo can appear as distinct dicts with different velocities in
    multiple buckets — rank._build_entry builds a new dict per bucket).

    Args:
        buckets: Dict from rank.compute_buckets (four-bucket contract).

    Returns:
        (entry, bucket_title), or (None, None) when every bucket is empty.
        On ties, the first-encountered max wins (matches JS `>` semantics —
        Python's max() only updates on strictly-greater values).
    """
    tagged = [
        (title, e)
        for key, kicker, title in _HTML_SECTIONS
        for e in buckets[key]["entries"]
    ]
    if not tagged:
        return None, None
    title, entry = max(tagged, key=lambda t: t[1]["velocity_per_day"])
    return entry, title


_HERO_PLACEHOLDER = (
    "<div style=\"margin-top:24px; font-family:'Newsreader', serif; font-style:italic; "
    "font-size:15px; color:#71717a; padding:16px 0; border-top:1px solid #20222a; "
    "border-bottom:1px solid #20222a;\">"
    "No qualifying repos yet — the radar is still warming up.</div>"
)


def render_html_hero(top_mover: dict | None, bucket_title: str | None, now: datetime) -> str:
    """Render the hero card for the fastest-mover repo, or a placeholder.

    Args:
        top_mover:    Entry dict (global max velocity_per_day), or None.
        bucket_title: Title of the bucket top_mover was found in, or None.
        now:          UTC datetime for age calculation.

    Returns:
        HTML string: an <a> hero card, or an italic placeholder <div> when
        top_mover is None (all buckets empty — never crashes).
    """
    if top_mover is None:
        return _HERO_PLACEHOLDER

    owner, _, name = top_mover["full_name"].partition("/")
    owner = html.escape(owner, quote=True)
    name = html.escape(name, quote=True)
    url = html.escape(top_mover["html_url"], quote=True)
    desc = _esc(top_mover.get("description", ""))
    vel_fmt = _vel_fmt(top_mover["velocity_per_day"])
    stars_full = _stars_full(top_mover["stars"])
    age = _age_str(top_mover["created_at"], now)
    title = html.escape(bucket_title or "", quote=True)

    return f"""<a href="{url}" style="display:block; text-decoration:none; margin-top:24px; background:#111318; border:1px solid #23262f; border-radius:10px; padding:24px 26px;">
  <div style="font-family:'IBM Plex Mono', monospace; font-size:10.5px; letter-spacing:0.14em; text-transform:uppercase; color:#34d399; font-weight:600;">● Fastest mover · {title}</div>
  <div style="font-family:'Newsreader', serif; font-size:26px; font-weight:500; color:#f4f4f5; margin-top:11px; letter-spacing:-0.01em;">{owner}/{name}</div>
  <div style="font-family:'Newsreader', serif; font-size:15px; color:#9ca3af; line-height:1.5; margin-top:6px;">{desc}</div>
  <div style="display:flex; align-items:flex-end; margin-top:20px;">
    <span style="font-family:'Newsreader', serif; font-size:52px; font-weight:500; color:#34d399; line-height:0.85; letter-spacing:-0.02em;">{vel_fmt}</span>
    <span style="font-family:'IBM Plex Mono', monospace; font-size:10.5px; color:#71717a; text-transform:uppercase; letter-spacing:0.08em; padding-bottom:5px; margin-left:7px;">stars / day</span>
    <span style="margin-left:auto; font-family:'IBM Plex Mono', monospace; font-size:11px; color:#5b6573; padding-bottom:5px;">★ {stars_full} · {age}</span>
  </div>
</a>"""


def render_html_row(entry: dict, markers: dict, bucket_max_vel: float, now: datetime) -> str:
    """Render one repo row within a bucket section.

    NEW badge shown only when markers.get(str(entry["id"]), "new") == "new".

    Args:
        entry:          Entry dict.
        markers:        Dict mapping str(repo_id) -> "new" | "returning".
        bucket_max_vel: max(1.0, *velocities) for this bucket (bar scaling).
        now:            UTC datetime for age calculation.

    Returns:
        HTML string for one repo <a> row.
    """
    owner, _, name = entry["full_name"].partition("/")
    owner = html.escape(owner, quote=True)
    name = html.escape(name, quote=True)
    url = html.escape(entry["html_url"], quote=True)
    desc = _esc(entry.get("description", ""))
    velocity = entry["velocity_per_day"]
    vel_fmt = _vel_fmt(velocity)
    stars_full = _stars_full(entry["stars"])
    age = _age_str(entry["created_at"], now)
    bar_pct = _bar_pct(velocity, bucket_max_vel)
    bar_fill = _bar_fill(bar_pct)
    is_new = markers.get(str(entry["id"]), "new") == "new"
    new_badge = (
        "<span style=\"font-family:'IBM Plex Mono', monospace; font-size:9px; font-weight:600; "
        "letter-spacing:0.08em; color:#34d399; border:1px solid #2f6f55; padding:1px 6px; "
        "border-radius:99px; margin-left:9px;\">NEW</span>"
        if is_new
        else ""
    )

    return f"""<a href="{url}" style="display:flex; text-decoration:none; padding:12px 0; border-top:1px solid #16181d;">
  <div style="flex-shrink:0; width:78px; text-align:right; margin-right:16px;">
    <div style="font-family:'Newsreader', serif; font-size:26px; font-weight:500; color:#34d399; line-height:1; letter-spacing:-0.02em;">{vel_fmt}</div>
    <div style="font-family:'IBM Plex Mono', monospace; font-size:9px; letter-spacing:0.09em; text-transform:uppercase; color:#52525b; margin-top:3px;">stars / day</div>
  </div>
  <div style="flex:1;">
    <div style="display:flex; align-items:center;">
      <span style="font-family:'IBM Plex Sans', sans-serif; font-size:14px; font-weight:600; color:#f4f4f5;">{owner}/{name}</span>
      {new_badge}
    </div>
    <div style="font-family:'Newsreader', serif; font-size:14px; color:#9ca3af; line-height:1.45; margin-top:3px;">{desc}</div>
    <div style="display:flex; align-items:center; margin-top:8px;">
      <div style="flex:1; height:4px; background:#1a1d24; border-radius:3px; overflow:hidden;">
        <div style="height:100%; background: {bar_fill}; border-radius:3px; width: {bar_pct}%;"></div>
      </div>
      <span style="font-family:'IBM Plex Mono', monospace; font-size:10.5px; color:#5b6573; white-space:nowrap; margin-left:12px;">★ {stars_full} · {age}</span>
    </div>
  </div>
</a>"""


def render_html_bucket(
    bucket_key: str,
    kicker: str,
    title: str,
    bucket: dict,
    markers: dict,
    now: datetime,
) -> str:
    """Render one bucket section (kicker/title header + rows or empty message).

    Args:
        bucket_key: Bucket dict key (kept for symmetry with the
                    (key, kicker, title) tuples in _HTML_SECTIONS).
        kicker:     Small-caps section label (e.g. "Brand New · Weekly").
        title:      Section title (e.g. "Brand New This Week").
        bucket:     Bucket dict from compute_buckets.
        markers:    Markers dict passed through to render_html_row.
        now:        UTC datetime for age calculation.

    Returns:
        HTML string for the section <div>. Never raises: computes
        bucket_max_vel only when entries are present (an empty/inactive
        bucket renders its emptyMsg instead, with no division by zero).
    """
    del bucket_key  # unused directly; kept for interface symmetry
    active = bucket["active"]
    entries = bucket["entries"]

    count_label = f"{len(entries)} repos" if (active and entries) else "warming up"

    if not active:
        empty_msg = render_warming_note(bucket).strip("_")
    elif not entries:
        empty_msg = "No qualifying repos yet."
    else:
        empty_msg = None

    if empty_msg is not None:
        body = (
            "<div style=\"margin-top:14px; font-family:'Newsreader', serif; font-style:italic; "
            "font-size:15px; color:#71717a; padding:16px 0; border-top:1px solid #20222a; "
            f"border-bottom:1px solid #20222a;\">{html.escape(empty_msg)}</div>"
        )
    else:
        bucket_max_vel = max(1.0, *[e["velocity_per_day"] for e in entries])
        body = "\n".join(render_html_row(e, markers, bucket_max_vel, now) for e in entries)

    return f"""<div style="margin-top:34px;">
  <div style="display:flex; align-items:baseline;">
    <span style="font-family:'IBM Plex Mono', monospace; font-size:11px; letter-spacing:0.14em; text-transform:uppercase; color:#34d399; font-weight:600; margin-right:12px;">{html.escape(kicker)}</span>
    <span style="flex:1; height:1px; background:#20222a;"></span>
    <span style="font-family:'IBM Plex Mono', monospace; font-size:11px; color:#5b6573; margin-left:12px;">{count_label}</span>
  </div>
  <div style="font-family:'Newsreader', serif; font-size:24px; font-weight:500; color:#f4f4f5; margin-top:6px; letter-spacing:-0.01em;">{html.escape(title)}</div>
  {body}
</div>"""


def render_html_digest(buckets: dict, markers: dict, now: datetime) -> str:
    """Render the full "4a: The Dispatch, hero edition" HTML digest document.

    Self-contained: inline CSS only, a Google Fonts <link> (progressive
    enhancement — harmless if stripped by an email client), and no
    JavaScript. Same underlying bucket+markers data as write_digest's
    markdown output, rendered as a dark editorial-style email.

    Args:
        buckets: Dict from rank.compute_buckets (four-bucket contract).
        markers: Dict from seen.classify_and_update.
        now:     UTC datetime for the run.

    Returns:
        Full HTML document string. Never raises, even when every bucket is
        empty (renders a hero placeholder instead).
    """
    issue_no = buckets["brand_new_weekly"]["snapshots_available"]
    date_label = html.escape(now.strftime("%a · %d %b %Y"))

    top_mover, bucket_title = select_top_mover(buckets)
    hero_html = render_html_hero(top_mover, bucket_title, now)

    sections_html = "\n".join(
        render_html_bucket(key, kicker, title, buckets[key], markers, now)
        for key, kicker, title in _HTML_SECTIONS
    )

    fonts_link = (
        '<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;'
        "6..72,500;6..72,600&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:"
        'wght@400;500;600&display=swap" rel="stylesheet">'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Dispatch</title>
{fonts_link}
<style>
  body {{ margin:0; padding:0; background:#d8dadc; font-family:'IBM Plex Sans', -apple-system, 'Segoe UI', sans-serif; }}
</style>
</head>
<body style="margin:0; padding:0; background:#d8dadc;">
<div style="width:100%; padding:40px 0; display:flex; justify-content:center;">
<div style="width:620px; background:#0c0d10; border:1px solid #20222a; border-radius:4px; overflow:hidden; box-shadow:0 24px 60px -24px rgba(0,0,0,.55);">
<div style="padding:38px 44px 26px;">
<div style="display:flex; justify-content:space-between; align-items:baseline; font-family:'IBM Plex Mono', monospace; font-size:11px; letter-spacing:0.14em; text-transform:uppercase; color:#5b6573;">
<span>Issue No. {issue_no}</span><span style="margin-left:16px;">{date_label}</span>
</div>
<div style="font-family:'Newsreader', serif; font-size:46px; font-weight:500; color:#f4f4f5; line-height:1.0; margin-top:18px; letter-spacing:-0.015em;">The Dispatch</div>
<div style="font-family:'Newsreader', serif; font-size:16px; font-style:italic; color:#8b8f99; margin-top:8px;">What the open-source AI world is starring this week.</div>
{hero_html}
</div>
<div style="padding:0 44px 40px;">
{sections_html}
</div>
</div>
</div>
</body>
</html>
"""


def write_html_digest(
    buckets: dict,
    markers: dict,
    now: datetime,
    reports_dir: Path = config.REPORTS_DIR,
) -> Path:
    """Render the 4a HTML digest and write it to reports/YYYY-MM-DD.html.

    Mirrors write_digest's structure but for HTML; does NOT write or alter
    any .md file.

    Args:
        buckets:     Dict from rank.compute_buckets (four-bucket contract).
        markers:     Dict from seen.classify_and_update.
        now:         UTC datetime for the run; used to derive the date filename.
        reports_dir: Directory for output files. Created if absent.

    Returns:
        Path of the written HTML digest file.
    """
    date_str = now.strftime("%Y-%m-%d")
    document = render_html_digest(buckets, markers, now)

    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{date_str}.html"
    path.write_text(document, encoding="utf-8")
    return path
