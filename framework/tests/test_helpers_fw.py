"""Pure helpers of fw.py: parsing, sizing, dotted config keys, MANIFEST matching, workday arithmetic."""
import datetime as dt
import unittest

from helpers import load_module

fw = load_module("fw", "bin/fw.py")


class Parsing(unittest.TestCase):
    def test_size_for_boundaries(self):
        self.assertEqual(fw.size_for(0.5), "XS")
        self.assertEqual(fw.size_for(1), "XS")
        self.assertEqual(fw.size_for(1.5), "S")
        self.assertEqual(fw.size_for(6), "M")
        self.assertEqual(fw.size_for(12), "L")
        self.assertEqual(fw.size_for(12.5), "XL")

    def test_parse_deps(self):
        self.assertEqual(fw.parse_deps("text\n<!-- fw:depends-on #3, #12 -->\n"), [3, 12])
        self.assertEqual(fw.parse_deps("<!--fw:depends-on 7-->"), [7])
        self.assertEqual(fw.parse_deps("no marker"), [])
        self.assertEqual(fw.parse_deps(None), [])

    def test_canon_status(self):
        self.assertEqual(fw.canon_status("Todo"), "ready")
        self.assertEqual(fw.canon_status("Doing"), "in progress")
        self.assertEqual(fw.canon_status(" In Review "), "in review")
        self.assertEqual(fw.canon_status(None), "backlog")
        self.assertEqual(fw.canon_status("Done"), "done")

    def test_ref_number(self):
        state = {"US-1": {"number": 42}}
        self.assertEqual(fw.ref_number(5, state), 5)
        self.assertEqual(fw.ref_number("#12", state), 12)
        self.assertEqual(fw.ref_number("US-1", state), 42)
        self.assertIsNone(fw.ref_number("US-2", state))

    def test_parse_frontmatter(self):
        fm, body = fw.parse_frontmatter('---\nname: a\ndescription: "b: c"\ntools: Read\n---\n# Body\n')
        self.assertEqual(fm, {"name": "a", "description": "b: c", "tools": "Read"})
        self.assertEqual(body.strip(), "# Body")
        self.assertEqual(fw.parse_frontmatter("# no frontmatter")[0], None)
        self.assertEqual(fw.parse_frontmatter("---\nunterminated")[0], None)


class DottedConfig(unittest.TestCase):
    def test_dig_and_set(self):
        d = {}
        fw.set_dotted(d, "framework.upstream", "u")
        fw.set_dotted(d, "capacity.hours_per_day", 5)
        self.assertEqual(d, {"framework": {"upstream": "u"}, "capacity": {"hours_per_day": 5}})
        self.assertEqual(fw.dig(d, "framework.upstream"), "u")
        self.assertEqual(fw.dig(d, "framework.missing", "x"), "x")
        self.assertEqual(fw.dig(d, "framework.upstream.deeper", "x"), "x")


class Manifest(unittest.TestCase):
    def test_template_manifest_ownership(self):
        owned, scaffold = fw.manifest()
        self.assertTrue(fw.matches("framework/bin/fw.py", owned))
        self.assertTrue(fw.matches("framework/tests/test_helpers_fw.py", owned))
        self.assertTrue(fw.matches(".claude/skills/fw-work/SKILL.md", owned))
        self.assertTrue(fw.matches("docs/framework/workflow.md", owned))
        self.assertTrue(fw.matches("CLAUDE.md", scaffold))
        self.assertTrue(fw.matches("docs/product/brief.md", scaffold))
        # project-specific skills and the template's own CI are never shipped
        self.assertFalse(fw.matches(".claude/skills/feature/SKILL.md", owned + scaffold))
        self.assertFalse(fw.matches(".github/workflows/framework-tests.yml", owned + scaffold))


class Workdays(unittest.TestCase):
    MON_TO_FRI = {1, 2, 3, 4, 5}

    def test_align_skips_weekend(self):
        self.assertEqual(fw.align(dt.date(2026, 10, 10), self.MON_TO_FRI), dt.date(2026, 10, 12))  # Sat → Mon
        self.assertEqual(fw.align(dt.date(2026, 10, 7), self.MON_TO_FRI), dt.date(2026, 10, 7))

    def test_add_workdays(self):
        fri = dt.date(2026, 10, 9)
        self.assertEqual(fw.add_workdays(fri, 0, self.MON_TO_FRI), fri)
        self.assertEqual(fw.add_workdays(fri, 1, self.MON_TO_FRI), dt.date(2026, 10, 12))
        self.assertEqual(fw.add_workdays(fri, 5, self.MON_TO_FRI), dt.date(2026, 10, 16))
        self.assertEqual(fw.add_workdays(fri, 1, {1, 3, 5}), dt.date(2026, 10, 12))
        self.assertEqual(fw.add_workdays(fri, 2, {1, 3, 5}), dt.date(2026, 10, 14))


if __name__ == "__main__":
    unittest.main()
