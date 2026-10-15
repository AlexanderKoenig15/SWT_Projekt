from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ISSUE_FORM = (
    REPO_ROOT
    / ".github"
    / "ISSUE_TEMPLATE"
    / "dashboard_repository_provisioning_request.yml"
)


class ProvisioningIssueFormTests(unittest.TestCase):
    def _load_form(self) -> dict[str, Any]:
        data = yaml.safe_load(ISSUE_FORM.read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)
        return data

    def test_provisioning_form_uses_enhancement_and_submitted_checklist_field(self) -> None:
        form = self._load_form()
        self.assertEqual("Enhancement", form["type"])
        self.assertEqual(
            "[Enhancement]: Provision Dashboard repository and Project",
            form["title"],
        )
        self.assertNotIn("Bug", form.get("labels", []))
        checklist = next(
            field for field in form["body"] if field.get("id") == "devops_actions"
        )
        self.assertEqual("textarea", checklist["type"])
        self.assertTrue(checklist["validations"]["required"])
        submitted_value = checklist["attributes"]["value"]
        for expected_text in (
            "1. Complete the definitive repository and Project operation stated above",
            "2. Apply the current repository Permission Matrix",
            "3. Grant `modul-dashboard-assembler`",
            "4. Return the exact repository and Project names/links/numbers",
        ):
            with self.subTest(expected_text=expected_text):
                self.assertIn(expected_text, submitted_value)

    def test_provisioning_form_has_no_readme_keep_delete_question(self) -> None:
        form = self._load_form()
        visible_text = "\n".join(
            str(field.get("attributes", {}).get("description", ""))
            + "\n"
            + str(field.get("attributes", {}).get("value", ""))
            for field in form["body"]
        )
        self.assertNotIn("README keep/delete preference", visible_text)
        self.assertNotIn("removes it automatically", form["body"][0]["attributes"]["value"])
        self.assertIn("definitive", visible_text)

    def test_provisioning_form_keeps_structure_decisions_out_of_devops_scope(self) -> None:
        form = self._load_form()
        field_ids = [field.get("id") for field in form["body"]]
        self.assertIn("requested_operation", field_ids)
        self.assertNotIn("registry_onboarding", field_ids)
        self.assertNotIn("mount_path", field_ids)
        self.assertNotIn("content_shape", field_ids)
        submitted_value = next(
            field["attributes"]["value"]
            for field in form["body"]
            if field.get("id") == "devops_actions"
        )
        for forbidden_text in (
            "If registry onboarding",
            "Feature move",
            "category move",
            "cutover",
            "navigation",
            "Home cards",
        ):
            with self.subTest(forbidden_text=forbidden_text):
                self.assertNotIn(forbidden_text, submitted_value)


if __name__ == "__main__":
    unittest.main()
