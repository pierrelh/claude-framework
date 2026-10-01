---
name: fw-resume
description: Continue a /fw-work run stopped with /fw-stop (or interrupted by a crash or a closed session) — take back every paused item at its saved step with its notes and findings, then go on with the run's original arguments. Use when the user types /fw-resume or asks to continue / pick up where the agents stopped.
argument-hint: "[#issue] — default: the whole paused run"
---

# /fw-resume — pick up where the run stopped

1. Show what can be resumed (one Bash call):
   `framework/bin/fw resume --run; framework/bin/fw resume`.
   Nothing paused and nothing in flight → say so and suggest `/fw-work`.
2. Assisted mode: summarise (paused run, items with their step and next action, items
   paused on another machine that stay there) and confirm. Auto mode: go on.
3. Run `/fw-work resume` — follow `.claude/skills/fw-work/SKILL.md` → *Resuming* (it clears
   the stop request, takes each paused item back with `fw resume <n>`, continues at its step,
   then continues the run). With an `#issue` argument: resume only that item, then stop.
