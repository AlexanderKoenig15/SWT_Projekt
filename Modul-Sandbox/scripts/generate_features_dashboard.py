from __future__ import annotations

import os
import re
import textwrap
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from dataclasses import field as dataclass_field
from datetime import date, datetime
from hashlib import sha256
from html import escape as html_escape
from math import isclose, isfinite
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from urllib.parse import quote, urlsplit

import yaml
from content_assembly import (
    REGISTRY_FILE,
    AssemblyPlan,
    build_assembly_plan,
    build_docs_directory_url,
    discover_visible_checkouts,
    load_content_sources,
    load_missing_mount_paths,
)
from markdown_templates import render_headless_key_value_table, render_markdown_template
from resolved_user import ResolvedUser
from responsibility import build_github_project_url, normalize_request_routing
from viewer_pages import (
    direct_file_link_attributes,
    direct_file_link_hint,
    direct_file_link_label,
    extract_frontmatter,
    extract_frontmatter_scalar_values,
    read_source_text,
)
from viewer_routes import feature_file_view_link_from_feature_index

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SECTION_NAME = "Features"
DOCS_ROOT_ENV = "MODUL_DASHBOARD_DOCS_DIR"
STATE_REQUIRED = "required"
STATE_OPTIONAL = "optional"
STATE_TEMPLATE = "template"
STATE_APPEND = "append"
SOURCE_NOT_APPLICABLE = "not_applicable"
SOURCE_STATUS_LINK = "Link"
SOURCE_STATUS_MD_FILE = "MD-File"
SOURCE_STATUS_NOT_APPLICABLE = "Not applicable"
SOURCE_STATUS_MISSING = "MISSING"
SOURCE_STATUS_REPOSITORY_MISSING = "REPO MISSING"

PROGRESS_COLOR_ZERO = "#ff1b45"
PROGRESS_COLOR_PARTIAL = "#8a5a00"
PROGRESS_COLOR_COMPLETE = "#47c24d"
PROCESS_METADATA_FALLBACK_COLOR = "#c65d00"

READINESS_TIER_COLOR_ZERO = PROGRESS_COLOR_ZERO
READINESS_TIER_COLOR_LOW = "#ff8716"
READINESS_TIER_COLOR_MEDIUM = "#fff129"
READINESS_TIER_COLOR_HIGH = "#7fe484"
READINESS_TIER_COLOR_COMPLETE = PROGRESS_COLOR_COMPLETE

VALID_STATES = {
    STATE_REQUIRED,
    STATE_OPTIONAL,
    STATE_TEMPLATE,
    STATE_APPEND,
    "template_only",
}
RESERVED_TEMPLATE_KEYS = {
    "dashboard_request",
    "content_request",
    "processes",
    "groups",
    "process_readiness_weights",
}
CONTENT_REQUEST_FIELDS = (
    "content_request.github_project",
    "content_request.assignees",
)

_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")
_MARKDOWN_SOURCE_LINK_RE = re.compile(r"^\[([^\]]+)\]\((.+)\)$")
_MARKDOWN_LINK_DESTINATION_RE = re.compile(
    r"(?P<prefix>!?\[[^\]\n]*\]\(\s*)(?P<destination>&lt;(?://|[A-Za-z][A-Za-z0-9+.-]*:).*?&gt;|//|[A-Za-z][A-Za-z0-9+.-]*:)",
    re.IGNORECASE,
)
_MARKDOWN_REFERENCE_DESTINATION_RE = re.compile(
    r"(?m)^(?P<prefix>[ \t]*\[[^\]\n]+\]:[ \t]*)(?P<destination>&lt;(?://|[A-Za-z][A-Za-z0-9+.-]*:).*?&gt;|//|[A-Za-z][A-Za-z0-9+.-]*:)",
    re.IGNORECASE,
)
_ANCHOR_UNSAFE_CHARACTERS_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _load_safe_external_schemes() -> set[str]:
    """Load allowed external URL schemes from env, with pragmatic defaults.

    The default list keeps common dashboard links usable (including ftp/ftps)
    while still blocking risky script-like schemes.
    """
    configured = os.environ.get("DASHBOARD_ALLOWED_EXTERNAL_SCHEMES", "")
    if configured.strip():
        values = {
            token.strip().lower() for token in configured.split(",") if token.strip()
        }
        return values or {"http", "https", "mailto", "ftp", "ftps"}
    return {"http", "https", "mailto", "ftp", "ftps"}


_SAFE_EXTERNAL_SCHEMES = _load_safe_external_schemes()
_SCHEMES_REQUIRING_NETLOC = {"http", "https", "ftp", "ftps"}


@dataclass(frozen=True)
class ProgressSummary:
    total_items: int
    reported_items: int
    total_progress: float

    @property
    def average(self) -> float | None:
        if not self.reported_items:
            return None
        return self.total_progress / self.reported_items


@dataclass(frozen=True)
class ProcessFieldDefinition:
    state: str
    default: Any
    value_is_declared: bool = False


@dataclass(frozen=True)
class ProcessReadinessWeights:
    source: float
    metadata: float
    progress: float


@dataclass(frozen=True)
class ProcessReadiness:
    source_linked: bool
    metadata_filled: int
    metadata_total: int
    progress: float
    value: float
    source_applicable: bool = True
    source_weight: float = 0.0


@dataclass(frozen=True)
class DocumentFrontmatter:
    author: str | None = None
    version: str | None = None
    state: str | None = None
    owner: str | None = None
    date: str | None = None


@dataclass(frozen=True)
class ResolvedRecord:
    """List-valued configuration fields with state-derived missing status."""

    _fields: Mapping[str, tuple[Any, ...]]
    _states: Mapping[str, str]
    path: str
    _template_defaulted_fields: frozenset[str] = dataclass_field(
        default_factory=frozenset, kw_only=True
    )

    def has_field(self, field_name: str) -> bool:
        return field_name in self._fields

    def get_field_names(self) -> list[str]:
        return list(self._fields)

    def get_required_field_names(self) -> list[str]:
        return [
            field_name
            for field_name, state in self._states.items()
            if state == STATE_REQUIRED
        ]

    def has_template_default(self, field_name: str) -> bool:
        return field_name in self._template_defaulted_fields

    def is_template_field(self, field_name: str) -> bool:
        return self._states.get(field_name) == STATE_TEMPLATE

    def get_value_many(self, field_name: str) -> tuple[list[Any], bool]:
        if field_name not in self._fields:
            raise ValueError(f"{self.path} contains no field '{field_name}'.")
        values = list(self._fields[field_name])
        required_missing = self._states[
            field_name
        ] == STATE_REQUIRED and not _has_non_empty_value(values)
        return values, required_missing

    def get_value_one(self, field_name: str) -> tuple[Any | None, bool]:
        values, required_missing = self.get_value_many(field_name)
        if len(values) > 1:
            raise ValueError(
                f"{self.path} field '{field_name}' requires one value, "
                f"but has {len(values)}."
            )
        return (values[0] if values else None), required_missing


@dataclass(frozen=True)
class ResolvedProcess(ResolvedRecord):
    process_id: str


@dataclass(frozen=True)
class ResolvedGroup:
    name: str
    _processes: tuple[ResolvedProcess, ...]

    def get_processes(self) -> list[ResolvedProcess]:
        return list(self._processes)


@dataclass(frozen=True)
class ResolvedFeature(ResolvedRecord):
    feature_dir_name: str
    _processes: Mapping[str, ResolvedProcess]
    _groups: tuple[ResolvedGroup, ...]

    def get_process(self, process_id: str) -> ResolvedProcess:
        try:
            return self._processes[process_id]
        except KeyError as exc:
            raise ValueError(
                f"{self.path} contains no process '{process_id}'."
            ) from exc

    def get_groups(self) -> list[ResolvedGroup]:
        return list(self._groups)


DocumentPage = tuple[str, str, DocumentFrontmatter]


@dataclass(frozen=True)
class ReadinessSummary:
    process_count: int
    linked_processes: int
    applicable_source_processes: int
    metadata_filled: int
    metadata_total: int
    total_progress: float
    total_readiness: float

    @property
    def progress(self) -> float:
        return self.total_progress / self.process_count if self.process_count else 0.0

    @property
    def value(self) -> float:
        return self.total_readiness / self.process_count if self.process_count else 0.0


@dataclass(frozen=True)
class FeatureFieldStatus:
    field_name: str
    values: tuple[Any, ...]
    effective_values: tuple[Any, ...]
    required: bool
    missing: bool
    template_defaulted: bool
    origins: tuple[str, ...]


@dataclass(frozen=True)
class FeatureSourceStatus:
    process_id: str
    label: str
    target: str
    status: str
    linked: bool


@dataclass(frozen=True)
class FeatureProcessStatus:
    process_id: str
    display_name: str
    readiness: ProcessReadiness
    reported_progress: float | None
    fields: tuple[FeatureFieldStatus, ...]
    owner: FeatureFieldStatus | None
    responsible: FeatureFieldStatus | None
    sources: tuple[FeatureSourceStatus, ...]


@dataclass(frozen=True)
class FeatureGroupStatus:
    name: str
    process_ids: tuple[str, ...]
    readiness: ReadinessSummary


@dataclass(frozen=True)
class FeatureStatus:
    section_name: str
    feature_name: str
    feature_dir_name: str
    owner: FeatureFieldStatus | None
    responsible: FeatureFieldStatus | None
    fields: tuple[FeatureFieldStatus, ...]
    processes: tuple[FeatureProcessStatus, ...]
    groups: tuple[FeatureGroupStatus, ...]
    readiness: ReadinessSummary
    reported_progress: float
    linked_source_count: int
    total_source_count: int
    linked_process_count: int
    total_process_count: int
    missing_required_fields: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the structured status using JSON-friendly container shapes."""
        return asdict(self)


@dataclass(frozen=True)
class EffectiveFeatureStatus:
    """Status lookup result resolved from current visible source checkouts."""

    feature_name: str
    status: FeatureStatus | None
    feature_dir: Path | None
    effective_source_id: str | None
    publication_status: str
    missing_source_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_docs_root() -> Path:
    configured_root = os.environ.get(DOCS_ROOT_ENV, "").strip()
    if configured_root:
        return Path(configured_root)
    return REPO_ROOT / "docs"


def get_section_root(section_name: str) -> Path:
    return get_docs_root() / section_name


def get_template_file(section_name: str) -> Path:
    return get_section_root(section_name) / "000_TEMPLATES" / "overview.yaml"


def get_detail_template_file(section_name: str) -> Path:
    return get_section_root(section_name) / "000_TEMPLATES" / "feature_detail.md"


def get_group_detail_template_file(section_name: str) -> Path:
    return get_section_root(section_name) / "000_TEMPLATES" / "group_detail.md"


def build_summary_placeholder(section_name: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "_", section_name).strip("_").upper()
    return f"[[AUTO:{token}_SUMMARY_TABLE]]"


def load_yaml(file_path: Path) -> Any:
    if not file_path.exists():
        return {}
    content = file_path.read_text(encoding="utf-8")
    return yaml.safe_load(content) or {}


def is_filled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def to_cell_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, list):
        if not value:
            return "-"
        return "<br>".join(escape_cell(str(item)) for item in value)
    if isinstance(value, dict):
        if not value:
            return "-"
        parts = [f"{k}: {v}" for k, v in value.items()]
        return "<br>".join(escape_cell(part) for part in parts)
    return escape_cell(str(value))


def sanitize_output(value: str, target: Literal["text", "url"] = "text") -> str:
    if target == "url":
        # Pipes are not safe in markdown table link destinations.
        return value.replace("|", "%7C")
    return value.replace("|", r"\|")


def escape_cell(value: str) -> str:
    return sanitize_output(value, target="text")


def red_missing_cell() -> str:
    return f'<span style="color:{PROGRESS_COLOR_ZERO};"><strong>MISSING</strong></span>'


def render_missing_value(field_state: str) -> str:
    if field_state == STATE_REQUIRED:
        return red_missing_cell()
    return "-"


def render_value_by_state(
    value: Any,
    field_state: str,
    filled_renderer: Callable[[Any], str] | None = None,
) -> str:
    if not is_filled(value):
        return render_missing_value(field_state)

    renderer = filled_renderer or to_cell_value
    return renderer(value)


def render_resolved_value(values: list[Any], required_missing: bool) -> str:
    """Render a resolved field using its consumer-facing missing status."""
    if _has_non_empty_value(values):
        return to_cell_value(values)
    return red_missing_cell() if required_missing else "-"


def get_item_documents_github_url(section_name: str, item_dir_name: str) -> str:
    """Build GitHub URL to an item folder under docs/<Section>."""
    return build_docs_directory_url(
        Path(section_name) / item_dir_name, load_content_sources()
    )


def load_feature_detail_template(section_name: str = DEFAULT_SECTION_NAME) -> str:
    template_file = get_detail_template_file(section_name)
    if template_file.exists():
        return template_file.read_text(encoding="utf-8")

    # Fallback keeps builds working even if the template file is missing.
    return """# [[AUTO:FEATURE_NAME]]

[[AUTO:FEATURE_DESCRIPTION]]

## Overview

[[AUTO:FEATURE_MAIN_FIELDS]]

[[AUTO:FEATURE_AGGREGATED_OVERVIEW_TABLE]]

[[AUTO:FEATURE_READINESS_DETAILS]]
[[AUTO:READINESS_FORMULA_NOTE]]

## Process Groups

[[AUTO:FEATURE_GROUP_READINESS]]

[[AUTO:FEATURE_RELATED_DOCS]]
"""


def load_group_detail_template(section_name: str = DEFAULT_SECTION_NAME) -> str:
    template_file = get_group_detail_template_file(section_name)
    if template_file.exists():
        return template_file.read_text(encoding="utf-8")

    # Fallback keeps builds working if a category has no group template yet.
    return """# [[AUTO:GROUP_NAME]]

## Overview

[[AUTO:GROUP_READINESS_DETAILS]]

[[AUTO:READINESS_FORMULA_NOTE]]

## Processes

[[AUTO:GROUP_PROCESS_DETAILS]]

[[AUTO:GROUP_PROCESS_SOURCES]]
"""


def collect_feature_dirs(features_root: Path) -> list[Path]:
    return sorted(
        [
            item
            for item in features_root.iterdir()
            if item.is_dir() and item.name != "000_TEMPLATES"
        ],
        key=lambda path: path.name.lower(),
    )


def collect_publishable_feature_dirs(features_root: Path) -> list[Path]:
    """Return Feature directories with an overview metadata file present."""
    return [
        feature_dir
        for feature_dir in collect_feature_dirs(features_root)
        if (feature_dir / "overview.yaml").exists()
    ]


def page_title_from_markdown_path(markdown_path: Path) -> str:
    """Create a human-friendly label for a markdown page file name."""
    stem = markdown_path.stem
    if stem.lower() == "index":
        return "Overview"
    if stem.lower() == "readme":
        return "README"
    return labelize(stem)


def _iter_feature_files(feature_dir: Path) -> list[Path]:
    """Return feature files while traversing mounted directory links."""
    files: list[Path] = []
    visited_directories: set[str] = set()
    for root, directories, filenames in os.walk(
        feature_dir, topdown=True, followlinks=True
    ):
        root_path = Path(root)
        root_key = os.path.normcase(os.path.realpath(root))
        if root_key in visited_directories:
            directories.clear()
            continue
        visited_directories.add(root_key)
        directories[:] = [
            directory
            for directory in directories
            if os.path.normcase(os.path.realpath(root_path / directory))
            not in visited_directories
        ]
        files.extend(root_path / filename for filename in filenames)
    return files


def _should_include_related_file(feature_dir: Path, source_file: Path) -> bool:
    """Return whether a source file should appear in Related Documents.

    Include document-like files that benefit from raw/render viewing, but skip
    support assets such as embedded images so the Related Documents section does
    not get flooded with image files.
    """
    relative_path = source_file.relative_to(feature_dir)

    if source_file == feature_dir / "overview.yaml":
        return False

    if any(part.lower() == "images" for part in relative_path.parts[:-1]):
        return False

    return source_file.suffix.lower() not in {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".webp",
        ".bmp",
        ".wmf",
        ".x-wmf",
    }


def _normalize_document_frontmatter_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_document_frontmatter_people(
    value: Any, separator: str = "<br>"
) -> str | None:
    if isinstance(value, list):
        people = [
            html_escape(str(person).strip())
            for person in value
            if person is not None
            and str(person).strip()
            and str(person).strip().lower() not in {"null", "~"}
        ]
        return separator.join(people) or None
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return html_escape(str(value).strip()) or None
    return None


def _normalize_document_frontmatter_date(value: str | None) -> str | None:
    normalized = _normalize_document_frontmatter_value(value)
    if normalized is None:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            parsed = date.fromisoformat(normalized)
        except ValueError:
            return None
    return parsed.isoformat()


def read_document_frontmatter(source_file: Path) -> DocumentFrontmatter:
    """Read displayable revision fields from a Markdown document safely."""
    if source_file.suffix.lower() not in {".md", ".markdown"}:
        return DocumentFrontmatter()

    source_text = read_source_text(source_file)
    metadata, _ = extract_frontmatter(source_text)
    scalar_metadata = extract_frontmatter_scalar_values(
        source_text, {"document_version", "modified_at", "state"}
    )
    author = _normalize_document_frontmatter_people(metadata.get("author"))
    return DocumentFrontmatter(
        author=author,
        version=_normalize_document_frontmatter_value(
            scalar_metadata.get("document_version")
        ),
        state=_normalize_document_frontmatter_value(scalar_metadata.get("state")),
        owner=_normalize_document_frontmatter_people(
            metadata.get("owner"), separator=", "
        ),
        date=_normalize_document_frontmatter_date(scalar_metadata.get("modified_at")),
    )


def _unpack_document_page(
    page: tuple[str, str] | DocumentPage,
) -> tuple[str, str, DocumentFrontmatter]:
    if len(page) == 3:
        return page
    return page[0], page[1], DocumentFrontmatter()


def _is_path_source(value: str) -> bool:
    """Return True if value should be treated as a local path, False if an external link."""
    if value.lower().startswith("www."):
        return False
    m = _SCHEME_RE.match(value)
    if m:
        return len(m.group(1)) == 1  # single letter = Windows drive (C:, D:)
    return True  # no recognised scheme → local path


def parse_source_reference(value: str) -> tuple[str, str]:
    """Return a source label and target from plain or Markdown-link syntax."""
    source = value.strip()
    match = _MARKDOWN_SOURCE_LINK_RE.fullmatch(source)
    if match:
        label, target = (part.strip() for part in match.groups())
        if label and target:
            return label, target
    return source, source


def sanitize_markdown_description(value: str) -> str:
    """Keep Markdown descriptions while neutralizing unsafe link destinations."""
    escaped_value = html_escape(value)

    def replace_destination(match: re.Match[str]) -> str:
        destination = match.group("destination")
        angle_bracketed = destination.startswith("&lt;")
        scheme_start = 4 if angle_bracketed else 0
        scheme_end = -4 if angle_bracketed else None
        destination_without_bracket = destination[scheme_start:scheme_end]
        if destination_without_bracket == "//":
            return f"{match.group('prefix')}#"
        scheme = destination_without_bracket[:-1].lower()
        if scheme not in _SAFE_EXTERNAL_SCHEMES:
            return f"{match.group('prefix')}#"
        return match.group(0)

    sanitized_value = _MARKDOWN_LINK_DESTINATION_RE.sub(
        replace_destination, escaped_value
    )
    return _MARKDOWN_REFERENCE_DESTINATION_RE.sub(replace_destination, sanitized_value)


def is_local_source_path(value: str) -> bool:
    """Return whether a plain or labeled source reference targets a local path."""
    _, target = parse_source_reference(value)
    return _is_path_source(target)


def build_anchor_id(value: str) -> str:
    """Return a stable, safe fragment identifier for generated headings."""
    normalized = _ANCHOR_UNSAFE_CHARACTERS_RE.sub("-", value.strip()).strip("-")
    if not normalized:
        normalized = "section"
    if normalized == value:
        return normalized
    suffix = sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"{normalized}-{suffix}"


def _ensure_absolute_url(url: str) -> str | None:
    """Normalize and validate external URLs used in generated links.

    Returns a fully-qualified URL for supported schemes or None for unsupported
    or malformed values.
    """
    raw = url.strip()
    if not raw:
        return None

    candidate = raw
    if candidate.lower().startswith("www."):
        candidate = f"https://{candidate}"

    parsed = urlsplit(candidate)
    scheme = parsed.scheme.lower()

    # Bare host/path values without scheme are interpreted as HTTPS links.
    if not scheme:
        candidate = f"https://{candidate}"
        parsed = urlsplit(candidate)
        scheme = parsed.scheme.lower()

    if scheme not in _SAFE_EXTERNAL_SCHEMES:
        return None

    if scheme in _SCHEMES_REQUIRING_NETLOC and not parsed.netloc:
        return None

    if scheme == "mailto" and not parsed.path:
        return None

    return candidate


def group_dir_slug(group_name: str) -> str:
    """Convert a group display name to a URL-safe directory slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", group_name.lower()).strip("-")
    return slug or "group"


def _classify_source(
    value: str, feature_dir: Path
) -> Literal["folder", "missing_folder", "link"]:
    _, target = parse_source_reference(value)
    if not is_local_source_path(value):
        return "link"
    return (
        "folder"
        if _resolve_local_source_dir(feature_dir, target) is not None
        else "missing_folder"
    )


def collect_process_field_definitions(
    template_data: dict[str, Any],
) -> dict[str, dict[str, ProcessFieldDefinition]]:
    """Parse every process field using the shared state/default grammar."""
    template_processes = template_data.get("processes", {})
    if not isinstance(template_processes, dict):
        return {}

    definitions: dict[str, dict[str, ProcessFieldDefinition]] = {}
    for process_id, spec in template_processes.items():
        if not isinstance(spec, dict):
            definitions[str(process_id)] = {}
            continue
        process_definitions = {}
        for field_name, field_spec in spec.items():
            definition = _build_field_definition(
                field_spec, f"Process '{process_id}' field '{field_name}'"
            )
            process_definitions[field_name] = definition
        description_definition = process_definitions.get("description")
        if (
            description_definition is not None
            and description_definition.state != STATE_TEMPLATE
        ):
            raise ValueError(
                f"Process '{process_id}' description must use the template state when declared."
            )
        definitions[str(process_id)] = process_definitions
    return definitions


def collect_groups(template_data: dict[str, Any]) -> list[Any]:
    """Return the groups list from template data."""
    groups = template_data.get("groups", [])
    if not isinstance(groups, list):
        return []
    return groups


def load_process_readiness_weights(
    template_data: dict[str, Any],
) -> ProcessReadinessWeights:
    """Load the template-only process readiness weights."""
    raw_weights = template_data.get("process_readiness_weights")
    if not isinstance(raw_weights, dict):
        raise TypeError("process_readiness_weights must be a mapping.")
    if not all(isinstance(key, str) for key in raw_weights):
        raise TypeError("process_readiness_weights keys must be strings.")

    expected_keys = {"source", "metadata", "progress"}
    actual_keys = set(raw_weights)
    if actual_keys != expected_keys:
        missing_keys = ", ".join(sorted(expected_keys - actual_keys))
        unknown_keys = ", ".join(sorted(actual_keys - expected_keys))
        details = []
        if missing_keys:
            details.append(f"missing: {missing_keys}")
        if unknown_keys:
            details.append(f"unknown: {unknown_keys}")
        raise ValueError(
            "process_readiness_weights must define exactly source, metadata, and "
            f"progress ({'; '.join(details)})."
        )

    values: dict[str, float] = {}
    for key in sorted(expected_keys):
        value = raw_weights[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"process_readiness_weights.{key} must be numeric.")
        normalized_value = float(value)
        if not isfinite(normalized_value) or normalized_value < 0:
            raise ValueError(
                f"process_readiness_weights.{key} must be a finite non-negative number."
            )
        values[key] = normalized_value

    if not isclose(sum(values.values()), 100.0, abs_tol=1e-9):
        raise ValueError("process_readiness_weights must sum to 100.")

    return ProcessReadinessWeights(**values)


def build_effective_groups(
    groups: list[Any],
    process_schemas: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    """Validate that every process belongs to exactly one configured group."""
    process_ids = {str(process_id) for process_id in process_schemas}
    effective_groups: list[dict[str, Any]] = []
    group_names: set[str] = set()
    memberships: dict[str, list[str]] = {}

    for index, group in enumerate(groups, start=1):
        if not isinstance(group, dict):
            raise TypeError(f"groups[{index}] must be a mapping.")
        group_name = group.get("name")
        if not isinstance(group_name, str) or not group_name.strip():
            raise ValueError(f"groups[{index}] must define a non-empty string 'name'.")
        group_name = group_name.strip()
        if group_name in group_names:
            raise ValueError(f"Duplicate group name '{group_name}'.")

        items = group.get("items")
        if not isinstance(items, list):
            raise TypeError(f"Group '{group_name}' must define 'items' as a list.")

        normalized_items: list[str] = []
        for item in items:
            process_id = str(item)
            normalized_items.append(process_id)
            memberships.setdefault(process_id, []).append(group_name)

        normalized_group = dict(group)
        normalized_group["name"] = group_name
        normalized_group["items"] = normalized_items
        effective_groups.append(normalized_group)
        group_names.add(group_name)

    unknown_processes = sorted(set(memberships) - process_ids)
    if unknown_processes:
        details = ", ".join(
            f"{process_id} ({', '.join(memberships[process_id])})"
            for process_id in unknown_processes
        )
        raise ValueError(f"Groups reference unknown process IDs: {details}.")

    duplicate_memberships = {
        process_id: names for process_id, names in memberships.items() if len(names) > 1
    }
    if duplicate_memberships:
        details = ", ".join(
            f"{process_id} ({', '.join(names)})"
            for process_id, names in sorted(duplicate_memberships.items())
        )
        raise ValueError(f"Processes belong to multiple groups: {details}.")

    ungrouped_processes = [
        str(process_id)
        for process_id in process_schemas
        if str(process_id) not in memberships
    ]
    if ungrouped_processes:
        raise ValueError(
            f"Processes are not assigned to a group: {', '.join(ungrouped_processes)}."
        )

    return effective_groups


def _normalize_sources(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [
            str(source).strip()
            for source in value
            if source is not None and str(source).strip()
        ]
    return []


def _is_not_applicable_source_value(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() == SOURCE_NOT_APPLICABLE
    if isinstance(value, (list, tuple)) and len(value) == 1:
        return _is_not_applicable_source_value(value[0])
    return False


def _normalize_append_values(value: Any) -> list[Any]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _append_values(template_value: Any, instance_value: Any) -> list[Any]:
    values: list[Any] = []
    for candidate in [
        *_normalize_append_values(template_value),
        *_normalize_append_values(instance_value),
    ]:
        if not any(candidate == existing for existing in values):
            values.append(candidate)
    return values


def _deduplicate_sources(sources: list[str]) -> list[str]:
    unique_sources: list[str] = []
    seen_targets: set[str] = set()
    for source in sources:
        _, target = parse_source_reference(source)
        normalized_target = (
            target.replace("\\", "/") if is_local_source_path(source) else target
        )
        if normalized_target in seen_targets:
            continue
        seen_targets.add(normalized_target)
        unique_sources.append(source)
    return unique_sources


def _get_active_docs_root() -> Path:
    configured_root = os.environ.get(DOCS_ROOT_ENV, "").strip()
    if configured_root:
        return Path(configured_root)
    return REPO_ROOT / "docs"


def _is_registered_mount_source(
    target: str, assembly_plan: AssemblyPlan | None = None
) -> bool:
    if assembly_plan is not None:
        return assembly_plan.is_registered_mount(target)
    return _registered_mount_root(target) is not None


def _registered_mount_root(target: str) -> Path | None:
    normalized_target = target.strip().replace("\\", "/")
    target_path = PurePosixPath(normalized_target)
    if target_path.is_absolute() or not normalized_target:
        return None
    for source in load_content_sources():
        if source.mount_path != PurePosixPath(".") and (
            target_path == source.mount_path or source.mount_path in target_path.parents
        ):
            return _get_active_docs_root().joinpath(*source.mount_path.parts)
    return None


def _collect_mounted_source_pages(source_target: str) -> list[DocumentPage]:
    """Collect Markdown pages from a registered mount using published routes."""
    if not _is_registered_mount_source(source_target):
        return []

    relative_target = PurePosixPath(source_target.replace("\\", "/"))
    source_dir = _get_active_docs_root().joinpath(*relative_target.parts)
    if not source_dir.is_dir():
        return []

    docs_root = _get_active_docs_root()
    pages: list[DocumentPage] = []
    for source_file in sorted(
        (
            path
            for path in _iter_feature_files(source_dir)
            if path.is_file()
            and path.suffix.lower() in {".md", ".markdown"}
            and _should_include_related_file(source_dir, path)
        ),
        key=lambda path: path.as_posix().lower(),
    ):
        relative_path = source_file.relative_to(docs_root).as_posix()
        pages.append(
            (
                page_title_from_markdown_path(source_file),
                f"/{relative_path}",
                read_document_frontmatter(source_file),
            )
        )
    return pages


def collect_feature_related_pages(
    feature_dir: Path,
) -> dict[str, list[DocumentPage]]:
    """Collect displayable related files below a feature directory, grouped by subdirectory."""
    grouped_pages: dict[str, list[DocumentPage]] = {}

    related_files = sorted(
        [
            path
            for path in _iter_feature_files(feature_dir)
            if path.is_file() and _should_include_related_file(feature_dir, path)
        ],
        key=lambda path: path.as_posix().lower(),
    )

    for related_file in related_files:
        if related_file == feature_dir / "index.md":
            continue

        relative_path = related_file.relative_to(feature_dir)
        if len(relative_path.parts) > 1:
            group_name = relative_path.parts[0]
        else:
            group_name = "Ungrouped"

        grouped_pages.setdefault(group_name, []).append(
            (
                page_title_from_markdown_path(related_file),
                relative_path.as_posix(),
                read_document_frontmatter(related_file),
            )
        )

    return grouped_pages


def get_related_pages_for_source(
    source_target: str,
    pages_by_dir: dict[str, list[DocumentPage | tuple[str, str]]],
) -> list[DocumentPage | tuple[str, str]]:
    """Return collected pages below a configured source directory."""
    source_path = Path(source_target)
    matching_pages: list[DocumentPage | tuple[str, str]] = []
    seen_links: set[str] = set()

    for pages in pages_by_dir.values():
        for page in pages:
            _, page_link, _ = _unpack_document_page(page)
            if page_link in seen_links:
                continue
            if source_path not in Path(page_link).parents:
                continue
            seen_links.add(page_link)
            matching_pages.append(page)

    return matching_pages


def is_page_below_source(
    page: DocumentPage | tuple[str, str], source_target: str
) -> bool:
    """Return whether a collected page belongs to a configured source directory."""
    _, page_link, _ = _unpack_document_page(page)
    return Path(source_target) in Path(page_link).parents


def normalize_state(value: str) -> str:
    normalized = value.strip().lower()
    if normalized == "template_only":
        return STATE_TEMPLATE
    return normalized


def parse_template_field_spec(field_spec: Any) -> tuple[str, Any]:
    """
    Parse a template field declaration and return (state, template_value).

    Supported declarations:
    - legacy: field: null / [] -> (required, None)
    - string state: field: required|optional|template|template_only
    - bool style: field:
        required: false
    - full style: field:
        state: template
        value: Feature Elaboration
    """
    if isinstance(field_spec, str):
        candidate = normalize_state(field_spec)
        if candidate in VALID_STATES:
            return candidate, None
        return STATE_REQUIRED, field_spec

    if isinstance(field_spec, (int, float)) and not isinstance(field_spec, bool):
        return STATE_REQUIRED, field_spec

    if isinstance(field_spec, list) and field_spec:
        return STATE_REQUIRED, field_spec

    if isinstance(field_spec, dict):
        declared_default = field_spec.get("value", field_spec.get("default"))

        if "state" in field_spec:
            state = normalize_state(str(field_spec.get("state")))
            if state not in VALID_STATES:
                state = STATE_REQUIRED
            return state, declared_default

        if "required" in field_spec:
            state = (
                STATE_REQUIRED if bool(field_spec.get("required")) else STATE_OPTIONAL
            )
            return state, declared_default

        # Allow shorthand default declarations without explicit state.
        if "value" in field_spec or "default" in field_spec:
            return STATE_REQUIRED, declared_default

    return STATE_REQUIRED, None


def labelize(key: str) -> str:
    # Split camelCase boundaries before normalizing separators so names like
    # "FeatureElaboration" become "Feature Elaboration".
    key = re.sub(r"([a-z])([A-Z])", r"\1 \2", key)
    tokens = key.replace("_", " ").replace("-", " ").strip().split()

    def _format_token(token: str) -> str:
        if token.isupper():
            return token
        # Preserve intentionally mixed-case tokens (e.g. "eBPF", "iOS").
        if any(char.isupper() for char in token[1:]):
            return token
        return token.capitalize()

    return " ".join(_format_token(token) for token in tokens)


def _build_field_definition(field_spec: Any, field_path: str) -> ProcessFieldDefinition:
    state, default = parse_template_field_spec(field_spec)
    value_is_declared = isinstance(field_spec, dict) and (
        "value" in field_spec or "default" in field_spec
    )
    if state == STATE_TEMPLATE and not value_is_declared:
        raise ValueError(
            f"{field_path} with state 'template' must declare value or default."
        )
    if state == STATE_APPEND and (
        not value_is_declared or not _has_non_empty_value(default)
    ):
        raise ValueError(
            f"{field_path} with state 'append' must declare a non-empty value or default."
        )
    return ProcessFieldDefinition(state, default, value_is_declared)


def collect_feature_field_definitions(
    template_data: dict[str, Any],
) -> dict[str, ProcessFieldDefinition]:
    """Parse the top-level feature field definitions from the shared template."""
    return {
        field_name: _build_field_definition(
            field_spec, f"Top-level field '{field_name}'"
        )
        for field_name, field_spec in template_data.items()
        if field_name not in RESERVED_TEMPLATE_KEYS
    }


def _normalize_resolved_values(value: Any) -> tuple[Any, ...]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return ()
    if isinstance(value, dict) and not value:
        return ()
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def _has_non_empty_value(value: Any) -> bool:
    if isinstance(value, list):
        return any(_has_non_empty_value(item) for item in value)
    return is_filled(value)


def _resolve_field_values(
    definition: ProcessFieldDefinition,
    instance_data: Mapping[str, Any],
    field_name: str,
) -> tuple[Any, ...]:
    template_values = _normalize_resolved_values(definition.default)
    if (
        field_name == "sources"
        and definition.state != STATE_TEMPLATE
        and _is_not_applicable_source_value(instance_data.get(field_name))
    ):
        return (SOURCE_NOT_APPLICABLE,)
    instance_values = _normalize_resolved_values(instance_data.get(field_name))
    if definition.state == STATE_TEMPLATE:
        return template_values
    if definition.state == STATE_APPEND:
        return tuple(_append_values(template_values, instance_values))
    return instance_values or template_values


def build_resolved_feature(
    feature_dir_name: str,
    feature_data: Mapping[str, Any],
    feature_definitions: Mapping[str, ProcessFieldDefinition],
    process_definitions: Mapping[str, Mapping[str, ProcessFieldDefinition]],
    groups: list[dict[str, Any]],
) -> ResolvedFeature:
    """Merge template and feature metadata into the consumer-facing model."""
    if not isinstance(feature_data, Mapping):
        raise TypeError(
            f"Feature '{feature_dir_name}' must contain a mapping at the root."
        )
    raw_processes = feature_data.get("processes", {})
    if not isinstance(raw_processes, Mapping):
        raw_processes = {}

    processes: dict[str, ResolvedProcess] = {}
    for process_id, definitions in process_definitions.items():
        raw_process = raw_processes.get(process_id, {})
        if not isinstance(raw_process, Mapping):
            raw_process = {}
        processes[process_id] = ResolvedProcess(
            _fields={
                field_name: _resolve_field_values(definition, raw_process, field_name)
                for field_name, definition in definitions.items()
            },
            _states={
                field_name: definition.state
                for field_name, definition in definitions.items()
            },
            path=f"Feature '{feature_dir_name}' process '{process_id}'",
            process_id=process_id,
            _template_defaulted_fields=frozenset(
                field_name
                for field_name, definition in definitions.items()
                if _has_non_empty_value(definition.default)
                and not is_filled(raw_process.get(field_name))
            ),
        )

    resolved_groups = tuple(
        ResolvedGroup(
            name=str(group["name"]),
            _processes=tuple(processes[process_id] for process_id in group["items"]),
        )
        for group in groups
    )
    raw_content_request = feature_data.get("content_request", {})
    if not isinstance(raw_content_request, Mapping):
        raise TypeError(
            f"Feature '{feature_dir_name}' content_request must be a mapping."
        )
    feature_fields = {
        field_name: _resolve_field_values(definition, feature_data, field_name)
        for field_name, definition in feature_definitions.items()
        if definition.state != STATE_TEMPLATE
    }
    feature_states = {
        field_name: definition.state
        for field_name, definition in feature_definitions.items()
        if definition.state != STATE_TEMPLATE
    }
    for field_name in CONTENT_REQUEST_FIELDS:
        _, request_field = field_name.split(".", maxsplit=1)
        feature_fields[field_name] = _normalize_resolved_values(
            raw_content_request.get(request_field)
        )
        feature_states[field_name] = STATE_OPTIONAL

    return ResolvedFeature(
        _fields=feature_fields,
        _states=feature_states,
        path=f"Feature '{feature_dir_name}'",
        feature_dir_name=feature_dir_name,
        _processes=processes,
        _groups=resolved_groups,
        _template_defaulted_fields=frozenset(
            field_name
            for field_name, definition in feature_definitions.items()
            if definition.state != STATE_TEMPLATE
            and _has_non_empty_value(definition.default)
            and not is_filled(feature_data.get(field_name))
        ),
    )


def build_resolved_features(
    features_root: Path,
    feature_definitions: Mapping[str, ProcessFieldDefinition],
    process_definitions: Mapping[str, Mapping[str, ProcessFieldDefinition]],
    groups: list[dict[str, Any]],
) -> list[tuple[ResolvedFeature, Path]]:
    """Build resolved feature records for every feature directory under a root."""
    return [
        (
            build_resolved_feature(
                feature_dir.name,
                load_yaml(feature_dir / "overview.yaml"),
                feature_definitions,
                process_definitions,
                groups,
            ),
            feature_dir,
        )
        for feature_dir in collect_publishable_feature_dirs(features_root)
    ]


def get_resolved_content_routing(
    feature: ResolvedFeature,
) -> tuple[str, list[str]] | None:
    """Return validated Feature request routing when locally complete."""
    github_project, _ = feature.get_value_one("content_request.github_project")
    assignees, _ = feature.get_value_many("content_request.assignees")
    if not is_filled(github_project) and not _has_non_empty_value(assignees):
        return None
    routing = normalize_request_routing(
        {"github_project": github_project, "assignees": assignees}
    )
    if routing is None:
        raise ValueError(
            f"{feature.path} content_request must define a valid github_project "
            "and non-empty unique assignees list."
        )
    return routing


def get_resolved_sources(process: ResolvedProcess) -> list[str]:
    """Return valid source strings from a resolved process field."""
    sources, _ = process.get_value_many("sources")
    if _is_not_applicable_source_value(sources):
        return []
    return _deduplicate_sources(_normalize_sources(sources))


def is_resolved_process_source_not_applicable(process: ResolvedProcess) -> bool:
    sources, _ = process.get_value_many("sources")
    return _is_not_applicable_source_value(sources)


def is_resolved_process_source_applicable(process: ResolvedProcess) -> bool:
    """Return whether this process contributes to source coverage."""
    if is_resolved_process_source_not_applicable(process):
        return False
    if get_resolved_sources(process):
        return True
    return process._states.get("sources") == STATE_REQUIRED


def is_resolved_process_linked(
    process: ResolvedProcess,
    feature_dir: Path,
    assembly_plan: AssemblyPlan | None = None,
) -> bool:
    """Return whether a resolved process has a usable source."""
    for source in get_resolved_sources(process):
        _, target = parse_source_reference(source)
        if is_local_source_path(source):
            source_dir = _resolve_local_source_dir(feature_dir, target, assembly_plan)
            if (
                source_dir is not None
                and source_dir.is_dir()
                and any(source_dir.iterdir())
            ):
                return True
        elif _ensure_absolute_url(target) is not None:
            return True
    return False


def _resolve_local_source_dir(
    feature_dir: Path,
    target: str,
    assembly_plan: AssemblyPlan | None = None,
) -> Path | None:
    """Resolve a local source while allowing assembled directory mounts."""
    normalized_target = target.strip().replace("\\", "/")
    relative_target = PurePosixPath(normalized_target)
    if (
        not normalized_target
        or relative_target.is_absolute()
        or any(part in {"", ".", ".."} for part in relative_target.parts)
        or any(":" in part for part in relative_target.parts)
    ):
        return None

    source_dir = feature_dir.joinpath(*relative_target.parts)
    try:
        if source_dir.is_dir():
            return source_dir
    except OSError:
        return None

    if assembly_plan is not None:
        mounted_source_dir = assembly_plan.resolve_docs_path(normalized_target)
        try:
            return (
                mounted_source_dir
                if mounted_source_dir is not None and mounted_source_dir.is_dir()
                else None
            )
        except OSError:
            return None

    if not _is_registered_mount_source(normalized_target):
        return None
    mounted_source_dir = _get_active_docs_root().joinpath(*relative_target.parts)
    try:
        return mounted_source_dir if mounted_source_dir.is_dir() else None
    except OSError:
        return None


def _source_has_markdown_file(
    source: str,
    feature_dir: Path,
    assembly_plan: AssemblyPlan | None = None,
) -> bool:
    if not is_local_source_path(source):
        return False
    _, target = parse_source_reference(source)
    source_dir = _resolve_local_source_dir(feature_dir, target, assembly_plan)
    if source_dir is None or not source_dir.is_dir():
        return False
    return any(
        path.is_file()
        and path.suffix.lower() in {".md", ".markdown"}
        and _should_include_related_file(source_dir, path)
        for path in _iter_feature_files(source_dir)
    )


def _is_missing_assembled_mount(
    target: str, assembly_plan: AssemblyPlan | None = None
) -> bool:
    normalized_target = target.strip().replace("\\", "/")
    target_path = PurePosixPath(normalized_target)
    if target_path.is_absolute() or not normalized_target:
        return False
    if assembly_plan is not None:
        return assembly_plan.is_missing_mount(normalized_target)
    return any(
        target_path == mount_path or mount_path in target_path.parents
        for mount_path in load_missing_mount_paths()
    )


def collect_process_root_documents(
    process: ResolvedProcess,
    feature_dir: Path,
    assembly_plan: AssemblyPlan | None = None,
) -> list[tuple[Path, DocumentFrontmatter]]:
    """Collect direct files from every local process source root."""
    documents: list[tuple[Path, DocumentFrontmatter]] = []
    seen_paths: set[str] = set()
    for source in get_resolved_sources(process):
        if not is_local_source_path(source):
            continue
        _, target = parse_source_reference(source)
        source_dir = _resolve_local_source_dir(feature_dir, target, assembly_plan)
        if source_dir is None or not source_dir.is_dir():
            continue
        for source_file in sorted(
            (
                path
                for path in source_dir.iterdir()
                if path.is_file()
                and path.suffix.lower() in {".md", ".markdown"}
                and _should_include_related_file(source_dir, path)
            ),
            key=lambda path: path.as_posix().lower(),
        ):
            resolved_path = str(source_file.resolve()).casefold()
            if resolved_path in seen_paths:
                continue
            seen_paths.add(resolved_path)
            documents.append((source_file, read_document_frontmatter(source_file)))

    return sorted(
        documents,
        key=lambda document: (
            0 if (document[1].state or "").casefold() == "released" else 1,
            document[0].as_posix().lower(),
        ),
    )


def get_process_frontmatter_value(
    frontmatter: DocumentFrontmatter, field_name: str
) -> str | None:
    """Return the frontmatter value corresponding to a process field."""
    return {
        "owner": frontmatter.owner,
        "version": frontmatter.version,
        "date": frontmatter.date,
    }.get(field_name)


def repository_missing_cell() -> str:
    return (
        f'<span style="color:{PROGRESS_COLOR_PARTIAL};">'
        f"<strong>{SOURCE_STATUS_REPOSITORY_MISSING}</strong></span>"
    )


def render_process_source_status(status: str) -> str:
    if status == SOURCE_STATUS_MISSING:
        return red_missing_cell()
    if status == SOURCE_STATUS_REPOSITORY_MISSING:
        return repository_missing_cell()
    return html_escape(status)


def parse_progress_value(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def build_resolved_process_readiness(
    process: ResolvedProcess,
    feature_dir: Path,
    weights: ProcessReadinessWeights,
    assembly_plan: AssemblyPlan | None = None,
) -> ProcessReadiness:
    """Return readiness from one resolved process and its configured sources."""
    root_documents = collect_process_root_documents(process, feature_dir, assembly_plan)
    metadata_filled = 0
    metadata_total = 0
    for field_name in process.get_required_field_names():
        if field_name in {"progress", "sources"}:
            continue
        if process.has_template_default(field_name):
            continue
        values, _ = process.get_value_many(field_name)
        metadata_total += 1
        frontmatter_values = [
            get_process_frontmatter_value(frontmatter, field_name)
            for _, frontmatter in root_documents
        ]
        if _has_non_empty_value(values) or _has_non_empty_value(frontmatter_values):
            metadata_filled += 1

    progress_value, _ = process.get_value_one("progress")
    progress = parse_progress_value(progress_value) or 0.0
    bounded_progress = min(max(progress, 0.0), 100.0)
    metadata_readiness = metadata_filled / metadata_total if metadata_total else 1.0
    source_linked = is_resolved_process_linked(process, feature_dir, assembly_plan)
    source_applicable = is_resolved_process_source_applicable(process)
    source_satisfied = source_linked or not source_applicable
    value = (
        weights.source * float(source_satisfied)
        + weights.metadata * metadata_readiness
        + weights.progress * bounded_progress / 100
    )
    return ProcessReadiness(
        source_linked=source_linked,
        metadata_filled=metadata_filled,
        metadata_total=metadata_total,
        progress=bounded_progress,
        value=value,
        source_applicable=source_applicable,
        source_weight=weights.source,
    )


def build_resolved_process_readiness_summaries(
    feature: ResolvedFeature,
    feature_dir: Path,
    weights: ProcessReadinessWeights,
    assembly_plan: AssemblyPlan | None = None,
) -> dict[str, ProcessReadiness]:
    return {
        process.process_id: build_resolved_process_readiness(
            process, feature_dir, weights, assembly_plan
        )
        for group in feature.get_groups()
        for process in group.get_processes()
    }


def summarize_process_readiness(
    process_ids: list[str],
    process_readiness: dict[str, ProcessReadiness],
) -> ReadinessSummary:
    selected = [
        process_readiness[process_id]
        for process_id in process_ids
        if process_id in process_readiness
    ]
    return ReadinessSummary(
        process_count=len(selected),
        linked_processes=sum(readiness.source_linked for readiness in selected),
        applicable_source_processes=sum(
            readiness.source_applicable for readiness in selected
        ),
        metadata_filled=sum(readiness.metadata_filled for readiness in selected),
        metadata_total=sum(readiness.metadata_total for readiness in selected),
        total_progress=sum(readiness.progress for readiness in selected),
        total_readiness=_summarize_readiness_value(selected),
    )


def _summarize_readiness_value(selected: list[ProcessReadiness]) -> float:
    if not selected:
        return 0.0
    source_weight = next(
        (readiness.source_weight for readiness in selected if readiness.source_weight),
        0.0,
    )
    if not source_weight:
        return sum(readiness.value for readiness in selected)
    linked_processes = sum(readiness.source_linked for readiness in selected)
    applicable_source_processes = sum(
        readiness.source_applicable for readiness in selected
    )
    source_ratio = (
        linked_processes / applicable_source_processes
        if applicable_source_processes
        else 1.0
    )
    non_source_total = sum(
        readiness.value
        - source_weight
        * float(readiness.source_linked or not readiness.source_applicable)
        for readiness in selected
    )
    return non_source_total + source_weight * source_ratio * len(selected)


def build_resolved_process_progress_summaries(
    feature: ResolvedFeature,
) -> dict[str, ProgressSummary]:
    summaries: dict[str, ProgressSummary] = {}
    for group in feature.get_groups():
        for process in group.get_processes():
            value, _ = process.get_value_one("progress")
            progress = parse_progress_value(value)
            summaries[process.process_id] = (
                ProgressSummary(total_items=1, reported_items=0, total_progress=0)
                if progress is None
                else ProgressSummary(
                    total_items=1, reported_items=1, total_progress=progress
                )
            )
    return summaries


def format_progress_percentage(value: float) -> str:
    if value.is_integer():
        return f"{int(value)}%"
    return f"{value:.1f}%"


def progress_color(progress: float) -> str:
    if progress <= 10:
        return PROGRESS_COLOR_ZERO
    if progress >= 100:
        return PROGRESS_COLOR_COMPLETE
    return PROGRESS_COLOR_PARTIAL


def readiness_tier_style(value: float) -> tuple[str, str]:
    if value <= 10:
        return READINESS_TIER_COLOR_ZERO, "#ffffff"
    if value < 50:
        return READINESS_TIER_COLOR_LOW, "#1a1a1a"
    if value < 80:
        return READINESS_TIER_COLOR_MEDIUM, "#1a1a1a"
    if value < 95:
        return READINESS_TIER_COLOR_HIGH, "#1a1a1a"
    return READINESS_TIER_COLOR_COMPLETE, "#ffffff"


def _mermaid_label_escape(text: str) -> str:
    return html_escape(text.replace("\\", "\\\\"), quote=True)


def _mermaid_readiness_label(name: str, value: float) -> str:
    name_lines = textwrap.wrap(
        name,
        width=24,
        break_long_words=False,
        break_on_hyphens=False,
    ) or [name]
    return (
        "<br/>".join(_mermaid_label_escape(line) for line in name_lines)
        + "<br/>"
        + (f"({format_progress_percentage(value)})")
    )


def _build_ordered_readiness_flowchart(
    node_ids: list[str],
    node_lines: list[str],
    style_lines: list[str],
    click_lines: list[str] | None = None,
) -> str:
    lines = ["```mermaid"]
    if len(node_ids) <= 5:
        lines.append("flowchart LR")
        lines.extend(f"    {line}" for line in node_lines)
        if len(node_ids) > 1:
            lines.append("    " + " --> ".join(node_ids))
    else:
        row_size = (len(node_ids) + 1) // 2
        lines.append("flowchart TB")
        rows = (node_ids[:row_size], node_ids[row_size:])
        for row_index, row in enumerate(rows):
            row_id = f"row{row_index}"
            lines.append(f'    subgraph {row_id}[" "]')
            lines.append("        direction LR")
            for node_id in row:
                node_index = node_ids.index(node_id)
                lines.append(f"        {node_lines[node_index]}")
            if len(row) > 1:
                lines.append("        " + " --> ".join(row))
            lines.append("    end")
            lines.append(
                f"    style {row_id} fill:transparent,stroke:transparent,color:transparent"
            )
        lines.append("    row0 --> row1")
    lines.extend(style_lines)
    lines.extend(click_lines or [])
    lines.append("```")
    return "\n".join(lines)


def render_progress_meter(
    progress: float | None,
    label: str,
    display_value: str | None = None,
) -> str:
    if progress is None:
        return red_missing_cell()

    bounded_progress = min(max(progress, 0), 100)
    color = progress_color(progress)
    percentage = format_progress_percentage(progress)
    visible_value = display_value or percentage
    safe_visible_value = html_escape(visible_value)
    safe_label = html_escape(label)
    meter_value = f"{bounded_progress:g}"
    return (
        f'<progress value="{meter_value}" max="100" '
        f'style="accent-color:{color};" aria-label="{safe_label} '
        f'{safe_visible_value}">{safe_visible_value}</progress> '
        f"<strong>{safe_visible_value}</strong>"
    )


def render_compact_progress(summary: ProgressSummary) -> str:
    progress = summary.average
    if progress is None:
        return red_missing_cell()

    percentage = format_progress_percentage(progress)
    safe_percentage = html_escape(percentage)
    color = progress_color(progress)
    return f'<span style="color:{color};"><strong>{safe_percentage}</strong></span>'


def parse_date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return date.fromisoformat(stripped)
    except ValueError:
        return None


def render_project_link_cell(project_link_url: str | None) -> str:
    if not isinstance(project_link_url, str):
        return to_cell_value(project_link_url)

    normalized_url = _ensure_absolute_url(project_link_url)
    if normalized_url is None:
        return red_missing_cell()

    safe_label = sanitize_output("View project", target="text")
    safe_url = sanitize_output(normalized_url, target="url")
    return f"[{safe_label}]({safe_url})"


def build_feature_summary_table(
    rows: list[dict[str, Any]],
    link_feature_name: bool,
    include_feature_column: bool = True,
) -> str:
    columns = ["Feature"] if include_feature_column else []
    columns.extend(
        ["Owner", "Feature readiness", "Last update", "GitHub project", "Documents"]
    )
    lines = [
        f"| {' | '.join(columns)} |",
        f"| {' | '.join('---' for _ in columns)} |",
    ]

    for row in rows:
        if include_feature_column and link_feature_name:
            feature_link = sanitize_output(str(row["link"]), target="url")
            feature_cell = f"[{escape_cell(row['name'])}]({feature_link})"
        elif include_feature_column:
            feature_cell = escape_cell(row["name"])

        owner_cell = sanitize_output(row["owner"], target="text")
        readiness_cell = sanitize_output(row["readiness"], target="text")
        last_update_cell = sanitize_output(row["last_update"], target="text")
        document_location_cell = sanitize_output(
            row["document_location"], target="text"
        )

        lines.append(
            "| "
            + " | ".join(
                ([feature_cell] if include_feature_column else [])
                + [
                    owner_cell,
                    readiness_cell,
                    last_update_cell,
                    render_value_by_state(
                        row.get("project_link_url"),
                        str(row.get("project_link_state", STATE_OPTIONAL)),
                        render_project_link_cell,
                    ),
                    document_location_cell,
                ]
            )
            + " |"
        )

    return "\n".join(lines)


def build_readiness_details_content(
    summary: ReadinessSummary,
    scope: str,
    include_readiness_value: bool = True,
) -> str:
    """Render the readiness components that explain an aggregate score."""
    metadata_progress = (
        summary.metadata_filled / summary.metadata_total * 100
        if summary.metadata_total
        else 100.0
    )
    rows: list[tuple[str, str]] = []
    if include_readiness_value:
        rows.append(
            (
                f"{scope} readiness",
                render_progress_meter(summary.value, f"{scope} readiness"),
            )
        )
    rows.extend(
        [
            (
                "Processes with linked sources",
                render_progress_meter(
                    summary.linked_processes / summary.applicable_source_processes * 100
                    if summary.applicable_source_processes
                    else None,
                    "Processes with linked sources",
                    display_value=(
                        f"{summary.linked_processes} / "
                        f"{summary.applicable_source_processes}"
                        if summary.applicable_source_processes
                        else "Not required"
                    ),
                ),
            ),
            (
                "Required process metadata",
                render_progress_meter(
                    metadata_progress,
                    "Required process metadata",
                    display_value=(
                        f"{summary.metadata_filled} / {summary.metadata_total}"
                        if summary.metadata_total
                        else "Not required"
                    ),
                ),
            ),
            (
                "Reported process progress",
                render_progress_meter(summary.progress, "Reported progress"),
            ),
        ]
    )
    return "\n".join(render_headless_key_value_table(rows, escape_values=False))


def build_readiness_formula_note(weights: ProcessReadinessWeights) -> str:
    """Explain the template-configured readiness formula in compact text."""
    return (
        '<div class="readiness-formula-note"><small>For each process, readiness '
        "combines linked sources "
        f"({weights.source:g}%), required process metadata ({weights.metadata:g}%), "
        f"and reported process progress ({weights.progress:g}%). "
        "Feature and group readiness are averages of their processes.</small></div>"
    )


# --- file-tree helpers (used by the per-process document sections) ---


def _new_related_tree_node() -> dict[str, Any]:
    return {"files": [], "dirs": {}}


def _insert_related_tree_entry(
    node: dict[str, Any],
    relative_parts: list[str],
    page_title: str,
    page_link: str,
    frontmatter: DocumentFrontmatter | None = None,
) -> None:
    if len(relative_parts) <= 1:
        node["files"].append(
            (page_title, page_link, frontmatter or DocumentFrontmatter())
        )
        return
    head = relative_parts[0]
    child = node["dirs"].setdefault(head, _new_related_tree_node())
    _insert_related_tree_entry(
        child, relative_parts[1:], page_title, page_link, frontmatter
    )


def _count_related_tree_files(node: dict[str, Any]) -> int:
    total = len(node["files"])
    for child in node["dirs"].values():
        total += _count_related_tree_files(child)
    return total


def _render_related_tree_html(
    node: dict[str, Any],
    indent: str = "",
    href_prefix: str = "",
) -> list[str]:
    """Render a flat table whose document cells retain the directory hierarchy."""
    if not node["files"] and not node["dirs"]:
        return []

    lines = [f'{indent}<table class="document-tree-table">']
    lines.append(f'{indent}  <thead><tr class="document-tree-table__header"><th></th>')
    lines.append(
        f"{indent}    <th>Author</th><th>State</th><th>Version</th></tr></thead>"
    )
    lines.append(f"{indent}  <tbody>")
    lines.extend(_render_document_tree_rows(node, indent + "    ", href_prefix))
    lines.extend([f"{indent}  </tbody>", f"{indent}</table>"])
    return lines


def _render_document_tree_prefix(
    ancestor_has_following: tuple[bool, ...], line_count: int = 1
) -> str:
    """Return visible branch guides, including continuation lines for multiline rows."""
    if not ancestor_has_following:
        return ""
    first_line = [
        "&#9474;&nbsp;&nbsp;" if follows else "&nbsp;&nbsp;&nbsp;"
        for follows in ancestor_has_following[:-1]
    ]
    first_line.append(
        "&#9492;&#9472;&nbsp;"
        if not ancestor_has_following[-1]
        else "&#9500;&#9472;&nbsp;"
    )
    lines = ["".join(first_line)]
    continuation_line = "".join(
        "&#9474;&nbsp;&nbsp;" if follows else "&nbsp;&nbsp;&nbsp;"
        for follows in ancestor_has_following
    )
    lines.extend(continuation_line for _ in range(max(line_count - 1, 0)))
    return "\n".join(lines)


def _document_frontmatter_line_count(*values: str) -> int:
    """Return the maximum explicit line count among rendered metadata cells."""
    return max(
        (value.count("<br>") + 1 for value in values if value),
        default=1,
    )


def _render_document_tree_rows(
    node: dict[str, Any],
    indent: str,
    href_prefix: str,
    ancestor_has_following: tuple[bool, ...] = (),
) -> list[str]:
    """Render one level as table rows with a visible text-tree prefix."""
    lines: list[str] = []
    directories = sorted(
        node["dirs"].items(), key=lambda item: item[0].lower(), reverse=True
    )
    files = sorted(node["files"], key=lambda item: item[0].lower(), reverse=True)
    child_count = len(directories) + len(files)

    for index, page in enumerate(files):
        page_title, page_link, frontmatter = _unpack_document_page(page)
        viewer_href = _to_viewer_href(page_link)
        href = viewer_href if viewer_href.startswith("/") else href_prefix + viewer_href
        source_path = Path(page_link)
        link_label = direct_file_link_label(page_title, source_path)
        link_attributes = direct_file_link_attributes(source_path)
        link_hint = direct_file_link_hint(source_path)
        hint_suffix = f" - {html_escape(link_hint)}" if link_hint else ""
        author = frontmatter.author or "&mdash;"
        version = html_escape(frontmatter.version) if frontmatter.version else "&mdash;"
        state = html_escape(frontmatter.state) if frontmatter.state else "&mdash;"
        line_count = _document_frontmatter_line_count(author, state, version)
        link_content = (
            f'<a href="{href}"{link_attributes}>{html_escape(link_label)}</a>'
            f"{hint_suffix}"
        )
        has_following = index < child_count - 1
        prefix = _render_document_tree_prefix(
            (*ancestor_has_following, has_following), line_count=line_count
        )
        prefix_class = (
            "document-tree-table__prefix document-tree-table__prefix--root"
            if not ancestor_has_following and index == 0
            else "document-tree-table__prefix"
        )
        lines.append(
            f'{indent}<tr><td><span class="document-tree-table__file-cell">'
            f'<span class="{prefix_class}" aria-hidden="true">{prefix}</span>'
            f'<span class="document-tree-table__name">{link_content}</span></span></td>'
            f"<td>{author}</td><td>{state}</td><td>{version}</td></tr>"
        )

    for index, (dir_name, child) in enumerate(directories, start=len(files)):
        file_count = _count_related_tree_files(child)
        file_label = "file" if file_count == 1 else "files"
        has_following = index < child_count - 1
        prefix = _render_document_tree_prefix((*ancestor_has_following, has_following))
        prefix_class = (
            "document-tree-table__prefix document-tree-table__prefix--root"
            if not ancestor_has_following and index == len(files)
            else "document-tree-table__prefix"
        )
        lines.append(
            f'{indent}<tr class="document-tree-table__directory"><td colspan="4">'
            f'<span class="{prefix_class}" aria-hidden="true">{prefix}</span>'
            f"&#128193; <strong>{html_escape(dir_name)}</strong>"
            f' <span class="document-tree-table__count">({file_count} {file_label})</span>'
            f"</td></tr>"
        )
        lines.extend(
            _render_document_tree_rows(
                child,
                indent,
                href_prefix,
                (*ancestor_has_following, has_following),
            )
        )

    return lines


def build_document_tree_card(
    title: str,
    tree: dict[str, Any] | None = None,
    empty_message: str | None = None,
    href_prefix: str = "",
) -> str:
    """Render an expandable HTML source-folder listing."""
    lines = ['<details class="abstract document-tree-card">']
    if title:
        if tree is not None:
            file_count = _count_related_tree_files(tree)
            file_label = "file" if file_count == 1 else "files"
            title = f"{title} ({file_count} {file_label})"
        lines.append(f"<summary>&#128193; {html_escape(title)}</summary>")
    if tree is not None:
        lines.extend(
            _render_related_tree_html(
                tree,
                href_prefix=href_prefix,
            )
        )
    elif empty_message is not None:
        lines.append(
            f'<p class="document-tree-card__empty"><em>{html_escape(empty_message)}</em></p>'
        )
    lines.append("</details>")
    return "\n".join(lines)


def _viewer_link_tree_parts(viewer_link: str, folder_name: str) -> list[str]:
    """Return path components for tree placement, relative to the folder root.

    Strips the folder dir name and the trailing viewer slug
    (render/index.md or index.md).
    """
    parts = list(PurePosixPath(viewer_link.replace("\\", "/").lstrip("/")).parts)
    folder_parts = list(PurePosixPath(folder_name.replace("\\", "/")).parts)
    if parts[: len(folder_parts)] == folder_parts:
        parts = parts[len(folder_parts) :]
    if parts and parts[-1] in {"index.md", "render.md"}:
        parts = parts[:-1]
    if parts and parts[-1] == "render":
        parts = parts[:-1]
    return parts


def build_resolved_group_process_readiness_content(
    group: ResolvedGroup,
    process_readiness: Mapping[str, ProcessReadiness],
) -> str:
    """Render per-process readiness for the group's own page."""
    node_lines: list[str] = []
    style_lines: list[str] = []
    node_ids: list[str] = []
    click_lines: list[str] = []
    for index, process in enumerate(group.get_processes()):
        readiness = process_readiness[process.process_id]
        node_id = f"process{index}"
        node_ids.append(node_id)
        process_name = _get_resolved_process_display_name(process)
        label = _mermaid_readiness_label(process_name, readiness.value)
        node_lines.append(f'{node_id}["{label}"]')
        fill_color, text_color = readiness_tier_style(readiness.value)
        style_lines.append(f"    style {node_id} fill:{fill_color},color:{text_color}")
        tooltip = _mermaid_label_escape(f"Open {process_name}")
        click_lines.append(
            f'    click {node_id} "#{build_anchor_id(process.process_id)}" "{tooltip}"'
        )

    return _build_ordered_readiness_flowchart(
        node_ids, node_lines, style_lines, click_lines
    )


def _to_viewer_href(page_link: str) -> str:
    normalized = page_link.replace("\\", "/")
    if normalized.endswith("/index.md"):
        return quote(normalized[: -len("index.md")], safe="/%-._~()")
    if normalized.endswith("/render.md"):
        return quote(normalized[: -len("render.md")] + "render/", safe="/%-._~()")
    if normalized.endswith(".md"):
        return quote(normalized[:-3] + "/", safe="/%-._~()")
    return quote(normalized, safe="/%-._~()")


def get_resolved_feature_display_name(feature: ResolvedFeature) -> str:
    """Return the configured feature name or retain the directory-name fallback."""
    if not feature.has_field("feature_name"):
        return feature.feature_dir_name
    value, _ = feature.get_value_one("feature_name")
    return (
        str(value).strip()
        if isinstance(value, str) and value.strip()
        else feature.feature_dir_name
    )


def _get_resolved_process_display_name(process: ResolvedProcess) -> str:
    value, _ = process.get_value_one("display_name")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{process.path} field 'display_name' requires one non-empty value."
        )
    return value.strip()


def build_resolved_feature_summary_row(
    feature: ResolvedFeature,
    feature_dir: Path,
    readiness_weights: ProcessReadinessWeights,
    section_name: str = DEFAULT_SECTION_NAME,
) -> dict[str, Any]:
    process_readiness = build_resolved_process_readiness_summaries(
        feature, feature_dir, readiness_weights
    )
    process_ids = [
        process.process_id
        for group in feature.get_groups()
        for process in group.get_processes()
    ]
    feature_readiness = summarize_process_readiness(process_ids, process_readiness)

    last_dates: list[date] = []
    for process_id in process_ids:
        process = feature.get_process(process_id)
        if not process.has_field("date"):
            continue
        value, _ = process.get_value_one("date")
        if value is not None:
            parsed_date = parse_date_value(value)
            if parsed_date is not None:
                last_dates.append(parsed_date)

    owner_field = "owner" if feature.has_field("owner") else "sfo"
    owner_values, owner_required_missing = (
        feature.get_value_many(owner_field)
        if feature.has_field(owner_field)
        else ([], False)
    )
    owner_values = [
        ResolvedUser.resolve(str(user)).markdown_link
        for user in owner_values
        if is_filled(user)
    ]
    content_routing = get_resolved_content_routing(feature)
    return {
        "name": get_resolved_feature_display_name(feature),
        "link": f"{feature.feature_dir_name}/index.md",
        "project_link_url": (
            build_github_project_url(content_routing[0])
            if content_routing is not None
            else None
        ),
        "project_link_state": STATE_OPTIONAL,
        "readiness": render_progress_meter(feature_readiness.value, "Readiness"),
        "last_update": max(last_dates).isoformat() if last_dates else "-",
        "document_location": (
            f"[View documents]({sanitize_output(get_item_documents_github_url(section_name, feature.feature_dir_name), target='url')})"
        ),
        "owner": render_resolved_value(owner_values, owner_required_missing),
        "owner_state": STATE_REQUIRED if owner_required_missing else STATE_OPTIONAL,
    }


def _build_feature_field_status(
    record: ResolvedRecord,
    field_name: str,
    root_documents: list[tuple[Path, DocumentFrontmatter]] | None = None,
) -> FeatureFieldStatus:
    root_documents = root_documents or []
    values, _ = record.get_value_many(field_name)
    template_defaulted = record.has_template_default(field_name)
    origins: list[str] = []
    if template_defaulted:
        origins.append("template_default")
    elif _has_non_empty_value(values):
        origins.append("feature_yaml")

    frontmatter_values = [
        get_process_frontmatter_value(frontmatter, field_name)
        for _, frontmatter in root_documents
    ]
    if _has_non_empty_value(frontmatter_values):
        origins.append("document_frontmatter")
    if not origins:
        origins.append("missing")

    missing = (
        record._states.get(field_name) == STATE_REQUIRED
        and not template_defaulted
        and not _has_non_empty_value(values)
        and not _has_non_empty_value(frontmatter_values)
    )
    return FeatureFieldStatus(
        field_name=field_name,
        values=tuple(values),
        effective_values=(
            tuple(value for value in frontmatter_values if is_filled(value))
            if _has_non_empty_value(frontmatter_values)
            else tuple(values)
        ),
        required=record._states.get(field_name) == STATE_REQUIRED,
        missing=missing,
        template_defaulted=template_defaulted,
        origins=tuple(origins),
    )


def _build_feature_source_status(
    process_id: str,
    source: str,
    feature_dir: Path,
    assembly_plan: AssemblyPlan | None = None,
) -> FeatureSourceStatus:
    label, target = parse_source_reference(source)
    if is_local_source_path(source):
        source_dir = _resolve_local_source_dir(feature_dir, target, assembly_plan)
        if source_dir is not None and source_dir.is_dir():
            if any(source_dir.iterdir()):
                return FeatureSourceStatus(
                    process_id, label, target, "linked-local-folder", True
                )
            return FeatureSourceStatus(
                process_id, label, target, "empty-local-folder", False
            )
        if _is_registered_mount_source(target, assembly_plan):
            mount_root = (
                assembly_plan.resolve_docs_path(target)
                if assembly_plan is not None
                else _registered_mount_root(target)
            )
            if mount_root is not None and mount_root.is_dir():
                return FeatureSourceStatus(
                    process_id, label, target, "missing-mounted-path", False
                )
            return FeatureSourceStatus(
                process_id, label, target, "unavailable-mounted-source", False
            )
        return FeatureSourceStatus(
            process_id, label, target, "missing-local-folder", False
        )

    if _ensure_absolute_url(target) is not None:
        return FeatureSourceStatus(
            process_id, label, target, "linked-external-source", True
        )
    return FeatureSourceStatus(process_id, label, target, "invalid-source-link", False)


def _get_process_source_display_status(
    process: ResolvedProcess,
    feature_dir: Path,
    assembly_plan: AssemblyPlan | None = None,
) -> str:
    if is_resolved_process_source_not_applicable(process):
        return SOURCE_STATUS_NOT_APPLICABLE

    sources = get_resolved_sources(process)
    if not sources:
        return (
            SOURCE_STATUS_MISSING
            if process._states.get("sources") == STATE_REQUIRED
            else "-"
        )

    source_statuses = [
        _build_feature_source_status(
            process.process_id, source, feature_dir, assembly_plan
        )
        for source in sources
    ]
    if any(source.linked for source in source_statuses):
        if any(
            _source_has_markdown_file(source, feature_dir, assembly_plan)
            for source in sources
        ):
            return SOURCE_STATUS_MD_FILE
        return SOURCE_STATUS_LINK

    if any(
        source.status == "unavailable-mounted-source"
        and _is_missing_assembled_mount(source.target, assembly_plan)
        for source in source_statuses
    ):
        return SOURCE_STATUS_REPOSITORY_MISSING
    return SOURCE_STATUS_MISSING


def _build_feature_process_status(
    process: ResolvedProcess,
    feature_dir: Path,
    readiness: ProcessReadiness,
    assembly_plan: AssemblyPlan | None = None,
) -> FeatureProcessStatus:
    root_documents = collect_process_root_documents(process, feature_dir, assembly_plan)
    fields = tuple(
        _build_feature_field_status(process, field_name, root_documents)
        for field_name in process.get_required_field_names()
        if field_name not in {"progress", "sources"}
    )
    field_by_name = {field.field_name: field for field in fields}
    owner = field_by_name.get("owner") or (
        _build_feature_field_status(process, "owner", root_documents)
        if process.has_field("owner")
        else None
    )
    responsible = field_by_name.get("responsible") or (
        _build_feature_field_status(process, "responsible", root_documents)
        if process.has_field("responsible")
        else None
    )
    sources = tuple(
        _build_feature_source_status(
            process.process_id, source, feature_dir, assembly_plan
        )
        for source in get_resolved_sources(process)
    )
    if is_resolved_process_source_not_applicable(process):
        sources = (
            FeatureSourceStatus(
                process.process_id,
                "sources",
                SOURCE_NOT_APPLICABLE,
                "not-applicable-source",
                False,
            ),
        )
    elif not sources and process.has_field("sources"):
        _, required_missing = process.get_value_many("sources")
        if required_missing:
            sources = (
                FeatureSourceStatus(
                    process.process_id,
                    "sources",
                    "",
                    "missing-source-declaration",
                    False,
                ),
            )
    progress_value, _ = process.get_value_one("progress")
    return FeatureProcessStatus(
        process_id=process.process_id,
        display_name=_get_resolved_process_display_name(process),
        readiness=readiness,
        reported_progress=parse_progress_value(progress_value),
        fields=fields,
        owner=owner,
        responsible=responsible,
        sources=sources,
    )


def build_feature_status(
    feature: ResolvedFeature,
    feature_dir: Path,
    readiness_weights: ProcessReadinessWeights,
    section_name: str = DEFAULT_SECTION_NAME,
    assembly_plan: AssemblyPlan | None = None,
) -> FeatureStatus:
    """Return structured Feature status using the generator's readiness path."""
    process_readiness = build_resolved_process_readiness_summaries(
        feature, feature_dir, readiness_weights, assembly_plan
    )
    process_ids = [
        process.process_id
        for group in feature.get_groups()
        for process in group.get_processes()
    ]
    feature_readiness = summarize_process_readiness(process_ids, process_readiness)
    process_statuses = tuple(
        _build_feature_process_status(
            feature.get_process(process_id),
            feature_dir,
            process_readiness[process_id],
            assembly_plan,
        )
        for process_id in process_ids
    )
    group_statuses = tuple(
        FeatureGroupStatus(
            name=group.name,
            process_ids=tuple(process.process_id for process in group.get_processes()),
            readiness=summarize_process_readiness(
                [process.process_id for process in group.get_processes()],
                process_readiness,
            ),
        )
        for group in feature.get_groups()
    )
    fields = tuple(
        _build_feature_field_status(feature, field_name)
        for field_name in feature.get_required_field_names()
    )
    owner_field = "owner" if feature.has_field("owner") else "sfo"
    owner = (
        _build_feature_field_status(feature, owner_field)
        if feature.has_field(owner_field)
        else None
    )
    responsible = (
        _build_feature_field_status(feature, "responsible")
        if feature.has_field("responsible")
        else None
    )
    source_statuses = [
        source for process in process_statuses for source in process.sources
    ]
    missing_required_fields = [
        f"feature.{field.field_name}" for field in fields if field.missing
    ]
    missing_required_fields.extend(
        f"process.{process.process_id}.{field.field_name}"
        for process in process_statuses
        for field in process.fields
        if field.missing
    )
    return FeatureStatus(
        section_name=section_name,
        feature_name=get_resolved_feature_display_name(feature),
        feature_dir_name=feature.feature_dir_name,
        owner=owner,
        responsible=responsible,
        fields=fields,
        processes=process_statuses,
        groups=group_statuses,
        readiness=feature_readiness,
        reported_progress=feature_readiness.progress,
        linked_source_count=sum(
            source.linked
            for source in source_statuses
            if source.status != "not-applicable-source"
        ),
        total_source_count=sum(
            source.status != "not-applicable-source" for source in source_statuses
        ),
        linked_process_count=feature_readiness.linked_processes,
        total_process_count=feature_readiness.process_count,
        missing_required_fields=tuple(missing_required_fields),
    )


def get_feature_status(
    feature_dir: Path,
    section_name: str = DEFAULT_SECTION_NAME,
    assembly_plan: AssemblyPlan | None = None,
) -> FeatureStatus:
    """Load one Feature and return its structured generator-derived status."""
    feature_dir = Path(feature_dir)
    if not feature_dir.is_dir():
        raise FileNotFoundError(f"Feature directory does not exist: {feature_dir}")
    overview_file = feature_dir / "overview.yaml"
    if overview_file.exists() and not overview_file.is_file():
        raise ValueError(
            f"Feature metadata path is not a regular file: {overview_file}"
        )
    if not overview_file.is_file():
        raise FileNotFoundError(f"Feature metadata does not exist: {overview_file}")

    template_file = (
        assembly_plan.template_file(section_name)
        if assembly_plan is not None
        else get_template_file(section_name)
    )
    if template_file is None or not template_file.is_file():
        raise FileNotFoundError(
            f"Feature template does not exist for section '{section_name}'."
        )
    template_data = load_yaml(template_file)
    feature_field_definitions = collect_feature_field_definitions(template_data)
    process_field_definitions = collect_process_field_definitions(template_data)
    process_ids = {process_id: {} for process_id in process_field_definitions}
    groups = build_effective_groups(collect_groups(template_data), process_ids)
    readiness_weights = load_process_readiness_weights(template_data)
    feature = build_resolved_feature(
        feature_dir.name,
        load_yaml(overview_file),
        feature_field_definitions,
        process_field_definitions,
        groups,
    )
    return build_feature_status(
        feature,
        feature_dir,
        readiness_weights,
        section_name=section_name,
        assembly_plan=assembly_plan,
    )


def get_feature_status_for_workspace(
    feature_name: str,
    workspace_folders: Sequence[str | Path],
    registry_file: Path = REGISTRY_FILE,
    section_name: str = DEFAULT_SECTION_NAME,
) -> EffectiveFeatureStatus:
    """Resolve and calculate Feature status from current visible checkouts."""
    sources = load_content_sources(registry_file)
    checkouts = discover_visible_checkouts(sources, workspace_folders)
    assembly_plan = build_assembly_plan(
        registry_file.resolve().parent, sources, checkouts
    )
    feature_mount = PurePosixPath(section_name) / feature_name
    feature_dir = assembly_plan.resolve_docs_path(feature_mount)
    effective_source = assembly_plan.resolve_content_source(feature_mount)
    effective_source_id = (
        effective_source.identifier if effective_source is not None else None
    )
    if feature_dir is None or not feature_dir.is_dir():
        return EffectiveFeatureStatus(
            feature_name=feature_name,
            status=None,
            feature_dir=feature_dir,
            effective_source_id=effective_source_id,
            publication_status="unavailable",
            missing_source_ids=assembly_plan.missing_source_ids,
        )

    fallback_active = any(
        source["mount_path"] == feature_mount.as_posix()
        for source in assembly_plan.shadowed_sources
    )
    overview_file = feature_dir / "overview.yaml"
    if overview_file.exists() and not overview_file.is_file():
        raise ValueError(
            f"Feature metadata path is not a regular file: {overview_file}"
        )
    if not overview_file.is_file():
        publication_status = (
            "fallback-effective; pending metadata"
            if fallback_active
            else "pending metadata"
        )
        return EffectiveFeatureStatus(
            feature_name=feature_name,
            status=None,
            feature_dir=feature_dir,
            effective_source_id=effective_source_id,
            publication_status=publication_status,
            missing_source_ids=assembly_plan.missing_source_ids,
        )

    return EffectiveFeatureStatus(
        feature_name=feature_name,
        status=get_feature_status(feature_dir, section_name, assembly_plan),
        feature_dir=feature_dir,
        effective_source_id=effective_source_id,
        publication_status="fallback-effective" if fallback_active else "effective",
        missing_source_ids=assembly_plan.missing_source_ids,
    )


def build_resolved_main_fields_content(feature: ResolvedFeature) -> str:
    lines: list[str] = []
    excluded_fields = {
        "feature_name",
        "description",
        "responsible",
        "sfo",
        "owner",
        *CONTENT_REQUEST_FIELDS,
    }
    for field_name in feature.get_field_names():
        if field_name in excluded_fields:
            continue
        values, required_missing = feature.get_value_many(field_name)
        lines.append(
            f"- {escape_cell(labelize(field_name))}: "
            f"{render_resolved_value(values, required_missing)}"
        )
    return "\n".join(lines)


def build_resolved_feature_description_content(feature: ResolvedFeature) -> str:
    if not feature.has_field("description"):
        return ""
    value, _ = feature.get_value_one("description")
    return sanitize_markdown_description(str(value)) if value is not None else ""


def _collect_resolved_group_fields(group: ResolvedGroup) -> list[str]:
    excluded_fields = {
        "display_name",
        "description",
        "sources",
    }
    fields: list[str] = []
    for process in group.get_processes():
        for field_name in process.get_field_names():
            if (
                field_name not in excluded_fields
                and not process.is_template_field(field_name)
                and field_name not in fields
            ):
                fields.append(field_name)
    if "responsible" not in fields:
        fields.append("responsible")
    return fields


def _render_process_metadata_values(values: list[Any]) -> str:
    filled_values = [value for value in values if is_filled(value)]
    if not filled_values:
        return "-"
    return ", ".join(escape_cell(str(value)) for value in filled_values)


def _render_process_yaml_fallback(process: ResolvedProcess, field_name: str) -> str:
    if field_name in {"date", "version"}:
        value, required_missing = process.get_value_one(field_name)
        values = [value] if value is not None else []
    else:
        values, required_missing = process.get_value_many(field_name)
    if not _has_non_empty_value(values):
        return red_missing_cell() if required_missing else "-"
    rendered = _render_process_metadata_values(values)
    return (
        f'<span style="color:{PROCESS_METADATA_FALLBACK_COLOR};" '
        f'title="Fallback from process YAML">{rendered}</span>'
    )


def _render_process_document_field(
    process: ResolvedProcess,
    field_name: str,
    frontmatter: DocumentFrontmatter,
) -> str:
    frontmatter_field = get_process_frontmatter_value(frontmatter, field_name)
    if is_filled(frontmatter_field):
        rendered = (
            frontmatter_field
            if field_name == "owner"
            else html_escape(str(frontmatter_field))
        )
    else:
        rendered = _render_process_yaml_fallback(process, field_name)
    if field_name == "version" and frontmatter.state:
        rendered += f" ({html_escape(frontmatter.state)})"
    return rendered


def _render_process_document_label(
    source_file: Path,
    feature_dir: Path,
) -> str:
    try:
        relative_path = source_file.relative_to(feature_dir).as_posix()
    except ValueError:
        docs_relative_path = source_file.relative_to(_get_active_docs_root()).as_posix()
        href = _to_viewer_href(f"/{docs_relative_path}")
    else:
        viewer_path = feature_file_view_link_from_feature_index(
            relative_path, source_file
        )
        href = _to_viewer_href(f"../{viewer_path}")
    return f'<a href="{html_escape(href)}">{html_escape(source_file.name)}</a>'


def build_resolved_group_process_details_content(
    group: ResolvedGroup,
    feature_dir: Path,
    process_progress: Mapping[str, ProgressSummary],
) -> str:
    group_fields = _collect_resolved_group_fields(group)
    lines: list[str] = ["<table><thead><tr><th>Process</th><th>Source status</th>"]
    lines.extend(
        f"<th>{html_escape(labelize(field_name))}</th>" for field_name in group_fields
    )
    lines.append("</tr></thead>")

    for process in group.get_processes():
        display_name = _get_resolved_process_display_name(process)
        process_anchor = build_anchor_id(process.process_id)
        root_documents = collect_process_root_documents(process, feature_dir)
        process_lines = [(None, None), *root_documents]
        lines.append("<tbody>")
        for line_index, document in enumerate(process_lines):
            source_file, frontmatter = document
            if line_index == 0:
                process_cell = (
                    f'<a href="#{process_anchor}">{html_escape(display_name)}</a>'
                )
                source_status_cell = render_process_source_status(
                    _get_process_source_display_status(process, feature_dir)
                )
            elif source_file is not None and frontmatter is not None:
                document_prefix = _render_document_tree_prefix(
                    (line_index < len(process_lines) - 1,)
                )
                process_cell = (
                    '<span class="document-tree-table__file-cell">'
                    f'<span class="document-tree-table__prefix" '
                    f'aria-hidden="true">{document_prefix}</span>'
                    f'<span class="document-tree-table__name">'
                    f"{_render_process_document_label(source_file, feature_dir)}"
                    "</span></span>"
                )
                source_status_cell = ""
            else:
                process_cell = ""
                source_status_cell = ""

            cell_attributes = ' style="border-top: 0"' if line_index else ""
            lines.append(
                f"<tr><td{cell_attributes}>{process_cell}</td>"
                f"<td{cell_attributes}>{source_status_cell}</td>"
            )
            for field_name in group_fields:
                if field_name == "progress":
                    cell = (
                        render_compact_progress(process_progress[process.process_id])
                        if line_index == 0
                        else ""
                    )
                elif field_name in {"owner", "version", "date"} and process.has_field(
                    field_name
                ):
                    if root_documents:
                        cell = (
                            _render_process_document_field(
                                process, field_name, frontmatter
                            )
                            if frontmatter is not None
                            else ""
                        )
                    else:
                        value, required_missing = (
                            process.get_value_one(field_name)
                            if field_name in {"date", "version"}
                            else (None, False)
                        )
                        if field_name == "owner":
                            values, required_missing = process.get_value_many(
                                field_name
                            )
                        else:
                            values = [value] if value is not None else []
                        cell = render_resolved_value(values, required_missing)
                elif process.has_field(field_name):
                    if line_index == 0:
                        values, required_missing = process.get_value_many(field_name)
                        cell = render_resolved_value(values, required_missing)
                    else:
                        cell = ""
                else:
                    cell = "&mdash;" if line_index == 0 else ""
                lines.append(f"<td{cell_attributes}>{cell}</td>")
            lines.append("</tr>")
        lines.append("</tbody>")

    lines.append("</table>")
    return "\n".join(lines)


def build_resolved_group_process_sources_content(
    group: ResolvedGroup,
    feature_dir: Path,
    remapped_pages_by_dir: dict[str, list[DocumentPage | tuple[str, str]]],
) -> str:
    lines: list[str] = []
    for process in group.get_processes():
        display_name = _get_resolved_process_display_name(process)
        lines.extend(
            [
                f"### {html_escape(display_name)} {{: #{build_anchor_id(process.process_id)} }}",
                "",
            ]
        )

        if process.has_field("description"):
            description, _ = process.get_value_one("description")
            if description is not None:
                lines.extend([sanitize_markdown_description(str(description)), ""])

        if is_resolved_process_source_not_applicable(process):
            lines.extend([f"<p>{SOURCE_STATUS_NOT_APPLICABLE}</p>", ""])
            continue

        sources, required_missing = process.get_value_many("sources")
        effective_sources = _deduplicate_sources(_normalize_sources(sources))
        if not effective_sources:
            lines.extend(
                [
                    f"<p>{red_missing_cell() if required_missing else '-'}</p>",
                    "",
                ]
            )
            continue

        external_links: list[tuple[str, str]] = []
        folder_sources: list[tuple[str, str]] = []
        missing_sources: list[tuple[str, str]] = []
        for source in effective_sources:
            label, target = parse_source_reference(source)
            kind = _classify_source(source, feature_dir)
            if kind == "folder":
                folder_sources.append((label, target))
            elif kind == "missing_folder":
                missing_sources.append((label, target))
            else:
                external_links.append((label, target))

        if external_links:
            lines.append('!!! abstract ""')
            for link_label, link_target in external_links:
                absolute_url = _ensure_absolute_url(link_target)
                if absolute_url is None:
                    lines.append(
                        f"    <p>{red_missing_cell()} unsupported link: {html_escape(link_target)}</p>"
                    )
                else:
                    lines.append(
                        f'    <p><a href="{html_escape(absolute_url)}" target="_blank" rel="noopener noreferrer">'
                        f"{html_escape(link_label)}</a></p>"
                    )
            lines.append("")

        for _source_label, source_target in folder_sources:
            display_label = Path(source_target.replace("\\", "/").rstrip("/")).name
            folder_pages = get_related_pages_for_source(
                source_target, remapped_pages_by_dir
            )
            if not folder_pages:
                folder_pages = _collect_mounted_source_pages(source_target)
            if folder_pages:
                tree = _new_related_tree_node()
                for page in folder_pages:
                    file_title, file_viewer_link, frontmatter = _unpack_document_page(
                        page
                    )
                    tree_parts = _viewer_link_tree_parts(
                        file_viewer_link, source_target
                    )
                    _insert_related_tree_entry(
                        tree,
                        tree_parts or [file_title],
                        file_title,
                        file_viewer_link,
                        frontmatter,
                    )
                lines.append(
                    build_document_tree_card(
                        display_label, tree=tree, href_prefix="../"
                    )
                )
            else:
                lines.append(
                    build_document_tree_card(
                        display_label, empty_message=f"No files in {source_target}/"
                    )
                )
            lines.append("")

        for source_label, source_target in missing_sources:
            display_label = (
                labelize(source_label)
                if source_label == source_target
                else source_label
            )
            missing_cell = (
                repository_missing_cell()
                if _is_missing_assembled_mount(source_target)
                else red_missing_cell()
            )
            lines.append(f'!!! abstract "\U0001f4c1 {html_escape(display_label)}"')
            lines.append(
                f"    <p>{missing_cell} {html_escape(source_target)}/ not found</p>"
            )
            lines.append("")

    return "\n".join(lines).rstrip()


def build_resolved_feature_extra_docs(
    feature: ResolvedFeature,
    remapped_pages_by_dir: dict[str, list[DocumentPage | tuple[str, str]]],
) -> str:
    source_dirs = {
        target
        for group in feature.get_groups()
        for process in group.get_processes()
        for source in get_resolved_sources(process)
        for _, target in [parse_source_reference(source)]
        if _is_path_source(target)
    }
    extra_dirs: dict[str, list[DocumentPage | tuple[str, str]]] = {}
    for source_dir, pages in remapped_pages_by_dir.items():
        if source_dir == "Ungrouped":
            continue
        extra_pages = [
            page
            for page in pages
            if not any(is_page_below_source(page, target) for target in source_dirs)
        ]
        if extra_pages:
            extra_dirs[source_dir] = extra_pages
    if not extra_dirs:
        return ""

    lines: list[str] = ["## Related Documents", ""]
    for folder, pages in sorted(extra_dirs.items()):
        folder_tree = _new_related_tree_node()
        for page in pages:
            file_title, file_viewer_link, frontmatter = _unpack_document_page(page)
            tree_parts = _viewer_link_tree_parts(file_viewer_link, folder)
            _insert_related_tree_entry(
                folder_tree,
                tree_parts or [file_title],
                file_title,
                file_viewer_link,
                frontmatter,
            )
        file_count = _count_related_tree_files(folder_tree)
        file_label = "file" if file_count == 1 else "files"
        lines.append(
            f"<details><summary>&#128193; {html_escape(folder)} ({file_count} {file_label})</summary>"
        )
        lines.extend(_render_related_tree_html(folder_tree, "  "))
        lines.append("</details>")
    return "\n".join(lines).rstrip()


def build_resolved_feature_group_readiness_content(
    feature: ResolvedFeature,
    process_readiness: Mapping[str, ProcessReadiness],
) -> str:
    node_lines: list[str] = []
    style_lines: list[str] = []
    click_lines: list[str] = []
    node_ids: list[str] = []
    for index, group in enumerate(feature.get_groups()):
        process_ids = [process.process_id for process in group.get_processes()]
        summary = summarize_process_readiness(process_ids, dict(process_readiness))
        node_id = f"group{index}"
        node_ids.append(node_id)
        label = _mermaid_readiness_label(group.name, summary.value)
        node_lines.append(f'{node_id}["{label}"]')
        fill_color, text_color = readiness_tier_style(summary.value)
        style_lines.append(f"    style {node_id} fill:{fill_color},color:{text_color}")
        mermaid_url = sanitize_output(f"{group_dir_slug(group.name)}/", target="url")
        tooltip = _mermaid_label_escape(f"Open {group.name}")
        click_lines.append(f'    click {node_id} "{mermaid_url}" "{tooltip}"')

    return _build_ordered_readiness_flowchart(
        node_ids, node_lines, style_lines, click_lines
    )


def build_resolved_group_page_content(
    group_page_template: str,
    group: ResolvedGroup,
    feature: ResolvedFeature,
    feature_dir: Path,
    readiness_weights: ProcessReadinessWeights,
    remapped_pages_by_dir: dict[str, list[DocumentPage | tuple[str, str]]],
) -> str:
    process_readiness = build_resolved_process_readiness_summaries(
        feature, feature_dir, readiness_weights
    )
    process_progress = build_resolved_process_progress_summaries(feature)
    replacements = {
        "[[AUTO:GROUP_NAME]]": html_escape(group.name),
        "[[AUTO:GROUP_READINESS_DETAILS]]": build_resolved_group_process_readiness_content(
            group, process_readiness
        ),
        "[[AUTO:READINESS_FORMULA_NOTE]]": build_readiness_formula_note(
            readiness_weights
        ),
        "[[AUTO:GROUP_PROCESS_DETAILS]]": build_resolved_group_process_details_content(
            group, feature_dir, process_progress
        ),
        "[[AUTO:GROUP_PROCESS_SOURCES]]": build_resolved_group_process_sources_content(
            group,
            feature_dir,
            remapped_pages_by_dir,
        ),
    }
    return render_markdown_template(group_page_template, replacements)


def build_resolved_feature_detail_content(
    feature_template: str,
    feature: ResolvedFeature,
    feature_dir: Path,
    readiness_weights: ProcessReadinessWeights,
    remapped_pages_by_dir: dict[str, list[DocumentPage | tuple[str, str]]],
    section_name: str = DEFAULT_SECTION_NAME,
) -> str:
    feature_summary_row = build_resolved_feature_summary_row(
        feature, feature_dir, readiness_weights, section_name=section_name
    )
    process_readiness = build_resolved_process_readiness_summaries(
        feature, feature_dir, readiness_weights
    )
    process_ids = [
        process.process_id
        for group in feature.get_groups()
        for process in group.get_processes()
    ]
    feature_readiness = summarize_process_readiness(process_ids, process_readiness)
    replacements = {
        "[[AUTO:FEATURE_NAME]]": escape_cell(
            get_resolved_feature_display_name(feature)
        ),
        "[[AUTO:FEATURE_DESCRIPTION]]": build_resolved_feature_description_content(
            feature
        ),
        "[[AUTO:FEATURE_MAIN_FIELDS]]": build_resolved_main_fields_content(feature),
        "[[AUTO:FEATURE_AGGREGATED_OVERVIEW_TABLE]]": build_feature_summary_table(
            [feature_summary_row], link_feature_name=False, include_feature_column=False
        ),
        "[[AUTO:FEATURE_READINESS_DETAILS]]": build_readiness_details_content(
            feature_readiness, "Feature", include_readiness_value=False
        ),
        "[[AUTO:READINESS_FORMULA_NOTE]]": build_readiness_formula_note(
            readiness_weights
        ),
        "[[AUTO:FEATURE_GROUP_READINESS]]": build_resolved_feature_group_readiness_content(
            feature, process_readiness
        ),
        "[[AUTO:FEATURE_RELATED_DOCS]]": build_resolved_feature_extra_docs(
            feature, remapped_pages_by_dir
        ),
    }
    return render_markdown_template(feature_template, replacements)


def build_resolved_summary_content(
    features: list[tuple[ResolvedFeature, Path]],
    readiness_weights: ProcessReadinessWeights,
    section_name: str = DEFAULT_SECTION_NAME,
) -> str:
    """Return the feature summary table from resolved feature metadata."""
    if not features:
        return f"No items were found in {section_name}.\n"
    return (
        build_feature_summary_table(
            [
                build_resolved_feature_summary_row(
                    feature,
                    feature_dir,
                    readiness_weights,
                    section_name=section_name,
                )
                for feature, feature_dir in features
            ],
            link_feature_name=True,
        )
        + "\n"
    )


def main() -> int:
    features_dir = get_section_root(DEFAULT_SECTION_NAME)
    template_data = load_yaml(get_template_file(DEFAULT_SECTION_NAME))
    feature_field_definitions = collect_feature_field_definitions(template_data)
    process_field_definitions = collect_process_field_definitions(template_data)
    process_ids = {process_id: {} for process_id in process_field_definitions}
    groups = build_effective_groups(collect_groups(template_data), process_ids)
    readiness_weights = load_process_readiness_weights(template_data)

    if not feature_field_definitions and not process_field_definitions:
        raise RuntimeError(
            "No template fields found. Check docs/Features/000_TEMPLATES/overview.yaml"
        )

    feature_template = load_feature_detail_template()
    features = build_resolved_features(
        features_dir,
        feature_field_definitions,
        process_field_definitions,
        groups,
    )
    summary = build_resolved_summary_content(features, readiness_weights)
    print("=== SUMMARY ===")
    print(summary)

    for feature, feature_dir in features:
        related_pages = collect_feature_related_pages(feature_dir)
        detail = build_resolved_feature_detail_content(
            feature_template,
            feature,
            feature_dir,
            readiness_weights,
            related_pages,
        )
        print(f"=== {feature_dir.name} ===")
        print(detail)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
