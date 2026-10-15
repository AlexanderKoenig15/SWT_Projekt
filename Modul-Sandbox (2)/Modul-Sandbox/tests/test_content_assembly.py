from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import unittest
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from content_assembly import (  # noqa: E402
    ContentSource,
    assemble_preview_workspace,
    build_deployment_manifest,
    build_docs_directory_url,
    build_docs_source_display_path,
    build_docs_source_url,
    discover_sibling_checkouts,
    load_repository_registry,
    load_content_sources,
    load_missing_mount_paths,
    load_shadowed_feature_mounts,
    resolve_content_source,
    workspace_repositories,
    write_assembly_status,
)


class ContentAssemblyTests(unittest.TestCase):
    def _write_dashboard(self, root: Path) -> None:
        (root / "docs" / "Home").mkdir(parents=True)
        (root / "docs" / "Features" / "000_TEMPLATES").mkdir(parents=True)
        (root / "scripts").mkdir()
        (root / "theme").mkdir()
        (root / "mkdocs.yml").write_text("site_name: Test\n", encoding="utf-8")
        (root / "docs" / "Home" / "index.md").write_text("# Home\n", encoding="utf-8")
        (root / "docs" / "Features" / "000_TEMPLATES" / "overview.yaml").write_text(
            "schema: test\n", encoding="utf-8"
        )
        (root / "docs" / "categories.yaml").write_text(
            "categories:\n"
            "  - title: Home\n"
            "    path: Home\n"
            "  - title: Features\n"
            "    path: Features\n"
            "  - title: Hardware\n"
            "    path: Hardware\n",
            encoding="utf-8",
        )

    def test_load_rejects_duplicate_mount_paths(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            registry_file = Path(temporary_directory) / "repositories.yaml"
            registry_file.write_text(
                "version: 2\n"
                "repositories:\n"
                "  - id: first\n"
                "    repository: ORG/modul-first\n"
                "    workspace: optional\n"
                "    mount_path: Features/First\n"
                "  - id: second\n"
                "    repository: ORG/modul-second\n"
                "    workspace: optional\n"
                "    mount_path: Features/First\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Duplicate content mount path"):
                load_content_sources(registry_file)

    def test_load_allows_nested_mount_paths(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            registry_file = Path(temporary_directory) / "repositories.yaml"
            registry_file.write_text(
                "version: 2\n"
                "repositories:\n"
                "  - id: documents\n"
                "    repository: ORG/modul-documents\n"
                "    workspace: required\n"
                "    mount_path: .\n"
                "  - id: category\n"
                "    repository: ORG/modul-features\n"
                "    workspace: optional\n"
                "    mount_path: Features\n"
                "  - id: feature\n"
                "    repository: ORG/modul-seclog\n"
                "    workspace: optional\n"
                "    mount_path: Features/SecLog\n",
                encoding="utf-8",
            )

            sources = load_content_sources(registry_file)

        self.assertEqual(
            [".", "Features", "Features/SecLog"],
            [source.mount_path.as_posix() for source in sources],
        )

    def test_load_separates_workspace_only_repositories_from_published_sources(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary_directory:
            registry_file = Path(temporary_directory) / "repositories.yaml"
            registry_file.write_text(
                "version: 2\n"
                "repositories:\n"
                "  - id: documents\n"
                "    repository: ORG/modul-documents\n"
                "    workspace: required\n"
                "    mount_path: .\n"
                "  - id: agents\n"
                "    repository: ORG/modul-agents\n"
                "    workspace: required\n"
                "  - id: tools\n"
                "    repository: ORG/modul-tools\n"
                "    workspace: optional\n",
                encoding="utf-8",
            )

            repositories = load_repository_registry(registry_file)
            sources = load_content_sources(registry_file)

        self.assertEqual(["documents"], [source.identifier for source in sources])
        self.assertEqual(
            ["documents", "agents", "tools"],
            [repository.identifier for repository in workspace_repositories(repositories)],
        )

    def test_load_rejects_empty_mount_path(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            registry_file = Path(temporary_directory) / "repositories.yaml"
            registry_file.write_text(
                "version: 2\n"
                "repositories:\n"
                "  - id: documents\n"
                "    repository: ORG/modul-documents\n"
                "    workspace: required\n"
                "    mount_path: ''\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "mount_path"):
                load_repository_registry(registry_file)

    def test_source_urls_follow_the_most_specific_registered_mount(self) -> None:
        sources = [
            ContentSource("documents", "AS-IO/Modul-Documents", Path(".")),
            ContentSource("hardware", "AS-IO/Modul-Hardware", Path("Hardware")),
            ContentSource("testcases", "AS-IO/Modul-TestCases", Path("TestCases")),
            ContentSource(
                "seclog",
                "AS-IO/Modul-Feature-SecLog",
                Path("Features/Logging of Security Events"),
            ),
        ]

        self.assertEqual(
            "https://github.siemens.cloud/AS-IO/Modul-Documents/blob/main/"
            "Features/Secure%20Boot/overview.yaml",
            build_docs_source_url("Features/Secure Boot/overview.yaml", sources),
        )
        self.assertEqual(
            "https://github.siemens.cloud/AS-IO/Modul-Hardware/blob/main/"
            "ASIC/overview.yaml",
            build_docs_source_url("Hardware/ASIC/overview.yaml", sources),
        )
        self.assertEqual(
            "https://github.siemens.cloud/AS-IO/Modul-TestCases/blob/main/"
            "IntegrationTests/feature/case.md",
            build_docs_source_url(
                "TestCases/IntegrationTests/feature/case.md", sources
            ),
        )
        self.assertEqual(
            "https://github.siemens.cloud/AS-IO/Modul-Feature-SecLog/blob/main/"
            "Testing/guide.md",
            build_docs_source_url(
                "Features/Logging of Security Events/Testing/guide.md", sources
            ),
        )
        self.assertEqual(
            "https://github.siemens.cloud/AS-IO/Modul-Feature-SecLog/tree/main/",
            build_docs_directory_url("Features/Logging of Security Events", sources),
        )
        self.assertEqual(
            "https://github.siemens.cloud/AS-IO/Modul-Dashboard/blob/main/"
            "docs/Platform/guide.md",
            build_docs_source_url("Platform/guide.md", []),
        )
        self.assertEqual(
            "Features/Secure Boot/overview.yaml",
            build_docs_source_display_path(
                "Features/Secure Boot/overview.yaml", sources
            ),
        )
        self.assertEqual(
            "Testing/guide.md",
            build_docs_source_display_path(
                "Features/Logging of Security Events/Testing/guide.md", sources
            ),
        )
        self.assertEqual(
            "docs/Platform/guide.md",
            build_docs_source_display_path("Platform/guide.md", []),
        )

    def test_assembly_links_available_content_and_masks_missing_mount(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dashboard_root = root / "modul-dashboard"
            self._write_dashboard(dashboard_root)
            seclog_checkout = root / "modul-seclog"
            (seclog_checkout / "documents").mkdir(parents=True)
            (seclog_checkout / ".git").mkdir()
            (seclog_checkout / "overview.yaml").write_text(
                "name: SecLog\n", encoding="utf-8"
            )
            (seclog_checkout / "documents" / "index.md").write_text(
                "# SecLog\n", encoding="utf-8"
            )
            sources = [
                ContentSource(
                    "seclog",
                    "ORG/modul-seclog",
                    Path("Features/Logging of Security Events"),
                ),
                ContentSource(
                    "hardware",
                    "ORG/modul-hardware",
                    Path("Hardware"),
                ),
            ]

            output_root = root / "preview"
            omitted_categories = assemble_preview_workspace(
                dashboard_root,
                output_root,
                sources,
                {"seclog": seclog_checkout},
            )

            self.assertEqual(["hardware"], omitted_categories)
            self.assertTrue(
                (
                    output_root
                    / "Features"
                    / "Logging of Security Events"
                    / "documents"
                    / "index.md"
                ).is_file()
            )
            source_file = seclog_checkout / "overview.yaml"
            source_file.write_text("name: Updated SecLog\n", encoding="utf-8")
            self.assertEqual(
                "name: Updated SecLog\n",
                (
                    output_root
                    / "Features"
                    / "Logging of Security Events"
                    / "overview.yaml"
                ).read_text(encoding="utf-8"),
            )
            self.assertFalse((output_root / "Hardware").exists())

    def test_assembly_links_root_content_and_nested_mount_without_collision(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dashboard_root = root / "modul-dashboard"
            self._write_dashboard(dashboard_root)
            documents_checkout = root / "Modul-Documents"
            (documents_checkout / "Features" / "Secure Boot").mkdir(parents=True)
            (documents_checkout / "categories.yaml").write_text(
                "categories: []\n", encoding="utf-8"
            )
            (documents_checkout / "Features" / "Secure Boot" / "index.md").write_text(
                "# Secure Boot\n", encoding="utf-8"
            )
            seclog_checkout = root / "Modul-Feature-SecLog"
            seclog_checkout.mkdir()
            (seclog_checkout / "index.md").write_text("# SecLog\n", encoding="utf-8")
            sources = [
                ContentSource(
                    "documents",
                    "ORG/Modul-Documents",
                    Path("."),
                ),
                ContentSource(
                    "seclog",
                    "ORG/Modul-Feature-SecLog",
                    Path("Features/Logging of Security Events"),
                ),
            ]

            output_root = root / "virtual-docs"
            assemble_preview_workspace(
                dashboard_root,
                output_root,
                sources,
                {"documents": documents_checkout, "seclog": seclog_checkout},
            )

            self.assertEqual(
                "# SecLog\n",
                (
                    output_root / "Features" / "Logging of Security Events" / "index.md"
                ).read_text(encoding="utf-8"),
            )
            source_file = documents_checkout / "Features" / "Secure Boot" / "index.md"
            source_file.write_text("# Updated Secure Boot\n", encoding="utf-8")
            self.assertEqual(
                "# Updated Secure Boot\n",
                (output_root / "Features" / "Secure Boot" / "index.md").read_text(
                    encoding="utf-8"
                ),
            )

    def test_assembly_excludes_git_metadata_from_content_mounts(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dashboard_root = root / "modul-dashboard"
            self._write_dashboard(dashboard_root)
            documents_checkout = root / "Modul-Documents"
            (documents_checkout / ".git").mkdir(parents=True)
            (documents_checkout / ".git" / "COMMIT_EDITMSG").write_text(
                "internal\n", encoding="utf-8"
            )
            (documents_checkout / "Home").mkdir()
            source_file = documents_checkout / "Home" / "index.md"
            source_file.write_text("# Home\n", encoding="utf-8")
            sources = [ContentSource("documents", "ORG/Modul-Documents", Path("."))]

            output_root = root / "virtual-docs"
            assemble_preview_workspace(
                dashboard_root,
                output_root,
                sources,
                {"documents": documents_checkout},
            )

            self.assertFalse((output_root / ".git").exists())
            self.assertEqual(
                "# Home\n",
                (output_root / "Home" / "index.md").read_text(encoding="utf-8"),
            )

    def test_assembly_uses_documents_for_direct_feature_mount_until_removed(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dashboard_root = root / "modul-dashboard"
            self._write_dashboard(dashboard_root)
            documents_checkout = root / "Modul-Documents"
            stale_override_file = (
                documents_checkout
                / "Features"
                / "Logging of Security Events"
                / "old.md"
            )
            stale_override_file.parent.mkdir(parents=True)
            stale_override_file.write_text("old\n", encoding="utf-8")
            feature_checkout = root / "Modul-Feature-SecLog"
            feature_checkout.mkdir()
            (feature_checkout / "old.md").write_text("child\n", encoding="utf-8")
            sources = [
                ContentSource(
                    "documents",
                    "ORG/Modul-Documents",
                    Path("."),
                ),
                ContentSource(
                    "seclog",
                    "ORG/Modul-Feature-SecLog",
                    Path("Features/Logging of Security Events"),
                ),
            ]
            output_root = root / "virtual-docs"
            checkouts = {
                "documents": documents_checkout,
                "seclog": feature_checkout,
            }
            assemble_preview_workspace(
                dashboard_root, output_root, sources, checkouts
            )
            feature_docs = output_root / "Features" / "Logging of Security Events"
            self.assertEqual("old\n", (feature_docs / "old.md").read_text(encoding="utf-8"))

            status_file = root / "assembly-status.json"
            write_assembly_status(status_file, sources, [], checkouts)
            with patch.dict(
                os.environ,
                {"MODUL_DASHBOARD_ASSEMBLY_STATUS_FILE": str(status_file)},
            ):
                self.assertEqual(
                    "https://github.siemens.cloud/ORG/Modul-Documents/blob/main/"
                    "Features/Logging%20of%20Security%20Events/old.md",
                    build_docs_source_url(
                        "Features/Logging of Security Events/old.md", sources
                    ),
                )
                self.assertEqual(
                    "ORG/Modul-Documents",
                    resolve_content_source(
                        "Features/Logging of Security Events/old.md", sources
                    ).repository,
                )
                self.assertIn(
                    PurePosixPath("Features/Logging of Security Events"),
                    load_shadowed_feature_mounts(),
                )

            shutil.rmtree(documents_checkout / "Features" / "Logging of Security Events")
            assemble_preview_workspace(dashboard_root, output_root, sources, checkouts)
            self.assertEqual(
                "child\n",
                (
                    output_root
                    / "Features"
                    / "Logging of Security Events"
                    / "old.md"
                ).read_text(encoding="utf-8"),
            )

    def test_shadowed_feature_assembly_status_marks_the_pages_source(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            documents_checkout = root / "Modul-Documents"
            legacy_feature = documents_checkout / "Features" / "Legacy Feature"
            legacy_feature.mkdir(parents=True)
            (legacy_feature / "index.md").write_text(
                "# Legacy feature\n", encoding="utf-8"
            )
            child_checkout = root / "Modul-Feature-New"
            child_checkout.mkdir()
            (child_checkout / "overview.yaml").write_text(
                "feature_name: New Feature\n", encoding="utf-8"
            )
            sources = [
                ContentSource("documents", "ORG/Modul-Documents", Path(".")),
                ContentSource(
                    "new-feature",
                    "ORG/Modul-Feature-New",
                    Path("Features/Legacy Feature"),
                ),
            ]
            status_file = root / "content-assembly-status.json"

            write_assembly_status(
                status_file,
                sources,
                [],
                {"documents": documents_checkout, "new-feature": child_checkout},
            )

            status = json.loads(status_file.read_text(encoding="utf-8"))
            self.assertEqual(
                [
                    {
                        "id": "new-feature",
                        "mount_path": "Features/Legacy Feature",
                        "repository": "ORG/Modul-Feature-New",
                        "effective_source_id": "documents",
                    }
                ],
                status["shadowed_sources"],
            )

    def test_shadowed_missing_child_keeps_effective_path_available(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dashboard_root = root / "modul-dashboard"
            self._write_dashboard(dashboard_root)
            documents_checkout = root / "Modul-Documents"
            legacy_file = (
                documents_checkout
                / "Features"
                / "Pending Feature"
                / "overview.yaml"
            )
            legacy_file.parent.mkdir(parents=True)
            legacy_file.write_text("feature_name: Legacy\n", encoding="utf-8")
            sources = [
                ContentSource("documents", "ORG/Modul-Documents", Path(".")),
                ContentSource(
                    "pending",
                    "ORG/Modul-Feature-Pending",
                    Path("Features/Pending Feature"),
                ),
            ]
            checkouts = {"documents": documents_checkout}
            output_root = root / "virtual-docs"
            missing = assemble_preview_workspace(
                dashboard_root, output_root, sources, checkouts
            )
            self.assertEqual(["pending"], missing)
            self.assertTrue(
                (output_root / "Features" / "Pending Feature" / "overview.yaml").is_file()
            )

            status_file = root / "assembly-status.json"
            write_assembly_status(status_file, sources, missing, checkouts)
            status = json.loads(status_file.read_text(encoding="utf-8"))
            self.assertFalse(status["complete"])
            self.assertEqual(["pending"], status["missing_source_ids"])
            self.assertEqual([], status["missing_mount_paths"])
            with patch.dict(
                os.environ,
                {"MODUL_DASHBOARD_ASSEMBLY_STATUS_FILE": str(status_file)},
            ):
                self.assertEqual(set(), load_missing_mount_paths())

            with self.assertRaisesRegex(ValueError, "required but its checkout"):
                assemble_preview_workspace(
                    dashboard_root,
                    root / "strict-docs",
                    sources,
                    checkouts,
                    require_all=True,
                )

    def test_non_feature_and_deeper_feature_collisions_remain_errors(self) -> None:
        collision_cases = (
            ("Hardware/ASIC", "Hardware/ASIC"),
            ("Features/Parent/Child", "Features/Parent/Child"),
        )
        for mount_path, relative_path in collision_cases:
            with self.subTest(mount_path=mount_path), TemporaryDirectory() as temp:
                root = Path(temp)
                dashboard_root = root / "modul-dashboard"
                self._write_dashboard(dashboard_root)
                documents_checkout = root / "Modul-Documents"
                collision_dir = documents_checkout.joinpath(*relative_path.split("/"))
                collision_dir.mkdir(parents=True)
                sources = [
                    ContentSource("documents", "ORG/Modul-Documents", Path(".")),
                    ContentSource(
                        "nested", "ORG/Modul-Nested", Path(mount_path)
                    ),
                ]
                with self.assertRaisesRegex(ValueError, "reserved for nested source"):
                    assemble_preview_workspace(
                        dashboard_root,
                        root / "virtual-docs",
                        sources,
                        {"documents": documents_checkout},
                    )

    def test_shadowed_feature_rejects_registered_descendant_mount(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dashboard_root = root / "modul-dashboard"
            self._write_dashboard(dashboard_root)
            documents_checkout = root / "Modul-Documents"
            (documents_checkout / "Features" / "Legacy Feature").mkdir(
                parents=True
            )
            sources = [
                ContentSource("documents", "ORG/Modul-Documents", Path(".")),
                ContentSource(
                    "feature",
                    "ORG/Modul-Feature",
                    Path("Features/Legacy Feature"),
                ),
                ContentSource(
                    "descendant",
                    "ORG/Modul-Feature-Docs",
                    Path("Features/Legacy Feature/Docs"),
                ),
            ]

            with self.assertRaisesRegex(ValueError, "nested below shadowed Feature"):
                assemble_preview_workspace(
                    dashboard_root,
                    root / "virtual-docs",
                    sources,
                    {"documents": documents_checkout},
                )

    def test_assembly_rejects_nested_mount_file_collision(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dashboard_root = root / "modul-dashboard"
            self._write_dashboard(dashboard_root)
            documents_checkout = root / "Modul-Documents"
            collision_file = (
                documents_checkout / "Features" / "Logging of Security Events"
            )
            collision_file.parent.mkdir(parents=True)
            collision_file.write_text("old\n", encoding="utf-8")
            sources = [
                ContentSource(
                    "documents",
                    "ORG/Modul-Documents",
                    Path("."),
                ),
                ContentSource(
                    "seclog",
                    "ORG/Modul-Feature-SecLog",
                    Path("Features/Logging of Security Events"),
                ),
            ]

            with self.assertRaisesRegex(
                ValueError, "reserved for nested source 'seclog'"
            ):
                assemble_preview_workspace(
                    dashboard_root,
                    root / "virtual-docs",
                    sources,
                    {"documents": documents_checkout},
                )

    def test_assembly_replaces_existing_root_link(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dashboard_root = root / "modul-dashboard"
            self._write_dashboard(dashboard_root)
            output_root = root / "virtual-docs"

            assemble_preview_workspace(dashboard_root, output_root, [], {})
            assemble_preview_workspace(dashboard_root, output_root, [], {})

            self.assertEqual(
                "# Home\n",
                (output_root / "Home" / "index.md").read_text(encoding="utf-8"),
            )

    def test_assembly_replaces_broken_root_link_after_content_moves(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dashboard_root = root / "modul-dashboard"
            self._write_dashboard(dashboard_root)
            output_root = root / "virtual-docs"

            assemble_preview_workspace(dashboard_root, output_root, [], {})
            shutil.rmtree(dashboard_root / "docs")
            documents_checkout = root / "Modul-Documents"
            documents_checkout.mkdir()
            (documents_checkout / "Home").mkdir()
            (documents_checkout / "Home" / "index.md").write_text(
                "# Migrated Home\n", encoding="utf-8"
            )
            sources = [
                ContentSource(
                    "documents",
                    "ORG/Modul-Documents",
                    Path("."),
                )
            ]

            assemble_preview_workspace(
                dashboard_root,
                output_root,
                sources,
                {"documents": documents_checkout},
            )

            self.assertEqual(
                "# Migrated Home\n",
                (output_root / "Home" / "index.md").read_text(encoding="utf-8"),
            )

    def test_sibling_checkout_discovery_uses_repository_name(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "modul-seclog").mkdir()
            sources = [
                ContentSource(
                    "seclog",
                    "ORG/modul-seclog",
                    Path("Features/SecLog"),
                )
            ]

            checkouts = discover_sibling_checkouts(sources, root)

        self.assertEqual({"seclog": root / "modul-seclog"}, checkouts)

    def test_assembly_can_require_all_registered_sources(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dashboard_root = root / "modul-dashboard"
            self._write_dashboard(dashboard_root)
            sources = [
                ContentSource(
                    "seclog",
                    "ORG/modul-seclog",
                    Path("Features/SecLog"),
                )
            ]

            with self.assertRaisesRegex(ValueError, "required but its checkout"):
                assemble_preview_workspace(
                    dashboard_root,
                    root / "preview",
                    sources,
                    {},
                    require_all=True,
                )

    def test_assembly_status_lists_only_missing_source_mounts(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            status_file = Path(temporary_directory) / "assembly-status.json"
            sources = [
                ContentSource("available", "ORG/available", Path("Available")),
                ContentSource("missing", "ORG/missing", Path("Missing/Section")),
            ]

            write_assembly_status(status_file, sources, ["missing"])

            self.assertEqual(
                {
                    "complete": False,
                    "missing_mount_paths": ["Missing/Section"],
                    "missing_source_ids": ["missing"],
                    "shadowed_sources": [],
                    "version": 1,
                },
                json.loads(status_file.read_text(encoding="utf-8")),
            )

            write_assembly_status(status_file, sources, [])

            self.assertEqual(
                {
                    "complete": True,
                    "missing_mount_paths": [],
                    "missing_source_ids": [],
                    "shadowed_sources": [],
                    "version": 1,
                },
                json.loads(status_file.read_text(encoding="utf-8")),
            )

    def test_assembly_requires_a_registered_root_content_source(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dashboard_root = root / "modul-dashboard"
            self._write_dashboard(dashboard_root)
            sources = [
                ContentSource(
                    "documents",
                    "ORG/Modul-Documents",
                    Path("."),
                )
            ]

            with self.assertRaisesRegex(ValueError, "Root content source 'documents'"):
                assemble_preview_workspace(
                    dashboard_root,
                    root / "preview",
                    sources,
                    {},
                )

    def test_deployment_manifest_records_revisions_and_registry_digest(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dashboard_root = root / "modul-dashboard"
            dashboard_root.mkdir()
            registry_file = dashboard_root / "repositories.yaml"
            registry_file.write_text(
                "version: 2\n"
                "repositories:\n"
                "  - id: documents\n"
                "    repository: ORG/modul-documents\n"
                "    workspace: required\n"
                "    mount_path: .\n",
                encoding="utf-8",
            )
            registry_digest = hashlib.sha256(registry_file.read_bytes()).hexdigest()
            source_checkout = root / "modul-seclog"
            source_checkout.mkdir()
            source = ContentSource(
                "seclog",
                "ORG/modul-seclog",
                Path("Features/SecLog"),
            )

            with patch(
                "content_assembly._git_revision",
                side_effect=["dashboard-sha", "source-sha"],
            ):
                manifest = build_deployment_manifest(
                    dashboard_root,
                    registry_file,
                    [source],
                    {"seclog": source_checkout},
                    "ORG/modul-dashboard",
                    "refs/heads/main",
                )

        self.assertEqual("dashboard-sha", manifest["dashboard"]["revision"])
        self.assertEqual("ORG/modul-dashboard", manifest["dashboard"]["repository"])
        self.assertEqual("refs/heads/main", manifest["dashboard"]["ref"])
        self.assertEqual("source-sha", manifest["sources"][0]["revision"])
        self.assertEqual(3, manifest["version"])
        self.assertNotIn("category_path", manifest["sources"][0])
        self.assertEqual(registry_digest, manifest["registry"]["sha256"])

    def test_deployment_manifest_records_shadowed_feature_source(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dashboard_root = root / "modul-dashboard"
            dashboard_root.mkdir()
            registry_file = dashboard_root / "repositories.yaml"
            registry_file.write_text("version: 2\nrepositories: []\n", encoding="utf-8")
            documents_checkout = root / "Modul-Documents"
            (documents_checkout / "Features" / "Example").mkdir(parents=True)
            feature_checkout = root / "Modul-Feature-Example"
            feature_checkout.mkdir()
            sources = [
                ContentSource("documents", "ORG/Modul-Documents", Path(".")),
                ContentSource(
                    "example",
                    "ORG/Modul-Feature-Example",
                    Path("Features/Example"),
                ),
            ]
            with patch(
                "content_assembly._git_revision",
                side_effect=["dashboard-sha", "documents-sha", "feature-sha"],
            ):
                manifest = build_deployment_manifest(
                    dashboard_root,
                    registry_file,
                    sources,
                    {"documents": documents_checkout, "example": feature_checkout},
                )

        self.assertEqual(3, manifest["version"])
        self.assertEqual(
            [
                {
                    "id": "example",
                    "repository": "ORG/Modul-Feature-Example",
                    "mount_path": "Features/Example",
                    "effective_source_id": "documents",
                }
            ],
            manifest["shadowed_sources"],
        )
        self.assertEqual(
            ["documents-sha", "feature-sha"],
            [source["revision"] for source in manifest["sources"]],
        )


if __name__ == "__main__":
    unittest.main()
