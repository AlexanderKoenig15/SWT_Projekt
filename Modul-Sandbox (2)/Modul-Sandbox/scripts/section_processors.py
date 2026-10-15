from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.structure.files import Files


@dataclass(frozen=True)
class GeneratedSectionProcessor:
    """Contract for section-specific generated-content processors."""

    build_item_nav_entries: Callable[[str], list[dict[str, Any]]]
    generate_item_pages: Callable[[Files, MkDocsConfig, str], None]
    replace_placeholders: Callable[[str, str], str]
    on_startup: Callable[[], None] | None = None
    has_summary_placeholder: bool = False
