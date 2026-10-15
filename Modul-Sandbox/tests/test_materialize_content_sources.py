from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import materialize_content_sources  # noqa: E402
from content_assembly import ContentSource  # noqa: E402


class MaterializeContentSourcesTests(unittest.TestCase):
    def test_materializes_main_at_the_resolved_immutable_revision(self) -> None:
        revision = "a" * 40
        source = ContentSource("documents", "AS-IO/Modul-Documents", Path("."))
        commands: list[list[str]] = []

        def run(
            command: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            stdout = ""
            if command[1] == "ls-remote":
                stdout = f"{revision}\trefs/heads/main\n"
            elif command[-2:] == ["rev-parse", "FETCH_HEAD"]:
                stdout = f"{revision}\n"
            return subprocess.CompletedProcess(command, 0, stdout, "")

        with TemporaryDirectory() as temporary_directory:
            checkout_parent = Path(temporary_directory) / "sources"
            with patch.object(
                materialize_content_sources.subprocess, "run", side_effect=run
            ):
                revisions = materialize_content_sources.materialize_content_sources(
                    [source], checkout_parent, "short-lived-token"
                )

        self.assertEqual({"documents": revision}, revisions)
        self.assertIn(
            [
                "git",
                "-C",
                str(checkout_parent / "Modul-Documents"),
                "fetch",
                "--depth=1",
                "origin",
                revision,
            ],
            commands,
        )
        self.assertIn(
            [
                "git",
                "-C",
                str(checkout_parent / "Modul-Documents"),
                "checkout",
                "--detach",
                revision,
            ],
            commands,
        )

    def test_rejects_unknown_or_non_immutable_revision_inputs(self) -> None:
        source = ContentSource("documents", "AS-IO/Modul-Documents", Path("."))
        with self.assertRaisesRegex(ValueError, "unknown content source"):
            materialize_content_sources.materialize_content_sources(
                [source], Path("checkouts"), "token", {"unknown": "a" * 40}
            )
        with self.assertRaisesRegex(ValueError, "40- or 64-character"):
            materialize_content_sources.materialize_content_sources(
                [source], Path("checkouts"), "token", {"documents": "main"}
            )

    def test_parses_multiple_source_revision_inputs(self) -> None:
        first = "a" * 40
        second = "b" * 64

        revisions = materialize_content_sources._parse_revisions(
            [f"documents={first}", f"seclog={second}"]
        )

        self.assertEqual({"documents": first, "seclog": second}, revisions)

    def test_rejects_duplicate_source_revision_inputs(self) -> None:
        revision = "a" * 40
        with self.assertRaisesRegex(ValueError, "Duplicate revision"):
            materialize_content_sources._parse_revisions(
                [f"documents={revision}", f"documents={revision}"]
            )

    def test_requires_a_short_lived_content_token(self) -> None:
        source = ContentSource("documents", "AS-IO/Modul-Documents", Path("."))
        with self.assertRaisesRegex(ValueError, "MODUL_DASHBOARD_CONTENT_TOKEN"):
            materialize_content_sources.materialize_content_sources(
                [source], Path("checkouts"), ""
            )


if __name__ == "__main__":
    unittest.main()
