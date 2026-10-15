"""Strictly validate a complete pre-materialized content-repository assembly."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from content_assembly import (
    ASSEMBLY_STATUS_ENV,
    REGISTRY_FILE,
    assemble_preview_workspace,
    discover_sibling_checkouts,
    load_content_sources,
    write_assembly_status,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS_DIRECTORY = REPO_ROOT / ".local-preview" / "assembled-docs"
DEFAULT_MANIFEST_FILE = REPO_ROOT / ".local-preview" / "deployment-manifest.json"
ASSEMBLED_BUILD_ENVIRONMENT_VARIABLES = (
    "LOCAL_PREVIEW_NOTICE",
    "MODUL_DASHBOARD_SITE_DIR",
)


def run_assembled_validation(
    dashboard_root: Path,
    docs_directory: Path,
    checkout_parent: Path,
    manifest_output: Path,
    dashboard_repository: str,
    dashboard_ref: str = "",
) -> int:
    """Assemble every registered source, then run the shared strict validator."""
    registry_file = dashboard_root / REGISTRY_FILE.name
    sources = load_content_sources(registry_file)
    checkouts = discover_sibling_checkouts(sources, checkout_parent)
    assemble_preview_workspace(
        dashboard_root,
        docs_directory,
        sources,
        checkouts,
        require_all=True,
        manifest_output=manifest_output,
        dashboard_repository=dashboard_repository,
        dashboard_ref=dashboard_ref,
    )
    assembly_status_file = docs_directory.parent / "content-assembly-status.json"
    write_assembly_status(assembly_status_file, sources, [], checkouts)

    environment = os.environ.copy()
    environment["MODUL_DASHBOARD_DOCS_DIR"] = str(docs_directory)
    for name in ASSEMBLED_BUILD_ENVIRONMENT_VARIABLES:
        environment.pop(name, None)
    environment[ASSEMBLY_STATUS_ENV] = str(assembly_status_file)
    result = subprocess.run(
        [sys.executable, "scripts/validate.py"],
        cwd=dashboard_root,
        env=environment,
        check=False,
    )
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=DEFAULT_DOCS_DIRECTORY,
        help="Disposable linked MkDocs documentation source directory.",
    )
    parser.add_argument(
        "--checkout-parent",
        type=Path,
        default=REPO_ROOT.parent,
        help="Folder containing materialized content-repository checkouts.",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=DEFAULT_MANIFEST_FILE,
        help="Deployment manifest JSON output path.",
    )
    parser.add_argument(
        "--dashboard-repository",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="Dashboard repository identifier to record in the manifest.",
    )
    parser.add_argument(
        "--dashboard-ref",
        default=os.environ.get("GITHUB_REF", ""),
        help="Git ref to record in the manifest.",
    )
    arguments = parser.parse_args()
    return run_assembled_validation(
        REPO_ROOT,
        arguments.docs_dir,
        arguments.checkout_parent,
        arguments.manifest_output,
        arguments.dashboard_repository,
        arguments.dashboard_ref,
    )


if __name__ == "__main__":
    raise SystemExit(main())
