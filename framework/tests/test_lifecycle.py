"""Resume after an interruption, triage, hotfix priority and release notes."""
import argparse
import json
import unittest
from unittest import mock

from helpers import TempDir, git, git_repo, load_module

fw = load_module("fw", "bin/fw.py")


def item(n, status="in progress", **extra):
    it = {"number": n, "title": f"#{n}", "state": "OPEN", "status": status, "labels": [], "deps": []}
    it.update(extra)
    return it


class ResumePlan(unittest.TestCase):
    def plan(self, it, branches=(), prs=(), current="main", dirty=False, mine=True, ahead=None):
        return fw.resume_plan(it, list(branches), list(prs), current, dirty, mine, ahead or {})

    def pr(self, n, state, branch):
        return {"number": n, "state": state, "headRefName": branch, "url": f"u/{n}"}

    def test_merged_pr_closes_the_loop_even_if_started_elsewhere(self):
        r = self.plan(item(5, "in review"), ["feat/5-x"], [self.pr(9, "MERGED", "feat/5-x")], mine=False)
        self.assertEqual((r["step"], r["pr"]), (11, 9))

    def test_started_elsewhere_is_left_alone(self):
        r = self.plan(item(5), ["feat/5-x"], mine=False, ahead={"feat/5-x": 2})
        self.assertIsNone(r["step"])
        self.assertIn("elsewhere", r["action"])

    def test_open_pr(self):
        self.assertEqual(self.plan(item(5, "in review"), ["fix/5-x"], [self.pr(9, "OPEN", "fix/5-x")])["step"], 9)
        r = self.plan(item(5, "in progress"), ["fix/5-x"], [self.pr(9, "OPEN", "fix/5-x")])
        self.assertIn("fw review 5", r["action"])

    def test_open_pr_wins_over_an_older_closed_one(self):
        prs = [self.pr(8, "CLOSED", "feat/5-x"), self.pr(9, "OPEN", "feat/5-x")]
        self.assertEqual(self.plan(item(5), ["feat/5-x"], prs)["pr"], 9)

    def test_closed_pr_needs_the_user(self):
        r = self.plan(item(5), ["feat/5-x"], [self.pr(9, "CLOSED", "feat/5-x")])
        self.assertIsNone(r["step"])

    def test_work_on_disk(self):
        self.assertEqual(self.plan(item(5), ["feat/5-x"], current="feat/5-x", dirty=True)["step"], 4)
        self.assertEqual(self.plan(item(5), ["feat/5-x"], ahead={"feat/5-x": 3})["step"], 5)
        self.assertEqual(self.plan(item(5), ["feat/5-x"])["step"], 3)
        self.assertEqual(self.plan(item(5), ["feat/15-other", "feat/5"])["step"], 2)  # no false match

    def test_branch_prefixes(self):
        for b in ("feat/5-a", "fix/5-a", "chore/5-a", "hotfix/5-a", "docs/5-a"):
            with self.subTest(branch=b):
                self.assertEqual(self.plan(item(5), [b])["branch"], b)


class Untriaged(unittest.TestCase):
    def issue(self, n, labels=(), **extra):
        d = {"number": n, "title": f"#{n}", "state": "open", "labels": [{"name": x} for x in labels],
             "user": {"login": "someone"}, "author_association": "NONE", "body": "it broke"}
        d.update(extra)
        return d

    def test_reasons(self):
        issues = [self.issue(1), self.issue(2), self.issue(3), self.issue(4, ["triage"]),
                  self.issue(5, ["needs-info"]), self.issue(6, pull_request={}), self.issue(7, ["needs-human"]),
                  self.issue(8)]
        items = [item(2, "ready", **{fw.F_TYPE: "Bug", fw.F_EFFORT: 2}), item(3, "backlog", **{fw.F_TYPE: "Story"}),
                 item(4, "ready", **{fw.F_TYPE: "Bug", fw.F_EFFORT: 1}),
                 item(7, "ready", **{fw.F_TYPE: "Task"}), item(8, "backlog", **{fw.F_TYPE: "Epic"})]
        out = {i["number"]: i for i in fw.untriaged(issues, items)}
        self.assertEqual(sorted(out), [1, 3, 4, 5])
        self.assertEqual(out[1]["reasons"], ["not on the board"])
        self.assertEqual(out[3]["reasons"], ["no estimate"])
        self.assertEqual(out[4]["reasons"], ["labelled triage"])
        self.assertTrue(out[5]["waiting_info"])
        self.assertEqual(out[1]["association"], "NONE")


class HotfixFirst(unittest.TestCase):
    def test_hotfix_beats_priority(self):
        items = [item(1, "ready", **{fw.F_PRIO: "Must"}),
                 item(2, "ready", labels=["hotfix"], **{fw.F_PRIO: "Could"})]
        self.assertEqual([i["number"] for i in fw.ready_items(items)], [2, 1])


class ReleaseNotes(unittest.TestCase):
    def test_parse_commit(self):
        c = fw.parse_commit("feat(auth)!: password reset (#12)")
        self.assertEqual((c["type"], c["scope"], c["breaking"], c["description"], c["pr"]),
                         ("feat", "auth", True, "password reset", 12))
        self.assertTrue(fw.parse_commit("fix: x", "BREAKING CHANGE: the API changed")["breaking"])
        self.assertEqual(fw.parse_commit("Merge branch 'x'")["type"], None)

    def test_next_version(self):
        fix, feat = fw.parse_commit("fix: a"), fw.parse_commit("feat: b")
        brk = fw.parse_commit("refactor!: c")
        self.assertEqual(fw.next_version("1.4.2", [fix]), "1.4.3")
        self.assertEqual(fw.next_version("1.4.2", [fix, feat]), "1.5.0")
        self.assertEqual(fw.next_version("1.4.2", [brk]), "2.0.0")
        self.assertEqual(fw.next_version("0.4.2", [brk]), "0.5.0")   # 0.x: breaking bumps minor
        self.assertEqual(fw.next_version("0.0.0", [feat]), "0.1.0")

    def test_notes_group_and_skip_internal_commits(self):
        commits = [fw.parse_commit(s) for s in (
            "feat(cart): add coupons (#3)", "fix: rounding (#4)", "docs: readme", "chore: deps", "test: more",
            "perf: faster search (#5)", "feat!: drop IE support (#6)", "Update thing")]
        notes = fw.release_notes(commits, "1.0.0", "2030-01-07")
        self.assertTrue(notes.startswith("## 1.0.0 — 2030-01-07"))
        self.assertLess(notes.index("### Breaking"), notes.index("### Added"))
        self.assertIn("- cart: add coupons (#3)", notes)
        self.assertIn("### Changed\n- faster search (#5)", notes)
        self.assertIn("### Other\n- Update thing", notes)
        for internal in ("readme", "deps", "more"):
            self.assertNotIn(internal, notes)

    def test_since_the_last_tag(self):
        with TempDir() as d:
            git_repo(d)
            git(d, "commit", "-q", "--allow-empty", "-m", "feat: before the tag")
            git(d, "tag", "-a", "v1.2.0", "-m", "v1.2.0")
            git(d, "commit", "-q", "--allow-empty", "-m", "fix: after the tag (#7)")
            with mock.patch.object(fw, "ROOT", d), mock.patch("builtins.print") as out:
                fw.cmd_release_notes(argparse.Namespace(since=None, current=None, version=None, json=True))
            res = json.loads(out.call_args.args[0])
            self.assertEqual((res["since"], res["current"], res["version"]), ("v1.2.0", "1.2.0", "1.2.1"))
            self.assertEqual([c["description"] for c in res["commits"]], ["after the tag"])


if __name__ == "__main__":
    unittest.main()
