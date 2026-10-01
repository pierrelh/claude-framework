---
name: fw-dashboard
description: Show the project dashboard — overall progress bar, milestones with due dates and on-track / at-risk / late health, epics, flow (backlog → done), what is in flight and what needs the user, burn-up and pace with a forecast end date, the upcoming roadmap as a timeline, estimate accuracy, and the project's own metrics. In the terminal, or as an HTML page opened in the browser. Use when the user asks for the dashboard, a progress overview, a burn-up / roadmap view, or "show me where we are" visually.
argument-hint: "[html] — default: terminal view"
---

# /fw-dashboard

1. Run one command:
   - terminal (default): `framework/bin/fw dashboard`
   - `html` argument, or the user wants charts: `framework/bin/fw dashboard --html --open`
     (self-contained page in `.fw/local/dashboard.html`, no external resource; say where it
     is if no browser opens, e.g. on a remote machine).
   Show the terminal output as is (it is already formatted).
2. Then 3–5 lines in the user's language, only what matters:
   - milestones **late** or **at risk** (planned date after the due date) and why
     (remaining hours vs pace);
   - the gap between *planned end* (roadmap) and *forecast* (current pace) when it is
     more than a week — suggest `/fw-plan`;
   - items that **need the user**, hotfixes;
   - actual/estimate ratio outside 0.7–1.3 → suggest `/fw-retro`.
   No problem → one sentence saying so.
3. Project metrics: `.fw/config.json → dashboard.metrics` adds the project's own figures
   (tiles in HTML, lines in the terminal). Each entry runs a command in the project root that
   prints a number, or JSON `{"value", "target", "unit", "detail"}`:
   ```
   framework/bin/fw config set dashboard.metrics '[{"title": "Test coverage", "unit": "%",
     "target": 80, "command": "jq .totals.percent_covered coverage.json"},
     {"title": "Open Sentry issues", "better": "lower", "target": 0, "command": "…"}]'
   ```
   Offer it when the user asks for "other metrics"; commands must be read-only and fast
   (30 s timeout each, `--no-custom` skips them).
