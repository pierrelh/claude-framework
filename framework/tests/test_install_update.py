"""`fw install` and `fw update`: the MANIFEST contract between the template and a project.

owned files are copied and replaced; scaffold files are copied only when missing and never
updated; CLAUDE.md and .claude/settings.json are merged, not overwritten.
"""
import argparse
import json
import unittest
from unittest import mock

from helpers import TEMPLATE_ROOT, TempDir, git, git_repo, load_module, write_json

fw = load_module("fw", "bin/fw.py")


def install(target):
    with mock.patch("builtins.print"):
        fw.cmd_install(argparse.Namespace(target=str(target)))


class Install(unittest.TestCase):
    def test_fresh_install(self):
        with TempDir() as d:
            install(d)
            for rel in ("framework/bin/fw.py", "framework/MANIFEST", ".claude/skills/fw-work/SKILL.md",
                        "docs/framework/workflow.md", "CLAUDE.md", ".claude/settings.json", ".fw/config.json"):
                self.assertTrue((d / rel).exists(), rel)
            self.assertEqual(list(d.rglob("__pycache__")), [])
            self.assertFalse((d / ".fw" / "state.json").exists())
            self.assertFalse((d / ".github" / "workflows").exists())  # the template's own CI stays home
            conf = json.loads((d / ".fw" / "config.json").read_text())
            self.assertFalse(conf["initialized"])
            self.assertEqual(conf["framework"]["version"], (TEMPLATE_ROOT / "framework" / "VERSION").read_text().strip())
            self.assertTrue((d / "framework" / "bin" / "fw").stat().st_mode & 0o111)
            gitignore = (d / ".gitignore").read_text()
            for line in fw.GITIGNORE_LINES:
                self.assertIn(line, gitignore)

    def test_install_into_existing_project_keeps_its_files(self):
        with TempDir() as d:
            (d / "CLAUDE.md").write_text("# My project\n")
            (d / "docs").mkdir()
            (d / "docs" / "index.md").write_text("mine\n")
            (d / ".gitignore").write_text("vendor/\n")
            write_json(d / ".claude" / "settings.json", {
                "permissions": {"allow": ["Bash(make test)"]},
                "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "make lint"}]}]}})
            install(d)
            self.assertTrue((d / "CLAUDE.md").read_text().startswith("@framework/CLAUDE.framework.md\n\n# My project"))
            self.assertEqual((d / "docs" / "index.md").read_text(), "mine\n")
            self.assertTrue((d / "docs" / "product" / "brief.md").exists())  # missing scaffold is added
            settings = json.loads((d / ".claude" / "settings.json").read_text())
            self.assertIn("Bash(make test)", settings["permissions"]["allow"])
            self.assertIn("Bash(framework/bin/fw:*)", settings["permissions"]["allow"])
            self.assertIn("Stop", settings["hooks"])
            self.assertIn("PreToolUse", settings["hooks"])
            self.assertTrue((d / ".gitignore").read_text().startswith("vendor/\n"))

    def test_reinstall_is_idempotent(self):
        with TempDir() as d:
            install(d)
            install(d)
            self.assertEqual((d / "CLAUDE.md").read_text().count("@framework/CLAUDE.framework.md"), 1)
            settings = json.loads((d / ".claude" / "settings.json").read_text())
            shipped = json.loads((TEMPLATE_ROOT / ".claude" / "settings.json").read_text())
            self.assertEqual(len(settings["hooks"]["PreToolUse"]), len(shipped["hooks"]["PreToolUse"]))
            self.assertEqual(len(settings["permissions"]["allow"]), len(set(settings["permissions"]["allow"])))
            self.assertEqual((d / ".gitignore").read_text().count("# framework"), 1)

    def test_refuses_to_install_into_itself(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            install(TEMPLATE_ROOT)


class MergeSettings(unittest.TestCase):
    def test_same_command_under_a_new_matcher_is_added(self):
        guard = {"type": "command", "command": "python3 guard.py"}
        with TempDir() as d:
            write_json(d / "settings.json", {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [guard]}]}})
            src = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [guard]},
                                            {"matcher": "Edit|Write", "hooks": [guard]}]}}
            fw.merge_settings(src, d / "settings.json")
            fw.merge_settings(src, d / "settings.json")
            merged = json.loads((d / "settings.json").read_text())["hooks"]["PreToolUse"]
            self.assertEqual([e["matcher"] for e in merged], ["Bash", "Edit|Write"])


class Update(unittest.TestCase):
    """A local 'upstream' template and a project installed from it, both throwaway git repos."""

    def setUp(self):
        self._tmp = TempDir()
        tmp = self._tmp.__enter__()
        self.addCleanup(self._tmp.__exit__, None, None, None)
        self.upstream, self.project = tmp / "upstream", tmp / "project"
        for d in (self.upstream, self.project):
            d.mkdir()
            install(d)
            git_repo(d)
        # upstream moves on: new version, a changed, an added and a removed owned file, a changed scaffold
        u = self.upstream
        (u / "framework" / "VERSION").write_text("9.9.9\n")
        (u / "framework" / "standards" / "git-workflow.md").write_text("new rules\n")
        (u / "framework" / "standards" / "new-standard.md").write_text("added\n")
        (u / "framework" / "templates" / "adr.template.md").unlink()
        (u / "docs" / "index.md").write_text("upstream scaffold change\n")
        settings = json.loads((u / ".claude" / "settings.json").read_text())
        settings["permissions"]["allow"].append("Bash(new-upstream-rule)")
        write_json(u / ".claude" / "settings.json", settings)
        git(u, "add", "-A")
        git(u, "commit", "-q", "-m", "upstream change")
        # the project customised its scaffold
        (self.project / "docs" / "index.md").write_text("project docs\n")
        git(self.project, "commit", "-qam", "project docs")

        for name, value in (("ROOT", self.project), ("CONFIG", self.project / ".fw" / "config.json")):
            p = mock.patch.object(fw, name, value)
            p.start()
            self.addCleanup(p.stop)

    def update(self, apply):
        with mock.patch("builtins.print"):
            fw.cmd_update(argparse.Namespace(apply=apply, upstream=self.upstream.as_uri(), branch="main"))

    def test_dry_run_changes_nothing(self):
        self.update(apply=False)
        self.assertEqual(git(self.project, "status", "--porcelain"), "")

    def test_apply(self):
        self.update(apply=True)
        p = self.project
        self.assertEqual((p / "framework" / "standards" / "git-workflow.md").read_text(), "new rules\n")
        self.assertTrue((p / "framework" / "standards" / "new-standard.md").exists())
        self.assertFalse((p / "framework" / "templates" / "adr.template.md").exists())
        self.assertEqual((p / "docs" / "index.md").read_text(), "project docs\n")
        self.assertEqual(json.loads((p / ".fw" / "config.json").read_text())["framework"]["version"], "9.9.9")
        self.assertIn("Bash(new-upstream-rule)",
                      json.loads((p / ".claude" / "settings.json").read_text())["permissions"]["allow"])

    def test_apply_refuses_a_dirty_tree(self):
        (self.project / "README.md").write_text("uncommitted\n")
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            self.update(apply=True)
        self.assertNotEqual((self.project / "framework" / "VERSION").read_text().strip(), "9.9.9")


if __name__ == "__main__":
    unittest.main()
