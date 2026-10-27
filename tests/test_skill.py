"""Tests for ocas-praxis skill structure."""

import os
import unittest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestSkillStructure(unittest.TestCase):

    def test_skill_md_exists(self):
        self.assertTrue(os.path.isfile(os.path.join(SKILL_DIR, "SKILL.md")))

    def test_frontmatter_parses(self):
        import re
        path = os.path.join(SKILL_DIR, "SKILL.md")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        self.assertTrue(content.startswith("---"))
        fm_end = content.index("---", 3)
        fm = content[3:fm_end]
        self.assertIn("name:", fm)
        self.assertIn("description:", fm)

    def test_references_exist(self):
        refs = os.path.join(SKILL_DIR, "references")
        self.assertTrue(os.path.isdir(refs))

    def test_no_dead_references(self):
        import re
        path = os.path.join(SKILL_DIR, "SKILL.md")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        pattern = re.compile(r"(?:[A-Za-z0-9._\-]+/)*(?:references|scripts|assets|templates)/[A-Za-z0-9._\-/]+")
        for match in pattern.finditer(content):
            ref = match.group(0)
            ref = ref.rstrip(".")
            # Skip template patterns like YYYYMMDD
            if "YYYYMMDD" in ref or "YYYY-MM-DD" in ref or "<" in ref:
                continue
            full = os.path.join(SKILL_DIR, ref)
            # Only check .md and .py refs that look like file paths
            if os.path.splitext(ref)[1] in (".md", ".py", ".sh"):
                self.assertTrue(os.path.isfile(full), f"Dead reference: {ref}")


if __name__ == "__main__":
    unittest.main()
