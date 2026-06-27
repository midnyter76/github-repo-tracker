# Phase 1: Collection Loop - Context

**Gathered:** 2026-06-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver the daily **fetch → snapshot → commit-back** loop running in GitHub Actions, so star-count history begins accumulating on day 1. Scope: query the GitHub Search API for AI repos, write an idempotent per-date snapshot keyed by numeric `repo.id`, persist it (plus repo metadata) by committing back to the repo, all on a daily cron with the token injected from an Actions secret.

In scope: DATA-01..05, FILTER-01..04, AUTO-01..03.
Out of scope (later phases): velocity ranking + the four buckets (Phase 2), markdown digest formatting (Phase 2), scheduler hardening / gap detection / star-gaming filters / pruning (Phase 3).

</domain>

<decisions>
## Implementation Decisions

### AI Filter Definition (FILTER-01, FILTER-03, FILTER-04)
- **D-01:** Topic-union half anchors on **LLM-era topics**: `topic:llm`, `topic:large-language-models`, `topic:agents`, `topic:rag`, `topic:generative-ai`, `topic:llmops`. Deliberately narrower than broad AI/ML to match the "AI tooling" core value and cut tutorial/course noise. (Classic-ML-only breakouts are an accepted blind spot.)
- **D-02:** Keyword-fallback half is **fresh-friendly with a low star floor (`stars:>=10`)**, querying AI terms in name/description for repos that haven't set topics — these are often the freshest repos and the whole point of an early radar. Accepts more noise in exchange for not missing day-2 rockets.
- **D-03:** Topic and keyword lists are **configurable constants** (FILTER-04), not inline — so the floor and term lists can be tuned after real data arrives. Both query halves exclude `fork:false archived:false`; the star floor applies to the keyword half (topic half stays floor-free so topiced fresh repos aren't suppressed).

### Collection Breadth (FILTER-02)
- **D-04:** Target a **focused tracked universe of ~150–300 repos**. New-repo windows are the required `last 7d` and `last 30d` slices; breakthrough universe (re-fetched daily) stays ~200. This sits comfortably under GITHUB_TOKEN's 1,000 core-req/hr ceiling — no PAT needed — and keeps runs fast and signal high.
- **D-05:** Each search sub-query stays **date-windowed (and star-banded where needed) to keep `total_count` under the 1,000-result search cap** (FILTER-02). Exact slice boundaries are a research/planning detail.

### Run Schedule (AUTO-01)
- **D-06:** Cron fires at **`'0 13 * * *'` (13:00 UTC = 6am PDT / 5am PST)** so the snapshot is fresh before the user's Pacific morning. Pacific clock time shifts 1h across DST since cron is fixed-UTC — accepted, because velocity is hour-normalized downstream (RANK-05, Phase 2).
- **D-07:** All stored timestamps are **UTC ISO 8601** (DATA-05). Phase 1 only stores timestamps; the 24h/30d diffing that consumes them lands in Phase 2.

### Hosting / Deploy Target (AUTO-02, AUTO-03)
- **D-08:** Lives in a **dedicated public GitHub repo** (`github-repo-tracker`). Free unlimited Actions minutes, digest publicly browsable/linkable on any device, forkable later. No leak risk — all inputs are public GitHub metadata.
- **D-09:** Auth uses the **built-in `GITHUB_TOKEN`** (zero setup, 1k core req/hr — sufficient at this breadth) with `contents: write` permission. No PAT. Token injected from the Actions context, never committed or echoed (AUTO-02).
- **D-10:** The **repo is also the datastore** — snapshots, metadata, and seen-store are committed back each run (AUTO-03) via `stefanzweifel/git-auto-commit-action`, with `[skip ci]` on the commit to avoid self-triggering the workflow.

### Breakthrough Universe (resolves RESEARCH.md Open Q#3)
- **D-11:** Universe uses a **star-banded standing query (Reading B)** — a `discover_established()` pass queries repos by star bands regardless of creation date, in addition to the date-windowed new-repo slices. This catches OLD repos that are suddenly spiking (sleeper breakouts), not just newly-created ones — matching the core value "catch exploding AI repos early." Accepts the extra search-call / rate budget. (Reading A, rolling-accumulation-only, was rejected: date-windowed queries can't see old-but-spiking repos.)

### Claude's Discretion
- Exact keyword strings in the fallback list, precise date/star slice boundaries, snapshot vs metadata field split, and same-day idempotency mechanics (DATA-04) are left to research/planning — the vision-level dials above constrain them.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project planning docs
- `.planning/PROJECT.md` — core value, constraints, Key Decisions table (Python / snapshots / markdown / Actions cron / AI-filter strategy / dedup).
- `.planning/REQUIREMENTS.md` §Data Collection & Storage, §AI Repo Filtering, §Automation — the DATA / FILTER / AUTO requirement text this phase implements.
- `.planning/ROADMAP.md` §"Phase 1: Collection Loop" — goal + the 5 success criteria that must be TRUE.

### Tech stack (already researched — authoritative)
- `CLAUDE.md` §Technology Stack — locked stack with versions and rationale: Python 3.12, **PyGithub 2.9.1** (`Github(retry=github.GithubRetry(), seconds_between_requests=0.5)`), **uv** via `astral-sh/setup-uv@v8`, `actions/checkout@v4`, `stefanzweifel/git-auto-commit-action@v5`.
- `CLAUDE.md` §"What NOT to Use" — key landmines: **key snapshots by numeric `repo.id`, never `owner/repo`** (rename/transfer breaks continuity); **per-date JSON files `data/snapshots/YYYY-MM-DD.json`, never a monolithic file**; no `tenacity`/`requests` (PyGithub covers retry); slice searches to stay under the 1,000-result cap.
- `CLAUDE.md` §"GitHub API Constraints" — 1,000 results/query, ~4,000 scanned, 30 search req/min, GITHUB_TOKEN 1k core req/hr.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None yet — greenfield. No source files exist (`CLAUDE.md` + `.planning/` only). Phase 1 establishes the first code.

### Established Patterns
- No code patterns yet. The stack table in `CLAUDE.md` is the de-facto pattern source: `safe_search` wrapper around PyGithub search that pre-checks `g.get_rate_limit().search.remaining`; per-date JSON snapshot files; commit-back via the auto-commit action.

### Integration Points
- This phase produces the data substrate (`data/snapshots/`, metadata store, seen-store) that Phase 2's ranking + reporting reads. Design the snapshot schema with Phase 2's velocity diffing in mind (numeric `repo.id` key, current stars, captured-at UTC timestamp).

</code_context>

<specifics>
## Specific Ideas

- Concept source (for tone/shape of the eventual digest, Phase 2): YouTube walkthrough https://www.youtube.com/watch?v=0k8rJseHQTA — 4-bucket velocity tracking, daily markdown digest.
- "Early radar" framing drove the fresh-friendly low keyword floor (D-02): prefer catching a 12-star day-2 rocket over suppressing noise.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 1 scope. Velocity ranking, digest formatting, and hardening were explicitly held for Phases 2–3 per the roadmap.

</deferred>

---

*Phase: 1-Collection Loop*
*Context gathered: 2026-06-26*
