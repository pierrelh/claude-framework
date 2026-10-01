"""The PreToolUse guard: what must be blocked and what must stay allowed.

Add a line to the tables below whenever a rule is added or a false positive is fixed.
"""
import io
import json
import unittest
from unittest import mock

from helpers import TempDir, git, git_repo, load_module, write_json

guard = load_module("guard", "hooks/guard.py")

BLOCKED = [
    "rm -rf /",
    "rm -rf ~",
    "rm -rf $HOME",
    "rm -fr ..",
    "sudo rm -rf / --no-preserve-root",
    "git push --force origin feat/1-x",
    "git push -f",
    "git push origin feat/1-x --force",
    "gh repo delete o/r --yes",
    "gh repo archive o/r",
    "gh project delete 3 --owner o",
    "git filter-branch --tree-filter x HEAD",
    "git filter-repo --path secret --invert-paths",
    "mkfs.ext4 /dev/sdb1",
    "dd if=/dev/zero of=/dev/sda bs=1M",
    "mysql -e 'DROP DATABASE app'",
    "psql -c 'drop schema public cascade'",
    "chmod -R 777 /",
]

ALLOWED = [
    "ls -la",
    "rm -rf build/",
    "rm -rf ./node_modules",
    "rm -rf ../sibling/tmp",
    "git push --force-with-lease origin feat/1-x",
    "git push -u origin feat/12-login",
    "git push origin HEAD:feat/12-login",
    "gh repo view",
    "gh pr merge 12 --squash --delete-branch",
    "chmod -R 755 storage",
]

# Known holes, fixed by the guard hardening work: move each line to BLOCKED once it is closed.
KNOWN_GAPS = [
    "rm -r -f /",
    "rm -f -r ~",
]

MAIN_PUSHES = [
    "git push origin main",
    "git push origin master",
    "git push origin HEAD:main",
    "git checkout main && git push origin main",
]


class Guard(unittest.TestCase):
    def setUp(self):
        self._tmp = TempDir()
        self.root = self._tmp.__enter__()
        self.addCleanup(self._tmp.__exit__, None, None, None)
        git_repo(self.root)
        self.init(True)
        patcher = mock.patch.object(guard, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def init(self, initialized):
        write_json(self.root / ".fw" / "config.json", {"initialized": initialized})

    def check(self, command, raw=None):
        stdin = io.StringIO(raw if raw is not None else json.dumps({"tool_input": {"command": command}}))
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stderr", io.StringIO()) as err:
            return guard.main(), err.getvalue()

    def test_blocked(self):
        for cmd in BLOCKED:
            with self.subTest(cmd=cmd):
                code, msg = self.check(cmd)
                self.assertEqual(code, 2)
                self.assertIn("Blocked by framework guard", msg)

    @unittest.expectedFailure
    def test_known_gaps(self):
        for cmd in KNOWN_GAPS:
            self.assertEqual(self.check(cmd)[0], 2, cmd)

    def test_allowed(self):
        git(self.root, "checkout", "-q", "-b", "feat/1-x")
        for cmd in ALLOWED:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.check(cmd)[0], 0)

    def test_push_to_main_blocked_once_initialized(self):
        git(self.root, "checkout", "-q", "-b", "feat/1-x")
        for cmd in MAIN_PUSHES:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.check(cmd)[0], 2)

    def test_bare_push_from_main_blocked(self):
        self.assertEqual(self.check("git push")[0], 2)
        self.assertEqual(self.check("git push origin")[0], 2)
        git(self.root, "checkout", "-q", "-b", "feat/1-x")
        self.assertEqual(self.check("git push")[0], 0)

    def test_push_to_main_allowed_before_init(self):
        self.init(False)
        for cmd in MAIN_PUSHES + ["git push"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.check(cmd)[0], 0)

    def test_destructive_rules_apply_even_before_init(self):
        self.init(False)
        self.assertEqual(self.check("git push --force")[0], 2)

    def test_garbage_input_is_ignored(self):
        self.assertEqual(self.check(None, raw="not json")[0], 0)
        self.assertEqual(self.check(None, raw="{}")[0], 0)


if __name__ == "__main__":
    unittest.main()
