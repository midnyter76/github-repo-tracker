"""Tests for src/junk.py — jailbreak/blank-junk filter (FILTER-JUNK-01).

Covers:
- filter_junk: blank description ("" and None) excluded when EXCLUDE_BLANK_DESCRIPTION is True
- filter_junk: jailbreak-keyword description excluded (Chinese deny-list term)
- filter_junk: legit description passes through unchanged (control)
- filter_junk: does not mutate input dict
"""
import types


def _make_repo(repo_id: int, description) -> types.SimpleNamespace:
    """Minimal fake repo object exposing the free search-response attribute
    used by filter_junk (mirrors test_gaming.py's _make_repo style)."""
    return types.SimpleNamespace(
        id=repo_id,
        description=description,
    )


class TestFilterJunk:
    def test_blank_string_description_excluded(self):
        """Repo with description="" is dropped when EXCLUDE_BLANK_DESCRIPTION is True."""
        from src.junk import filter_junk

        repo = _make_repo(repo_id=1, description="")
        result = filter_junk({"1": repo})
        assert "1" not in result, "Blank string description must be filtered"

    def test_none_description_excluded(self):
        """Repo with description=None is dropped when EXCLUDE_BLANK_DESCRIPTION is True."""
        from src.junk import filter_junk

        repo = _make_repo(repo_id=2, description=None)
        result = filter_junk({"2": repo})
        assert "2" not in result, "None description must be filtered"

    def test_jailbreak_keyword_excluded(self):
        """Repo whose description matches the recurring jailbreak example is dropped."""
        from src.junk import filter_junk

        repo = _make_repo(
            repo_id=3,
            description="Codex CLI 破甲工具（GPT-5.5）— 注入无限制模式系统指令，关闭所有内容过滤器。",
        )
        result = filter_junk({"3": repo})
        assert "3" not in result, "Jailbreak-keyword description must be filtered"

    def test_legit_description_passes_through(self):
        """Repo with a normal description is retained unchanged."""
        from src.junk import filter_junk

        repo = _make_repo(repo_id=4, description="A fast RAG framework for building LLM agents")
        result = filter_junk({"4": repo})
        assert "4" in result, "Legit description must NOT be filtered"
        assert result["4"] is repo

    def test_does_not_mutate_input(self):
        """filter_junk returns a new dict; input candidates is unchanged."""
        from src.junk import filter_junk

        repo = _make_repo(repo_id=5, description="")
        original = {"5": repo}
        original_copy = dict(original)
        filter_junk(original)
        assert original == original_copy, "filter_junk must not mutate the input dict"
