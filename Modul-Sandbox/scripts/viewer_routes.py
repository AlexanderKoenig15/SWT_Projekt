from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from viewer_pages import (
    DISPLAY_MODE_RAW,
    DISPLAY_MODE_RENDER,
    supports_direct_file_link,
    supports_render_mode,
)


def build_section_template_raw_dest_path(section_name: str, relative_path: str) -> str:
    """Compute the output path for a template source file in raw display mode."""
    relative_without_suffix = Path(relative_path).with_suffix("").as_posix()
    return f"{section_name}/000_TEMPLATES/{relative_without_suffix}/index.md"


def build_section_template_render_dest_path(
    section_name: str, relative_path: str
) -> str:
    """Compute the output path for a template source file in render display mode."""
    relative_without_suffix = Path(relative_path).with_suffix("").as_posix()
    return f"{section_name}/000_TEMPLATES/{relative_without_suffix}/render.md"


def template_index_relative_link(relative_path: str, source_path: Path) -> str:
    """Path from the Templates index page to an individual source page (relative link)."""
    relative_without_suffix = Path(relative_path).with_suffix("").as_posix()
    # For markdown sources, listings prefer the rendered page.
    if supports_render_mode(source_path):
        return f"{relative_without_suffix}/render.md"
    return f"{relative_without_suffix}/index.md"


def _sibling_link_for_mode(current_mode: str, target_mode: str) -> str:
    """Compute the filename to switch between raw and render modes for a file page.

    Args:
        current_mode: Current display mode (DISPLAY_MODE_RAW or DISPLAY_MODE_RENDER).
        target_mode: Desired display mode.

    Returns:
        Filename to navigate to the target mode ("index.md" for raw, "render.md" for render).

    Raises:
        ValueError: If an unsupported mode combination is provided.
    """
    if current_mode == target_mode:
        return "index.md" if current_mode == DISPLAY_MODE_RAW else "render.md"
    if current_mode == DISPLAY_MODE_RAW and target_mode == DISPLAY_MODE_RENDER:
        return "render.md"
    if current_mode == DISPLAY_MODE_RENDER and target_mode == DISPLAY_MODE_RAW:
        return "index.md"
    raise ValueError(f"Unsupported mode switch: {current_mode} -> {target_mode}")


def template_sibling_link_for_mode(current_mode: str, target_mode: str) -> str:
    """Path between mode variants for a template file page. Delegates to shared implementation."""
    return _sibling_link_for_mode(current_mode, target_mode)


def build_section_item_file_raw_view_dest_path(
    section_name: str,
    item_dir_name: str,
    relative_path: str,
) -> str:
    """Compute raw viewer output path for a section item file."""
    relative_without_suffix = Path(relative_path).with_suffix("").as_posix()
    return f"{section_name}/{item_dir_name}/{relative_without_suffix}/index.md"


def build_section_item_file_render_view_dest_path(
    section_name: str,
    item_dir_name: str,
    relative_path: str,
) -> str:
    """Compute render viewer output path for a section item file."""
    relative_without_suffix = Path(relative_path).with_suffix("").as_posix()
    return f"{section_name}/{item_dir_name}/{relative_without_suffix}/render/index.md"


def feature_file_view_link_from_feature_index(
    relative_path: str, source_path: Path
) -> str:
    """Generate a relative link from a feature's index page to one of its file viewer pages.

    For markdown files, prefers the rendered view. PDF and MSG files link to
    their encoded source assets; other files link to a raw viewer page.

    Args:
        relative_path: Path relative to the feature directory (e.g., "SolutionConcept/overview.md").
        source_path: Absolute path to the source file (used to check if markdown).

    Returns:
        Relative link to the appropriate viewer page or direct source asset.
    """
    relative_without_suffix = Path(relative_path).with_suffix("").as_posix()
    if supports_direct_file_link(source_path):
        return quote(relative_path.replace("\\", "/"), safe="/%-._~()")
    # Related-document listings prefer rendered markdown pages when available.
    if supports_render_mode(source_path):
        return f"{relative_without_suffix}/render/index.md"
    return f"{relative_without_suffix}/index.md"


def feature_file_view_sibling_link(current_mode: str, target_mode: str) -> str:
    """Path between raw and rendered variants of a feature file page."""
    if current_mode == DISPLAY_MODE_RAW and target_mode == DISPLAY_MODE_RENDER:
        return "render/index.md"
    if current_mode == DISPLAY_MODE_RENDER and target_mode == DISPLAY_MODE_RAW:
        return "../index.md"
    if current_mode == DISPLAY_MODE_RAW:
        return "index.md"
    if current_mode == DISPLAY_MODE_RENDER:
        return "index.md"
    raise ValueError(f"Unsupported mode switch: {current_mode} -> {target_mode}")
