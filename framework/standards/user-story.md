# Standard — backlog items (epics, user stories, tasks, bugs)

Every item created on GitHub must be **qualified** (clear who/what/why), **testable**
(acceptance criteria a QA agent can verify) and **measured** (estimate + success measure).
`fw backlog-validate` enforces the mechanical part of this standard; this document is the
part that needs judgement.

## Language
Write items in `issue_language` from `.fw/config.json` (the user's language, or English if
they chose so). Keys, field names and code identifiers stay in English.

## Hierarchy
- **Milestone** — a releasable increment (`MVP`, `v1.1`, `POC`). A POC has one milestone.
- **Epic** — a user-facing capability (e.g. "Account management"). Has a goal and a success
  measure. Stories are attached as GitHub sub-issues.
- **Story** — a vertical slice of value for a persona, deliverable in one pull request.
- **Task** — technical enabler with no direct user value (project skeleton, CI, deployment,
  migration). Keep them few: prefer folding technical work into the story that needs it.
- **Bug** — observed behaviour ≠ expected behaviour.

## A good story (INVEST)
- **Independent** — can be merged on its own; dependencies are explicit (`depends_on`).
- **Negotiable** — describes the need, not the implementation.
- **Valuable** — the `so that` states a real benefit for the persona, not "so that it is done".
- **Estimable** — the agent can estimate it; if not, write a time-boxed spike Task first.
- **Small** — at most **L** (≤ 12 h agent + review). XL is rejected: split it.
- **Testable** — each acceptance criterion is observable and binary (pass/fail).

## Fields (backlog JSON → issue)
| Field | Rule |
|---|---|
| `key` | Stable id: `M1`, `E1`, `US-1`, `T-1`, `BUG-1`. Never reused. |
| `title` | ≤ 90 chars, starts with a verb or the capability: "Reset password by email". |
| `persona` / `want` / `benefit` | "As a *registered customer*, I want *…*, so that *…*". A named persona, not "user". |
| `context` | Why now, business rules, links. Optional but encouraged. |
| `acceptance_criteria` | ≥ 2 for stories. Prefer `{given, when, then}`. Cover the main path **and** at least one edge/error case. |
| `measure` | How we know it delivered value: a metric, threshold or observable outcome ("password reset completes in < 2 min; reset emails < 1 % bounce"). For a POC: "demonstrable in the demo script". |
| `technical_notes` | Constraints and hints for the implementer (not a design). |
| `out_of_scope` | What this story deliberately does not do — prevents gold-plating by agents. |
| `agent_hours` / `review_hours` / `size` | See [estimation.md](estimation.md). |
| `agent` | Name of the implementing agent from `.claude/agents/`. |
| `priority` | MoSCoW: `Must`, `Should`, `Could`, `Won't`. |
| `depends_on` | Keys of this file or `#123` for existing issues. Avoid depending on an item of a *later* milestone (`fw backlog-validate` warns). |
| `owner` | `agent` (default) or `human` — work only the user can do (create an account, choose a name, legal validation). Human tasks get the `needs-human` label, no agent, `agent_hours` may be 0 and `review_hours` is the user's own time. |
| `wait_days` | Workdays of waiting after the work is done, on nobody's time (store review, account approval, an answer from a third party). Delays dependents in the roadmap. |

## Splitting patterns (when a story is too big)
By workflow step · by business rule · happy path first then errors · by data variation ·
by interface (API then UI) · read before write · simple before complex (defer options,
performance, i18n).

## First items of a new project
1. **Walking skeleton** (Task): repository layout, dependency manager, one trivial end-to-end
   path, test runner, linter, CI pipeline green. Everything else depends on it.
2. The thinnest end-to-end version of the core value story.
3. Then breadth.

## Definition of Done (appended to every story by `fw`)
Acceptance criteria verified · automated tests added and passing · reviewed and approved ·
docs updated (user docs + `CLAUDE.md` when conventions or commands change) · CI green.
Add story-specific items with `dod_extra`.

## Example (French)
```json
{
  "key": "US-4", "type": "Story", "epic": "E2", "priority": "Must",
  "title": "Réinitialiser son mot de passe par e-mail",
  "persona": "client inscrit", "want": "recevoir un lien de réinitialisation par e-mail",
  "benefit": "retrouver l'accès à mon compte sans contacter le support",
  "acceptance_criteria": [
    {"given": "un e-mail inscrit", "when": "je demande une réinitialisation", "then": "je reçois un lien valable 30 minutes"},
    {"given": "un lien expiré", "when": "je l'ouvre", "then": "un message m'invite à refaire une demande"},
    {"given": "un e-mail inconnu", "when": "je demande une réinitialisation", "then": "le même message neutre s'affiche (pas de fuite d'information)"}
  ],
  "measure": "95 % des réinitialisations aboutissent en moins de 2 minutes",
  "out_of_scope": ["Authentification à deux facteurs"],
  "agent_hours": 4, "review_hours": 0.5, "size": "M", "agent": "php-developer",
  "depends_on": ["US-2"]
}
```
