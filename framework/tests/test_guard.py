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
    # recursive deletes
    "rm -rf /",
    "rm -rf ~",
    "rm -rf $HOME",
    "rm -fr ..",
    "rm -r -f /",
    "rm -f -r ~",
    "rm -R /*",
    "rm --recursive --force ~/",
    "rm -rf .",
    "rm -rf /etc",
    "sudo rm -rf / --no-preserve-root",
    "sudo -u root rm -rf /var",
    "cd /tmp && rm -rf ~",
    "ls; rm -rf /",
    "bash -c 'rm -rf /'",
    "sh -c \"cd x && rm -rf ~\"",
    "eval rm -rf /",
    "echo $(rm -rf ~)",
    "X=1 env rm -rf /",
    # git
    "git push --force origin feat/1-x",
    "git push -f",
    "git push -fu origin feat/1-x",
    "git push origin feat/1-x --force",
    "git push origin +feat/1-x",
    "git push --mirror origin",
    "git push --no-verify origin feat/1-x",
    "git push origin --delete main",
    "git push origin :main",
    "git -C sub push -f",
    "git commit --no-verify -m 'x'",
    "git commit -nm 'x'",
    "git merge --no-verify feat/1-x",
    "git clean -fdx",
    "git clean -f",
    "git branch -D main",
    "git filter-branch --tree-filter x HEAD",
    "git filter-repo --path secret --invert-paths",
    # GitHub
    "gh repo delete o/r --yes",
    "gh repo archive o/r",
    "gh repo edit --visibility public",
    "gh project delete 3 --owner o",
    "gh pr merge 12 --squash --admin",
    "gh api -X DELETE repos/o/r",
    "gh api --method DELETE /repos/o/r",
    "gh api -XDELETE repos/o/r/rulesets/5",
    "gh api --method=PUT repos/o/r/rulesets/5 --input r.json",
    "gh api -X DELETE repos/o/r/branches/main/protection",
    # devices, permissions
    "mkfs.ext4 /dev/sdb1",
    "dd if=/dev/zero of=/dev/sda bs=1M",
    "chmod -R 777 /",
    "sudo chown -R me ~",
    # databases
    "mysql -e 'DROP DATABASE app'",
    "psql -c 'drop schema public cascade'",
    "psql app -c 'DROP TABLE users'",
    "mysql app -e 'TRUNCATE users'",
    "sqlite3 app.db 'DELETE FROM users'",
    "mysql app <<'SQL'\nDELETE FROM users;\nSQL",
    "dropdb app",
    "mysqladmin -u root drop app",
    "redis-cli FLUSHALL",
]

ALLOWED = [
    "ls -la",
    "rm -rf build/",
    "rm -rf ./node_modules",
    "rm -rf ../sibling/tmp",
    "rm -f /tmp/fw-x.json",
    "git push --force-with-lease origin feat/1-x",
    "git push -u origin feat/12-login",
    "git push origin HEAD:feat/12-login",
    "git push origin --delete feat/12-login",
    "git commit -am 'fix: handle -n flag'",
    "git commit -m 'docs: never use git push --force or rm -rf /'",
    "git clean -n",
    "git clean -fdn",
    "git reset --hard",  # clean tree in the test repo
    "git branch -D feat/1-x",
    "gh repo view",
    "gh pr merge 12 --squash --delete-branch",
    "gh api repos/o/r/rulesets",
    "gh api repos/o/r",
    "gh api -X DELETE repos/o/r/git/refs/heads/feat/1-x",
    "chmod -R 755 storage",
    # mentioning a dangerous command is not running it
    "echo 'drop database is blocked by the guard'",
    "gh pr create --title t --body 'the guard blocks rm -rf / and DROP DATABASE'",
    "cat > notes.md <<'EOF'\nrm -rf /\ngit push --force\nDROP DATABASE prod;\nEOF",
    "grep -rn 'rm -rf' framework/",
    "psql app -c 'DELETE FROM sessions WHERE expires < now()'",
    "mysql app <<<\"SELECT 1\"",
]

MAIN_PUSHES = [
    "git push origin main",
    "git push origin master",
    "git push origin HEAD:main",
    "git push origin feat/1-x:refs/heads/main",
    "git push --all origin",
    "git checkout main && git push origin main",
    "FW_ALLOW_MAIN_PUSH=1 git push origin main",  # the old text bypass no longer works
]


class GuardCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TempDir()
        tmp = self._tmp.__enter__()
        self.addCleanup(self._tmp.__exit__, None, None, None)
        self.root = git_repo(tmp / "project")
        self.remote = tmp / "remote.git"
        git(tmp, "init", "-q", "--bare", "-b", "main", str(self.remote))
        git(self.root, "remote", "add", "origin", str(self.remote))
        (self.root / "framework").mkdir()
        (self.root / "framework" / "MANIFEST").write_text(
            "owned framework/*\nowned .claude/skills/fw-*\nscaffold CLAUDE.md\n")
        self.init(True)
        patcher = mock.patch.object(guard, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def init(self, initialized):
        write_json(self.root / ".fw" / "config.json", {"initialized": initialized})

    def call(self, data):
        stdin = io.StringIO(data if isinstance(data, str) else json.dumps(data))
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stderr", io.StringIO()) as err:
            return guard.main(), err.getvalue()

    def check(self, command):
        return self.call({"tool_name": "Bash", "tool_input": {"command": command}})


class BashRules(GuardCase):
    def setUp(self):
        super().setUp()
        git(self.root, "checkout", "-q", "-b", "feat/1-x")

    def test_blocked(self):
        for cmd in BLOCKED:
            with self.subTest(cmd=cmd):
                code, msg = self.check(cmd)
                self.assertEqual(code, 2)
                self.assertIn("Blocked by framework guard", msg)

    def test_allowed(self):
        for cmd in ALLOWED:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.check(cmd), (0, ""))

    def test_reset_hard_only_blocked_with_uncommitted_changes(self):
        (self.root / "tracked.txt").write_text("v1\n")
        git(self.root, "add", "tracked.txt")
        git(self.root, "commit", "-qm", "tracked")
        self.assertEqual(self.check("git reset --hard")[0], 0)
        (self.root / "tracked.txt").write_text("v2\n")
        self.assertEqual(self.check("git reset --hard HEAD")[0], 2)

    def test_unparseable_line_falls_back_to_text_rules(self):
        self.assertEqual(self.check("rm -rf / 'unbalanced")[0], 2)
        self.assertEqual(self.check("echo 'unbalanced")[0], 0)

    def test_garbage_input_is_ignored(self):
        self.assertEqual(self.call("not json")[0], 0)
        self.assertEqual(self.call("{}")[0], 0)


class PushToMain(GuardCase):
    def setUp(self):
        super().setUp()
        git(self.root, "push", "-q", "origin", "main")  # the remote now has a main
        git(self.root, "checkout", "-q", "-b", "feat/1-x")

    def test_blocked_once_initialized(self):
        for cmd in MAIN_PUSHES:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.check(cmd)[0], 2)

    def test_bare_push_from_main_blocked(self):
        git(self.root, "checkout", "-q", "main")
        for cmd in ("git push", "git push origin", "git push origin HEAD", "git push -u origin HEAD"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.check(cmd)[0], 2)
        git(self.root, "checkout", "-q", "feat/1-x")
        self.assertEqual(self.check("git push")[0], 0)

    def test_allowed_before_init(self):
        self.init(False)
        for cmd in MAIN_PUSHES:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.check(cmd)[0], 0)

    def test_destructive_rules_apply_even_before_init(self):
        self.init(False)
        self.assertEqual(self.check("git push --force")[0], 2)


class FirstPush(GuardCase):
    def test_first_push_of_a_new_repository_is_allowed(self):
        self.assertEqual(self.check("git push -u origin main")[0], 0)

    def test_unreachable_remote_fails_closed(self):
        git(self.root, "remote", "set-url", "origin", str(self.root / "nowhere.git"))
        self.assertEqual(self.check("git push -u origin main")[0], 2)


class ProtectedPaths(GuardCase):
    def edit(self, tool, path, key="file_path"):
        return self.call({"tool_name": tool, "tool_input": {key: str(path)}})[0]

    def test_owned_files_are_read_only_once_initialized(self):
        for tool in ("Edit", "Write", "MultiEdit"):
            with self.subTest(tool=tool):
                self.assertEqual(self.edit(tool, self.root / "framework" / "bin" / "fw.py"), 2)
        self.assertEqual(self.edit("Edit", self.root / ".claude" / "skills" / "fw-work" / "SKILL.md"), 2)
        self.assertEqual(self.edit("Write", self.root / ".fw" / "state.json"), 2)
        self.assertEqual(self.edit("NotebookEdit", self.root / "framework" / "x.ipynb", "notebook_path"), 2)

    def test_project_files_stay_writable(self):
        for rel in ("CLAUDE.md", "src/app.py", ".fw/config.json", ".claude/skills/feature/SKILL.md",
                    ".claude/agents/qa.md"):
            with self.subTest(rel=rel):
                self.assertEqual(self.edit("Write", self.root / rel), 0)
        self.assertEqual(self.edit("Write", "/tmp/elsewhere/framework/bin/fw.py"), 0)

    def test_template_itself_is_editable(self):
        self.init(False)
        self.assertEqual(self.edit("Edit", self.root / "framework" / "bin" / "fw.py"), 0)

    def test_shell_writes(self):
        for cmd in ("echo x > framework/bin/fw.py", "echo x >> .fw/state.json", "sed -i 's/a/b/' framework/MANIFEST",
                    "cp /tmp/fw.py framework/bin/fw.py", "mv framework/bin/fw.py /tmp/", "tee framework/x.md < y",
                    "rm framework/standards/estimation.md", f"echo x > {self.root}/framework/VERSION"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.check(cmd)[0], 2)
        for cmd in ("cat framework/bin/fw.py > /tmp/copy.py", "echo x > docs/index.md", "sed -n 1p framework/MANIFEST",
                    "cp framework/templates/adr.template.md docs/architecture/decisions/0001-x.md"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.check(cmd)[0], 0)


if __name__ == "__main__":
    unittest.main()
