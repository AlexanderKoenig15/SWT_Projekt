from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from workspace_inventory import (  # noqa: E402
    build_workspace_inventory,
    render_text,
)


class WorkspaceInventoryTests(unittest.TestCase):
    def _write_registry(self, root: Path) -> Path:
        registry_file = root / "repositories.yaml"
        registry_file.write_text(
            "version: 2\n"
            "repositories:\n"
            "  - id: documents\n"
            "    repository: ORG/Modul-Documents\n"
            "    workspace: required\n"
            "    mount_path: .\n"
            "    purpose: Shared documentation root\n"
            "  - id: seclog\n"
            "    repository: ORG/Modul-Feature-SecLog\n"
            "    workspace: optional\n"
            "    mount_path: Features/SecLog\n"
            "    purpose: Feature content\n"
            "  - id: tools\n"
            "    repository: ORG/Modul-Tools\n"
            "    workspace: optional\n"
            "    purpose: Conversion tools\n",
            encoding="utf-8",
        )
        return registry_file

    def test_reports_explicitly_visible_and_unavailable_repositories(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            registry_file = self._write_registry(root)
            dashboard = root / "Modul-Dashboard"
            documents = root / "Modul-Documents"
            sibling_seclog = root / "Modul-Feature-SecLog"
            tools = root / "Modul-Tools"
            dashboard.mkdir()
            documents.mkdir()
            sibling_seclog.mkdir()
            tools.mkdir()

            inventory = build_workspace_inventory(
                [dashboard, documents], registry_file
            )

        statuses = {
            repository.identifier: repository.status
            for repository in inventory.repositories
        }
        self.assertEqual("available", statuses["dashboard"])
        self.assertEqual("available", statuses["documents"])
        self.assertEqual(
            "unavailable-in-current-workspace", statuses["seclog"]
        )
        self.assertEqual("unavailable-in-current-workspace", statuses["tools"])
        self.assertEqual((), inventory.unknown_workspace_folders)

    def test_reports_unknown_explicit_folder_without_scanning_siblings(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            registry_file = self._write_registry(root)
            (root / "Modul-Dashboard").mkdir()
            (root / "Modul-Documents").mkdir()
            unrelated = root / "Other-Workspace-Repository"
            unrelated.mkdir()
            (root / "Modul-Feature-SecLog").mkdir()

            inventory = build_workspace_inventory(
                [root / "Modul-Dashboard", root / "Modul-Documents", unrelated],
                registry_file,
            )

        self.assertEqual((str(unrelated.resolve()),), inventory.unknown_workspace_folders)
        seclog = next(
            repository
            for repository in inventory.repositories
            if repository.identifier == "seclog"
        )
        self.assertEqual("unavailable-in-current-workspace", seclog.status)

    def test_observes_partial_categories_and_features(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            registry_file = self._write_registry(root)
            dashboard = root / "Modul-Dashboard"
            documents = root / "Modul-Documents"
            dashboard.mkdir()
            (documents / "Home").mkdir(parents=True)
            (documents / "Features" / "Alpha").mkdir(parents=True)
            (documents / "Features" / "000_TEMPLATES").mkdir()
            (documents / "categories.yaml").write_text(
                "categories:\n"
                "  - title: Home\n"
                "    path: Home\n"
                "  - title: Features\n"
                "    path: Features\n",
                encoding="utf-8",
            )
            (documents / "Features" / "Alpha" / "overview.yaml").write_text(
                "name: Alpha Feature\n", encoding="utf-8"
            )

            inventory = build_workspace_inventory(
                [dashboard, documents], registry_file, include_content=True
            )

        self.assertEqual("partial", inventory.content_scope)
        self.assertEqual(["Home", "Features"], [item.name for item in inventory.categories])
        self.assertEqual(["Alpha"], [item.name for item in inventory.features])
        self.assertTrue(any("partial" in warning for warning in inventory.warnings))

    def test_uses_feature_name_for_a_mounted_feature(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            registry_file = self._write_registry(root)
            dashboard = root / "Modul-Dashboard"
            documents = root / "Modul-Documents"
            seclog = root / "Modul-Feature-SecLog"
            dashboard.mkdir()
            documents.mkdir()
            seclog.mkdir()
            (seclog / "overview.yaml").write_text(
                "feature_name: Alpha Feature\n", encoding="utf-8"
            )

            inventory = build_workspace_inventory(
                [dashboard, documents, seclog], registry_file, include_content=True
            )

        self.assertEqual(["Alpha Feature"], [item.name for item in inventory.features])

    def test_json_shape_and_text_use_stable_plain_language(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            registry_file = self._write_registry(root)
            dashboard = root / "Modul-Dashboard"
            dashboard.mkdir()
            inventory = build_workspace_inventory([dashboard], registry_file)

        document = inventory.to_dict()
        self.assertEqual(2, document["version"])
        self.assertEqual(
            ["dashboard", "documents", "seclog", "tools"],
            [repository["identifier"] for repository in document["repositories"]],
        )
        self.assertEqual(
            ["documents", "seclog", "tools"],
            document["unavailable_repository_ids"],
        )
        self.assertEqual([], document["categories"])
        self.assertEqual([], document["features"])
        self.assertIn("unavailable in current workspace", render_text(inventory))
        json.dumps(document, sort_keys=True)

    def test_content_inventory_distinguishes_feature_fallback_and_shadowed_child(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            registry_file = self._write_registry(root)
            dashboard = root / "Modul-Dashboard"
            documents = root / "Modul-Documents"
            seclog = root / "Modul-Feature-SecLog"
            dashboard.mkdir()
            (documents / "Features" / "SecLog").mkdir(parents=True)
            (documents / "Features" / "SecLog" / "overview.yaml").write_text(
                "feature_name: Legacy SecLog\n", encoding="utf-8"
            )
            seclog.mkdir()
            (seclog / "overview.yaml").write_text(
                "feature_name: New SecLog\n", encoding="utf-8"
            )

            inventory = build_workspace_inventory(
                [dashboard, documents, seclog], registry_file, include_content=True
            )

        statuses = {
            observation.source_id: observation.publication_status
            for observation in inventory.features
        }
        self.assertEqual("fallback-effective", statuses["documents"])
        self.assertEqual("shadowed by Modul-Documents", statuses["seclog"])
        self.assertIn("shadowed by Modul-Documents", render_text(inventory))

    def test_shadowed_inventory_does_not_parse_child_metadata(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            registry_file = self._write_registry(root)
            dashboard = root / "Modul-Dashboard"
            documents = root / "Modul-Documents"
            seclog = root / "Modul-Feature-SecLog"
            dashboard.mkdir()
            (documents / "Features" / "SecLog").mkdir(parents=True)
            seclog.mkdir()
            (seclog / "overview.yaml").write_text(
                "feature_name: [unterminated\n", encoding="utf-8"
            )

            inventory = build_workspace_inventory(
                [dashboard, documents, seclog], registry_file, include_content=True
            )

        shadowed = next(item for item in inventory.features if item.source_id == "seclog")
        self.assertEqual("shadowed by Modul-Documents", shadowed.publication_status)

    def test_invalid_registry_is_reported(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            registry_file = root / "repositories.yaml"
            registry_file.write_text("version: 1\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "version: 2"):
                build_workspace_inventory([root], registry_file)


if __name__ == "__main__":
    unittest.main()
