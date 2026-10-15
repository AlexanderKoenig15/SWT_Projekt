from __future__ import annotations

import json
import os
import shutil
import sys
import subprocess
import unittest
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import yaml
from mkdocs.structure.files import Files

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import features_section  # noqa: E402
import generate_features_dashboard  # noqa: E402
from generate_features_dashboard import (  # noqa: E402
    ProgressSummary,
    ProcessReadinessWeights,
    build_effective_groups,
    build_document_tree_card,
    build_feature_summary_table,
    build_resolved_feature,
    build_resolved_feature_group_readiness_content,
    build_resolved_main_fields_content,
    build_resolved_group_process_details_content,
    build_resolved_group_process_sources_content,
    build_resolved_process_progress_summaries,
    build_resolved_process_readiness,
    build_readiness_details_content,
    _collect_resolved_group_fields,
    collect_feature_field_definitions,
    collect_feature_related_pages,
    collect_process_field_definitions,
    collect_process_root_documents,
    get_resolved_sources,
    get_feature_status,
    get_feature_status_for_workspace,
    get_resolved_content_routing,
    _get_process_source_display_status,
    is_local_source_path,
    parse_date_value,
    parse_progress_value,
    parse_template_field_spec,
    parse_source_reference,
    read_document_frontmatter,
    red_missing_cell,
    render_resolved_value,
    render_progress_meter,
    sanitize_markdown_description,
    load_process_readiness_weights,
    load_feature_detail_template,
    _resolve_local_source_dir,
    summarize_process_readiness,
    _insert_related_tree_entry,
    _new_related_tree_node,
)
from responsibility import (  # noqa: E402
    build_create_issue_url,
    build_github_project_url,
    normalize_assignees,
    normalize_github_project,
)


def _write_feature_fixture(repo_root: Path) -> None:
    section_root = repo_root / "docs" / "Features"
    template_root = section_root / "000_TEMPLATES"
    feature_root = section_root / "Example Feature"
    template_root.mkdir(parents=True)
    (feature_root / "Documents").mkdir(parents=True)
    (feature_root / "Supporting Material").mkdir()

    (template_root / "overview.yaml").write_text(
        yaml.safe_dump(
            {
                "feature_name": "required",
                "processes": {
                    "delivery": {
                        "display_name": {
                            "state": "template",
                            "value": "Delivery",
                        },
                        "sources": {
                            "state": "template",
                            "value": ["Documents"],
                        },
                        "owner": "required",
                        "progress": 0,
                    }
                },
                "groups": [{"name": "Delivery", "items": ["delivery"]}],
                "process_readiness_weights": {
                    "source": 10,
                    "metadata": 10,
                    "progress": 80,
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    (template_root / "feature_detail.md").write_text(
        "# [[AUTO:FEATURE_NAME]]\n\n"
        "## Overview\n\n"
        "[[AUTO:FEATURE_MAIN_FIELDS]]\n\n"
        "[[AUTO:FEATURE_AGGREGATED_OVERVIEW_TABLE]]\n\n"
        "[[AUTO:FEATURE_READINESS_DETAILS]]\n"
        "[[AUTO:READINESS_FORMULA_NOTE]]\n\n"
        "## Process Groups\n\n"
        "[[AUTO:FEATURE_GROUP_READINESS]]\n\n"
        "[[AUTO:FEATURE_RELATED_DOCS]]\n",
        encoding="utf-8",
    )
    (template_root / "group_detail.md").write_text(
        "# [[AUTO:GROUP_NAME]]\n\n"
        "## Overview\n\n"
        "[[AUTO:GROUP_READINESS_DETAILS]]\n"
        "[[AUTO:READINESS_FORMULA_NOTE]]\n\n"
        "## Processes\n\n"
        "[[AUTO:GROUP_PROCESS_DETAILS]]\n\n"
        "[[AUTO:GROUP_PROCESS_SOURCES]]\n",
        encoding="utf-8",
    )
    (feature_root / "overview.yaml").write_text(
        yaml.safe_dump(
            {
                "feature_name": "Example Feature",
                "content_request": {
                    "github_project": "AS-IO/9",
                    "assignees": ["feature-owner"],
                },
                "processes": {
                    "delivery": {"owner": "Ada", "progress": 50},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (feature_root / "Documents" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (feature_root / "Supporting Material" / "notes.md").write_text(
        "# Notes\n", encoding="utf-8"
    )
    empty_feature_root = section_root / "Empty Feature"
    empty_feature_root.mkdir()
    (empty_feature_root / "overview.yaml").write_text(
        yaml.safe_dump(
            {
                "feature_name": "Empty Feature",
                "content_request": {
                    "github_project": "AS-IO/9",
                    "assignees": ["feature-owner"],
                },
                "processes": {
                    "delivery": {"owner": "Ada", "progress": 0},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    pending_feature_root = section_root / "Pending Feature"
    pending_feature_root.mkdir()
    (pending_feature_root / "README.md").write_text(
        "# Bootstrap only\n", encoding="utf-8"
    )


def _build_process_table_feature(feature_dir: Path, sources: list[str] | None = None):
    template_data = {
        "processes": {
            "delivery": {
                "display_name": {"state": "template", "value": "Delivery"},
                "sources": {
                    "state": "template",
                    "value": sources or ["Documents"],
                },
                "owner": "required",
                "version": "required",
                "date": "required",
                "progress": 0,
            }
        }
    }
    return build_resolved_feature(
        feature_dir.name,
        {
            "processes": {
                "delivery": {
                    "owner": "YAML Owner",
                    "version": "1.0",
                    "date": "2025-01-01",
                    "progress": 50,
                }
            }
        },
        {},
        collect_process_field_definitions(template_data),
        [{"name": "Delivery", "items": ["delivery"]}],
    )


class GeneratorCliTests(unittest.TestCase):
    def test_main_uses_docs_root_configured_after_module_import(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            _write_feature_fixture(repo_root)

            with (
                patch.dict(
                    generate_features_dashboard.os.environ,
                    {"MODUL_DASHBOARD_DOCS_DIR": str(repo_root / "docs")},
                ),
                patch("builtins.print"),
            ):
                self.assertEqual(0, generate_features_dashboard.main())


class FeatureStatusTests(unittest.TestCase):
    def _write_status_fixture(self, root: Path) -> Path:
        docs_root = root / "docs"
        template_root = docs_root / "Features" / "000_TEMPLATES"
        feature_dir = docs_root / "Features" / "Example Feature"
        documents_dir = feature_dir / "Documents"
        template_root.mkdir(parents=True)
        documents_dir.mkdir(parents=True)
        (documents_dir / "guide.md").write_text(
            "---\n"
            "owner: Ada Lovelace\n"
            "document_version: 1.0\n"
            "modified_at: 2026-08-31\n"
            "state: released\n"
            "---\n# Guide\n",
            encoding="utf-8",
        )
        (template_root / "overview.yaml").write_text(
            yaml.safe_dump(
                {
                    "feature_name": "required",
                    "owner": "required",
                    "processes": {
                        "delivery": {
                            "display_name": {
                                "state": "template",
                                "value": "Delivery",
                            },
                            "sources": "required",
                            "owner": "required",
                            "version": "required",
                            "date": "required",
                            "progress": 0,
                        },
                        "design": {
                            "display_name": {
                                "state": "template",
                                "value": "Design",
                            },
                            "sources": "required",
                            "owner": "required",
                            "version": "required",
                            "date": "required",
                            "progress": 0,
                        },
                    },
                    "groups": [
                        {"name": "Elaboration", "items": ["design"]},
                        {"name": "Delivery", "items": ["delivery"]},
                    ],
                    "process_readiness_weights": {
                        "source": 10,
                        "metadata": 10,
                        "progress": 80,
                    },
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (feature_dir / "overview.yaml").write_text(
            yaml.safe_dump(
                {
                    "feature_name": "Example Feature",
                    "owner": "Feature Owner",
                    "processes": {
                        "delivery": {
                            "sources": "Documents",
                            "progress": 120,
                        },
                        "design": {
                            "sources": "Missing",
                            "progress": -5,
                        },
                    },
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return feature_dir

    def test_status_reuses_readiness_and_reports_metadata_origins(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            feature_dir = self._write_status_fixture(root)
            with patch.dict(
                os.environ, {"MODUL_DASHBOARD_DOCS_DIR": str(root / "docs")}
            ):
                status = get_feature_status(feature_dir)

        self.assertEqual("Example Feature", status.feature_name)
        self.assertEqual(("feature_yaml",), status.owner.origins)
        self.assertEqual(50.0, status.readiness.value)
        self.assertEqual(50.0, status.reported_progress)
        self.assertEqual(1, status.linked_source_count)
        self.assertEqual(2, status.total_source_count)
        self.assertEqual(1, status.linked_process_count)
        self.assertEqual(2, status.total_process_count)
        self.assertEqual(
            ["Elaboration", "Delivery"], [group.name for group in status.groups]
        )

        process_by_id = {process.process_id: process for process in status.processes}
        delivery = process_by_id["delivery"]
        self.assertEqual(100.0, delivery.readiness.progress)
        self.assertEqual(120.0, delivery.reported_progress)
        self.assertEqual(3, delivery.readiness.metadata_filled)
        self.assertEqual(3, delivery.readiness.metadata_total)
        self.assertEqual(
            {"document_frontmatter"},
            {origin for field in delivery.fields for origin in field.origins},
        )
        self.assertEqual("linked-local-folder", delivery.sources[0].status)

        design = process_by_id["design"]
        self.assertEqual(0.0, design.readiness.progress)
        self.assertEqual(-5.0, design.reported_progress)
        self.assertEqual("missing-local-folder", design.sources[0].status)
        self.assertEqual(
            {
                "process.design.owner",
                "process.design.version",
                "process.design.date",
            },
            set(status.missing_required_fields),
        )

    def test_status_reports_missing_overview_for_existing_feature_directory(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            feature_dir = self._write_status_fixture(root)
            (feature_dir / "overview.yaml").unlink()
            with patch.dict(
                os.environ, {"MODUL_DASHBOARD_DOCS_DIR": str(root / "docs")}
            ):
                with self.assertRaisesRegex(
                    FileNotFoundError, "Feature metadata does not exist"
                ):
                    get_feature_status(feature_dir)

    def test_status_rejects_overview_directory_as_invalid_metadata(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            feature_dir = self._write_status_fixture(root)
            (feature_dir / "overview.yaml").unlink()
            (feature_dir / "overview.yaml").mkdir()
            with self.assertRaisesRegex(ValueError, "not a regular file"):
                get_feature_status(feature_dir)

    def test_workspace_status_rejects_overview_directory_as_invalid_metadata(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fixture_root = root / "fixture"
            feature_fixture = self._write_status_fixture(fixture_root)
            documents_root = root / "Modul-Documents"
            documents_root.mkdir()
            (fixture_root / "docs" / "Features").rename(documents_root / "Features")
            (
                documents_root / "Features" / feature_fixture.name / "overview.yaml"
            ).unlink()
            (
                documents_root / "Features" / feature_fixture.name / "overview.yaml"
            ).mkdir()
            registry_file = root / "repositories.yaml"
            registry_file.write_text(
                "version: 2\n"
                "repositories:\n"
                "  - id: documents\n"
                "    repository: ORG/Modul-Documents\n"
                "    workspace: required\n"
                "    mount_path: .\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "not a regular file"):
                get_feature_status_for_workspace(
                    "Example Feature", [documents_root], registry_file
                )

    def test_workspace_status_resolves_current_effective_feature_source(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fixture_root = root / "fixture"
            feature_fixture = self._write_status_fixture(fixture_root)
            documents_root = root / "Modul-Documents"
            documents_root.mkdir()
            (fixture_root / "docs" / "Features").rename(documents_root / "Features")

            child_root = root / "Modul-Feature-Example-Feature"
            shutil.copytree(
                documents_root / "Features" / feature_fixture.name,
                child_root,
            )
            registry_file = root / "repositories.yaml"
            registry_file.write_text(
                "version: 2\n"
                "repositories:\n"
                "  - id: documents\n"
                "    repository: ORG/Modul-Documents\n"
                "    workspace: required\n"
                "    mount_path: .\n"
                "  - id: example\n"
                "    repository: ORG/Modul-Feature-Example-Feature\n"
                "    workspace: optional\n"
                "    mount_path: Features/Example Feature\n",
                encoding="utf-8",
            )

            workspace_folders = [documents_root, child_root]
            fallback_result = get_feature_status_for_workspace(
                "Example Feature", workspace_folders, registry_file
            )
            shutil.rmtree(documents_root / "Features" / feature_fixture.name)
            child_result = get_feature_status_for_workspace(
                "Example Feature", workspace_folders, registry_file
            )
            (child_root / "overview.yaml").unlink()
            pending_result = get_feature_status_for_workspace(
                "Example Feature", workspace_folders, registry_file
            )

        self.assertEqual("documents", fallback_result.effective_source_id)
        self.assertEqual("example", child_result.effective_source_id)
        self.assertEqual("fallback-effective", fallback_result.publication_status)
        self.assertEqual("effective", child_result.publication_status)
        self.assertIsNone(pending_result.status)
        self.assertEqual("pending metadata", pending_result.publication_status)

    def test_status_preserves_explicit_null_as_missing_readiness_value(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            feature_dir = self._write_status_fixture(root)
            overview_file = feature_dir / "overview.yaml"
            overview = yaml.safe_load(overview_file.read_text(encoding="utf-8"))
            overview["owner"] = None
            overview_file.write_text(
                yaml.safe_dump(overview, sort_keys=False), encoding="utf-8"
            )
            with patch.dict(
                os.environ, {"MODUL_DASHBOARD_DOCS_DIR": str(root / "docs")}
            ):
                status = get_feature_status(feature_dir)

        self.assertTrue(status.owner.missing)
        self.assertIn("feature.owner", status.missing_required_fields)

    def test_status_marks_template_defaults_without_counting_them_as_metadata(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            feature_dir = self._write_status_fixture(root)
            template_file = (
                root / "docs" / "Features" / "000_TEMPLATES" / "overview.yaml"
            )
            template_data = yaml.safe_load(template_file.read_text(encoding="utf-8"))
            template_data["processes"]["delivery"]["owner"] = {
                "state": "required",
                "value": "Template owner",
            }
            template_file.write_text(
                yaml.safe_dump(template_data, sort_keys=False), encoding="utf-8"
            )
            with patch.dict(
                os.environ, {"MODUL_DASHBOARD_DOCS_DIR": str(root / "docs")}
            ):
                status = get_feature_status(feature_dir)

        delivery = next(
            process for process in status.processes if process.process_id == "delivery"
        )
        owner = next(field for field in delivery.fields if field.field_name == "owner")
        self.assertTrue(owner.template_defaulted)
        self.assertEqual(("template_default", "document_frontmatter"), owner.origins)
        self.assertFalse(owner.missing)
        self.assertEqual(2, delivery.readiness.metadata_total)

    def test_status_distinguishes_an_unavailable_mounted_source(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            feature_dir = self._write_status_fixture(root)
            overview_file = feature_dir / "overview.yaml"
            overview = yaml.safe_load(overview_file.read_text(encoding="utf-8"))
            overview["processes"]["design"]["sources"] = "TestCases/Missing"
            overview_file.write_text(
                yaml.safe_dump(overview, sort_keys=False), encoding="utf-8"
            )
            with (
                patch.dict(
                    os.environ, {"MODUL_DASHBOARD_DOCS_DIR": str(root / "docs")}
                ),
                patch.object(
                    generate_features_dashboard,
                    "_is_registered_mount_source",
                    return_value=True,
                ),
            ):
                status = get_feature_status(feature_dir)

        design = next(
            process for process in status.processes if process.process_id == "design"
        )
        self.assertEqual("unavailable-mounted-source", design.sources[0].status)

    def test_status_distinguishes_a_missing_path_inside_an_available_mount(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            feature_dir = self._write_status_fixture(root)
            mounted_root = root / "docs" / "TestCases"
            mounted_root.mkdir()
            overview_file = feature_dir / "overview.yaml"
            overview = yaml.safe_load(overview_file.read_text(encoding="utf-8"))
            overview["processes"]["design"]["sources"] = "TestCases/Missing"
            overview_file.write_text(
                yaml.safe_dump(overview, sort_keys=False), encoding="utf-8"
            )
            with (
                patch.dict(
                    os.environ, {"MODUL_DASHBOARD_DOCS_DIR": str(root / "docs")}
                ),
                patch.object(
                    generate_features_dashboard,
                    "_is_registered_mount_source",
                    return_value=True,
                ),
                patch.object(
                    generate_features_dashboard,
                    "_registered_mount_root",
                    return_value=mounted_root,
                ),
            ):
                status = get_feature_status(feature_dir)

        design = next(
            process for process in status.processes if process.process_id == "design"
        )
        self.assertEqual("missing-mounted-path", design.sources[0].status)

    def test_status_marks_not_applicable_sources_without_counting_them(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            feature_dir = self._write_status_fixture(root)
            overview_file = feature_dir / "overview.yaml"
            overview = yaml.safe_load(overview_file.read_text(encoding="utf-8"))
            overview["processes"]["design"]["sources"] = "not_applicable"
            overview_file.write_text(
                yaml.safe_dump(overview, sort_keys=False), encoding="utf-8"
            )
            with patch.dict(
                os.environ, {"MODUL_DASHBOARD_DOCS_DIR": str(root / "docs")}
            ):
                status = get_feature_status(feature_dir)

        design = next(
            process for process in status.processes if process.process_id == "design"
        )
        self.assertEqual("not-applicable-source", design.sources[0].status)
        self.assertEqual(1, status.linked_source_count)
        self.assertEqual(1, status.total_source_count)
        self.assertEqual(1, status.readiness.applicable_source_processes)

    def test_status_marks_missing_repository_only_when_mount_is_absent(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            feature_dir = root / "Example Feature"
            feature_dir.mkdir()
            source_root = root / "TestCases"
            status_file = root / "assembly-status.json"
            status_file.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "missing_mount_paths": ["TestCases"],
                    }
                ),
                encoding="utf-8",
            )
            feature = _build_process_table_feature(
                feature_dir, ["TestCases/IntegrationTests"]
            )
            with (
                patch.dict(
                    os.environ,
                    {"MODUL_DASHBOARD_ASSEMBLY_STATUS_FILE": str(status_file)},
                ),
                patch.object(
                    generate_features_dashboard,
                    "_is_registered_mount_source",
                    return_value=True,
                ),
                patch.object(
                    generate_features_dashboard,
                    "_registered_mount_root",
                    return_value=source_root,
                ),
            ):
                rendered = build_resolved_group_process_details_content(
                    feature.get_groups()[0],
                    feature_dir,
                    {"delivery": ProgressSummary(1, 1, 0)},
                )

        self.assertIn("REPO MISSING", rendered)
        self.assertIn("color:#8a5a00", rendered)

    def test_missing_subpath_inside_available_mount_stays_missing(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            feature_dir = root / "Example Feature"
            feature_dir.mkdir()
            source_root = root / "TestCases"
            source_root.mkdir()
            status_file = root / "assembly-status.json"
            status_file.write_text(
                json.dumps({"version": 1, "missing_mount_paths": []}),
                encoding="utf-8",
            )
            feature = _build_process_table_feature(
                feature_dir, ["TestCases/IntegrationTests"]
            )
            with (
                patch.dict(
                    os.environ,
                    {"MODUL_DASHBOARD_ASSEMBLY_STATUS_FILE": str(status_file)},
                ),
                patch.object(
                    generate_features_dashboard,
                    "_is_registered_mount_source",
                    return_value=True,
                ),
                patch.object(
                    generate_features_dashboard,
                    "_registered_mount_root",
                    return_value=source_root,
                ),
            ):
                rendered = build_resolved_group_process_details_content(
                    feature.get_groups()[0],
                    feature_dir,
                    {"delivery": ProgressSummary(1, 1, 0)},
                )

        self.assertIn(
            '<span style="color:#ff1b45;"><strong>MISSING</strong></span>',
            rendered,
        )
        self.assertNotIn("REPO MISSING", rendered)

    def test_status_rejects_missing_feature_metadata(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with self.assertRaisesRegex(FileNotFoundError, "Feature directory"):
                with patch.dict(
                    os.environ, {"MODUL_DASHBOARD_DOCS_DIR": str(root / "docs")}
                ):
                    get_feature_status(root / "docs" / "Features" / "Missing")


class GroupProgressContentTests(unittest.TestCase):
    def test_process_source_display_statuses_distinguish_source_kinds(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            feature_dir = Path(temporary_directory) / "Example Feature"
            documents_dir = feature_dir / "Documents"
            documents_dir.mkdir(parents=True)
            (documents_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")

            markdown_feature = _build_process_table_feature(feature_dir)
            link_feature = _build_process_table_feature(
                feature_dir, ["https://example.test/source"]
            )
            missing_feature = _build_process_table_feature(feature_dir, ["Missing"])
            optional_definitions = collect_process_field_definitions(
                {
                    "processes": {
                        "delivery": {
                            "display_name": {
                                "state": "template",
                                "value": "Delivery",
                            },
                            "sources": "optional",
                        }
                    }
                }
            )
            optional_feature = build_resolved_feature(
                "Example Feature",
                {},
                {},
                optional_definitions,
                [{"name": "Delivery", "items": ["delivery"]}],
            )
            not_applicable_feature = build_resolved_feature(
                "Example Feature",
                {"processes": {"delivery": {"sources": "not_applicable"}}},
                {},
                collect_process_field_definitions(
                    {
                        "processes": {
                            "delivery": {
                                "display_name": {
                                    "state": "template",
                                    "value": "Delivery",
                                },
                                "sources": "required",
                            }
                        }
                    }
                ),
                [{"name": "Delivery", "items": ["delivery"]}],
            )

            self.assertEqual(
                "MD-File",
                _get_process_source_display_status(
                    markdown_feature.get_process("delivery"), feature_dir
                ),
            )
            self.assertEqual(
                "Link",
                _get_process_source_display_status(
                    link_feature.get_process("delivery"), feature_dir
                ),
            )
            self.assertEqual(
                "-",
                _get_process_source_display_status(
                    optional_feature.get_process("delivery"), feature_dir
                ),
            )
            self.assertEqual(
                "MISSING",
                _get_process_source_display_status(
                    missing_feature.get_process("delivery"), feature_dir
                ),
            )
            self.assertEqual(
                "Not applicable",
                _get_process_source_display_status(
                    not_applicable_feature.get_process("delivery"), feature_dir
                ),
            )

    def test_not_applicable_source_overrides_append_default(self) -> None:
        template_data = {
            "processes": {
                "delivery": {
                    "display_name": {
                        "state": "template",
                        "value": "Delivery",
                    },
                    "sources": {
                        "state": "append",
                        "value": ["Documents"],
                    },
                }
            }
        }
        feature = build_resolved_feature(
            "Example Feature",
            {"processes": {"delivery": {"sources": "not_applicable"}}},
            {},
            collect_process_field_definitions(template_data),
            [{"name": "Delivery", "items": ["delivery"]}],
        )
        process = feature.get_process("delivery")

        self.assertEqual((["not_applicable"], False), process.get_value_many("sources"))
        self.assertEqual([], get_resolved_sources(process))
        self.assertIn(
            "Not applicable",
            build_resolved_group_process_sources_content(
                feature.get_groups()[0], Path("."), {}
            ),
        )

    def test_empty_source_values_keep_append_default(self) -> None:
        template_data = {
            "processes": {
                "delivery": {
                    "display_name": {
                        "state": "template",
                        "value": "Delivery",
                    },
                    "sources": {
                        "state": "append",
                        "value": ["Documents"],
                    },
                }
            }
        }
        definitions = collect_process_field_definitions(template_data)

        for source_value in (None, "", []):
            with self.subTest(source_value=source_value):
                feature = build_resolved_feature(
                    "Example Feature",
                    {"processes": {"delivery": {"sources": source_value}}},
                    {},
                    definitions,
                    [{"name": "Delivery", "items": ["delivery"]}],
                )

                self.assertEqual(
                    (["Documents"], False),
                    feature.get_process("delivery").get_value_many("sources"),
                )

    def test_source_coverage_excludes_not_applicable_processes(self) -> None:
        process_readiness = {
            process_id: generate_features_dashboard.ProcessReadiness(
                source_linked=process_id in {"linked-a", "linked-b", "linked-c"},
                metadata_filled=0,
                metadata_total=0,
                progress=0,
                value=(
                    10
                    if process_id
                    in {"linked-a", "linked-b", "linked-c", "not-applicable"}
                    else 0
                ),
                source_applicable=process_id != "not-applicable",
                source_weight=10,
            )
            for process_id in [
                "linked-a",
                "linked-b",
                "linked-c",
                "not-applicable",
                "missing",
            ]
        }
        summary = summarize_process_readiness(
            list(process_readiness), process_readiness
        )

        self.assertEqual(5, summary.process_count)
        self.assertEqual(3, summary.linked_processes)
        self.assertEqual(4, summary.applicable_source_processes)
        self.assertEqual(7.5, summary.value)
        self.assertIn("3 / 4", build_readiness_details_content(summary, "Feature"))

    def test_collect_related_pages_follows_mounted_directory_links(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            feature_dir = root / "Example Feature"
            feature_dir.mkdir()
            mounted_source = root / "Mounted Source"
            mounted_source.mkdir()
            (mounted_source / "guide.md").write_text("# Guide\n", encoding="utf-8")
            mounted_documents = feature_dir / "Documents"
            try:
                if sys.platform == "win32":
                    result = subprocess.run(
                        [
                            "cmd.exe",
                            "/d",
                            "/c",
                            "mklink",
                            "/J",
                            str(mounted_documents),
                            str(mounted_source),
                        ],
                        capture_output=True,
                        check=False,
                        encoding="utf-8",
                        errors="replace",
                        text=True,
                    )
                    if result.returncode != 0:
                        self.skipTest("directory links are unavailable")
                else:
                    mounted_documents.symlink_to(
                        mounted_source, target_is_directory=True
                    )
            except OSError:
                self.skipTest("directory links are unavailable")

            pages = collect_feature_related_pages(feature_dir)["Documents"]
            self.assertEqual(
                mounted_documents,
                _resolve_local_source_dir(feature_dir, "Documents"),
            )
            if mounted_documents.is_symlink():
                mounted_documents.unlink()
            else:
                mounted_documents.rmdir()

        self.assertEqual("Guide", pages[0][0])
        self.assertEqual("Documents/guide.md", pages[0][1])

    def test_document_tree_reads_frontmatter_from_markdown_extension(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            feature_dir = Path(temporary_directory) / "Example Feature"
            source_dir = feature_dir / "Documents"
            source_dir.mkdir(parents=True)
            (source_dir / "guide.markdown").write_text(
                "---\nauthor: Ada Lovelace\nstate: Released\n"
                "document_version: 1.10\n"
                "owner:\n  - Grace Hopper\n"
                "modified_at: 2026-08-27T12:00:00+00:00\n"
                "---\n# Guide\n",
                encoding="utf-8",
            )

            pages = collect_feature_related_pages(feature_dir)["Documents"]

        self.assertEqual(
            ("Ada Lovelace", "Released", "1.10"),
            (
                pages[0][2].author,
                pages[0][2].state,
                pages[0][2].version,
            ),
        )
        self.assertEqual("Grace Hopper", pages[0][2].owner)
        self.assertEqual("2026-08-27", pages[0][2].date)

    def test_process_table_uses_root_frontmatter_with_per_field_yaml_fallback(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary_directory:
            feature_dir = Path(temporary_directory) / "Example Feature"
            source_dir = feature_dir / "Documents"
            source_dir.mkdir(parents=True)
            (source_dir / "a-draft.md").write_text(
                "---\nowner: Draft Owner\nstate: draft\n---\n# Draft\n",
                encoding="utf-8",
            )
            (source_dir / "z-released.md").write_text(
                "---\n"
                "owner: null\n"
                "document_version: 2.0\n"
                "modified_at: 2026-08-20T12:00:00+00:00\n"
                "state: released\n"
                "---\n# Released\n",
                encoding="utf-8",
            )

            feature = _build_process_table_feature(feature_dir)
            rendered = build_resolved_group_process_details_content(
                feature.get_groups()[0],
                feature_dir,
                {"delivery": ProgressSummary(1, 1, 50)},
            )

        self.assertLess(
            rendered.index(">z-released.md</a>"),
            rendered.index(">a-draft.md</a>"),
        )
        self.assertEqual(1, rendered.count("<tbody>"))
        self.assertEqual(4, rendered.count("<tr>"))
        self.assertIn(
            '<a href="../Documents/z-released/render/">z-released.md</a>',
            rendered,
        )
        self.assertIn('<a href="../Documents/a-draft/render/">a-draft.md</a>', rendered)
        self.assertEqual(
            2,
            rendered.count(
                '<span class="document-tree-table__prefix" aria-hidden="true">'
            ),
        )
        self.assertIn(
            '<span class="document-tree-table__prefix" aria-hidden="true">'
            "&#9500;&#9472;&nbsp;</span>",
            rendered,
        )
        self.assertIn(
            '<span class="document-tree-table__prefix" aria-hidden="true">'
            "&#9492;&#9472;&nbsp;</span>",
            rendered,
        )
        self.assertIn(
            '<tr><td><a href="#delivery">Delivery</a></td><td>MD-File</td>\n'
            "<td></td>\n<td></td>\n<td></td>",
            rendered,
        )
        self.assertIn(
            '<tr><td style="border-top: 0">'
            '<span class="document-tree-table__file-cell">'
            '<span class="document-tree-table__prefix" aria-hidden="true">'
            "&#9500;&#9472;&nbsp;</span>"
            '<span class="document-tree-table__name">'
            '<a href="../Documents/z-released/render/">z-released.md</a>'
            '</span></span></td><td style="border-top: 0"></td>\n'
            '<td style="border-top: 0"><span style="color:#c65d00;" '
            'title="Fallback from process YAML">'
            "YAML Owner</span></td>",
            rendered,
        )
        self.assertIn(
            '<td style="border-top: 0">2.0 (released)</td>',
            rendered,
        )
        self.assertIn(
            '<td style="border-top: 0">2026-08-20</td>',
            rendered,
        )
        self.assertIn(
            '<td style="border-top: 0"><span style="color:#c65d00;" '
            'title="Fallback from process YAML">'
            "1.0</span> (draft)</td>",
            rendered,
        )
        self.assertIn(
            '<td style="border-top: 0"><span style="color:#c65d00;" '
            'title="Fallback from process YAML">'
            "2025-01-01</span></td>",
            rendered,
        )

    def test_process_table_ignores_nested_files_for_overview_metadata(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            feature_dir = Path(temporary_directory) / "Example Feature"
            source_dir = feature_dir / "Documents"
            (source_dir / "Archive").mkdir(parents=True)
            (source_dir / "Archive" / "old.md").write_text(
                "---\nowner: Archived Owner\n"
                "document_version: 0.1\n"
                "modified_at: 2020-01-01\nstate: released\n---\n",
                encoding="utf-8",
            )
            (source_dir / "current.md").write_text(
                "---\nowner: Current Owner\n"
                "document_version: 2.0\n"
                "modified_at: 2026-08-20\nstate: released\n---\n",
                encoding="utf-8",
            )

            feature = _build_process_table_feature(feature_dir)
            root_documents = collect_process_root_documents(
                feature.get_process("delivery"), feature_dir
            )
            rendered = build_resolved_group_process_details_content(
                feature.get_groups()[0],
                feature_dir,
                {"delivery": ProgressSummary(1, 1, 50)},
            )

        self.assertEqual(["current.md"], [path.name for path, _ in root_documents])
        self.assertIn(">current.md</a>", rendered)
        self.assertNotIn("Documents/Archive/old.md", rendered)
        self.assertNotIn("Archived Owner", rendered)

    def test_process_table_uses_corner_connector_for_single_root_document(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            feature_dir = Path(temporary_directory) / "Example Feature"
            source_dir = feature_dir / "Documents"
            source_dir.mkdir(parents=True)
            (source_dir / "guide.md").write_text(
                "---\nstate: released\n---\n# Guide\n",
                encoding="utf-8",
            )

            feature = _build_process_table_feature(feature_dir)
            rendered = build_resolved_group_process_details_content(
                feature.get_groups()[0],
                feature_dir,
                {"delivery": ProgressSummary(1, 1, 50)},
            )

        self.assertEqual(
            1,
            rendered.count(
                '<span class="document-tree-table__prefix" aria-hidden="true">'
            ),
        )
        self.assertIn("&#9492;&#9472;&nbsp;</span>", rendered)
        self.assertNotIn("&#9500;&#9472;&nbsp;</span>", rendered)

    def test_process_table_uses_normal_yaml_metadata_without_root_markdown_files(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary_directory:
            feature_dir = Path(temporary_directory) / "Example Feature"
            source_dir = feature_dir / "Documents"
            source_dir.mkdir(parents=True)
            (source_dir / "source.pptx").write_bytes(b"binary")

            feature = _build_process_table_feature(feature_dir)
            rendered = build_resolved_group_process_details_content(
                feature.get_groups()[0],
                feature_dir,
                {"delivery": ProgressSummary(1, 1, 50)},
            )

        self.assertNotIn("source.pptx", rendered)
        self.assertNotIn('title="Fallback from process YAML"', rendered)
        self.assertIn("<td>YAML Owner</td>", rendered)
        self.assertIn("<td>1.0</td>", rendered)
        self.assertIn("<td>2025-01-01</td>", rendered)

    def test_process_table_does_not_read_documents_outside_feature_directory(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary_directory:
            parent_dir = Path(temporary_directory)
            feature_dir = parent_dir / "Example Feature"
            outside_dir = parent_dir / "Outside"
            outside_dir.mkdir(parents=True)
            (outside_dir / "secret.md").write_text(
                "---\nowner: Outside Owner\n---\n# Secret\n",
                encoding="utf-8",
            )

            feature = _build_process_table_feature(feature_dir, ["../Outside"])
            rendered = build_resolved_group_process_details_content(
                feature.get_groups()[0],
                feature_dir,
                {"delivery": ProgressSummary(1, 1, 50)},
            )

        self.assertNotIn("secret.md", rendered)
        self.assertNotIn("Outside Owner", rendered)
        self.assertIn("MISSING", rendered)

    def test_document_tree_renders_version_and_state_in_separate_columns(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            feature_dir = Path(temporary_directory) / "Example Feature"
            source_dir = feature_dir / "Documents"
            source_dir.mkdir(parents=True)
            archive_dir = source_dir / "ArchiveAndImages"
            archive_dir.mkdir()
            (archive_dir / "released.md").write_text(
                "---\n"
                "author:\n"
                "  - Ada Lovelace\n"
                "  - Grace Hopper\n"
                "document_version: 1.10\n"
                "state: Released\n"
                "---\n"
                "# Released\n",
                encoding="utf-8",
            )
            (archive_dir / "draft.md").write_text("# Draft\n", encoding="utf-8")
            zeta_dir = source_dir / "Zeta"
            zeta_dir.mkdir()
            (zeta_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")
            (source_dir / "unclassified.md").write_text(
                "# Unclassified\n", encoding="utf-8"
            )
            (source_dir / "null-author.md").write_text(
                "---\nauthor:\n  - null\n---\n# Null Author\n",
                encoding="utf-8",
            )

            pages = collect_feature_related_pages(feature_dir)["Documents"]
            tree = _new_related_tree_node()
            for page in pages:
                relative_parts = page[1].split("/")[1:]
                _insert_related_tree_entry(tree, relative_parts, *page)
            rendered = build_document_tree_card("Documents", tree=tree)

        self.assertIn('<table class="document-tree-table">', rendered)
        self.assertIn("<thead>", rendered)
        self.assertIn('<tr class="document-tree-table__header"><th></th>', rendered)
        self.assertIn("<th>Author</th><th>State</th><th>Version</th>", rendered)
        self.assertIn(
            '<details class="abstract document-tree-card">\n'
            "<summary>&#128193; Documents (5 files)</summary>",
            rendered,
        )
        self.assertEqual(2, rendered.count('class="document-tree-table__directory"'))
        self.assertLess(
            rendered.index(">Unclassified</a>"),
            rendered.index(">Null Author</a>"),
        )
        self.assertLess(
            rendered.index(">Null Author</a>"),
            rendered.index(">ArchiveAndImages</strong>"),
        )
        self.assertLess(
            rendered.index(">Zeta</strong>"),
            rendered.index(">ArchiveAndImages</strong>"),
        )
        self.assertNotIn(">Archive And Images</strong>", rendered)
        self.assertLess(rendered.index(">Released</a>"), rendered.index(">Draft</a>"))
        self.assertIn("&#9500;&#9472;&nbsp;", rendered)
        self.assertIn("&#9492;&#9472;&nbsp;", rendered)
        self.assertIn("document-tree-table__file-cell", rendered)
        self.assertIn("document-tree-table__prefix--root", rendered)
        self.assertNotIn("document-tree-table__guide-layer", rendered)
        self.assertNotIn("document-tree-table__guide-segment", rendered)
        self.assertIn(
            "<td>Ada Lovelace<br>Grace Hopper</td><td>Released</td><td>1.10</td>",
            rendered,
        )
        self.assertIn("<td>&mdash;</td><td>&mdash;</td><td>&mdash;</td>", rendered)
        self.assertNotIn(">None</td>", rendered)
        self.assertNotIn("width: calc", rendered)
        self.assertNotIn("margin-left:", rendered)
        self.assertNotIn("Version: 1.10", rendered)
        self.assertNotIn("State: Released", rendered)

    def test_empty_document_tree_is_expandable(self) -> None:
        rendered = build_document_tree_card(
            "ArchiveAndImages", empty_message="No files in ArchiveAndImages/"
        )

        self.assertIn(
            '<details class="abstract document-tree-card">\n'
            "<summary>&#128193; ArchiveAndImages</summary>",
            rendered,
        )
        self.assertIn(
            '<p class="document-tree-card__empty"><em>No files in ArchiveAndImages/</em></p>',
            rendered,
        )
        self.assertNotIn("Archive And Images", rendered)

    def test_labeled_source_keeps_folder_label_verbatim(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            feature_dir = Path(temporary_directory) / "Example Feature"
            source_dir = feature_dir / "System_Spec" / "ArchiveAndImages"
            source_dir.mkdir(parents=True)
            (source_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")
            feature = _build_process_table_feature(
                feature_dir, ["[ArchiveAndImages](System_Spec/ArchiveAndImages)"]
            )
            rendered = build_resolved_group_process_sources_content(
                feature.get_groups()[0],
                feature_dir,
                {
                    "System_Spec/ArchiveAndImages": [
                        ("Guide", "System_Spec/ArchiveAndImages/guide.md")
                    ]
                },
            )

        self.assertIn(
            "<summary>&#128193; ArchiveAndImages (1 file)</summary>", rendered
        )
        self.assertNotIn("Archive And Images", rendered)

    def test_labeled_external_source_renders_as_direct_link(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            feature = _build_process_table_feature(
                Path(temporary_directory),
                [
                    "[System tests](https://pages.github.siemens.cloud/AS-IO/Modul-Dashboard/TestCases/SystemTests/example)"
                ],
            )
            rendered = build_resolved_group_process_sources_content(
                feature.get_groups()[0],
                Path(temporary_directory),
                {},
            )

        self.assertIn(
            '<a href="https://pages.github.siemens.cloud/AS-IO/Modul-Dashboard/TestCases/SystemTests/example" '
            'target="_blank" rel="noopener noreferrer">System tests</a>',
            rendered,
        )
        self.assertNotIn("Testcase Explorer", rendered)

    def test_registered_mount_source_renders_normal_document_tree(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            docs_root = Path(temporary_directory) / "docs"
            feature_dir = docs_root / "Features" / "Example Feature"
            source_root = docs_root / "TestCases" / "IntegrationTests" / "Security"
            source_dir = source_root / "Area"
            feature_dir.mkdir(parents=True)
            source_dir.mkdir(parents=True)
            (source_root / "direct.md").write_text("# Direct\n", encoding="utf-8")
            (source_dir / "case.md").write_text(
                "---\nauthor: Test Owner\nstate: Released\n---\n# Case\n",
                encoding="utf-8",
            )
            feature = _build_process_table_feature(
                feature_dir,
                ["[Integration tests](TestCases/IntegrationTests/Security)"],
            )

            with (
                patch.dict(
                    generate_features_dashboard.os.environ,
                    {"MODUL_DASHBOARD_DOCS_DIR": str(docs_root)},
                ),
                patch.object(
                    generate_features_dashboard,
                    "load_content_sources",
                    return_value=[
                        SimpleNamespace(mount_path=PurePosixPath("TestCases"))
                    ],
                ),
            ):
                rendered = build_resolved_group_process_sources_content(
                    feature.get_groups()[0], feature_dir, {}
                )
                details = build_resolved_group_process_details_content(
                    feature.get_groups()[0],
                    feature_dir,
                    build_resolved_process_progress_summaries(feature),
                )

        self.assertIn("<strong>Area</strong>", rendered)
        self.assertIn(
            'href="/TestCases/IntegrationTests/Security/Area/case/"', rendered
        )
        self.assertIn('href="/TestCases/IntegrationTests/Security/direct/"', details)
        self.assertIn("Test Owner", rendered)
        self.assertIn("Released", rendered)

    def test_group_file_navigation_distinguishes_rendered_documents(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            feature_dir = Path(temporary_directory) / "Feature"
            source_dir = feature_dir / "Documents"
            source_dir.mkdir(parents=True)
            (source_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")

            entries = features_section._build_group_file_view_nav_entries(
                "Features",
                feature_dir,
                {"Documents": [("Guide", "Documents/guide.md")]},
                {"Documents": ("Group", "group")},
            )

        self.assertEqual(
            [
                {"Documents/Guide": "Features/Feature/Documents/guide/index.md"},
                {
                    "Documents/Guide (rendered)": (
                        "Features/Feature/Documents/guide/render/index.md"
                    )
                },
            ],
            entries["group"],
        )

    def test_group_file_navigation_deduplicates_overlapping_sources(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            feature_dir = Path(temporary_directory)
            document = feature_dir / "System_Spec" / "Feature_Elaboration" / "guide.md"
            document.parent.mkdir(parents=True)
            document.write_text("# Guide\n", encoding="utf-8")
            related_pages = {
                "System_Spec": [("Guide", "System_Spec/Feature_Elaboration/guide.md")]
            }

            entries = features_section._build_group_file_view_nav_entries(
                "Features",
                feature_dir,
                related_pages,
                {
                    "System_Spec": ("Group", "group"),
                    "System_Spec/Feature_Elaboration": ("Group", "group"),
                },
            )

        self.assertEqual(2, len(entries["group"]))
        self.assertEqual(
            {
                "System_Spec/Guide": (
                    f"Features/{feature_dir.name}/System_Spec/Feature_Elaboration/guide/index.md"
                )
            },
            entries["group"][0],
        )
        self.assertEqual(
            {
                "System_Spec/Guide (rendered)": (
                    f"Features/{feature_dir.name}/System_Spec/Feature_Elaboration/guide/render/index.md"
                )
            },
            entries["group"][1],
        )

    def test_feature_file_views_follow_source_group_and_file_type_rules(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            feature_dir = repo_root / "docs" / "Library" / "Example"
            design_dir = feature_dir / "Design"
            default_dir = feature_dir / "Default"
            design_dir.mkdir(parents=True)
            default_dir.mkdir()
            (design_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")
            (design_dir / "config.json").write_text("{}\n", encoding="utf-8")
            (design_dir / "manual.pdf").write_bytes(b"%PDF")
            (default_dir / "notes.md").write_text("# Notes\n", encoding="utf-8")
            related_pages = {
                "Design": [
                    ("Guide", "Design/guide.md"),
                    ("Config", "Design/config.json"),
                    ("Manual", "Design/manual.pdf"),
                    ("Missing", "Design/missing.yaml"),
                ],
                "Default": [("Notes", "Default/notes.md")],
            }
            groups = [{"name": "Engineering", "items": ["design", "default"]}]
            feature = build_resolved_feature(
                "Example",
                {
                    "processes": {
                        "design": {
                            "sources": [
                                "[Design records](Design)",
                                "https://example.test/design",
                            ]
                        }
                    }
                },
                {},
                collect_process_field_definitions(
                    {
                        "processes": {
                            "design": {
                                "sources": [
                                    "[Design records](Design)",
                                    "https://example.test/design",
                                ]
                            },
                            "default": {"sources": "Default"},
                        }
                    }
                ),
                groups,
            )
            source_dir_group_map = (
                features_section._build_resolved_source_dir_group_map(feature)
            )
            files = Files([])
            config = SimpleNamespace(
                site_dir=str(repo_root / "site"),
                use_directory_urls=True,
                plugins=SimpleNamespace(_current_plugin=None),
            )
            with patch.object(features_section, "REPO_ROOT", repo_root):
                remapped_pages = features_section._build_feature_file_view_pages(
                    files,
                    config,
                    "Library",
                    feature_dir,
                    related_pages,
                )
                navigation = features_section._build_group_file_view_nav_entries(
                    "Library",
                    feature_dir,
                    related_pages,
                    source_dir_group_map,
                )

        self.assertEqual(
            {
                "Design": ("Engineering", "engineering"),
                "Default": ("Engineering", "engineering"),
            },
            source_dir_group_map,
        )
        self.assertEqual(
            [
                ("Guide", "Design/guide/render/index.md"),
                ("Config", "Design/config/index.md"),
                ("Manual", "Design/manual.pdf"),
                ("Missing", "Design/missing.yaml"),
            ],
            remapped_pages["Design"],
        )
        generated_files = {file.src_uri for file in files}
        self.assertIn("Library/Example/Design/guide/index.md", generated_files)
        self.assertIn("Library/Example/Design/guide/render/index.md", generated_files)
        self.assertIn("Library/Example/Design/config/index.md", generated_files)
        self.assertNotIn("Library/Example/Design/manual/index.md", generated_files)
        self.assertEqual(
            [
                {"Design/Guide": "Library/Example/Design/guide/index.md"},
                {
                    "Design/Guide (rendered)": (
                        "Library/Example/Design/guide/render/index.md"
                    )
                },
                {"Design/Config": "Library/Example/Design/config/index.md"},
                {"Default/Notes": "Library/Example/Default/notes/index.md"},
                {
                    "Default/Notes (rendered)": (
                        "Library/Example/Default/notes/render/index.md"
                    )
                },
            ],
            navigation["engineering"],
        )

    def test_markdown_source_reference_returns_label_and_target(self) -> None:
        self.assertEqual(
            ("Test plan", "https://example.test/plan"),
            parse_source_reference("[Test plan](https://example.test/plan)"),
        )
        self.assertEqual(
            ("documents", "documents"), parse_source_reference("documents")
        )

    def test_source_classifier_handles_bare_www_urls(self) -> None:
        self.assertFalse(is_local_source_path("www.example.test/plan"))
        self.assertFalse(is_local_source_path("[Test plan](www.example.test/plan)"))
        self.assertTrue(is_local_source_path("documents"))

    def test_process_description_must_be_template_owned_when_declared(self) -> None:
        template_data = {
            "processes": {
                "instance_owned": {"description": "optional"},
            }
        }

        with self.assertRaisesRegex(ValueError, "description must use the template"):
            collect_process_field_definitions(template_data)

    def test_process_description_sanitization_keeps_safe_markdown(self) -> None:
        template_data = {
            "processes": {
                "documented": {"description": {"state": "template", "value": "Note"}}
            }
        }
        definitions = collect_process_field_definitions(template_data)
        self.assertEqual("template", definitions["documented"]["description"].state)

        description = (
            "**Keep this formatting** [safe](https://example.test) "
            "[unsafe](javascript:alert(1)) [angle](<javascript:alert(2)>) "
            "[reference][unsafe-reference]\n\n"
            "[unsafe-reference]: <data:text/html,alert(1)>"
        )
        sanitized = sanitize_markdown_description(description)
        self.assertIn("**Keep this formatting**", sanitized)
        self.assertIn("[safe](https://example.test)", sanitized)
        self.assertIn("[unsafe](#alert(1))", sanitized)
        self.assertIn("[angle](#)", sanitized)
        self.assertIn("[unsafe-reference]: #", sanitized)
        self.assertNotIn("javascript:", sanitized.lower())
        self.assertNotIn("data:", sanitized.lower())

    def test_append_state_combines_template_and_feature_values(self) -> None:
        template_data = {
            "processes": {
                "append": {
                    "sources": {
                        "state": "append",
                        "value": [
                            "Shared/Documents",
                            "[Baseline](https://example.test/documents)",
                        ],
                    }
                }
            }
        }
        feature = build_resolved_feature(
            "Example",
            {
                "processes": {
                    "append": {
                        "sources": [
                            "Shared\\Documents",
                            "[Feature label](https://example.test/documents)",
                            "Product/Documents",
                        ]
                    }
                }
            },
            {},
            collect_process_field_definitions(template_data),
            [{"name": "Append", "items": ["append"]}],
        )
        self.assertEqual(
            [
                "Shared/Documents",
                "[Baseline](https://example.test/documents)",
                "Product/Documents",
            ],
            get_resolved_sources(feature.get_process("append")),
        )

    def test_template_and_append_states_validate_declared_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "state 'template' must declare"):
            collect_process_field_definitions(
                {"processes": {"process": {"description": {"state": "template"}}}}
            )
        with self.assertRaisesRegex(ValueError, "state 'append' must declare"):
            collect_process_field_definitions(
                {
                    "processes": {
                        "process": {"sources": {"state": "append", "value": []}}
                    }
                }
            )
        with self.assertRaisesRegex(ValueError, "state 'append' must declare"):
            collect_process_field_definitions(
                {
                    "processes": {
                        "process": {"sources": {"state": "append", "value": [""]}}
                    }
                }
            )
        definitions = collect_process_field_definitions(
            {
                "processes": {
                    "process": {
                        "description": {"state": "template", "value": ""},
                        "sources": {"state": "append", "value": "Documents"},
                    }
                }
            }
        )

        self.assertTrue(definitions["process"]["description"].value_is_declared)
        self.assertEqual("", definitions["process"]["description"].default)
        self.assertEqual("append", definitions["process"]["sources"].state)

    def test_template_owned_sources_reject_feature_override(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            feature_dir = Path(temporary_directory) / "Example Feature"
            feature_dir.mkdir()
            (feature_dir / "overview.yaml").write_text("{}\n", encoding="utf-8")
            template_definitions = collect_process_field_definitions(
                {
                    "processes": {
                        "template": {
                            "display_name": {
                                "state": "template",
                                "value": "Template",
                            },
                            "description": {
                                "state": "template",
                                "value": "Template description",
                            },
                            "sources": {
                                "state": "template",
                                "value": "template-default",
                            },
                        }
                    }
                }
            )

            with (
                patch.object(features_section, "REPO_ROOT", feature_dir.parent),
                self.assertLogs("mkdocs.hooks", "WARNING") as captured,
            ):
                features_section._warn_template_mismatches(
                    "Features",
                    feature_dir,
                    {
                        "processes": {
                            "template": {
                                "display_name": "Override",
                                "description": "Override description",
                                "sources": "override",
                            }
                        }
                    },
                    {},
                    template_definitions,
                )

        self.assertTrue(
            any(
                "cannot override template-only field 'sources'" in line
                for line in captured.output
            )
        )
        self.assertTrue(
            any(
                "cannot override template-only field 'display_name'" in line
                for line in captured.output
            )
        )
        self.assertTrue(
            any(
                "cannot override template-only field 'description'" in line
                for line in captured.output
            )
        )

        feature = build_resolved_feature(
            "Example",
            {
                "processes": {
                    "template": {
                        "display_name": "Override",
                        "description": "Override description",
                        "sources": "override",
                    }
                }
            },
            {},
            template_definitions,
            [{"name": "Template", "items": ["template"]}],
        )
        self.assertEqual(
            ["template-default"], get_resolved_sources(feature.get_process("template"))
        )

    def test_non_template_sources_allow_feature_override(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            feature_dir = Path(temporary_directory) / "Example Feature"
            feature_dir.mkdir()
            (feature_dir / "overview.yaml").write_text("{}\n", encoding="utf-8")
            template_definitions = collect_process_field_definitions(
                {"processes": {"required": {"sources": "template-source"}}}
            )

            with (
                patch.object(features_section, "REPO_ROOT", feature_dir.parent),
                self.assertNoLogs("mkdocs.hooks", "WARNING"),
            ):
                features_section._warn_template_mismatches(
                    "Features",
                    feature_dir,
                    {"processes": {"required": {"sources": "feature-source"}}},
                    {},
                    template_definitions,
                )

        feature = build_resolved_feature(
            "Example",
            {"processes": {"required": {"sources": "feature-source"}}},
            {},
            template_definitions,
            [{"name": "Required", "items": ["required"]}],
        )
        self.assertEqual(
            ["feature-source"], get_resolved_sources(feature.get_process("required"))
        )


class FeedbackUrlTests(unittest.TestCase):
    def test_issue_url_preassigns_project_and_all_assignees(self) -> None:
        issue_url = build_create_issue_url(
            "content_request.yml",
            "AS-IO/9",
            ["assignee-one-ext", "assignee-two-ext"],
        )

        query = parse_qs(urlsplit(issue_url).query)
        self.assertEqual(["content_request.yml"], query["template"])
        self.assertEqual(["AS-IO/9"], query["projects"])
        self.assertEqual(["assignee-one-ext,assignee-two-ext"], query["assignees"])

    def test_issue_url_prefills_related_page_location(self) -> None:
        page_url = (
            "https://pages.github.siemens.cloud/AS-IO/Modul-Dashboard/"
            "Features/Example%20Feature/?view=details&tab=1"
        )

        issue_url = build_create_issue_url(
            "content_request.yml", "AS-IO/9", ["feature-owner"], page_url=page_url
        )

        query = parse_qs(urlsplit(issue_url).query)
        self.assertEqual([page_url], query["location"])

    def test_project_shorthand_builds_organization_project_url(self) -> None:
        project = normalize_github_project(" AS-IO/9 ")

        self.assertEqual("AS-IO/9", project)
        self.assertEqual(
            "https://github.siemens.cloud/orgs/AS-IO/projects/9",
            build_github_project_url(project),
        )

    def test_invalid_routing_metadata_is_rejected(self) -> None:
        for project in (None, "", "AS-IO/0", "AS-IO/not-a-number", "orgs/AS-IO/9"):
            with self.subTest(project=project):
                self.assertIsNone(normalize_github_project(project))

        for assignees in (None, [], [""], ["person", "person"], ["not a login"]):
            with self.subTest(assignees=assignees):
                self.assertIsNone(normalize_assignees(assignees))

    def test_partial_feature_routing_is_rejected_instead_of_inheriting(self) -> None:
        feature = build_resolved_feature(
            "Example",
            {
                "content_request": {
                    "github_project": "AS-IO/9",
                    "assignees": [],
                }
            },
            {},
            {},
            [],
        )

        with self.assertRaisesRegex(ValueError, "content_request must define"):
            get_resolved_content_routing(feature)

    def test_non_mapping_feature_routing_is_rejected(self) -> None:
        with self.assertRaisesRegex(TypeError, "content_request must be a mapping"):
            build_resolved_feature(
                "Example", {"content_request": "AS-IO/9"}, {}, {}, []
            )


class TemplateAndSummaryTests(unittest.TestCase):
    def test_feature_main_fields_exclude_top_level_responsible(self) -> None:
        definitions = collect_feature_field_definitions(
            {
                "feature_name": "required",
                "responsible": "optional",
                "owner": "required",
            }
        )
        feature = build_resolved_feature(
            "Example",
            {
                "feature_name": "Example",
                "responsible": "SFO",
                "owner": "Feature Owner",
            },
            definitions,
            {},
            [],
        )

        content = build_resolved_main_fields_content(feature)

        self.assertNotIn("Responsible", content)
        self.assertNotIn("SFO", content)

    def test_summary_project_link_is_optional_without_feature_routing(self) -> None:
        rendered = build_feature_summary_table(
            [
                {
                    "name": "Example Feature",
                    "link": "Example Feature/index.md",
                    "owner": "Example Owner",
                    "readiness": "-",
                    "last_update": "-",
                    "project_link_url": None,
                    "project_link_state": generate_features_dashboard.STATE_OPTIONAL,
                    "document_location": "-",
                }
            ],
            link_feature_name=True,
        )

        self.assertIn("| - | - |", rendered)
        self.assertNotIn("MISSING", rendered)

    def test_template_field_grammar_preserves_states_and_defaults(self) -> None:
        template_data = {
            "required": "required",
            "optional": {"required": False},
            "defaulted": {"state": "optional", "value": "fallback"},
            "template_only": {"state": "template", "value": "internal"},
            "dashboard_request": {},
            "processes": {},
        }

        definitions = collect_feature_field_definitions(template_data)

        self.assertEqual(
            {
                "required": "required",
                "optional": "optional",
                "defaulted": "optional",
                "template_only": "template",
            },
            {
                field_name: definition.state
                for field_name, definition in definitions.items()
            },
        )
        self.assertEqual("fallback", definitions["defaulted"].default)
        self.assertEqual(("required", 42), parse_template_field_spec(42))
        self.assertEqual(("template", None), parse_template_field_spec("template_only"))

    def test_resolved_feature_normalizes_values_and_enforces_cardinality(self) -> None:
        template_data = {
            "feature_name": "required",
            "description": "optional",
            "processes": {
                "delivery": {
                    "display_name": {"state": "template", "value": "Delivery"},
                    "owner": "required",
                    "version": "required",
                    "sources": {"state": "append", "value": "Shared"},
                    "description": {"state": "template", "value": ""},
                }
            },
        }
        feature = build_resolved_feature(
            "Example",
            {
                "feature_name": ["Example"],
                "processes": {
                    "delivery": {
                        "owner": "Ada",
                        "sources": ["Product", "Shared"],
                    }
                },
            },
            collect_feature_field_definitions(template_data),
            collect_process_field_definitions(template_data),
            [{"name": "Delivery", "items": ["delivery"]}],
        )
        process = feature.get_groups()[0].get_processes()[0]

        self.assertEqual(("Example", False), feature.get_value_one("feature_name"))
        self.assertEqual(([], False), feature.get_value_many("description"))
        self.assertEqual((["Ada"], False), process.get_value_many("owner"))
        self.assertEqual((None, True), process.get_value_one("version"))
        self.assertEqual(
            (["Shared", "Product"], False), process.get_value_many("sources")
        )
        self.assertEqual((None, False), process.get_value_one("description"))
        with self.assertRaisesRegex(ValueError, "requires one value, but has 2"):
            process.get_value_one("sources")
        with self.assertRaisesRegex(ValueError, "contains no field 'unknown'"):
            process.get_value_many("unknown")

    def test_resolved_scalar_consumers_reject_multiple_values(self) -> None:
        template_data = {
            "feature_name": "required",
            "processes": {
                "delivery": {
                    "progress": "required",
                    "date": "required",
                    "version": "required",
                    "sources": "optional",
                }
            },
        }
        feature = build_resolved_feature(
            "Example",
            {
                "feature_name": "Example",
                "processes": {
                    "delivery": {
                        "progress": [40, 80],
                        "date": "2026-08-28",
                        "version": ["1.0", "2.0"],
                    }
                },
            },
            collect_feature_field_definitions(template_data),
            collect_process_field_definitions(template_data),
            [{"name": "Delivery", "items": ["delivery"]}],
        )

        with self.assertRaisesRegex(ValueError, "progress.*requires one value"):
            build_resolved_process_readiness(
                feature.get_process("delivery"),
                Path("."),
                ProcessReadinessWeights(source=10, metadata=10, progress=80),
            )
        with self.assertRaisesRegex(ValueError, "version.*requires one value"):
            feature.get_process("delivery").get_value_one("version")

    def test_resolved_readiness_does_not_count_template_defaults(self) -> None:
        template_data = {
            "processes": {
                "delivery": {
                    "owner": "Template owner",
                    "version": "required",
                    "progress": 0,
                    "sources": "optional",
                }
            }
        }
        feature = build_resolved_feature(
            "Example",
            {"processes": {"delivery": {"version": "1.0", "progress": 50}}},
            {},
            collect_process_field_definitions(template_data),
            [{"name": "Delivery", "items": ["delivery"]}],
        )

        readiness = build_resolved_process_readiness(
            feature.get_process("delivery"),
            Path("."),
            ProcessReadinessWeights(source=10, metadata=10, progress=80),
        )

        self.assertEqual(1, readiness.metadata_total)
        self.assertEqual(1, readiness.metadata_filled)

    def test_resolved_readiness_counts_frontmatter_metadata(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            feature_dir = Path(temporary_directory) / "Example Feature"
            source_dir = feature_dir / "Documents"
            source_dir.mkdir(parents=True)
            (source_dir / "released.md").write_text(
                "---\n"
                "owner: Ada Lovelace\n"
                "document_version: 1.0\n"
                "modified_at: 2026-08-31\n"
                "state: released\n"
                "---\n# Released\n",
                encoding="utf-8",
            )

            template_data = {
                "processes": {
                    "delivery": {
                        "owner": "required",
                        "version": "required",
                        "date": "required",
                        "sources": {
                            "state": "template",
                            "value": ["Documents"],
                        },
                        "progress": 0,
                    }
                }
            }
            feature = build_resolved_feature(
                "Example Feature",
                {"processes": {"delivery": {"progress": 50}}},
                {},
                collect_process_field_definitions(template_data),
                [{"name": "Delivery", "items": ["delivery"]}],
            )
            readiness = build_resolved_process_readiness(
                feature.get_process("delivery"),
                feature_dir,
                ProcessReadinessWeights(source=10, metadata=10, progress=80),
            )

        self.assertEqual(3, readiness.metadata_total)
        self.assertEqual(3, readiness.metadata_filled)

    def test_resolved_readiness_combines_metadata_across_frontmatter_files(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary_directory:
            feature_dir = Path(temporary_directory) / "Example Feature"
            source_dir = feature_dir / "Documents"
            source_dir.mkdir(parents=True)
            (source_dir / "owner.md").write_text(
                "---\nowner: Ada Lovelace\n---\n# Owner\n", encoding="utf-8"
            )
            (source_dir / "version-date.md").write_text(
                "---\ndocument_version: 1.0\nmodified_at: 2026-08-31\n---\n# Version\n",
                encoding="utf-8",
            )

            template_data = {
                "processes": {
                    "delivery": {
                        "owner": "required",
                        "version": "required",
                        "date": "required",
                        "sources": {
                            "state": "template",
                            "value": ["Documents"],
                        },
                        "progress": 0,
                    }
                }
            }
            feature = build_resolved_feature(
                "Example Feature",
                {"processes": {"delivery": {"progress": 50}}},
                {},
                collect_process_field_definitions(template_data),
                [{"name": "Delivery", "items": ["delivery"]}],
            )
            readiness = build_resolved_process_readiness(
                feature.get_process("delivery"),
                feature_dir,
                ProcessReadinessWeights(source=10, metadata=10, progress=80),
            )

        self.assertEqual(3, readiness.metadata_total)
        self.assertEqual(3, readiness.metadata_filled)

    def test_resolved_readiness_counts_explicit_override_of_template_default(
        self,
    ) -> None:
        template_data = {
            "processes": {
                "delivery": {
                    "owner": "Template owner",
                    "version": "required",
                    "progress": 0,
                    "sources": "optional",
                }
            }
        }
        feature = build_resolved_feature(
            "Example",
            {"processes": {"delivery": {"owner": "Feature owner", "progress": 50}}},
            {},
            collect_process_field_definitions(template_data),
            [{"name": "Delivery", "items": ["delivery"]}],
        )

        readiness = build_resolved_process_readiness(
            feature.get_process("delivery"),
            Path("."),
            ProcessReadinessWeights(source=10, metadata=10, progress=80),
        )

        self.assertEqual(2, readiness.metadata_total)
        self.assertEqual(1, readiness.metadata_filled)

    def test_empty_template_list_default_remains_required_missing(self) -> None:
        template_data = {
            "processes": {
                "delivery": {
                    "owner": {"state": "required", "value": [""]},
                    "progress": 0,
                    "sources": "optional",
                }
            }
        }
        feature = build_resolved_feature(
            "Example",
            {},
            {},
            collect_process_field_definitions(template_data),
            [{"name": "Delivery", "items": ["delivery"]}],
        )

        readiness = build_resolved_process_readiness(
            feature.get_process("delivery"),
            Path("."),
            ProcessReadinessWeights(source=10, metadata=10, progress=80),
        )

        self.assertEqual(1, readiness.metadata_total)
        self.assertEqual(0, readiness.metadata_filled)

    def test_template_only_top_level_values_are_not_exposed_as_feature_fields(
        self,
    ) -> None:
        template_data = {
            "feature_name": "required",
            "internal": {"state": "template", "value": "secret"},
            "processes": {},
        }
        feature = build_resolved_feature(
            "Example",
            {"feature_name": "Example"},
            collect_feature_field_definitions(template_data),
            {},
            [],
        )

        self.assertIn("feature_name", feature.get_field_names())
        self.assertNotIn("internal", feature.get_field_names())
        with self.assertRaisesRegex(ValueError, "contains no field 'internal'"):
            feature.get_value_many("internal")

    def test_empty_mapping_resolves_as_missing_value(self) -> None:
        template_data = {"processes": {"delivery": {"owner": "required"}}}
        feature = build_resolved_feature(
            "Example",
            {"processes": {"delivery": {"owner": {}}}},
            {},
            collect_process_field_definitions(template_data),
            [{"name": "Delivery", "items": ["delivery"]}],
        )

        self.assertEqual(
            (None, True), feature.get_process("delivery").get_value_one("owner")
        )

    def test_resolved_lists_preserve_empty_items_for_consumers(self) -> None:
        template_data = {"processes": {"delivery": {"owner": "required"}}}
        feature = build_resolved_feature(
            "Example",
            {"processes": {"delivery": {"owner": ["Ada", "", None]}}},
            {},
            collect_process_field_definitions(template_data),
            [{"name": "Delivery", "items": ["delivery"]}],
        )

        self.assertEqual(
            (["Ada", "", None], False),
            feature.get_process("delivery").get_value_many("owner"),
        )

    def test_required_empty_list_items_report_required_missing(self) -> None:
        template_data = {"processes": {"delivery": {"owner": "required"}}}
        feature = build_resolved_feature(
            "Example",
            {"processes": {"delivery": {"owner": ["", None]}}},
            {},
            collect_process_field_definitions(template_data),
            [{"name": "Delivery", "items": ["delivery"]}],
        )

        self.assertEqual(
            (["", None], True),
            feature.get_process("delivery").get_value_many("owner"),
        )
        self.assertIn(
            "MISSING",
            render_resolved_value(
                feature.get_process("delivery").get_value_many("owner")[0],
                True,
            ),
        )

    def test_resolved_top_level_default_provenance_tracks_overrides(self) -> None:
        template_data = {"label": "Template label", "processes": {}}
        definitions = collect_feature_field_definitions(template_data)

        fallback = build_resolved_feature("Fallback", {}, definitions, {}, [])
        override = build_resolved_feature(
            "Override", {"label": "Feature label"}, definitions, {}, []
        )

        self.assertTrue(fallback.has_template_default("label"))
        self.assertFalse(override.has_template_default("label"))

    def test_required_sources_are_not_counted_as_metadata(self) -> None:
        template_data = {
            "processes": {
                "delivery": {
                    "owner": "required",
                    "sources": "required",
                    "progress": 0,
                }
            }
        }
        feature = build_resolved_feature(
            "Example",
            {
                "processes": {
                    "delivery": {
                        "sources": "https://example.test/source",
                        "progress": 100,
                    }
                }
            },
            {},
            collect_process_field_definitions(template_data),
            [{"name": "Delivery", "items": ["delivery"]}],
        )

        readiness = build_resolved_process_readiness(
            feature.get_process("delivery"),
            Path("."),
            ProcessReadinessWeights(source=10, metadata=10, progress=80),
        )

        self.assertEqual(1, readiness.metadata_total)
        self.assertEqual(0, readiness.metadata_filled)

    def test_template_only_process_fields_are_not_group_table_columns(self) -> None:
        template_data = {
            "processes": {
                "delivery": {
                    "display_name": {"state": "template", "value": "Delivery"},
                    "internal": {"state": "template", "value": "secret"},
                    "progress": 0,
                }
            }
        }
        feature = build_resolved_feature(
            "Example",
            {},
            {},
            collect_process_field_definitions(template_data),
            [{"name": "Delivery", "items": ["delivery"]}],
        )

        self.assertNotIn(
            "internal", _collect_resolved_group_fields(feature.get_groups()[0])
        )

    def test_resolved_feature_rejects_non_mapping_root(self) -> None:
        with self.assertRaisesRegex(TypeError, "must contain a mapping"):
            build_resolved_feature(
                "Example",
                [],
                {},
                {},
                [],
            ).get_value_many("missing")

    def test_group_validation_rejects_unknown_duplicate_and_ungrouped_processes(
        self,
    ) -> None:
        schemas = {"first": {}, "second": {}}
        invalid_cases = (
            ([{"name": "A", "items": ["unknown"]}], "unknown process"),
            (
                [
                    {"name": "A", "items": ["first"]},
                    {"name": "B", "items": ["first", "second"]},
                ],
                "multiple groups",
            ),
            ([{"name": "A", "items": ["first"]}], "not assigned"),
        )

        for groups, error in invalid_cases:
            with self.subTest(groups=groups), self.assertRaisesRegex(ValueError, error):
                build_effective_groups(groups, schemas)

        self.assertEqual(
            [{"name": "A", "items": ["first", "second"]}],
            build_effective_groups(
                [{"name": " A ", "items": ["first", "second"]}], schemas
            ),
        )

    def test_process_readiness_weight_configuration_requires_valid_total(self) -> None:
        self.assertEqual(
            ProcessReadinessWeights(source=10, metadata=10, progress=80),
            load_process_readiness_weights(
                {
                    "process_readiness_weights": {
                        "source": 10,
                        "metadata": 10,
                        "progress": 80,
                    }
                }
            ),
        )
        for weights, error in (
            ({"source": 10, "progress": 90}, "missing: metadata"),
            ({"source": 10, "metadata": 10, "progress": 70}, "sum to 100"),
            ({"source": -10, "metadata": 10, "progress": 100}, "non-negative"),
        ):
            with (
                self.subTest(weights=weights),
                self.assertRaisesRegex(ValueError, error),
            ):
                load_process_readiness_weights({"process_readiness_weights": weights})
        with self.assertRaisesRegex(TypeError, "keys must be strings"):
            load_process_readiness_weights(
                {"process_readiness_weights": {1: 10, "metadata": 10, "progress": 80}}
            )


class ProgressAndParsingTests(unittest.TestCase):
    def test_progress_parsing_and_rendering_handles_boundaries(self) -> None:
        self.assertEqual(12.5, parse_progress_value(" 12.5 "))
        self.assertIsNone(parse_progress_value("unknown"))
        self.assertIsNone(parse_progress_value(None))
        self.assertEqual("2026-08-20", parse_date_value("2026-08-20").isoformat())
        self.assertIsNone(parse_date_value("20/08/2026"))
        self.assertIn('value="100"', render_progress_meter(130, "Done"))
        self.assertIn('value="0"', render_progress_meter(-1, "Done"))
        count_meter = render_progress_meter(50, "Items", display_value="15 / 30")
        self.assertIn('aria-label="Items 15 / 30"', count_meter)
        self.assertIn("<strong>15 / 30</strong>", count_meter)
        self.assertIn("MISSING", render_progress_meter(None, "Done"))

    def test_group_flowchart_uses_internal_urls_without_callback_syntax(self) -> None:
        process_definitions = collect_process_field_definitions(
            {
                "processes": {
                    "delivery": {
                        "display_name": {
                            "state": "template",
                            "value": "Delivery",
                        },
                    }
                }
            }
        )
        feature = build_resolved_feature(
            "Example",
            {},
            {},
            process_definitions,
            [{"name": 'Delivery "A"', "items": ["delivery"]}],
        )
        process_readiness = {
            "delivery": generate_features_dashboard.ProcessReadiness(
                source_linked=True,
                metadata_filled=0,
                metadata_total=0,
                progress=50,
                value=60,
            )
        }

        rendered = build_resolved_feature_group_readiness_content(
            feature, process_readiness
        )

        self.assertIn('click group0 "delivery-a/"', rendered)
        self.assertIn('group0["Delivery &quot;A&quot;<br/>(60%)"]', rendered)
        self.assertNotIn("callback", rendered)
        self.assertNotIn(" call ", rendered)

    def test_group_flowchart_uses_two_left_to_right_rows_for_six_groups(self) -> None:
        process_definitions = collect_process_field_definitions(
            {
                "processes": {
                    f"process{index}": {
                        "display_name": {
                            "state": "template",
                            "value": f"Process {index}",
                        },
                    }
                    for index in range(6)
                }
            }
        )
        feature = build_resolved_feature(
            "Example",
            {},
            {},
            process_definitions,
            [
                {"name": f"Group {index}", "items": [f"process{index}"]}
                for index in range(6)
            ],
        )
        process_readiness = {
            f"process{index}": generate_features_dashboard.ProcessReadiness(
                source_linked=True,
                metadata_filled=0,
                metadata_total=0,
                progress=50,
                value=60 + index,
            )
            for index in range(6)
        }

        rendered = build_resolved_feature_group_readiness_content(
            feature, process_readiness
        )

        self.assertIn("flowchart TB", rendered)
        self.assertIn('group0["Group 0<br/>(60%)"]', rendered)
        self.assertIn('group5["Group 5<br/>(65%)"]', rendered)
        self.assertIn('subgraph row0[" "]', rendered)
        self.assertIn("direction LR", rendered)
        self.assertIn("group0 --> group1 --> group2", rendered)
        self.assertIn('subgraph row1[" "]', rendered)
        self.assertEqual(2, rendered.count("direction LR"))
        self.assertIn("group3 --> group4 --> group5", rendered)
        self.assertIn("row0 --> row1", rendered)
        self.assertNotIn("group2 --> group3", rendered)


class FeaturesProcessorTests(unittest.TestCase):
    def test_existing_overview_directory_is_not_silently_skipped(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            section_root = Path(temporary_directory)
            feature_dir = section_root / "Invalid Metadata"
            (feature_dir / "overview.yaml").mkdir(parents=True)
            (section_root / "Pending Metadata").mkdir()

            self.assertEqual(
                [feature_dir],
                generate_features_dashboard.collect_publishable_feature_dirs(
                    section_root
                ),
            )
            with self.assertRaises(OSError):
                generate_features_dashboard.load_yaml(feature_dir / "overview.yaml")

    def tearDown(self) -> None:
        features_section.reset_cache()

    def test_reset_cache_discards_template_data(self) -> None:
        features_section._template_cache["Features"] = ("cached",)

        features_section.reset_cache()

        self.assertEqual({}, features_section._template_cache)

    def test_feature_template_fallback_keeps_readiness_placeholders(self) -> None:
        with patch(
            "generate_features_dashboard.get_detail_template_file",
            return_value=Path("missing-feature-detail.md"),
        ):
            template = load_feature_detail_template("Features")

        for placeholder in (
            "[[AUTO:FEATURE_READINESS_DETAILS]]",
            "[[AUTO:READINESS_FORMULA_NOTE]]",
            "[[AUTO:FEATURE_GROUP_READINESS]]",
        ):
            with self.subTest(placeholder=placeholder):
                self.assertIn(placeholder, template)

    def test_item_navigation_uses_feature_overviews_and_groups(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            _write_feature_fixture(repo_root)
            with (
                patch.object(generate_features_dashboard, "REPO_ROOT", repo_root),
                patch.object(features_section, "REPO_ROOT", repo_root),
            ):
                entries = features_section.build_item_nav_entries("Features")

        example_entry = next(
            entry["Example Feature"] for entry in entries if "Example Feature" in entry
        )
        self.assertEqual(
            {"Overview": "Features/Example Feature/index.md"}, example_entry[0]
        )
        self.assertTrue(
            any(
                "Delivery" in entry and isinstance(entry["Delivery"], list)
                for entry in example_entry[1:]
            )
        )
        self.assertEqual(
            {
                "Related Documents": (
                    "https://pages.github.siemens.cloud/AS-IO/Modul-Dashboard/"
                    "Features/Example%20Feature/#related-documents"
                )
            },
            example_entry[-1],
        )

        empty_entry = next(
            entry["Empty Feature"] for entry in entries if "Empty Feature" in entry
        )
        self.assertFalse(any("Related Documents" in entry for entry in empty_entry))
        self.assertFalse(any("Pending Feature" in entry for entry in entries))

    def test_item_navigation_omits_related_documents_for_nested_source(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            _write_feature_fixture(repo_root)
            template_path = (
                repo_root / "docs" / "Features" / "000_TEMPLATES" / "overview.yaml"
            )
            template_data = yaml.safe_load(template_path.read_text(encoding="utf-8"))
            template_data["processes"]["delivery"]["sources"]["value"] = [
                "Documents/Nested"
            ]
            template_path.write_text(
                yaml.safe_dump(template_data, sort_keys=False), encoding="utf-8"
            )
            feature_dir = repo_root / "docs" / "Features" / "Example Feature"
            (feature_dir / "Documents" / "guide.md").unlink()
            (feature_dir / "Supporting Material" / "notes.md").unlink()
            nested_dir = feature_dir / "Documents" / "Nested"
            nested_dir.mkdir()
            (nested_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")

            with (
                patch.object(generate_features_dashboard, "REPO_ROOT", repo_root),
                patch.object(features_section, "REPO_ROOT", repo_root),
            ):
                entries = features_section.build_item_nav_entries("Features")

        example_entry = next(
            entry["Example Feature"] for entry in entries if "Example Feature" in entry
        )
        self.assertFalse(any("Related Documents" in entry for entry in example_entry))

    def test_related_documents_navigation_uses_configured_site_url(self) -> None:
        with patch.dict(
            "os.environ",
            {"PAGES_URL": "http://127.0.0.1:8001/preview/"},
        ):
            link = features_section._feature_fragment_url(
                "Features", "A feature (test)", "related-documents"
            )

        self.assertEqual(
            "http://127.0.0.1:8001/preview/Features/A%20feature%20(test)/"
            "#related-documents",
            link,
        )

    def test_summary_placeholder_is_replaced_with_generated_table(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            _write_feature_fixture(repo_root)
            with (
                patch.object(generate_features_dashboard, "REPO_ROOT", repo_root),
                patch.object(features_section, "REPO_ROOT", repo_root),
            ):
                rendered = features_section.replace_placeholders(
                    "# Features\n\n[[AUTO:FEATURES_SUMMARY_TABLE]]\n", "Features"
                )

        self.assertNotIn("[[AUTO:FEATURES_SUMMARY_TABLE]]", rendered)
        self.assertIn("| Feature | Owner | Feature readiness |", rendered)
        self.assertIn("View project", rendered)
        self.assertIn("View documents", rendered)
        self.assertIn("Example Feature", rendered)
        self.assertNotIn("Pending Feature", rendered)

    def test_generate_item_pages_creates_feature_group_and_file_views(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            _write_feature_fixture(repo_root)
            files = Files([])
            config = SimpleNamespace(
                site_dir=str(repo_root / "site"),
                use_directory_urls=True,
                plugins=SimpleNamespace(_current_plugin=None),
            )
            with (
                patch.object(generate_features_dashboard, "REPO_ROOT", repo_root),
                patch.object(features_section, "REPO_ROOT", repo_root),
            ):
                features_section.generate_item_pages(files, config, "Features")

        generated_files = {file.src_uri: file.content_string for file in files}
        feature_index = "Features/Example Feature/index.md"
        group_index = "Features/Example Feature/delivery/index.md"
        self.assertIn(feature_index, generated_files)
        self.assertIn(group_index, generated_files)
        self.assertIn("## Overview", generated_files[feature_index])
        self.assertIn("## Process Groups", generated_files[feature_index])
        self.assertIn(
            "<small>For each process, readiness combines linked sources",
            generated_files[feature_index],
        )
        self.assertIn(
            "Feature and group readiness are averages of their processes.",
            generated_files[feature_index],
        )
        self.assertNotIn("<td>Feature readiness</td>", generated_files[feature_index])
        self.assertIn(
            'aria-label="Processes with linked sources 1 / 1"',
            generated_files[feature_index],
        )
        self.assertIn("<strong>1 / 1</strong>", generated_files[feature_index])
        self.assertIn("```mermaid\nflowchart LR", generated_files[feature_index])
        self.assertIn('group0["Delivery<br/>(60%)"]', generated_files[feature_index])
        self.assertIn(
            "style group0 fill:#fff129,color:#1a1a1a", generated_files[feature_index]
        )
        self.assertIn(
            'click group0 "delivery/" "Open Delivery"', generated_files[feature_index]
        )
        self.assertNotIn(
            "[Delivery](delivery/index.md)", generated_files[feature_index]
        )
        self.assertIn('process0["Delivery<br/>(60%)"]', generated_files[group_index])
        self.assertIn(
            "style process0 fill:#fff129,color:#1a1a1a", generated_files[group_index]
        )
        self.assertIn(
            'click process0 "#delivery" "Open Delivery"', generated_files[group_index]
        )
        self.assertIn("## Processes", generated_files[group_index])
        self.assertIn("## Related Documents", generated_files[feature_index])
        self.assertIn(
            "<summary>&#128193; Supporting Material (1 file)</summary>",
            generated_files[feature_index],
        )
        self.assertTrue(
            any(uri.endswith("/render/index.md") for uri in generated_files)
        )
        self.assertNotIn("Features/Pending Feature/index.md", generated_files)

    def test_template_mismatch_warnings_identify_invalid_feature_metadata(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            feature_dir = Path(temporary_directory)
            (feature_dir / "overview.yaml").write_text("{}\n", encoding="utf-8")
            with (
                patch.object(features_section, "REPO_ROOT", feature_dir.parent),
                self.assertLogs("mkdocs.hooks", "WARNING") as captured,
            ):
                features_section._warn_template_mismatches(
                    "Features",
                    feature_dir,
                    {
                        "unknown": "value",
                        "internal": "override",
                        "processes": {
                            "unknown_process": {},
                            "known": "not a mapping",
                        },
                    },
                    {
                        "required_field": SimpleNamespace(
                            state="required", default=None
                        ),
                        "internal": SimpleNamespace(
                            state="template", default="internal"
                        ),
                    },
                    {"known": {}},
                )

        warnings = "\n".join(captured.output)
        self.assertIn("unknown top-level key 'unknown'", warnings)
        self.assertIn("unknown top-level key 'internal'", warnings)
        self.assertIn(
            "missing template-defined top-level key 'required_field'", warnings
        )
        self.assertIn("unknown process 'unknown_process'", warnings)
        self.assertIn("process 'known' must be a mapping", warnings)

    def test_template_mismatch_warnings_identify_invalid_process_fields(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            feature_dir = Path(temporary_directory)
            (feature_dir / "overview.yaml").write_text("{}\n", encoding="utf-8")
            with (
                patch.object(features_section, "REPO_ROOT", feature_dir.parent),
                self.assertLogs("mkdocs.hooks", "WARNING") as captured,
            ):
                features_section._warn_template_mismatches(
                    "Features",
                    feature_dir,
                    {
                        "processes": {
                            "known": {"template": "override", "extra": 1, "sources": 2}
                        }
                    },
                    {},
                    {
                        "known": {
                            "template": SimpleNamespace(state="template"),
                        }
                    },
                )

        warnings = "\n".join(captured.output)
        self.assertIn("cannot override template-only field 'template'", warnings)
        self.assertIn("contains unknown field 'extra'", warnings)
        self.assertIn("field 'sources' must be a string or list", warnings)


if __name__ == "__main__":
    unittest.main()
