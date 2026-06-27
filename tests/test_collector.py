"""Tests for src/collector.py (Plan 01-04).

Task 1: build_client, run orchestration, token safety, entry-point gate.
Task 2: workflow YAML content assertions.

All tests are offline (no network). The entry-point gate spawns a subprocess
to verify that `python -m src.collector` resolves imports identically to pytest.
"""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Task 1: build_client
# ---------------------------------------------------------------------------

class TestBuildClient:
    """build_client() reads GITHUB_TOKEN from env and constructs the Github client."""

    def test_returns_github_client_using_env_token(self):
        """Happy path: env var present -> constructs Github with correct auth."""
        with (
            patch("github.Auth.Token") as mock_auth_token,
            patch("github.GithubRetry") as mock_retry_cls,
            patch("github.Github") as mock_github_cls,
        ):
            mock_auth = MagicMock()
            mock_auth_token.return_value = mock_auth
            mock_retry = MagicMock()
            mock_retry_cls.return_value = mock_retry

            with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_fake_token"}):
                from src.collector import build_client  # noqa: PLC0415
                result = build_client()

            # Auth.Token must be called with the token value from env
            mock_auth_token.assert_called_once_with("ghp_fake_token")
            # Github must be called with retry and seconds_between_requests
            mock_github_cls.assert_called_once_with(
                auth=mock_auth,
                retry=mock_retry,
                seconds_between_requests=0.5,
            )
            assert result is mock_github_cls.return_value

    def test_raises_runtime_error_when_token_missing(self):
        """Missing GITHUB_TOKEN raises RuntimeError — message must NOT echo a value."""
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_TOKEN"}
        with patch.dict(os.environ, env, clear=True):
            from src.collector import build_client  # noqa: PLC0415
            with pytest.raises(RuntimeError, match="GITHUB_TOKEN not set"):
                build_client()

    def test_error_message_contains_no_token_value(self):
        """RuntimeError message must not echo any token-like value (Pitfall 4)."""
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_TOKEN"}
        with patch.dict(os.environ, env, clear=True):
            from src.collector import build_client  # noqa: PLC0415
            with pytest.raises(RuntimeError) as exc_info:
                build_client()
        # The message should identify WHAT is missing but echo no value
        msg = str(exc_info.value)
        assert "GITHUB_TOKEN" in msg
        # Must not contain any suspicious-looking token-format strings
        assert "ghp_" not in msg
        assert "=" not in msg or "not set" in msg  # "not set" is fine; stray = is not


# ---------------------------------------------------------------------------
# Task 1: run() orchestration
# ---------------------------------------------------------------------------

class TestRun:
    """run() calls all discovery/refresh/persistence functions in the right order."""

    def _make_fake_repo(self, repo_id: str, stars: int = 100):
        r = MagicMock()
        r.id = int(repo_id)
        r.stargazers_count = stars
        r.full_name = f"owner/repo-{repo_id}"
        r.description = f"Repo {repo_id}"
        r.html_url = f"https://github.com/owner/repo-{repo_id}"
        r.created_at.isoformat.return_value = "2026-01-01T00:00:00+00:00"
        return r

    def test_calls_all_discovery_and_persistence_functions(self):
        """run() calls discover, established, load_ids, refresh, write_snap, write_meta."""
        from datetime import datetime, timezone  # noqa: PLC0415
        from src.collector import run  # noqa: PLC0415

        g = MagicMock()
        now = datetime(2026, 6, 27, 13, 0, 0, tzinfo=timezone.utc)

        repo_a = self._make_fake_repo("111", stars=50)
        repo_b = self._make_fake_repo("222", stars=80)
        repo_c = self._make_fake_repo("333", stars=120)
        repo_d = self._make_fake_repo("444", stars=200)

        mock_discover = MagicMock(return_value={"111": repo_a})
        mock_established = MagicMock(return_value={"222": repo_b})
        mock_load_ids = MagicMock(return_value=["333", "444"])
        mock_refresh = MagicMock(return_value={"333": repo_c, "444": repo_d})
        mock_write_snap = MagicMock()
        mock_write_meta = MagicMock()

        run(
            g,
            now,
            discover=mock_discover,
            established=mock_established,
            load_ids=mock_load_ids,
            refresh=mock_refresh,
            write_snap=mock_write_snap,
            write_meta=mock_write_meta,
        )

        mock_discover.assert_called_once_with(g)
        mock_established.assert_called_once_with(g)
        mock_load_ids.assert_called_once_with()
        mock_refresh.assert_called_once_with(g, ["333", "444"])
        mock_write_snap.assert_called_once()
        mock_write_meta.assert_called_once()

    def test_union_contains_all_ids_from_all_sources(self):
        """Candidates passed to write_snap/write_meta contain all ids from all sources."""
        from datetime import datetime, timezone  # noqa: PLC0415
        from src.collector import run  # noqa: PLC0415

        g = MagicMock()
        now = datetime(2026, 6, 27, 13, 0, 0, tzinfo=timezone.utc)

        repo_a = self._make_fake_repo("111")
        repo_b = self._make_fake_repo("222")
        repo_c = self._make_fake_repo("333")

        captured_snap = {}
        captured_meta = {}

        def fake_write_snap(candidates, ts):
            captured_snap.update(candidates)

        def fake_write_meta(candidates, ts):
            captured_meta.update(candidates)

        run(
            g,
            now,
            discover=lambda _g: {"111": repo_a},
            established=lambda _g: {"222": repo_b},
            load_ids=lambda: ["333"],
            refresh=lambda _g, _ids: {"333": repo_c},
            write_snap=fake_write_snap,
            write_meta=fake_write_meta,
        )

        assert "111" in captured_snap
        assert "222" in captured_snap
        assert "333" in captured_snap
        assert "111" in captured_meta
        assert "222" in captured_meta
        assert "333" in captured_meta

    def test_refresh_overrides_earlier_discovery(self):
        """Refresh runs LAST so re-fetched star counts override discovery stubs."""
        from datetime import datetime, timezone  # noqa: PLC0415
        from src.collector import run  # noqa: PLC0415

        g = MagicMock()
        now = datetime(2026, 6, 27, 13, 0, 0, tzinfo=timezone.utc)

        # Repo "111" appears in both discover and refresh with different star counts
        repo_discover = self._make_fake_repo("111", stars=50)
        repo_refresh = self._make_fake_repo("111", stars=999)  # fresher

        captured = {}

        def fake_write_snap(candidates, ts):
            captured.update(candidates)

        run(
            g,
            now,
            discover=lambda _g: {"111": repo_discover},
            established=lambda _g: {},
            load_ids=lambda: ["111"],
            refresh=lambda _g, _ids: {"111": repo_refresh},
            write_snap=fake_write_snap,
            write_meta=MagicMock(),
        )

        # The refreshed repo (999 stars) must win
        assert captured["111"] is repo_refresh

    def test_write_functions_receive_now_timestamp(self):
        """write_snap and write_meta are called with the 'now' datetime."""
        from datetime import datetime, timezone  # noqa: PLC0415
        from src.collector import run  # noqa: PLC0415

        g = MagicMock()
        now = datetime(2026, 6, 27, 13, 0, 0, tzinfo=timezone.utc)

        mock_write_snap = MagicMock()
        mock_write_meta = MagicMock()

        run(
            g,
            now,
            discover=lambda _g: {},
            established=lambda _g: {},
            load_ids=lambda: [],
            refresh=lambda _g, _ids: {},
            write_snap=mock_write_snap,
            write_meta=mock_write_meta,
        )

        _, snap_ts = mock_write_snap.call_args[0]
        _, meta_ts = mock_write_meta.call_args[0]
        assert snap_ts is now
        assert meta_ts is now


# ---------------------------------------------------------------------------
# Task 1: Token safety grep gate (static analysis of collector.py source)
# ---------------------------------------------------------------------------

class TestTokenSafety:
    """Collector source must not echo the token in any print/log statement."""

    def _get_collector_source(self) -> str:
        p = Path(__file__).parent.parent / "src" / "collector.py"
        return p.read_text()

    def test_os_environ_referenced_exactly_once(self):
        """GITHUB_TOKEN must be read exactly once — no redundant env references."""
        src = self._get_collector_source()
        # Count all occurrences of os.environ
        count = src.count('os.environ')
        assert count == 1, (
            f"Expected 1 occurrence of 'os.environ' in collector.py, found {count}"
        )

    def test_no_print_of_token_or_env(self):
        """No print() call that references token, auth, or os.environ (Pitfall 4)."""
        import re  # noqa: PLC0415
        src = self._get_collector_source()
        # Case-insensitive: print( ... token ... ) or similar
        bad = re.search(r'print\s*\(.*(?:token|os\.environ|auth)', src, re.IGNORECASE)
        assert bad is None, f"Found suspicious print: {bad.group()}"

    def test_github_auth_token_call_present(self):
        """build_client must use github.Auth.Token (Pattern 1 / D-09)."""
        src = self._get_collector_source()
        assert "github.Auth.Token" in src

    def test_seconds_between_requests_present(self):
        """build_client must pass seconds_between_requests=0.5 (Pattern 1)."""
        src = self._get_collector_source()
        assert "seconds_between_requests=0.5" in src

    def test_github_retry_present(self):
        """build_client must use GithubRetry (Pattern 1)."""
        src = self._get_collector_source()
        assert "GithubRetry" in src

    def test_utc_timestamp_present(self):
        """main() must stamp run_at with datetime.now(timezone.utc) (D-07)."""
        src = self._get_collector_source()
        assert "datetime.now(timezone.utc)" in src

    def test_module_entry_point_present(self):
        """collector.py must have __main__ guard (module entry point)."""
        src = self._get_collector_source()
        assert 'if __name__ == "__main__"' in src


# ---------------------------------------------------------------------------
# Task 1: Entry-point subprocess gate
# ---------------------------------------------------------------------------

class TestEntryPoint:
    """python -m src.collector with no token must raise GITHUB_TOKEN error, not import error."""

    def test_no_module_not_found_error_on_missing_token(self):
        """Imports resolve correctly when invoked as a module; missing token gives RuntimeError."""
        # Build env with PATH preserved but no GITHUB_TOKEN
        e = dict(os.environ)
        e.pop("GITHUB_TOKEN", None)

        result = subprocess.run(
            [sys.executable, "-m", "src.collector"],
            capture_output=True,
            text=True,
            env=e,
        )

        combined = result.stdout + result.stderr
        assert "GITHUB_TOKEN not set" in combined, (
            f"Expected 'GITHUB_TOKEN not set' in output.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )
        assert "ModuleNotFoundError" not in combined, (
            f"Got ModuleNotFoundError — imports failed under -m invocation.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )


# ---------------------------------------------------------------------------
# Task 2: Workflow YAML content assertions
# ---------------------------------------------------------------------------

class TestWorkflowYaml:
    """daily.yml must contain all required strings (AUTO-01, AUTO-02, AUTO-03)."""

    def _get_workflow_text(self) -> str:
        p = Path(__file__).parent.parent / ".github" / "workflows" / "daily.yml"
        assert p.exists(), f"Workflow file not found: {p}"
        return p.read_text()

    def test_cron_schedule(self):
        """Workflow must have the D-06 cron schedule."""
        assert "cron: '0 13 * * *'" in self._get_workflow_text()

    def test_workflow_dispatch_present(self):
        """Workflow must have workflow_dispatch for manual trigger."""
        assert "workflow_dispatch" in self._get_workflow_text()

    def test_contents_write_permission(self):
        """Workflow must declare contents: write (AUTO-03 minimal scope)."""
        assert "contents: write" in self._get_workflow_text()

    def test_token_injected_from_secret(self):
        """GITHUB_TOKEN must be injected from secrets, never hardcoded (AUTO-02)."""
        assert "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}" in self._get_workflow_text()

    def test_module_invocation(self):
        """Workflow must invoke the module form, not the path form (entry-point rule)."""
        assert "uv run python -m src.collector" in self._get_workflow_text()

    def test_auto_commit_action_version(self):
        """git-auto-commit-action must be pinned to v5 (CLAUDE.md stack)."""
        assert "stefanzweifel/git-auto-commit-action@v5" in self._get_workflow_text()

    def test_skip_ci_in_commit_message(self):
        """Commit message must include [skip ci] to prevent self-trigger (D-10)."""
        assert "[skip ci]" in self._get_workflow_text()

    def test_file_pattern_data(self):
        """git-auto-commit-action must commit only data/** files (AUTO-03)."""
        assert 'file_pattern: "data/**"' in self._get_workflow_text()

    def test_no_token_echo_in_run_steps(self):
        """No run: step echoes the token or the secrets context (Pitfall 4)."""
        import re  # noqa: PLC0415
        text = self._get_workflow_text()
        bad = re.search(r'run:.*(?:echo|print).*(?:token|secrets)', text, re.IGNORECASE)
        assert bad is None, f"Found token echo in run step: {bad.group()}"
