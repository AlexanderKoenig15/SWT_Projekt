from __future__ import annotations

import unittest
from pathlib import Path

import markdown


REPO_ROOT = Path(__file__).resolve().parents[1]
MKDOCS_FILE = REPO_ROOT / "mkdocs.yml"


class MkdocsAbbreviationTests(unittest.TestCase):
    def test_mkdocs_registers_abbreviation_extension(self) -> None:
        mkdocs = MKDOCS_FILE.read_text(encoding="utf-8")

        self.assertIn("\n  - abbr\n", mkdocs)

    def test_definition_wraps_matching_terms_and_is_removed(self) -> None:
        source = (
            "The HTML specification is maintained by the W3C.\n\n"
            "*[HTML]: Hypertext Markup Language\n"
            "*[W3C]: World Wide Web Consortium\n"
        )

        rendered = markdown.markdown(source, extensions=["abbr"])

        self.assertIn(
            '<abbr title="Hypertext Markup Language">HTML</abbr>', rendered
        )
        self.assertIn(
            '<abbr title="World Wide Web Consortium">W3C</abbr>', rendered
        )
        self.assertNotIn("*[HTML]", rendered)
        self.assertNotIn("*[W3C]", rendered)

    def test_definitions_are_page_local(self) -> None:
        with_definition = markdown.markdown(
            "HTML\n\n*[HTML]: Hypertext Markup Language", extensions=["abbr"]
        )
        without_definition = markdown.markdown("HTML", extensions=["abbr"])

        self.assertIn(
            '<abbr title="Hypertext Markup Language">HTML</abbr>', with_definition
        )
        self.assertEqual("<p>HTML</p>", without_definition)

    def test_fenced_code_keeps_abbreviation_syntax_literal(self) -> None:
        source = "```markdown\n*[HTML]: Hypertext Markup Language\nHTML\n```"

        rendered = markdown.markdown(source, extensions=["abbr", "fenced_code"])

        self.assertIn("*[HTML]: Hypertext Markup Language", rendered)
        self.assertNotIn(
            '<abbr title="Hypertext Markup Language">HTML</abbr>', rendered
        )


if __name__ == "__main__":
    unittest.main()