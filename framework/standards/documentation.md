# Standard — documentation

Two audiences, one source of truth: **the repository**. Docs change in the same pull request
as the code they describe.

## Where things go
| Audience | Location | Content |
|---|---|---|
| Agents (every session) | `CLAUDE.md` | Stack + versions, commands (install, run, test, lint, build), conventions, short architecture, pointers. **≤ 150 lines** — it is loaded in every session. |
| Agents (role-specific) | `.claude/agents/*.md` | How each role works on this project. |
| Humans | `docs/index.md` | Entry point, what the project is, how to navigate. |
| Humans | `docs/product/` | Brief, glossary, generated roadmap snapshot. |
| Humans | `docs/architecture/` | Overview (with a Mermaid diagram), components, data model, decisions (ADR). |
| Humans | `docs/guides/` | Getting started, "how my stack works" explanations, operations/runbooks. |
| Humans | `docs/agents/team.md` | The agent team in plain language: who does what, when, and how to ask them. |
| Everyone | `docs/framework/` | How the framework works (owned by the template — do not edit). |

## Rules
- **Relative Markdown links** (`[text](../guides/getting-started.md)`), not `[[wikilinks]]`:
  they work in GitHub, Obsidian (configured for Markdown links) and MkDocs.
- Diagrams in **Mermaid** fenced blocks (rendered by GitHub, Obsidian and MkDocs Material).
- Explain for a newcomer: what it is, why it is this way, how to use it — then details.
  The user may not be a developer: "how my stack works" guides avoid jargon or define it.
- Record significant decisions as ADRs (`docs/architecture/decisions/NNNN-title.md`, template
  in `framework/templates/adr.template.md`): choosing a library, a pattern, a trade-off.
- Don't duplicate: `CLAUDE.md` summarises and links to `docs/`; docs link to code paths.
- Never document secrets. Document where they come from (`.env.example`, secret manager).
- Run `fw docs-check` before committing docs (broken links fail it).

## Tooling
- **Obsidian**: open the `docs/` folder as a vault. `docs/.obsidian/app.json` is committed
  with Markdown-link settings; workspace files are git-ignored.
- **MkDocs Material** (optional site / GitHub Pages): `pip install mkdocs-material`, then
  `mkdocs serve`. `/fw-docs` can install the Pages workflow from
  `framework/templates/workflows/docs.yml`.
