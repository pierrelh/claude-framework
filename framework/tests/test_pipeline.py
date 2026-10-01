"""Review pipeline: when the implementer may start, the pipelined schedule, story worktrees."""
import argparse
import datetime as dt
import io
import json
import shutil
import subprocess
import sys
import unittest
from unittest import mock

from helpers import FRAMEWORK, TempDir, git, git_repo, load_module, write_json

fw = load_module("fw", "bin/fw.py")
guard = load_module("guard", "hooks/guard.py")
MON = dt.date(2026, 10, 5)


def item(n, status="ready", state="OPEN", labels=(), **extra):
    it = {"number": n, "title": f"Item {n}", "state": state, "status": status, "labels": list(labels),
          "deps": [], "parent": None, fw.F_TYPE: "Story", fw.F_PRIO: "Must"}
    it.update(extra)
    return it


class PipelineState(unittest.TestCase):
    ON = {"pipeline": {"enabled": True, "review_wip": 2}}

    def state(self, items, conf=None, mine=("1", "2", "3", "4")):
        return fw.pipeline_state(items, self.ON if conf is None else conf, mine)

    def test_free(self):
        st = self.state([item(1, "in review")])
        self.assertTrue(st["can_start"])
        self.assertEqual([i["number"] for i in st["in_review"]], [1])

    def test_implementer_busy(self):
        st = self.state([item(1, "in review"), item(2, "in progress")])
        self.assertFalse(st["can_start"])
        self.assertIn("#2", st["reason"])

    def test_review_limit(self):
        st = self.state([item(1, "in review"), item(2, "in review")])
        self.assertFalse(st["can_start"])
        self.assertIn("2/2", st["reason"])
        self.assertTrue(self.state([item(1, "in review"), item(2, "in review")],
                                   {"pipeline": {"enabled": True, "review_wip": 3}})["can_start"])

    def test_default_limit_is_two(self):
        st = self.state([item(1, "in review"), item(2, "in review")], {"pipeline": {"enabled": True}})
        self.assertEqual((st["review_wip"], st["can_start"]), (2, False))

    def test_escalated_and_other_machines_do_not_count(self):
        items = [item(1, "in review", labels=["needs-human"]), item(2, "in review"), item(3, "in progress"),
                 item(4, "in review")]
        st = self.state(items, mine=("2",))
        self.assertTrue(st["can_start"])
        self.assertEqual(sorted(i["number"] for i in st["in_review"]), [2, 4])

    def test_disabled_means_one_item_at_a_time(self):
        self.assertFalse(self.state([item(1, "in progress")], {})["can_start"])
        self.assertTrue(self.state([item(1, "in review")], {})["can_start"])


class PipelinedSchedule(unittest.TestCase):
    def plan(self, items, **cap):
        capacity = {"hours_per_day": 6, "parallel_lanes": 1, "workdays": [1, 2, 3, 4, 5], **cap}
        with mock.patch.object(fw, "today", return_value=MON):
            return fw.compute_schedule(items, capacity)[0]

    def items(self):
        return [item(1, **{fw.F_EFFORT: 4, fw.F_REVIEW: 2}), item(2, **{fw.F_EFFORT: 4, fw.F_REVIEW: 2})]

    def test_review_overlaps_the_next_item(self):
        self.assertEqual(self.plan(self.items())[2][0], MON + dt.timedelta(1))      # starts after 6 h
        self.assertEqual(self.plan(self.items(), pipeline=True)[2][0], MON)         # starts after 4 h

    def test_dependents_still_wait_for_the_review(self):
        items = self.items()
        items[1]["deps"] = [1]
        self.assertEqual(self.plan(items, pipeline=True)[2][0], MON + dt.timedelta(1))

    def test_pipeline_uses_a_single_implementer(self):
        plan = self.plan([item(n, **{fw.F_EFFORT: 6}) for n in (1, 2)], parallel_lanes=2, pipeline=True)
        self.assertEqual(plan[2][0], MON + dt.timedelta(1))


class Names(unittest.TestCase):
    def test_branch_for(self):
        self.assertEqual(fw.branch_for(item(12, title="Sign up with e-mail & password!")),
                         "feat/12-sign-up-with-e-mail-password")
        self.assertEqual(fw.branch_for(item(3, title="Crash", **{fw.F_TYPE: "Bug"})), "fix/3-crash")
        self.assertEqual(fw.branch_for(item(3, title="Crash", labels=["hotfix"], **{fw.F_TYPE: "Bug"})),
                         "hotfix/3-crash")
        self.assertEqual(fw.branch_for(item(4, title="CI", **{fw.F_TYPE: "Task"})), "chore/4-ci")
        self.assertEqual(fw.slugify("Éléphant — rose"), "lphant-rose")
        self.assertEqual(fw.slugify("!!!"), "item")


class Worktrees(unittest.TestCase):
    def setUp(self):
        self._tmp = TempDir()
        tmp = self._tmp.__enter__()
        self.addCleanup(self._tmp.__exit__, None, None, None)
        self.root = tmp / "project"
        self.root.mkdir()
        write_json(self.root / ".fw" / "config.json", {"github": {"default_branch": "main"}})
        git_repo(self.root)
        git(tmp, "init", "-q", "--bare", "-b", "main", str(tmp / "remote.git"))
        git(self.root, "remote", "add", "origin", str(tmp / "remote.git"))
        git(self.root, "push", "-q", "origin", "main")
        self.items = {12: item(12, title="Sign up"), 13: item(13, title="Fix login", **{fw.F_TYPE: "Bug"})}
        for name, value in (("ROOT", self.root), ("CONFIG", self.root / ".fw" / "config.json")):
            p = mock.patch.object(fw, name, value)
            p.start()
            self.addCleanup(p.stop)
        for name, value in (("gh_ctx", mock.Mock(return_value={})),
                            ("get_item", mock.Mock(side_effect=lambda ctx, n: ([], self.items[n])))):
            p = mock.patch.object(fw, name, value)
            p.start()
            self.addCleanup(p.stop)

    def wt(self, action, issue=None):
        with mock.patch("builtins.print") as out:
            fw.cmd_worktree(argparse.Namespace(action=action, issue=issue, branch=None, json=False))
        return out.call_args.args[0] if out.call_args else None

    def test_add_list_remove(self):
        path = self.wt("add", 12)
        self.assertEqual(str(path), str(self.root.parent / "project.worktrees" / "12-sign-up"))
        self.assertEqual(git(path, "rev-parse", "--abbrev-ref", "HEAD").strip(), "feat/12-sign-up")
        self.assertEqual(str(self.wt("add", 12)), str(path))  # idempotent
        self.wt("add", 13)
        wts = {w["number"]: w for w in fw.worktree_list()}
        self.assertEqual(sorted(wts), [12, 13])
        self.assertEqual(wts[13]["branch"], "fix/13-fix-login")
        self.assertFalse(wts[12]["dirty"])

        (path / "wip.txt").write_text("work in progress")
        self.assertTrue({w["number"]: w for w in fw.worktree_list()}[12]["dirty"])
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            self.wt("remove", 12)
        (path / "wip.txt").unlink()
        self.wt("remove", 12)
        self.assertEqual([w["number"] for w in fw.worktree_list()], [13])
        self.assertIn("feat/12-sign-up", git(self.root, "branch", "--list", "feat/12-sign-up"))  # branch kept

    def test_reuses_an_existing_branch(self):
        git(self.root, "branch", "feat/12-sign-up")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "later on main")
        path = self.wt("add", 12)
        self.assertEqual(git(path, "rev-parse", "HEAD"), git(self.root, "rev-parse", "feat/12-sign-up"))


class GuardInWorktrees(unittest.TestCase):
    def test_owned_files_are_protected_in_story_worktrees(self):
        with TempDir() as tmp:
            root = tmp / "project"
            (root / "framework").mkdir(parents=True)
            (root / "framework" / "MANIFEST").write_text("owned framework/*\n")
            write_json(root / ".fw" / "config.json", {"initialized": True})
            wt = tmp / "project.worktrees" / "12-sign-up"

            def edit(path):
                stdin = io.StringIO(json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(path)}}))
                with mock.patch.object(guard, "ROOT", root), mock.patch("sys.stdin", stdin), \
                        mock.patch("sys.stderr", io.StringIO()):
                    return guard.main()

            self.assertEqual(edit(wt / "framework" / "bin" / "fw.py"), 2)
            self.assertEqual(edit(wt / "src" / "app.py"), 0)
            self.assertEqual(edit(tmp / "elsewhere.worktrees" / "1-x" / "framework" / "bin" / "fw.py"), 0)


class GateInWorktrees(unittest.TestCase):
    def test_failing_check_in_a_story_worktree_blocks(self):
        with TempDir() as tmp:
            root = tmp / "project"
            for rel in ("bin/fw.py", "hooks/check_gate.py", "MANIFEST"):
                (root / "framework" / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(FRAMEWORK / rel, root / "framework" / rel)
            (root / ".gitignore").write_text(".fw/local/\n__pycache__/\n")
            write_json(root / ".fw" / "config.json",
                       {"gates": {"check_on_stop": True}, "commands": {"test": "test ! -f broken"}})
            git_repo(root)
            wt = tmp / "project.worktrees" / "5-x"
            git(root, "worktree", "add", "-q", "-b", "feat/5-x", str(wt))

            def stop():
                p = subprocess.run([sys.executable, str(root / "framework" / "hooks" / "check_gate.py")],
                                   input=json.dumps({"stop_hook_active": False}), capture_output=True, text=True)
                return p.returncode, p.stderr

            self.assertEqual(stop()[0], 0)  # main is clean, the worktree is green
            (wt / "broken").write_text("x")
            code, err = stop()
            self.assertEqual(code, 2)
            self.assertIn("in " + str(wt), err)


if __name__ == "__main__":
    unittest.main()
