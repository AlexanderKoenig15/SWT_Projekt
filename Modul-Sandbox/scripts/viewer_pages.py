from __future__ import annotations

import os
import re
from html import escape as html_escape
from pathlib import Path
from urllib.parse import quote

import yaml
from markdown_templates import render_headless_key_value_table

DISPLAY_MODE_RENDER = "render"
DISPLAY_MODE_RAW = "raw"
DEFAULT_PROJECT_URL = "https://github.siemens.cloud/AS-IO/Modul-Dashboard"
_FRONTMATTER_RE = re.compile(
    r"\A(?:\ufeff)?---[ \t]*\r?\n(.*?)(?:\r?\n)---[ \t]*(?:\r?\n|\Z)",
    re.DOTALL,
)

_LANGUAGE_BY_SUFFIX = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".xml": "xml",
    ".svg": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "ini",
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".css": "css",
    ".html": "html",
    ".htm": "html",
    ".sql": "sql",
    ".sh": "bash",
    ".bash": "bash",
    ".ps1": "powershell",
    ".bat": "bat",
    ".cmd": "bat",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".java": "java",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
}
_DIRECT_FILE_SUFFIXES = {".pdf", ".msg"}


def _shift_markdown_headings_for_toc(markdown_text: str) -> str:
    """Shift ATX headings one level deeper outside fenced code blocks.

    Material's sidebar TOC commonly focuses on H2+ entries. Many converted
    office documents use mostly H1 headings, so we shift heading levels in
    render mode to improve TOC population without touching source files.
    """
    lines = markdown_text.splitlines()
    out: list[str] = []
    in_fence = False
    fence_char = ""

    for line in lines:
        stripped = line.lstrip()

        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_char = marker
            elif marker == fence_char:
                in_fence = False
                fence_char = ""
            out.append(line)
            continue

        if in_fence:
            out.append(line)
            continue

        # Shift only ATX headings with 1-5 leading #; keep H6 unchanged.
        if stripped.startswith("#"):
            prefix = stripped.split(" ", 1)[0]
            if 1 <= len(prefix) <= 5 and all(ch == "#" for ch in prefix):
                indent_len = len(line) - len(stripped)
                indent = line[:indent_len]
                rest = stripped[len(prefix) :]
                out.append(f"{indent}{prefix}#{rest}")
                continue

        out.append(line)

    return "\n".join(out)


def _rewrite_relative_paths(markdown_text: str, path_prefix: str) -> str:
    """Prefix all relative image/link paths in markdown with path_prefix.

    Render pages live several levels deeper in the URL hierarchy than the
    source file, so relative paths like ``images/foo.png`` would resolve to
    the wrong location.  This rewrites them to point back to the source
    file's actual directory via the computed path_prefix.
    Only relative paths are touched; absolute URLs, anchors, and data URIs
    are left unchanged.
    """
    if not path_prefix or path_prefix == ".":
        return markdown_text

    def _rewrite(m: re.Match) -> str:
        bracket = m.group(1)  # "![" or "["
        alt = m.group(2)  # alt / link text
        url = m.group(3)  # the URL/path
        if url.startswith(("http://", "https://", "/", "#", "data:", "mailto:")):
            return m.group(0)
        return f"{bracket}{alt}]({path_prefix}/{url})"

    return re.sub(r"(!?\[)([^\]]*?)\]\(([^)]+)\)", _rewrite, markdown_text)


def read_source_text(source_path: Path) -> str:
    """Read file content for viewer pages without failing on non-UTF-8 text or binary data."""
    raw_bytes = source_path.read_bytes()

    # If file looks binary, avoid embedding unreadable bytes in generated markdown.
    if b"\x00" in raw_bytes:
        return "[Binary file preview unavailable]"

    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        # Fallback keeps builds resilient for legacy encodings.
        return raw_bytes.decode("utf-8", errors="replace")


def extract_frontmatter(source_text: str) -> tuple[dict[str, object], str]:
    """Extract a YAML frontmatter mapping and the document body.

    Only a frontmatter block at the start of the source is recognized. Invalid
    or non-mapping YAML is left untouched so user documents do not fail builds.
    """
    match = _FRONTMATTER_RE.match(source_text)
    if match is None:
        return {}, source_text

    try:
        metadata = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}, source_text

    if not isinstance(metadata, dict):
        return {}, source_text

    return {str(key): value for key, value in metadata.items()}, source_text[
        match.end() :
    ]


def extract_frontmatter_scalar_values(
    source_text: str, field_names: set[str]
) -> dict[str, str]:
    """Return original spellings for requested non-null scalar fields."""
    match = _FRONTMATTER_RE.match(source_text)
    if match is None:
        return {}

    try:
        document = yaml.compose(match.group(1))
    except yaml.YAMLError:
        return {}

    if not isinstance(document, yaml.MappingNode):
        return {}

    values: dict[str, str] = {}
    for key_node, value_node in document.value:
        if (
            not isinstance(key_node, yaml.ScalarNode)
            or key_node.value not in field_names
        ):
            continue
        if not isinstance(value_node, yaml.ScalarNode) or value_node.tag.endswith(
            ":null"
        ):
            continue
        if value_node.tag.endswith(":bool"):
            continue
        normalized_value = value_node.value.strip()
        if normalized_value:
            values[key_node.value] = normalized_value
    return values


def _format_frontmatter_value(value: object) -> str:
    if value is None:
        return "-"
    elif isinstance(value, (list, tuple)):
        return "<br>".join(_format_frontmatter_value(item) for item in value)
    elif isinstance(value, dict):
        text = yaml.safe_dump(value, default_flow_style=True, sort_keys=False).strip()
    else:
        text = str(value)
    return (
        html_escape(text)
        .replace("\r\n", "\n")
        .replace("\n", "<br>")
        .replace("|", "&#124;")
    )


def build_frontmatter_table(metadata: dict[str, object]) -> list[str]:
    """Build an indented headerless table for the File Viewer admonition."""
    if not metadata:
        return []

    table_lines = render_headless_key_value_table(
        [
            (str(key), _format_frontmatter_value(value))
            for key, value in metadata.items()
        ],
        escape_values=False,
    )
    return [f"    {line}" for line in table_lines]


def detect_code_language(source_path: Path) -> str:
    return _LANGUAGE_BY_SUFFIX.get(source_path.suffix.lower(), "text")


def supports_direct_file_link(source_path: Path) -> bool:
    return source_path.suffix.lower() in _DIRECT_FILE_SUFFIXES


def direct_file_link_label(page_title: str, source_path: Path) -> str:
    suffix = source_path.suffix.lower()
    if suffix in _DIRECT_FILE_SUFFIXES and not page_title.lower().endswith(suffix):
        return f"{page_title}{suffix}"
    return page_title


def direct_file_link_hint(source_path: Path) -> str:
    suffix = source_path.suffix.lower()
    if suffix == ".pdf":
        return "open in new tab"
    if suffix == ".msg":
        return "download file"
    return ""


def direct_file_link_attributes(source_path: Path) -> str:
    if source_path.suffix.lower() == ".pdf":
        return ' target="_blank" rel="noopener noreferrer"'
    if source_path.suffix.lower() == ".msg":
        return " download"
    return ""


def supports_render_mode(source_path: Path) -> bool:
    return source_path.suffix.lower() in {".md", ".markdown"}


def build_file_display_page(
    title: str,
    source_path: Path,
    repo_root: Path,
    docs_root: Path | None = None,
    source_url: str | None = None,
    source_display_path: str | None = None,
    display_mode: str = DISPLAY_MODE_RAW,
    language: str | None = None,
    render_link: str | None = None,
    raw_link: str | None = None,
    render_dest: str | None = None,
) -> str:
    """Build a generated page that shows a source file either rendered or as raw text."""
    effective_docs_root = docs_root or repo_root / "docs"
    relative_source = (
        Path("docs") / source_path.relative_to(effective_docs_root)
    ).as_posix()
    displayed_source = source_display_path or relative_source
    if source_url is None:
        project_url = os.environ.get("PROJECT_URL", DEFAULT_PROJECT_URL).rstrip("/")
        source_url = f"{project_url}/blob/main/{quote(relative_source, safe='/')}"
    source_text = read_source_text(source_path).rstrip()
    frontmatter, document_text = extract_frontmatter(source_text)

    switch_line = ""
    if render_link and raw_link:
        render_label = "Render" if display_mode == DISPLAY_MODE_RENDER else "render"
        raw_label = "Raw" if display_mode == DISPLAY_MODE_RAW else "raw"
        switch_line = f"[{render_label}]({render_link}) | [{raw_label}]({raw_link})"

    header_lines: list[str] = []
    header_lines.extend(
        [
            '<div class="file-viewer-header" markdown="1">',
            "",
            '!!! info "File Viewer"',
        ]
    )
    header_lines.append(f"    Source file: [{displayed_source}]({source_url})")
    if frontmatter:
        header_lines.append("")
        header_lines.extend(build_frontmatter_table(frontmatter))
    if switch_line:
        header_lines.append("")
        header_lines.append(f"    View mode: {switch_line}")
    header_lines.extend(["", "</div>", ""])

    if display_mode == DISPLAY_MODE_RENDER:
        lines: list[str] = []
        lines.extend(header_lines)
        content = _shift_markdown_headings_for_toc(document_text)
        if render_dest is not None:
            # Compute relative path from the render page's served URL directory
            # back to the source file's parent directory so that relative asset
            # references (e.g. images/) resolve correctly in the browser.
            source_parent = source_path.parent.relative_to(
                effective_docs_root
            ).as_posix()
            render_path = Path(render_dest)
            render_dir = (
                render_path.parent
                if render_path.name == "index.md"
                else render_path.with_suffix("")
            ).as_posix()
            path_prefix = os.path.relpath(source_parent, render_dir).replace("\\", "/")
            content = _rewrite_relative_paths(content, path_prefix)
        lines.append(content)
        lines.append("")
        return "\n".join(lines)

    if display_mode != DISPLAY_MODE_RAW:
        raise ValueError(f"Unsupported display mode: {display_mode}")

    if language is None:
        language = detect_code_language(source_path)

    fence = "```"
    while fence in source_text:
        fence += "`"
    return "\n".join(
        [
            *header_lines,
            f"{fence}{language}",
            source_text,
            fence,
            "",
        ]
    )
