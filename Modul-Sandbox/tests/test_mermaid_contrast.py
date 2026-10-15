from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MKDOCS_FILE = REPO_ROOT / "mkdocs.yml"
MERMAID_SCRIPT = REPO_ROOT / "theme" / "assets" / "javascripts" / "mermaid-contrast.mjs"


class MermaidContrastTests(unittest.TestCase):
    def test_mkdocs_registers_local_mermaid_contrast_initializer(self) -> None:
        mkdocs = MKDOCS_FILE.read_text(encoding="utf-8")

        self.assertIn("extra_javascript:", mkdocs)
        self.assertIn("assets/javascripts/mermaid-contrast.mjs", mkdocs)

    def test_initializer_preserves_material_and_mermaid_security_contract(self) -> None:
        script = MERMAID_SCRIPT.read_text(encoding="utf-8")

        self.assertIn('securityLevel: "antiscript"', script)
        self.assertIn("themeCSS: `${themeCSS}", script)
        self.assertIn("mermaid.initialize = (config = {})", script)
        self.assertIn("window.mermaid = mermaid", script)
        self.assertIn("#a3cc74", script)
        self.assertIn("#fff129", script)
        self.assertNotIn('securityLevel: "loose"', script)


if __name__ == "__main__":
    unittest.main()
