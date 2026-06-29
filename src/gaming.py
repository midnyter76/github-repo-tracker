"""Star-gaming filter for GitHub Repo Tracker (HARD-03).

filter_gamed() silently removes repos that match gaming heuristics from the
candidate dict. Operates only on free search-response attributes (stargazers_count,
forks_count). Never logs, warns, or prints — gamed repos are silently excluded (D-07).

Free-attribute constraint (CRITICAL):
  Only `stargazers_count` and `forks_count` are safe to read without triggering
  a per-repo PyGithub lazy-fetch. Any other attribute (topics, subscribers_count,
  contributors) makes an extra API call per repo and blows the 30 req/min limit
  across 100–500 candidates. See RESEARCH.md Pattern 2 free-attribute whitelist.
"""

from src.config import GAMING_MIN_STARS, GAMING_STAR_FORK_RATIO


def filter_gamed(candidates: dict) -> dict:
    """Silently remove likely-gamed repos from candidate set (HARD-03, D-07).

    Heuristics applied only to repos above GAMING_MIN_STARS to avoid false positives
    on legitimate new repos that haven't attracted forks yet.

    Heuristic:
        stars >= GAMING_MIN_STARS AND (forks == 0 OR stars/forks > GAMING_STAR_FORK_RATIO)
        → excluded (likely gamed)

    Args:
        candidates: Dict mapping str(repo_id) to PyGithub repo objects. NOT mutated.

    Returns:
        New dict with gamed repos removed. Original `candidates` is unchanged.
    """
    clean = {}
    for rid, repo in candidates.items():
        stars = repo.stargazers_count
        forks = repo.forks_count

        # Repos below the star floor pass unconditionally (avoids false positives
        # on legitimate day-1 rockets that organically haven't attracted forks yet).
        if stars < GAMING_MIN_STARS:
            clean[rid] = repo
            continue

        # Above the floor: apply ratio filter.
        # Zero-fork guard: ratio = inf when forks == 0 (new legit repos below floor
        # are already passed above; a high-star zero-fork repo is suspicious).
        ratio = stars / forks if forks > 0 else float("inf")
        if ratio <= GAMING_STAR_FORK_RATIO:
            clean[rid] = repo
        # else: silently drop — no print, no log, no digest marker (D-07)

    return clean
