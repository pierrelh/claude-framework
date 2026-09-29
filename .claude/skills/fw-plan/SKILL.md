---
name: fw-plan
description: Discuss estimates and capacity with the user and compute the roadmap — start/target dates on every issue, epic spans and milestone due dates on GitHub, plus a Markdown snapshot. Use after creating backlog items, when estimates or priorities change, or to answer "when will it be done?".
argument-hint: "[optional: what to re-plan, e.g. 'we can run 10 h/day now']"
---

# /fw-plan — estimates and roadmap

Read `framework/standards/estimation.md` first.

## 1. Capacity (ask once, then only when it changes)
Current values: `framework/bin/fw config get capacity`. Ask in plain words:
- How many hours per day will agents actually run? (a session the user keeps open; in auto
  mode it can be more — `hours_per_day`, default 6)
- How many stories in parallel? (`parallel_lanes`, default 1; >1 only in auto mode with
  independent stories)
- Which days? (`workdays`, ISO 1–7, default Mon–Fri) · Start date? (`start_date`, default today)
Save with `framework/bin/fw config set capacity.hours_per_day 8` etc.

## 2. Estimates
- Items without estimates (e.g. imported issues): estimate them from their content with the
  scale and multipliers, then `framework/bin/fw set-field <n> "Agent effort (h)" <h>`,
  `… "Human review (h)" <h>`, `… Size <S>`.
- `framework/bin/fw status` shows the actual/estimated ratio: if it drifts beyond ±30 % over
  5+ done items, propose scaling the remaining estimates and explain why.
- Present the riskiest estimates and let the user challenge them; apply changes with
  `set-field`.

## 3. Compute and publish
```
framework/bin/fw schedule                       # preview
framework/bin/fw schedule --apply --markdown docs/product/roadmap.md
```
Report in the user's language: projected end per milestone, the critical path (longest
dependency chain), what would move the date the most (capacity, a big story, a dependency).
Remind them the Roadmap view on GitHub now shows the plan.
