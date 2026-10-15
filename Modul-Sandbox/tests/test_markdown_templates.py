from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from markdown_templates import render_markdown_template  # noqa: E402


class MarkdownTemplateTests(unittest.TestCase):
    def test_empty_replacements_leave_template_unchanged(self) -> None:
        template = "# [[AUTO:TITLE]]\n"

        self.assertEqual(template, render_markdown_template(template, {}))

    def test_block_placeholder_preserves_template_indentation(self) -> None:
        rendered = render_markdown_template(
            "!!! info \"Details\"\n\n    [[AUTO:DETAILS]]\n",
            {"[[AUTO:DETAILS]]": "First\n\nSecond"},
        )

        self.assertEqual(
            "!!! info \"Details\"\n\n    First\n    \n    Second\n",
            rendered,
        )

    def test_inline_and_missing_placeholders_are_replaced_without_changing_text(self) -> None:
        rendered = render_markdown_template(
            "# [[AUTO:TITLE]]\n\n[[AUTO:EMPTY]]\n",
            {"[[AUTO:TITLE]]": "Overview", "[[AUTO:EMPTY]]": ""},
        )

        self.assertEqual("# Overview\n\n\n", rendered)

    def test_multiple_replacements_do_not_reprocess_generated_placeholder_text(self) -> None:
        rendered = render_markdown_template(
            "[[AUTO:FIRST]]\n[[AUTO:SECOND]]\n",
            {
                "[[AUTO:FIRST]]": "[[AUTO:SECOND]]",
                "[[AUTO:SECOND]]": "done",
            },
        )

        self.assertEqual("[[AUTO:SECOND]]\ndone\n", rendered)


if __name__ == "__main__":
    unittest.main()