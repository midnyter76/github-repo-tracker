---
phase: "01-collection-loop"
plan: "01"
subsystem: "scaffold"
tags: ["python", "uv", "pygithub", "config", "tdd", "filter-constants"]
dependency_graph:
  requires: []
  provides: ["src/config.py", "pyproject.toml", "uv.lock", "data/snapshots/"]
  affects: ["src/search.py (Plan 02)", "src/store.py (Plan 03)", ".github/workflows/ (Plan 04)"]
tech_stack:
  added: ["Python 3.12", "PyGithub 2.9.1", "pytest 9.1.1", "uv 0.11.25"]
  patterns: ["per-date JSON snapshots", "configurable constants in src/config.py", "numeric repo.id keying"]
key_files:
  created:
    - "pyproject.toml"
    - "uv.lock"
    - ".python-version"
    - ".gitignore"
    - "src/__init__.py"
    - "src/config.py"
    - "tests/__init__.py"
    - "tests/test_config.py"
    - "data/snapshots/.gitkeep"
  modified: []
decisions:
  - "Named project 'github-repo-tracker' in pyproject.toml (correcting uv init default of worktree name)"
  - "Installed uv 0.11.25 via astral.sh installer (not pre-installed on machine — Rule 3 auto-fix)"
  - "Used .as_posix() in path assertions to avoid Windows backslash mismatch in tests"
  - "Added [tool.pytest.ini_options] not needed — src/__init__.py presence sufficient for src.config import resolution"
metrics:
  duration: "~3 minutes"
  completed: "2026-06-27"
  tasks_completed: 3
  files_created: 9
---

# Phase 01 Plan 01: Project Scaffold and Config Constants Summary

uv project initialized with Python 3.12, PyGithub==2.9.1 pinned, pytest harness runnable, and all FILTER-04 tunable constants centralized in `src/config.py` with 8 passing tests.

## What Was Built

### Task 1: uv project scaffold
- `pyproject.toml` with `requires-python = ">=3.12"`, `PyGithub==2.9.1` runtime dep, `pytest` dev dep
- `uv.lock` committed for reproducible CI installs (not gitignored)
- `.python-version` pinned to `3.12`
- `.gitignore` with `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`

### Task 2: src/config.py constants module (TDD)
All D-01/02/03/04/11 constants implemented as module-level literals in `src/config.py`:
- `TOPICS` — 6 LLM-era topics in exact order (D-01)
- `KEYWORD_SETS` — two keyword sublists, max 5 terms each (D-02, Pattern 5 operator cap)
- `KEYWORD_STAR_FLOOR = 10` — fresh-friendly low floor (D-02)
- `KEYWORD_IN_QUALIFIER = "in:name,description"` (FILTER-01)
- `QUALIFIER_EXCLUSIONS = "fork:false archived:false"` (D-03/FILTER-03)
- `BREAKTHROUGH_STAR_BANDS = ["100..1000", "1000..10000"]` (D-11/Pattern 5a)
- `NEW_REPO_WINDOWS = [7, 30]` — weekly + monthly creation windows (D-04)
- `TOTAL_COUNT_CAP_WARN = 900` — warn threshold below 1,000 hard cap (FILTER-02)
- `SNAPSHOTS_DIR = Path("data/snapshots")`, `METADATA_PATH = Path("data/metadata.json")` (Pattern 9)

8/8 tests in `tests/test_config.py` pass green.

### Task 3: data/snapshots directory
`data/snapshots/.gitkeep` ensures the directory is tracked from day 1 so the first
scheduled run can write `data/snapshots/YYYY-MM-DD.json` without a missing-directory error.
`data/metadata.json` intentionally NOT pre-created (written at runtime by Plan 03).

## Commits

| Task | Commit | Type | Description |
|------|--------|------|-------------|
| Task 1 | d3c7b7f | chore | Initialize uv project with Python 3.12 and PyGithub 2.9.1 |
| Task 2 RED | c77fad2 | test | Add failing tests for config constants (FILTER-04) |
| Task 2 GREEN | ffb7b82 | feat | Implement src/config.py FILTER-04 constants module |
| Task 3 | 5ed0c12 | chore | Add data/snapshots/.gitkeep to track directory in git |

## TDD Gate Compliance

- RED gate: `test(01-01)` commit c77fad2 — 8 tests fail with ModuleNotFoundError (src/config.py absent)
- GREEN gate: `feat(01-01)` commit ffb7b82 — 8 tests pass after config.py created
- REFACTOR: no structural cleanup needed; constants are literals

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] uv not installed on machine**
- **Found during:** Task 1 setup
- **Issue:** `uv` not in PATH; mandated by CLAUDE.md but not pre-installed
- **Fix:** Installed uv 0.11.25 via `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Files modified:** None (system install)
- **Commit:** d3c7b7f (prerequisite)

**2. [Rule 1 - Bug] pyproject.toml project name and PyGithub capitalization**
- **Found during:** Task 1
- **Issue:** `uv init` defaulted project name to worktree ID (`agent-a5ee9018152f9b06e`) and normalized PyGithub to lowercase `pygithub==2.9.1`, failing the acceptance criterion `grep -F "PyGithub==2.9.1" pyproject.toml`
- **Fix:** Edited pyproject.toml to set `name = "github-repo-tracker"` and `PyGithub==2.9.1`
- **Files modified:** pyproject.toml
- **Commit:** d3c7b7f

**3. [Rule 2 - Windows path safety] Path assertions use .as_posix()**
- **Found during:** Task 2 test writing
- **Issue:** `str(Path("data/snapshots"))` on Windows returns `data\snapshots`, not `data/snapshots`; `.endswith("data/snapshots")` would fail at runtime
- **Fix:** Tests use `SNAPSHOTS_DIR.as_posix().endswith(...)` and `METADATA_PATH.as_posix().endswith(...)` instead of `str()` comparison
- **Files modified:** tests/test_config.py
- **Commit:** c77fad2

## Verification Results

- `uv run pytest -q`: 8 passed in 0.02s
- `uv run python -c "from github import Github; print('ok')"`: passes
- No literal token values in committed files (ghp_/github_pat_ grep returns only plan documentation)
- `data/snapshots/.gitkeep` tracked; `data/metadata.json` absent

## Known Stubs

None — this plan contains only configuration constants, tests, and scaffolding. No data-rendering or API paths exist yet.

## Threat Surface Scan

No new threat surface introduced beyond what the plan's threat model covered (T-01-01, T-01-02, T-01-03). No network endpoints, auth paths, or file access patterns were added in this scaffold plan.

## Self-Check: PASSED

Files:
- FOUND: src/config.py
- FOUND: pyproject.toml
- FOUND: uv.lock
- FOUND: .python-version
- FOUND: .gitignore
- FOUND: src/__init__.py
- FOUND: tests/__init__.py
- FOUND: tests/test_config.py
- FOUND: data/snapshots/.gitkeep

Commits (all verified in git log):
- FOUND: d3c7b7f chore(01-01): initialize uv project
- FOUND: c77fad2 test(01-01): add failing tests
- FOUND: ffb7b82 feat(01-01): implement config constants
- FOUND: 5ed0c12 chore(01-01): add data/snapshots/.gitkeep
