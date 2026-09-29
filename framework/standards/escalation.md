# Standard — escalations (questions to the human)

When an agent run needs a human decision, it **escalates** in a structured way, so the
question reaches the user wherever they are: in the terminal, on GitHub, or in a tool/app
built on the framework. The machine-readable part is versioned with the contract
(`fw schema --json → escalation`).

## Kinds
| Kind | When |
|---|---|
| `question` | A business rule, UX or scope choice the spec does not settle (`SPEC: NEEDS_INPUT`) |
| `approval` | Assisted mode: before starting a story, before merging a PR |
| `blocked` | Credentials, paid service, production access, 3 failed review rounds, broken tooling |

## Lifecycle
`open` → `answered` → `resolved`, recorded as issue comments with hidden markers:
- `fw escalate <n> --kind … --question "…" [--option … --recommended 0] [--pr N]` posts the
  question (`<!-- fw:escalation {json} -->`) and adds the `needs-human` label;
- the human answers with a comment starting with `/answer <text>`, or a tool runs
  `fw answer <n> "<text>"` (`<!-- fw:answer {json} -->`);
- the run that uses the answer calls `fw resolve <n>` (`<!-- fw:resolved {json} -->`), which
  removes `needs-human` once no escalation is left on the issue.
`fw escalations --json` lists the open and answered ones (all `needs-human` issues, or `--issue N`).

## Interactive vs headless sessions
- **Interactive** (a human at the terminal): post the escalation, then ask with
  AskUserQuestion. The question text starts with `[fw:<kind> <id>]` (the id printed by
  `fw escalate`) so tools driving the session can link it to the GitHub escalation. Then
  `fw resolve <n> --answer "<answer>"`.
  **Approvals in interactive assisted mode** don't need a GitHub comment: ask directly with
  the prefix `[fw:approval start #<n>]` or `[fw:approval merge #<n> pr #<m>]`.
- **Headless** (`FW_HEADLESS=1` or `CI=true` — cloud runs, SDK-driven runs without a question
  channel): post the escalation, set the item back to Ready, and stop working on it. A later
  run picks it up once it is `answered`.

## Writing a good escalation
One decision per escalation; options that are complete and mutually exclusive, the
recommended one first; enough context to decide on a phone without opening the code.
