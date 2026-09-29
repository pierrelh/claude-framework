---
name: fw-docs
description: Audit and bring the documentation back in sync with the code — CLAUDE.md for agents, docs/ for humans (architecture, guides, agent team, glossary), ADRs, broken links; optionally publish with MkDocs on GitHub Pages. Use periodically, after large changes, or when docs feel stale.
argument-hint: "[optional: area to focus on | 'publish' to set up GitHub Pages]"
---

# /fw-docs — keep docs true

Standard: `framework/standards/documentation.md`. Use the docs agent (`roles.docs`) if there
is one; the orchestrator reviews its output.

## 1. Audit (read-only first)
- `CLAUDE.md`: every command still works? stack versions still right (manifests/lockfiles)?
  conventions still observed in recent code (`git log --stat -20`)? ≤ 150 lines?
- `docs/architecture/overview.md`: components and diagram match the code layout?
- `docs/guides/`: getting-started reproducible from scratch? A "how the stack works" guide
  exists for each major layer, in plain language?
- `docs/agents/team.md` matches `.claude/agents/` and `roles`.
- Decisions taken in merged PRs without an ADR.
- `framework/bin/fw docs-check` for broken links.
List the drifts found, grouped by file.

## 2. Fix
Apply the fixes on a `docs/<slug>` branch, keep explanations newcomer-friendly, re-run
`fw docs-check`, open a PR (merge per autonomy mode).

## 3. Publish (only when asked: `publish`)
Copy `framework/templates/workflows/docs.yml` to `.github/workflows/docs.yml`, check the
action versions it uses are current, and tell the user to enable **Settings → Pages →
Source: GitHub Actions**. Local preview: `pip install mkdocs-material && mkdocs serve`.
