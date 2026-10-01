# Changelog

Framework versions (`framework/VERSION`). `/fw-update` shows the entries between your version
and the upstream one. "Contract" = the machine-readable interface (`fw schema`, `--json`).

## 0.11.0 — 2026-10-01
### Added
- `/fw-dashboard` and `fw dashboard [--html [--out F] [--open]] [--json] [--no-custom]`:
  overall progress bar; milestones with due date, planned date and health (on track / at
  risk / late / done); epics; flow; hotfixes, items in flight and items needing you; weekly
  burn-up (scope vs done hours, last 16 weeks) with the pace of the last 4 weeks and the
  forecast end date; upcoming items as a timeline with a today marker; estimate accuracy
  by size; review pipeline state. Terminal view with progress bars, or a self-contained
  HTML page (`.fw/local/dashboard.html`, light/dark, no external resource, all GitHub
  text escaped). Rendering lives in `framework/bin/fw_dashboard.py`.
- Project metrics: `dashboard.metrics` = `[{"title", "command", "unit"?, "target"?,
  "better"?: "higher"|"lower", "timeout"?}]` — each command prints a number or JSON
  `{"value", "target", "unit", "detail"}`; shown as tiles / lines, checked against the target.
### Changed
- The board query also reads each issue's creation and closing dates and each milestone's
  due date (`created_at`, `closed_at`, `milestone_due` on items).

## 0.10.0 — 2026-10-01
### Added
- `fw stop [--now] [--remote] [--reason]`: ask a running `/fw-work` to stop cleanly;
  `--check` (exit 1 = stop requested; headless runs also read the `FW_STOP` repository
  variable set by `--remote`), `--clear`. While a stop is pending the guard refuses new
  agents (Agent / Task), `fw start`, `fw rework`, `fw worktree add` and `gh pr merge`.
- `fw checkpoint <n> --step --next [--note] [--findings-file] [--local]`: where an item
  stands — saved in `.fw/local/checkpoints/` and as a "⏸ Paused" comment on the issue
  (marker `fw:checkpoint`, user text neutralised); `fw checkpoint --run --args` saves the
  run. Stopped time counts neither as agent nor as waiting time (timeline events
  `stop` / `resume`).
- `fw resume <n>` takes a paused item back (timer resumed, comment turned into "▶ Resumed");
  `fw resume` shows checkpoints and the story worktrees; `fw resume --run` the paused run.
  `/fw-work resume` continues the run; `/fw-work` → *Stopping* / *Resuming*.
- `/fw-stop [now] [remote]` and `/fw-resume` skills. Mid-run, type `stop` as plain text
  (Claude Code hands it over between two tool calls; a queued slash command would only run
  after the whole run); Esc then `/fw-stop` stops immediately. Framework rule 7.
### Upgrading from an older version
- `framework/bin/fw migrate` adds the guard hook on Agent / Task launches to
  `.claude/settings.json` (migration 0.10.0).

## 0.9.0 — 2026-10-01
### Added
- Review pipeline (`pipeline.enabled`, both autonomy modes; `fw pipeline on|off [--wip N]`):
  one implementer that starts the next item while reviewers, QA and CI check the previous
  ones in the background — at most `review_wip` (default 2) items in review, rework first,
  no item depending on an unmerged one, overlapping files avoided, merges one at a time with
  the other branches rebased after each. `fw pipeline [--json]` says whether a new item may
  start; items escalated or started on another machine are not counted.
- `fw worktree add|list|remove`: one worktree per item in `<repo>.worktrees/<n>-<slug>`
  (outside the repository, so test runners and linters never scan it), branch named from
  the item; `add` is idempotent and reuses an existing branch; `remove` refuses uncommitted work.
- `fw rework <n>`: back to In progress after changes were requested, resuming the agent timer.
### Changed
- `fw schedule` with the pipeline on: one implementer lane, occupied for the agent hours
  only — human review overlaps the next item, dependents still wait for it.
- The guard protects framework-owned files inside story worktrees too; the check gate checks
  every changed story worktree, not only the main checkout.
- `/fw-status` shows the pipeline state; `/fw-init` offers the pipeline.

## 0.8.0 — 2026-10-01
### Added
- `fw resume [--json]`: items left in progress / in review, with the step `/fw-work` resumes
  them from (branch, uncommitted work, commits ahead, open / merged / closed PR); items
  started on another machine are left alone. `/fw-work` runs it before picking new work.
- Hotfix path: `hotfix` label, first in `fw next`; `/fw-work` short path (regression test
  first, smallest fix, one focused review, CI), branch `hotfix/<n>-<slug>`.
- `/fw-triage` and `fw untriaged [--json]`: open issues not on the board, labelled `triage`
  or without type / estimate → duplicate, needs info, hotfix, bug, story, or handed to
  `/fw-backlog`. Labels `triage` and `needs-info`; the bug form adds `triage`.
- `/fw-release` and `fw release-notes [--since] [--current] [--version] [--json]`: notes
  grouped from the Conventional Commits since the last `v*` tag, next semantic version,
  CHANGELOG and version bump through a PR, annotated tag, GitHub release, milestone closed.
  Always confirmed by the user, even in auto mode.
### Upgrading from an older version
- Re-run `framework/bin/fw github-setup` once to create the `hotfix`, `triage` and
  `needs-info` labels. `.github/ISSUE_TEMPLATE/bug.yml` is a project file: add `triage` to
  its labels if you want new reports to land in `/fw-triage`.

## 0.7.0 — 2026-10-01
### Added
- Time is measured per phase: `fw start`, `fw review` and `fw escalate` log a timeline in
  `.fw/local/timers.json`; `fw done` records **Actual (h)** = agent working time and the new
  **Wait (h)** = time waiting on a human; `fw done --rounds N` records the new
  **Review rounds** field.
- `fw metrics [--milestone] [--json]`: agent estimate vs actual by size, type and agent,
  review rounds, waits, outliers.
- `/fw-retro [milestone]`: retrospective from the metrics and the review findings of the
  milestone's PRs → proposals (estimate calibration noted in `CLAUDE.md`, rules in the
  project's `.claude/review-rules.md`, agent edits through `/fw-team`, process changes),
  each approved by the user, recorded in `docs/retros/`.
### Changed
- **Actual (h)** used to be wall-clock time from `fw start` to `fw done` (it included waiting
  for the merge); it is now agent working time, and accuracy compares it with **Agent
  effort** only (not effort + human review). Old timer entries are still read.
- `/fw-work`: reviewers check `.claude/review-rules.md`, implementers read it; every review
  finding (`category — finding`) and the number of rounds go into the PR (new *Review
  findings* section of the PR template); `fw done --rounds`; suggests `/fw-retro` when a
  milestone completes.
- `/fw-backlog` and `/fw-plan` apply the calibration notes of `CLAUDE.md`.
### Upgrading from an older version
- Re-run `framework/bin/fw github-setup` once to add the *Wait (h)* and *Review rounds*
  fields to the project (until then `fw done` skips them with a warning).
- `.github/pull_request_template.md` is a project file: copy the *Review findings* section
  from the template if you want it.

## 0.6.0 — 2026-10-01
### Added
- `.fw/config.json → commands` (`install`, `lint`, `typecheck`, `test`, `build`): one
  definition of the quality gate. `fw check [steps] [--json] [--fail-fast] [--if-configured]`
  runs it; implementers and QA finish with it. `fw commands --detect [--apply]` suggests the
  commands from package.json, composer.json, pyproject.toml, go.mod, Cargo.toml and Makefile.
  `fw doctor` warns when no `test` command is configured.
- CI templates `ci-node`, `ci-php`, `ci-python`, `ci-go`, `ci-generic`
  (`fw workflow install ci-<stack> [--env KEY=VALUE]`): one job named `check` that runs
  `fw check`, actions pinned to SHAs, read-only token, no persisted credentials. Make it
  required with `fw protect --checks check`.
- Optional check gate (`gates.check_on_stop`): a Stop / SubagentStop hook keeps an agent
  working while `fw check` fails on its changes, without looping.
- Docs: `docs/framework/quality-gates.md`.
### Changed
- `/fw-init` records the commands (detected when adopting), offers the check gate and
  installs CI; the walking-skeleton example task requires `fw check` and a required CI check.

## 0.5.0 — 2026-10-01
### Added
- `.fw/framework.lock.json`: hashes of the framework-owned files, written by `fw install` and
  `fw update --apply` (commit it). `fw drift [--json]` lists files modified, added or deleted
  locally since then; `fw doctor` reports it (`framework-drift`).
- `fw update` previews the CHANGELOG entries between the installed and the upstream version,
  and warns about the local changes `--apply` would overwrite.
- `fw migrate [--dry-run]`: versioned, idempotent migrations of the project's config and
  settings, tracked in `framework.migrated`. `fw update --apply` runs them with the *new*
  code. First migration (0.4.0): add the Edit/Write guard hook that older `fw` versions
  failed to merge into `.claude/settings.json`.
### Fixed
- `fw protect --repo <other>` no longer writes that repository's protection into the
  local config.
### Upgrading from an older version
- The `fw` doing the update is still the old one: after `fw update --apply`, run
  `framework/bin/fw migrate` once — it adds the missing Edit/Write guard hook and creates the
  baseline lock. Later updates run it automatically.

## 0.4.0 — 2026-10-01
### Added
- `fw protect`: GitHub ruleset on the default branch — pull request required, no force push,
  no deletion, no bypass actors; `--checks` for required CI checks, `--approvals`,
  `--check`. Run by `/fw-init` after the first push; `fw doctor` reports it (`branch-rules`).
- The guard also covers Edit / Write / MultiEdit / NotebookEdit: once initialized,
  framework-owned files and `.fw/state.json` are read-only (also through `>`, `tee`,
  `sed -i`, `cp`, `mv`, `rm`).
- New guard rules: `rm -r -f` in any flag order, `.` and top-level directories,
  `--no-preserve-root`; `+refspec` and `--mirror` pushes, deleting main, `--no-verify`,
  `git clean -f`, `git reset --hard` over uncommitted changes, `git branch -D main`;
  `gh pr merge --admin`, `gh repo edit --visibility`, `gh api` repository deletion and
  branch-protection changes; recursive `chown`; `TRUNCATE` / unfiltered `DELETE` sent to a
  database client, `dropdb`, `mysqladmin drop`, Redis flushes.
### Changed
- The guard parses commands instead of matching raw text: a commit message, a PR body or a
  heredoc that only *mentions* a dangerous command is no longer blocked. `sudo`, `env`,
  `bash -c`, `eval` and `$(…)` are unwrapped.
- **Breaking:** `FW_ALLOW_MAIN_PUSH=1` is gone (any command could set it). A direct push to
  main is allowed only when the remote has no main/master yet, i.e. the first push of a new
  repository; an unreachable remote counts as "has one". `/fw-init` adoption now lands its
  commit through a `chore/fw-init` pull request.
- `fw update` / `fw install` merge hooks by (matcher, command), so a hook command reused
  under a new matcher reaches existing projects.

## 0.3.1 — 2026-10-01
### Added
- Test suite extended to backlog validation, the `fw done` cascade, `install` / `update` on
  throwaway git repos, `lint-agents`, `docs-check`, the SessionStart hook and the guard
  (`framework/tests/test_*.py`, shared `helpers.py`). Known guard holes are recorded as an
  expected failure.
- Template CI: `.github/workflows/framework-tests.yml` (Python 3.8 and 3.12). Template-only,
  never copied into projects.
### Changed
- `manifest()` / `repo_files()` resolve the project root at call time (testability; no
  behaviour change).

## 0.3.0 — 2026-09-29
### Added
- Structured escalations (`framework/standards/escalation.md`): `fw escalate`, `fw answer`,
  `fw resolve`, `fw escalations --json`. Humans answer with a `/answer <text>` comment.
  Contract: `fw schema --json → escalation` (contract_version stays 1 — additive).
- Cloud runs: `framework/templates/workflows/fw-cloud-run.yml` and
  `fw workflow install cloud-run` (checks the required secrets). Docs: `docs/framework/cloud-runs.md`.
### Changed
- `/fw-work` resumes answered escalations first, escalates through `fw escalate`, prefixes
  its questions with `[fw:<kind> <id>]`, and never waits for an answer in headless sessions
  (`FW_HEADLESS=1` / `CI=true`).
### Security
- Escalation comments are honoured only from OWNER / MEMBER / COLLABORATOR authors
  (`escalations.trusted_associations`), ids can't be reopened, marker payloads are escaped.
- Cloud-run workflow: `fw-cloud-run` environment, no persisted checkout credentials, token
  scoped to steps, actions pinned to SHAs, refuses public repositories unless `FW_ALLOW_PUBLIC`.

## 0.2.0 — 2026-09-29
### Added
- `fw schema --json`: versioned machine-readable contract (field names, statuses, markers).
  `CONTRACT_VERSION = 1`.
- `fw status --json`: counts, hours, accuracy, milestones (with Musts target), in progress,
  in review, needs attention, ready items.
- `fw github-setup --project <n>` to attach an existing project; `--fix-status` to replace
  the default Todo/In Progress/Done columns while keeping every item's status (backed up to
  `.fw/local/status-backup.json`; `--restore-status` re-applies it).
- Backlog items: `owner: human` (no agent, may have 0 agent hours, `needs-human` label) and
  `wait_days` (calendar waiting that delays dependents).
- `fw backlog-validate` warns when an item depends on a later milestone.
- Unit tests: `python3 -m unittest discover framework/tests`.
### Changed
- `fw schedule` orders by milestone before priority (`capacity.order: priority` restores the
  old behaviour); human items run on their own lane; reports "Musts done by" per milestone.
- `fw start` refuses an item already in progress / in review (exit code 3; `--force` to take over).
- `/fw-work` runs **every** agent of `roles.review` (string or list); all must approve.
### Fixed
- `fw github-setup` saves the project to the config right after creating it, so a failed
  setup no longer creates a duplicate project on re-run.
- Status columns are also applied when a project is reused with GitHub's default options.

## 0.1.0
### Fixed
- The `Type` project field is reserved by GitHub: renamed to `Item type` (#1).
