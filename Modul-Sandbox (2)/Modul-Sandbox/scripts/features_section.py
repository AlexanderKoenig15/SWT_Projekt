from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

from content_assembly import (
    build_docs_source_display_path,
    build_docs_source_url,
    load_content_sources,
)
from generate_features_dashboard import (
    DocumentPage,
    ResolvedFeature,
    _unpack_document_page,
    build_effective_groups,
    build_resolved_feature,
    build_resolved_feature_detail_content,
    build_resolved_features,
    build_resolved_group_page_content,
    build_resolved_summary_content,
    build_summary_placeholder,
    collect_feature_field_definitions,
    collect_feature_related_pages,
    collect_groups,
    collect_process_field_definitions,
    collect_publishable_feature_dirs,
    get_related_pages_for_source,
    get_resolved_feature_display_name,
    get_resolved_sources,
    get_section_root,
    get_template_file,
    group_dir_slug,
    is_filled,
    is_local_source_path,
    load_feature_detail_template,
    load_group_detail_template,
    load_process_readiness_weights,
    load_yaml,
    parse_source_reference,
)
from markdown_templates import render_markdown_template
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.structure.files import File, Files
from responsibility import (
    ResponsibilityOverride,
    merge_responsibility_overrides,
    parse_policy_data,
)
from section_processors import GeneratedSectionProcessor
from viewer_pages import (
    DISPLAY_MODE_RAW,
    DISPLAY_MODE_RENDER,
    build_file_display_page,
    detect_code_language,
    supports_direct_file_link,
    supports_render_mode,
)
from viewer_routes import (
    build_section_item_file_raw_view_dest_path,
    build_section_item_file_render_view_dest_path,
    feature_file_view_link_from_feature_index,
    feature_file_view_sibling_link,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SITE_URL = "https://pages.github.siemens.cloud/AS-IO/Modul-Dashboard"
log = logging.getLogger("mkdocs.hooks")

_template_cache: dict[str, tuple] = {}


def _get_active_docs_root() -> Path:
    configured_root = os.environ.get("MODUL_DASHBOARD_DOCS_DIR", "").strip()
    if configured_root:
        return Path(configured_root)
    return REPO_ROOT / "docs"


def _source_reference_for_path(source_path: Path) -> tuple[str, str]:
    docs_path = source_path.relative_to(_get_active_docs_root())
    sources = load_content_sources()
    return (
        build_docs_source_url(docs_path, sources),
        build_docs_source_display_path(docs_path, sources),
    )


def _display_relative_path(path: Path) -> str:
    configured_root = os.environ.get("MODUL_DASHBOARD_DOCS_DIR", "").strip()
    root = Path(configured_root) if configured_root else REPO_ROOT
    return path.relative_to(root).as_posix()


def reset_cache() -> None:
    _template_cache.clear()


def _get_template(section_name: str) -> tuple:
    """Return parsed template data used by Features rendering and validation."""
    cached = _template_cache.get(section_name)
    if cached is not None:
        return cached

    template_data = load_yaml(get_template_file(section_name))
    feature_field_definitions = collect_feature_field_definitions(template_data)
    process_field_definitions = collect_process_field_definitions(template_data)
    process_ids = {process_id: {} for process_id in process_field_definitions}
    groups = build_effective_groups(collect_groups(template_data), process_ids)
    readiness_weights = load_process_readiness_weights(template_data)
    page_template = load_feature_detail_template(section_name)
    group_page_template = load_group_detail_template(section_name)
    cached = (
        feature_field_definitions,
        process_field_definitions,
        groups,
        readiness_weights,
        page_template,
        group_page_template,
    )
    _template_cache[section_name] = cached
    return cached


def get_feature_responsibility_override(
    source_uri: str, section_name: str = "Features"
) -> ResponsibilityOverride | None:
    """Return the generated section or Feature page policy for a published URI."""
    prefix = f"{section_name}/"
    if not source_uri.startswith(prefix):
        return None

    relative_uri = source_uri[len(prefix) :]
    template_data = load_yaml(get_template_file(section_name))
    policy_fields = ("responsible", "owner", "dashboard_request", "content_request")
    template_policy_data = {
        field_name: template_data[field_name]
        for field_name in policy_fields
        if field_name in template_data
    }
    template_policy = parse_policy_data(
        template_policy_data,
        f"{get_template_file(section_name).as_posix()} responsibility",
    )
    if relative_uri == "index.md" or relative_uri.startswith("000_TEMPLATES/"):
        return template_policy

    feature_name = relative_uri.split("/", maxsplit=1)[0]
    if not feature_name:
        return None

    feature_dir = get_section_root(section_name) / feature_name
    overview_file = feature_dir / "overview.yaml"
    if not overview_file.is_file():
        return None

    feature_data = load_yaml(overview_file)
    if not isinstance(feature_data, Mapping):
        raise TypeError(
            f"{overview_file.as_posix()} must contain a mapping at the root."
        )
    feature_policy = parse_policy_data(
        {
            field_name: feature_data[field_name]
            for field_name in policy_fields
            if field_name in feature_data
        },
        f"{overview_file.as_posix()} responsibility",
    )
    return merge_responsibility_overrides(template_policy, feature_policy)


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
        docs_root=_get_active_docs_root(),
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
        docs_root=_get_active_docs_root(),
        source_url=source_url,
        source_display_path=source_display_path,
        display_mode=DISPLAY_MODE_RENDER,
        language="md",
        render_link=sibling_link_for_mode(DISPLAY_MODE_RENDER, DISPLAY_MODE_RENDER),
        raw_link=sibling_link_for_mode(DISPLAY_MODE_RENDER, DISPLAY_MODE_RAW),
        render_dest=render_dest,
    )
    return raw_content, render_content


def _build_resolved_source_dir_group_map(
    feature: ResolvedFeature,
) -> dict[str, tuple[str, str]]:
    mapping: dict[str, tuple[str, str]] = {}
    for group in feature.get_groups():
        group_slug = group_dir_slug(group.name)
        for process in group.get_processes():
            for source in get_resolved_sources(process):
                if is_local_source_path(source):
                    _, target = parse_source_reference(source)
                    mapping.setdefault(target, (group.name, group_slug))
    return mapping


def _build_feature_file_view_pages(
    files: Files,
    config: MkDocsConfig,
    section_name: str,
    feature_dir: Path,
    related_pages: dict[str, list[DocumentPage | tuple[str, str]]],
) -> dict[str, list[DocumentPage | tuple[str, str]]]:
    remapped_related_pages: dict[str, list[DocumentPage | tuple[str, str]]] = {}

    for source_dir, pages in related_pages.items():
        remapped_pages: list[DocumentPage | tuple[str, str]] = []
        for page in pages:
            page_title, page_link, frontmatter = _unpack_document_page(page)
            has_frontmatter = len(page) == 3
            source_path = feature_dir / Path(page_link)
            if not source_path.is_file():
                remapped_pages.append(
                    (page_title, page_link, frontmatter)
                    if has_frontmatter
                    else (page_title, page_link)
                )
                continue

            if supports_direct_file_link(source_path):
                remapped_page = (
                    page_title,
                    feature_file_view_link_from_feature_index(page_link, source_path),
                    frontmatter,
                )
                remapped_pages.append(
                    remapped_page if has_frontmatter else remapped_page[:2]
                )
                continue

            raw_dest = build_section_item_file_raw_view_dest_path(
                section_name,
                feature_dir.name,
                page_link,
            )
            source_url, source_display_path = _source_reference_for_path(source_path)

            if supports_render_mode(source_path):
                render_dest = build_section_item_file_render_view_dest_path(
                    section_name,
                    feature_dir.name,
                    page_link,
                )
                raw_content, render_content = _build_markdown_view_pages(
                    title=page_title,
                    source_path=source_path,
                    render_dest=render_dest,
                    sibling_link_for_mode=feature_file_view_sibling_link,
                )
                files.append(File.generated(config, raw_dest, content=raw_content))
                files.append(
                    File.generated(config, render_dest, content=render_content)
                )
            else:
                raw_content = build_file_display_page(
                    title=page_title,
                    source_path=source_path,
                    repo_root=REPO_ROOT,
                    docs_root=_get_active_docs_root(),
                    source_url=source_url,
                    source_display_path=source_display_path,
                    display_mode=DISPLAY_MODE_RAW,
                    language=detect_code_language(source_path),
                )
                files.append(File.generated(config, raw_dest, content=raw_content))

            remapped_page = (
                page_title,
                feature_file_view_link_from_feature_index(page_link, source_path),
                frontmatter,
            )
            remapped_pages.append(
                remapped_page if has_frontmatter else remapped_page[:2]
            )

        remapped_related_pages[source_dir] = remapped_pages

    return remapped_related_pages


def _build_feature_nav_entry(
    section_name: str,
    feature_label: str,
    feature_dir: Path,
    groups: list[dict[str, Any]],
    file_view_entries_by_group_slug: dict[str, list[dict[str, str]]],
    has_related_documents: bool,
) -> dict[str, Any]:
    feature_index = f"{section_name}/{feature_dir.name}/index.md"
    related_documents_link = _feature_fragment_url(
        section_name, feature_dir.name, "related-documents"
    )
    if not groups and not has_related_documents:
        return {feature_label: feature_index}

    sub_entries: list[dict[str, Any]] = [{"Overview": feature_index}]
    for group in groups:
        group_name = str(group.get("name") or "")
        if not group_name:
            continue
        slug = group_dir_slug(group_name)
        group_entries: list[dict[str, Any]] = [
            {"Overview": f"{section_name}/{feature_dir.name}/{slug}/index.md"}
        ]

        file_view_entries = file_view_entries_by_group_slug.get(slug, [])
        if file_view_entries:
            group_entries.append({"File Views": file_view_entries})

        sub_entries.append({group_name: group_entries})
    if has_related_documents:
        sub_entries.append({"Related Documents": related_documents_link})
    return {feature_label: sub_entries}


def _feature_fragment_url(
    section_name: str, feature_dir_name: str, fragment: str
) -> str:
    """Build an absolute feature URL so MkDocs accepts a nav fragment link."""
    site_url = os.environ.get("PAGES_URL", DEFAULT_SITE_URL).rstrip("/")
    section = quote(section_name, safe="/-._~")
    feature = quote(feature_dir_name, safe="-._~()")
    return f"{site_url}/{section}/{feature}/#{fragment}"


def _build_group_file_view_nav_entries(
    section_name: str,
    feature_dir: Path,
    related_pages: dict[str, list[DocumentPage | tuple[str, str]]],
    source_dir_group_map: dict[str, tuple[str, str]],
) -> dict[str, list[dict[str, str]]]:
    entries_by_group_slug: dict[str, list[dict[str, str]]] = {}
    seen_page_links_by_group: dict[str, set[str]] = {}

    for source_dir, group_context in source_dir_group_map.items():
        _, group_slug = group_context
        pages = get_related_pages_for_source(source_dir, related_pages)
        file_entries = entries_by_group_slug.setdefault(group_slug, [])
        seen_page_links = seen_page_links_by_group.setdefault(group_slug, set())
        for page in pages:
            page_title, page_link, _ = _unpack_document_page(page)
            if page_link in seen_page_links:
                continue
            source_path = feature_dir / Path(page_link)
            if not source_path.is_file():
                continue

            if supports_direct_file_link(source_path):
                continue

            seen_page_links.add(page_link)

            page_dest = build_section_item_file_raw_view_dest_path(
                section_name,
                feature_dir.name,
                page_link,
            )
            label = f"{source_dir}/{page_title}"
            file_entries.append({label: page_dest})
            if supports_render_mode(source_path):
                render_dest = build_section_item_file_render_view_dest_path(
                    section_name,
                    feature_dir.name,
                    page_link,
                )
                file_entries.append({f"{label} (rendered)": render_dest})

    return entries_by_group_slug


def build_item_nav_entries(section_name: str) -> list[dict[str, Any]]:
    section_root = get_section_root(section_name)
    feature_dirs = collect_publishable_feature_dirs(section_root)
    if not feature_dirs:
        return []

    (
        feature_field_definitions,
        process_field_definitions,
        groups,
        _,
        _,
        _,
    ) = _get_template(section_name)
    nav_entries: list[dict[str, Any]] = []
    label_counts: dict[str, int] = {}

    for feature_dir in feature_dirs:
        feature_data = load_yaml(feature_dir / "overview.yaml")
        feature = build_resolved_feature(
            feature_dir.name,
            feature_data,
            feature_field_definitions,
            process_field_definitions,
            groups,
        )
        display_name = get_resolved_feature_display_name(feature)
        related_pages = collect_feature_related_pages(feature_dir)
        source_dir_group_map = _build_resolved_source_dir_group_map(feature)
        file_view_entries_by_group_slug = _build_group_file_view_nav_entries(
            section_name,
            feature_dir,
            related_pages,
            source_dir_group_map,
        )
        mapped_page_links = {
            page[1]
            for source_dir in source_dir_group_map
            for page in get_related_pages_for_source(source_dir, related_pages)
        }
        has_related_documents = any(
            source_dir != "Ungrouped"
            and any(page[1] not in mapped_page_links for page in pages)
            for source_dir, pages in related_pages.items()
        )

        count = label_counts.get(display_name, 0) + 1
        label_counts[display_name] = count
        if count > 1:
            display_name = f"{display_name} ({feature_dir.name})"

        nav_entries.append(
            _build_feature_nav_entry(
                section_name,
                display_name,
                feature_dir,
                groups,
                file_view_entries_by_group_slug,
                has_related_documents,
            )
        )

    return nav_entries


def _warn_template_mismatches(
    section_name: str,
    feature_dir: Path,
    feature_data: Any,
    feature_field_definitions: dict[str, Any],
    process_field_definitions: dict[str, dict[str, Any]],
) -> None:
    overview_path = feature_dir / "overview.yaml"
    relative_path = _display_relative_path(overview_path)

    if not isinstance(feature_data, dict):
        log.warning("[dashboard] %s must contain a mapping at the root.", relative_path)
        return

    instance_field_definitions = {
        field_name: definition
        for field_name, definition in feature_field_definitions.items()
        if definition.state != "template"
    }
    allowed_root_keys = set(instance_field_definitions) | {
        "dashboard_request",
        "content_request",
        "processes",
    }
    for key in sorted(feature_data.keys()):
        if key not in allowed_root_keys:
            log.warning(
                "[dashboard] %s contains unknown top-level key '%s' (not in template).",
                relative_path,
                key,
            )

    for key, definition in sorted(instance_field_definitions.items()):
        if key not in feature_data and not is_filled(definition.default):
            log.warning(
                "[dashboard] %s is missing template-defined top-level key '%s'.",
                relative_path,
                key,
            )

    processes_data = feature_data.get("processes", {})
    if not isinstance(processes_data, dict):
        log.warning("[dashboard] %s key 'processes' must be a mapping.", relative_path)
        return

    for process_id, process_value in sorted(processes_data.items()):
        if process_id not in process_field_definitions:
            log.warning(
                "[dashboard] %s contains unknown process '%s' (not in template).",
                relative_path,
                process_id,
            )
            continue

        if not isinstance(process_value, dict):
            log.warning(
                "[dashboard] %s process '%s' must be a mapping.",
                relative_path,
                process_id,
            )
            continue

        allowed_process_fields = {
            field_name
            for field_name, definition in process_field_definitions.get(
                process_id, {}
            ).items()
            if definition.state != "template"
        }
        for field_name in sorted(process_value.keys()):
            definition = process_field_definitions.get(process_id, {}).get(field_name)
            if definition is not None and definition.state == "template":
                log.warning(
                    "[dashboard] %s process '%s' cannot override template-only field '%s'.",
                    relative_path,
                    process_id,
                    field_name,
                )
                continue
            if field_name not in allowed_process_fields:
                log.warning(
                    "[dashboard] %s process '%s' contains unknown field '%s' (not in template).",
                    relative_path,
                    process_id,
                    field_name,
                )

        if "sources" in process_value and not isinstance(
            process_value["sources"], (str, list)
        ):
            log.warning(
                "[dashboard] %s process '%s' field 'sources' must be a string or list.",
                relative_path,
                process_id,
            )


def generate_item_pages(files: Files, config: MkDocsConfig, section_name: str) -> None:
    (
        feature_field_definitions,
        process_field_definitions,
        groups,
        readiness_weights,
        feature_page_template,
        group_page_template,
    ) = _get_template(section_name)
    for feature_dir in collect_publishable_feature_dirs(get_section_root(section_name)):
        feature_data = load_yaml(feature_dir / "overview.yaml")
        _warn_template_mismatches(
            section_name,
            feature_dir,
            feature_data,
            feature_field_definitions,
            process_field_definitions,
        )
        feature = build_resolved_feature(
            feature_dir.name,
            feature_data,
            feature_field_definitions,
            process_field_definitions,
            groups,
        )
        related_pages = collect_feature_related_pages(feature_dir)
        related_pages_for_viewer = _build_feature_file_view_pages(
            files,
            config,
            section_name,
            feature_dir,
            related_pages,
        )

        content = build_resolved_feature_detail_content(
            feature_page_template,
            feature,
            feature_dir,
            readiness_weights,
            related_pages_for_viewer,
            section_name=section_name,
        )

        files.append(
            File.generated(
                config,
                f"{section_name}/{feature_dir.name}/index.md",
                content=content,
            )
        )

        for group in feature.get_groups():
            group_name = group.name

            group_content = build_resolved_group_page_content(
                group_page_template,
                group,
                feature,
                feature_dir,
                readiness_weights,
                related_pages_for_viewer,
            )
            files.append(
                File.generated(
                    config,
                    f"{section_name}/{feature_dir.name}/{group_dir_slug(group_name)}/index.md",
                    content=group_content,
                )
            )


def replace_placeholders(markdown: str, section_name: str) -> str:
    placeholder = build_summary_placeholder(section_name)
    if placeholder not in markdown:
        return markdown

    (
        feature_field_definitions,
        process_field_definitions,
        groups,
        readiness_weights,
        _,
        _,
    ) = _get_template(section_name)
    features = build_resolved_features(
        get_section_root(section_name),
        feature_field_definitions,
        process_field_definitions,
        groups,
    )
    content = build_resolved_summary_content(
        features,
        readiness_weights,
        section_name=section_name,
    )
    return render_markdown_template(markdown, {placeholder: content})


FEATURES_SECTION_PROCESSOR = GeneratedSectionProcessor(
    build_item_nav_entries=build_item_nav_entries,
    generate_item_pages=generate_item_pages,
    replace_placeholders=replace_placeholders,
    on_startup=reset_cache,
    has_summary_placeholder=True,
)
