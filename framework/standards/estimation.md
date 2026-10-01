# Standard — estimation and roadmap

Estimates are in **hours**, for work done **by an AI agent**, plus the **human review** time
the story will cost the user. They feed the Roadmap view through `fw schedule`.

## What `agent_hours` covers
Wall-clock time of the agent team for the story, end to end: reading context → implementing
→ writing tests → running the suite → review/fix loops → docs → PR. Not the calendar time the
issue waits in the queue.

## Reference scale
| Size | agent + review | Typical content |
|---|---|---|
| XS | ≤ 1 h | Copy change, config flag, trivial fix with a test |
| S | ≤ 3 h | One endpoint or one screen on an existing pattern |
| M | ≤ 6 h | Feature touching 2–3 layers (DB + logic + UI), new pattern once |
| L | ≤ 12 h | New module, external integration, non-trivial migration |
| XL | > 12 h | **Not allowed** — split |

## Multipliers (apply before choosing the size)
- Technology new to the project, or no existing pattern to copy: ×1.5
- External API / third-party integration (sandbox, auth, webhooks): ×1.5
- Data migration on existing data: ×1.5
- Polished UI (pixel work, responsive, accessibility audit): ×1.3
- Security-sensitive (auth, payments, personal data): ×1.3 **and** a security review
- Brownfield code without tests: ×1.5 (tests must be written around the change first)

## `review_hours` — the human's time
| Autonomy / risk | Review hours |
|---|---|
| Auto mode, low risk | 0 – 0.25 (the user skims the merged PR later) |
| Assisted mode, normal story | 0.25 – 0.5 |
| Security, money, data migration, public API | 0.5 – 2 (always human-reviewed, even in auto mode) |

## Discussing estimates with the user
Present estimates as a table per epic with totals per milestone. Invite the user to
challenge them: they may know the domain complexity better. Record any change in the
backlog file before applying, or with `fw set-field <n> "Agent effort (h)" <h>` afterwards.

## Scheduling model (`fw schedule`)
- Capacity from `.fw/config.json → capacity`: `hours_per_day` (default 6 — the hours per day
  the user actually lets agents run), `parallel_lanes` (default 1 — stories worked on at the
  same time), `workdays` (ISO numbers, default Mon–Fri), optional `start_date`, `order`
  (`milestone` — default — or `priority`).
- Items are ordered by dependencies, then in-progress first, then **milestone** (earlier
  milestones first; `order: priority` skips this), then priority (Must → Could), then issue
  number. `Won't` items are not scheduled.
- Each agent item occupies `agent_hours + review_hours` on the first free lane, never before
  its dependencies end. **Human items** (`owner: human` / `needs-human`) run on a separate
  human lane and don't consume agent capacity. `wait_days` is added after the work as
  waiting time (in workdays) before dependents can start.
- The report gives, per milestone, the date its **Musts** are done and the date everything is
  done. Hours are converted to workdays; epics span their children; milestone due
  dates are the latest target date of their items.
- Closed items keep their dates. Re-run `fw schedule --apply` whenever scope, estimates or
  capacity change — `/fw-work` does it after every merged story.

## Calibration
`fw start`, `fw review` and `fw escalate` log a timeline per item (`.fw/local/timers.json`).
`fw done` turns it into **Actual (h)** — agent working time only (from each start to the
pull request or an escalation) — comparable with **Agent effort (h)**, and **Wait (h)** —
time spent waiting on a human (PR approval, escalation answers). `--rounds` records the
review rounds. Human review effort is not measured.
`fw status` prints the actual/estimated ratio and `fw metrics` breaks it down by size, type
and agent. When it drifts beyond ±30 % over 5+ items, tell the user and scale the remaining
estimates (or the capacity) accordingly; `/fw-retro` does this analysis per milestone and
records the calibration in `CLAUDE.md`, which `/fw-backlog` and `/fw-plan` apply.
