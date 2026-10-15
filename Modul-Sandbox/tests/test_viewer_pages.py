from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from generate_features_dashboard import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    _insert_related_tree_entry,
    _new_related_tree_node,
    _render_related_tree_html,
)
from viewer_pages import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    DISPLAY_MODE_RAW,
    DISPLAY_MODE_RENDER,
    build_file_display_page,
    build_frontmatter_table,
    detect_code_language,
    direct_file_link_attributes,
    direct_file_link_hint,
    direct_file_link_label,
    extract_frontmatter,
    read_source_text,
    supports_direct_file_link,
    supports_render_mode,
)
from viewer_routes import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    build_section_item_file_raw_view_dest_path,
    build_section_item_file_render_view_dest_path,
    build_section_template_raw_dest_path,
    build_section_template_render_dest_path,
    feature_file_view_link_from_feature_index,
    feature_file_view_sibling_link,
    template_index_relative_link,
    template_sibling_link_for_mode,
)


class ViewerPagesTests(unittest.TestCase):
    def test_raw_view_detects_common_text_languages(self) -> None:
        expected_languages = {
            "document.md": "markdown",
            "config.xml": "xml",
            "config.yaml": "yaml",
            "config.json": "json",
            "config.toml": "toml",
            "config.ini": "ini",
            "script.py": "python",
            "script.ts": "typescript",
        }

        for filename, language in expected_languages.items():
            with self.subTest(filename=filename):
                self.assertEqual(language, detect_code_language(Path(filename)))

    def test_diagram_sources_fall_back_to_plain_text_without_extra_lexers(self) -> None:
        self.assertEqual("text", detect_code_language(Path("diagram.puml")))
        self.assertEqual("text", detect_code_language(Path("diagram.mermaid")))

    def test_frontmatter_is_rendered_as_a_table(self) -> None:
        self.assertEqual(
            [
                "    <table>",
                "    <tbody>",
                "    <tr><td>author</td><td>Kerstin Franke<br>Thorsten Drogge</td></tr>",
                "    <tr><td>state</td><td>-</td></tr>",
                "    <tr><td>comment</td><td>A &#124; B<br>Next</td></tr>",
                "    </tbody>",
                "    </table>",
            ],
            build_frontmatter_table(
                {
                    "author": ["Kerstin Franke", "Thorsten Drogge"],
                    "state": None,
                    "comment": "A | B\nNext",
                }
            ),
        )

    def test_render_view_moves_frontmatter_into_viewer_header(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            source_path = repo_root / "docs" / "guide.md"
            source_path.parent.mkdir()
            source_path.write_text(
                "---\ntitle: A Guide\nauthor:\n  - Ada\n---\n\n# Guide\n\nBody.\n",
                encoding="utf-8",
            )

            content = build_file_display_page(
                title="guide",
                source_path=source_path,
                repo_root=repo_root,
                display_mode=DISPLAY_MODE_RENDER,
                render_dest="Features/guide/render/index.md",
            )

        self.assertIn("<tr><td>title</td><td>A Guide</td></tr>", content)
        self.assertIn("<tr><td>author</td><td>Ada</td></tr>", content)
        self.assertNotIn("Frontmatter", content)
        self.assertIn("# Guide", content)
        self.assertNotIn("---\ntitle: A Guide", content)
        self.assertIn("</div>", content)
        self.assertNotIn("\n---\n", content)
        self.assertIn("## Guide", content)

    def test_raw_view_preserves_frontmatter_source(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            source_path = repo_root / "docs" / "guide.md"
            source_path.parent.mkdir()
            source_path.write_text(
                "---\ntitle: A Guide\n---\n\n# Guide\n",
                encoding="utf-8",
            )

            content = build_file_display_page(
                title="guide",
                source_path=source_path,
                repo_root=repo_root,
                display_mode=DISPLAY_MODE_RAW,
            )

        self.assertIn("<tr><td>title</td><td>A Guide</td></tr>", content)
        self.assertNotIn("Frontmatter", content)
        self.assertIn(
            "```markdown\n---\ntitle: A Guide\n---",
            content.replace("\r\n", "\n"),
        )

    def test_pdf_and_msg_links_use_original_assets(self) -> None:
        pdf_path = Path("09_Patent_Clearing/guide.pdf")
        msg_path = Path("09_Patent_Clearing/meeting.msg")

        self.assertTrue(supports_direct_file_link(pdf_path))
        self.assertTrue(supports_direct_file_link(msg_path))
        self.assertEqual(
            "guide.pdf",
            direct_file_link_label("guide", pdf_path),
        )
        self.assertEqual(
            "meeting.msg",
            direct_file_link_label("meeting", msg_path),
        )
        self.assertEqual("open in new tab", direct_file_link_hint(pdf_path))
        self.assertEqual("download file", direct_file_link_hint(msg_path))
        self.assertIn('target="_blank"', direct_file_link_attributes(pdf_path))
        self.assertIn("download", direct_file_link_attributes(msg_path))
        self.assertEqual(
            "09_Patent_Clearing/guide.pdf",
            feature_file_view_link_from_feature_index(pdf_path.as_posix(), pdf_path),
        )
        self.assertEqual(
            "09_Patent_Clearing/meeting.msg",
            feature_file_view_link_from_feature_index(msg_path.as_posix(), msg_path),
        )

    def test_related_tree_renders_direct_file_behavior(self) -> None:
        tree = _new_related_tree_node()
        _insert_related_tree_entry(
            tree,
            ["guide.pdf"],
            "guide",
            "09_Patent_Clearing/guide.pdf",
        )
        _insert_related_tree_entry(
            tree,
            ["meeting.msg"],
            "meeting",
            "09_Patent_Clearing/meeting.msg",
        )

        content = "\n".join(_render_related_tree_html(tree))

        self.assertIn(
            '<a href="09_Patent_Clearing/guide.pdf" target="_blank" '
            'rel="noopener noreferrer">guide.pdf</a> - open in new tab',
            content,
        )
        self.assertIn(
            '<a href="09_Patent_Clearing/meeting.msg" download>meeting.msg</a> '
            "- download file",
            content,
        )

    def test_invalid_or_non_mapping_frontmatter_is_preserved(self) -> None:
        for source in (
            "---\n- value\n---\n# Document\n",
            "---\n[not valid\n---\n# Document\n",
        ):
            with self.subTest(source=source):
                metadata, body = extract_frontmatter(source)
                self.assertEqual({}, metadata)
                self.assertEqual(source, body)

    def test_render_view_rewrites_assets_and_does_not_shift_fenced_headings(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            source_path = repo_root / "docs" / "Features" / "guide.md"
            source_path.parent.mkdir(parents=True)
            source_path.write_text(
                "# Heading\n\n![Diagram](images/diagram.png)\n\n```md\n# Literal\n```\n",
                encoding="utf-8",
            )
            content = build_file_display_page(
                "Guide",
                source_path,
                repo_root,
                display_mode=DISPLAY_MODE_RENDER,
                render_dest="Features/Item/guide/render/index.md",
            )

        self.assertIn("## Heading", content)
        self.assertIn("![Diagram](../../../images/diagram.png)", content)
        self.assertIn("```md\n# Literal\n```", content)

    def test_binary_text_is_safe(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            source_path = repo_root / "docs" / "Folder with spaces" / "file.bin"
            source_path.parent.mkdir(parents=True)
            source_path.write_bytes(b"first\x00second")

            self.assertEqual(
                "[Binary file preview unavailable]", read_source_text(source_path)
            )

    def test_viewer_uses_configured_source_url_when_provided(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            source_path = repo_root / "docs" / "guide.md"
            source_path.parent.mkdir()
            source_path.write_text("# Guide\n", encoding="utf-8")

            content = build_file_display_page(
                "Guide",
                source_path,
                repo_root,
                source_url="https://github.example/ORG/modul-documents/blob/main/guide.md",
                source_display_path="guide.md",
            )

        self.assertIn(
            "[guide.md](https://github.example/ORG/modul-documents/blob/main/guide.md)",
            content,
        )

    def test_viewer_routes_cover_raw_render_and_direct_links(self) -> None:
        markdown_path = Path("nested/guide.md")
        data_path = Path("nested/data.yaml")

        self.assertTrue(supports_render_mode(markdown_path))
        self.assertFalse(supports_render_mode(data_path))
        self.assertEqual(
            "Features/000_TEMPLATES/nested/guide/index.md",
            build_section_template_raw_dest_path("Features", markdown_path.as_posix()),
        )
        self.assertEqual(
            "Features/000_TEMPLATES/nested/guide/render.md",
            build_section_template_render_dest_path(
                "Features", markdown_path.as_posix()
            ),
        )
        self.assertEqual(
            "Features/Item/nested/guide/index.md",
            build_section_item_file_raw_view_dest_path(
                "Features", "Item", markdown_path.as_posix()
            ),
        )
        self.assertEqual(
            "Features/Item/nested/guide/render/index.md",
            build_section_item_file_render_view_dest_path(
                "Features", "Item", markdown_path.as_posix()
            ),
        )
        self.assertEqual(
            "nested/guide/render.md",
            template_index_relative_link(markdown_path.as_posix(), markdown_path),
        )
        self.assertEqual(
            "nested/data/index.md",
            template_index_relative_link(data_path.as_posix(), data_path),
        )
        self.assertEqual(
            "render.md",
            template_sibling_link_for_mode(DISPLAY_MODE_RAW, DISPLAY_MODE_RENDER),
        )
        self.assertEqual(
            "index.md",
            template_sibling_link_for_mode(DISPLAY_MODE_RENDER, DISPLAY_MODE_RAW),
        )
        self.assertEqual(
            "render/index.md",
            feature_file_view_sibling_link(DISPLAY_MODE_RAW, DISPLAY_MODE_RENDER),
        )
        self.assertEqual(
            "../index.md",
            feature_file_view_sibling_link(DISPLAY_MODE_RENDER, DISPLAY_MODE_RAW),
        )

    def test_viewer_routes_cover_same_mode_and_invalid_switches(self) -> None:
        self.assertEqual(
            "index.md",
            feature_file_view_sibling_link(DISPLAY_MODE_RAW, DISPLAY_MODE_RAW),
        )
        self.assertEqual(
            "index.md",
            feature_file_view_sibling_link(DISPLAY_MODE_RENDER, DISPLAY_MODE_RENDER),
        )
        with self.assertRaisesRegex(ValueError, "Unsupported mode switch"):
            feature_file_view_sibling_link("invalid", DISPLAY_MODE_RAW)
        with self.assertRaisesRegex(ValueError, "Unsupported mode switch"):
            template_sibling_link_for_mode("invalid", DISPLAY_MODE_RENDER)

    def test_legacy_encoding_project_override_and_invalid_mode_are_handled(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            source_path = repo_root / "docs" / "guide.md"
            source_path.parent.mkdir()
            source_path.write_bytes(b"caf\xe9")

            self.assertIn("caf", read_source_text(source_path))
            with self.assertRaisesRegex(ValueError, "Unsupported display mode"):
                build_file_display_page(
                    "Guide", source_path, repo_root, display_mode="invalid"
                )


if __name__ == "__main__":
    unittest.main()
