"""`fw backlog-validate`: the story standard enforced on backlog JSON files."""
import copy
import json
import unittest

from helpers import FRAMEWORK, load_module

fw = load_module("fw", "bin/fw.py")
EXAMPLE = json.loads((FRAMEWORK / "templates" / "backlog.example.json").read_text(encoding="utf-8"))


def story(key, **over):
    s = {"key": key, "type": "Story", "epic": "E1", "title": f"Story {key}", "persona": "user", "want": "x",
         "benefit": "y", "measure": "z", "acceptance_criteria": ["a", "b"], "agent_hours": 2, "review_hours": 0.5}
    s.update(over)
    return s


def backlog(*stories):
    return {"epics": [{"key": "E1", "title": "Epic", "goal": "g"}], "stories": list(stories)}


class ValidateBacklog(unittest.TestCase):
    def validate(self, b, state=None):
        return fw.validate_backlog(b, state or {})

    def assertError(self, errors, fragment):
        self.assertTrue(any(fragment in e for e in errors), f"no error containing {fragment!r} in {errors}")

    def test_shipped_example_is_valid(self):
        errors, _ = self.validate(copy.deepcopy(EXAMPLE))
        self.assertEqual(errors, [])

    def test_story_requires_user_story_fields(self):
        errors, _ = self.validate(backlog(story("US-1", persona="", measure="")))
        self.assertError(errors, "story missing 'persona'")
        self.assertError(errors, "story missing 'measure'")

    def test_story_needs_two_criteria_task_needs_one(self):
        errors, _ = self.validate(backlog(story("US-1", acceptance_criteria=["only one"])))
        self.assertError(errors, "at least 2 acceptance criteria")
        task = {"key": "T-1", "type": "Task", "title": "t", "description": "d", "acceptance_criteria": [],
                "agent_hours": 1}
        errors, _ = self.validate(backlog(task))
        self.assertError(errors, "at least 1 acceptance criterion")

    def test_gherkin_criteria_must_be_complete(self):
        errors, _ = self.validate(backlog(story("US-1", acceptance_criteria=[
            {"given": "g", "when": "w", "then": "t"}, {"given": "g", "when": "w"}])))
        self.assertError(errors, "given/when/then")

    def test_xl_is_rejected_and_size_mismatch_warned(self):
        errors, _ = self.validate(backlog(story("US-1", agent_hours=12, review_hours=1)))
        self.assertError(errors, "too big")
        errors, warns = self.validate(backlog(story("US-1", agent_hours=2, review_hours=0.5, size="L")))
        self.assertEqual(errors, [])
        self.assertTrue(any("suggests S" in w for w in warns), warns)

    def test_effort_must_be_positive_numbers(self):
        errors, _ = self.validate(backlog(story("US-1", agent_hours=0)))
        self.assertError(errors, "agent_hours must be > 0")
        errors, _ = self.validate(backlog(story("US-1", agent_hours="lots")))
        self.assertError(errors, "must be numbers")

    def test_unknown_references(self):
        errors, _ = self.validate(backlog(story("US-1", epic="E9", milestone="M9", depends_on=["US-9"])))
        self.assertError(errors, "unknown epic 'E9'")
        self.assertError(errors, "unknown milestone 'M9'")
        self.assertError(errors, "unknown dependency 'US-9'")

    def test_references_to_existing_issues_are_accepted(self):
        state = {"issues": {"E1": {"number": 3, "title": "Epic"}}}
        b = {"stories": [story("US-1", epic="E1", depends_on=["#10"])]}
        errors, _ = self.validate(b, state)
        self.assertEqual(errors, [])

    def test_duplicate_and_reused_keys(self):
        errors, _ = self.validate(backlog(story("US-1"), story("US-1")))
        self.assertError(errors, "duplicate key")
        state = {"issues": {"US-1": {"number": 7, "title": "Something else"}}}
        errors, _ = self.validate(backlog(story("US-1")), state)
        self.assertError(errors, "key already used by #7")
        state = {"issues": {"US-1": {"number": 7, "title": "Story US-1"}}}
        errors, warns = self.validate(backlog(story("US-1")), state)
        self.assertEqual(errors, [])
        self.assertTrue(any("will be skipped" in w for w in warns))

    def test_dependency_cycle(self):
        errors, _ = self.validate(backlog(story("A", depends_on=["B"]), story("B", depends_on=["A"])))
        self.assertError(errors, "dependency cycle")

    def test_invalid_type_and_priority(self):
        errors, _ = self.validate(backlog(story("US-1", type="Feature", priority="Urgent")))
        self.assertError(errors, "type must be one of")
        self.assertError(errors, "priority must be one of")


class TopoStories(unittest.TestCase):
    def test_dependencies_come_first(self):
        stories = [story("C", depends_on=["B"]), story("A"), story("B", depends_on=["A"])]
        self.assertEqual([s["key"] for s in fw.topo_stories(stories)], ["A", "B", "C"])


if __name__ == "__main__":
    unittest.main()
