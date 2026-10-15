from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml
from content_assembly import (
    ASSEMBLY_STATUS_ENV,
    assemble_preview_workspace,
    discover_sibling_checkouts,
    load_content_sources,
    write_assembly_status,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
COVERAGE_SOURCE = "scripts"
COVERAGE_THRESHOLD = 85
DEFAULT_LOCAL_DOCS_DIRECTORY = REPO_ROOT / ".local-preview" / "virtual-docs"
DEFAULT_LOCAL_SITE_DIRECTORY = REPO_ROOT / ".local-preview" / "site"
DEFAULT_LOCAL_ASSEMBLY_STATUS_FILE = (
    REPO_ROOT / ".local-preview" / "content-assembly-status.json"
)
LOCAL_PREVIEW_ENVIRONMENT_VARIABLES = (
    "LOCAL_PREVIEW_NOTICE",
    ASSEMBLY_STATUS_ENV,
    "MODUL_DASHBOARD_DOCS_DIR",
    "MODUL_DASHBOARD_SITE_DIR",
    "PAGES_URL",
)


def _run(command: list[str]) -> int:
    print(f"==> {' '.join(command[2:])}", flush=True)
    result = subprocess.run(command, cwd=REPO_ROOT, check=False)
    return result.returncode


def _run_ruff() -> int:
    format_status = _run([sys.executable, "-m", "ruff", "format", "--check", "scripts"])
    lint_status = _run([sys.executable, "-m", "ruff", "check", "scripts"])
    return format_status or lint_status


def _validate_content_sources() -> int:
    try:
        load_content_sources()
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        print(f"Content source registry validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


def _run_tests() -> int:
    saved_environment = {
        name: os.environ.pop(name)
        for name in LOCAL_PREVIEW_ENVIRONMENT_VARIABLES
        if name in os.environ
    }
    try:
        return _run(
            [
                sys.executable,
                "-m",
                "coverage",
                "run",
                f"--source={COVERAGE_SOURCE}",
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
            ]
        )
    finally:
        os.environ.update(saved_environment)


def _run_coverage_report() -> int:
    return _run(
        [
            sys.executable,
            "-m",
            "coverage",
            "report",
            "--show-missing",
            f"--fail-under={COVERAGE_THRESHOLD}",
        ]
    )


def _run_build() -> int:
    if not os.environ.get("MODUL_DASHBOARD_DOCS_DIR", "").strip():
        try:
            sources = load_content_sources()
            checkouts = discover_sibling_checkouts(sources, REPO_ROOT.parent)
            missing_sources = assemble_preview_workspace(
                REPO_ROOT,
                DEFAULT_LOCAL_DOCS_DIRECTORY,
                sources,
                checkouts,
            )
        except (OSError, RuntimeError, TypeError, ValueError, yaml.YAMLError) as exc:
            print(f"Local content assembly failed: {exc}", file=sys.stderr)
            return 1
        if missing_sources:
            print(f"Local validation omits sources: {', '.join(missing_sources)}")
            os.environ["LOCAL_PREVIEW_NOTICE"] = (
                "This local preview may be incomplete. Registered source repositories "
                "without local checkouts are reported; a path may still be served from "
                "an available fallback source. Central CI validates the complete site."
            )
        write_assembly_status(
            DEFAULT_LOCAL_ASSEMBLY_STATUS_FILE,
            sources,
            missing_sources,
            checkouts,
        )
        os.environ[ASSEMBLY_STATUS_ENV] = str(DEFAULT_LOCAL_ASSEMBLY_STATUS_FILE)
        os.environ["MODUL_DASHBOARD_DOCS_DIR"] = str(DEFAULT_LOCAL_DOCS_DIRECTORY)
        # Keep a direct local run out of the repository-root build output that
        # central assembly publishes to Pages.
        os.environ.setdefault(
            "MODUL_DASHBOARD_SITE_DIR", str(DEFAULT_LOCAL_SITE_DIRECTORY)
        )

    return _run([sys.executable, "-m", "mkdocs", "build", "--strict"])


def main() -> int:
    if _validate_content_sources() != 0:
        return 1

    if _run_ruff() != 0:
        return 1

    if _run_tests() != 0:
        return 1

    if _run_coverage_report() != 0:
        return 1

    return _run_build()


if __name__ == "__main__":
    raise SystemExit(main())
