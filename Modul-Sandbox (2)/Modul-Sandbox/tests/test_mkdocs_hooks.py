from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from mkdocs.structure.files import File, Files

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import mkdocs_hooks  # noqa: E402
import features_section  # noqa: E402
from responsibility import ResolvedResponsibility, ResolvedRouting  # noqa: E402
from section_processors import GeneratedSectionProcessor  # noqa: E402


class CategoryRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        mkdocs_hooks._categories_cache = None
        self.temporary_directory = TemporaryDirectory()
        self.repo_root = Path(self.temporary_directory.name) / "dashboard"
        self.docs_root = self.repo_root / "docs"
        (self.docs_root / "Home").mkdir(parents=True)
        (self.docs_root / "About").mkdir()
        (self.docs_root / "categories.yaml").write_text(
            "categories: []\n", encoding="utf-8"
        )
        self.repo_root_patch = patch.object(mkdocs_hooks, "REPO_ROOT", self.repo_root)
        self.repo_root_patch.start()
        self.categories_file_patch = patch.object(
            mkdocs_hooks, "CATEGORIES_FILE", self.docs_root / "categories.yaml"
        )
        self.categories_file_patch.start()

    def tearDown(self) -> None:
        self.categories_file_patch.stop()
        self.repo_root_patch.stop()
        self.temporary_directory.cleanup()
        mkdocs_hooks._categories_cache = None

    def test_categories_load_navigation_without_request_routing(self) -> None:
        category_data = {
            "categories": [
                {
                    "title": "Reference",
                    "path": "Reference",
                },
                {
                    "title": "Archived",
                    "path": "Archived",
                    "enabled": False,
                },
            ]
        }
        with TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            (repo_root / "docs" / "Reference").mkdir(parents=True)
            with (
                patch.object(mkdocs_hooks, "REPO_ROOT", repo_root),
                patch.object(
                    mkdocs_hooks,
                    "CATEGORIES_FILE",
                    repo_root / "docs" / "categories.yaml",
                ),
                patch.object(mkdocs_hooks, "_load_yaml", return_value=category_data),
            ):
                categories = mkdocs_hooks._load_categories()

        self.assertEqual(["Reference"], [category["title"] for category in categories])
        self.assertNotIn("dashboard_routing", categories[0])
        self.assertNotIn("content_routing", categories[0])

    def test_category_page_uses_compact_footer_metadata(self) -> None:
        page = SimpleNamespace(
            file=SimpleNamespace(src_uri="Reference/index.md"),
            meta={},
            canonical_url="https://pages.example/Reference/",
        )
        responsibility = ResolvedResponsibility(
            responsible="SFO",
            owners=("Reference Owner",),
            dashboard_request=ResolvedRouting("ORG/1", ("dashboard-owner",)),
            content_request=ResolvedRouting("ORG/2", ("content-owner",)),
        )
        with patch.object(
            mkdocs_hooks, "resolve_responsibility", return_value=responsibility
        ):
            content = mkdocs_hooks.on_page_markdown(
                "# Reference\n\nOverview\n", page
            )

        self.assertEqual("# Reference\n\nOverview\n", content)
        self.assertIn("projects=ORG%2F1", page.meta["feedback_links"][0]["url"])
        self.assertIn("assignees=dashboard-owner", page.meta["feedback_links"][0]["url"])
        self.assertEqual(["Reference Owner"], page.meta["responsibility"]["owners"])
        self.assertEqual(
            ["https://pages.example/Reference/"],
            parse_qs(
                urlsplit(page.meta["feedback_links"][0]["url"]).query
            )["location"],
        )

    def test_feature_page_uses_compact_footer_metadata(self) -> None:
        page = SimpleNamespace(
            file=SimpleNamespace(src_uri="Library/Example/index.md"),
            meta={},
            canonical_url="https://pages.example/Library/Example/",
        )
        responsibility = ResolvedResponsibility(
            responsible="SFO",
            owners=("Feature Owner",),
            dashboard_request=ResolvedRouting("ORG/1", ("dashboard-owner",)),
            content_request=ResolvedRouting("ORG/2", ("feature-owner",)),
        )
        with patch.object(
            mkdocs_hooks, "resolve_responsibility", return_value=responsibility
        ):
            content = mkdocs_hooks.on_page_markdown(
                "# Example\n\nOverview\n",
                page,
            )

        self.assertEqual("# Example\n\nOverview\n", content)
        self.assertIn("projects=ORG%2F1", page.meta["feedback_links"][0]["url"])
        self.assertIn("projects=ORG%2F2", page.meta["feedback_links"][1]["url"])

    def test_local_preview_notice_is_prepended_when_configured(self) -> None:
        with patch.dict(
            "os.environ",
            {mkdocs_hooks.LOCAL_PREVIEW_NOTICE_ENV: "Only local content is shown."},
        ):
            content = mkdocs_hooks._prepend_local_preview_notice("# Page\n")

        self.assertTrue(content.startswith('!!! warning "Local preview"'))
        self.assertIn("Only local content is shown.", content)

    def test_feature_fallback_notice_is_scoped_to_shadowed_mount(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            status_file = Path(temporary_directory) / "assembly-status.json"
            status_file.write_text(
                '{"version":1,"shadowed_sources":[{"id":"seclog",'
                '"repository":"ORG/Modul-Feature-SecLog",'
                '"mount_path":"Features/SecLog",'
                '"effective_source_id":"documents"}]}',
                encoding="utf-8",
            )
            with patch.dict(
                "os.environ",
                {"MODUL_DASHBOARD_ASSEMBLY_STATUS_FILE": str(status_file)},
            ):
                feature_content = mkdocs_hooks._prepend_feature_fallback_notice(
                    "# Feature\n", "Features/SecLog/design/index.md"
                )
                unrelated_content = mkdocs_hooks._prepend_feature_fallback_notice(
                    "# Other\n", "Hardware/index.md"
                )

        self.assertIn('!!! info "Feature content transition: SecLog"', feature_content)
        self.assertIn("ORG/Modul-Feature-SecLog", feature_content)
        self.assertIn("still comes from `Modul-Documents`", feature_content)
        self.assertEqual("# Other\n", unrelated_content)

    def test_page_markdown_renders_shadowed_feature_notice(self) -> None:
        page = SimpleNamespace(
            file=SimpleNamespace(src_uri="Features/SecLog/index.md"),
            meta={},
            canonical_url="https://pages.example/Features/SecLog/",
        )
        with TemporaryDirectory() as temporary_directory:
            status_file = Path(temporary_directory) / "assembly-status.json"
            status_file.write_text(
                '{"version":1,"shadowed_sources":[{"id":"seclog",'
                '"repository":"ORG/Modul-Feature-SecLog",'
                '"mount_path":"Features/SecLog",'
                '"effective_source_id":"documents"}]}',
                encoding="utf-8",
            )
            with (
                patch.dict(
                    "os.environ",
                    {"MODUL_DASHBOARD_ASSEMBLY_STATUS_FILE": str(status_file)},
                ),
                patch.object(mkdocs_hooks, "_collect_generated_section_names", return_value=[]),
                patch.object(
                    mkdocs_hooks,
                    "resolve_responsibility",
                    return_value=ResolvedResponsibility(
                        "SFO",
                        ("Owner",),
                        ResolvedRouting("ORG/1", ("dashboard-owner",)),
                        ResolvedRouting("ORG/2", ("content-owner",)),
                    ),
                ),
            ):
                rendered = mkdocs_hooks.on_page_markdown("# Feature\n", page)

        self.assertIn('!!! info "Feature content transition: SecLog"', rendered)
        self.assertIn("ORG/Modul-Feature-SecLog", rendered)

    def test_page_context_uses_registered_source_owner_for_edit_action(self) -> None:
        page = SimpleNamespace(
            file=SimpleNamespace(
                src_uri="Features/Example/overview.yaml", edit_uri="overview.yaml"
            ),
            edit_url="old-url",
        )
        with patch.object(
            mkdocs_hooks,
            "build_docs_source_url",
            return_value="https://github.example/ORG/modul-documents/blob/main/Features/Example/overview.yaml",
        ) as build_url:
            context = mkdocs_hooks.on_page_context({}, page, SimpleNamespace(), None)

        self.assertEqual({}, context)
        self.assertEqual(
            "https://github.example/ORG/modul-documents/blob/main/Features/Example/overview.yaml",
            page.edit_url,
        )
        build_url.assert_called_once_with(
            "Features/Example/overview.yaml", mkdocs_hooks.load_content_sources()
        )

    def test_page_context_leaves_generated_pages_without_edit_actions(self) -> None:
        page = SimpleNamespace(
            file=SimpleNamespace(src_uri="Features/Example/index.md", edit_uri=None),
            edit_url=None,
        )
        with patch.object(mkdocs_hooks, "build_docs_source_url") as build_url:
            mkdocs_hooks.on_page_context({}, page, SimpleNamespace(), None)

        self.assertIsNone(page.edit_url)
        build_url.assert_not_called()

    def test_page_context_applies_root_responsibility_to_404(self) -> None:
        page = SimpleNamespace(
            file=SimpleNamespace(src_uri="", edit_uri=None),
            url="404.html",
            meta={},
            edit_url=None,
        )
        with TemporaryDirectory() as temporary_directory:
            docs_root = Path(temporary_directory)
            (docs_root / "responsibility.yaml").write_text(
                "responsible: Dashboard\n"
                "owner: [Dashboard Owner]\n"
                "dashboard_request:\n"
                "  github_project: ORG/1\n"
                "  assignees: [dashboard-owner]\n"
                "content_request:\n"
                "  github_project: ORG/2\n"
                "  assignees: [content-owner]\n",
                encoding="utf-8",
            )
            with patch.object(mkdocs_hooks, "get_docs_root", return_value=docs_root):
                mkdocs_hooks.on_page_context({}, page, SimpleNamespace(), None)

        self.assertEqual("Dashboard", page.meta["responsibility"]["responsible"])
        self.assertEqual(["Dashboard Owner"], page.meta["responsibility"]["owners"])
        self.assertEqual(2, len(page.meta["feedback_links"]))
        self.assertNotIn("location", page.meta["feedback_links"][0]["url"])

    def test_local_preview_omits_categories_missing_from_virtual_docs_root(self) -> None:
        routing = {"github_project": "ORG/1", "assignees": ["owner"]}
        category_data = {
            "categories": [
                {
                    "title": "Available",
                    "path": "Available",
                    "dashboard_request": routing,
                    "content_request": routing,
                },
                {
                    "title": "Unavailable",
                    "path": "Unavailable",
                    "dashboard_request": routing,
                    "content_request": routing,
                },
            ]
        }
        with TemporaryDirectory() as temporary_directory:
            docs_root = Path(temporary_directory)
            (docs_root / "Available").mkdir()
            with (
                patch.dict(
                    "os.environ",
                    {
                        mkdocs_hooks.LOCAL_PREVIEW_NOTICE_ENV: "Partial preview.",
                        "MODUL_DASHBOARD_DOCS_DIR": str(docs_root),
                    },
                ),
                patch.object(mkdocs_hooks, "CATEGORIES_FILE", docs_root / "categories.yaml"),
                patch.object(mkdocs_hooks, "_load_yaml", return_value=category_data),
            ):
                categories = mkdocs_hooks._load_categories()

        self.assertEqual(["Available"], [category["title"] for category in categories])

    def test_feature_overview_uses_compact_footer_metadata(self) -> None:
        page = SimpleNamespace(
            file=SimpleNamespace(src_uri="Library/Example/index.md"),
            meta={},
        )
        responsibility = ResolvedResponsibility(
            owners=("Feature Owner",),
            dashboard_request=ResolvedRouting("ORG/1", ("dashboard-owner",)),
            content_request=ResolvedRouting("ORG/2", ("feature-owner",)),
        )
        with patch.object(
            mkdocs_hooks, "resolve_responsibility", return_value=responsibility
        ):
            content = mkdocs_hooks.on_page_markdown("# Example\n\nOverview\n", page)

        self.assertEqual("# Example\n\nOverview\n", content)
        self.assertIn(
            "projects=ORG%2F1", page.meta["feedback_links"][0]["url"]
        )
        self.assertIn(
            "projects=ORG%2F2", page.meta["feedback_links"][1]["url"]
        )

    def test_compact_feedback_links_are_added_to_other_pages(self) -> None:
        page = SimpleNamespace(
            file=SimpleNamespace(src_uri="Library/Example/delivery/index.md"),
            meta={},
        )
        responsibility = ResolvedResponsibility(
            owners=("Feature Owner",),
            dashboard_request=ResolvedRouting("ORG/1", ("dashboard-owner",)),
            content_request=ResolvedRouting("ORG/2", ("feature-owner",)),
        )
        with patch.object(
            mkdocs_hooks, "resolve_responsibility", return_value=responsibility
        ):
            content = mkdocs_hooks.on_page_markdown("# Delivery\n\nDetails\n", page)

        self.assertEqual("# Delivery\n\nDetails\n", content)
        self.assertEqual(2, len(page.meta["feedback_links"]))
        self.assertIn("projects=ORG%2F1", page.meta["feedback_links"][0]["url"])
        self.assertIn("projects=ORG%2F2", page.meta["feedback_links"][1]["url"])

    def test_template_pages_use_feedback_routing(self) -> None:
        page = SimpleNamespace(
            file=SimpleNamespace(src_uri="Library/000_TEMPLATES/example/index.md"),
            meta={},
        )
        responsibility = ResolvedResponsibility(
            dashboard_request=ResolvedRouting("ORG/1", ("dashboard-owner",)),
            content_request=ResolvedRouting("ORG/2", ("content-owner",)),
        )
        with patch.object(
            mkdocs_hooks, "resolve_responsibility", return_value=responsibility
        ):
            content = mkdocs_hooks.on_page_markdown(
                "# Template\n\nTemplate content\n", page
            )

        self.assertEqual("# Template\n\nTemplate content\n", content)
        self.assertEqual(2, len(page.meta["feedback_links"]))
        self.assertIn("projects=ORG%2F1", page.meta["feedback_links"][0]["url"])

    def test_incomplete_responsibility_renders_disabled_feedback_metadata(self) -> None:
        page = SimpleNamespace(
            file=SimpleNamespace(src_uri="Reference/index.md"), meta={}
        )
        with patch.object(
            mkdocs_hooks,
            "resolve_responsibility",
            return_value=ResolvedResponsibility(responsible="SFO"),
        ):
            content = mkdocs_hooks.on_page_markdown("# Reference\n", page)

        self.assertEqual("# Reference\n", content)
        self.assertTrue(all(link["disabled"] for link in page.meta["feedback_links"]))
        self.assertIn("owner", page.meta["responsibility"]["missing"])

    def test_ordinary_page_gets_responsibility_table_model(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            docs_root = Path(temporary_directory)
            source_path = docs_root / "Reference" / "index.md"
            source_path.parent.mkdir(parents=True)
            source_path.write_text("# Reference\n", encoding="utf-8")
            page = SimpleNamespace(
                file=SimpleNamespace(src_uri="Reference/index.md"), meta={}
            )
            responsibility = ResolvedResponsibility(
                responsible="Reference Team",
                owners=("Reference Owner",),
                dashboard_request=ResolvedRouting(
                    "ORG/1", ("dashboard-owner",)
                ),
                content_request=ResolvedRouting("ORG/2", ("content-owner",)),
            )
            with (
                patch.object(mkdocs_hooks, "get_docs_root", return_value=docs_root),
                patch.object(
                    mkdocs_hooks,
                    "_source_reference_for_path",
                    return_value=(
                        "https://github.example/content/blob/main/Reference/index.md",
                        "Reference/index.md",
                    ),
                ),
            ):
                table = mkdocs_hooks._responsibility_table_for_page(
                    page, "Reference/index.md", responsibility
                )

        self.assertEqual("Reference Team", table["responsible"])
        self.assertEqual(["Reference Owner"], table["owners"])
        self.assertIn("/orgs/ORG/projects/2", table["content_project_url"])
        self.assertEqual("Reference/index.md", table["source_display_path"])
        self.assertNotIn("ORG/1", table["content_project_url"])

    def test_responsibility_table_excludes_features_templates_and_generated_viewers(self) -> None:
        responsibility = ResolvedResponsibility()
        feature_page = SimpleNamespace(
            file=SimpleNamespace(src_uri="Features/Example/index.md"), meta={}
        )
        template_page = SimpleNamespace(
            file=SimpleNamespace(
                src_uri="Reference/000_TEMPLATES/schema/index.md"
            ),
            meta={},
        )
        generated_viewer = SimpleNamespace(
            file=SimpleNamespace(
                src_uri="Reference/guide/render/index.md", generated_by="hook"
            ),
            meta={},
        )
        with patch.object(
            mkdocs_hooks, "get_docs_root", return_value=Path("C:/docs")
        ), patch.object(
            mkdocs_hooks,
            "_source_reference_for_path",
            return_value=("https://source", "Reference/guide.md"),
        ):
            feature = mkdocs_hooks._responsibility_table_for_page(
                feature_page, "Features/Example/index.md", responsibility
            )
            template = mkdocs_hooks._responsibility_table_for_page(
                template_page, "Reference/000_TEMPLATES/schema/index.md", responsibility
            )
            viewer = mkdocs_hooks._responsibility_table_for_page(
                generated_viewer, "Reference/guide/render/index.md", responsibility
            )

        self.assertIsNone(feature)
        self.assertIsNone(template)
        self.assertIsNone(viewer)

    def test_features_template_is_policy_node_for_section_and_feature_pages(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            docs_root = Path(temporary_directory) / "docs"
            template_root = docs_root / "Features" / "000_TEMPLATES"
            feature_root = docs_root / "Features" / "Example"
            template_root.mkdir(parents=True)
            feature_root.mkdir()
            (template_root / "overview.yaml").write_text(
                "feature_name: required\n"
                "responsible: SFO\n"
                "owner: []\n"
                "processes: {}\n"
                "groups: []\n"
                "process_readiness_weights:\n"
                "  source: 10\n"
                "  metadata: 10\n"
                "  progress: 80\n",
                encoding="utf-8",
            )
            (feature_root / "overview.yaml").write_text(
                "feature_name: Example\nowner: Feature Owner\n",
                encoding="utf-8",
            )
            with patch.dict(
                "os.environ", {"MODUL_DASHBOARD_DOCS_DIR": str(docs_root)}
            ):
                features_section.reset_cache()
                section_override = features_section.get_feature_responsibility_override(
                    "Features/index.md"
                )
                feature_override = features_section.get_feature_responsibility_override(
                    "Features/Example/index.md"
                )

        self.assertEqual("SFO", section_override.responsible)
        self.assertTrue(section_override.owners_clear)
        self.assertEqual("SFO", feature_override.responsible)
        self.assertEqual(("Feature Owner",), feature_override.owners)

    def test_feature_policy_preserves_template_routes_and_explicit_nulls(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            docs_root = Path(temporary_directory) / "docs"
            template_root = docs_root / "Features" / "000_TEMPLATES"
            feature_root = docs_root / "Features" / "Example"
            template_root.mkdir(parents=True)
            feature_root.mkdir()
            (template_root / "overview.yaml").write_text(
                "responsible: SFO\n"
                "owner: null\n"
                "dashboard_request:\n"
                "  github_project: ORG/10\n"
                "  assignees: [dashboard-owner]\n"
                "content_request:\n"
                "  github_project: ORG/11\n"
                "  assignees: [content-owner]\n"
                "processes: {}\n"
                "groups: []\n"
                "process_readiness_weights:\n"
                "  source: 10\n"
                "  metadata: 10\n"
                "  progress: 80\n",
                encoding="utf-8",
            )
            (feature_root / "overview.yaml").write_text(
                "feature_name: Example\n"
                "responsible: null\n"
                "owner: null\n"
                "content_request:\n"
                "  github_project: ORG/20\n"
                "  assignees: [feature-owner]\n",
                encoding="utf-8",
            )
            with patch.dict(
                "os.environ", {"MODUL_DASHBOARD_DOCS_DIR": str(docs_root)}
            ):
                features_section.reset_cache()
                feature_override = features_section.get_feature_responsibility_override(
                    "Features/Example/index.md"
                )

        self.assertTrue(feature_override.responsible_clear)
        self.assertTrue(feature_override.owners_clear)
        self.assertEqual("ORG/10", feature_override.dashboard_request.github_project)
        self.assertEqual("ORG/20", feature_override.content_request.github_project)

    def test_feature_dashboard_route_is_allowed_by_metadata_validation(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            feature_dir = Path(temporary_directory) / "Example"
            feature_dir.mkdir()
            with patch.object(
                features_section,
                "_display_relative_path",
                return_value="Features/Example/overview.yaml",
            ):
                with self.assertNoLogs("mkdocs.hooks", level="WARNING"):
                    features_section._warn_template_mismatches(
                        "Features",
                        feature_dir,
                        {
                            "feature_name": "Example",
                            "dashboard_request": {
                                "github_project": "ORG/1",
                                "assignees": ["dashboard-owner"],
                            },
                        },
                        {
                            "feature_name": SimpleNamespace(
                                state="required", default=None
                            )
                        },
                        {},
                    )

    def test_feature_policy_rejects_invalid_owner_values(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            docs_root = Path(temporary_directory) / "docs"
            template_root = docs_root / "Features" / "000_TEMPLATES"
            feature_root = docs_root / "Features" / "Example"
            template_root.mkdir(parents=True)
            feature_root.mkdir()
            (template_root / "overview.yaml").write_text(
                "responsible: SFO\nowner: null\nprocesses: {}\n"
                "groups: []\nprocess_readiness_weights:\n"
                "  source: 10\n  metadata: 10\n  progress: 80\n",
                encoding="utf-8",
            )
            (feature_root / "overview.yaml").write_text(
                "feature_name: Example\nowner: 123\n", encoding="utf-8"
            )
            with patch.dict(
                "os.environ", {"MODUL_DASHBOARD_DOCS_DIR": str(docs_root)}
            ):
                features_section.reset_cache()
                with self.assertRaisesRegex(ValueError, "owner.*non-empty strings"):
                    features_section.get_feature_responsibility_override(
                        "Features/Example/index.md"
                    )

    def test_on_config_builds_navigation_in_category_order(self) -> None:
        config = SimpleNamespace(nav=[])

        categories = [
            {"title": "Reference", "kind": "page", "path": "Reference/index.md"},
            {"title": "Guides", "kind": "page", "path": "Guides/index.md"},
        ]
        with patch.object(mkdocs_hooks, "_load_categories", return_value=categories):
            result = mkdocs_hooks.on_config(config)

        self.assertIs(config, result)
        self.assertEqual(
            ["Reference", "Guides"],
            [next(iter(entry)) for entry in config.nav],
        )

    def test_directory_navigation_discovers_only_displayable_markdown(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            category_root = repo_root / "docs" / "Reference"
            (category_root / "Topic").mkdir(parents=True)
            (category_root / "Single").mkdir()
            (category_root / "_Private").mkdir()
            (category_root / "000_TEMPLATES").mkdir()
            (category_root / "index.md").write_text("# Reference\n", encoding="utf-8")
            (category_root / "guide.md").write_text("# Guide\n", encoding="utf-8")
            (category_root / "notes.txt").write_text("notes\n", encoding="utf-8")
            (category_root / "Topic" / "index.md").write_text(
                "# Topic\n", encoding="utf-8"
            )
            (category_root / "Topic" / "deep_dive.md").write_text(
                "# Deep dive\n", encoding="utf-8"
            )
            (category_root / "Single" / "index.md").write_text(
                "# Single\n", encoding="utf-8"
            )
            (category_root / "_Private" / "index.md").write_text(
                "# Private\n", encoding="utf-8"
            )
            (category_root / "000_TEMPLATES" / "index.md").write_text(
                "# Templates\n", encoding="utf-8"
            )
            with patch.object(mkdocs_hooks, "REPO_ROOT", repo_root):
                entries = mkdocs_hooks._discover_directory_nav_entries("Reference")

        self.assertEqual(
            [
                {"Overview": "Reference/index.md"},
                {"Guide": "Reference/guide.md"},
                {"Single": "Reference/Single/index.md"},
                {
                    "Topic": [
                        {"Overview": "Reference/Topic/index.md"},
                        {"Deep Dive": "Reference/Topic/deep_dive.md"},
                    ]
                },
            ],
            entries,
        )

    def test_group_child_navigation_uses_the_active_docs_root(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            docs_root = Path(temporary_directory) / "assembled-docs"
            child_path = docs_root / "Guides" / "install.md"
            child_path.parent.mkdir(parents=True)
            child_path.write_text("# Install\n", encoding="utf-8")

            with patch.dict(
                "os.environ", {"MODUL_DASHBOARD_DOCS_DIR": str(docs_root)}
            ):
                entry = mkdocs_hooks._build_group_child_nav_entry(
                    "Guides",
                    {"title": "Install", "path": "Guides/install.md"},
                    1,
                )

        self.assertEqual({"Install": "Guides/install.md"}, entry)

    def test_template_navigation_excludes_assets_and_direct_files(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            template_root = repo_root / "docs" / "Library" / "000_TEMPLATES"
            (template_root / "Nested").mkdir(parents=True)
            (template_root / "images").mkdir()
            (template_root / "overview.yaml").write_text("fields: {}\n", encoding="utf-8")
            (template_root / "guide.md").write_text("# Guide\n", encoding="utf-8")
            (template_root / "feature_detail.md").write_text(
                "# Internal\n", encoding="utf-8"
            )
            (template_root / "manual.pdf").write_bytes(b"%PDF")
            (template_root / "Nested" / "checklist.yaml").write_text(
                "steps: []\n", encoding="utf-8"
            )
            (template_root / "images" / "diagram.png").write_bytes(b"image")
            with patch.object(mkdocs_hooks, "REPO_ROOT", repo_root):
                sources = mkdocs_hooks._collect_displayable_template_sources("Library")
                navigation = mkdocs_hooks._build_templates_nav_entries("Library")
                index = mkdocs_hooks._build_templates_index_page("Library")

        self.assertEqual(
            {"guide.md", "overview.yaml", "Nested/checklist.yaml"},
            {relative_path for relative_path, _ in sources},
        )
        self.assertIn(
            {"Guide": "Library/000_TEMPLATES/guide/index.md"}, navigation
        )
        self.assertIn(
            {"Guide (rendered)": "Library/000_TEMPLATES/guide/render.md"},
            navigation,
        )
        self.assertIn("Schema Template", index)
        self.assertIn("## Nested", index)
        self.assertIn("Checklist", index)
        self.assertNotIn("manual.pdf", index)
        self.assertNotIn("Internal", index)

    def test_root_home_page_rewrites_relative_links_but_keeps_external_urls(self) -> None:
        source = (
            "---\nhero_cta_href: '../Features'\n---\n\n"
            "[Features](../Features) [External](https://example.test) [Anchor](#top)\n"
        )

        rendered = mkdocs_hooks._build_root_home_page(source)

        self.assertIn("hero_cta_href: 'Features'", rendered)
        self.assertIn("[Features](Features)", rendered)
        self.assertIn("[External](https://example.test)", rendered)
        self.assertIn("[Anchor](#top)", rendered)

    def test_root_home_page_normalizes_second_hero_cta_href(self) -> None:
        source = (
            "---\n"
            "hero_cta_href: '../Features'\n"
            'hero_cta2_href: "../About/"\n'
            "---\n"
        )

        rendered = mkdocs_hooks._build_root_home_page(source)

        self.assertIn("hero_cta_href: 'Features'", rendered)
        self.assertIn('hero_cta2_href: "About/"', rendered)

    def test_root_home_page_keeps_external_second_hero_cta_href(self) -> None:
        source = '---\nhero_cta2_href: "https://example.test"\n---\n'

        rendered = mkdocs_hooks._build_root_home_page(source)

        self.assertIn('hero_cta2_href: "https://example.test"', rendered)

    def test_on_files_preserves_customer_markdown_for_strict_validation(self) -> None:
        config = SimpleNamespace(
            site_dir=str(SCRIPTS_DIR.parent / "site"),
            use_directory_urls=True,
            plugins=SimpleNamespace(_current_plugin=None),
        )

        customer_file = SimpleNamespace(
            src_uri="Features/Item/document.md",
            content_string="# Customer document\n",
        )
        with patch.object(mkdocs_hooks, "_load_categories", return_value=[]):
            result = mkdocs_hooks.on_files(Files([customer_file]), config)

        self.assertEqual([customer_file], list(result))

    def test_template_pages_receive_body_marker_only(self) -> None:
        template_page = SimpleNamespace(url="Features/000_TEMPLATES/schema/")
        ordinary_page = SimpleNamespace(url="Features/Item/")
        html = '<html><body class="md-typeset">Content</body></html>'

        marked = mkdocs_hooks.on_post_page(html, template_page)

        self.assertIn('data-dashboard-template-page="true"', marked)
        self.assertEqual(html, mkdocs_hooks.on_post_page(html, ordinary_page))

    def test_category_loader_rejects_duplicate_titles_and_missing_paths(self) -> None:
        invalid_cases = (
            (
                {
                    "categories": [
                        {
                            "title": "Duplicate",
                            "path": "Home",
                            "dashboard_request": {
                                "github_project": "AS-IO/11",
                                "assignees": ["owner"],
                            },
                            "content_request": {
                                "github_project": "AS-IO/11",
                                "assignees": ["owner"],
                            },
                        },
                        {
                            "title": "Duplicate",
                            "path": "About",
                            "dashboard_request": {
                                "github_project": "AS-IO/11",
                                "assignees": ["owner"],
                            },
                            "content_request": {
                                "github_project": "AS-IO/11",
                                "assignees": ["owner"],
                            },
                        },
                    ]
                },
                "Duplicate category title",
            ),
            (
                {
                    "categories": [
                        {
                            "title": "Missing",
                            "path": "not-a-real-category",
                            "dashboard_request": {
                                "github_project": "AS-IO/11",
                                "assignees": ["owner"],
                            },
                            "content_request": {
                                "github_project": "AS-IO/11",
                                "assignees": ["owner"],
                            },
                        }
                    ]
                },
                "references missing path",
            ),
        )

        for categories, error in invalid_cases:
            with self.subTest(error=error):
                mkdocs_hooks._categories_cache = None
                with (
                    patch.object(mkdocs_hooks, "_load_yaml", return_value=categories),
                    self.assertRaisesRegex(ValueError, error),
                ):
                    mkdocs_hooks._load_categories()

    def test_category_loader_rejects_malformed_root_entries_and_flags(self) -> None:
        invalid_cases = (
            ([], "must contain a mapping at the root"),
            ({"categories": {}}, "must contain a 'categories' list"),
            ({"categories": ["not a mapping"]}, "must be a mapping"),
            (
                {
                    "categories": [
                        {
                            "title": "Home",
                            "path": "Home",
                            "enabled": "yes",
                            "dashboard_request": {
                                "github_project": "AS-IO/11",
                                "assignees": ["owner"],
                            },
                            "content_request": {
                                "github_project": "AS-IO/11",
                                "assignees": ["owner"],
                            },
                        }
                    ]
                },
                "non-boolean 'enabled'",
            ),
            (
                {
                    "categories": [
                        {
                            "title": "Group",
                            "children": [],
                            "dashboard_request": {
                                "github_project": "AS-IO/11",
                                "assignees": ["owner"],
                            },
                            "content_request": {
                                "github_project": "AS-IO/11",
                                "assignees": ["owner"],
                            },
                        }
                    ]
                },
                "non-empty 'children' list",
            ),
        )

        for categories, error in invalid_cases:
            with self.subTest(error=error):
                mkdocs_hooks._categories_cache = None
                with (
                    patch.object(mkdocs_hooks, "_load_yaml", return_value=categories),
                    self.assertRaisesRegex((TypeError, ValueError), error),
                ):
                    mkdocs_hooks._load_categories()

    def test_on_files_generates_home_templates_and_feature_pages(self) -> None:
        routing = ("ORG/1", ["owner"])
        categories = [
            {
                "title": "Home",
                "kind": "directory",
                "path": "Landing",
                "dashboard_routing": routing,
                "content_routing": routing,
            },
            {
                "title": "Library",
                "kind": "generated-section",
                "path": "Library",
                "dashboard_routing": routing,
                "content_routing": routing,
            },
        ]

        def generate_example_page(files: Files, config: object, section_name: str) -> None:
            files.append(
                File.generated(
                    config,
                    f"{section_name}/Example/index.md",
                    content="# Example\n",
                )
            )

        processor = GeneratedSectionProcessor(
            build_item_nav_entries=lambda section_name: [],
            generate_item_pages=generate_example_page,
            replace_placeholders=lambda markdown, section_name: markdown,
            has_summary_placeholder=True,
        )
        with TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            home_index = repo_root / "docs" / "Landing" / "index.md"
            home_index.parent.mkdir(parents=True)
            home_index.write_text("# Dashboard\n", encoding="utf-8")
            template_root = repo_root / "docs" / "Library" / "000_TEMPLATES"
            template_root.mkdir(parents=True)
            (template_root / "overview.yaml").write_text(
                "fields: {}\n", encoding="utf-8"
            )
            (template_root / "guide.md").write_text("# Guide\n", encoding="utf-8")
            files = Files([])
            config = SimpleNamespace(
                site_dir=str(repo_root / "site"),
                use_directory_urls=True,
                plugins=SimpleNamespace(_current_plugin=None),
            )
            template_prefixes = mkdocs_hooks._template_render_prefixes
            try:
                with (
                    patch.object(mkdocs_hooks, "REPO_ROOT", repo_root),
                    patch.object(mkdocs_hooks, "_load_categories", return_value=categories),
                    patch.object(mkdocs_hooks, "_get_section_processor", return_value=processor),
                ):
                    result = mkdocs_hooks.on_files(files, config)
            finally:
                mkdocs_hooks._template_render_prefixes = template_prefixes

        self.assertIs(files, result)
        generated_files = {file.src_uri: file.content_string for file in files}
        self.assertIn("index.md", generated_files)
        self.assertIn("# Dashboard", generated_files["index.md"])
        self.assertIn("Library/index.md", generated_files)
        self.assertIn(
            "[[AUTO:LIBRARY_SUMMARY_TABLE]]", generated_files["Library/index.md"]
        )
        self.assertIn("Library/000_TEMPLATES/index.md", generated_files)
        self.assertIn("# Templates", generated_files["Library/000_TEMPLATES/index.md"])
        self.assertIn("Library/000_TEMPLATES/guide/index.md", generated_files)
        self.assertIn("Library/000_TEMPLATES/guide/render.md", generated_files)
        self.assertIn("Library/Example/index.md", generated_files)

    def test_generated_section_requires_an_overview_or_item(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            (repo_root / "docs" / "Library").mkdir(parents=True)
            processor = GeneratedSectionProcessor(
                build_item_nav_entries=lambda section_name: [],
                generate_item_pages=lambda files, config, section_name: None,
                replace_placeholders=lambda markdown, section_name: markdown,
            )
            category = {"title": "Library", "path": "Library"}
            with (
                patch.object(mkdocs_hooks, "REPO_ROOT", repo_root),
                patch.object(mkdocs_hooks, "_get_section_processor", return_value=processor),
                self.assertRaisesRegex(ValueError, "no displayable content"),
            ):
                mkdocs_hooks._build_generated_section_nav_entries(category)


class SearchPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.policy_file = Path(self.temporary_directory.name) / "search-policy.yaml"
        self.policy_file.write_text(
            "version: 1\nexcluded_path_prefixes:\n  - TestCases/\n",
            encoding="utf-8",
        )
        self.policy_file_patch = patch.object(
            mkdocs_hooks, "SEARCH_POLICY_FILE", self.policy_file
        )
        self.policy_file_patch.start()
        mkdocs_hooks._search_excluded_path_prefixes_cache = None

    def tearDown(self) -> None:
        self.policy_file_patch.stop()
        self.temporary_directory.cleanup()
        mkdocs_hooks._search_excluded_path_prefixes_cache = None

    def test_excludes_configured_prefix_and_preserves_search_metadata(self) -> None:
        source_uri = "TestCases/SystemTests/example.md"
        page = SimpleNamespace(
            file=SimpleNamespace(src_uri=source_uri),
            meta={"search": {"boost": 10}},
            canonical_url="",
        )

        mkdocs_hooks._exclude_page_from_search_when_configured(page, source_uri)

        self.assertEqual({"boost": 10, "exclude": True}, page.meta["search"])

    def test_leaves_normal_and_similarly_named_paths_searchable(self) -> None:
        for source_uri in ("Features/example.md", "TestCases-Archive/example.md"):
            page = SimpleNamespace(
                file=SimpleNamespace(src_uri=source_uri), meta={}, canonical_url=""
            )

            mkdocs_hooks._exclude_page_from_search_when_configured(page, source_uri)

            self.assertNotIn("search", page.meta)

    def test_supports_multiple_configured_prefixes(self) -> None:
        self.policy_file.write_text(
            "version: 1\n"
            "excluded_path_prefixes:\n"
            "  - TestCases/\n"
            "  - Features/Example/TestCases/\n",
            encoding="utf-8",
        )
        mkdocs_hooks._search_excluded_path_prefixes_cache = None
        page = SimpleNamespace(
            file=SimpleNamespace(
                src_uri="Features/Example/TestCases/integration/case.md"
            ),
            meta={},
            canonical_url="",
        )

        mkdocs_hooks._exclude_page_from_search_when_configured(
            page, "Features/Example/TestCases/integration/case.md"
        )

        self.assertEqual({"exclude": True}, page.meta["search"])

    def test_rejects_invalid_or_duplicate_policy_prefixes(self) -> None:
        for policy in (
            "version: 1\nexcluded_path_prefixes: invalid\n",
            "version: 1\nexcluded_path_prefixes:\n  - ../outside/\n",
            "version: 1\nexcluded_path_prefixes:\n  - TestCases/\n  - TestCases\n",
        ):
            self.policy_file.write_text(policy, encoding="utf-8")
            mkdocs_hooks._search_excluded_path_prefixes_cache = None

            with self.assertRaises((TypeError, ValueError)):
                mkdocs_hooks._load_search_excluded_path_prefixes()

    def test_rejects_missing_policy_file(self) -> None:
        self.policy_file.unlink()

        with self.assertRaisesRegex(ValueError, "search policy.*missing"):
            mkdocs_hooks._load_search_excluded_path_prefixes()


class RenderWarningFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.template_prefixes = mkdocs_hooks._template_render_prefixes
        mkdocs_hooks._template_render_prefixes = {"Features/000_TEMPLATES/"}

    def tearDown(self) -> None:
        mkdocs_hooks._template_render_prefixes = self.template_prefixes

    def test_template_render_link_warning_is_always_suppressed(self) -> None:
        record = logging.LogRecord(
            "mkdocs.structure.pages",
            logging.WARNING,
            "",
            0,
            "Features/000_TEMPLATES/03_TestConcept/template/render.md contains a link",
            (),
            None,
        )

        self.assertFalse(mkdocs_hooks._TemplateRenderWarningFilter().filter(record))

    def test_customer_render_link_warning_is_not_suppressed(self) -> None:
        record = logging.LogRecord(
            "mkdocs.structure.pages",
            logging.WARNING,
            "",
            0,
            "Features/Item/source/render/index.md contains a link",
            (),
            None,
        )

        self.assertTrue(mkdocs_hooks._TemplateRenderWarningFilter().filter(record))


class MissingMountLinkWarningFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.filter = mkdocs_hooks._MissingMountLinkWarningFilter(
            {PurePosixPath("Unavailable")}
        )

    def _record(self, message: str) -> logging.LogRecord:
        return logging.LogRecord(
            "mkdocs.structure.pages",
            logging.WARNING,
            "",
            0,
            message,
            (),
            None,
        )

    def test_suppresses_missing_file_below_absent_mount(self) -> None:
        record = self._record(
            "Doc file 'Home/index.md' contains a link '../Unavailable/index.md', "
            "but the target 'Unavailable/index.md' is not found among documentation files."
        )

        self.assertFalse(self.filter.filter(record))

    def test_suppresses_directory_style_target_below_absent_mount(self) -> None:
        record = self._record(
            "Doc file 'index.md' contains an unrecognized relative link "
            "'Unavailable/?view=all#summary', it was left as is."
        )

        self.assertFalse(self.filter.filter(record))

    def test_keeps_warnings_outside_absent_mount(self) -> None:
        record = self._record(
            "Doc file 'Home/index.md' contains a link '../Available/missing.md', "
            "but the target 'Available/missing.md' is not found among documentation files."
        )

        self.assertTrue(self.filter.filter(record))

    def test_keeps_similarly_named_target_outside_absent_mount(self) -> None:
        record = self._record(
            "Doc file 'Home/index.md' contains a link '../UnavailableExtra/index.md', "
            "but the target 'UnavailableExtra/index.md' is not found among documentation files."
        )

        self.assertTrue(self.filter.filter(record))

    def test_keeps_anchor_and_excluded_target_warnings(self) -> None:
        anchor_record = self._record(
            "Doc file 'Home/index.md' contains a link '../Unavailable/index.md#missing', "
            "but the doc 'Unavailable/index.md' does not contain an anchor '#missing'."
        )
        excluded_record = self._record(
            "Doc file 'Home/index.md' contains a link to 'Unavailable/index.md' "
            "which is excluded from the built site."
        )

        self.assertTrue(self.filter.filter(anchor_record))
        self.assertTrue(self.filter.filter(excluded_record))


class LegacyTestCasesImageWarningFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.filter = mkdocs_hooks._LegacyTestCasesImageWarningFilter()

    def _record(self, message: str) -> logging.LogRecord:
        return logging.LogRecord(
            "mkdocs.structure.pages",
            logging.WARNING,
            "",
            0,
            message,
            (),
            None,
        )

    def test_suppresses_legacy_testcases_image_warning(self) -> None:
        record = self._record(
            "Doc file 'TestCases/SystemTests/example.md' contains a link "
            "'[TMSIMG]/TMS_2_16_example.PNG', but the target "
            "'TestCases/SystemTests/[TMSIMG]/TMS_2_16_example.PNG' is not found "
            "among documentation files."
        )

        self.assertFalse(self.filter.filter(record))

    def test_keeps_normal_testcases_missing_link_warning(self) -> None:
        record = self._record(
            "Doc file 'TestCases/SystemTests/example.md' contains a link "
            "'missing.md', but the target 'TestCases/SystemTests/missing.md' "
            "is not found among documentation files."
        )

        self.assertTrue(self.filter.filter(record))

    def test_keeps_legacy_image_warning_outside_testcases(self) -> None:
        record = self._record(
            "Doc file 'Features/example.md' contains a link "
            "'[TMSIMG]\\TMS_2_16_example.PNG', but the target "
            "'Features/[TMSIMG]\\TMS_2_16_example.PNG' is not found among "
            "documentation files."
        )

        self.assertTrue(self.filter.filter(record))


if __name__ == "__main__":
    unittest.main()
