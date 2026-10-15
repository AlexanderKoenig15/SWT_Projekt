"""Materialize registered content repositories at immutable revisions for assembly."""

from __future__ import annotations

import argparse
import base64
import os
import re
import subprocess
from pathlib import Path

from content_assembly import (
    REPO_ROOT,
    ContentSource,
    discover_sibling_checkouts,
    load_content_sources,
)

DEFAULT_CHECKOUT_PARENT = REPO_ROOT / ".local-preview" / "materialized-sources"
CONTENT_TOKEN_ENV = "MODUL_DASHBOARD_CONTENT_TOKEN"
DEFAULT_SERVER_URL = "https://github.siemens.cloud"
REVISION_PATTERN = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?$")


def _authenticated_environment(token: str) -> dict[str, str]:
    if not token:
        raise ValueError(f"{CONTENT_TOKEN_ENV} must be set for content checkout.")
    credentials = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    environment = os.environ.copy()
    environment["GIT_CONFIG_COUNT"] = "1"
    environment["GIT_CONFIG_KEY_0"] = "http.extraheader"
    environment["GIT_CONFIG_VALUE_0"] = f"AUTHORIZATION: basic {credentials}"
    return environment


def _run_git(arguments: list[str], environment: dict[str, str]) -> str:
    result = subprocess.run(
        ["git", *arguments],
        capture_output=True,
        check=False,
        encoding="utf-8",
        env=environment,
        errors="replace",
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Git command failed: {' '.join(arguments)}: {message}")
    return result.stdout.strip()


def _repository_url(source: ContentSource) -> str:
    server_url = os.environ.get("GITHUB_SERVER_URL", DEFAULT_SERVER_URL).rstrip("/")
    return f"{server_url}/{source.repository}.git"


def _resolve_revision(source: ContentSource, environment: dict[str, str]) -> str:
    output = _run_git(
        ["ls-remote", "--exit-code", _repository_url(source), "refs/heads/main"],
        environment,
    )
    revision = output.split(maxsplit=1)[0].lower() if output else ""
    if not REVISION_PATTERN.fullmatch(revision):
        raise RuntimeError(
            f"Could not resolve an immutable main revision for '{source.repository}'."
        )
    return revision


def _validate_revision(identifier: str, revision: str) -> str:
    normalized = revision.lower()
    if not REVISION_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"Revision for source '{identifier}' must be a 40- or 64-character Git SHA."
        )
    return normalized


def materialize_content_sources(
    sources: list[ContentSource],
    checkout_parent: Path,
    token: str,
    revisions: dict[str, str] | None = None,
) -> dict[str, str]:
    """Check out all registered sources at supplied or resolved immutable revisions."""
    revisions = revisions or {}
    unknown_identifiers = set(revisions) - {source.identifier for source in sources}
    if unknown_identifiers:
        names = ", ".join(sorted(unknown_identifiers))
        raise ValueError(f"Revisions reference unknown content source IDs: {names}.")

    environment = _authenticated_environment(token)
    checkout_parent.mkdir(parents=True, exist_ok=True)
    resolved_revisions: dict[str, str] = {}
    for source in sources:
        revision = revisions.get(source.identifier)
        if revision is None:
            revision = _resolve_revision(source, environment)
        else:
            revision = _validate_revision(source.identifier, revision)

        checkout = checkout_parent / source.repository.rsplit("/", maxsplit=1)[-1]
        if checkout.exists():
            raise ValueError(f"Checkout destination already exists: {checkout}")
        _run_git(["init", str(checkout)], environment)
        _run_git(
            ["-C", str(checkout), "remote", "add", "origin", _repository_url(source)],
            environment,
        )
        _run_git(
            ["-C", str(checkout), "fetch", "--depth=1", "origin", revision], environment
        )
        actual_revision = _run_git(
            ["-C", str(checkout), "rev-parse", "FETCH_HEAD"], environment
        ).lower()
        if actual_revision != revision:
            raise RuntimeError(
                f"Checkout for '{source.identifier}' resolved '{actual_revision}', expected '{revision}'."
            )
        _run_git(["-C", str(checkout), "checkout", "--detach", revision], environment)
        resolved_revisions[source.identifier] = revision
        print(f"Materialized {source.identifier} at {revision}")

    return resolved_revisions


def _parse_revisions(values: list[str]) -> dict[str, str]:
    revisions: dict[str, str] = {}
    for value in values:
        identifier, separator, revision = value.partition("=")
        if not separator or not identifier or not revision:
            raise ValueError("Each --revision value must use source-id=immutable-sha.")
        if identifier in revisions:
            raise ValueError(f"Duplicate revision supplied for source '{identifier}'.")
        revisions[identifier] = revision
    return revisions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkout-parent",
        type=Path,
        default=DEFAULT_CHECKOUT_PARENT,
        help="Empty directory in which source repositories are materialized.",
    )
    parser.add_argument(
        "--revision",
        action="append",
        default=[],
        metavar="SOURCE=SHA",
        help="Use a supplied immutable revision for one registered source.",
    )
    arguments = parser.parse_args()
    sources = load_content_sources()
    materialize_content_sources(
        sources,
        arguments.checkout_parent,
        os.environ.get(CONTENT_TOKEN_ENV, ""),
        _parse_revisions(arguments.revision),
    )
    checkouts = discover_sibling_checkouts(sources, arguments.checkout_parent)
    if len(checkouts) != len(sources):
        raise RuntimeError("Not every registered content source was materialized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
