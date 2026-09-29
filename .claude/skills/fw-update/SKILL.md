---
name: fw-update
description: Update this project's framework files (framework/, fw-* skills, docs/framework/) from the upstream template repository, on a branch with a pull request. Use when the user wants the latest framework version.
disable-model-invocation: true
---

# /fw-update

1. `framework/bin/fw config get framework` — if `upstream` is empty, ask the user for the
   template's git URL (default: `https://github.com/pierrelh/claude-framework.git`) and run
   `framework/bin/fw config set framework.upstream <url>`.
2. Preview: `framework/bin/fw update` (dry run: version change, changed and removed files).
   Summarise it for the user; if the upstream has a CHANGELOG, show the relevant entries.
3. With the user's OK: clean tree required →
   `git checkout -b chore/framework-update-<version>` → `framework/bin/fw update --apply`.
4. Check nothing project-specific broke: `framework/bin/fw lint-agents`,
   `framework/bin/fw docs-check`, `framework/bin/fw doctor`. New standards may require
   agent adjustments — propose them (via `/fw-team` revision) rather than editing silently.
5. Commit `chore: update framework to <version>`, push, open a PR; merge per autonomy mode.
Only framework-owned paths (see `framework/MANIFEST`) are touched; project files never are.
