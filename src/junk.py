"""Jailbreak/blank-junk filter for GitHub Repo Tracker (FILTER-JUNK-01).

filter_junk() silently removes repos with jailbreak-keyword or blank descriptions
from the candidate dict. Operates only on the free search-response attribute
`description` (store.py:115). Never logs, warns, or prints — junk repos are
silently excluded, mirroring filter_gamed / D-07.

Free-attribute constraint (CRITICAL):
  Only `description` is safe to read without triggering a per-repo PyGithub
  lazy-fetch. Any other attribute (topics, owner, subscribers_count) makes an
  extra API call per repo and blows the 30 req/min limit across 100-500 candidates.
"""

from src.config import EXCLUDE_BLANK_DESCRIPTION, JUNK_KEYWORDS


def filter_junk(candidates: dict) -> dict:
    """Silently drop jailbreak/blank-junk repos (FILTER-JUNK-01).

    Args:
        candidates: Dict mapping str(repo_id) to PyGithub repo objects. NOT mutated.

    Returns:
        New dict with junk repos removed. Original `candidates` is unchanged.
    """
    clean = {}
    for rid, repo in candidates.items():
        desc = (repo.description or "").lower()
        if EXCLUDE_BLANK_DESCRIPTION and not desc:
            continue
        if any(kw in desc for kw in JUNK_KEYWORDS):
            continue
        clean[rid] = repo
    return clean
