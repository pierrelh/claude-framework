---
name: fw-work
description: Implement backlog items end to end with the project's agent team — pick the next ready story, branch, spec check, implementation, tests, code review, QA against acceptance criteria, docs, pull request, merge, board and roadmap update. Chains stories autonomously in auto mode. Use to make progress on the project.
argument-hint: "[#issue | all | N (number of stories)] — default: the next ready story"
---

# /fw-work — deliver stories

You are the **orchestrator**. You don't write the feature yourself: you run the team defined
in `.fw/config.json → roles` and keep the board truthful. Read `CLAUDE.md`,
`framework/standards/git-workflow.md` and the config (`autonomy`, `roles`, languages) first.

Argument: `$ARGUMENTS` — `#12` (that item), `all` (until nothing is ready), `3` (three
items), empty (one item).

## Calling an agent
Use the Agent tool with `subagent_type: <agent name>`. If that agent type is not available
in this session (created after start-up), use a general-purpose agent and put the full
content of `.claude/agents/<name>.md` at the top of its prompt. Give each agent: the issue
number and body, the branch, the relevant file paths, and what the previous agent reported.
Parse its final status token (`SPEC:`, `STATUS:`, `VERDICT:`, `QA:`, `DOCS:`). If a role
has no agent, do that step yourself, briefly.

## Loop — for each item
0. **Preconditions**: clean working tree; `git checkout <default> && git pull`.
1. **Pick**: `framework/bin/fw next` (or the requested issue). Assisted mode: show the top
   candidates and confirm. Auto mode: take the first.
2. **Start**: `framework/bin/fw start <n>` — exit code 3 means the item is already in progress
   elsewhere (another machine or a cloud run): skip it and pick the next one, never `--force`
   without the user. Then `git checkout -b feat/<n>-<slug>` (`fix/` for bugs,
   `chore/` for tasks). Read the issue: `gh issue view <n> --comments`.
3. **Spec check** (spec agent): are the acceptance criteria clear and still valid against
   the code? `SPEC: NEEDS_INPUT` → assisted: ask the user; auto: if the product owner can
   decide with a reasonable, reversible assumption, it posts the assumption as an issue
   comment and continues; otherwise escalate (see below).
4. **Implement** (the agent in the issue's *Agent* field, else the first implementer):
   tests first where practical, then code, following `CLAUDE.md`. It must run the project's
   test/lint commands. `STATUS: BLOCKED` → escalate.
5. **Review** on `git diff <default>...HEAD` by **every** agent listed in `roles.review` (a
   string or a list — e.g. a code reviewer and a security reviewer), run in parallel. The
   step passes only when **all** return `VERDICT: APPROVE`. Any `CHANGES_REQUESTED` → send
   the merged findings back to the implementer; max **3** review rounds, then escalate.
6. **QA** (qa agent): verify every acceptance criterion with evidence (test names, command
   output, observed behaviour). `QA: FAIL` → back to step 4 (counts as a review round).
7. **Docs** (docs agent): update `docs/` and `CLAUDE.md` if behaviour, commands,
   conventions or architecture changed; ADR for significant decisions. `fw docs-check`.
8. **PR**: commit (Conventional Commits, `(#<n>)`), push the branch, `gh pr create` with the
   template filled: summary, `Closes #<n>`, acceptance-criteria checklist with QA evidence,
   review verdict, tests run, docs updated, estimate vs actual. Then
   `framework/bin/fw review <n>`.
9. **CI**: if the repo has workflows, `gh pr checks <pr> --watch` (fail → back to step 4).
10. **Merge**:
    - auto: when every reviewer APPROVE + QA PASS + CI green → `gh pr merge <pr> --squash --delete-branch`.
    - assisted: give the PR link and a 3-line summary; merge only when the user says so
      (or they merge on GitHub).
11. **Close the loop**: `git checkout <default> && git pull`; `framework/bin/fw done <n>`
    (records actual hours, unblocks dependents, closes the epic when complete);
    `framework/bin/fw schedule --apply --markdown docs/product/roadmap.md` (the snapshot is
    committed with the next PR).
12. **Continue?** auto + `all`/N: next item. Assisted: ask.

## Escalation — stop the item, never guess
Add the `needs-human` label and a comment explaining exactly what is needed, set the item
back to Ready (`fw set-status <n> ready`), switch back to the default branch (keep the
feature branch), and move to the next item. Escalate when:
- a business rule is ambiguous and a wrong guess is costly or irreversible;
- credentials, secrets, paid services or production access are needed;
- the change would delete or migrate existing data, touch payments/auth in a way the
  story did not foresee, or weaken security;
- 3 review/QA rounds failed, or the estimate is exceeded by more than 2× without an end in sight.
Stop the whole run (auto mode) after **3 escalations in a row** or if CI/tooling is broken
for every item.

## Parallel lanes (auto mode, `capacity.parallel_lanes` > 1)
Only for ready items with no dependency between them and no overlapping files. Run each
implementer with `isolation: "worktree"`, one branch/PR per item; review, QA and merge stay
sequential; rebase the later branches after each merge.

## Report (end of run)
Per item: #, title, result (merged / PR open / escalated — why), estimate vs actual. Then
`framework/bin/fw status` summary and the next ready items.
