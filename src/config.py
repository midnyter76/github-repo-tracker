"""FILTER-04 tunable constants for the GitHub Repo Tracker.

All filter parameters — topics, keywords, star floors, breakthrough star bands,
and path constants — live here per D-03. Import from this module to keep every
plan on a single source of truth. Never inline these values in search queries.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# AI Repo Filter — Topic Half (D-01, FILTER-01)
# ---------------------------------------------------------------------------
# Six LLM-era topics used in the topic-union search path.
# Each requires a separate `search_repositories()` call (GitHub topic: qualifier
# is AND-only; OR between topics requires separate queries merged client-side).
# No star floor on the topic half — topiced fresh repos must not be suppressed.
TOPICS = [
    "llm",
    "large-language-models",
    "agents",
    "rag",
    "generative-ai",
    "llmops",
]

# ---------------------------------------------------------------------------
# AI Repo Filter — Keyword Half (D-02, FILTER-01)
# ---------------------------------------------------------------------------
# Keyword fallback for repos that haven't set GitHub topics (often the freshest).
# Each sublist is a single query (max 5 OR/AND/NOT operators per GitHub query).
# Two sublists = two `search_repositories()` calls; results merged by repo.id.
KEYWORD_SETS = [
    ["llm", "gpt", "langchain", "transformer", "chatgpt"],
    ["openai", "claude", "gemini", '"language model"', "rag"],
]

# Search qualifier for keyword matching (name/description).
KEYWORD_IN_QUALIFIER = "in:name,description"

# Minimum star count for the topic half.
# Low floor suppresses 0-star placeholder repos while keeping fresh rockets.
# topic:llm alone returns 1000+ repos/week with no floor, burning search quota.
TOPIC_STAR_FLOOR: int = 5

# Minimum star count for the keyword half (D-02).
# Fresh-friendly low floor: prefer catching a 12-star day-2 rocket over noise.
KEYWORD_STAR_FLOOR = 10

# ---------------------------------------------------------------------------
# Shared Qualifiers (D-02, D-03, FILTER-03)
# ---------------------------------------------------------------------------
# Applied to BOTH the topic and keyword search halves.
QUALIFIER_EXCLUSIONS = "fork:false archived:false"

# ---------------------------------------------------------------------------
# Breakthrough Universe — Star Bands (D-11, Pattern 5a)
# ---------------------------------------------------------------------------
# Standing queries for established repos that may be spiking (Reading B).
# These catch OLD repos suddenly gaining stars, not just newly-created ones.
# Two bands keep total_count < 1,000 per slice (FILTER-02 / D-05).
BREAKTHROUGH_STAR_BANDS = ["100..1000", "1000..10000"]

# ---------------------------------------------------------------------------
# New-Repo Discovery Windows (D-04)
# ---------------------------------------------------------------------------
# Days for the `created:>DATE` qualifier used in date-windowed new-repo search.
# 7 = weekly (Brand New Top 10); 30 = monthly (Brand New Top 5).
NEW_REPO_WINDOWS = [7, 30]  # days

# ---------------------------------------------------------------------------
# Safety / Rate-Limit Thresholds (FILTER-02, Pitfall 2)
# ---------------------------------------------------------------------------
# Warn and narrow the search slice when total_count approaches the hard 1,000
# GitHub Search result cap. Threshold set below the cap to give headroom.
TOTAL_COUNT_CAP_WARN = 900  # < 1000 (hard GitHub search cap)

# ---------------------------------------------------------------------------
# File Paths (Pattern 9, DATA-02, DATA-03)
# ---------------------------------------------------------------------------
# Per-date snapshot files: data/snapshots/YYYY-MM-DD.json
# Keyed by str(repo.id) to survive renames/transfers.
SNAPSHOTS_DIR = Path("data/snapshots")

# Current metadata store — full overwrite each run (DATA-03).
METADATA_PATH = Path("data/metadata.json")

# ---------------------------------------------------------------------------
# Phase 2 — Ranking + Reporting
# ---------------------------------------------------------------------------

# Phase 2 paths (D-05, D-09)
REPORTS_DIR = Path("reports")
SEEN_PATH = Path("data") / "seen.json"

# Phase 2 ranking tunables (D-02, D-03, D-06)
BRAND_NEW_WEEKLY_DAYS = 7       # RANK-01 creation window
BRAND_NEW_WEEKLY_TOP = 10       # RANK-01 cap
BRAND_NEW_MONTHLY_DAYS = 30     # RANK-02 creation window
BRAND_NEW_MONTHLY_TOP = 5       # RANK-02 cap
SPIKE_TOP = 10                  # RANK-03 cap
VELOCITY_30D_TOP = 10           # RANK-04 cap
VELOCITY_30D_WINDOW_DAYS = 30   # RANK-04 widest window (D-06)
SPIKE_MIN_SNAPSHOTS = 2         # RANK-06: breakthrough activates at >=2 snapshots (D-06)

# Phase 2 safety floors / guards
AGE_HOURS_FLOOR = 1.0           # Pitfall 2: avoid div-by-zero for same-hour creation
STALE_SPIKE_HOURS = 30.0        # Pitfall 7: prior snapshot older than this => 24h bucket warms instead of mislabeling a multi-day delta
DESCRIPTION_MAX_CHARS = 120     # Pitfall 1: bullet-line truncation (used by Plan 03)

# ---------------------------------------------------------------------------
# Phase 3 — Production Hardening
# ---------------------------------------------------------------------------

# HARD-02: Gap detection
# Gap check fires when the last snapshot's captured_at is older than this.
# 26h gives 2h slack relative to the 24h run interval (D-05, CONTEXT.md).
GAP_WARN_HOURS: float = 26.0

# HARD-03: Star-gaming filters
# Only apply the ratio filter above GAMING_MIN_STARS.
# Repos below this threshold pass through unconditionally (avoids false positives
# on legitimate day-1 rockets with organic traction but no forks yet).
GAMING_MIN_STARS: int = 200           # [ASSUMED] — tune after first 30 days of data
# Stars-to-forks ratio above which a repo is flagged as likely gamed.
GAMING_STAR_FORK_RATIO: float = 50.0  # [ASSUMED] — tune after first 30 days of data

# HARD-04: Snapshot retention
# Files older than this are pruned by prune_snapshots(). 90 days = 3× the
# widest velocity window (30d), providing headroom for missed days + debugging.
SNAPSHOT_RETENTION_DAYS: int = 90    # D-08

# HARD-05: Metadata refresh age cap
# Only re-fetch star counts (core API) for repos created within this window.
# Older repos are always re-discovered fresh by discover_established() searches,
# so individual refreshes are redundant and blow past the 1,000 req/hr Actions limit.
# 45d = 30d velocity window + 15d buffer for missed runs / slow starters.
METADATA_REFRESH_MAX_AGE_DAYS: int = 45

# HARD-04-EXT: Tracked-repo eviction ledger
# Runtime ledger {str(repo_id): last-active YYYY-MM-DD}, created on first run by
# prune_metadata(). Additive-only file — never touches metadata.json's schema or
# seen.json's contracted dict shape (see PLAN <why_a_separate_ledger>).
TRACKED_LEDGER_PATH = Path("data/tracked_ledger.json")

# Repos absent from every ranked bucket for this many days are evicted from
# metadata.json by prune_metadata(). 14 gives a fresh repo two weeks to prove
# velocity, and discover_repos' 30d window re-finds any evicted repo that later
# spikes, so eviction never permanently loses a spike candidate.
METADATA_TRACKED_RETENTION_DAYS: int = 14
