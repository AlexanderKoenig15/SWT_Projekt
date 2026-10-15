from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from resolved_user import _user_from_email  # noqa: E402


class UserFromEmailTests(unittest.TestCase):
    def test_given_family_address_renders_as_family_given(self) -> None:
        user = _user_from_email("jane.doe@example.com")

        self.assertEqual("Doe, Jane", user.name)
        self.assertEqual("jane.doe@example.com", user.email)
        self.assertEqual("mailto:jane.doe@example.com", user.html_url)

    def test_markdown_link_targets_the_mailto_url(self) -> None:
        user = _user_from_email("jane.doe@example.com")

        self.assertEqual("[Doe, Jane](mailto:jane.doe@example.com)", user.markdown_link)

    def test_address_without_separator_keeps_the_local_part(self) -> None:
        self.assertEqual("Jdoe", _user_from_email("jdoe@example.com").name)

    def test_additional_given_names_precede_the_family_name(self) -> None:
        self.assertEqual(
            "Roe, Richard John", _user_from_email("richard.john.roe@example.com").name
        )

    def test_contractor_suffix_is_not_treated_as_a_name(self) -> None:
        user = _user_from_email("jane.doe.ext@example.com")

        self.assertEqual("Doe, Jane", user.name)
        self.assertEqual("mailto:jane.doe.ext@example.com", user.html_url)


if __name__ == "__main__":
    unittest.main()
