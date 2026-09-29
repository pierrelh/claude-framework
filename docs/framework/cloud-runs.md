# Cloud runs

Run `/fw-work`, `/fw-backlog` or `/fw-status` in **GitHub Actions** instead of on your
computer: useful when your machine is off, or to let a tool or app start work remotely.

## Set up (once per project)
1. `framework/bin/fw workflow install cloud-run` — copies the workflow to
   `.github/workflows/fw-cloud-run.yml` and tells you which secrets are missing. Commit it
   through a pull request.
2. Add two repository secrets (*Settings → Secrets and variables → Actions*):
   - `ANTHROPIC_API_KEY` — your Anthropic API key. Cloud runs are billed per use on it.
   - `FW_GH_TOKEN` — a *classic* personal access token with the `repo`, `project` and
     `workflow` scopes. The built-in `GITHUB_TOKEN` can't read or edit a Project owned by a
     personal account, and the framework keeps the board up to date.

## Start a run
- GitHub: *Actions → fw cloud run → Run workflow*, choose the command and the arguments
  (`#12`, `all`, `3`, or the need for `fw-backlog`).
- CLI: `gh workflow run fw-cloud-run.yml -f command=fw-work -f args="#12"`.
One run at a time per repository (later dispatches wait in the queue).

## When an agent has a question
A cloud run can't wait for you, so it posts the question on the issue (a comment marked
**🙋 Needs you**), labels it `needs-human`, and moves on or ends. To answer:
- reply on the issue with a comment starting with `/answer`, e.g. `/answer Use option 2`,
  then start a new run. It picks up answered questions first.
- Or answer and resume in one step:
  `gh workflow run fw-cloud-run.yml -f command=fw-work -f args="#12" -f answer_issue=12 -f answer="Use option 2"`.

## Safety
The run uses `--permission-mode bypassPermissions` inside a disposable GitHub runner. The
framework's guard hook still blocks pushes to the default branch and force pushes. Merges
follow your project's autonomy mode, and escalation rules still apply.
