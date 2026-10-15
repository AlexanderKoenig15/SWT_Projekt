"""Assemble registered content repositories into a linked MkDocs source tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_FILE = REPO_ROOT / "repositories.yaml"
DOCS_DIRECTORY = "docs"
DEFAULT_GITHUB_SERVER_URL = "https://github.siemens.cloud"
DEFAULT_DASHBOARD_REPOSITORY = "AS-IO/Modul-Dashboard"
MANIFEST_VERSION = 3
ASSEMBLY_STATUS_VERSION = 1
ASSEMBLY_STATUS_ENV = "MODUL_DASHBOARD_ASSEMBLY_STATUS_FILE"


def _load_assembly_status(status_file: Path | None = None) -> dict[str, Any]:
    status_file_value = (
        str(status_file)
        if status_file is not None
        else os.environ.get(ASSEMBLY_STATUS_ENV, "").strip()
    )
    if not status_file_value:
        return {"missing_mount_paths": [], "shadowed_sources": []}
    status_path = Path(status_file_value)
    try:
        stat = status_path.stat()
    except OSError as exc:
        raise ValueError(
            f"Could not load local assembly status '{status_path}'."
        ) from exc
    return _read_assembly_status_file(
        str(status_path.resolve()), stat.st_mtime_ns, stat.st_size
    )


@lru_cache(maxsize=8)
def _read_assembly_status_file(
    status_file_value: str,
    modified_time_ns: int,
    file_size: int,
) -> dict[str, Any]:
    del modified_time_ns, file_size
    status_path = Path(status_file_value)
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Could not load local assembly status '{status_path}'."
        ) from exc
    if not isinstance(status, dict) or status.get("version") != ASSEMBLY_STATUS_VERSION:
        raise ValueError(f"Local assembly status '{status_path}' is invalid.")
    return status


def _shadowed_mounts_from_status(
    status: dict[str, Any],
    status_path: Path | None = None,
) -> dict[PurePosixPath, dict[str, str]]:
    entries = status.get("shadowed_sources", [])
    if not isinstance(entries, list):
        raise TypeError(f"Local assembly status '{status_path}' is invalid.")
    mounts: dict[PurePosixPath, dict[str, str]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or any(
            not isinstance(entry.get(key), str) or not entry[key].strip()
            for key in ("id", "repository", "mount_path", "effective_source_id")
        ):
            raise ValueError(f"Local assembly status '{status_path}' is invalid.")
        mounts[PurePosixPath(entry["mount_path"])] = {
            "id": entry["id"],
            "repository": entry["repository"],
            "effective_source_id": entry["effective_source_id"],
        }
    return mounts


def load_missing_mount_paths(
    status_file: Path | None = None,
) -> set[PurePosixPath]:
    """Load registered mount paths omitted from a local partial assembly."""
    status = _load_assembly_status(status_file)
    missing_mount_paths = status.get("missing_mount_paths")
    if not isinstance(missing_mount_paths, list) or any(
        not isinstance(mount_path, str) or not mount_path.strip()
        for mount_path in missing_mount_paths
    ):
        raise ValueError(f"Local assembly status '{status_file}' is invalid.")
    shadowed_mounts = _shadowed_mounts_from_status(status, status_file)
    return {
        PurePosixPath(mount_path)
        for mount_path in missing_mount_paths
        if PurePosixPath(mount_path) not in shadowed_mounts
    }


def load_shadowed_feature_mounts(
    status_file: Path | None = None,
) -> dict[PurePosixPath, dict[str, str]]:
    """Read Feature mounts served from the broader Documents source."""
    return _shadowed_mounts_from_status(_load_assembly_status(status_file), status_file)


@dataclass(frozen=True)
class ContentSource:
    """A repository that owns one mount in the published documentation tree."""

    identifier: str
    repository: str
    mount_path: PurePosixPath


@dataclass(frozen=True)
class AssemblyPlan:
    """Current source ownership and checkout resolution for one assembly."""

    dashboard_root: Path
    sources: tuple[ContentSource, ...]
    checkouts: Mapping[str, Path]
    missing_source_ids: tuple[str, ...]
    shadowed_sources: tuple[dict[str, str], ...]
    root_source: Path | None

    @property
    def shadowed_mount_paths(self) -> frozenset[PurePosixPath]:
        return frozenset(
            PurePosixPath(source["mount_path"]) for source in self.shadowed_sources
        )

    @property
    def missing_mount_paths(self) -> frozenset[PurePosixPath]:
        return frozenset(
            _mount_path(source)
            for source in self.sources
            if source.identifier in self.missing_source_ids
            and _mount_path(source) not in self.shadowed_mount_paths
        )

    def resolve_content_source(
        self, docs_path: str | Path | PurePosixPath
    ) -> ContentSource | None:
        return _select_content_source(
            docs_path, list(self.sources), self.shadowed_mount_paths
        )

    def resolve_docs_path(self, docs_path: str | Path | PurePosixPath) -> Path | None:
        path = _normalize_docs_path(docs_path)
        source = self.resolve_content_source(path)
        if source is None:
            return self.dashboard_root / DOCS_DIRECTORY / path
        checkout = self.checkouts.get(source.identifier)
        if checkout is None:
            return None
        return checkout / path.relative_to(_mount_path(source))

    def template_file(self, section_name: str = "Features") -> Path | None:
        return self.resolve_docs_path(
            PurePosixPath(section_name) / "000_TEMPLATES" / "overview.yaml"
        )

    def is_missing_mount(self, target: str) -> bool:
        normalized_target = target.strip().replace("\\", "/")
        target_path = PurePosixPath(normalized_target)
        if target_path.is_absolute() or not normalized_target:
            return False
        return any(
            target_path == mount_path or mount_path in target_path.parents
            for mount_path in self.missing_mount_paths
        )

    def is_registered_mount(self, target: str) -> bool:
        normalized_target = target.strip().replace("\\", "/")
        target_path = PurePosixPath(normalized_target)
        if target_path.is_absolute() or not normalized_target:
            return False
        source = self.resolve_content_source(target_path)
        return source is not None and _mount_path(source) != PurePosixPath(".")


@dataclass(frozen=True)
class RepositoryEntry:
    """A repository registered for workspace use or published documentation."""

    identifier: str
    repository: str
    workspace: str
    mount_path: PurePosixPath | None
    purpose: str = ""


def _load_yaml(file_path: Path) -> Any:
    return yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}


def _parse_relative_path(
    value: object, field: str, identifier: str, allow_root: bool = False
) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Source '{identifier}' must define a non-empty {field}.")

    path = PurePosixPath(value.strip())
    if (
        path.is_absolute()
        or ".." in path.parts
        or (not allow_root and path == PurePosixPath("."))
    ):
        raise ValueError(
            f"Source '{identifier}' {field} must be a non-empty relative path"
            f"{' or the documentation root' if allow_root else ''}."
        )
    return path


def load_repository_registry(
    registry_file: Path = REGISTRY_FILE,
) -> list[RepositoryEntry]:
    """Load and validate the unified dashboard-owned repository registry."""
    data = _load_yaml(registry_file)
    if not isinstance(data, dict) or data.get("version") != 2:
        raise ValueError(f"{registry_file.name} must define version: 2.")

    raw_repositories = data.get("repositories")
    if not isinstance(raw_repositories, list):
        raise TypeError(f"{registry_file.name} must define a repositories list.")

    repositories: list[RepositoryEntry] = []
    identifiers: set[str] = set()
    repository_names: set[str] = set()
    mount_paths: set[PurePosixPath] = set()
    for index, entry in enumerate(raw_repositories, start=1):
        if not isinstance(entry, dict):
            raise TypeError(
                f"repositories[{index}] in {registry_file.name} must be a mapping."
            )

        identifier = entry.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError(
                f"repositories[{index}] in {registry_file.name} must define a non-empty id."
            )
        identifier = identifier.strip()
        if identifier in identifiers:
            raise ValueError(f"Duplicate repository id '{identifier}'.")
        identifiers.add(identifier)

        repository = entry.get("repository")
        if not isinstance(repository, str) or not repository.strip():
            raise ValueError(
                f"Repository '{identifier}' must define a non-empty repository."
            )
        repository = repository.strip()
        if repository in repository_names:
            raise ValueError(f"Duplicate repository '{repository}'.")
        repository_names.add(repository)

        workspace = entry.get("workspace")
        if workspace not in {"required", "optional"}:
            raise ValueError(
                f"Repository '{identifier}' workspace must be 'required' or 'optional'."
            )

        mount_path = None
        if "mount_path" in entry:
            mount_path = _parse_relative_path(
                entry["mount_path"], "mount_path", identifier, allow_root=True
            )
            if mount_path in mount_paths:
                raise ValueError(f"Duplicate content mount path '{mount_path}'.")
            mount_paths.add(mount_path)

        purpose = entry.get("purpose", "")
        if not isinstance(purpose, str):
            raise TypeError(f"Repository '{identifier}' purpose must be text.")

        repositories.append(
            RepositoryEntry(identifier, repository, workspace, mount_path, purpose)
        )

    if PurePosixPath(".") not in mount_paths:
        raise ValueError("The repository registry must define a published root mount.")

    return repositories


def published_sources(
    repositories: list[RepositoryEntry],
) -> list[ContentSource]:
    """Return only repositories mounted into the published documentation tree."""
    return [
        ContentSource(
            repository.identifier, repository.repository, repository.mount_path
        )
        for repository in repositories
        if repository.mount_path is not None
    ]


def workspace_repositories(
    repositories: list[RepositoryEntry],
) -> list[RepositoryEntry]:
    """Return repositories configured for local workspace checkout."""
    return [
        repository
        for repository in repositories
        if repository.workspace in {"required", "optional"}
    ]


def load_content_sources(registry_file: Path = REGISTRY_FILE) -> list[ContentSource]:
    """Load only repositories mounted into the published documentation tree."""
    return published_sources(load_repository_registry(registry_file))


def discover_sibling_checkouts(
    sources: list[ContentSource] | list[RepositoryEntry], parent_directory: Path
) -> dict[str, Path]:
    """Find registry sources cloned as sibling folders named after their repositories."""
    checkouts: dict[str, Path] = {}
    for source in sources:
        checkout = parent_directory / source.repository.rsplit("/", maxsplit=1)[-1]
        if checkout.is_dir():
            checkouts[source.identifier] = checkout
    return checkouts


def discover_visible_checkouts(
    sources: list[ContentSource], workspace_folders: Sequence[Path]
) -> dict[str, Path]:
    """Match published sources only against explicitly visible workspace folders."""
    normalized_folders = tuple(Path(folder).resolve() for folder in workspace_folders)
    checkouts: dict[str, Path] = {}
    for source in sources:
        expected_name = source.repository.rsplit("/", maxsplit=1)[-1].casefold()
        for folder in normalized_folders:
            if folder.is_dir() and folder.name.casefold() == expected_name:
                checkouts[source.identifier] = folder
                break
    return checkouts


def _normalize_docs_path(value: str | Path | PurePosixPath) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path == PurePosixPath("."):
        raise ValueError("Documentation source paths must be non-empty relative paths.")
    return path


def resolve_content_source(
    docs_path: str | Path | PurePosixPath,
    sources: list[ContentSource],
) -> ContentSource | None:
    """Return the most-specific registered content source owning a docs path."""
    return _select_content_source(
        docs_path, sources, load_shadowed_feature_mounts().keys()
    )


def _select_content_source(
    docs_path: str | Path | PurePosixPath,
    sources: list[ContentSource],
    shadowed_mount_paths: Collection[PurePosixPath],
) -> ContentSource | None:
    path = _normalize_docs_path(docs_path)
    candidates = [
        source
        for source in sources
        if _mount_path(source) == PurePosixPath(".")
        or _mount_path(source) == path
        or _mount_path(source) in path.parents
    ]
    if not candidates:
        return None
    selected = max(candidates, key=lambda source: len(_mount_path(source).parts))
    if _mount_path(selected) in shadowed_mount_paths:
        return next(
            (
                source
                for source in candidates
                if _mount_path(source) == PurePosixPath(".")
            ),
            selected,
        )
    return selected


def _github_server_url() -> str:
    return os.environ.get("GITHUB_SERVER_URL", DEFAULT_GITHUB_SERVER_URL).rstrip("/")


def _dashboard_repository() -> str:
    return os.environ.get("GITHUB_REPOSITORY", DEFAULT_DASHBOARD_REPOSITORY).strip()


def _repository_source_url(
    repository: str,
    relative_path: PurePosixPath,
    view: str,
) -> str:
    base_url = f"{_github_server_url()}/{repository}/{view}/main/"
    if relative_path == PurePosixPath("."):
        return base_url
    return f"{base_url}{quote(relative_path.as_posix(), safe='/')}"


def build_docs_source_url(
    docs_path: str | Path | PurePosixPath,
    sources: list[ContentSource],
) -> str:
    """Build a GitHub file URL from the registered owner of a docs path."""
    path = _normalize_docs_path(docs_path)
    source = resolve_content_source(path, sources)
    if source is None:
        return _repository_source_url(
            _dashboard_repository(), PurePosixPath(DOCS_DIRECTORY) / path, "blob"
        )
    return _repository_source_url(
        source.repository, path.relative_to(_mount_path(source)), "blob"
    )


def build_docs_directory_url(
    docs_path: str | Path | PurePosixPath,
    sources: list[ContentSource],
) -> str:
    """Build a GitHub directory URL from the registered owner of a docs path."""
    path = _normalize_docs_path(docs_path)
    source = resolve_content_source(path, sources)
    if source is None:
        return _repository_source_url(
            _dashboard_repository(), PurePosixPath(DOCS_DIRECTORY) / path, "tree"
        )
    return _repository_source_url(
        source.repository, path.relative_to(_mount_path(source)), "tree"
    )


def build_docs_source_display_path(
    docs_path: str | Path | PurePosixPath,
    sources: list[ContentSource],
) -> str:
    """Return the repository-relative path displayed for a documentation source."""
    path = _normalize_docs_path(docs_path)
    source = resolve_content_source(path, sources)
    if source is None:
        return (PurePosixPath(DOCS_DIRECTORY) / path).as_posix()
    return path.relative_to(_mount_path(source)).as_posix()


def _mount_checkout(checkout: Path, destination: Path) -> None:
    """Mount a live content checkout without requiring Windows symlink privileges."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(destination), str(checkout)],
            capture_output=True,
            check=False,
            errors="replace",
            text=True,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(
                f"Could not mount local checkout '{checkout}': {message}"
            )
        return
    destination.symlink_to(checkout, target_is_directory=True)


def _link_file(source: Path, destination: Path) -> None:
    """Link a file without copying it, using a hard link where Windows blocks symlinks."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.symlink_to(source)
    except OSError:
        try:
            os.link(source, destination)
        except OSError as exc:
            raise RuntimeError(
                f"Could not link local source file '{source}' to '{destination}'."
            ) from exc


def _mount_checkout_contents(checkout: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for child in checkout.iterdir():
        if child.name == ".git":
            continue
        target = destination / child.name
        if child.is_dir():
            _mount_checkout(child, target)
        else:
            _link_file(child, target)


def _remove_path(path: Path) -> None:
    if not os.path.lexists(path):
        return
    is_junction = getattr(path, "is_junction", lambda: False)()
    if path.is_symlink():
        path.unlink()
    elif path.is_dir() and not is_junction:
        shutil.rmtree(path)
    elif path.is_dir():
        path.rmdir()
    else:
        path.unlink()


def _is_descendant_path(path: PurePosixPath, ancestor: PurePosixPath) -> bool:
    return path != ancestor and ancestor in path.parents


def _mount_path(source: ContentSource) -> PurePosixPath:
    return PurePosixPath(source.mount_path.as_posix())


def _is_documents_feature_mount(
    broader_source: ContentSource,
    nested_source: ContentSource,
) -> bool:
    nested_mount = _mount_path(nested_source)
    return (
        _mount_path(broader_source) == PurePosixPath(".")
        and broader_source.repository.rsplit("/", maxsplit=1)[-1].casefold()
        == "modul-documents"
        and len(nested_mount.parts) == 2
        and nested_mount.parts[0] == "Features"
    )


def _shadowed_feature_sources(
    sources: list[ContentSource],
    checkouts: dict[str, Path],
) -> list[dict[str, str]]:
    """Describe direct Feature mounts whose Documents directory remains present."""
    documents_source = next(
        (
            source
            for source in sources
            if _mount_path(source) == PurePosixPath(".")
            and source.repository.rsplit("/", maxsplit=1)[-1].casefold()
            == "modul-documents"
        ),
        None,
    )
    if documents_source is None:
        return []
    documents_checkout = checkouts.get(documents_source.identifier)
    if documents_checkout is None:
        return []

    shadowed: list[dict[str, str]] = []
    for source in sources:
        if not _is_documents_feature_mount(documents_source, source):
            continue
        mount_path = _mount_path(source)
        if not documents_checkout.joinpath(*mount_path.parts).is_dir():
            continue
        shadowed.append(
            {
                "id": source.identifier,
                "repository": source.repository,
                "mount_path": mount_path.as_posix(),
                "effective_source_id": documents_source.identifier,
            }
        )
    return shadowed


def _validate_shadowed_descendant_mounts(
    sources: list[ContentSource],
    shadowed_sources: list[dict[str, str]],
) -> None:
    shadowed_mounts = {
        PurePosixPath(source["mount_path"]) for source in shadowed_sources
    }
    for source in sources:
        mount_path = _mount_path(source)
        if any(
            shadowed_mount in mount_path.parents for shadowed_mount in shadowed_mounts
        ):
            raise ValueError(
                f"Source '{source.identifier}' is nested below shadowed Feature "
                f"mount '{next(shadowed_mount for shadowed_mount in shadowed_mounts if shadowed_mount in mount_path.parents)}' "
                "and cannot be assembled while the legacy Documents directory is effective."
            )


def _source_for_mount(
    sources: list[ContentSource],
    checkouts: dict[str, Path],
    mount_path: PurePosixPath,
) -> Path | None:
    for source in sources:
        if _mount_path(source) == mount_path:
            return checkouts.get(source.identifier)
    return None


def _validate_nested_mount_collisions(
    sources: list[ContentSource],
    checkouts: dict[str, Path],
) -> None:
    """Reject content at a nested mount path in any broader source checkout."""
    for broader_source in sources:
        broader_checkout = checkouts.get(broader_source.identifier)
        if broader_checkout is None:
            continue
        broader_mount = _mount_path(broader_source)
        for nested_source in sources:
            nested_mount = _mount_path(nested_source)
            if not _is_descendant_path(nested_mount, broader_mount):
                continue
            nested_relative_path = nested_mount.relative_to(broader_mount)
            collision_path = broader_checkout.joinpath(*nested_relative_path.parts)
            if os.path.lexists(collision_path):
                if collision_path.is_dir() and _is_documents_feature_mount(
                    broader_source, nested_source
                ):
                    continue
                raise ValueError(
                    f"Source '{broader_source.identifier}' contains "
                    f"'{nested_relative_path.as_posix()}', which is reserved for "
                    f"nested source '{nested_source.identifier}' at "
                    f"'{nested_mount.as_posix()}'."
                )


def build_assembly_plan(
    dashboard_root: Path,
    sources: list[ContentSource],
    checkouts: Mapping[str, Path],
    require_all: bool = False,
) -> AssemblyPlan:
    """Resolve current source ownership without materializing a docs tree."""
    checkout_map = dict(checkouts)
    missing_source_ids = tuple(
        source.identifier for source in sources if source.identifier not in checkout_map
    )
    if require_all and missing_source_ids:
        raise ValueError(
            f"Source '{missing_source_ids[0]}' is required but its checkout was not found."
        )

    root_mount = PurePosixPath(".")
    root_source = _source_for_mount(sources, checkout_map, root_mount)
    root_is_registered = any(_mount_path(source) == root_mount for source in sources)
    if root_source is None and root_is_registered:
        root_registry_source = next(
            source for source in sources if _mount_path(source) == root_mount
        )
        raise ValueError(
            f"Root content source '{root_registry_source.identifier}' must be checked out "
            "for local assembly."
        )
    if root_source is None and not root_is_registered:
        root_source = dashboard_root / DOCS_DIRECTORY

    _validate_nested_mount_collisions(sources, checkout_map)
    shadowed_sources = _shadowed_feature_sources(sources, checkout_map)
    _validate_shadowed_descendant_mounts(sources, shadowed_sources)
    return AssemblyPlan(
        dashboard_root=dashboard_root,
        sources=tuple(sources),
        checkouts=checkout_map,
        missing_source_ids=missing_source_ids,
        shadowed_sources=tuple(shadowed_sources),
        root_source=root_source,
    )


def _materialize_docs_node(
    destination: Path,
    mount_path: PurePosixPath,
    source_directory: Path | None,
    sources: list[ContentSource],
    checkouts: dict[str, Path],
    shadowed_mount_paths: set[PurePosixPath],
) -> None:
    nested_sources = [
        source
        for source in sources
        if _is_descendant_path(_mount_path(source), mount_path)
    ]
    if source_directory is not None and not nested_sources:
        _mount_checkout_contents(source_directory, destination)
        return
    if source_directory is None and not nested_sources:
        return

    destination.mkdir(parents=True, exist_ok=True)
    nested_names = {
        _mount_path(source).relative_to(mount_path).parts[0]
        for source in nested_sources
    }
    if source_directory is not None:
        for child in source_directory.iterdir():
            if child.name in nested_names or child.name == ".git":
                continue
            target = destination / child.name
            if child.is_dir():
                _mount_checkout(child, target)
            else:
                _link_file(child, target)

    for name in sorted(nested_names, key=str.lower):
        child_mount = mount_path / name
        if child_mount in shadowed_mount_paths and source_directory is not None:
            candidate = source_directory / name
            child_source = candidate if candidate.is_dir() else None
        else:
            child_source = _source_for_mount(sources, checkouts, child_mount)
        child_is_registered_mount = any(
            _mount_path(source) == child_mount for source in sources
        )
        if (
            child_source is None
            and not child_is_registered_mount
            and source_directory is not None
        ):
            candidate = source_directory / name
            child_source = candidate if candidate.is_dir() else None
        _materialize_docs_node(
            destination / name,
            child_mount,
            child_source,
            sources,
            checkouts,
            shadowed_mount_paths,
        )


def _git_revision(checkout: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        capture_output=True,
        check=False,
        errors="replace",
        text=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"Could not determine Git revision for '{checkout}': {message}"
        )
    return result.stdout.strip()


def build_deployment_manifest(
    dashboard_root: Path,
    registry_file: Path,
    sources: list[ContentSource],
    checkouts: dict[str, Path],
    dashboard_repository: str = "",
    dashboard_ref: str = "",
    assembly_plan: AssemblyPlan | None = None,
) -> dict[str, Any]:
    """Build a reproducibility manifest for an assembled dashboard."""
    assembly_plan = assembly_plan or build_assembly_plan(
        dashboard_root, sources, checkouts, require_all=True
    )
    dashboard_revision = _git_revision(dashboard_root)
    source_revisions = []
    for source in assembly_plan.sources:
        checkout = assembly_plan.checkouts.get(source.identifier)
        if checkout is None:
            raise ValueError(
                f"Source '{source.identifier}' is required for a deployment manifest."
            )
        source_revisions.append(
            {
                "id": source.identifier,
                "repository": source.repository,
                "mount_path": source.mount_path.as_posix(),
                "revision": _git_revision(checkout),
            }
        )

    registry_digest = hashlib.sha256(registry_file.read_bytes()).hexdigest()
    return {
        "version": MANIFEST_VERSION,
        "dashboard": {
            "repository": dashboard_repository,
            "revision": dashboard_revision,
            "ref": dashboard_ref,
        },
        "registry": {
            "path": registry_file.name,
            "dashboard_revision": dashboard_revision,
            "sha256": registry_digest,
        },
        "sources": source_revisions,
        "shadowed_sources": list(assembly_plan.shadowed_sources),
    }


def write_deployment_manifest(
    output_file: Path,
    dashboard_root: Path,
    registry_file: Path,
    sources: list[ContentSource],
    checkouts: dict[str, Path],
    dashboard_repository: str = "",
    dashboard_ref: str = "",
    assembly_plan: AssemblyPlan | None = None,
) -> None:
    """Write a deployment manifest as stable, human-readable JSON."""
    manifest = build_deployment_manifest(
        dashboard_root,
        registry_file,
        sources,
        checkouts,
        dashboard_repository,
        dashboard_ref,
        assembly_plan,
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_assembly_status(
    output_file: Path,
    sources: list[ContentSource],
    missing_source_ids: list[str],
    checkouts: dict[str, Path] | None = None,
    assembly_plan: AssemblyPlan | None = None,
) -> None:
    """Write the missing local content mounts for a partial-build consumer."""
    assembly_plan = assembly_plan or build_assembly_plan(
        REPO_ROOT, sources, checkouts or {}
    )
    sources_by_id = {source.identifier: source for source in assembly_plan.sources}
    missing_mount_paths = [
        _mount_path(sources_by_id[source_id]).as_posix()
        for source_id in missing_source_ids
        if _mount_path(sources_by_id[source_id])
        not in assembly_plan.shadowed_mount_paths
    ]
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(
            {
                "version": ASSEMBLY_STATUS_VERSION,
                "complete": not missing_source_ids,
                "missing_source_ids": missing_source_ids,
                "missing_mount_paths": missing_mount_paths,
                "shadowed_sources": list(assembly_plan.shadowed_sources),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def assemble_preview_workspace(
    dashboard_root: Path,
    output_root: Path,
    sources: list[ContentSource],
    checkouts: dict[str, Path],
    require_all: bool = False,
    manifest_output: Path | None = None,
    dashboard_repository: str = "",
    dashboard_ref: str = "",
) -> list[str]:
    """Create a disposable source tree whose entries link to their owning checkout."""
    _remove_path(output_root)
    assembly_plan = build_assembly_plan(
        dashboard_root, sources, checkouts, require_all=require_all
    )
    _materialize_docs_node(
        output_root,
        PurePosixPath("."),
        assembly_plan.root_source,
        list(assembly_plan.sources),
        dict(assembly_plan.checkouts),
        set(assembly_plan.shadowed_mount_paths),
    )

    if manifest_output is not None:
        write_deployment_manifest(
            manifest_output,
            dashboard_root,
            dashboard_root / REGISTRY_FILE.name,
            sources,
            checkouts,
            dashboard_repository,
            dashboard_ref,
            assembly_plan,
        )

    return list(assembly_plan.missing_source_ids)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / ".local-preview" / "virtual-docs",
        help="Disposable assembled MkDocs documentation source path.",
    )
    parser.add_argument(
        "--checkout-parent",
        type=Path,
        default=REPO_ROOT.parent,
        help="Folder containing sibling content-repository checkouts.",
    )
    parser.add_argument(
        "--require-all",
        action="store_true",
        help="Fail instead of omitting registered sources without local checkouts.",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        help="Write a deployment manifest for the assembled revisions.",
    )
    parser.add_argument(
        "--status-output",
        type=Path,
        help="Write local assembly status JSON for MkDocs hooks.",
    )
    parser.add_argument(
        "--dashboard-repository",
        default="",
        help="Repository identifier to record in the deployment manifest.",
    )
    parser.add_argument(
        "--dashboard-ref",
        default="",
        help="Git ref to record in the deployment manifest.",
    )
    arguments = parser.parse_args()

    sources = load_content_sources()
    checkouts = discover_sibling_checkouts(sources, arguments.checkout_parent)
    missing_sources = assemble_preview_workspace(
        REPO_ROOT,
        arguments.output,
        sources,
        checkouts,
        require_all=arguments.require_all,
        manifest_output=arguments.manifest_output,
        dashboard_repository=arguments.dashboard_repository,
        dashboard_ref=arguments.dashboard_ref,
    )
    if arguments.status_output is not None:
        write_assembly_status(
            arguments.status_output, sources, missing_sources, checkouts
        )
    if missing_sources:
        print(f"Local preview omits sources: {', '.join(missing_sources)}")
    else:
        print("Local preview includes all registered categories.")
    print(f"Assembled workspace: {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
