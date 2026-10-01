---
name: fw-retro
description: Run a retrospective on a finished milestone (or the last N done items) — compare estimates with measured agent time, look at review rounds, waits and escalations, find the review findings that keep coming back, and propose concrete changes (estimate calibration, project review rules, agent prompt or standard changes) for the user to approve. Use when a milestone closes, when estimates drift, or when the user asks "what can we improve?".
argument-hint: "[milestone title or number — default: the most recently completed one]"
---

# /fw-retro — learn from what was delivered

Talk to the user in `language` (`.fw/config.json`); write the report in `docs_language`.
Read-only until the user approves a proposal. Argument: `$ARGUMENTS`.

## 1. Collect (one Bash call)
```
framework/bin/fw metrics --milestone "<m>" --json; framework/bin/fw status --json
gh pr list --state merged --limit 200 --json number,title,body,mergedAt
```
Pick the milestone: the argument, else the latest whose items are all done (ask if unclear).
Keep the PRs whose body says `Closes #<n>` (or Fixes/Resolves) for an item of that milestone. From each PR body,
read the **Review findings** section (one line per finding: `category — finding`) and the
estimate vs actual line. Also read `.claude/review-rules.md` if it exists, and
`docs/retros/` for the previous retros (don't re-propose what was rejected there).

## 2. Analyse — facts first, each with its numbers
- **Estimates**: overall ratio actual/estimate (agent time only); by size, type and agent.
  A group with ≥ 3 items and a ratio outside 0.7–1.3 is a calibration signal. Name the
  outliers (ratio < 0.5 or > 2) and, from their PR and issue, the reason (unclear spec,
  underestimated area, environment problems, rework after review…).
- **Review**: average rounds and first-time approval rate. Group the findings by category
  and by area (files/modules). A category seen in ≥ 3 PRs, or in ≥ 2 PRs of different
  implementers, is a **recurring finding**.
- **Flow**: waiting time on humans (median, max) and escalations (items labelled
  `needs-human` during the milestone, from their comments). Long waits are a process signal
  for the user, not an agent problem.
- Items done without measured time (no local timer: other machine, cloud run) are listed,
  not guessed.

## 3. Propose — few, concrete, each tied to a finding
For each proposal: the evidence (numbers, PR links), the exact change, and the expected
effect. Typical proposals:
1. **Calibration**: "Stories of size M take 1.6× their estimate (5 items): estimate M stories
   ×1.5 from now on" → recorded in `CLAUDE.md → Gotchas` (estimation notes) and applied by
   `/fw-backlog` and `/fw-plan` to new and remaining estimates (ask before re-estimating).
2. **Review rule**: a recurring finding becomes a rule in `.claude/review-rules.md` (create
   it if missing): `- **<category>** — <rule, phrased as a check> (from retro <milestone>,
   PRs #a #b #c)`. Reviewers check every rule; implementers read the file before coding, so
   the finding stops recurring. Keep it short: merge or drop rules that no longer fire.
3. **Agent change**: when one agent causes the rework (e.g. its procedure misses the test
   command, or it ignores a convention), propose the precise edit to `.claude/agents/<name>.md`
   through the `/fw-team` revision flow (`fw lint-agents` must pass).
4. **Process**: waits, escalations, story slicing, acceptance criteria quality → a change in
   how the user and the team work (e.g. smaller stories, answering escalations daily).
5. **Framework**: a problem in the framework itself (a standard, a skill, `fw`) → a note for
   the template maintainer; never edit framework-owned files in a project.
Ask the user to accept, amend or reject each proposal.

## 4. Record
- Write `docs/retros/<milestone-slug>.md`: date, scope, the numbers, findings, and each
  proposal with its decision (accepted / rejected — why). Link it from `docs/index.md`.
- Apply the accepted changes (review rules, CLAUDE.md notes, agent edits via `/fw-team`).
- On a branch `docs/retro-<milestone-slug>`, `fw docs-check`, commit
  `docs: retrospective <milestone>`, PR; merge per autonomy mode.

## 5. Report
In the user's language, 5–10 lines: the headline numbers, the top 3 findings, what changes
now, and when the next retro makes sense (next milestone, or after ~10 more items).
