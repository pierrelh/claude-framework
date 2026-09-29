# Autonomy modes

Switch any time: `framework/bin/fw autonomy assisted|auto` (then restart Claude Code).

| | Assisted (default) | Fully automatic |
|---|---|---|
| Permission prompts | on | off (`permissions.defaultMode: bypassPermissions` in `.claude/settings.local.json`, equivalent to `claude --dangerously-skip-permissions`) |
| Starting a story | you confirm | the agent picks the next ready one |
| Merging | you approve (or merge on GitHub) | the agent merges when review, QA and CI are green |
| Chaining stories | one at a time | `/fw-work all` runs until nothing is ready |
| Brief, team, initial backlog | your approval | your approval |

## Safety nets that stay on in auto mode
- **Guard hook** (`framework/hooks/guard.py`) blocks: force pushes, direct pushes to
  main/master, repository/project deletion, history rewriting, `rm -rf` on `/`, `~` or `..`,
  writing to block devices, dropping databases.
- **Quality gates**: reviewer `VERDICT: APPROVE`, QA `QA: PASS`, CI green before any merge.
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
