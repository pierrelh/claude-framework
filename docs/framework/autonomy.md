# Autonomy modes

Switch any time: `framework/bin/fw autonomy assisted|auto` (then restart Claude Code).

| | Assisted (default) | Fully automatic |
|---|---|---|
| Permission prompts | on | off (`permissions.defaultMode: bypassPermissions` in `.claude/settings.local.json`, equivalent to `claude --dangerously-skip-permissions`) |
| Starting a story | you confirm | the agent picks the next ready one |
| Merging | you approve (or merge on GitHub) | the agent merges when review, QA and CI are green |
| Chaining stories | one at a time | `/fw-work all` runs until nothing is ready |
| Review pipeline (optional, `fw pipeline on`) | the next story starts while the previous one waits for review or for your merge — each start still confirmed | the implementer never waits: reviews, QA and CI of up to 2 stories run in the background |
| Brief, team, initial backlog | your approval | your approval |

## Safety nets that stay on in auto mode
- **Guard hook** (`framework/hooks/guard.py`) parses each command (so merely *mentioning*
  one in a commit message or a PR body is fine) and blocks:
  - recursive deletes of `/`, `~`, `..`, `.` or a top-level directory;
  - force pushes (`--force`, `-f`, `+refspec`, `--mirror`), direct pushes to main/master
    (except the first push of a new repository), deleting main, `--no-verify`,
    `git clean -f`, `git reset --hard` over uncommitted changes, history rewriting;
  - deleting or archiving the repository or the project, changing its visibility,
    `gh pr merge --admin`, changing branch protection through `gh api`;
  - writing to block devices, recursive `chmod`/`chown` on system or home directories;
  - `DROP`/`TRUNCATE`/unfiltered `DELETE` sent to a database client, `dropdb`, Redis flushes;
  - once initialized, any edit of framework-owned files (`framework/MANIFEST`) or
    `.fw/state.json`, through Edit/Write or the shell.
- **Branch protection on GitHub** (`fw protect`, run by `/fw-init`): pull request required,
  no force push, no deletion, nobody bypasses — enforced even if the local guard is skipped.
  Not available for private repositories on GitHub Free; `fw doctor` reports it.
- **Quality gates**: reviewer `VERDICT: APPROVE`, QA `QA: PASS`, CI green before any merge;
  optionally the check gate, which keeps an agent working while `fw check` fails
  ([quality gates](quality-gates.md)).
- **Escalation rules**: ambiguous business rules, secrets/credentials, paid services,
  data deletion or migration, security-sensitive changes beyond the story, 3 failed review
  rounds → the item is labelled `needs-human` and skipped. Three escalations in a row stop
  the run.
- **Everything is a pull request**: any merged change can be reverted from GitHub.

## Risks you accept in auto mode
Without permission prompts, Claude Code can run any other command on this machine and
reach the network without asking. Use auto mode on a machine/account where that is
acceptable (a dev VM or container is ideal), never with production credentials in the
environment.
