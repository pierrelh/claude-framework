# How the framework works

This project is driven by an AI agent team inside Claude Code. You describe needs; the
agents turn them into GitHub issues, plan them on a roadmap, implement them through pull
requests and keep this documentation up to date.

- [Workflow](workflow.md) — from an idea to merged code, step by step
- [GitHub setup](github.md) — repository, Kanban board, roadmap, fields
- [Autonomy modes](autonomy.md) — assisted vs fully automatic, and the safety nets
- [Cloud runs](cloud-runs.md) — run `/fw-work` in GitHub Actions, answer questions from GitHub

## Daily commands
| You want to… | Type |
|---|---|
| Know where things stand | `/fw-status` (summary) · `/fw-dashboard` (progress bars, burn-up, timeline — `/fw-dashboard html` in the browser) |
| Make progress | `/fw-work` (one story) · `/fw-work all` (chain, auto mode) |
| Add a feature or report a bug | `/fw-backlog <your words>` |
| Re-estimate or re-plan | `/fw-plan` |
| Change the agent team | `/fw-team` |
| Sort incoming issues from users or teammates | `/fw-triage` |
| Ship a version | `/fw-release` |
| Fix something urgent | label the bug `hotfix` (or ask `/fw-triage`), then `/fw-work` |
| Stop the agents / continue later | `/fw-stop` · `/fw-resume` |
| Learn from a finished milestone | `/fw-retro` |
| Refresh the docs | `/fw-docs` |
| Check your machine / GitHub access | `/fw-doctor` |
| Get the latest framework | `/fw-update` |
| Run the project's checks | `framework/bin/fw check` — see [quality gates](quality-gates.md) |

## What lives where
| Path | Owner | Content |
|---|---|---|
| `framework/` | template | CLI (`framework/bin/fw`), hooks, standards, templates |
| `.claude/skills/fw-*` | template | The `/fw-*` commands |
| `docs/framework/` | template | This documentation |
| `.claude/agents/` | project | The agent team |
| `.fw/` | project | Config, backlog batches, key → issue mapping |
| `CLAUDE.md`, `docs/` | project | Knowledge for agents and humans |

Template-owned files are replaced by `/fw-update`; don't edit them in a project (the guard
blocks it once the project is initialized). `.fw/framework.lock.json` records their hashes as
installed: `fw drift` lists local edits, and `/fw-update` warns before overwriting them. After
an update, `fw migrate` (run automatically) adapts the project's config and settings to the
new version.

## The `fw` CLI
Skills call `framework/bin/fw` for everything touching the GitHub project, so behaviour is
deterministic. You can use it too: `framework/bin/fw -h`.
