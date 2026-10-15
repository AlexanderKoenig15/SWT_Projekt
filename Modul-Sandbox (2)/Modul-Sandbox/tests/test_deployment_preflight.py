from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import deployment_preflight  # noqa: E402
from content_assembly import ContentSource  # noqa: E402


class DeploymentPreflightTests(unittest.TestCase):
    def test_current_manifest_contains_dashboard_registry_and_source_revisions(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            registry_file = root / "repositories.yaml"
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
            source = ContentSource("documents", "ORG/modul-documents", Path("."))
            with (
                patch.object(
                    deployment_preflight, "_git_revision", return_value="dashboard-sha"
                ),
                patch.object(
                    deployment_preflight,
                    "_authenticated_environment",
                    return_value={"auth": "token"},
                ),
                patch.object(
                    deployment_preflight,
                    "_resolve_revision",
                    return_value="source-sha",
                ),
            ):
                manifest = deployment_preflight.build_current_manifest(
                    root,
                    registry_file,
                    [source],
                    "token",
                    "ORG/modul-dashboard",
                    "refs/heads/main",
                )

        self.assertEqual("dashboard-sha", manifest["dashboard"]["revision"])
        self.assertEqual("refs/heads/main", manifest["dashboard"]["ref"])
        self.assertEqual("source-sha", manifest["sources"][0]["revision"])
        self.assertEqual(3, manifest["version"])
        self.assertNotIn("category_path", manifest["sources"][0])
        self.assertEqual(
            registry_digest,
            manifest["registry"]["sha256"],
        )

    def test_deployment_is_skipped_only_for_an_exact_published_manifest(self) -> None:
        current_manifest = {
            "version": 1,
            "dashboard": {
                "repository": "ORG/dashboard",
                "revision": "dashboard-sha",
                "ref": "refs/heads/main",
            },
            "registry": {"path": "repositories.yaml", "sha256": "registry-sha"},
            "sources": [{"id": "documents", "revision": "source-sha"}],
        }

        self.assertFalse(
            deployment_preflight.deployment_required(current_manifest, current_manifest)
        )
        self.assertTrue(
            deployment_preflight.deployment_required(current_manifest, None)
        )
        self.assertTrue(
            deployment_preflight.deployment_required(
                current_manifest,
                {
                    **current_manifest,
                    "dashboard": {
                        **current_manifest["dashboard"],
                        "ref": "refs/heads/feature",
                    },
                },
            )
        )

    def test_derived_shadow_status_does_not_trigger_an_extra_rebuild(self) -> None:
        current_manifest = {
            "version": 3,
            "dashboard": {
                "repository": "ORG/dashboard",
                "revision": "dashboard-sha",
                "ref": "refs/heads/main",
            },
            "registry": {"path": "repositories.yaml", "sha256": "registry-sha"},
            "sources": [
                {"id": "documents", "revision": "documents-sha"},
                {"id": "feature", "revision": "feature-sha"},
            ],
        }
        published_manifest = {
            **current_manifest,
            "shadowed_sources": [
                {
                    "id": "feature",
                    "mount_path": "Features/Example",
                    "effective_source_id": "documents",
                    "repository": "ORG/feature",
                }
            ],
        }

        self.assertFalse(
            deployment_preflight.deployment_required(
                current_manifest, published_manifest
            )
        )
        self.assertTrue(
            deployment_preflight.deployment_required(
                {
                    **current_manifest,
                    "sources": [
                        {"id": "documents", "revision": "new-documents-sha"},
                        {"id": "feature", "revision": "feature-sha"},
                    ],
                },
                published_manifest,
            )
        )
        self.assertTrue(
            deployment_preflight.deployment_required(
                current_manifest,
                {
                    **current_manifest,
                    "sources": [{"id": "documents", "revision": "new"}],
                },
            )
        )


if __name__ == "__main__":
    unittest.main()
