from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import validate_assembled_content  # noqa: E402
from content_assembly import ASSEMBLY_STATUS_ENV  # noqa: E402


class ValidateAssembledContentTests(unittest.TestCase):
    def test_runs_shared_validation_against_complete_linked_assembly(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dashboard_root = root / "modul-dashboard"
            dashboard_root.mkdir()
            docs_directory = root / "assembled-docs"
            checkout_parent = root / "sources"
            manifest_output = root / "manifest.json"
            sources = [object()]
            checkouts = {"documents": root / "Modul-Documents"}
            result = type("Result", (), {"returncode": 0})()

            with (
                patch.object(
                    validate_assembled_content,
                    "load_content_sources",
                    return_value=sources,
                ) as load_sources,
                patch.object(
                    validate_assembled_content,
                    "discover_sibling_checkouts",
                    return_value=checkouts,
                ) as discover_checkouts,
                patch.object(
                    validate_assembled_content,
                    "assemble_preview_workspace",
                ) as assemble,
                patch.object(
                    validate_assembled_content,
                    "write_assembly_status",
                ) as write_status,
                patch.object(
                    validate_assembled_content.subprocess,
                    "run",
                    return_value=result,
                ) as run,
                patch.dict(
                    validate_assembled_content.os.environ,
                    {
                        "LOCAL_PREVIEW_NOTICE": "Partial preview.",
                        ASSEMBLY_STATUS_ENV: "partial-status.json",
                        "MODUL_DASHBOARD_SITE_DIR": "preview-site",
                    },
                ),
            ):
                return_code = validate_assembled_content.run_assembled_validation(
                    dashboard_root,
                    docs_directory,
                    checkout_parent,
                    manifest_output,
                    "AS-IO/modul-dashboard",
                    "refs/heads/main",
                )

        self.assertEqual(0, return_code)
        load_sources.assert_called_once_with(dashboard_root / "repositories.yaml")
        discover_checkouts.assert_called_once_with(sources, checkout_parent)
        assemble.assert_called_once_with(
            dashboard_root,
            docs_directory,
            sources,
            checkouts,
            require_all=True,
            manifest_output=manifest_output,
            dashboard_repository="AS-IO/modul-dashboard",
            dashboard_ref="refs/heads/main",
        )
        write_status.assert_called_once_with(
            docs_directory.parent / "content-assembly-status.json",
            sources,
            [],
            checkouts,
        )
        command = run.call_args.args[0]
        self.assertEqual([sys.executable, "scripts/validate.py"], command)
        self.assertEqual(dashboard_root, run.call_args.kwargs["cwd"])
        environment = run.call_args.kwargs["env"]
        self.assertEqual(str(docs_directory), environment["MODUL_DASHBOARD_DOCS_DIR"])
        self.assertNotIn("LOCAL_PREVIEW_NOTICE", environment)
        self.assertEqual(
            str(docs_directory.parent / "content-assembly-status.json"),
            environment[ASSEMBLY_STATUS_ENV],
        )
        self.assertNotIn("MODUL_DASHBOARD_SITE_DIR", environment)

    def test_returns_shared_validator_status(self) -> None:
        result = type("Result", (), {"returncode": 7})()
        with (
            patch.object(validate_assembled_content, "load_content_sources", return_value=[]),
            patch.object(
                validate_assembled_content,
                "discover_sibling_checkouts",
                return_value={},
            ),
            patch.object(validate_assembled_content, "assemble_preview_workspace"),
            patch.object(validate_assembled_content, "write_assembly_status"),
            patch.object(
                validate_assembled_content.subprocess,
                "run",
                return_value=result,
            ),
        ):
            return_code = validate_assembled_content.run_assembled_validation(
                Path("dashboard"),
                Path("docs"),
                Path("checkouts"),
                Path("manifest.json"),
                "",
                "",
            )

        self.assertEqual(7, return_code)


if __name__ == "__main__":
    unittest.main()