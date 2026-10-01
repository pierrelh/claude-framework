---
name: fw-stop
description: Stop the running /fw-work cleanly — finish the current step, start nothing new, save a checkpoint for every item in flight (step, next action, context, unresolved findings) and for the run, then end; /fw-resume continues later. Use when the user types /fw-stop (after pressing Esc), or writes "stop" / "pause" / "arrête" while a run is working — a plain-text message reaches Claude between two tool calls, a queued slash command only after the run.
argument-hint: "[now] [remote] [reason…] — now: don't wait for background reviews; remote: also stop cloud runs"
---

# /fw-stop — stop a run cleanly

Arguments: `$ARGUMENTS` — `now`, `remote`, and anything else is the reason.

1. Record the request (this is what blocks new work, through the guard):
   `framework/bin/fw stop [--now] [--remote] [--reason "<reason>"]`.
2. **Was `/fw-work` running in this session** (this message arrived during a run, or the user
   pressed Esc to interrupt one)? Then follow `/fw-work` → *Stopping* now:
   - if Esc interrupted an agent in the middle of its work, its step is unfinished: say so
     in that item's checkpoint (`--step` = that step, `--next` = "check the worktree state,
     then redo <step>"), don't try to complete it;
   - graceful: wait for the background reviewers / QA still running and keep their results;
     `now`: don't wait;
   - `framework/bin/fw checkpoint <n> --step … --next "…" --note "…" [--findings-file …]`
     for **every** item in flight, then `framework/bin/fw checkpoint --run --args "…"`.
3. **No run in this session** (the run is in another terminal, or a cloud run with `remote`):
   the request is enough — that run sees it at its next step and checkpoints itself. Say so.
4. Report in the user's language, short: what was paused (item, step, next action), what was
   already merged, and that `/fw-resume` continues exactly there (`fw stop --clear` lifts the
   stop without resuming).
