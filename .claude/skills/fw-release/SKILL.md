---
name: fw-release
description: Cut a release — notes generated from the Conventional Commits since the last tag, semantic version bump, CHANGELOG and version files updated through a pull request, git tag, GitHub release, milestone closed. Always asks the user before publishing, even in auto mode. Use when a milestone is complete, after a hotfix, or when the user asks to release / ship / tag a version.
argument-hint: "[version | major | minor | patch] — default: computed from the commits"
---

# /fw-release — ship a version

Talk to the user in `language`; write the release notes in `docs_language`. Read
`framework/standards/git-workflow.md`. Argument: `$ARGUMENTS`.
A release is **public and outward-facing**: whatever the autonomy mode, the user confirms
the version and the notes before anything is tagged or published.

## 1. Prepare (one Bash call)
```
git checkout <default> && git pull; framework/bin/fw release-notes --json
framework/bin/fw status --json; gh release list --limit 3
```
- No commit since the last tag → say so and stop.
- `fw release-notes` reads the commits since the latest `v*` tag: `feat` → Added,
  `fix` → Fixed, `perf`/`refactor`/`revert` → Changed, `!` or `BREAKING CHANGE` → Breaking;
  `docs`/`chore`/`test`/`ci`/`build`/`style` are left out. It proposes the next version
  (breaking → major, or minor while 0.x; feat → minor; otherwise patch). The argument
  overrides it: a version, or `major`/`minor`/`patch` (compute it from `current`).
- First release (no tag): ask for the version (`0.1.0` for a first usable increment,
  `1.0.0` when the brief's first release is complete); pass `--current` if the code
  already carries a version.
- Check: open `needs-human` items or open PRs targeting this release → list them and ask
  whether to wait. Items of the milestone still open → this is a partial release; say so.

## 2. Confirm with the user
Show: version, the notes rewritten for humans (group the entries, merge the noisy ones, keep
the PR links, lead with Breaking), and what will happen (files changed, tag, GitHub release,
milestone closed). Wait for an explicit OK, and apply their edits.

## 3. Release pull request
On `chore/release-<version>`:
1. Prepend the notes to `CHANGELOG.md` at the root (create it with a `# Changelog` title if
   missing; keep the existing entries).
2. Bump the version where the project declares it — `CLAUDE.md → Commands/Conventions`
   says where; otherwise detect: `package.json` (`npm version <v> --no-git-tag-version`),
   `composer.json` "version" (only if present), `pyproject.toml` `[project] version`,
   `Cargo.toml`, a `VERSION` file, mobile build numbers. Don't invent a version field.
3. `framework/bin/fw check`, commit `chore(release): <version>`, push, `gh pr create`
   (body: the notes), wait for CI, merge per the usual rules (assisted: the user merges or
   says so).

## 4. Tag and publish (after the merge, with the user's OK from step 2)
```
git checkout <default> && git pull
git tag -a v<version> -m "v<version>" && git push origin v<version>
gh release create v<version> --title "v<version>" --notes-file <notes file> [--prerelease]
```
`--prerelease` for `0.x` releases only if the user wants it. Deployment is project-specific:
run it only if `CLAUDE.md` documents a deploy command and the user asks; production access
is an escalation (`/fw-work` rules).

## 5. Close the loop
- Milestone fully done → close it:
  `gh api -X PATCH repos/<owner/repo>/milestones/<number> -f state=closed`, and suggest
  `/fw-retro <milestone>` if it hasn't run.
- `framework/bin/fw schedule --apply --markdown docs/product/roadmap.md` and commit the
  snapshot with the next PR.
- Report: version, release URL, highlights, and what's next on the roadmap.
