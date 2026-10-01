---
name: fw-work
description: Implement backlog items end to end with the project's agent team — pick the next ready story, branch, spec check, implementation, tests, code review, QA against acceptance criteria, docs, pull request, merge, board and roadmap update. Chains stories autonomously in auto mode. Use to make progress on the project.
argument-hint: "[#issue | all | N (number of stories) | resume] — default: the next ready story"
---

# /fw-work — deliver stories

You are the **orchestrator**. You don't write the feature yourself: you run the team defined
in `.fw/config.json → roles` and keep the board truthful. Read `CLAUDE.md`,
`framework/standards/git-workflow.md` and the config (`autonomy`, `roles`, languages) first.

Argument: `$ARGUMENTS` — `#12` (that item), `all` (until nothing is ready), `3` (three
items), empty (one item), `resume` (continue a run stopped with `fw stop`, see *Stopping*).
A new run starts with `framework/bin/fw stop --clear` — except `resume`, which reads the
paused run first (`fw resume --run --json`) and then clears it.

## Calling an agent
Use the Agent tool with `subagent_type: <agent name>`. If that agent type is not available
in this session (created after start-up), use a general-purpose agent and put the full
content of `.claude/agents/<name>.md` at the top of its prompt. Give each agent: the issue
number and body, the branch, the relevant file paths, and what the previous agent reported.
Parse its final status token (`SPEC:`, `STATUS:`, `VERDICT:`, `QA:`, `DOCS:`). If a role
has no agent, do that step yourself, briefly.

## Loop — for each item
0. **Resume first**: `framework/bin/fw resume --json` lists the items left in progress / in
   review (a crash, a closed session, a merge done on GitHub). For each item started on this
   machine, continue it from the `step` it gives (11 = close the loop, 9 = PR open, 5 =
   commits without PR, 4 = uncommitted work on its branch — don't stash or reset it, 3/2 =
   restart the item); `step: null` = started elsewhere or PR closed without merge: leave it,
   mention it in the report. With the pipeline on, reuse each item's worktree
   (`fw worktree list`). Only then:
   **Preconditions**: clean working tree; `git checkout <default> && git pull`.
   Headless session (`FW_HEADLESS=1` or `CI=true`): you cannot ask anyone — every question
   goes through `fw escalate` (see *Escalation*).
1. **Pick**: first resume answered questions — `framework/bin/fw escalations --json`, items in
   state `answered` go first (use the answer, then `fw resolve <n>` once applied). Otherwise
   `framework/bin/fw next` (or the requested issue) — `hotfix` items always come first.
   Assisted mode: show the top candidates and confirm. Auto mode: take the first.
2. **Start**: `framework/bin/fw start <n>` — exit code 3 means the item is already in progress
   elsewhere (another machine or a cloud run): skip it and pick the next one, never `--force`
   without the user. Then `git checkout -b feat/<n>-<slug>` (`fix/` for bugs,
   `chore/` for tasks). Read the issue: `gh issue view <n> --comments`.
3. **Spec check** (spec agent): are the acceptance criteria clear and still valid against
   the code? `SPEC: NEEDS_INPUT` → assisted: escalate as a `question` and ask the user; auto: if the product owner can
   decide with a reasonable, reversible assumption, it posts the assumption as an issue
   comment and continues; otherwise escalate (see below).
4. **Implement** (the agent in the issue's *Agent* field, else the first implementer):
   tests first where practical, then code, following `CLAUDE.md` and `.claude/review-rules.md`
   (when present — the rules reviewers will check). It must run
   `framework/bin/fw check` (the project's lint/typecheck/test/build commands) and finish green.
   `STATUS: BLOCKED` → escalate.
5. **Review** on `git diff <default>...HEAD` by **every** agent listed in `roles.review` (a
   string or a list — e.g. a code reviewer and a security reviewer), run in parallel. The
   step passes only when **all** return `VERDICT: APPROVE`. Reviewers also check every rule
   of `.claude/review-rules.md` (when present). Any `CHANGES_REQUESTED` → send the merged
   findings back to the implementer; max **3** review rounds, then escalate. Keep every
   finding (`category — one line`, e.g. `security — SQL built by concatenation in
   OrderRepository`) and count the rounds: both go into the PR and feed `/fw-retro`.
6. **QA** (qa agent): run `framework/bin/fw check` and verify every acceptance criterion with
   evidence (test names, command output, observed behaviour). `QA: FAIL` → back to step 4 (counts as a review round).
7. **Docs** (docs agent): update `docs/` and `CLAUDE.md` if behaviour, commands,
   conventions or architecture changed; ADR for significant decisions. `fw docs-check`.
8. **PR**: commit (Conventional Commits, `(#<n>)`), push the branch, `gh pr create` with the
   template filled: summary, `Closes #<n>`, acceptance-criteria checklist with QA evidence,
   review verdict, **review findings** (all rounds, `category — finding`, or "none"), review
   rounds, tests run, docs updated, estimate vs actual. Then
   `framework/bin/fw review <n>`.
9. **CI**: if the repo has workflows, `gh pr checks <pr> --watch` (fail → back to step 4). CI
   runs the same `fw check` as the agents, so a red CI that was green locally points at the
   environment (versions, services, missing `install` command) — fix that, not the test.
10. **Merge**:
    - auto: when every reviewer APPROVE + QA PASS + CI green → `gh pr merge <pr> --squash --delete-branch`.
    - assisted: give the PR link and a 3-line summary; ask with the prefix
      `[fw:approval merge #<n> pr #<pr>]` and merge only when the user says so (or they merge
      on GitHub). Headless: `fw escalate <n> --kind approval --pr <pr> …` and move on.
11. **Close the loop**: `git checkout <default> && git pull`; `framework/bin/fw done <n>
    --rounds <review rounds>` (records agent hours and waiting time — measured from
    `fw start` / `fw review` / `fw escalate` on this machine —, unblocks dependents, closes
    the epic when complete);
    `framework/bin/fw schedule --apply --markdown docs/product/roadmap.md` (the snapshot is
    committed with the next PR).
12. **Continue?** auto + `all`/N: next item. Assisted: ask. When the item closed the last
    open item of a milestone, suggest `/fw-retro <milestone>` (auto mode: run it at the end of
    the run, proposals wait for the user).

## Hotfix — short path for items labelled `hotfix`
Same loop, faster, without dropping a safety net:
- Branch `hotfix/<n>-<slug>`; skip the spec check when the bug has steps and expected /
  actual behaviour (otherwise escalate: a hotfix on a guess is worse than the bug).
- Implement **regression test first**: it must fail on the current code (quote the failure),
  then the smallest fix that makes it pass; no refactoring, no unrelated change.
- `fw check`, then one review by every `roles.review` agent focused on correctness and
  security of the diff (still max 3 rounds); QA verifies the regression test and the
  criteria. Docs only if behaviour visible to users changed.
- PR title `fix: <title> (#<n>)`, label `hotfix`; merge rules unchanged (assisted: the user
  approves; auto: green gates). Then suggest `/fw-release patch`.

## Escalation — stop the item, never guess
Follow `framework/standards/escalation.md`: `framework/bin/fw escalate <n> --kind
question|approval|blocked --question "…" --option "…" --recommended 0` (it posts a structured
comment and adds `needs-human`). Interactive session: then ask the user with AskUserQuestion,
question text prefixed `[fw:<kind> <id>]`, and `fw resolve <n> --answer "…"` — continue the
item with the answer. Headless session, or no answer possible now: set the item back to Ready
(`fw set-status <n> ready`), switch back to the default branch (keep the feature branch, push
it), and move to the next item. Escalate when:
- a business rule is ambiguous and a wrong guess is costly or irreversible;
- credentials, secrets, paid services or production access are needed;
- the change would delete or migrate existing data, touch payments/auth in a way the
  story did not foresee, or weaken security;
- 3 review/QA rounds failed, or the estimate is exceeded by more than 2× without an end in sight.
Stop the whole run (auto mode) after **3 escalations in a row** or if CI/tooling is broken
for every item.

## Review pipeline (`pipeline.enabled`, both modes)
One implementer that never waits for reviews; several readers in parallel. Turn it on or off
with `framework/bin/fw pipeline on|off [--wip N]` (default: at most **2** items in review).
The loop above still applies to each item; what changes is the scheduling:
- **Worktrees**: every item lives in its own worktree, `framework/bin/fw worktree add <n>`
  (prints the path, next to the repository: `<repo>.worktrees/<n>-<slug>`; branch
  `feat|fix|chore|hotfix/<n>-<slug>`); run `fw check install --if-configured` in it once.
  Give every agent the worktree's absolute path and tell it to work only there. Run `fw`
  board commands (`start`, `review`, `rework`, `done`, `escalate`…) from the main checkout;
  only the project's own commands (`fw check`) run inside the worktree.
- **One writer**: only one implementer runs at a time, in the foreground. When it finishes an
  item (step 4 green), `framework/bin/fw review <n>`, then launch the reviewers and QA for
  that item **in the background** (Agent `run_in_background`, all in parallel, read-only, in
  its worktree) and go straight on.
- **What next** — in this order, every time the implementer is free:
  1. **Rework**: an item came back (`CHANGES_REQUESTED`, `QA: FAIL`, red CI, rebase conflict)
     → `framework/bin/fw rework <n>`, implementer in that item's worktree with the complete
     findings (it remembers nothing: give the issue, the diff summary and every finding),
     `fw check`, `fw review <n>`, new background review of the changed diff.
  2. **New item** only if `framework/bin/fw pipeline --json` says `can_start` (the implementer
     is free and fewer than `review_wip` items are in review). Pick with `fw next`, skipping
     items that depend on an unmerged item (`fw next` already does) and items whose expected
     files (explorer map) overlap the diff of an item in review
     (`git diff --name-only <default>...<branch>`) — prefer another item, or wait.
  3. Otherwise wait for the next background result.
- **When a review/QA result arrives**: approved + QA PASS → docs agent in that worktree,
  commit, push, PR, `fw review` already done, CI in the background. Assisted mode: ask for the
  merge as usual — the implementer keeps working while you decide.
- **Merges one at a time**. After each merge: `fw done <n> --rounds <r>`,
  `fw worktree remove <n>`, then for every other item in review: `git rebase
  origin/<default>` in its worktree — clean → `fw check` (and `git push --force-with-lease`
  if its PR exists); conflicts → `git rebase --abort`, then it is rework (the implementer
  rebases and resolves, and the changed diff is reviewed again).
- **Assisted mode**: confirm once per run that the pipeline may start the next item while
  the previous one is in review, then confirm each item start as usual.
- Escalated items leave the pipeline (`needs-human` is not counted); their worktree stays.
  Stop starting new items when 2 items in a row come back from review — the queue is not
  converging; finish the rework first.
- `capacity.parallel_lanes` is ignored while the pipeline is on (one implementer by design);
  `fw schedule` then lets human review overlap the next item.

## Parallel lanes (auto mode, `capacity.parallel_lanes` > 1, pipeline off)
Only for ready items with no dependency between them and no overlapping files. Run each
implementer with `isolation: "worktree"`, one branch/PR per item; review, QA and merge stay
sequential; rebase the later branches after each merge.

## Stopping — `fw stop`, "stop", "pause", or Esc then "stop"
The user can stop a run at any time: `framework/bin/fw stop` from another terminal (`--now`:
don't wait for background reviews; `--remote`: also for cloud runs and other machines), or by
saying so in the session. Check `framework/bin/fw stop --check` (exit 1 = stop requested;
cheap, local — headless runs also look at the repository variable) **before picking an item,
after every agent returns, and before every merge**. While a stop is pending the guard refuses
new agents, `fw start`, `fw rework`, `fw worktree add` and `gh pr merge` — that is expected.
When a stop is requested:
1. Let the agent that is running finish its step; start nothing new. Graceful mode: wait for
   the background reviewers / QA and keep their results; `now` mode: don't wait — note them
   as "review running, re-run on resume".
2. Leave every working tree as it is: never stash, reset or commit half-done work to stop.
3. Checkpoint **every** item in flight, from the main checkout:
   `framework/bin/fw checkpoint <n> --step <step to resume at> --next "<the first concrete
   action on resume>" --note "<decisions taken, what was tried, review round, state of
   background agents>" [--findings-file <file with the unresolved findings, verbatim>]`.
   The note must let a fresh session continue without guessing — agents remember nothing.
   Items already merged need no checkpoint: run step 11 for them before stopping if
   `gh pr merge` already happened.
4. Checkpoint the run: `framework/bin/fw checkpoint --run --args "<what is left: all, or the
   remaining N>" --note "<pipeline state, escalation streak>"`.
5. Report what is paused and where, then end. Don't clear the stop request yourself.

## Resuming — `/fw-work resume`
1. `framework/bin/fw resume --run --json` (the paused run's arguments) and
   `framework/bin/fw resume --json` (every in-flight item; paused ones carry `checkpoint`).
2. `framework/bin/fw stop --clear`.
3. For each item with a checkpoint started on this machine: `framework/bin/fw resume <n>`
   (takes it back: timer resumed, checkpoint retired) and continue at its `step`, giving the
   agents its `next`, `note` and `findings`. Items paused on another machine with
   uncommitted work stay there — report them.
4. Continue the run with the saved arguments (`all`, or the remaining count).

## Report (end of run)
Per item: #, title, result (merged / PR open / escalated — why), estimate vs actual. Then
`framework/bin/fw status` summary and the next ready items.
