---
phase: quick-260701-tnx
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/report.py
  - tests/test_report.py
autonomous: true
requirements:
  - QUICK-TNX
user_setup: []

must_haves:
  truths:
    - "All four CATEGORY LEADERS grid cards render at the same visual height regardless of active/empty state, so the row of cards has a flush bottom edge"
    - "The empty-state 'Warming up.' cell still shows no 'stars / day' text and no velocity number (existing invariant, must not regress)"
    - "Active-cell markup (kicker, velocity number, 'stars / day', repo name) is unchanged"
  artifacts:
    - path: "src/report.py"
      provides: "_render_leader_cell card wrapper with explicit min-height so empty/active cells match height"
      contains: "min-height"
  key_links:
    - from: "_render_leader_cell"
      to: "card div (line ~550)"
      via: "shared wrapper div used by both active and empty branches"
      pattern: "min-height"
---

<objective>
User reported (screenshot) that the CATEGORY LEADERS grid's "24H SPIKE" empty-state
card ("Warming up.") renders visibly shorter than its three sibling cards (which show
a big velocity number + "stars / day" + bold repo name — 3 content lines vs. the empty
state's 1 line). Because each card's height is driven by its own content (no shared
height constraint), the row of 4 cards has a ragged/misaligned bottom edge instead of
a flush one.

Fix: give the shared card wrapper div in `_render_leader_cell` (src/report.py ~line 550,
used by both the active and empty-state branches) an explicit `min-height` sized to fit
the tallest (active) card's content. This is a single-line CSS addition — no markup
restructuring, no change to which text renders in either branch.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@C:\dev\CLAUDE.md
@C:\dev\github-repo-tracker\CLAUDE.md

Target function: `_render_leader_cell` in src/report.py (~lines 526-554).
Existing tests: tests/test_report.py `TestRenderHtmlLeaders` (~lines 869-928) —
in particular `test_inactive_cell_shows_warming_up_and_no_number`, which asserts
`"stars / day" not in spike_cell` and no number text in the empty cell. This
invariant must keep passing unchanged.
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Give leader-grid cards a shared min-height so empty and active cells align</name>
  <files>src/report.py</files>
  <behavior>
    - The card wrapper div in `_render_leader_cell` (the one with
      `background:#111318; border:1px solid #23262f; border-radius:10px; padding:14px 16px;`)
      gains a `min-height` declaration, applied identically to both the active-leader
      branch and the empty/"Warming up." branch (it's the same wrapper for both — no
      per-branch duplication).
    - No other markup changes: kicker, value/unit/name lines for the active branch and
      the "Warming up." text for the empty branch stay exactly as they are.
  </behavior>
  <action>
In `src/report.py`, in `_render_leader_cell`, add `min-height:96px;` to the inline style
of the card wrapper div (the one currently reading
`style="background:#111318; border:1px solid #23262f; border-radius:10px; padding:14px 16px;"`
at ~line 550). 96px comfortably fits the active branch's 3-line stack (kicker ~9.5px +
value line margin-top:8px/font-size:30px + unit line margin-top:2px/font-size:9px + name
line margin-top:8px/font-size:13px) so the empty-state 1-line branch renders at the same
card height instead of shrinking to fit its own shorter content.

Do not touch the footer stats strip cards (`_render_strip_cell`) — those are a separate,
already-uniform 1-number-1-label structure with no active/empty branching, out of scope.
  </action>
  <verify>
    <automated>cd C:/dev/github-repo-tracker && uv run pytest tests/test_report.py -q</automated>
  </verify>
  <done>_render_leader_cell's shared card div has min-height:96px; existing TestRenderHtmlLeaders tests (including the no-"stars / day"/no-number invariant for the empty cell) still pass unchanged; a new test asserts both an active-cell card and an empty-cell card contain the same min-height token.</done>
</task>

<task type="auto">
  <name>Task 2: Add regression test pinning equal card height across active/empty cells</name>
  <files>tests/test_report.py</files>
  <action>
Add a test in `TestRenderHtmlLeaders` (mirror existing conventions, reuse `_make_buckets`,
`_entry`, `_now`): build buckets with at least one active bucket and at least one
inactive/empty bucket (e.g. `_make_buckets(weekly_entries=[...], spike_active=False)`),
call `render_html_leaders`, split into the four `<td width="25%"` cells as
`test_inactive_cell_shows_warming_up_and_no_number` already does, and assert the
active cell's card div and the empty cell's card div both contain the identical
`min-height:96px` substring (structural guard against the two branches drifting apart
in height again).
  </action>
  <verify>
    <automated>cd C:/dev/github-repo-tracker && uv run pytest tests/ -q</automated>
  </verify>
  <done>New test passes; full suite green; no regressions in markdown or hero/bucket tests.</done>
</task>

</tasks>

<verification>
- `uv run pytest tests/ -q` — full suite passes.
- `_render_leader_cell` empty and active branches share the same card `min-height`.
- No change to markdown path, hero, bucket/row renderers, or footer stats strip.
</verification>

<success_criteria>
- All four CATEGORY LEADERS cards render at equal height in both active and empty states.
- Empty-state cell still shows only kicker + "Warming up." (no number, no "stars / day").
- All tests pass, including the new height-parity regression test.
</success_criteria>

<output>
After completion, create `.planning/quick/260701-tnx-fix-leaders-alignment/260701-tnx-SUMMARY.md`
</output>
