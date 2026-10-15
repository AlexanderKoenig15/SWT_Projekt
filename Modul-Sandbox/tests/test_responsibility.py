from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from responsibility import (  # noqa: E402
    ResponsibilityOverride,
    ResolvedResponsibility,
    ResolvedRouting,
    load_policy_file,
    merge_responsibility,
    normalize_frontmatter_owner,
    parse_policy_data,
    resolve_responsibility,
)


class ResponsibilityPolicyTests(unittest.TestCase):
    def test_resolves_root_category_and_nested_overrides_field_by_field(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            docs_root = Path(temporary_directory)
            (docs_root / "responsibility.yaml").write_text(
                "responsible: SFO\n"
                "owner: [Root Owner]\n"
                "dashboard_request:\n"
                "  github_project: AS-IO/1\n"
                "  assignees: [dashboard-owner]\n"
                "content_request:\n"
                "  github_project: AS-IO/2\n"
                "  assignees: [content-owner]\n",
                encoding="utf-8",
            )
            (docs_root / "Hardware").mkdir()
            (docs_root / "Hardware" / "responsibility.yaml").write_text(
                "owner: [Hardware Owner]\n"
                "content_request:\n"
                "  assignees: [hardware-content-owner]\n",
                encoding="utf-8",
            )
            (docs_root / "Hardware" / "ASIC").mkdir()
            (docs_root / "Hardware" / "ASIC" / "responsibility.yaml").write_text(
                "responsible: ARC\n"
                "dashboard_request:\n"
                "  github_project: AS-IO/3\n",
                encoding="utf-8",
            )

            resolved = resolve_responsibility(
                docs_root,
                "Hardware/ASIC/architecture.md",
                frontmatter_owner=["Document Owner"],
            )

        self.assertEqual("ARC", resolved.responsible)
        self.assertEqual(("Document Owner",), resolved.owners)
        self.assertEqual("AS-IO/3", resolved.dashboard_request.github_project)
        self.assertEqual(("dashboard-owner",), resolved.dashboard_request.assignees)
        self.assertEqual("AS-IO/2", resolved.content_request.github_project)
        self.assertEqual(("hardware-content-owner",), resolved.content_request.assignees)
        self.assertTrue(resolved.complete)

    def test_empty_document_owner_does_not_override_inherited_owner(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            docs_root = Path(temporary_directory)
            (docs_root / "responsibility.yaml").write_text(
                "owner: Root Owner\n", encoding="utf-8"
            )

            resolved = resolve_responsibility(
                docs_root, "index.md", frontmatter_owner=""
            )

        self.assertEqual(("Root Owner",), resolved.owners)

    def test_missing_values_are_returned_without_failing(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            resolved = resolve_responsibility(Path(temporary_directory), "page.md")

        self.assertIsInstance(resolved, ResolvedResponsibility)
        self.assertFalse(resolved.complete)
        self.assertEqual(
            (
                "responsible",
                "owner",
                "dashboard_request.github_project",
                "dashboard_request.assignees",
                "content_request.github_project",
                "content_request.assignees",
            ),
            resolved.missing_fields,
        )

    def test_policy_rejects_unknown_keys_and_invalid_routes(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown field"):
            parse_policy_data({"paths": {"Hardware": {}}}, "responsibility.yaml")
        with self.assertRaisesRegex(ValueError, "ORG/NUMBER"):
            parse_policy_data(
                {"dashboard_request": {"github_project": "invalid"}},
                "responsibility.yaml",
            )
        with self.assertRaisesRegex(ValueError, "non-empty strings"):
            parse_policy_data({"owner": [""]}, "responsibility.yaml")

    def test_policy_parser_accepts_partial_routes_and_null_overrides(self) -> None:
        override = parse_policy_data(
            {
                "responsible": None,
                "owner": None,
                "dashboard_request": {"assignees": ["dashboard-owner"]},
                "content_request": None,
            }
        )

        self.assertTrue(override.dashboard_request.assignees)
        self.assertIsNone(override.dashboard_request.github_project)
        self.assertTrue(override.content_request.clear)
        self.assertFalse(override.content_request.is_empty)
        self.assertTrue(override.is_empty is False)
        self.assertTrue(override.responsible_clear)
        self.assertTrue(override.owners_clear)

    def test_explicit_null_policy_values_clear_inherited_values(self) -> None:
        current = ResolvedResponsibility(
            responsible="Root Role",
            owners=("Root Owner",),
        )
        override = parse_policy_data(
            {"responsible": None, "owner": None}, "category/responsibility.yaml"
        )

        resolved = merge_responsibility(current, override)

        self.assertIsNone(resolved.responsible)
        self.assertEqual((), resolved.owners)

    def test_explicit_null_route_clears_inherited_route(self) -> None:
        current = ResolvedResponsibility(
            dashboard_request=ResolvedRouting("ORG/1", ("dashboard-owner",)),
        )
        override = parse_policy_data({"dashboard_request": None})

        resolved = merge_responsibility(current, override)

        self.assertIsNone(resolved.dashboard_request.github_project)
        self.assertIsNone(resolved.dashboard_request.assignees)

    def test_normalize_frontmatter_owner_preserves_scalar_and_list_values(self) -> None:
        self.assertEqual(("One Owner",), normalize_frontmatter_owner("One Owner"))
        self.assertEqual(
            ("First Owner", "Second Owner"),
            normalize_frontmatter_owner(["First Owner", "Second Owner"]),
        )
        self.assertIsNone(normalize_frontmatter_owner(None))

    def test_merge_responsibility_does_not_replace_omitted_fields(self) -> None:
        current = ResolvedResponsibility(
            responsible="SFO",
            owners=("Owner",),
        )
        override = ResponsibilityOverride(
            dashboard_request=parse_policy_data(
                {"dashboard_request": {"github_project": "AS-IO/4"}}
            ).dashboard_request
        )

        merged = merge_responsibility(current, override)

        self.assertEqual("SFO", merged.responsible)
        self.assertEqual(("Owner",), merged.owners)
        self.assertEqual("AS-IO/4", merged.dashboard_request.github_project)

    def test_missing_policy_file_is_an_empty_override(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            override = load_policy_file(Path(temporary_directory) / "missing.yaml")

        self.assertTrue(override.is_empty)


if __name__ == "__main__":
    unittest.main()
