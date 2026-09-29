"""Unit tests for the pure parts of `fw` (no GitHub calls). Run: python3 -m unittest discover framework/tests"""
import datetime as dt
import importlib.machinery
import importlib.util
import sys
import unittest
from pathlib import Path

_path = Path(__file__).resolve().parents[1] / "bin" / "fw.py"
_spec = importlib.util.spec_from_loader("fw", importlib.machinery.SourceFileLoader("fw", str(_path)))
fw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fw)
sys.modules["fw"] = fw

MONDAY = dt.date(2030, 1, 7)


def item(n, prio="Must", ms=1, h=6, deps=(), labels=(), body="", status="ready"):
    return {"number": n, "title": f"#{n}", "state": "OPEN", "status": status, "labels": list(labels),
            "milestone": ms, "milestone_title": f"M{ms}", "parent": None, "deps": list(deps),
            "body": body, "wait_days": fw.parse_wait(body),
            fw.F_TYPE: "Story", fw.F_PRIO: prio, fw.F_EFFORT: h, fw.F_REVIEW: 0}


class Schedule(unittest.TestCase):
    def setUp(self):
        fw.today = lambda: MONDAY  # deterministic calendar

    def plan(self, items, **cap):
        capacity = {"hours_per_day": 6, "parallel_lanes": 1, "workdays": [1, 2, 3, 4, 5], **cap}
        return fw.compute_schedule(items, capacity, MONDAY)[0]

    def test_milestone_order_beats_priority(self):
        p = self.plan([item(1, "Should", ms=1), item(2, "Must", ms=2)])
        self.assertLess(p[1][0], p[2][0])

    def test_priority_order_when_configured(self):
        p = self.plan([item(1, "Should", ms=1), item(2, "Must", ms=2)], order="priority")
        self.assertLess(p[2][0], p[1][0])

    def test_human_items_do_not_take_agent_capacity(self):
        p = self.plan([item(1, body="<!-- fw:owner human -->", h=6), item(2, h=6)])
        self.assertEqual(p[1][0], p[2][0])

    def test_needs_human_label_alone_keeps_agent_lane(self):
        p = self.plan([item(1, labels=["needs-human"], h=6), item(2, h=6)])
        self.assertLess(p[1][0], p[2][0])

    def test_wait_days_delay_dependents(self):
        p = self.plan([item(1, h=6, body="<!-- fw:wait-days 5 -->"), item(2, h=6, deps=[1])])
        self.assertEqual((p[2][0] - MONDAY).days, 8)  # Mon work, Tue→Mon waiting, starts next Tue


class Validate(unittest.TestCase):
    def batch(self, stories):
        return {"milestones": [{"key": "M1", "title": "a"}, {"key": "M2", "title": "b"}],
                "epics": [{"key": "E1", "title": "e1", "goal": "g", "milestone": "M1"},
                          {"key": "E2", "title": "e2", "goal": "g", "milestone": "M2"}],
                "stories": stories}

    def task(self, key, epic="E1", **kw):
        return {"key": key, "type": "Task", "epic": epic, "title": key, "description": "d",
                "acceptance_criteria": ["x"], "agent_hours": 1, "review_hours": 0.5, "size": "S", **kw}

    def test_human_task_may_have_zero_agent_hours(self):
        errors, _ = fw.validate_backlog(self.batch([self.task("T-1", owner="human", agent_hours=0, size="XS")]), {})
        self.assertEqual(errors, [])

    def test_agent_task_needs_hours(self):
        errors, _ = fw.validate_backlog(self.batch([self.task("T-1", agent_hours=0, size="XS")]), {})
        self.assertTrue(any("agent_hours" in e for e in errors))

    def test_dependency_on_later_milestone_warns(self):
        _, warns = fw.validate_backlog(self.batch([self.task("T-1", depends_on=["T-2"]), self.task("T-2", epic="E2")]), {})
        self.assertTrue(any("later milestone" in w for w in warns))


class Contract(unittest.TestCase):
    def test_schema_names_match_constants(self):
        s = fw.schema()
        self.assertEqual(s["fields"]["item_type"], "Item type")
        self.assertIn("Backlog", s["statuses"])
        self.assertEqual(s["contract_version"], fw.CONTRACT_VERSION)

    def test_markers_parse(self):
        self.assertEqual(fw.parse_wait("x <!-- fw:wait-days 2.5 --> y"), 2.5)
        self.assertTrue(fw.is_human({"body": "<!-- fw:owner human -->", "labels": []}))
        self.assertEqual(fw.parse_wait("<!-- fw:wait-days 1.2.3 -->"), 0.0)
        self.assertFalse(fw.is_human({"body": "", "labels": ["story"]}))


if __name__ == "__main__":
    unittest.main()
