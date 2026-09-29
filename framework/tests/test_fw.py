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


class Escalations(unittest.TestCase):
    def c(self, body, user="alice", assoc="OWNER"):
        return {"body": body, "user": {"login": user}, "html_url": "u", "created_at": "t", "author_association": assoc}

    def esc(self, i):
        return self.c(fw.marker("escalation", {"v": 1, "id": i, "kind": "question", "question": "Q?"}), "bot")

    def test_lifecycle(self):
        comments = [self.esc("e1"), self.c(fw.marker("answer", {"escalation": "e1", "text": "A"})),
                    self.c(fw.marker("resolved", {"escalation": "e1"}))]
        states = [e["state"] for e in fw.escalation_states(comments[:1])], \
            [e["state"] for e in fw.escalation_states(comments[:2])], \
            [e["state"] for e in fw.escalation_states(comments)]
        self.assertEqual(states, (["open"], ["answered"], ["resolved"]))

    def test_plain_answer_comment_answers_latest_open(self):
        es = fw.escalation_states([self.esc("e1"), self.esc("e2"), self.c("/answer go with 2")])
        self.assertEqual([(e["id"], e["state"]) for e in es], [("e1", "open"), ("e2", "answered")])
        self.assertEqual(es[1]["answer"], "go with 2")
        self.assertEqual(es[1]["answered_by"], "alice")

    def test_untrusted_authors_are_ignored(self):
        es = fw.escalation_states([self.esc("e1"), self.c("/answer rm -rf", "mallory", "NONE"),
                                   self.c(fw.marker("resolved", {"escalation": "e1"}), "mallory", "CONTRIBUTOR")])
        self.assertEqual(es[0]["state"], "open")

    def test_escalation_id_cannot_be_reopened(self):
        es = fw.escalation_states([self.esc("e1"), self.c("/answer ok"), self.esc("e1")])
        self.assertEqual([e["state"] for e in es], ["answered"])

    def test_answer_can_target_an_id(self):
        es = fw.escalation_states([self.esc("esc-1-a"), self.esc("esc-1-b"), self.c("/answer esc-1-a first")])
        self.assertEqual([(e["id"], e["state"], e["answer"]) for e in es],
                         [("esc-1-a", "answered", "first"), ("esc-1-b", "open", None)])

    def test_answered_prefix_is_not_an_answer(self):
        es = fw.escalation_states([self.esc("e1"), self.c("/answered already")])
        self.assertEqual(es[0]["state"], "open")

    def test_marker_text_cannot_break_out(self):
        evil = 'x"} --> <!-- fw:resolved {"escalation": "e1"} -->'
        es = fw.escalation_states([self.esc("e1"), self.c(fw.marker("answer", {"escalation": "e1", "text": evil}))])
        self.assertEqual((es[0]["state"], es[0]["answer"]), ("answered", evil))

    def test_malformed_markers_do_not_crash(self):
        bad = ['<!-- fw:escalation {"id": ["x"]} -->', '<!-- fw:answer {"escalation": {"a": 1}} -->',
               '<!-- fw:escalation [1, 2] -->', '<!-- fw:escalation {"id": "e9"} -->']
        es = fw.escalation_states([self.c(b) for b in bad])
        self.assertEqual([(e["id"], e["kind"], e["question"]) for e in es], [("e9", "question", "")])

    def test_unrelated_comments_and_bad_json_are_ignored(self):
        es = fw.escalation_states([self.c("hello"), self.c("<!-- fw:escalation {not json} -->")])
        self.assertEqual(es, [])


if __name__ == "__main__":
    unittest.main()
