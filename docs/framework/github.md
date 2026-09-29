# GitHub setup

`framework/bin/fw github-setup` creates (or reuses) everything below on **your** account.

## Requirements
- GitHub CLI ≥ 2.40, logged in: `gh auth login -h github.com -s repo,project,workflow`
- Already logged in without the scopes: `gh auth refresh -h github.com -s project,workflow`
- `/fw-doctor` checks all of this and explains each fix.

## What gets created
| Item | Details |
|---|---|
| Repository | private by default, on your account |
| Project (v2) | linked to the repository (appears in its *Projects* tab) |
| Status | Backlog → Ready → In progress → In review → Done |
| Fields | Item type (Epic/Story/Task/Bug), Priority (Must/Should/Could/Won't), Size (XS–XL), Agent effort (h), Human review (h), Actual (h), Start date, Target date, Agent. `Type` is reserved by GitHub for built-in issue types, hence `Item type`. |
| Labels | epic, story, task, bug, blocked, needs-human |
| Milestones | from the backlog; due date = latest target date of their items |
| Relations | stories are sub-issues of their epic; dependencies are GitHub "blocked by" links (plus a hidden `fw:depends-on` marker the scheduler reads) |

## Views — one manual step
GitHub's API cannot create project views. After setup, open the project and add:
1. **Kanban** — *New view → Board*, column by **Status**.
2. **Roadmap** — *New view → Roadmap*, date fields **Start date** / **Target date**, group by
   **Milestone**.
`framework/bin/fw views-check` verifies them.

**Tip — skip this step next time**: once a project has both views, put its `owner/number`
in `framework.template_project` of the template's `.fw/config.json`. New projects are then
*copied* from it (views included) instead of created empty.

## If the Status columns stay "Todo / In Progress / Done"
Customising the built-in Status field through the API may be refused depending on GitHub's
API version. The framework then maps its statuses onto the defaults automatically; you can
add *Backlog*, *Ready* and *In review* by hand in the project settings.
