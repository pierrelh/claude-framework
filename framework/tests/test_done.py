"""`fw done`: closes the issue, records actual hours, unblocks dependents, closes completed epics.

GitHub is mocked at the function level (get_item, set_item_field, rest), so these tests check the
cascade logic, not the API calls themselves.
"""
import argparse
import datetime as dt
import unittest
from unittest import mock

from helpers import load_module

fw = load_module("fw", "bin/fw.py")


def item(n, status="ready", state="OPEN", deps=(), parent=None, effort=2):
    return {"number": n, "item_id": f"I{n}", "title": f"#{n}", "state": state, "status": status,
            "deps": list(deps), "parent": parent, "labels": [], fw.F_EFFORT: effort}


class Done(unittest.TestCase):
    def run_done(self, items, issue, actual=None, timers=None):
        self.fields, self.rests, self.saved = [], [], {}
        target = next(i for i in items if i["number"] == issue)
        patches = [
            mock.patch.object(fw, "gh_ctx", return_value={"repo": "o/r", "project_id": "P"}),
            mock.patch.object(fw, "project_fields", return_value={}),
            mock.patch.object(fw, "get_item", return_value=(items, target)),
            mock.patch.object(fw, "set_item_field",
                              side_effect=lambda ctx, f, iid, name, value: self.fields.append((iid, name, value))),
            mock.patch.object(fw, "rest", side_effect=lambda m, path, body=None, **k: self.rests.append((m, path, body))),
            mock.patch.object(fw, "timers", return_value=dict(timers or {})),
            mock.patch.object(fw, "save_json", side_effect=lambda p, d: self.saved.update(timers=d)),
        ]
        for p in patches:
            p.start()
        self.addCleanup(mock.patch.stopall)
        with mock.patch("builtins.print"):
            fw.cmd_done(argparse.Namespace(issue=issue, actual=actual))

    def statuses(self):
        return [(iid, v) for iid, name, v in self.fields if name == fw.F_STATUS]

    def test_closes_issue_and_records_explicit_actual(self):
        self.run_done([item(1, status="in review")], 1, actual=3.5)
        self.assertIn(("PATCH", "repos/o/r/issues/1", {"state": "closed", "state_reason": "completed"}), self.rests)
        self.assertIn(("I1", fw.F_STATUS, "done"), self.fields)
        self.assertIn(("I1", fw.F_ACTUAL, 3.5), self.fields)

    def test_actual_from_timer_and_timer_cleared(self):
        started = (dt.datetime.now() - dt.timedelta(hours=2)).isoformat(timespec="seconds")
        self.run_done([item(1, status="in review")], 1, timers={"1": started, "7": started})
        actual = [v for _, name, v in self.fields if name == fw.F_ACTUAL]
        self.assertEqual(len(actual), 1)
        self.assertAlmostEqual(actual[0], 2.0, delta=0.1)
        self.assertEqual(list(self.saved["timers"]), ["7"])

    def test_no_actual_without_timer(self):
        self.run_done([item(1, status="in review")], 1)
        self.assertFalse([f for f in self.fields if f[1] == fw.F_ACTUAL])

    def test_already_closed_issue_is_not_patched(self):
        self.run_done([item(1, state="CLOSED", status="in review")], 1)
        self.assertEqual(self.rests, [])

    def test_unblocks_dependents_only_when_all_deps_are_closed(self):
        self.run_done([
            item(1, status="in review"),
            item(2, status="backlog", deps=[1]),             # → ready
            item(3, status="backlog", deps=[1, 4]),          # #4 still open → stays
            item(4, status="ready"),
            item(5, status="backlog", deps=[1, 6]), item(6, state="CLOSED", status="done"),  # → ready
            item(7, status="ready", deps=[1]),               # not in backlog → untouched
        ], 1)
        self.assertEqual(sorted(self.statuses()), [("I1", "done"), ("I2", "ready"), ("I5", "ready")])

    def test_last_child_closes_the_epic(self):
        self.run_done([
            item(10, status="in progress"),
            item(1, status="in review", parent=10), item(2, state="CLOSED", status="done", parent=10),
        ], 1)
        self.assertIn(("PATCH", "repos/o/r/issues/10", {"state": "closed", "state_reason": "completed"}), self.rests)
        self.assertIn(("I10", "done"), self.statuses())

    def test_epic_moves_to_in_progress_while_children_remain(self):
        self.run_done([
            item(10, status="backlog"),
            item(1, status="in review", parent=10), item(2, status="ready", parent=10),
        ], 1)
        self.assertIn(("I10", "in progress"), self.statuses())
        self.assertNotIn("repos/o/r/issues/10", [p for _, p, _ in self.rests])


if __name__ == "__main__":
    unittest.main()
