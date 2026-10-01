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
    def run_done(self, items, issue, actual=None, timers=None, rounds=None):
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
            fw.cmd_done(argparse.Namespace(issue=issue, actual=actual, rounds=rounds))

    def statuses(self):
        return [(iid, v) for iid, name, v in self.fields if name == fw.F_STATUS]

    def test_closes_issue_and_records_explicit_actual(self):
        self.run_done([item(1, status="in review")], 1, actual=3.5)
        self.assertIn(("PATCH", "repos/o/r/issues/1", {"state": "closed", "state_reason": "completed"}), self.rests)
        self.assertIn(("I1", fw.F_STATUS, "done"), self.fields)
        self.assertIn(("I1", fw.F_ACTUAL, 3.5), self.fields)

    def test_agent_and_wait_time_from_the_timeline(self):
        now = dt.datetime.now()
        at = lambda h: (now - dt.timedelta(hours=h)).isoformat(timespec="seconds")  # noqa: E731
        events = [["start", at(10)], ["pause", at(8)], ["start", at(5)], ["review", at(4)]]
        self.run_done([item(1, status="in review")], 1, timers={"1": {"events": events}}, rounds=2)
        got = {name: v for _, name, v in self.fields if name in (fw.F_ACTUAL, fw.F_WAIT, fw.F_ROUNDS)}
        self.assertAlmostEqual(got[fw.F_ACTUAL], 3.0, delta=0.1)   # 2 h + 1 h of agent work
        self.assertAlmostEqual(got[fw.F_WAIT], 7.0, delta=0.1)     # 3 h on the escalation + 4 h on the PR
        self.assertEqual(got[fw.F_ROUNDS], 2)

    def test_actual_from_legacy_timer_and_timer_cleared(self):
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


class Timeline(unittest.TestCase):
    T0 = dt.datetime(2030, 1, 7, 9, 0)

    def ev(self, *pairs):
        return [[e, (self.T0 + dt.timedelta(hours=h)).isoformat()] for e, h in pairs]

    def test_split(self):
        end = self.T0 + dt.timedelta(hours=10)
        self.assertEqual(fw.split_time(self.ev(("start", 0)), end), (10.0, 0.0))
        self.assertEqual(fw.split_time(self.ev(("start", 0), ("review", 2)), end), (2.0, 8.0))
        # changes requested on the PR: the agent works again, then waits again
        self.assertEqual(fw.split_time(self.ev(("start", 0), ("review", 2), ("start", 5), ("review", 6)), end),
                         (3.0, 7.0))
        # a second start while working (another `fw start --force`) does not double count
        self.assertEqual(fw.split_time(self.ev(("start", 0), ("start", 1), ("review", 2)), end), (2.0, 8.0))

    def test_legacy_entry(self):
        self.assertEqual(fw.timeline("2030-01-07T09:00:00"), [["start", "2030-01-07T09:00:00"]])
        self.assertEqual(fw.timeline(None), [])

    def test_log_event(self):
        store = {}
        with mock.patch.object(fw, "timers", side_effect=lambda: dict(store)), \
                mock.patch.object(fw, "save_json", side_effect=lambda p, d: store.update(d)):
            fw.log_event(3, "review")                       # never started here: ignored
            self.assertEqual(store, {})
            fw.log_event(3, "start", self.T0)
            fw.log_event(3, "review", self.T0 + dt.timedelta(hours=1))
        self.assertEqual([e for e, _ in store["3"]["events"]], ["start", "review"])


class Metrics(unittest.TestCase):
    def done(self, n, est, act=None, size="M", type_="Story", agent="dev", wait=None, rounds=None, ms=1):
        it = {"number": n, "title": f"#{n}", "state": "CLOSED", "status": "done", "labels": [], "milestone": ms,
              "milestone_title": f"M{ms}", fw.F_TYPE: type_, fw.F_SIZE: size, fw.F_AGENT: agent, fw.F_EFFORT: est}
        for k, v in ((fw.F_ACTUAL, act), (fw.F_WAIT, wait), (fw.F_ROUNDS, rounds)):
            if v is not None:
                it[k] = v
        return it

    def test_summary(self):
        items = [self.done(1, 4, 4, wait=2, rounds=1), self.done(2, 2, 5, size="S", wait=10, rounds=3),
                 self.done(3, 6, None), self.done(4, 3, 3, ms=2),
                 {"number": 9, "title": "open", "state": "OPEN", "status": "ready", "labels": [], fw.F_EFFORT: 1},
                 {"number": 10, "title": "epic", "state": "CLOSED", "status": "done", "labels": [], fw.F_TYPE: "Epic"}]
        m = fw.metrics_summary(items, milestone="M1")
        self.assertEqual((m["done"], m["measured"]), (3, 2))
        self.assertEqual((m["estimate"], m["actual"], m["ratio"]), (6.0, 9.0, 1.5))
        self.assertEqual(m["by_size"]["S"]["ratio"], 2.5)
        self.assertEqual(m["review_rounds"], {"average": 2.0, "first_time_approved": 1, "items": 2})
        self.assertEqual(m["wait"], {"total": 12.0, "median": 10.0, "max": 10.0})
        self.assertEqual([r["number"] for r in m["outliers"]], [2])
        self.assertEqual(fw.metrics_summary(items, milestone=2)["done"], 1)
        self.assertEqual(fw.metrics_summary(items)["done"], 4)

    def test_status_accuracy_uses_agent_effort_only(self):
        it = self.done(1, 4, 4)
        it[fw.F_REVIEW] = 2
        self.assertEqual(fw.agent_effort(it), 4.0)
        self.assertEqual(fw.effort(it), 6.0)
