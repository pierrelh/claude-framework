# Quality gates

One definition of "the code is OK", used everywhere: the commands in
`.fw/config.json → commands`.

```json
"commands": {
  "install": "composer install --no-interaction --prefer-dist --no-progress",
  "lint": "vendor/bin/php-cs-fixer fix --dry-run --diff",
  "typecheck": "vendor/bin/phpstan analyse --no-progress",
  "test": "vendor/bin/phpunit",
  "build": ""
}
```

| Command | Purpose |
|---|---|
| `fw commands` | Show them. `--detect` suggests them from package.json, composer.json, pyproject.toml, go.mod, Cargo.toml and Makefile targets (a Makefile target wins); `--detect --apply` adds the missing ones, never replacing yours. |
| `fw check` | Runs `lint`, `typecheck`, `test`, `build` — the configured ones, in that order, from the project root. Exit 0 = all green. `fw check test` runs one; `--fail-fast`; `--json` for tools. |
| `fw config set commands.test '"pytest -q"'` | Change one. |

## Who runs it
- **Implementer agents** finish only when `fw check` is green; **QA** runs it again as evidence.
- **CI**: `fw workflow install ci-<node|php|python|go|generic>` installs a workflow whose
  single job, `check`, sets up the runtime, runs `fw check install --if-configured` then
  `fw check`. Because it reads the same config, changing a command changes CI too. Versions:
  `--env NODE_VERSION=22`, `--env PHP_VERSION=8.4`, `--env PYTHON_VERSION=3.13` (Node and
  Python read `.nvmrc` / `.python-version` / the manifest when left empty; Go reads `go.mod`).
  Actions are pinned to commit SHAs and the checkout keeps no credentials.
- **Branch protection**: once the workflow ran green on a pull request,
  `fw protect --checks check` makes it required for every merge.
- **Check gate (optional)** — `fw config set gates.check_on_stop true`. A Stop/SubagentStop
  hook (`framework/hooks/check_gate.py`) runs `fw check` when an agent stops with changes in
  the working tree (or on a feature branch). If it fails, the agent gets the failing output
  and keeps working; a second stop in a row is let through so it can report
  `STATUS: BLOCKED` instead of looping. Green results are cached per tree state
  (`.fw/local/check-gate.json`); `gates.check_timeout` (default 900 s) never blocks.

Nothing configured → `fw check` fails (exit 2) and CI is red: a pipeline that runs nothing
must not look green.
