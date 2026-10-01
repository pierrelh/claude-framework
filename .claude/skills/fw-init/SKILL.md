---
name: fw-init
description: One-time setup of a project with the framework — environment and GitHub checks, language, autonomy mode, GitHub repo + Kanban/Roadmap project, product brief, stack, agent team, backlog of qualified user stories, estimates, roadmap and docs. Handles both a brand-new project and the adoption of an existing codebase.
argument-hint: "[optional: what you want to build, in your own words]"
disable-model-invocation: true
---

# /fw-init — set up this project

You are the **initialization orchestrator**. Take the user from a fresh clone (or an existing
codebase with the framework just installed) to a GitHub project full of qualified,
estimated user stories, an agent team and living docs. Be warm and clear: the user may not
be a developer. Explain *why* before asking for anything.

User's opening words (may be empty): `$ARGUMENTS`

## Ground rules
- Talk in the user's language (detect it from their messages; confirm in phase 1).
- One phase at a time. Announce the phase, do it, summarise it in 2–3 lines, move on.
- Ask with `AskUserQuestion` when there are clear options (put your recommendation first,
  marked "(Recommended)"); ask open questions in plain text.
- Every GitHub operation goes through `framework/bin/fw` — never improvise `gh project`
  GraphQL. Commands that need an interactive terminal (e.g. `gh auth login`) must be run by
  the user: tell them to type `! <command>` in the prompt.
- **Gates that always need an explicit "yes"**, whatever the autonomy mode: enabling auto
  mode, deleting/recreating git history, creating the repository, the brief, the team, the
  backlog before it is pushed to GitHub.
- Progress is saved in `.fw/config.json` (`init_phase`). If it is already set, offer to
  resume from that phase instead of restarting.

## Phase 0 — State
Run `framework/bin/fw config get` and `framework/bin/fw doctor --json`.
- `initialized: true` → the project is already set up. Offer instead: `/fw-backlog` (new
  need), `/fw-team` (revise the team), `/fw-plan`, `/fw-status`. Stop unless the user insists.
- Decide the **mode** from `repo` in the doctor output and confirm it with the user:
  - **new** — `project_files` is 0 (only framework files).
  - **adopt** — real project files exist (`project_files_sample` shows some).

## Phase 1 — Language
Confirm three things (one `AskUserQuestion` with 2–3 questions):
- conversation language (`language`, e.g. `fr`),
- issue language (`issue_language`: the same language, or English),
- docs language (`docs_language`: usually the same as the conversation).
Save them: `framework/bin/fw config set language fr` etc. Then `fw config set init_phase language`.

## Phase 2 — Environment
Follow `.claude/skills/fw-doctor/SKILL.md` until `fw doctor` reports READY. Typical fixes:
- `gh` missing or too old → give the install command for their OS (from the doctor output).
- not authenticated → `! gh auth login -h github.com -s repo,project,workflow`
- missing scopes → `! gh auth refresh -h github.com -s project,workflow`
- git identity → `git config --global user.name/user.email` (ask the values).
Re-run `fw doctor` after each fix. Never continue with a ✘ on a required check.

## Phase 3 — Autonomy mode
Explain both modes in plain words, then ask:
- **Assisted (Recommended to start)** — agents propose, you approve each story start and
  each merge. Permission prompts stay on.
- **Fully automatic** — agents chain stories, open PRs, review, test and **merge
  themselves**; Claude Code runs without permission prompts
  (`--dangerously-skip-permissions`). Safety nets that remain: the guard hook (blocks force
  pushes, pushes to main, repo deletion, `rm -rf /`…), the reviewer/QA gates, CI, and the
  escalation rules of `/fw-work` (anything touching secrets, payments, data deletion or
  unclear business rules stops and asks). Risks: the agent can run any other command on this
  machine without asking; mistakes land on main (revertible through git).
Ask for **explicit consent** for auto mode (a clear "yes, I accept"). Then run
`framework/bin/fw autonomy auto` (or `assisted`) and tell the user auto mode takes effect at
the next start of Claude Code — `claude --dangerously-skip-permissions` or simply `claude`
(the local setting `permissions.defaultMode: bypassPermissions` is written to
`.claude/settings.local.json`, which is git-ignored). The session can continue now.
The mode can be changed any time with `fw autonomy <mode>`.
Then offer the **check gate** (recommended in auto mode): with
`framework/bin/fw config set gates.check_on_stop true`, an agent that changed code cannot
finish while `fw check` (the project's lint/test commands) fails — the failing output is sent
back to it once; a second attempt to stop is allowed so it can report `STATUS: BLOCKED`.

## Phase 4 — Git and GitHub
Owner = the authenticated user (from doctor `login`). Ask: repository name (default: folder
name), visibility (private recommended), one-line description.

**New project**
1. If `origin` points to the framework template (a clone of the template): record it as the
   framework upstream — `fw config set framework.upstream <origin-url>` — then offer:
   - **Fresh history (Recommended)**: with consent, `rm -rf .git && git init -b main`.
   - Keep history: `git remote rename origin framework`.
2. If there is no git repo: `git init -b main`.
3. `framework/bin/fw github-setup --repo <name> --create-repo --visibility <v> --description "<d>"`
4. `git remote add origin https://github.com/<owner>/<name>.git` if missing (check `git remote -v`).

**Adopt**
1. If `origin` is already a GitHub repo of the user: `fw github-setup --repo <owner>/<name>`
   (no `--create-repo`). Otherwise create one as above and add it as `origin`.
2. `framework/bin/fw import-issues` to bring the existing open issues onto the board.

**Both** — views: `fw github-setup` prints whether Board and Roadmap views exist. GitHub's API
cannot create views, so walk the user through the one-minute manual step it prints (Board
grouped by Status; Roadmap using Start date / Target date, grouped by Milestone), then
`framework/bin/fw views-check`. Tip for later: once a project has these views, its
`owner/number` can be stored in `framework.template_project` of the template, and future
projects will be *copied* with views included.

## Phase 5 — Understanding the codebase (adopt only)
Launch an `Explore` subagent (very thorough) to map: languages and frameworks with versions
(from manifests/lockfiles), entry points, directory layout, test setup and how to run it,
build/CI, database and migrations, conventions visible in the code, obvious risks/tech debt.
Record the project's commands: `framework/bin/fw commands --detect` (from package.json,
composer.json, pyproject, go.mod, Makefile…), adjust with the user, `--apply`, then fill gaps
with `fw config set commands.<install|lint|typecheck|test|build> '"<command>"'`. When it is
safe, run `framework/bin/fw check` and report what fails — don't fix it here, failing checks
become backlog items. `CLAUDE.md → Commands` points to the same commands.
Write the findings to `docs/architecture/overview.md` (with a Mermaid diagram) and a first
pass of `CLAUDE.md` (Stack, Commands, Conventions, Architecture, Gotchas).

## Phase 6 — Brief
Follow `.claude/skills/fw-brief/SKILL.md` (it handles precise vs exploratory/POC requests,
and in adopt mode focuses on *what comes next* while documenting what exists).
Gate: the user approves `docs/product/brief.md`.

## Phase 7 — Stack
- Adopt: the stack is what exists; only additions are discussed.
- New: if the brief fixes the stack, use it. Otherwise recommend one with 2–3 reasons tied
  to the brief (team skills, hosting, POC speed — for a POC pick the simplest thing that can
  be demoed) and one alternative. Verify current stable versions from official sources
  (WebSearch/WebFetch when available) — do not rely on memory.
Record `fw config set stack '{"backend":"PHP 8.4 / Symfony 7.3","db":"PostgreSQL 17",...}'` and
fill `CLAUDE.md → Stack` with versions and today's date.
New project: also record the **planned** commands (`fw config set commands '{"install":…,
"lint":…,"test":…}'`) — the walking-skeleton task makes them real, makes `fw check` pass and
installs CI (`fw workflow install ci-<node|php|python|go|generic>`, then
`fw protect --checks check` once it ran green).

## Phase 8 — Agent team
Follow `.claude/skills/fw-team/SKILL.md`. Gate: the user picks the agents.

## Phase 9 — Backlog
Follow `.claude/skills/fw-backlog/SKILL.md` in *initial* mode. Gate: the user approves the
backlog before `fw backlog-apply`.

## Phase 10 — Estimates and roadmap
Follow `.claude/skills/fw-plan/SKILL.md` (capacity questions, estimate discussion,
`fw schedule --apply --markdown docs/product/roadmap.md`).

## Phase 11 — Docs and first commit
1. Fill `docs/index.md`, `docs/guides/getting-started.md` (how to run the project — even if
   it is only planned: say what will exist after the walking skeleton), `docs/agents/team.md`,
   `docs/product/glossary.md` (domain terms from the brief).
2. Replace `README.md` with a project README: name, one-paragraph pitch, links to the board,
   the roadmap and `docs/`, how to start (`claude` → `/fw-status`, `/fw-work`). The framework
   documentation stays in `docs/framework/`.
3. Remove the "not initialized" banner from `CLAUDE.md`; keep it ≤ 150 lines.
4. `framework/bin/fw docs-check` and `framework/bin/fw lint-agents` must pass.
5. `fw config set name "<project name>"`, then `fw config set initialized true`,
   `fw config set init_phase done`.
6. Commit `chore: initialize project with AI framework`, then push:
   - **New project** (the remote has no `main` yet): `git push -u origin main`. The guard
     allows a direct push to main only in that case — it checks the remote, not the command.
   - **Adopt** (the remote already has `main`): commit on `chore/fw-init` instead, push it,
     `gh pr create`, and merge once the user agrees (or they merge on GitHub).
   New agents in `.claude/agents/` are loaded at the next start of Claude Code.
7. Protect the default branch: `framework/bin/fw protect` (GitHub ruleset: pull request
   required, no force push, no deletion, no bypass). Exit code 4 = the plan does not allow it
   (private repository on GitHub Free): explain the options it prints and continue — the local
   guard still applies.
8. Adopt, when `fw check` passes: `framework/bin/fw workflow install ci-<stack>` (the stack
   `fw commands --detect` suggests; `--env` for versions), commit it through a pull request,
   and once it ran green `framework/bin/fw protect --checks check`. When it fails, the CI
   setup becomes a backlog task instead.

## Phase 12 — Hand-over
Summarise in the user's language: repo URL, board URL, number of epics/stories, total hours,
projected end per milestone, the agent team, the autonomy mode. Then explain the daily loop:
- `/fw-status` — where are we?
- `/fw-work` — implement the next story (`/fw-work all` to chain them in auto mode)
- `/fw-backlog <new need>` — add a feature or report a bug
- `/fw-plan` — re-estimate / re-plan
- docs: open `docs/` in Obsidian, or `mkdocs serve`.
If auto mode was chosen, remind them to restart Claude Code before `/fw-work all`.
