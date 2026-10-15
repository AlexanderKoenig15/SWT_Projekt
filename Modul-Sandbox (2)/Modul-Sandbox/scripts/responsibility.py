from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, urlencode

import yaml

POLICY_FILENAME = "responsibility.yaml"
DEFAULT_PROJECT_URL = "https://github.siemens.cloud/AS-IO/Modul-Dashboard"
GITHUB_PROJECT_BASE_URL = "https://github.siemens.cloud"
_POLICY_FIELDS = {
    "responsible",
    "owner",
    "dashboard_request",
    "content_request",
}
_ROUTING_FIELDS = {"github_project", "assignees"}
_GITHUB_PROJECT_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9-]*)/([1-9]\d*)$")
_GITHUB_LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


@dataclass(frozen=True)
class RoutingOverride:
    github_project: str | None = None
    assignees: tuple[str, ...] | None = None
    clear: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.clear and self.github_project is None and self.assignees is None


@dataclass(frozen=True)
class ResponsibilityOverride:
    responsible: str | None = None
    owners: tuple[str, ...] | None = None
    responsible_clear: bool = False
    owners_clear: bool = False
    dashboard_request: RoutingOverride = RoutingOverride()
    content_request: RoutingOverride = RoutingOverride()

    @property
    def is_empty(self) -> bool:
        return (
            self.responsible is None
            and self.owners is None
            and not self.responsible_clear
            and not self.owners_clear
            and self.dashboard_request.is_empty
            and self.content_request.is_empty
        )

    @staticmethod
    def from_routing(routing: tuple[str, list[str]]) -> RoutingOverride:
        return RoutingOverride(github_project=routing[0], assignees=tuple(routing[1]))


@dataclass(frozen=True)
class ResolvedRouting:
    github_project: str | None = None
    assignees: tuple[str, ...] | None = None

    @property
    def complete(self) -> bool:
        return self.github_project is not None and bool(self.assignees)

    @property
    def missing_fields(self) -> tuple[str, ...]:
        missing: list[str] = []
        if self.github_project is None:
            missing.append("github_project")
        if not self.assignees:
            missing.append("assignees")
        return tuple(missing)

    def as_tuple(self) -> tuple[str, list[str]] | None:
        if not self.complete:
            return None
        return self.github_project, list(self.assignees or ())


@dataclass(frozen=True)
class ResolvedResponsibility:
    responsible: str | None = None
    owners: tuple[str, ...] = ()
    dashboard_request: ResolvedRouting = ResolvedRouting()
    content_request: ResolvedRouting = ResolvedRouting()

    @property
    def missing_fields(self) -> tuple[str, ...]:
        missing: list[str] = []
        if self.responsible is None:
            missing.append("responsible")
        if not self.owners:
            missing.append("owner")
        if not self.dashboard_request.complete:
            missing.extend(
                f"dashboard_request.{field_name}"
                for field_name in self.dashboard_request.missing_fields
            )
        if not self.content_request.complete:
            missing.extend(
                f"content_request.{field_name}"
                for field_name in self.content_request.missing_fields
            )
        return tuple(missing)

    @property
    def complete(self) -> bool:
        return not self.missing_fields


def normalize_github_project(value: Any) -> str | None:
    """Return a normalized organization-project shorthand or None when invalid."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    match = _GITHUB_PROJECT_RE.fullmatch(candidate)
    if match is None:
        return None
    return f"{match.group(1)}/{match.group(2)}"


def normalize_assignees(value: Any) -> list[str] | None:
    """Return normalized GitHub logins or None when the value is invalid."""
    if not isinstance(value, list) or not value:
        return None
    assignees: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None
        login = item.strip()
        if not _GITHUB_LOGIN_RE.fullmatch(login) or login in assignees:
            return None
        assignees.append(login)
    return assignees


def normalize_request_routing(value: Any) -> tuple[str, list[str]] | None:
    """Return normalized project and assignees from one request-routing block."""
    if not isinstance(value, Mapping):
        return None
    github_project = normalize_github_project(value.get("github_project"))
    assignees = normalize_assignees(value.get("assignees"))
    if github_project is None or assignees is None:
        return None
    return github_project, assignees


def build_github_project_url(project: str) -> str:
    """Build the browser URL for an organization-scoped GitHub project."""
    owner, number = project.split("/", maxsplit=1)
    return f"{GITHUB_PROJECT_BASE_URL}/orgs/{quote(owner)}/projects/{quote(number)}"


def build_create_issue_url(
    template_name: str,
    github_project: str,
    assignees: list[str],
    page_url: str | None = None,
) -> str:
    """Build an issue-form URL pre-assigned to a project and GitHub logins."""
    repo_url = os.environ.get("PROJECT_URL", DEFAULT_PROJECT_URL).rstrip("/")
    parameters = {
        "template": template_name,
        "projects": github_project,
        "assignees": ",".join(assignees),
    }
    if page_url:
        parameters["location"] = page_url
    return f"{repo_url}/issues/new?{urlencode(parameters)}"


def _normalize_optional_text(value: Any, field_path: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_path} must be a string or null.")
    candidate = value.strip()
    return candidate or None


def _normalize_owner(value: Any, field_path: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    values = value if isinstance(value, list) else [value]
    if not values:
        return ()
    normalized: list[str] = []
    for item in values:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_path} must contain only non-empty strings.")
        normalized.append(item.strip())
    return tuple(normalized)


def _normalize_routing(
    value: Any, field_path: str, *, present: bool
) -> RoutingOverride:
    if not present:
        return RoutingOverride()
    if value is None:
        return RoutingOverride(clear=True)
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_path} must be a mapping or null.")

    unknown_fields = set(value) - _ROUTING_FIELDS
    if unknown_fields:
        names = ", ".join(sorted(str(field) for field in unknown_fields))
        raise ValueError(f"{field_path} contains unknown field(s): {names}.")

    project = value.get("github_project")
    if isinstance(project, str) and not project.strip():
        project = None
    elif project is not None:
        project = normalize_github_project(project)
        if project is None:
            raise ValueError(
                f"{field_path}.github_project must use the ORG/NUMBER format."
            )

    assignees_value = value.get("assignees")
    if assignees_value is None:
        assignees = None
    elif isinstance(assignees_value, list) and not assignees_value:
        raise ValueError(f"{field_path}.assignees must not be an empty list.")
    else:
        assignees = normalize_assignees(assignees_value)
        if assignees is None:
            raise ValueError(
                f"{field_path}.assignees must contain unique valid GitHub logins."
            )

    return RoutingOverride(
        github_project=project,
        assignees=tuple(assignees) if assignees is not None else None,
    )


def parse_policy_data(
    data: Any, source: str = POLICY_FILENAME
) -> ResponsibilityOverride:
    if data is None:
        return ResponsibilityOverride()
    if not isinstance(data, Mapping):
        raise TypeError(f"{source} must contain a mapping at the root.")

    unknown_fields = set(data) - _POLICY_FIELDS
    if unknown_fields:
        names = ", ".join(sorted(str(field) for field in unknown_fields))
        raise ValueError(f"{source} contains unknown field(s): {names}.")

    responsible_present = "responsible" in data
    owner_present = "owner" in data
    responsible = _normalize_optional_text(
        data.get("responsible"), f"{source}.responsible"
    )
    owners = _normalize_owner(data.get("owner"), f"{source}.owner")
    if owner_present and owners == ():
        owners = None
    return ResponsibilityOverride(
        responsible=responsible,
        owners=owners,
        responsible_clear=responsible_present and responsible is None,
        owners_clear=owner_present and owners is None,
        dashboard_request=_normalize_routing(
            data.get("dashboard_request"),
            f"{source}.dashboard_request",
            present="dashboard_request" in data,
        ),
        content_request=_normalize_routing(
            data.get("content_request"),
            f"{source}.content_request",
            present="content_request" in data,
        ),
    )


def load_policy_file(policy_file: Path) -> ResponsibilityOverride:
    if not policy_file.is_file():
        return ResponsibilityOverride()
    try:
        data = yaml.safe_load(policy_file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"{policy_file} contains invalid YAML.") from exc
    return parse_policy_data(data, policy_file.as_posix())


def _merge_routing(
    current: ResolvedRouting, override: RoutingOverride
) -> ResolvedRouting:
    if override.clear:
        return ResolvedRouting()
    return ResolvedRouting(
        github_project=(
            override.github_project
            if override.github_project is not None
            else current.github_project
        ),
        assignees=(
            override.assignees if override.assignees is not None else current.assignees
        ),
    )


def _merge_routing_overrides(
    current: RoutingOverride, override: RoutingOverride
) -> RoutingOverride:
    if override.clear:
        return override
    if override.is_empty:
        return current
    return RoutingOverride(
        github_project=(
            override.github_project
            if override.github_project is not None
            else current.github_project
        ),
        assignees=(
            override.assignees if override.assignees is not None else current.assignees
        ),
    )


def merge_responsibility_overrides(
    current: ResponsibilityOverride, override: ResponsibilityOverride
) -> ResponsibilityOverride:
    """Merge sparse policy layers before applying them to a page."""
    return ResponsibilityOverride(
        responsible=(
            override.responsible
            if override.responsible is not None
            else current.responsible
        ),
        owners=override.owners if override.owners is not None else current.owners,
        responsible_clear=(
            override.responsible_clear
            or (current.responsible_clear and override.responsible is None)
        ),
        owners_clear=override.owners_clear
        or (current.owners_clear and override.owners is None),
        dashboard_request=_merge_routing_overrides(
            current.dashboard_request, override.dashboard_request
        ),
        content_request=_merge_routing_overrides(
            current.content_request, override.content_request
        ),
    )


def merge_responsibility(
    current: ResolvedResponsibility, override: ResponsibilityOverride
) -> ResolvedResponsibility:
    return ResolvedResponsibility(
        responsible=(
            None
            if override.responsible_clear
            else override.responsible
            if override.responsible is not None
            else current.responsible
        ),
        owners=(
            ()
            if override.owners_clear
            else override.owners
            if override.owners is not None
            else current.owners
        ),
        dashboard_request=_merge_routing(
            current.dashboard_request, override.dashboard_request
        ),
        content_request=_merge_routing(
            current.content_request, override.content_request
        ),
    )


def _normalized_source_path(source_uri: str) -> PurePosixPath:
    normalized = source_uri.replace("\\", "/").strip("/")
    source_path = PurePosixPath(normalized or "index.md")
    if source_path.is_absolute() or ".." in source_path.parts:
        raise ValueError(f"Source URI '{source_uri}' must stay below the docs root.")
    return source_path


def _policy_directories(source_path: PurePosixPath) -> tuple[PurePosixPath, ...]:
    directory = source_path.parent
    if directory == PurePosixPath("."):
        return (PurePosixPath("."),)
    ancestors = tuple(
        parent for parent in reversed(directory.parents) if parent != PurePosixPath(".")
    )
    return (PurePosixPath("."), *ancestors, directory)


def normalize_frontmatter_owner(value: Any) -> tuple[str, ...] | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, list) and not value:
        return None
    if isinstance(value, list):
        filtered = [item for item in value if item is not None and item != ""]
        if not filtered:
            return None
        value = filtered
    return _normalize_owner(value, "frontmatter.owner")


def resolve_responsibility(
    docs_root: Path,
    source_uri: str,
    *,
    frontmatter_owner: Any = None,
    extra_overrides: Iterable[ResponsibilityOverride] = (),
) -> ResolvedResponsibility:
    source_path = _normalized_source_path(source_uri)
    resolved = ResolvedResponsibility()
    for directory in _policy_directories(source_path):
        policy_file = docs_root / directory / POLICY_FILENAME
        resolved = merge_responsibility(resolved, load_policy_file(policy_file))
    for override in extra_overrides:
        resolved = merge_responsibility(resolved, override)
    owners = normalize_frontmatter_owner(frontmatter_owner)
    if owners is not None:
        resolved = merge_responsibility(resolved, ResponsibilityOverride(owners=owners))
    return resolved
