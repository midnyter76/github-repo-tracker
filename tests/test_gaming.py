"""Tests for src/gaming.py — star-gaming filter (HARD-03).

Covers:
- filter_gamed: empty input → empty output
- filter_gamed: repos below GAMING_MIN_STARS pass unconditionally (zero-fork safe)
- filter_gamed: ratio at threshold boundary (kept)
- filter_gamed: ratio above threshold (removed)
- filter_gamed: zero-fork high-star repo (removed — ratio = inf)
- filter_gamed: does not mutate input dict
- filter_gamed: produces no stdout/stderr output (D-07)
"""
import types


def _make_repo(repo_id: int, stars: int, forks: int) -> types.SimpleNamespace:
    """Minimal fake repo object with the free search-response attributes used by filter_gamed.

    IMPORTANT: Must include forks_count — test_store.py's _make_repo omits it,
    which would cause AttributeError in filter_gamed (it reads repo.forks_count).
    """
    return types.SimpleNamespace(
        id=repo_id,
        stargazers_count=stars,
        forks_count=forks,
    )


class TestFilterGamed:
    def test_empty_candidates_returns_empty(self):
        """filter_gamed({}) returns {}."""
        from src.gaming import filter_gamed

        assert filter_gamed({}) == {}

    def test_below_floor_passes_unconditionally_zero_forks(self):
        """Repos with stars < GAMING_MIN_STARS (200) pass regardless of fork count."""
        from src.gaming import filter_gamed

        repo = _make_repo(repo_id=1, stars=50, forks=0)
        result = filter_gamed({"1": repo})
        assert "1" in result, "Low-star repo with 0 forks must NOT be filtered"

    def test_ratio_at_threshold_kept(self):
        """Repos with ratio == GAMING_STAR_FORK_RATIO are kept (boundary: not strictly greater)."""
        from src.gaming import filter_gamed
        from src.config import GAMING_MIN_STARS, GAMING_STAR_FORK_RATIO

        # stars / forks == exactly GAMING_STAR_FORK_RATIO (50.0): should be kept
        forks = 10
        stars = int(GAMING_STAR_FORK_RATIO * forks)  # 500 stars, 10 forks → ratio = 50.0
        assert stars >= GAMING_MIN_STARS, "Test setup: stars must exceed floor"
        repo = _make_repo(repo_id=2, stars=stars, forks=forks)
        result = filter_gamed({"2": repo})
        assert "2" in result, f"Ratio exactly at threshold ({GAMING_STAR_FORK_RATIO}) should be kept"

    def test_high_ratio_removed(self):
        """Repos with ratio > GAMING_STAR_FORK_RATIO and stars >= GAMING_MIN_STARS are removed."""
        from src.gaming import filter_gamed

        # stars=600, forks=3 → ratio=200.0 > 50.0 → gamed
        repo = _make_repo(repo_id=3, stars=600, forks=3)
        result = filter_gamed({"3": repo})
        assert "3" not in result, "High-ratio high-star repo must be filtered"

    def test_zero_forks_high_stars_removed(self):
        """Repos with 0 forks AND stars >= GAMING_MIN_STARS are removed (ratio = inf)."""
        from src.gaming import filter_gamed

        repo = _make_repo(repo_id=4, stars=300, forks=0)
        result = filter_gamed({"4": repo})
        assert "4" not in result, "Zero-fork high-star repo must be filtered (ratio = inf)"

    def test_does_not_mutate_input(self):
        """filter_gamed returns a new dict; input candidates is unchanged."""
        from src.gaming import filter_gamed

        repo = _make_repo(repo_id=5, stars=600, forks=3)
        original = {"5": repo}
        original_copy = dict(original)
        filter_gamed(original)
        assert original == original_copy, "filter_gamed must not mutate the input dict"

    def test_no_output_produced(self, capsys):
        """filter_gamed produces no stdout or stderr output (D-07: silent exclusion)."""
        from src.gaming import filter_gamed

        repo_kept = _make_repo(repo_id=6, stars=50, forks=5)
        repo_filtered = _make_repo(repo_id=7, stars=600, forks=3)
        filter_gamed({"6": repo_kept, "7": repo_filtered})
        captured = capsys.readouterr()
        assert captured.out == "", "filter_gamed must produce no stdout"
        assert captured.err == "", "filter_gamed must produce no stderr"
