---
name: fw-status
description: Summarise where the project stands — progress per milestone, hours done and remaining, projected end, items in progress or in review, open pull requests, items needing a human, and what is next. Use when the user asks for status, progress, or "where are we".
---

# /fw-status

Run in one Bash call:
```
framework/bin/fw status; echo; framework/bin/fw next --limit 5; echo; gh pr list --limit 10
```
Answer in the user's language, short:
1. One sentence overall (e.g. "MVP 60 % done, on track for 14 Nov").
2. Milestones with done/total and projected dates.
3. In progress / in review, open PRs (links).
4. **Needs you**: `needs-human` items and PRs waiting for approval in assisted mode — with
   what exactly is expected from the user.
5. Next up (top 3) and the suggested command (`/fw-work`, `/fw-work all`).
If the estimate accuracy ratio drifts beyond ±30 %, mention it and suggest `/fw-plan`.
