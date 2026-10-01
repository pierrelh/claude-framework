"""`fw check`, `fw commands --detect`, CI workflow templates and the Stop/SubagentStop check gate."""
import argparse
import json
import shutil
import subprocess
import sys
import unittest
from unittest import mock

from helpers import FRAMEWORK, TempDir, git, git_repo, load_module, write_json

fw = load_module("fw", "bin/fw.py")
WORKFLOWS = FRAMEWORK / "templates" / "workflows"


class ProjectCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TempDir()
        self.root = self._tmp.__enter__()
        self.addCleanup(self._tmp.__exit__, None, None, None)
        self.config = self.root / ".fw" / "config.json"
        write_json(self.config, {})
        for name, value in (("ROOT", self.root), ("CONFIG", self.config)):
            p = mock.patch.object(fw, name, value)
            p.start()
            self.addCleanup(p.stop)

    def commands(self, **cmds):
        write_json(self.config, {"commands": cmds})


class Check(ProjectCase):
    def check(self, *steps, **flags):
        ns = argparse.Namespace(steps=list(steps), if_configured=False, fail_fast=False, json=True)
        ns.__dict__.update(flags)
        with mock.patch("builtins.print") as out, mock.patch("sys.stderr"):
            try:
                fw.cmd_check(ns)
                code = 0
            except SystemExit as e:
                code = e.code
        text = "\n".join(str(c.args[0]) for c in out.call_args_list if c.args)
        return code, (json.loads(text) if flags.get("json", True) and text.startswith("{") else text)

    def test_runs_configured_steps_in_order(self):
        self.commands(install="echo inst", test="echo T", lint="echo L", build="echo B")
        code, res = self.check()
        self.assertEqual(code, 0)
        self.assertTrue(res["ok"])
        self.assertEqual([s["name"] for s in res["steps"]], ["lint", "test", "build"])  # install is not a check
        self.assertIn("T", res["steps"][1]["output_tail"])

    def test_runs_in_the_project_root(self):
        (self.root / "marker").write_text("x")
        self.commands(test="test -f marker")
        self.assertEqual(self.check()[0], 0)

    def test_failure_runs_everything_and_reports(self):
        self.commands(lint="echo bad >&2; exit 3", test="echo ok")
        code, res = self.check()
        self.assertEqual(code, 1)
        self.assertFalse(res["ok"])
        self.assertEqual([(s["name"], s["exit"]) for s in res["steps"]], [("lint", 3), ("test", 0)])
        self.assertIn("bad", res["steps"][0]["output_tail"])

    def test_fail_fast(self):
        self.commands(lint="exit 1", test="echo ok")
        code, res = self.check(fail_fast=True)
        self.assertEqual((code, len(res["steps"])), (1, 1))

    def test_explicit_steps(self):
        self.commands(install="echo inst", test="exit 1")
        code, res = self.check("install")
        self.assertEqual((code, [s["name"] for s in res["steps"]]), (0, ["install"]))

    def test_nothing_configured_fails_unless_if_configured(self):
        self.assertEqual(self.check()[0], 2)
        self.assertEqual(self.check("install")[0], 2)
        self.assertEqual(self.check("install", if_configured=True, json=False)[0], 0)


class Detect(unittest.TestCase):
    def detect(self, files):
        with TempDir() as d:
            for name, content in files.items():
                (d / name).parent.mkdir(parents=True, exist_ok=True)
                (d / name).write_text(content if isinstance(content, str) else json.dumps(content))
            return fw.detect_commands(d)

    def test_node(self):
        cmds, ci, _ = self.detect({"package.json": {"scripts": {"lint": "eslint .", "test": "vitest", "tsc": "tsc"}},
                                   "package-lock.json": "{}"})
        self.assertEqual(ci, "node")
        self.assertEqual(cmds, {"install": "npm ci", "lint": "npm run lint", "typecheck": "npm run tsc",
                                "test": "npm run test"})

    def test_node_pnpm_and_default_test_script(self):
        cmds, _, _ = self.detect({"package.json": {"scripts": {
            "test": "echo \"Error: no test specified\" && exit 1", "build": "vite build"}}, "pnpm-lock.yaml": ""})
        self.assertEqual(cmds, {"install": "pnpm install --frozen-lockfile", "build": "pnpm build"})

    def test_php(self):
        cmds, ci, _ = self.detect({"composer.json": {"scripts": {"test": "phpunit"}}, "phpstan.neon.dist": "",
                                   ".php-cs-fixer.dist.php": ""})
        self.assertEqual(ci, "php")
        self.assertEqual(cmds["test"], "composer test")
        self.assertEqual(cmds["typecheck"], "vendor/bin/phpstan analyse --no-progress")
        self.assertEqual(cmds["lint"], "vendor/bin/php-cs-fixer fix --dry-run --diff")

    def test_python_uv(self):
        cmds, ci, _ = self.detect({"pyproject.toml": "[dependency-groups]\ndev = ['pytest', 'ruff', 'mypy']\n",
                                   "uv.lock": ""})
        self.assertEqual(ci, "python")
        self.assertEqual(cmds, {"install": "uv sync", "lint": "uv run ruff check .", "typecheck": "uv run mypy .",
                                "test": "uv run pytest"})

    def test_go(self):
        cmds, ci, _ = self.detect({"go.mod": "module x\n"})
        self.assertEqual((ci, cmds["test"]), ("go", "go test ./..."))

    def test_makefile_targets_win(self):
        cmds, ci, src = self.detect({"package.json": {"scripts": {"test": "jest"}},
                                     "Makefile": "VAR := 1\ntest: deps\n\tjest\nlint:\n\teslint .\n.PHONY: test\n"})
        self.assertEqual((cmds["test"], cmds["lint"]), ("make test", "make lint"))
        self.assertIn("Makefile", src)

    def test_nothing(self):
        self.assertEqual(self.detect({"README.md": "hi"})[:2], ({}, "generic"))


class DetectApply(ProjectCase):
    def test_apply_keeps_existing_commands(self):
        (self.root / "go.mod").write_text("module x\n")
        self.commands(test="make test-all")
        with mock.patch("builtins.print"):
            fw.cmd_commands(argparse.Namespace(detect=True, apply=True))
        cmds = json.loads(self.config.read_text())["commands"]
        self.assertEqual(cmds["test"], "make test-all")
        self.assertEqual(cmds["lint"], "go vet ./...")


class Workflows(ProjectCase):
    def install(self, name, *env):
        (self.root / "framework" / "templates").mkdir(parents=True, exist_ok=True)
        if not (self.root / "framework" / "templates" / "workflows").exists():
            shutil.copytree(WORKFLOWS, self.root / "framework" / "templates" / "workflows")
        with mock.patch("builtins.print"):
            fw.cmd_workflow(argparse.Namespace(action="install", name=name, force=True, env=list(env)))
        return (self.root / ".github" / "workflows" / f"{name}.yml").read_text()

    def test_ci_templates_share_one_contract(self):
        names = sorted(p.stem for p in WORKFLOWS.glob("ci-*.yml"))
        self.assertEqual(names, ["ci-generic", "ci-go", "ci-node", "ci-php", "ci-python"])
        for name in names:
            with self.subTest(name=name):
                text = (WORKFLOWS / f"{name}.yml").read_text()
                self.assertIn("\njobs:\n  check:\n", text)                 # required-check name
                self.assertIn("run: framework/bin/fw check\n", text)     # same gate as the agents
                self.assertIn("framework/bin/fw check install --if-configured", text)
                self.assertIn("persist-credentials: false", text)
                self.assertIn("permissions:\n  contents: read", text)
                for line in text.splitlines():
                    if "uses:" in line:
                        self.assertRegex(line, r"@[0-9a-f]{40} # ", "actions must be pinned to a commit SHA")

    def test_env_override(self):
        text = self.install("ci-php", "PHP_VERSION=8.3", "PHP_EXTENSIONS=mbstring")
        self.assertIn('PHP_VERSION: "8.3"', text)
        self.assertIn('PHP_EXTENSIONS: "mbstring"', text)

    def test_unknown_env_key(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            self.install("ci-go", "NOPE=1")


class CheckGate(unittest.TestCase):
    """The hook runs in a throwaway project with a copy of the framework scripts."""

    def setUp(self):
        self._tmp = TempDir()
        self.root = self._tmp.__enter__()
        self.addCleanup(self._tmp.__exit__, None, None, None)
        for rel in ("bin/fw.py", "hooks/check_gate.py", "MANIFEST"):
            (self.root / "framework" / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(FRAMEWORK / rel, self.root / "framework" / rel)
        (self.root / ".gitignore").write_text(".fw/local/\n__pycache__/\n")
        self.configure(enabled=True, test="test ! -f broken")
        git_repo(self.root)
        git(self.root, "checkout", "-q", "-b", "feat/1-x")

    def configure(self, enabled, **commands):
        write_json(self.root / ".fw" / "config.json", {"gates": {"check_on_stop": enabled}, "commands": commands})

    def stop(self, active=False):
        p = subprocess.run([sys.executable, str(self.root / "framework" / "hooks" / "check_gate.py")],
                           input=json.dumps({"hook_event_name": "SubagentStop", "stop_hook_active": active}),
                           capture_output=True, text=True)
        return p.returncode, p.stderr

    def test_green_passes_and_is_cached(self):
        self.assertEqual(self.stop()[0], 0)
        self.assertTrue((self.root / ".fw" / "local" / "check-gate.json").exists())
        self.configure(enabled=True, test="exit 1")  # config change = tree change: re-checked
        self.assertEqual(self.stop()[0], 2)

    def test_red_blocks_with_the_output(self):
        (self.root / "broken").write_text("x")
        code, err = self.stop()
        self.assertEqual(code, 2)
        self.assertIn("Quality gate failed", err)
        self.assertIn("test (exit 1)", err)
        self.assertIn("STATUS: BLOCKED", err)

    def test_second_stop_in_a_row_is_allowed(self):
        (self.root / "broken").write_text("x")
        self.assertEqual(self.stop(active=True)[0], 0)

    def test_disabled_or_unconfigured(self):
        (self.root / "broken").write_text("x")
        self.configure(enabled=False, test="exit 1")
        self.assertEqual(self.stop()[0], 0)
        self.configure(enabled=True)
        self.assertEqual(self.stop()[0], 0)

    def test_clean_main_is_skipped(self):
        self.configure(enabled=True, test="exit 1")
        git(self.root, "commit", "-qam", "red config")
        git(self.root, "checkout", "-q", "main")
        git(self.root, "merge", "-q", "feat/1-x")
        self.assertEqual(self.stop()[0], 0)


if __name__ == "__main__":
    unittest.main()
