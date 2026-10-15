"""Report repository and optional content visibility in an explicit workspace."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from content_assembly import (
    DEFAULT_DASHBOARD_REPOSITORY,
    REGISTRY_FILE,
    RepositoryEntry,
    load_repository_registry,
)

DASHBOARD_ID = "dashboard"
INVENTORY_VERSION = 2


@dataclass(frozen=True)
class RepositoryVisibility:
    identifier: str
    repository: str
    workspace: str
    mount_path: str | None
    purpose: str
    status: str
    workspace_path: str | None


@dataclass(frozen=True)
class ContentObservation:
    source_id: str
    name: str
    path: str
    kind: str
    publication_status: str = "observed"


@dataclass(frozen=True)
class WorkspaceInventory:
    workspace_folders: tuple[str, ...]
    repositories: tuple[RepositoryVisibility, ...]
    unknown_workspace_folders: tuple[str, ...]
    warnings: tuple[str, ...]
    content_scope: str
    categories: tuple[ContentObservation, ...]
    features: tuple[ContentObservation, ...]

    @property
    def unavailable_repository_ids(self) -> tuple[str, ...]:
        return tuple(
            repository.identifier
            for repository in self.repositories
            if repository.status != "available"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": INVENTORY_VERSION,
            "workspace_folders": list(self.workspace_folders),
            "repositories": [asdict(repository) for repository in self.repositories],
            "unavailable_repository_ids": list(self.unavailable_repository_ids),
            "unknown_workspace_folders": list(self.unknown_workspace_folders),
            "warnings": list(self.warnings),
            "content_scope": self.content_scope,
            "categories": [asdict(observation) for observation in self.categories],
            "features": [asdict(observation) for observation in self.features],
        }


def _dashboard_entry() -> RepositoryEntry:
    return RepositoryEntry(
        DASHBOARD_ID,
        DEFAULT_DASHBOARD_REPOSITORY,
        "required",
        None,
        "Dashboard configuration and scripts",
    )


def _repository_folder_name(repository: str) -> str:
    return repository.rsplit("/", maxsplit=1)[-1]


def _normalize_workspace_folders(
    workspace_folders: Sequence[str | Path],
) -> tuple[Path, ...]:
    normalized: list[Path] = []
    seen: set[Path] = set()
    for value in workspace_folders:
        path = Path(value).resolve()
        if path not in seen:
            normalized.append(path)
            seen.add(path)
    return tuple(normalized)


def _match_workspace_folder(
    repository: RepositoryEntry,
    workspace_folders: tuple[Path, ...],
) -> Path | None:
    expected_name = _repository_folder_name(repository.repository).casefold()
    for folder in workspace_folders:
        if folder.is_dir() and folder.name.casefold() == expected_name:
            return folder
    return None


def _load_yaml(path: Path) -> Any:
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _category_observations(
    source_id: str,
    source_root: Path,
) -> list[ContentObservation]:
    data = _load_yaml(source_root / "categories.yaml")
    raw_categories = data.get("categories") if isinstance(data, dict) else None
    observations: list[ContentObservation] = []
    if isinstance(raw_categories, list):
        for item in raw_categories:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                continue
            category_path = PurePosixPath(item["path"])
            if category_path.is_absolute() or ".." in category_path.parts:
                continue
            target = source_root.joinpath(*category_path.parts)
            if not target.is_dir():
                continue
            name = str(item.get("title") or category_path.name)
            observations.append(
                ContentObservation(
                    source_id, name, category_path.as_posix(), "category"
                )
            )
        return observations

    for child in sorted(source_root.iterdir(), key=lambda path: path.name.casefold()):
        if child.is_dir() and not child.name.startswith("."):
            observations.append(
                ContentObservation(source_id, child.name, child.name, "category")
            )
    return observations


def _feature_observations(
    source_id: str,
    source_root: Path,
    nested_feature_mounts: set[PurePosixPath],
) -> list[ContentObservation]:
    from generate_features_dashboard import collect_feature_dirs

    features_root = source_root / "Features"
    if not features_root.is_dir():
        return []
    observations: list[ContentObservation] = []
    for feature_dir in collect_feature_dirs(features_root):
        feature_mount = PurePosixPath("Features") / feature_dir.name
        has_overview = (feature_dir / "overview.yaml").is_file()
        is_fallback = feature_mount in nested_feature_mounts
        if is_fallback and not has_overview:
            publication_status = "fallback-effective; pending metadata"
        elif is_fallback:
            publication_status = "fallback-effective"
        elif not has_overview:
            publication_status = "pending metadata"
        else:
            publication_status = "effective"
        observations.append(
            ContentObservation(
                source_id,
                feature_dir.name,
                feature_dir.relative_to(source_root).as_posix(),
                "feature",
                publication_status,
            )
        )
    return observations


def _nested_feature_observation(
    source: RepositoryEntry,
    source_root: Path,
    documents_root: Path | None,
) -> ContentObservation | None:
    if source.mount_path is None or not source.mount_path.parts:
        return None
    if source.mount_path.parts[0].casefold() != "features":
        return None
    is_direct_feature_mount = len(source.mount_path.parts) == 2
    legacy_path = (
        documents_root.joinpath(*source.mount_path.parts)
        if documents_root is not None and is_direct_feature_mount
        else None
    )
    if legacy_path is not None and legacy_path.is_dir():
        return ContentObservation(
            source.identifier,
            source.mount_path.parts[-1],
            ".",
            "feature",
            "shadowed by Modul-Documents",
        )

    overview = _load_yaml(source_root / "overview.yaml")
    name = overview.get("feature_name") if isinstance(overview, dict) else None
    if not isinstance(name, str) or not name.strip():
        name = _repository_folder_name(source.repository)
    if not (source_root / "overview.yaml").is_file():
        publication_status = "pending metadata"
    else:
        publication_status = "effective"
    return ContentObservation(
        source.identifier,
        name.strip(),
        ".",
        "feature",
        publication_status,
    )


def _observe_content(
    repositories: Sequence[tuple[RepositoryEntry, Path | None]],
) -> tuple[list[ContentObservation], list[ContentObservation]]:
    categories: list[ContentObservation] = []
    features: list[ContentObservation] = []
    documents_root = next(
        (
            workspace_path
            for source, workspace_path in repositories
            if workspace_path is not None
            and source.mount_path == PurePosixPath(".")
            and _repository_folder_name(source.repository).casefold()
            == "modul-documents"
        ),
        None,
    )
    nested_feature_mounts = {
        source.mount_path
        for source, _ in repositories
        if source.mount_path is not None
        and len(source.mount_path.parts) == 2
        and source.mount_path.parts[0] == "Features"
    }
    for source, workspace_path in repositories:
        if workspace_path is None or source.mount_path is None:
            continue
        if source.mount_path == PurePosixPath("."):
            categories.extend(_category_observations(source.identifier, workspace_path))
            features.extend(
                _feature_observations(
                    source.identifier, workspace_path, nested_feature_mounts
                )
            )
        else:
            nested_feature = _nested_feature_observation(
                source, workspace_path, documents_root
            )
            if nested_feature is not None:
                features.append(nested_feature)
    return categories, features


def build_workspace_inventory(
    workspace_folders: Sequence[str | Path],
    registry_file: Path = REGISTRY_FILE,
    include_content: bool = False,
) -> WorkspaceInventory:
    """Classify only repositories represented by explicit workspace folders."""
    folders = _normalize_workspace_folders(workspace_folders)
    entries = [_dashboard_entry(), *load_repository_registry(registry_file)]
    repository_rows: list[RepositoryVisibility] = []
    repository_paths: list[tuple[RepositoryEntry, Path | None]] = []
    warnings: list[str] = []

    for entry in entries:
        workspace_path = _match_workspace_folder(entry, folders)
        if workspace_path is None:
            status = "unavailable-in-current-workspace"
            workspace_path_value = None
        else:
            status = "available"
            workspace_path_value = str(workspace_path)
        repository_rows.append(
            RepositoryVisibility(
                entry.identifier,
                entry.repository,
                entry.workspace,
                entry.mount_path.as_posix() if entry.mount_path is not None else None,
                entry.purpose,
                status,
                workspace_path_value,
            )
        )
        repository_paths.append((entry, workspace_path))

    known_names = {
        _repository_folder_name(entry.repository).casefold() for entry in entries
    }
    unknown_folders = tuple(
        str(folder) for folder in folders if folder.name.casefold() not in known_names
    )
    invalid_folders = [str(folder) for folder in folders if not folder.is_dir()]
    if invalid_folders:
        warnings.append(
            "Explicit workspace folder is missing or not a directory: "
            + ", ".join(invalid_folders)
        )
    if unknown_folders:
        warnings.append(
            "Explicit workspace folders do not match a configured repository: "
            + ", ".join(unknown_folders)
        )

    content_sources_missing = any(
        entry.mount_path is not None and workspace_path is None
        for entry, workspace_path in repository_paths
    )
    categories: list[ContentObservation] = []
    features: list[ContentObservation] = []
    content_scope = "not-requested"
    if include_content:
        categories, features = _observe_content(repository_paths)
        content_scope = "partial" if content_sources_missing else "observed"
        if content_sources_missing:
            warnings.append(
                "Content observations are partial because one or more published "
                "sources are unavailable in the current workspace."
            )

    return WorkspaceInventory(
        tuple(str(folder) for folder in folders),
        tuple(repository_rows),
        unknown_folders,
        tuple(warnings),
        content_scope,
        tuple(categories),
        tuple(features),
    )


def render_text(inventory: WorkspaceInventory) -> str:
    lines = ["Workspace inventory", "", "Repositories:"]
    for repository in inventory.repositories:
        label = (
            "available"
            if repository.status == "available"
            else "unavailable in current workspace"
        )
        lines.append(f"- {repository.identifier}: {label}")
    if inventory.unknown_workspace_folders:
        lines.extend(["", "Unmatched workspace folders:"])
        lines.extend(f"- {path}" for path in inventory.unknown_workspace_folders)
    if inventory.content_scope != "not-requested":
        lines.extend(["", f"Content observations: {inventory.content_scope}"])
        lines.append("Categories:")
        lines.extend(
            f"- {observation.name} ({observation.source_id})"
            for observation in inventory.categories
        )
        lines.append("Features:")
        lines.extend(
            f"- {observation.name} ({observation.source_id}; {observation.publication_status})"
            for observation in inventory.features
        )
    if inventory.warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in inventory.warnings)
    return "\n".join(lines)


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace-folder",
        action="append",
        type=Path,
        required=True,
        help="Explicit workspace folder; repeat for each visible repository.",
    )
    parser.add_argument("--registry-file", type=Path, default=REGISTRY_FILE)
    parser.add_argument(
        "--include-content",
        action="store_true",
        help="Observe categories and Features from visible content sources.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parsed = parser.parse_args(arguments)
    inventory = build_workspace_inventory(
        parsed.workspace_folder,
        parsed.registry_file,
        include_content=parsed.include_content,
    )
    if parsed.format == "json":
        print(json.dumps(inventory.to_dict(), indent=2, sort_keys=True))
    else:
        print(render_text(inventory))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
