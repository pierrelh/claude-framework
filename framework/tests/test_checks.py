"""`fw lint-agents`, `fw docs-check` and the SessionStart hook, run against throwaway projects."""
import argparse
import shutil
import subprocess
import sys
import unittest
from unittest import mock

from helpers import FRAMEWORK, TempDir, load_module, write_json

fw = load_module("fw", "bin/fw.py")

GOOD_AGENT = """---
name: code-reviewer
description: Reviews a diff for correctness, security and convention issues. Use after every implementation step.
tools: Read, Grep, Glob, Bash
---

## Mission
Find real defects in the diff before it is merged.

## Scope
Only the files of the diff, and the code they call.

## Inputs
The issue, the branch and the implementer's report.

## Procedure
1. Read the issue and its acceptance criteria.
2. Read `git diff main...HEAD` file by file.
3. For each change, check correctness, error handling, security and the project conventions.
4. Run the tests and the linter; quote their output.

## Quality bar
Every finding names a file, a line and a concrete failure scenario. No style nitpicks.

## Output contract
A list of findings, then exactly one line: `VERDICT: APPROVE` or `VERDICT: CHANGES_REQUESTED`.

## Escalation
Stop and report when the diff touches secrets, payments or data deletion beyond the story.
""" + "Extra guidance so the body is long enough to be concrete. " * 10


class ProjectCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TempDir()
        self.root = self._tmp.__enter__()
        self.addCleanup(self._tmp.__exit__, None, None, None)
        for name, value in (("ROOT", self.root), ("CONFIG", self.root / ".fw" / "config.json")):
            p = mock.patch.object(fw, name, value)
            p.start()
            self.addCleanup(p.stop)

    def exit_code(self, fn):
        with mock.patch("builtins.print") as out:
            with self.assertRaises(SystemExit) as cm:
                fn(argparse.Namespace())
        self.output = "\n".join(str(c.args[0]) for c in out.call_args_list if c.args)
        return cm.exception.code


class LintAgents(ProjectCase):
    def agent(self, name, text):
        p = self.root / ".claude" / "agents" / f"{name}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def test_good_agent_passes(self):
        self.agent("code-reviewer", GOOD_AGENT)
        write_json(fw.CONFIG, {"roles": {"review": "code-reviewer"}})
        self.assertEqual(self.exit_code(fw.cmd_lint_agents), 0, self.output)

    def test_missing_section_and_name_mismatch(self):
        self.agent("reviewer", GOOD_AGENT.replace("## Escalation", "## Notes"))
        self.assertEqual(self.exit_code(fw.cmd_lint_agents), 1)
        self.assertIn("must equal the file name", self.output)
        self.assertIn("missing section '## Escalation'", self.output)

    def test_role_needs_its_output_token(self):
        self.agent("code-reviewer", GOOD_AGENT)
        write_json(fw.CONFIG, {"roles": {"qa": "code-reviewer", "docs": "doc-writer"}})
        self.assertEqual(self.exit_code(fw.cmd_lint_agents), 1)
        self.assertIn("requires the output token 'QA:'", self.output)
        self.assertIn("agent 'doc-writer' has no file", self.output)

    def test_placeholders_are_errors(self):
        self.agent("code-reviewer", GOOD_AGENT.replace("No style nitpicks.", "TODO"))
        self.assertEqual(self.exit_code(fw.cmd_lint_agents), 1)
        self.assertIn("placeholders", self.output)


class DocsCheck(ProjectCase):
    def test_broken_links(self):
        docs = self.root / "docs"
        (docs / "guides").mkdir(parents=True)
        (docs / "index.md").write_text(
            "[ok](guides/a.md) [anchor](#x) [web](https://example.com) [bad](guides/missing.md)\n"
            "`[ignored](nope.md)`\n```\n[ignored](nope.md)\n```\n")
        (docs / "guides" / "a.md").write_text("[up](../index.md#top) [[wiki]]\n")
        self.assertEqual(self.exit_code(fw.cmd_docs_check), 1)
        self.assertIn("docs/index.md → guides/missing.md", self.output)
        self.assertNotIn("nope.md", self.output)
        self.assertIn("wikilinks", self.output)

    def test_clean_docs_pass(self):
        (self.root / "docs").mkdir()
        (self.root / "docs" / "index.md").write_text("[readme](../README.md)\n")
        (self.root / "README.md").write_text("# hi\n")
        self.assertEqual(self.exit_code(fw.cmd_docs_check), 0, self.output)


class SessionStart(unittest.TestCase):
    def run_hook(self, config, agents=()):
        with TempDir() as d:
            shutil.copytree(FRAMEWORK / "hooks", d / "framework" / "hooks")
            write_json(d / ".fw" / "config.json", config)
            (d / ".claude" / "agents").mkdir(parents=True)
            for a in agents:
                (d / ".claude" / "agents" / f"{a}.md").write_text("x")
            return subprocess.run([sys.executable, str(d / "framework" / "hooks" / "session_start.py")],
                                  capture_output=True, text=True, check=True).stdout

    def test_not_initialized(self):
        self.assertIn("NOT initialized", self.run_hook({"initialized": False}))

    def test_initialized(self):
        out = self.run_hook({"initialized": True, "name": "demo", "autonomy": "auto",
                             "github": {"repo": "o/demo"}}, agents=["qa-engineer", "code-reviewer"])
        self.assertIn("project=demo", out)
        self.assertIn("autonomy=auto", out)
        self.assertIn("repo=o/demo", out)
        self.assertIn("agents=code-reviewer, qa-engineer", out)


if __name__ == "__main__":
    unittest.main()
