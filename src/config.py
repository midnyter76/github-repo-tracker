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

# Minimum star count for the keyword half (D-02).
# Fresh-friendly low floor: prefer catching a 12-star day-2 rocket over noise.
# The topic half intentionally has NO floor.
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
