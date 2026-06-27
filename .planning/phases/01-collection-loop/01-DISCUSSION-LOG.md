# Phase 1: Collection Loop - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-26
**Phase:** 1-Collection Loop
**Areas discussed:** AI filter definition, Collection breadth, Run schedule, Hosting / deploy target

---

## AI Filter Definition

### Topic anchor

| Option | Description | Selected |
|--------|-------------|----------|
| LLM-era focus | `llm, large-language-models, agents, rag, generative-ai, llmops`. Narrow, matches 2026 AI-tooling zeitgeist. | ✓ |
| Broad AI/ML | Adds `machine-learning, deep-learning, ai, artificial-intelligence, neural-network`. Widest net, heavy noise. | |
| You decide | Claude picks an LLM-leaning starter list. | |

**User's choice:** LLM-era focus
**Notes:** Configurable per FILTER-04, so tunable later. Classic-ML breakouts accepted as a blind spot.

### Keyword fallback aggressiveness

| Option | Description | Selected |
|--------|-------------|----------|
| Low floor, fresh-friendly | Star floor ~10; keeps brand-new untopiced repos visible, more noise. | ✓ |
| Higher floor, signal-first | Star floor ~50; fewer junk repos, but a 12-star rocket can slip past keyword half. | |
| You decide | Claude sets a low floor (~10). | |

**User's choice:** Low floor, fresh-friendly (`stars:>=10`)
**Notes:** Matches "catch them before they trend" core value — prefer fresh discovery over noise suppression.

---

## Collection Breadth

| Option | Description | Selected |
|--------|-------------|----------|
| Focused (~150–300) | Tighter windows + topic priority; safely under GITHUB_TOKEN 1k req/hr; fast, high signal. | ✓ |
| Wide (~500–800) | More slices, larger universe; catches long-tail risers but nears core ceiling (PAT advised). | |
| You decide | Claude targets focused band. | |

**User's choice:** Focused (~150–300)
**Notes:** Confirms GITHUB_TOKEN is sufficient — no PAT. Date windows (7d/30d) fixed by requirements.

---

## Run Schedule

| Option | Description | Selected |
|--------|-------------|----------|
| Early Pacific morning | `'0 13 * * *'` = 13:00 UTC = 6am PDT; digest ready at start of day. | ✓ |
| Off-peak UTC | ~`'0 5 * * *'`; lower Actions load, more consistent spacing, less local alignment. | |
| You decide | Claude picks 13:00 UTC. | |

**User's choice:** Early Pacific morning (`'0 13 * * *'`)
**Notes:** Cron is fixed-UTC so Pacific clock shifts 1h across DST — acceptable, velocity is hour-normalized (RANK-05). Timestamps stored UTC ISO 8601.

---

## Hosting / Deploy Target

*Initial question re-asked at user request to expand public-vs-private tradeoffs (Actions minutes, digest visibility, identical mechanics/security, forkability).*

| Option | Description | Selected |
|--------|-------------|----------|
| Public | Free unlimited Actions, digest browsable/linkable, forkable, no leak risk (public inputs). | ✓ |
| Private | Digest unlisted; ~60 of 2,000 free private min/mo; flip to public later. | |

**User's choice:** Public — dedicated `github-repo-tracker` repo
**Notes:** Built-in `GITHUB_TOKEN` + `contents: write`; commit-back datastore via `git-auto-commit-action` with `[skip ci]`. No PAT.

---

## Claude's Discretion

- Exact keyword fallback strings, precise date/star slice boundaries, snapshot-vs-metadata field split, and same-day idempotency mechanics (DATA-04) — left to research/planning within the dials above.

## Deferred Ideas

None — discussion stayed within Phase 1 scope.
