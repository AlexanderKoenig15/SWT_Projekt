"""Decide whether scheduled reconciliation requires a new Pages deployment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from content_assembly import (
    MANIFEST_VERSION,
    REGISTRY_FILE,
    REPO_ROOT,
    ContentSource,
    load_content_sources,
)
from materialize_content_sources import (
    CONTENT_TOKEN_ENV,
    _authenticated_environment,
    _resolve_revision,
)


def _git_revision(directory: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(directory), "rev-parse", "HEAD"],
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"Could not determine Git revision for '{directory}': {message}"
        )
    return result.stdout.strip()


def build_current_manifest(
    dashboard_root: Path,
    registry_file: Path,
    sources: list[ContentSource],
    token: str,
    dashboard_repository: str,
    dashboard_ref: str,
) -> dict[str, Any]:
    """Build the exact fingerprint of the Dashboard and current source branches."""
    dashboard_revision = _git_revision(dashboard_root)
    environment = _authenticated_environment(token)
    source_entries = []
    for source in sources:
        source_entries.append(
            {
                "id": source.identifier,
                "repository": source.repository,
                "mount_path": source.mount_path.as_posix(),
                "revision": _resolve_revision(source, environment),
            }
        )

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
            "sha256": hashlib.sha256(registry_file.read_bytes()).hexdigest(),
        },
        "sources": source_entries,
    }


def fetch_published_manifest(manifest_url: str) -> dict[str, Any] | None:
    """Return the published deployment manifest, or None when no baseline is available."""
    request = Request(manifest_url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=15) as response:
            data = json.load(response)
    except HTTPError, URLError, OSError, json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def deployment_required(
    current_manifest: dict[str, Any], published_manifest: dict[str, Any] | None
) -> bool:
    """Return whether the published site does not match the current build inputs."""
    if published_manifest is None:
        return True
    if published_manifest.get("dashboard", {}).get("ref") != "refs/heads/main":
        return True
    # The published manifest records the effective Feature fallback for audit.
    # It is derived from the already-compared registry and immutable source
    # revisions, so scheduled preflight must not treat that annotation as an
    # independent build input.
    current_inputs = {
        key: value
        for key, value in current_manifest.items()
        if key != "shadowed_sources"
    }
    published_inputs = {
        key: value
        for key, value in published_manifest.items()
        if key != "shadowed_sources"
    }
    return published_inputs != current_inputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--published-manifest-url",
        required=True,
        help="URL of the deployment manifest from the currently published site.",
    )
    parser.add_argument(
        "--dashboard-repository",
        required=True,
        help="Dashboard repository identifier recorded in deployment manifests.",
    )
    parser.add_argument(
        "--dashboard-ref",
        required=True,
        help="Git ref for the current workflow run.",
    )
    parser.add_argument(
        "--github-output",
        type=Path,
        required=True,
        help="GitHub Actions output file to receive build_required.",
    )
    arguments = parser.parse_args()

    registry_file = REPO_ROOT / REGISTRY_FILE.name
    sources = load_content_sources(registry_file)
    current_manifest = build_current_manifest(
        REPO_ROOT,
        registry_file,
        sources,
        os.environ.get(CONTENT_TOKEN_ENV, ""),
        arguments.dashboard_repository,
        arguments.dashboard_ref,
    )
    build_required = deployment_required(
        current_manifest,
        fetch_published_manifest(arguments.published_manifest_url),
    )
    arguments.github_output.write_text(
        f"build_required={'true' if build_required else 'false'}\n", encoding="utf-8"
    )
    print(
        "Scheduled reconciliation requires a full build."
        if build_required
        else "Scheduled reconciliation inputs match the deployed site; skipping build."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
