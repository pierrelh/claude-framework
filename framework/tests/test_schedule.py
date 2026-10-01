"""`fw schedule` and `fw next`: dates from estimates, dependencies and capacity; what is ready."""
import datetime as dt
import unittest
from unittest import mock

from helpers import load_module

fw = load_module("fw", "bin/fw.py")
MON = dt.date(2026, 10, 5)
FRI = dt.date(2026, 10, 9)
CAP = {"hours_per_day": 6, "parallel_lanes": 1, "workdays": [1, 2, 3, 4, 5]}


def item(n, effort=None, deps=(), prio="Must", status="ready", state="OPEN", type_="Story", parent=None,
         labels=(), **extra):
    it = {"number": n, "title": f"#{n}", "state": state, "status": status, "deps": list(deps),
          fw.F_TYPE: type_, fw.F_PRIO: prio, "parent": parent, "labels": list(labels)}
    if effort is not None:
        it[fw.F_EFFORT] = effort
    it.update(extra)
    return it


class ComputeSchedule(unittest.TestCase):
    def schedule(self, items, cap=CAP, today=MON):
        with mock.patch.object(fw, "today", return_value=today):
            return fw.compute_schedule(items, cap)

    def test_dependencies_then_priority(self):
        plan, cyclic, missing = self.schedule([
            item(1, 6), item(2, 3, deps=[1]), item(3, 2, prio="Should")])
        self.assertEqual(plan[1], (MON, MON))
        self.assertEqual(plan[2], (MON + dt.timedelta(1), MON + dt.timedelta(1)))  # after #1, before #3
        self.assertEqual(plan[3], (MON + dt.timedelta(1), MON + dt.timedelta(1)))
        self.assertEqual((cyclic, missing), ([], []))

    def test_work_spills_over_the_weekend(self):
        plan, _, _ = self.schedule([item(1, 12)], today=FRI)
        self.assertEqual(plan[1], (FRI, dt.date(2026, 10, 12)))

    def test_start_on_weekend_aligns_to_monday(self):
        plan, _, _ = self.schedule([item(1, 1)], today=dt.date(2026, 10, 10))
        self.assertEqual(plan[1], (dt.date(2026, 10, 12),) * 2)

    def test_parallel_lanes(self):
        cap = dict(CAP, parallel_lanes=2)
        plan, _, _ = self.schedule([item(1, 6), item(2, 6), item(3, 6)], cap)
        self.assertEqual(plan[1][0], MON)
        self.assertEqual(plan[2][0], MON)
        self.assertEqual(plan[3][0], MON + dt.timedelta(1))

    def test_review_hours_count(self):
        plan, _, _ = self.schedule([item(1, 4, **{fw.F_REVIEW: 4}), item(2, 1)])
        self.assertEqual(plan[2][0], MON + dt.timedelta(1))

    def test_done_and_wont_are_not_scheduled(self):
        plan, _, _ = self.schedule([item(1, 6, state="CLOSED", status="done"), item(2, 6, deps=[1]),
                                    item(3, 6, prio="Won't")])
        self.assertNotIn(1, plan)
        self.assertNotIn(3, plan)
        self.assertEqual(plan[2], (MON, MON))

    def test_in_progress_goes_first(self):
        plan, _, _ = self.schedule([item(1, 6), item(2, 6, prio="Could", status="in progress")])
        self.assertEqual(plan[2][0], MON)
        self.assertEqual(plan[1][0], MON + dt.timedelta(1))

    def test_cycles_and_missing_estimates_are_reported(self):
        plan, cyclic, missing = self.schedule([item(1, 2, deps=[2]), item(2, 2, deps=[1]), item(3)])
        self.assertEqual(sorted(cyclic), [1, 2])
        self.assertEqual(missing, [3])
        self.assertIn(3, plan)  # scheduled with the default effort

    def test_epic_spans_its_children(self):
        plan, _, _ = self.schedule([
            item(10, type_="Epic"), item(1, 6, parent=10), item(2, 6, deps=[1], parent=10),
            item(3, 6, parent=10, state="CLOSED", status="done",
                 **{fw.F_START: "2026-09-28", fw.F_TARGET: "2026-09-29"})])
        self.assertEqual(plan[10], (dt.date(2026, 9, 28), MON + dt.timedelta(1)))


class ReadyItems(unittest.TestCase):
    def test_filters_and_order(self):
        items = [
            item(1, prio="Should"), item(2, prio="Must"), item(3, deps=[99]),       # unknown dep → ready
            item(4, deps=[5]), item(5, status="in progress"),                       # waits on #5
            item(6, labels=["needs-human"]), item(7, prio="Won't"), item(8, type_="Epic"),
            item(9, state="CLOSED", status="done"), item(11, deps=[9], status="backlog"),
        ]
        self.assertEqual([i["number"] for i in fw.ready_items(items)], [2, 3, 11, 1])


if __name__ == "__main__":
    unittest.main()
