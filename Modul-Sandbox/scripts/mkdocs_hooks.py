"""MkDocs hooks for category-driven navigation and generated section orchestration."""

from __future__ import annotations

import logging
import os
import posixpath
import re
import sys
from collections.abc import Callable
from html import escape as html_escape
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

import yaml
from content_assembly import (
    build_docs_source_display_path,
    build_docs_source_url,
    load_content_sources,
    load_missing_mount_paths,
    load_shadowed_feature_mounts,
)
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.structure.files import File, Files

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from features_section import (  # noqa: E402
    FEATURES_SECTION_PROCESSOR,
    get_feature_responsibility_override,
)
from generate_features_dashboard import get_docs_root  # noqa: E402
from responsibility import (  # noqa: E402
    ResolvedResponsibility,
    build_create_issue_url,
    build_github_project_url,
    resolve_responsibility,
)
from section_processors import GeneratedSectionProcessor  # noqa: E402
from viewer_pages import (  # noqa: E402
    DISPLAY_MODE_RAW,
    DISPLAY_MODE_RENDER,
    build_file_display_page,
    detect_code_language,
    supports_direct_file_link,
    supports_render_mode,
)
from viewer_routes import (  # noqa: E402
    build_section_template_raw_dest_path,
    build_section_template_render_dest_path,
    template_index_relative_link,
    template_sibling_link_for_mode,
)

log = logging.getLogger("mkdocs.hooks")

TEMPLATE_NAV_TITLE = "Templates"
EXCLUDED_TEMPLATE_SOURCE_FILES = {"feature_detail.md"}
CATEGORIES_FILE = REPO_ROOT / "docs" / "categories.yaml"
SEARCH_POLICY_FILE = REPO_ROOT / "search-policy.yaml"
LOCAL_PREVIEW_NOTICE_ENV = "LOCAL_PREVIEW_NOTICE"

SECTION_PROCESSORS: dict[str, GeneratedSectionProcessor] = {
    "Features": FEATURES_SECTION_PROCESSOR,
}

_categories_cache: list[dict[str, Any]] | None = None
_search_excluded_path_prefixes_cache: tuple[PurePosixPath, ...] | None = None
_template_render_prefixes: set[str] = set()
_missing_mount_paths: set[PurePosixPath] = set()

_MISSING_TARGET_WARNING = re.compile(
    r"^Doc file '(?P<source>[^']+)' contains a link '(?P<link>[^']+)', "
    r"but the target(?: '[^']+')? is not found among documentation files\."
)
_UNRECOGNIZED_TARGET_WARNING = re.compile(
    r"^Doc file '(?P<source>[^']+)' contains an unrecognized relative link "
    r"'(?P<link>[^']+)', it was left as is\."
)


class _TemplateRenderWarningFilter(logging.Filter):
    """Suppress link-validation warnings for generated template render pages."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno != logging.WARNING:
            return True
        msg = record.getMessage()
        if "contains a link" not in msg:
            return True
        is_render_page = "render.md" in msg or "render/index.md" in msg
        if is_render_page:
            for prefix in _template_render_prefixes:
                if prefix in msg:
                    return False
        return True


# Approved local-preview exception: absent registered mounts cannot be validated.
class _MissingMountLinkWarningFilter(logging.Filter):
    """Suppress local partial-build link warnings below absent source mounts."""

    def __init__(self, missing_mount_paths: set[PurePosixPath]) -> None:
        super().__init__()
        self.missing_mount_paths = missing_mount_paths

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno != logging.WARNING or not self.missing_mount_paths:
            return True
        match = _MISSING_TARGET_WARNING.match(record.getMessage())
        if match is None:
            match = _UNRECOGNIZED_TARGET_WARNING.match(record.getMessage())
        if match is None:
            return True
        return not _target_is_below_missing_mount(
            match.group("source"),
            match.group("link"),
            self.missing_mount_paths,
        )


class _LegacyTestCasesImageWarningFilter(logging.Filter):
    """Suppress unresolved legacy image references inside TestCases documents."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno != logging.WARNING:
            return True
        msg = record.getMessage()
        match = _MISSING_TARGET_WARNING.match(msg)
        if match is None:
            match = _UNRECOGNIZED_TARGET_WARNING.match(msg)
        if match is None:
            return True
        source = match.group("source")
        link = match.group("link")
        is_testcases_source = source == "TestCases" or source.startswith("TestCases/")
        is_legacy_image_reference = link.startswith(("[TMSIMG]\\", "[TMSIMG]/"))
        return not (is_testcases_source and is_legacy_image_reference)


def _labelize(key: str) -> str:
    key = re.sub(r"([a-z])([A-Z])", r"\1 \2", key)
    tokens = key.replace("_", " ").replace("-", " ").strip().split()

    def _format_token(token: str) -> str:
        if token.isupper():
            return token
        if any(char.isupper() for char in token[1:]):
            return token
        return token.capitalize()

    return " ".join(_format_token(token) for token in tokens)


def _page_title_from_markdown_path(markdown_path: Path) -> str:
    stem = markdown_path.stem
    if stem.lower() == "index":
        return "Overview"
    if stem.lower() == "readme":
        return "README"
    return _labelize(stem)


def _load_yaml(file_path: Path) -> Any:
    if not file_path.exists():
        return {}
    content = file_path.read_text(encoding="utf-8")
    return yaml.safe_load(content) or {}


def _get_section_root(section_name: str) -> Path:
    return _get_docs_root() / section_name


def _get_docs_root() -> Path:
    configured_root = os.environ.get("MODUL_DASHBOARD_DOCS_DIR", "").strip()
    if configured_root:
        return Path(configured_root)
    return REPO_ROOT / "docs"


def _source_reference_for_path(source_path: Path) -> tuple[str, str]:
    docs_path = source_path.relative_to(_get_docs_root())
    sources = load_content_sources()
    return (
        build_docs_source_url(docs_path, sources),
        build_docs_source_display_path(docs_path, sources),
    )


def _get_template_file(section_name: str) -> Path:
    return _get_section_root(section_name) / "000_TEMPLATES" / "overview.yaml"


def _build_summary_placeholder(section_name: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "_", section_name).strip("_").upper()
    return f"[[AUTO:{token}_SUMMARY_TABLE]]"


def _get_section_processor(section_name: str) -> GeneratedSectionProcessor | None:
    return SECTION_PROCESSORS.get(section_name)


def _target_is_below_missing_mount(
    source_uri: str,
    link: str,
    missing_mount_paths: set[PurePosixPath],
) -> bool:
    parsed_link = urlsplit(link)
    if parsed_link.scheme or parsed_link.netloc or link.startswith(("/", "\\")):
        return False
    target_path = unquote(parsed_link.path)
    if not target_path:
        return False
    target_uri = PurePosixPath(
        posixpath.normpath(
            posixpath.join(posixpath.dirname(source_uri), target_path).lstrip("/")
        )
    )
    return any(
        target_uri == mount_path or mount_path in target_uri.parents
        for mount_path in missing_mount_paths
    )


def _load_missing_mount_paths() -> set[PurePosixPath]:
    return load_missing_mount_paths()


def _configure_warning_filters() -> None:
    for logger_name in ("mkdocs.structure.pages", "mkdocs.structure.files"):
        logger = logging.getLogger(logger_name)
        logger.filters = [
            existing_filter
            for existing_filter in logger.filters
            if not isinstance(
                existing_filter,
                (_MissingMountLinkWarningFilter, _TemplateRenderWarningFilter),
            )
        ]
        logger.addFilter(_TemplateRenderWarningFilter())
        logger.addFilter(_MissingMountLinkWarningFilter(_missing_mount_paths))
        logger.addFilter(_LegacyTestCasesImageWarningFilter())


def on_startup(**kwargs: object) -> None:
    for processor in SECTION_PROCESSORS.values():
        if processor.on_startup is not None:
            processor.on_startup()

    global _categories_cache
    _categories_cache = None
    global _search_excluded_path_prefixes_cache
    _search_excluded_path_prefixes_cache = None
    global _missing_mount_paths
    _missing_mount_paths = _load_missing_mount_paths()
    _configure_warning_filters()


def _load_categories() -> list[dict[str, Any]]:
    global _categories_cache
    if _categories_cache is not None:
        return _categories_cache

    config_data = _load_yaml(CATEGORIES_FILE)
    if not isinstance(config_data, dict):
        raise TypeError(
            f"{CATEGORIES_FILE.relative_to(REPO_ROOT).as_posix()} must contain a mapping at the root."
        )

    raw_entries = config_data.get("categories")
    if not isinstance(raw_entries, list):
        raise TypeError(
            f"{CATEGORIES_FILE.relative_to(REPO_ROOT).as_posix()} must contain a 'categories' list."
        )

    categories: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for index, entry in enumerate(raw_entries, start=1):
        if not isinstance(entry, dict):
            raise TypeError(
                f"categories[{index}] in {CATEGORIES_FILE.name} must be a mapping."
            )

        title = entry.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(
                f"categories[{index}] in {CATEGORIES_FILE.name} must define a non-empty 'title'."
            )
        title = title.strip()

        if title in seen_titles:
            raise ValueError(
                f"Duplicate category title '{title}' in {CATEGORIES_FILE.name}."
            )
        seen_titles.add(title)

        enabled = entry.get("enabled", True)
        if not isinstance(enabled, bool):
            raise TypeError(f"Category '{title}' uses a non-boolean 'enabled' value.")
        if not enabled:
            continue

        children = entry.get("children")
        if children is not None:
            if not isinstance(children, list) or not children:
                raise ValueError(
                    f"Category '{title}' must define a non-empty 'children' list."
                )
            categories.append(
                {
                    "title": title,
                    "kind": "group",
                    "children": children,
                }
            )
            continue

        path_value = entry.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            raise ValueError(
                f"Category '{title}' must define a non-empty 'path' or 'children'."
            )

        relative_path = Path(path_value.strip())
        absolute_path = _get_docs_root() / relative_path
        if absolute_path.is_file():
            kind = "page"
        elif absolute_path.is_dir():
            section_name = relative_path.as_posix()
            kind = (
                "generated-section"
                if _get_template_file(section_name).is_file()
                else "directory"
            )
        else:
            if os.environ.get(LOCAL_PREVIEW_NOTICE_ENV, "").strip():
                log.info(
                    "[dashboard] Local preview omits unavailable category '%s'.", title
                )
                continue
            raise ValueError(
                f"Category '{title}' references missing path docs/{relative_path.as_posix()}."
            )

        categories.append(
            {
                "title": title,
                "kind": kind,
                "path": relative_path.as_posix(),
            }
        )

    _categories_cache = categories
    return categories


def _load_search_excluded_path_prefixes() -> tuple[PurePosixPath, ...]:
    """Load published documentation paths intentionally omitted from site search."""
    global _search_excluded_path_prefixes_cache
    if _search_excluded_path_prefixes_cache is not None:
        return _search_excluded_path_prefixes_cache

    if not SEARCH_POLICY_FILE.is_file():
        raise ValueError(
            f"Required search policy '{SEARCH_POLICY_FILE.name}' is missing."
        )

    policy_data = _load_yaml(SEARCH_POLICY_FILE)
    if not isinstance(policy_data, dict) or policy_data.get("version") != 1:
        raise ValueError(f"{SEARCH_POLICY_FILE.name} must define version: 1.")

    raw_prefixes = policy_data.get("excluded_path_prefixes")
    if not isinstance(raw_prefixes, list):
        raise TypeError(
            f"{SEARCH_POLICY_FILE.name} must define an excluded_path_prefixes list."
        )

    prefixes: list[PurePosixPath] = []
    seen_prefixes: set[PurePosixPath] = set()
    for index, raw_prefix in enumerate(raw_prefixes, start=1):
        if (
            not isinstance(raw_prefix, str)
            or not raw_prefix.strip()
            or "\\" in raw_prefix
        ):
            raise ValueError(
                f"excluded_path_prefixes[{index}] in {SEARCH_POLICY_FILE.name} "
                "must be a non-empty relative POSIX path."
            )
        prefix = PurePosixPath(raw_prefix.strip())
        if prefix.is_absolute() or prefix == PurePosixPath(".") or ".." in prefix.parts:
            raise ValueError(
                f"excluded_path_prefixes[{index}] in {SEARCH_POLICY_FILE.name} "
                "must be a non-empty relative POSIX path."
            )
        if prefix in seen_prefixes:
            raise ValueError(
                f"Duplicate excluded search path prefix '{prefix.as_posix()}'."
            )
        seen_prefixes.add(prefix)
        prefixes.append(prefix)

    _search_excluded_path_prefixes_cache = tuple(prefixes)
    return _search_excluded_path_prefixes_cache


def _is_search_excluded_source_uri(source_uri: str) -> bool:
    source_path = PurePosixPath(source_uri)
    return any(
        source_path == prefix or prefix in source_path.parents
        for prefix in _load_search_excluded_path_prefixes()
    )


def _exclude_page_from_search_when_configured(page: Any, source_uri: str) -> None:
    if not _is_search_excluded_source_uri(source_uri):
        return
    page_meta = getattr(page, "meta", None)
    if not isinstance(page_meta, dict):
        return
    search_metadata = page_meta.get("search")
    if search_metadata is None:
        search_metadata = {}
        page_meta["search"] = search_metadata
    if not isinstance(search_metadata, dict):
        raise TypeError(
            f"{source_uri} search metadata must be a mapping to apply search policy."
        )
    # Approved policy: omit designated collections before client-side indexing.
    search_metadata["exclude"] = True


def _collect_generated_section_names() -> list[str]:
    return [
        str(category["path"])
        for category in _load_categories()
        if category.get("kind") == "generated-section"
    ]


def _discover_directory_nav_entries(directory_path: str) -> list[dict[str, Any]]:
    root = _get_docs_root() / directory_path
    entries: list[dict[str, Any]] = []

    index_file = root / "index.md"
    if index_file.is_file():
        entries.append({"Overview": f"{directory_path}/index.md"})

    for child in sorted(root.iterdir(), key=lambda path: path.name.lower()):
        if child.name.startswith("_") or child.name == "000_TEMPLATES":
            continue
        if (
            child.is_file()
            and child.suffix.lower() == ".md"
            and child.name.lower() != "index.md"
        ):
            entries.append(
                {
                    _page_title_from_markdown_path(
                        child
                    ): f"{directory_path}/{child.name}"
                }
            )
            continue
        if child.is_dir():
            child_entries = _discover_subdirectory_nav_entries(child)
            if child_entries:
                child_relative_path = child.relative_to(_get_docs_root()).as_posix()
                if child_entries == [{"Overview": f"{child_relative_path}/index.md"}]:
                    entries.append(
                        {_labelize(child.name): f"{child_relative_path}/index.md"}
                    )
                else:
                    entries.append({_labelize(child.name): child_entries})

    return entries


def _discover_subdirectory_nav_entries(child_dir: Path) -> list[dict[str, Any]]:
    relative_child = child_dir.relative_to(_get_docs_root()).as_posix()
    entries: list[dict[str, Any]] = []

    index_file = child_dir / "index.md"
    if index_file.is_file():
        entries.append({"Overview": f"{relative_child}/index.md"})

    for child in sorted(child_dir.iterdir(), key=lambda path: path.name.lower()):
        if child.name.startswith("_") or child.name == "000_TEMPLATES":
            continue
        if (
            child.is_file()
            and child.suffix.lower() == ".md"
            and child.name.lower() != "index.md"
        ):
            entries.append(
                {
                    _page_title_from_markdown_path(
                        child
                    ): f"{relative_child}/{child.name}"
                }
            )
            continue
        if child.is_dir():
            nested_entries = _discover_subdirectory_nav_entries(child)
            if nested_entries:
                nested_relative_path = child.relative_to(_get_docs_root()).as_posix()
                if nested_entries == [{"Overview": f"{nested_relative_path}/index.md"}]:
                    entries.append(
                        {_labelize(child.name): f"{nested_relative_path}/index.md"}
                    )
                else:
                    entries.append({_labelize(child.name): nested_entries})

    return entries


def _category_directory_index_path(category: dict[str, Any]) -> str | None:
    directory_path = str(category["path"])
    index_path = _get_docs_root() / directory_path / "index.md"
    if index_path.is_file():
        return f"{directory_path}/index.md"
    return None


def _build_root_home_page(source_markdown: str) -> str:
    def _normalize_target(url: str) -> str:
        if url.startswith(("http://", "https://", "mailto:", "#", "data:", "/")):
            return url
        if url.startswith("../"):
            return url[3:]
        return url

    rewritten_lines: list[str] = []
    for line in source_markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith(("hero_cta_href:", "hero_cta2_href:")):
            prefix, _, value_part = line.partition(":")
            value = value_part.strip()
            quote_char = ""
            if len(value) >= 2 and value[0] in {'"', "'"} and value[-1] == value[0]:
                quote_char = value[0]
                value = value[1:-1]
            value = _normalize_target(value)
            rewritten_lines.append(
                f"{prefix}: {quote_char}{value}{quote_char}"
                if quote_char
                else f"{prefix}: {value}"
            )
            continue
        rewritten_lines.append(line)

    rewritten = "\n".join(rewritten_lines)

    def _rewrite_markdown_link(match: re.Match[str]) -> str:
        bracket = match.group(1)
        label = match.group(2)
        url = match.group(3)
        return f"{bracket}{label}]({_normalize_target(url)})"

    return re.sub(r"(!?\[)([^\]]*?)\]\(([^)]+)\)", _rewrite_markdown_link, rewritten)


def _templates_index_dest(section_name: str) -> str:
    return f"{section_name}/000_TEMPLATES/index.md"


def _collect_displayable_template_sources(section_name: str) -> list[tuple[str, Path]]:
    template_source_dir = _get_section_root(section_name) / "000_TEMPLATES"
    displayable_sources: list[tuple[str, Path]] = []

    for source_path in sorted(
        template_source_dir.rglob("*"), key=lambda path: path.as_posix().lower()
    ):
        if not source_path.is_file():
            continue
        if source_path.name in EXCLUDED_TEMPLATE_SOURCE_FILES:
            continue

        if supports_direct_file_link(source_path):
            continue

        relative_parts = source_path.relative_to(template_source_dir).parts
        if any(part.lower() == "images" for part in relative_parts[:-1]):
            continue

        relative_path = source_path.relative_to(template_source_dir).as_posix()
        displayable_sources.append((relative_path, source_path))

    return displayable_sources


def _build_markdown_view_pages(
    title: str,
    source_path: Path,
    render_dest: str,
    sibling_link_for_mode: Callable[[str, str], str],
) -> tuple[str, str]:
    source_url, source_display_path = _source_reference_for_path(source_path)
    raw_content = build_file_display_page(
        title=title,
        source_path=source_path,
        repo_root=REPO_ROOT,
        docs_root=_get_docs_root(),
        source_url=source_url,
        source_display_path=source_display_path,
        display_mode=DISPLAY_MODE_RAW,
        language="md",
        render_link=sibling_link_for_mode(DISPLAY_MODE_RAW, DISPLAY_MODE_RENDER),
        raw_link=sibling_link_for_mode(DISPLAY_MODE_RAW, DISPLAY_MODE_RAW),
    )
    render_content = build_file_display_page(
        title=title,
        source_path=source_path,
        repo_root=REPO_ROOT,
        docs_root=_get_docs_root(),
        source_url=source_url,
        source_display_path=source_display_path,
        display_mode=DISPLAY_MODE_RENDER,
        language="md",
        render_link=sibling_link_for_mode(DISPLAY_MODE_RENDER, DISPLAY_MODE_RENDER),
        raw_link=sibling_link_for_mode(DISPLAY_MODE_RENDER, DISPLAY_MODE_RAW),
        render_dest=render_dest,
    )
    return raw_content, render_content


def _build_template_title(relative_path: str) -> str:
    path = Path(relative_path)
    if path.name in {"overview.yaml", "overview.yml"}:
        return "Schema Template"
    return _labelize(path.stem)


def _build_template_source_page(title: str, source_path: Path, language: str) -> str:
    source_url, source_display_path = _source_reference_for_path(source_path)
    return build_file_display_page(
        title=title,
        source_path=source_path,
        repo_root=REPO_ROOT,
        docs_root=_get_docs_root(),
        source_url=source_url,
        source_display_path=source_display_path,
        display_mode=DISPLAY_MODE_RAW,
        language=language,
    )


def _build_templates_nav_entries(section_name: str) -> list[dict[str, Any]]:
    sources = _collect_displayable_template_sources(section_name)
    entries: list[dict[str, Any]] = [{"Overview": _templates_index_dest(section_name)}]
    root_entries: list[dict[str, str]] = []
    grouped_entries: dict[str, list[dict[str, str]]] = {}

    for relative_path, source_path in sources:
        path = Path(relative_path)
        title = _build_template_title(relative_path)
        destinations = [
            {title: build_section_template_raw_dest_path(section_name, relative_path)}
        ]
        if supports_render_mode(source_path):
            destinations.append(
                {
                    f"{title} (rendered)": build_section_template_render_dest_path(
                        section_name,
                        relative_path,
                    )
                }
            )

        target_entries = root_entries
        if len(path.parts) > 1:
            group_name = _labelize(path.parts[0])
            target_entries = grouped_entries.setdefault(group_name, [])
        target_entries.extend(destinations)

    entries.extend(root_entries)
    entries.extend(
        {group_name: group_entries}
        for group_name, group_entries in grouped_entries.items()
    )
    return entries


def _build_templates_index_page(section_name: str) -> str:
    sources = _collect_displayable_template_sources(section_name)
    lines: list[str] = [
        "# Templates",
        "",
        (
            "This page lists the template files for this section. "
            "These files define the structure and required fields for individual items."
        ),
        "",
    ]

    root_entries: list[tuple[str, str]] = []
    grouped_entries: dict[str, list[tuple[str, str]]] = {}

    for relative_path, source_path in sources:
        path = Path(relative_path)
        title = _build_template_title(relative_path)
        dest = template_index_relative_link(relative_path, source_path)

        if len(path.parts) == 1:
            root_entries.append((title, dest))
        else:
            group_name = _labelize(path.parts[0])
            grouped_entries.setdefault(group_name, []).append((title, dest))

    if root_entries:
        for title, dest in root_entries:
            lines.append(f"- [{title}]({dest})")
        lines.append("")

    for group_name, entries in grouped_entries.items():
        lines.append(f"## {group_name}")
        lines.append("")
        for title, dest in entries:
            lines.append(f"- [{title}]({dest})")
        lines.append("")

    return "\n".join(lines)


def _build_default_section_index_page(
    section_name: str, include_summary_placeholder: bool
) -> str:
    lines: list[str] = [f"# {section_name} Overview", ""]
    if include_summary_placeholder:
        lines.extend(
            [
                "This page is generated from item metadata in this section.",
                "",
                _build_summary_placeholder(section_name),
            ]
        )
    else:
        lines.append(
            "This section is configured as generated but has no category-specific summary processor yet."
        )
    return "\n".join(lines)


def _build_group_child_nav_entry(
    parent_title: str, entry: Any, index: int
) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise TypeError(f"Category '{parent_title}' child #{index} must be a mapping.")

    title = entry.get("title")
    path = entry.get("path")
    if (
        not isinstance(title, str)
        or not title.strip()
        or not isinstance(path, str)
        or not path.strip()
    ):
        raise ValueError(
            f"Category '{parent_title}' child #{index} must define non-empty 'title' and 'path'."
        )

    relative_path = Path(path.strip())
    absolute_path = _get_docs_root() / relative_path
    if not absolute_path.is_file():
        raise ValueError(
            f"Category '{parent_title}' child '{title.strip()}' references missing file docs/{relative_path.as_posix()}."
        )

    return {title.strip(): relative_path.as_posix()}


def _build_generated_section_nav_entries(
    category: dict[str, Any],
) -> list[dict[str, Any]]:
    section_name = str(category["path"])
    section_root = _get_section_root(section_name)
    processor = _get_section_processor(section_name)

    item_entries = processor.build_item_nav_entries(section_name) if processor else []
    has_real_overview = (section_root / "index.md").is_file()
    if not has_real_overview and not item_entries:
        raise ValueError(
            f"Category '{category['title']}' has no displayable content. "
            f"Add docs/{section_name}/index.md or at least one item folder."
        )

    nav_entries: list[dict[str, Any]] = [{"Overview": f"{section_name}/index.md"}]
    nav_entries.extend(item_entries)
    nav_entries.append({TEMPLATE_NAV_TITLE: _build_templates_nav_entries(section_name)})
    return nav_entries


def _build_category_nav_entry(category: dict[str, Any]) -> dict[str, Any]:
    title = str(category["title"])
    kind = str(category["kind"])

    if kind == "page":
        return {title: str(category["path"])}

    if kind == "group":
        child_entries = [
            _build_group_child_nav_entry(title, entry, index)
            for index, entry in enumerate(category["children"], start=1)
        ]
        if not child_entries:
            raise ValueError(f"Category '{title}' has no displayable child pages.")
        return {title: child_entries}

    if kind == "generated-section":
        return {title: _build_generated_section_nav_entries(category)}

    if kind == "directory":
        directory_path = str(category["path"])
        child_entries = _discover_directory_nav_entries(directory_path)
        if not child_entries:
            raise ValueError(
                f"Category '{title}' has no displayable markdown content under docs/{directory_path}."
            )
        index_target = _category_directory_index_path(category)
        if title == "Home" and index_target:
            return {title: "index.md"}
        if (
            index_target
            and len(child_entries) == 1
            and child_entries[0] == {"Overview": index_target}
        ):
            return {title: index_target}
        return {title: child_entries}

    raise ValueError(f"Unsupported category kind '{kind}' for '{title}'.")


def on_config(config: MkDocsConfig) -> MkDocsConfig:
    global CATEGORIES_FILE
    docs_dir = getattr(config, "docs_dir", None)
    if docs_dir is not None:
        CATEGORIES_FILE = Path(docs_dir) / "categories.yaml"
    global _search_excluded_path_prefixes_cache
    _search_excluded_path_prefixes_cache = None
    _load_search_excluded_path_prefixes()
    config.nav = [
        _build_category_nav_entry(category) for category in _load_categories()
    ]
    return config


def on_env(env: Any, config: MkDocsConfig, files: Files, **kwargs: object) -> Any:
    """Expose root responsibility data to system templates without page metadata."""
    system_responsibility = resolve_responsibility(get_docs_root(), "index.md")
    feedback_links, _ = _feedback_metadata(system_responsibility, None)
    env.globals["system_feedback_links"] = feedback_links
    return env


def on_files(files: Files, config: MkDocsConfig, **kwargs: object) -> Files:
    for category in _load_categories():
        if category.get("title") != "Home" or category.get("kind") != "directory":
            continue

        home_index = _get_docs_root() / str(category["path"]) / "index.md"
        if not home_index.is_file():
            raise ValueError("Home category must provide docs/Home/index.md.")

        files.append(
            File.generated(
                config,
                "index.md",
                content=_build_root_home_page(home_index.read_text(encoding="utf-8")),
            )
        )
        break

    global _template_render_prefixes
    _template_render_prefixes = set()

    for section_name in _collect_generated_section_names():
        processor = _get_section_processor(section_name)
        section_index_file = _get_section_root(section_name) / "index.md"
        if not section_index_file.exists():
            files.append(
                File.generated(
                    config,
                    f"{section_name}/index.md",
                    content=_build_default_section_index_page(
                        section_name,
                        include_summary_placeholder=bool(
                            processor and processor.has_summary_placeholder
                        ),
                    ),
                )
            )

        files.append(
            File.generated(
                config,
                _templates_index_dest(section_name),
                content=_build_templates_index_page(section_name),
            )
        )

        _template_render_prefixes.add(f"{section_name}/000_TEMPLATES/")

        for relative_path, source_path in _collect_displayable_template_sources(
            section_name
        ):
            title = _build_template_title(relative_path)
            language = detect_code_language(source_path)
            raw_dest = build_section_template_raw_dest_path(section_name, relative_path)

            if supports_render_mode(source_path):
                render_dest = build_section_template_render_dest_path(
                    section_name, relative_path
                )
                content_raw, content_render = _build_markdown_view_pages(
                    title=title,
                    source_path=source_path,
                    render_dest=render_dest,
                    sibling_link_for_mode=template_sibling_link_for_mode,
                )
                files.append(File.generated(config, raw_dest, content=content_raw))
                files.append(
                    File.generated(config, render_dest, content=content_render)
                )
            else:
                content_raw = _build_template_source_page(title, source_path, language)
                files.append(File.generated(config, raw_dest, content=content_raw))

        if processor is not None:
            processor.generate_item_pages(files, config, section_name)

    return files


def _page_source_uri(page: Any) -> str:
    file = getattr(page, "file", None)
    return str(getattr(file, "src_uri", "") or "").replace("\\", "/")


def _feedback_metadata(
    responsibility: ResolvedResponsibility, page_url: str | None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for label, template_name, routing in (
        (
            "Dashboard/Process Request",
            "dashboard_request.yml",
            responsibility.dashboard_request,
        ),
        ("Content Request", "content_request.yml", responsibility.content_request),
    ):
        route = routing.as_tuple()
        if route is None:
            links.append(
                {
                    "label": label,
                    "url": None,
                    "disabled": True,
                    "missing": list(routing.missing_fields),
                }
            )
            continue
        links.append(
            {
                "label": label,
                "url": build_create_issue_url(
                    template_name, route[0], route[1], page_url
                ),
                "disabled": False,
                "missing": [],
            }
        )
    return links, {
        "responsible": responsibility.responsible,
        "owners": list(responsibility.owners),
        "missing": list(responsibility.missing_fields),
    }


def _responsibility_table_for_page(
    page: Any, source_uri: str, responsibility: ResolvedResponsibility
) -> dict[str, Any] | None:
    if not source_uri or source_uri.startswith("Features/"):
        return None

    source_parts = PurePosixPath(source_uri).parts
    if "000_TEMPLATES" in source_parts:
        return None

    page_file = getattr(page, "file", None)
    if (
        getattr(page_file, "generated_by", None) is not None
        and source_uri != "index.md"
    ):
        return None

    source_uri_for_link = "Home/index.md" if source_uri == "index.md" else source_uri
    source_path = get_docs_root() / source_uri_for_link
    if not source_path.is_file():
        return None

    source_url, source_display_path = _source_reference_for_path(source_path)
    content_project_url = None
    if responsibility.content_request.github_project is not None:
        content_project_url = build_github_project_url(
            responsibility.content_request.github_project
        )

    return {
        "responsible": responsibility.responsible,
        "owners": list(responsibility.owners),
        "content_project_url": content_project_url,
        "source_url": source_url,
        "source_display_path": source_display_path,
    }


def _set_responsibility_metadata(
    page: Any,
    responsibility: ResolvedResponsibility,
    page_url: str | None,
    responsibility_table: dict[str, Any] | None = None,
) -> None:
    page_meta = getattr(page, "meta", None)
    if not isinstance(page_meta, dict):
        return
    feedback_links, page_responsibility = _feedback_metadata(responsibility, page_url)
    page_meta["feedback_links"] = feedback_links
    page_meta["responsibility"] = page_responsibility
    page_meta["responsibility_table"] = responsibility_table


def _feedback_page_url(page: Any) -> str | None:
    canonical_url = str(getattr(page, "canonical_url", "") or "").strip()
    if canonical_url:
        return canonical_url
    page_url = str(getattr(page, "url", "") or "").strip()
    return page_url or None


def _prepend_local_preview_notice(markdown: str) -> str:
    notice = os.environ.get(LOCAL_PREVIEW_NOTICE_ENV, "").strip()
    if not notice:
        return markdown
    return f'!!! warning "Local preview"\n    {notice}\n\n{markdown}'


def _prepend_feature_fallback_notice(markdown: str, source_uri: str) -> str:
    """Explain when a Feature page is still served from Documents during a move."""
    page_path = PurePosixPath(source_uri)
    for mount_path, source in load_shadowed_feature_mounts().items():
        if page_path != mount_path and mount_path not in page_path.parents:
            continue
        feature_name = html_escape(mount_path.name)
        repository = html_escape(source["repository"])
        return (
            f'!!! info "Feature content transition: {feature_name}"\n'
            "    The content currently published from this Feature path still comes "
            "from `Modul-Documents`. The registered Feature repository "
            f"<code>{repository}</code> will become active after the exact old "
            "directory is removed from `Modul-Documents`.\n\n"
            f"{markdown}"
        )
    return markdown


def on_page_markdown(markdown: str, page: Any, **kwargs: object) -> str:
    source_uri = _page_source_uri(page)
    rendered = _prepend_feature_fallback_notice(
        _prepend_local_preview_notice(markdown), source_uri
    )
    for section_name in _collect_generated_section_names():
        processor = _get_section_processor(section_name)
        if processor is None:
            continue
        rendered = processor.replace_placeholders(rendered, section_name)

    _exclude_page_from_search_when_configured(page, source_uri)
    page_url = _feedback_page_url(page)
    page_meta = getattr(page, "meta", {})
    responsibility = resolve_responsibility(
        get_docs_root(),
        source_uri,
        frontmatter_owner=page_meta.get("owner")
        if isinstance(page_meta, dict)
        else None,
        extra_overrides=(
            override
            for section_name in _collect_generated_section_names()
            for override in (
                get_feature_responsibility_override(source_uri, section_name),
            )
            if override is not None
        ),
    )
    _set_responsibility_metadata(
        page,
        responsibility,
        page_url,
        _responsibility_table_for_page(page, source_uri, responsibility),
    )
    return rendered


def on_post_page(output: str, page: Any, **kwargs: object) -> str:
    page_url = str(getattr(page, "url", "") or "")
    page_parts = Path(page_url).parts if page_url else ()
    if "000_TEMPLATES" in page_parts:
        body_open = re.search(r"<body(?P<attributes>[^>]*)>", output, re.IGNORECASE)
        if body_open is not None:
            marked_body = (
                f"<body{body_open.group('attributes')} "
                'data-dashboard-template-page="true">'
            )
            output = (
                output[: body_open.start()] + marked_body + output[body_open.end() :]
            )
    return output


def on_page_context(
    context: dict[str, Any], page: Any, config: MkDocsConfig, nav: Any, **kwargs: object
) -> dict[str, Any]:
    file = getattr(page, "file", None)
    source_uri = str(getattr(file, "src_uri", "") or "").replace("\\", "/")
    page_url = str(getattr(page, "url", "") or "").strip()
    if not source_uri or page_url in {"404.html", "oauth2-redirect.html"}:
        responsibility = resolve_responsibility(get_docs_root(), "index.md")
        _set_responsibility_metadata(page, responsibility, page_url=None)
    if getattr(file, "edit_uri", None) is not None and source_uri:
        page.edit_url = build_docs_source_url(source_uri, load_content_sources())
    return context
