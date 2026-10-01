"""`fw dashboard`: the data (health, burn-up, pace, project metrics) and both renderers."""
import datetime as dt
import re
import unittest

from helpers import TempDir, load_module

fw = load_module("fw", "bin/fw.py")
view = load_module("fw_dashboard", "bin/fw_dashboard.py")
TODAY = dt.date(2026, 10, 1)  # a Thursday


def item(n, status="ready", ms=1, due="2026-10-20", hours=4, created="2026-09-01", closed=None, prio="Must",
         start=None, target=None, parent=None, labels=(), type_="Story", **extra):
    it = {"number": n, "title": f"Item {n}", "url": f"https://github.com/o/r/issues/{n}",
          "state": "CLOSED" if status == "done" else "OPEN", "status": status, "labels": list(labels), "deps": [],
          "parent": parent, "milestone": ms, "milestone_title": f"M{ms}" if ms else None, "milestone_due": due,
          "created_at": created, "closed_at": closed, fw.F_TYPE: type_, fw.F_PRIO: prio, fw.F_EFFORT: hours,
          fw.F_START: start, fw.F_TARGET: target}
    it.update(extra)
    return it


def data(items, conf=None, custom=()):
    return fw.dashboard_data(items, conf or {"name": "Demo"}, today_=TODAY, extra={"custom": list(custom)})


class Data(unittest.TestCase):
    def test_progress_counts_hours_and_skips_epics_and_wont(self):
        d = data([item(1, "done", closed="2026-09-20"), item(2), item(3, prio="Won't"),
                  item(9, type_="Epic")])
        self.assertEqual((d["progress"]["items"], d["progress"]["done"]), (2, 1))
        self.assertEqual((d["progress"]["hours"], d["progress"]["hours_done"]), (8.0, 4.0))

    def test_milestone_health(self):
        d = data([item(1, "done", ms=1, closed="2026-09-20"),                                   # all done
                  item(2, ms=2, due="2026-10-20", target="2026-10-10"),                         # on track
                  item(3, ms=3, due="2026-10-20", target="2026-10-25", prio="Should"),          # at risk
                  item(4, ms=4, due="2026-10-20", target="2026-10-25"),                         # Must late
                  item(5, ms=5, due=None, target="2026-10-25"),                                 # no due date
                  item(6, ms=6, due="2026-09-30")])                                              # due passed
        health = {m["title"]: m["health"] for m in d["milestones"]}
        self.assertEqual(health, {"M1": "done", "M2": "on track", "M3": "at risk", "M4": "late",
                                  "M5": "no due date", "M6": "late"})

    def test_epics(self):
        d = data([item(10, type_="Epic"), item(1, "done", parent=10, closed="2026-09-20"), item(2, parent=10),
                  item(11, type_="Epic")])
        self.assertEqual([(e["number"], e["done"], e["items"]) for e in d["epics"]], [(10, 1, 2)])

    def test_burnup_and_pace(self):
        items = [item(1, "done", created="2026-09-01", closed="2026-09-10"),
                 item(2, "done", created="2026-09-01", closed="2026-09-24"),
                 item(3, created="2026-09-22"), item(4, created=None)]
        d = data(items)
        weeks = {p["week"]: (p["scope"], p["done"]) for p in d["burnup"]}
        self.assertEqual(list(weeks)[0], "2026-08-31")
        self.assertEqual(list(weeks)[-1], "2026-09-28")   # the current week is the last point
        self.assertEqual(weeks["2026-09-07"], (12.0, 4.0))  # #4 has no creation date: always in scope
        self.assertEqual(weeks["2026-09-21"], (16.0, 8.0))
        self.assertEqual(d["velocity"]["hours_per_week"], 2.0)  # 8 h closed in the last 4 weeks
        self.assertEqual(d["velocity"]["forecast_end"], (TODAY + dt.timedelta(weeks=4)).isoformat())

    def test_burnup_window_is_bounded(self):
        d = data([item(1, created="2025-01-06")])
        self.assertEqual(len(d["burnup"]), 16)

    def test_lists(self):
        d = data([item(1, "in progress", labels=["hotfix"]), item(2, "in review"), item(3, labels=["needs-human"]),
                  item(4, start="2026-10-05", target="2026-10-06"), item(5, start="2026-10-02", target="2026-10-02")])
        self.assertEqual([i["number"] for i in d["hotfixes"]], [1])
        self.assertEqual([i["number"] for i in d["in_flight"]], [1, 2])
        self.assertEqual([i["number"] for i in d["needs_you"]], [3])
        self.assertEqual([i["number"] for i in d["upcoming"]], [5, 4])
        self.assertEqual(d["flow"], {"backlog": 0, "ready": 3, "in progress": 1, "in review": 1, "done": 0})


class CustomMetrics(unittest.TestCase):
    def run_metrics(self, metrics):
        with TempDir() as d:
            (d / "coverage.txt").write_text("82.5\n")
            return fw.custom_metrics({"dashboard": {"metrics": metrics}}, root=d)

    def test_number_json_errors_and_targets(self):
        out = self.run_metrics([
            {"title": "Coverage", "command": "cat coverage.txt", "unit": "%", "target": 80},
            {"title": "Errors", "command": "echo '{\"value\": 3, \"detail\": \"last 24 h\"}'", "better": "lower",
             "target": 0},
            {"title": "Broken", "command": "echo nope >&2; exit 3"},
            {"title": "Garbage", "command": "echo not-a-number"},
            {"title": "Slow", "command": "sleep 5", "timeout": 0.2},
        ])
        by = {m["title"]: m for m in out}
        self.assertEqual((by["Coverage"]["value"], by["Coverage"]["ok"]), (82.5, True))
        self.assertEqual((by["Errors"]["value"], by["Errors"]["detail"], by["Errors"]["ok"]), (3, "last 24 h", False))
        self.assertEqual(by["Broken"]["error"], "nope")
        self.assertEqual(by["Garbage"]["error"], "ValueError")
        self.assertEqual(by["Slow"]["error"], "TimeoutExpired")

    def test_none_configured(self):
        self.assertEqual(fw.custom_metrics({}), [])


class Render(unittest.TestCase):
    def sample(self):
        items = [item(1, "done", closed="2026-09-10", created="2026-08-20"),
                 item(2, "in review", start="2026-10-01", target="2026-10-02"),
                 item(3, start="2026-10-03", target="2026-10-07", labels=["needs-human"]),
                 item(4, title='<script>alert("x")</script>', url="javascript:alert(1)",
                      start="2026-10-04", target="2026-10-05")]
        return data(items, {"name": "Demo <img src=x onerror=alert(1)>",
                            "github": {"project_url": "https://github.com/users/o/projects/1"}},
                    custom=[{"title": "Coverage", "value": 82.0, "unit": "%", "target": 80, "ok": True}])

    def test_text(self):
        out = view.render_text(self.sample())
        self.assertIn("Progress   █████", out)
        for section in ("Milestones", "Flow", "In flight", "Needs you", "Next up", "Project metrics"):
            self.assertIn(section, out)
        self.assertNotIn("\033[", out)
        self.assertIn("\033[", view.render_text(self.sample(), color=True))

    def test_html_is_self_contained_and_escaped(self):
        page = view.render_html(self.sample())
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertNotIn("<script", page)
        self.assertNotIn("<img", page)
        self.assertNotIn('href="javascript:', page)
        self.assertIn("&lt;script&gt;", page)
        # no external resource: the only absolute URLs are links
        self.assertEqual(re.findall(r'(?:src|@import|url\()\s*["\']?https?:', page), [])
        for section in ("Overall progress", "Milestones", "Burn-up", "Flow", "Next up", "Epics", "Estimates"):
            self.assertIn(section, page)
        self.assertIn('class="today"', page)
        self.assertIn("Coverage", page)
        self.assertIn("prefers-color-scheme:dark", page)

    def test_empty_project(self):
        d = data([])
        self.assertIn("Progress", view.render_text(d))
        page = view.render_html(d)
        self.assertIn("No milestone yet", page)
        self.assertIn("Not enough history", page)


if __name__ == "__main__":
    unittest.main()
