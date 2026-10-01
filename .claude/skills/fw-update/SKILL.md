---
name: fw-update
description: Update this project's framework files (framework/, fw-* skills, docs/framework/) from the upstream template repository, on a branch with a pull request. Use when the user wants the latest framework version.
disable-model-invocation: true
---

# /fw-update

1. `framework/bin/fw config get framework` — if `upstream` is empty, ask the user for the
   template's git URL (default: `https://github.com/pierrelh/claude-framework.git`) and run
   `framework/bin/fw config set framework.upstream <url>`.
2. Preview: `framework/bin/fw update` (dry run). It prints the CHANGELOG entries between the
   two versions, the changed and removed files, and the **local changes to framework-owned
   files** that `--apply` would overwrite (from `fw drift`). Summarise for the user: what
   changes for them (Breaking / Security entries first), and for each local change, whether
   it should be proposed upstream before it is lost.
3. With the user's OK: clean tree required →
   `git checkout -b chore/framework-update-<version>` → `framework/bin/fw update --apply`.
   It also refreshes the baseline `.fw/framework.lock.json` and runs the pending migrations
   (`fw migrate`) with the new code — report what they changed. If a migration fails, stop
   and show the error; `framework/bin/fw migrate` can be re-run once it is fixed.
4. Run `framework/bin/fw migrate` (a no-op when `--apply` already ran them; updates started
   from a version older than 0.5.0 do not). Then check nothing project-specific broke: `framework/bin/fw lint-agents`,
   `framework/bin/fw docs-check`, `framework/bin/fw doctor`. New standards may require
   agent adjustments — propose them (via `/fw-team` revision) rather than editing silently.
5. Commit `chore: update framework to <version>`, push, open a PR; merge per autonomy mode.
Only framework-owned paths (see `framework/MANIFEST`) are touched; project files never are.
