# Standard — git and pull requests

- **One backlog item = one branch = one pull request.** Branch from an up-to-date default branch.
- Branch names: `feat/<issue>-<slug>`, `fix/<issue>-<slug>`, `chore/<issue>-<slug>`, `docs/<slug>`.
- Commits: [Conventional Commits](https://www.conventionalcommits.org/) in English —
  `feat(auth): add password reset (#12)`. Small, meaningful commits; no "wip".
- PR title = issue title; PR body follows `.github/pull_request_template.md` and contains
  `Closes #<issue>` so merging closes the issue.
- **Never** push directly to the default branch. Enforced twice: the guard hook blocks it once
  the project is initialized (only the first push of a new repository, when the remote has no
  `main` yet, goes through), and `fw protect` sets a GitHub ruleset (pull request required,
  no force push, no deletion, no bypass). Never use `--no-verify`, `gh pr merge --admin`, or
  change the ruleset to get a change in: escalate instead.
- **Never** force-push shared branches; `--force-with-lease` only on your own feature branch.
- Merge strategy: **squash and merge**, delete the branch.
- Merge conditions: reviewer `VERDICT: APPROVE`, QA `QA: PASS`, CI green (when CI exists).
  In assisted mode the user also approves; in auto mode the orchestrator merges.
- Never commit secrets, generated artefacts, dependencies (`vendor/`, `node_modules/`) or
  local settings (`.claude/settings.local.json`, `.fw/local/`).
