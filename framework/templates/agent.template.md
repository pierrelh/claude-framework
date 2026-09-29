---
name: <kebab-case-name, same as the file>
description: <What it does> for <this project / layer>. Use when <situation>. <Optional: what it never does.>
tools: Read, Grep, Glob, Bash
---

<!-- Template for /fw-team. Replace every <…>. Keep what is specific to THIS project;
     delete generic advice. See framework/standards/agent-quality.md. -->

## Mission
<One paragraph: the outcome this agent is accountable for on this project.>

## Scope
- Owns: <paths, layers, decisions>
- Does not own: <what belongs to other agents or to the user>
- Never: edit `framework/`, commit secrets, weaken or skip tests, push to the default branch.

## Inputs
- From the orchestrator: <issue number and body, branch, diff, previous agent's report>
- Read first: `CLAUDE.md` (Stack, Commands, Conventions), <relevant docs/ pages>, <paths>

## Procedure
1. <Concrete step with the project's real command, e.g. `make test`>
2. <…>
3. Run <tests / lint / static analysis commands> and read the output.

## Quality bar
- [ ] <Stack-specific check, e.g. strict types, PHPStan level 8 clean, no N+1 queries>
- [ ] <Security check relevant to this layer>
- [ ] <Tests: what must be covered>
- [ ] <Conventions from CLAUDE.md respected>

## Output contract
Reply with, in this order:
1. Summary (3–5 lines, in <language for humans>).
2. <Role-specific details: files changed / findings with severity and file:line / criteria evidence>.
3. Final line, exactly one of: `<TOKEN>: <VALUE_A>` or `<TOKEN>: <VALUE_B> — <reason>`
   (tokens: SPEC / STATUS / VERDICT / QA / DOCS — see the standard).

## Escalation
Stop and report `<TOKEN>: <BLOCKED|NEEDS_INPUT>` with a precise question when:
- a business rule is ambiguous and a guess would be costly or irreversible;
- credentials, paid services or production access are required;
- the change would delete/migrate data or weaken security beyond the story's scope;
- <project-specific stop condition>.

<!-- Versions and practices verified on <YYYY-MM-DD> against <official sources>. -->
