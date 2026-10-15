from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import validate  # noqa: E402


class ValidateScriptTests(unittest.TestCase):
    def test_registry_validation_reports_invalid_registry(self) -> None:
        with patch.object(
            validate, "load_content_sources", side_effect=ValueError("invalid mount")
        ):
            self.assertEqual(1, validate._validate_content_sources())

    def test_main_stops_before_ruff_when_registry_is_invalid(self) -> None:
        with (
            patch.object(validate, "_validate_content_sources", return_value=1),
            patch.object(validate, "_run_ruff") as run_ruff,
        ):
            self.assertEqual(1, validate.main())

        run_ruff.assert_not_called()

    def test_ruff_runs_format_and_lint_even_if_format_fails(self) -> None:
        with patch.object(validate, "_run", side_effect=[1, 0]) as run:
            self.assertEqual(1, validate._run_ruff())

        self.assertEqual(2, run.call_count)
        self.assertIn("format", run.call_args_list[0].args[0])
        self.assertIn("check", run.call_args_list[1].args[0])

    def test_run_uses_repository_root_and_returns_subprocess_status(self) -> None:
        result = type("Result", (), {"returncode": 7})()
        command = [sys.executable, "-m", "tool", "argument"]

        with (
            patch("builtins.print"),
            patch.object(validate.subprocess, "run", return_value=result) as run,
        ):
            self.assertEqual(7, validate._run(command))

        run.assert_called_once_with(command, cwd=validate.REPO_ROOT, check=False)

    def test_main_stops_before_tests_when_ruff_fails(self) -> None:
        with (
            patch.object(validate, "_run_ruff", return_value=1),
            patch.object(validate, "_run_tests") as run_tests,
        ):
            self.assertEqual(1, validate.main())

        run_tests.assert_not_called()

    def test_main_stops_before_build_when_tests_fail(self) -> None:
        with (
            patch.object(validate, "_run_ruff", return_value=0),
            patch.object(validate, "_run_tests", return_value=1),
            patch.object(validate, "_run_coverage_report") as run_coverage_report,
            patch.object(validate, "_run_build") as run_build,
        ):
            self.assertEqual(1, validate.main())

        run_coverage_report.assert_not_called()
        run_build.assert_not_called()

    def test_main_stops_before_build_when_coverage_is_below_threshold(self) -> None:
        with (
            patch.object(validate, "_run_ruff", return_value=0),
            patch.object(validate, "_run_tests", return_value=0),
            patch.object(validate, "_run_coverage_report", return_value=1),
            patch.object(validate, "_run_build") as run_build,
        ):
            self.assertEqual(1, validate.main())

        run_build.assert_not_called()

    def test_main_runs_build_after_successful_tests_and_coverage(self) -> None:
        with (
            patch.object(validate, "_run_ruff", return_value=0),
            patch.object(validate, "_run_tests", return_value=0),
            patch.object(validate, "_run_coverage_report", return_value=0),
            patch.object(validate, "_run_build", return_value=0) as run_build,
        ):
            self.assertEqual(0, validate.main())

        run_build.assert_called_once_with()

    def test_build_assembles_sibling_content_when_docs_root_is_unset(self) -> None:
        sources = [object()]
        checkouts = {"documents": Path("Modul-Documents")}
        with (
            patch.dict(validate.os.environ, {}, clear=True),
            patch.object(validate, "load_content_sources", return_value=sources),
            patch.object(
                validate,
                "discover_sibling_checkouts",
                return_value=checkouts,
            ) as discover_checkouts,
            patch.object(
                validate,
                "assemble_preview_workspace",
                return_value=[],
            ) as assemble,
            patch.object(validate, "write_assembly_status") as write_status,
            patch.object(validate, "_run", return_value=0) as run,
        ):
            self.assertEqual(0, validate._run_build())
            self.assertEqual(
                str(validate.DEFAULT_LOCAL_SITE_DIRECTORY),
                validate.os.environ["MODUL_DASHBOARD_SITE_DIR"],
            )

        discover_checkouts.assert_called_once_with(sources, validate.REPO_ROOT.parent)
        assemble.assert_called_once_with(
            validate.REPO_ROOT,
            validate.DEFAULT_LOCAL_DOCS_DIRECTORY,
            sources,
            checkouts,
        )
        write_status.assert_called_once_with(
            validate.DEFAULT_LOCAL_ASSEMBLY_STATUS_FILE,
            sources,
            [],
            checkouts,
        )
        self.assertEqual(
            [sys.executable, "-m", "mkdocs", "build", "--strict"],
            run.call_args.args[0],
        )

    def test_build_keeps_preassembled_docs_root(self) -> None:
        with (
            patch.dict(
                validate.os.environ,
                {"MODUL_DASHBOARD_DOCS_DIR": "already-assembled"},
                clear=True,
            ),
            patch.object(validate, "assemble_preview_workspace") as assemble,
            patch.object(validate, "_run", return_value=0),
        ):
            self.assertEqual(0, validate._run_build())
            self.assertNotIn("MODUL_DASHBOARD_SITE_DIR", validate.os.environ)

        assemble.assert_not_called()

    def test_build_marks_partial_local_assembly_as_a_preview(self) -> None:
        sources = [object()]
        with (
            patch.dict(validate.os.environ, {}, clear=True),
            patch.object(validate, "load_content_sources", return_value=sources),
            patch.object(validate, "discover_sibling_checkouts", return_value={}),
            patch.object(
                validate,
                "assemble_preview_workspace",
                return_value=["testautomation"],
            ),
            patch.object(validate, "write_assembly_status"),
            patch.object(validate, "_run", return_value=0),
        ):
            self.assertEqual(0, validate._run_build())
            self.assertIn("LOCAL_PREVIEW_NOTICE", validate.os.environ)

    def test_tests_and_coverage_report_use_scripts_threshold(self) -> None:
        with patch.object(validate, "_run", return_value=0) as run:
            self.assertEqual(0, validate._run_tests())
            self.assertEqual(0, validate._run_coverage_report())

        self.assertEqual(
            [
                sys.executable,
                "-m",
                "coverage",
                "run",
                "--source=scripts",
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
            ],
            run.call_args_list[0].args[0],
        )
        self.assertEqual(
            [
                sys.executable,
                "-m",
                "coverage",
                "report",
                "--show-missing",
                f"--fail-under={validate.COVERAGE_THRESHOLD}",
            ],
            run.call_args_list[1].args[0],
        )

    def test_tests_do_not_inherit_local_preview_environment(self) -> None:
        def run_with_clean_environment(command: list[str]) -> int:
            for name in validate.LOCAL_PREVIEW_ENVIRONMENT_VARIABLES:
                self.assertNotIn(name, validate.os.environ)
            return 0

        preview_environment = {
            name: "test-value" for name in validate.LOCAL_PREVIEW_ENVIRONMENT_VARIABLES
        }
        with (
            patch.dict(validate.os.environ, preview_environment),
            patch.object(validate, "_run", side_effect=run_with_clean_environment),
        ):
            self.assertEqual(0, validate._run_tests())
            for name, value in preview_environment.items():
                self.assertEqual(value, validate.os.environ[name])


if __name__ == "__main__":
    unittest.main()