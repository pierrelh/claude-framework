# Changelog

Framework versions (`framework/VERSION`). `/fw-update` shows the entries between your version
and the upstream one. "Contract" = the machine-readable interface (`fw schema`, `--json`).

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
