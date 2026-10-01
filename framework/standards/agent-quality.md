# Standard — what a project agent must look like

There is **no agent library** in this framework: libraries go stale. Agents are written for
*this* project, at init time (`/fw-team`), from the actual stack, brief and conventions — and
rewritten when those change. This standard is the minimum quality bar every agent must meet,
so the result is good even when the user is not a developer.
`fw lint-agents` enforces the mechanical rules; the checklist at the end covers the rest.

## Principles
1. **One job.** An agent owns one role (spec, implement one layer, review, QA, docs…). If
   its description needs "and" twice, split it.
2. **Selectable.** The `description` states *what it does* and *when to use it* — the
   orchestrator picks agents from that sentence alone.
3. **Least privilege.** List `tools` explicitly. Reviewers, QA and product owner are
   read-only (`Read, Grep, Glob, Bash`) — they report, they don't fix.
4. **Grounded in this project.** Reference real paths, real commands (`CLAUDE.md →
   Commands`; implementers and QA run the quality gate with `framework/bin/fw check`), real
   conventions. Generic advice ("write clean code") is noise.
5. **Current, not remembered.** Versions, APIs and best practices of the stack are checked
   against official documentation at creation time (web search/fetch when available), and
   written down with the date checked. Never hard-code what a file in the repo already says —
   point to the file.
6. **Contract-driven.** Every agent ends with a machine-readable status line so the
   orchestrator can chain agents without guessing (see *Output tokens*).
7. **Knows when to stop.** Explicit escalation: what it must not decide alone, and how to
   say so.
8. **Safe.** Never prints or commits secrets; never weakens tests to make them pass; never
   touches `framework/` (owned by the upstream template).
9. **Prompt in English, output in the user's language** when it writes for humans (issue
   comments, PR text, docs), as configured in `.fw/config.json`.

## Required structure
```markdown
---
name: kebab-case, same as the file name
description: What it does + when to use it (one or two sentences, >= 60 chars)
tools: Read, Grep, Glob, Bash[, Edit, Write]
model: (optional) omit to inherit; a cheaper model is fine for mechanical roles
---
## Mission        — one paragraph: the outcome this agent is accountable for
## Scope          — owns / does not own (paths, layers, decisions)
## Inputs         — what the orchestrator gives it (issue number, diff, files) and what to read first
## Procedure      — numbered, concrete steps, with the project's real commands
## Quality bar    — the checklist its output must satisfy before reporting
## Output contract — exact shape of the final message, ending with its status token
## Escalation     — when to stop and report NEEDS_INPUT / BLOCKED instead of guessing
```

## Output tokens (checked by `fw lint-agents` for mapped roles)
| Role (`.fw/config.json → roles`) | Final line |
|---|---|
| `spec` | `SPEC: READY` or `SPEC: NEEDS_INPUT` (+ questions) |
| `implement` | `STATUS: DONE` or `STATUS: BLOCKED` (+ reason), with files changed and tests run |
| `review` | `VERDICT: APPROVE` or `VERDICT: CHANGES_REQUESTED` (+ findings with severity and file:line) |
| `qa` | `QA: PASS` or `QA: FAIL` (+ one line of evidence per acceptance criterion) |
| `docs` | `DOCS: UPDATED` (+ files) or `DOCS: NO_CHANGE` |

## Typical team (recommend, never impose)
| Role | When to recommend |
|---|---|
| Product owner (`spec`) | Always — refines issues, arbitrates scope, writes assumptions down |
| Implementer per major layer (`implement`) | One per real stack layer (e.g. backend PHP, frontend Vue). Not one per language feature |
| Code reviewer (`review`) | Always — the gate before merge, essential in auto mode |
| QA / test engineer (`qa`) | Always when acceptance criteria are user-facing |
| Doc writer (`docs`) | Always — keeps docs and `CLAUDE.md` true |
| Architect | Non-trivial systems, several services, or brownfield refactors |
| Security reviewer | Auth, personal data (GDPR), payments, public APIs |
| Database specialist | Rich schema, migrations on live data, performance-sensitive queries |
| DevOps | Deployment, containers, infrastructure as code |
| UX / accessibility | Public-facing UI |

Keep the team small (4–7). Every extra agent costs context and coordination.

## Review checklist (run it on each generated agent)
- [ ] Would a newcomer understand from `description` alone when to call it?
- [ ] Are the commands in *Procedure* the ones in `CLAUDE.md`, and do they work?
- [ ] Does *Quality bar* contain checks specific to this stack (not generic)?
- [ ] Are stack versions verified today and dated?
- [ ] Is the *Output contract* token present and unambiguous?
- [ ] Is *Escalation* explicit about business decisions, credentials and destructive actions?
- [ ] Is it explained in plain language in `docs/agents/team.md`?
