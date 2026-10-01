"""`fw protect`: the default-branch ruleset on GitHub. `api_try` is mocked."""
import argparse
import json
import unittest
from unittest import mock

from helpers import TempDir, load_module, write_json

fw = load_module("fw", "bin/fw.py")


class Protect(unittest.TestCase):
    def setUp(self):
        self._tmp = TempDir()
        self.root = self._tmp.__enter__()
        self.addCleanup(self._tmp.__exit__, None, None, None)
        self.config = self.root / ".fw" / "config.json"
        write_json(self.config, {"github": {"repo": "o/r"}})
        for name, value in (("ROOT", self.root), ("CONFIG", self.config)):
            p = mock.patch.object(fw, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.calls = []

    def run_protect(self, existing=None, fail=None, **args):
        def api(method, path, body=None):
            self.calls.append((method, path, body))
            if fail and method != "GET":
                return False, fail
            if method == "GET":
                return True, existing or []
            return True, {"id": 7}

        ns = argparse.Namespace(repo=None, checks=None, approvals=None, check=False)
        ns.__dict__.update(args)
        with mock.patch.object(fw, "api_try", side_effect=api), mock.patch("builtins.print") as out:
            try:
                fw.cmd_protect(ns)
                code = 0
            except SystemExit as e:
                code = e.code
        self.output = "\n".join(str(c.args[0]) for c in out.call_args_list if c.args)
        return code

    def rules(self, body):
        return {r["type"]: r.get("parameters") for r in body["rules"]}

    def test_creates_the_ruleset(self):
        self.assertEqual(self.run_protect(), 0)
        method, path, body = self.calls[-1]
        self.assertEqual((method, path), ("POST", "repos/o/r/rulesets"))
        self.assertEqual(body["conditions"]["ref_name"]["include"], ["~DEFAULT_BRANCH"])
        self.assertEqual(body["bypass_actors"], [])
        rules = self.rules(body)
        self.assertEqual(set(rules), {"deletion", "non_fast_forward", "pull_request"})
        self.assertEqual(rules["pull_request"]["required_approving_review_count"], 0)
        saved = json.loads(self.config.read_text())["github"]["protection"]
        self.assertEqual(saved, {"ruleset_id": 7, "checks": [], "approvals": 0})

    def test_updates_the_existing_ruleset_and_keeps_checks(self):
        self.assertEqual(self.run_protect(checks="test (3.12), lint"), 0)
        self.calls.clear()
        self.assertEqual(self.run_protect(existing=[{"id": 7, "name": fw.RULESET_NAME}], approvals=1), 0)
        method, path, body = self.calls[-1]
        self.assertEqual((method, path), ("PUT", "repos/o/r/rulesets/7"))
        rules = self.rules(body)
        self.assertEqual([c["context"] for c in rules["required_status_checks"]["required_status_checks"]],
                         ["test (3.12)", "lint"])
        self.assertEqual(rules["pull_request"]["required_approving_review_count"], 1)

    def test_other_rulesets_are_left_alone(self):
        self.run_protect(existing=[{"id": 3, "name": "release tags"}])
        self.assertEqual(self.calls[-1][0], "POST")

    def test_plan_without_rulesets(self):
        code = self.run_protect(fail="HTTP 403: Upgrade to GitHub Pro or make this repository public")
        self.assertEqual(code, 4)
        self.assertIn("GitHub Free", self.output)
        self.assertNotIn("protection", json.loads(self.config.read_text())["github"])

    def test_other_repository_leaves_the_config_alone(self):
        write_json(self.config, {"github": {"repo": "o/r", "protection": {"checks": ["ci"], "approvals": 1}}})
        self.assertEqual(self.run_protect(repo="o/other"), 0)
        rules = self.rules(self.calls[-1][2])
        self.assertNotIn("required_status_checks", rules)  # o/r's settings are not carried over
        self.assertEqual(json.loads(self.config.read_text())["github"]["protection"]["approvals"], 1)

    def test_check_mode(self):
        self.assertEqual(self.run_protect(check=True), 1)
        self.assertEqual(self.run_protect(check=True, existing=[{"id": 7, "name": fw.RULESET_NAME}]), 0)
        self.assertTrue(all(m == "GET" for m, _, _ in self.calls))


if __name__ == "__main__":
    unittest.main()
