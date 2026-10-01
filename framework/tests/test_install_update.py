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


def printed(mock_print):
    return "\n".join(str(c.args[0]) for c in mock_print.call_args_list if c.args)


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
            self.assertEqual(conf["framework"]["migrated"], conf["framework"]["version"])
            lock = json.loads((d / ".fw" / "framework.lock.json").read_text())
            self.assertEqual(lock["version"], conf["framework"]["version"])
            self.assertIn("framework/bin/fw.py", lock["files"])
            self.assertIn(".claude/skills/fw-work/SKILL.md", lock["files"])
            self.assertNotIn("CLAUDE.md", lock["files"])
            self.assertFalse([f for f in lock["files"] if "__pycache__" in f])
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
        changelog = (u / "framework" / "CHANGELOG.md").read_text()
        (u / "framework" / "CHANGELOG.md").write_text(
            changelog.replace("\n## ", "\n## 9.9.9 — 2030-01-01\n### Added\n- Time travel.\n\n## ", 1))
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
        with mock.patch("builtins.print") as out:
            fw.cmd_update(argparse.Namespace(apply=apply, upstream=self.upstream.as_uri(), branch="main"))
        return printed(out)

    def test_dry_run_changes_nothing(self):
        self.update(apply=False)
        self.assertEqual(git(self.project, "status", "--porcelain"), "")

    def test_preview_shows_new_changelog_entries_only(self):
        out = self.update(apply=False)
        self.assertIn("## 9.9.9", out)
        self.assertIn("Time travel.", out)
        current = (self.project / "framework" / "VERSION").read_text().strip()
        self.assertNotIn(f"## {current}", out)

    def test_preview_warns_about_local_changes(self):
        (self.project / "framework" / "standards" / "estimation.md").write_text("tweaked locally\n")
        git(self.project, "commit", "-qam", "local tweak")
        out = self.update(apply=False)
        self.assertIn("local changes to framework-owned files", out)
        self.assertIn("framework/standards/estimation.md", out)

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
        lock = json.loads((p / ".fw" / "framework.lock.json").read_text())
        self.assertEqual(lock["version"], "9.9.9")
        self.assertIn("framework/standards/new-standard.md", lock["files"])
        self.assertNotIn("framework/templates/adr.template.md", lock["files"])
        self.assertEqual(fw.drift(p), {"modified": [], "added": [], "deleted": []})
        self.assertEqual(json.loads((p / ".fw" / "config.json").read_text())["framework"]["migrated"], "9.9.9")

    def test_apply_refuses_a_dirty_tree(self):
        (self.project / "README.md").write_text("uncommitted\n")
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            self.update(apply=True)
        self.assertNotEqual((self.project / "framework" / "VERSION").read_text().strip(), "9.9.9")


if __name__ == "__main__":
    unittest.main()


class Drift(unittest.TestCase):
    def test_reports_local_changes_to_owned_files_only(self):
        with TempDir() as d:
            install(d)
            self.assertEqual(fw.drift(d), {"modified": [], "added": [], "deleted": []})
            (d / "framework" / "standards" / "estimation.md").write_text("changed\r\n")
            (d / "framework" / "standards" / "mine.md").write_text("new\n")
            (d / "framework" / "templates" / "adr.template.md").unlink()
            (d / "CLAUDE.md").write_text("scaffold edits are the project's business\n")
            self.assertEqual(fw.drift(d), {"modified": ["framework/standards/estimation.md"],
                                           "added": ["framework/standards/mine.md"],
                                           "deleted": ["framework/templates/adr.template.md"]})

    def test_line_endings_are_not_drift(self):
        with TempDir() as d:
            install(d)
            f = d / "framework" / "standards" / "estimation.md"
            f.write_bytes(f.read_bytes().replace(b"\n", b"\r\n"))
            self.assertEqual(fw.drift(d)["modified"], [])

    def test_no_baseline(self):
        with TempDir() as d:
            self.assertIsNone(fw.drift(d))


class Changelog(unittest.TestCase):
    TEXT = "# Changelog\n\nintro\n\n## 0.5.0 — x\n- e\n\n## 0.4.1\n- d\n\n## 0.4.0\n- c\n\n## 0.3.0\n- b\n"

    def test_between(self):
        out = fw.changelog_between(self.TEXT, "0.4.0", "0.5.0")
        self.assertEqual(out, "## 0.5.0 — x\n- e\n\n## 0.4.1\n- d")
        self.assertEqual(fw.changelog_between(self.TEXT, "0.5.0", "0.5.0"), "")
        self.assertEqual(fw.changelog_between("", "0.1.0", "0.2.0"), "")

    def test_versions_compare_numerically(self):
        self.assertLess(fw.vtuple("0.9.0"), fw.vtuple("0.10.0"))
        self.assertEqual(fw.vtuple("?"), (0,))


class Migrate(unittest.TestCase):
    def setUp(self):
        self._tmp = TempDir()
        self.root = self._tmp.__enter__()
        self.addCleanup(self._tmp.__exit__, None, None, None)
        install(self.root)
        self.settings = self.root / ".claude" / "settings.json"
        s = json.loads(self.settings.read_text())
        s["hooks"]["PreToolUse"] = [e for e in s["hooks"]["PreToolUse"] if e.get("matcher") == "Bash"]
        write_json(self.settings, s)
        self.config = self.root / ".fw" / "config.json"
        conf = json.loads(self.config.read_text())
        conf["framework"]["migrated"] = "0.3.1"
        write_json(self.config, conf)
        for name, value in (("ROOT", self.root), ("CONFIG", self.config)):
            p = mock.patch.object(fw, name, value)
            p.start()
            self.addCleanup(p.stop)

    def migrate(self, dry_run=False):
        with mock.patch("builtins.print") as out:
            fw.cmd_migrate(argparse.Namespace(dry_run=dry_run))
        return printed(out)

    def matchers(self):
        return [e.get("matcher") for e in json.loads(self.settings.read_text())["hooks"]["PreToolUse"]]

    def test_dry_run_reports_without_changing(self):
        out = self.migrate(dry_run=True)
        self.assertIn("→ 0.4.0", out)
        self.assertEqual(self.matchers(), ["Bash"])
        self.assertEqual(json.loads(self.config.read_text())["framework"]["migrated"], "0.3.1")

    def test_apply_once(self):
        self.migrate()
        self.assertEqual(self.matchers(), ["Bash", "Edit|Write|MultiEdit|NotebookEdit", "Agent|Task"])
        version = (self.root / "framework" / "VERSION").read_text().strip()
        self.assertEqual(json.loads(self.config.read_text())["framework"]["migrated"], version)
        self.assertIn("no migration pending", self.migrate())
        self.assertEqual(len(self.matchers()), 3)

    def test_missing_marker_runs_everything_idempotently(self):
        conf = json.loads(self.config.read_text())
        del conf["framework"]["migrated"]
        write_json(self.config, conf)
        self.migrate()
        self.migrate()
        self.assertEqual(self.matchers().count("Edit|Write|MultiEdit|NotebookEdit"), 1)

    def test_missing_lock_is_created(self):
        (self.root / ".fw" / "framework.lock.json").unlink()
        self.migrate()
        self.assertEqual(fw.drift(self.root), {"modified": [], "added": [], "deleted": []})

    def test_migrations_are_ordered(self):
        versions = [fw.vtuple(v) for v, _, _ in fw.MIGRATIONS]
        self.assertEqual(versions, sorted(versions))
