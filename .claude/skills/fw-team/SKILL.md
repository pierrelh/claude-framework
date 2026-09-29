---
name: fw-team
description: Design this project's AI agent team from its stack and brief — recommend roles with reasons, let the user choose, then write each agent in .claude/agents/ to the framework's quality standard and map roles in the config. Use during /fw-init, when the stack changes, or when an agent under-performs.
---

# /fw-team — build the agent team

There is no agent library: you write agents for **this** project, today, against
`framework/standards/agent-quality.md` (read it first — it is the quality bar).

## 1. Inputs
Read `docs/product/brief.md`, `CLAUDE.md` (Stack, Commands, Conventions), `.fw/config.json`
(`stack`, `autonomy`, existing `roles`), existing `.claude/agents/*.md` (revision mode).

## 2. Recommend
Derive the competencies the project really needs: one implementer per real stack layer,
plus the always-recommended roles (product owner, code reviewer, QA, doc writer), plus
conditional ones (architect, security, database, devops, UX/a11y) only when the brief
justifies them. Present a table in the user's language:

| Agent | Role in plain words | Why for this project | Recommended |

Keep it to 4–7 agents. In auto mode, insist on reviewer + QA (they are the merge gate).
Then let the user choose (AskUserQuestion, multiSelect, recommended ones first). If they
drop the reviewer or QA, say what that changes (the orchestrator will do a lighter review
itself) and accept their choice.

## 3. Research before writing
For each implementer/specialist: check current stable versions, official conventions,
recommended tooling (test runner, linter, formatter, static analysis) from official
documentation (WebSearch/WebFetch when available). Note the date. If a tool is not yet
installed in the project, the agent's procedure says to use it once the walking skeleton
adds it — and the walking-skeleton task must add it.

## 4. Write the agents
For each chosen agent, create `.claude/agents/<name>.md` from
`framework/templates/agent.template.md`:
- `name` kebab-case = file name (e.g. `php-developer`, `code-reviewer`).
- `description`: what + when, specific enough for the orchestrator to choose it.
- `tools`: least privilege — reviewer/QA/product-owner read-only (`Read, Grep, Glob, Bash`),
  implementers and doc writer get `Edit, Write` too.
- Procedure with the project's **real** commands and paths; quality bar specific to the
  stack (e.g. PHP: strict types, PSR-12, PHPStan level, no SQL string concatenation…);
  output contract ending with the role token; explicit escalation rules.
- Prompts in English; human-facing outputs in the configured languages.

## 5. Map roles and lint
```
framework/bin/fw config set roles '{"spec":"product-owner","implement":["php-developer","vue-developer"],"review":"code-reviewer","qa":"qa-engineer","docs":"doc-writer"}'
framework/bin/fw lint-agents
```
Fix every ✘ and re-run until clean. Then walk the checklist at the end of the standard
yourself and fix what fails.

## 6. Explain to the human
Write `docs/agents/team.md` in `docs_language`: one short section per agent (what it does,
when it intervenes in the workflow, what it will never do), a Mermaid diagram of the story
flow (spec → implement → review → QA → docs → PR → merge), and how to call an agent
directly ("ask Claude: *use the code-reviewer agent on this branch*").

## 7. Hand-over
New agent files are picked up at the next start of Claude Code; `/fw-work` falls back to a
general-purpose subagent carrying the agent's file until then.
