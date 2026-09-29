# Cloud runs

Run `/fw-work`, `/fw-backlog` or `/fw-status` in **GitHub Actions** instead of on your
computer: useful when your machine is off, or to let a tool or app start work remotely.

## Set up (once per project)
1. `framework/bin/fw workflow install cloud-run` — copies the workflow to
   `.github/workflows/fw-cloud-run.yml` and tells you which secrets are missing. Commit it
   through a pull request.
2. Create an environment named **`fw-cloud-run`** (*Settings → Environments*). **Recommended:**
   add yourself as a required reviewer, so each run waits for your approval. Add two secrets to it:
   - `ANTHROPIC_API_KEY` — your Anthropic API key. Cloud runs are billed per use on it.
   - `FW_GH_TOKEN` — a *classic* personal access token with the `repo` and `project`
     scopes (no `workflow` scope, so agents can't rewrite workflows). The built-in
     `GITHUB_TOKEN` can't read or edit a Project owned by a personal account.
3. Protect the default branch (*Settings → Branches*): require a pull request and status checks.

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
follow your project's autonomy mode, and escalation rules still apply. Other protections:
- only people with write access can start a run;
- only answers from the owner, members and collaborators count (see
  `framework/standards/escalation.md`);
- the token isn't stored in the checkout;
- actions are pinned to commit SHAs.
**Public repositories:** the workflow refuses to run unless the repository variable
`FW_ALLOW_PUBLIC` is `true`. The agent reads issue and PR text that anyone can write, and a
prompt injection could try to misuse the token, so enable it only if you accept that risk.

**Remaining risk (accepted):** during a run, the agent holds the token and the API key, and runs
commands without prompts. A classic `repo` token reaches all your repositories. Keep runs on
private repositories, require your approval on the environment, and protect the default branch.
If a fine-grained token works for your setup (organisation-owned projects), limit it to this
repository.
