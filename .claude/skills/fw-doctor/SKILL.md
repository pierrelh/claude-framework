---
name: fw-doctor
description: Check that this machine can run the framework (git, GitHub CLI, authentication and token scopes, Python) and guide the user through each fix. Use at init, or whenever a GitHub operation fails with an auth/scope/permission error.
---

# /fw-doctor — environment check

1. Run `framework/bin/fw doctor`.
2. If READY: say so in one line (logged-in account included) and stop.
3. Otherwise, for each ✘ (required) item, in this order — git, git identity, gh, gh auth,
   gh scopes, GitHub API:
   - Explain in one plain sentence what is missing and why the framework needs it
     (e.g. "the `project` scope lets me create and update your Kanban board").
   - Give the exact fix. Commands that open a browser or prompt interactively must be run
     by the user: "type `! gh auth login -h github.com -s repo,project,workflow`".
     Non-interactive fixes (e.g. `git config --global user.name "…"` once you know the value)
     you may run yourself after asking.
   - Installing software (gh, git, python) is the user's call: give the command for their OS
     (the doctor output contains the hint) and wait.
   - Re-run `framework/bin/fw doctor` after each fix.
4. Warnings (`!`) are not blocking; mention them briefly:
   - `GH_TOKEN`/`GITHUB_TOKEN` set: it overrides `gh auth login`; a fine-grained token must
     grant Issues, Projects, Contents, Pull requests and Workflows (read/write).
   - `claude` not in PATH: only matters for launching auto mode from a terminal.
   - `commands` without `test`: the quality gate has nothing to run — offer
     `framework/bin/fw commands --detect` (then `--apply`).
   - `branch-rules` not protected: offer `framework/bin/fw protect` (needs admin rights; not
     available for private repositories on GitHub Free).
   - `framework-drift`: framework-owned files were edited in this project and the next
     `/fw-update` will overwrite them. Show `framework/bin/fw drift`; suggest moving the change
     to the template, or project-specific behaviour to `CLAUDE.md` / agents / `docs/`.
5. Finish with a one-line summary: READY, or what still blocks.
