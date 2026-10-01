---
name: fw-backlog
description: Turn a need into qualified, measured, estimated GitHub issues — milestones, epics, user stories, tasks or bugs — linked to the project board, with dependencies. Initial mode builds the whole backlog from the brief; incremental mode adds a new feature request or bug. Use whenever work must be planned before it is implemented.
argument-hint: "[new request or bug — empty for the initial backlog from the brief]"
---

# /fw-backlog — from need to GitHub issues

Read first: `framework/standards/user-story.md`, `framework/standards/estimation.md`,
`.fw/config.json` (`issue_language`, `roles`, `autonomy`), `.claude/agents/` (who can be
assigned), `docs/product/brief.md`, and `.fw/state.json` (existing keys).
Request: `$ARGUMENTS` (empty → initial mode).

## 1. Scope the batch
- **Initial**: everything in the brief's first release (and later milestones as `Could`
  if the brief lists them). A POC has a single milestone.
- **Incremental**: only the new request. First look for duplicates or related work:
  `gh issue list --search "<keywords>" --state all --limit 20`. Attach to an existing epic
  (`"epic": "#12"`) when it fits; reference existing issues as dependencies with `"#34"`.
  Ask clarifying questions if the request is ambiguous — in assisted mode always; in auto
  mode only when a wrong guess would waste real work.
- **Bug**: one `Bug` item with description, steps, expected, actual, and acceptance
  criteria that include a regression test.

## 2. Decompose
Milestones → epics (user-facing capabilities) → stories (vertical slices, INVEST) → the few
technical tasks that do not fit a story. For a new project the first item is the
**walking-skeleton task** (layout, dependencies, test runner, linter, CI, one end-to-end
path); everything else depends on it directly or transitively.
For each story: persona/want/benefit, ≥ 2 acceptance criteria (Given/When/Then, including an
error or edge case), a success measure, out-of-scope, technical notes, agent assignment,
priority, dependencies, and the estimate (agent hours with multipliers, review hours, size —
then the calibration notes of `CLAUDE.md` from `/fw-retro`, when there are any).
Split anything above L.

## 3. Write the batch file
`.fw/backlog/<YYYY-MM-DD>-<slug>.json` — format: `framework/templates/backlog.example.json`.
Keys never reuse existing ones in `.fw/state.json` (continue the numbering). Set
`"language"` to `issue_language`.
```
framework/bin/fw backlog-validate .fw/backlog/<file>.json
```
Fix every ✘; address warnings (size mismatches, missing agents) or justify them.
Optionally preview a body: `framework/bin/fw backlog-apply <file> --dry-run | head -60`.

## 4. Review with the user (always, even in auto mode for the initial backlog)
Show, per milestone and epic, a compact table: key · title · type · priority · size ·
agent h · review h · depends on — with totals per epic and milestone. Highlight the
assumptions you made and the riskiest estimates. Invite changes to scope, priorities and
estimates; apply them to the file and re-validate. In auto mode, an **incremental** batch of
≤ 3 items may be applied without this review — say so in the report.

## 5. Push to GitHub
```
framework/bin/fw backlog-apply .fw/backlog/<file>.json
```
It is idempotent (safe to re-run after a failure) and records keys → issue numbers in
`.fw/state.json`. It creates milestones, epics, items, sub-issue links, dependencies,
project fields and statuses (Ready when unblocked, Backlog otherwise).

## 6. Roadmap and report
Run `/fw-plan` logic: `framework/bin/fw schedule --apply --markdown docs/product/roadmap.md`.
Report: issues created (with links to the board), total hours, projected dates.
Commit the batch file, `.fw/state.json` and the roadmap snapshot (on a `docs/backlog-<slug>`
branch + PR once the project is initialized; during `/fw-init` they go in the initial commit).
