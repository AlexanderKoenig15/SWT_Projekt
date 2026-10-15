"""Configure a repeatable local workspace for the dashboard repositories."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MINIMUM_PYTHON = (3, 14)
TASKS_EXTENSION_ID = "actboy168.tasks"
DEFAULT_SERVER_URL = "https://github.siemens.cloud"
SENSITIVE_CONFIG_KEYS = (
    "credential",
    "extraheader",
    "password",
    "secret",
    "token",
)
URL_CREDENTIALS = re.compile(r"(https?://)([^/@\s]+)@", re.IGNORECASE)


class SetupError(RuntimeError):
    """A user-actionable setup failure."""


@dataclass(frozen=True)
class CheckoutState:
    path: Path
    branch: str
    dirty: bool
    ahead: int
    behind: int
    remote_url: str


def _dashboard_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run(
    command: Sequence[str],
    cwd: Path | None = None,
    check: bool = True,
    stream_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(command),
            cwd=cwd,
            capture_output=not stream_output,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        raise SetupError(
            f"Could not start command '{command[0]}': {exc}. "
            "Check that the required executable is installed and available."
        ) from exc
    if check and result.returncode != 0:
        detail = (result.stderr or "").strip() or (result.stdout or "").strip()
        raise SetupError(
            f"Command failed ({result.returncode}): {' '.join(command)}"
            + (f"\n{detail}" if detail else "")
        )
    return result


def check_prerequisites(require_code: bool = False, announce: bool = False) -> None:
    """Check required executables without installing or changing anything."""
    if sys.version_info[:2] < MINIMUM_PYTHON:
        raise SetupError(
            "Python 3.14 or newer is required. "
            f"The current interpreter is {sys.version.split()[0]}."
        )

    required = {"git": shutil.which("git"), "uv": shutil.which("uv")}
    if require_code:
        required["code"] = shutil.which("code")

    missing = [name for name, executable in required.items() if executable is None]
    if missing:
        requirements = ", ".join(missing)
        raise SetupError(
            f"Required tool(s) not found: {requirements}. "
            "Install them and run the workspace setup again."
        )
    if announce:
        code_status = (
            "available"
            if shutil.which("code") is not None
            else "not found (optional unless opening the workspace)"
        )
        print(
            f"Prerequisites passed: Python 3.14+, Git, uv. VS Code CLI: {code_status}."
        )


def _redact_config_line(line: str) -> str:
    columns = line.split("\t")
    if len(columns) >= 3:
        key = columns[-2]
        if any(secret in key.lower() for secret in SENSITIVE_CONFIG_KEYS):
            columns[-1] = "<redacted>"
            return "\t".join(columns)
    key, separator, _value = line.partition("=")
    if any(secret in key.lower() for secret in SENSITIVE_CONFIG_KEYS):
        return f"{key}{separator}<redacted>"
    return URL_CREDENTIALS.sub(r"\1<redacted>@", line)


def git_global_configuration() -> list[str]:
    """Return global Git configuration with credential-bearing values redacted."""
    result = _run(
        [
            "git",
            "config",
            "--global",
            "--list",
            "--show-origin",
            "--show-scope",
        ],
        check=False,
    )
    if result.returncode != 0:
        raise SetupError(f"Could not read global Git configuration.\n{result.stderr}")
    return [_redact_config_line(line) for line in result.stdout.splitlines()]


def print_global_git_configuration(output: Callable[[str], None] = print) -> None:
    output("Global Git configuration:")
    lines = git_global_configuration()
    if not lines:
        output("  (no configuration entries)")
    for line in lines:
        output(f"  {line}")


def configure_git_longpaths(pause_on_warning: bool = False) -> None:
    """Enable Git long paths and warn when Windows long paths are disabled."""
    current = _run(
        ["git", "config", "--global", "--get", "core.longpaths"], check=False
    )
    if current.returncode != 0 or current.stdout.strip().lower() != "true":
        _run(["git", "config", "--global", "core.longpaths", "true"])

    if os.name != "nt":
        return

    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\FileSystem",
        ) as key:
            enabled, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
    except OSError:
        enabled = 0

    if int(enabled) != 1:
        print(
            "\n"
            "+====================================================================+\n"
            "| WARNING: Windows long-path support is disabled.                    |\n"
            "+====================================================================+\n"
            "| Ask an administrator to set LongPathsEnabled=1 at:                 |\n"
            "| HKLM\\SYSTEM\\CurrentControlSet\\Control\\FileSystem             |\n"
            "|                                                                    |\n"
            "| Restart VS Code and other affected applications after enabling it. |\n"
            "| A full Windows restart is the safest option but is not normally   |\n"
            "| required if all affected processes are restarted.                 |\n"
            "+====================================================================+\n"
        )
        if pause_on_warning:
            input("Press Enter to continue setup...")


def _git(
    checkout: Path,
    *arguments: str,
    check: bool = True,
    stream_output: bool = False,
) -> str:
    result = _run(
        ["git", "-C", str(checkout), *arguments],
        check=check,
        stream_output=stream_output,
    )
    return (result.stdout or "").strip()


def dashboard_repository() -> str:
    """Owner and name of this checkout, read from its 'origin' remote."""
    remote = _git(_dashboard_root(), "remote", "get-url", "origin")
    return re.search(r"[:/]([^/:]+/[^/:]+?)(?:\.git)?/?$", remote)[1]


def workspace_filename() -> str:
    return f"{dashboard_repository().rsplit('/', maxsplit=1)[-1]}.code-workspace"


def _repository_url(repository: str) -> str:
    server = os.environ.get("GITHUB_SERVER_URL", DEFAULT_SERVER_URL).rstrip("/")
    return f"{server}/{repository}.git"


def _repository_path(parent: Path, repository: str) -> Path:
    return parent / repository.rsplit("/", maxsplit=1)[-1]


def _code_command(*arguments: str) -> list[str]:
    executable = shutil.which("code")
    if executable is None:
        raise SetupError(
            "The VS Code CLI ('code') is not available. "
            "Install or enable it before using this option."
        )
    if os.name == "nt" and Path(executable).suffix.lower() in {".cmd", ".bat"}:
        return ["cmd.exe", "/d", "/c", executable, *arguments]
    return [executable, *arguments]


def _is_git_checkout(path: Path) -> bool:
    return (
        path.is_dir()
        and _run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"], check=False
        ).returncode
        == 0
    )


def clone_repository(repository: str, destination: Path) -> None:
    if destination.exists():
        raise SetupError(
            f"Cannot clone {repository}: destination already exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run(
        ["git", "clone", _repository_url(repository), str(destination)],
        stream_output=True,
    )


def _expected_remote(repository: str) -> str:
    return _repository_url(repository).removesuffix(".git").lower()


def _normalize_remote(url: str) -> str:
    normalized = url.strip().rstrip("/").removesuffix(".git")
    if normalized.startswith("git@") and ":" in normalized:
        host, repository = normalized[4:].split(":", maxsplit=1)
        normalized = f"https://{host}/{repository}"
    return normalized.lower()


def checkout_state(path: Path, repository: str) -> CheckoutState:
    if not _is_git_checkout(path):
        raise SetupError(f"Expected a Git checkout at {path} for {repository}.")
    remote_url = _git(path, "remote", "get-url", "origin")
    if _normalize_remote(remote_url) != _expected_remote(repository):
        raise SetupError(
            f"Remote mismatch for {path}: expected {_repository_url(repository)}, "
            f"found {remote_url}."
        )
    branch = _git(path, "branch", "--show-current") or "(detached HEAD)"
    dirty = bool(_git(path, "status", "--porcelain", "--untracked-files=all"))
    counts = _git(
        path, "rev-list", "--left-right", "--count", "HEAD...origin/main", check=False
    )
    if counts:
        ahead, behind = (int(value) for value in counts.split())
    else:
        ahead, behind = 0, 0
    return CheckoutState(path, branch, dirty, ahead, behind, remote_url)


def fetch_and_fast_forward(
    repository: str, path: Path, output: Callable[[str], None] = print
) -> CheckoutState:
    state = checkout_state(path, repository)
    _git(path, "fetch", "origin", stream_output=True)
    state = checkout_state(path, repository)
    if (
        state.branch == "main"
        and not state.dirty
        and state.behind > 0
        and state.ahead == 0
    ):
        _git(path, "merge", "--ff-only", "origin/main", stream_output=True)
        output(f"Fast-forwarded {path.name} to origin/main.")
        state = checkout_state(path, repository)
    elif state.dirty:
        output(f"Skipped update for {path.name}: working tree has changes.")
    elif state.branch != "main":
        output(f"Skipped update for {path.name}: current branch is {state.branch}.")
    elif state.ahead or state.behind:
        output(
            f"Skipped update for {path.name}: local/remote history differs "
            f"(ahead {state.ahead}, behind {state.behind})."
        )
    return state


def _parse_selection(value: str, option_count: int) -> set[int]:
    value = value.strip().lower()
    if not value or value == "none":
        return set()
    if value == "all":
        return set(range(option_count))
    selected: set[int] = set()
    for part in value.split(","):
        try:
            index = int(part.strip()) - 1
        except ValueError as exc:
            raise ValueError(
                "Enter numbers separated by commas, 'all', or 'none'."
            ) from exc
        if index < 0 or index >= option_count:
            raise ValueError(f"Selection {index + 1} is outside the available choices.")
        selected.add(index)
    return selected


def select_multiple(
    prompt: str,
    options: Sequence[str],
    input_function: Callable[[str], str] = input,
    output: Callable[[str], None] = print,
    display_options: bool = True,
) -> set[int]:
    if not options:
        return set()
    output(prompt)
    if display_options:
        for index, option in enumerate(options, start=1):
            output(f"  {index}. {option}")
    while True:
        try:
            return _parse_selection(
                input_function(
                    "Selection (comma-separated, 'all', or 'NONE'; default: NONE): "
                ),
                len(options),
            )
        except ValueError as exc:
            output(f"Invalid selection: {exc}")


def print_optional_repository_list(
    options: Sequence[tuple[str, str]],
    output: Callable[[str], None] = print,
) -> None:
    """Print the stable optional-repository list shared by add/remove prompts."""
    output("Optional repositories:")
    if not options:
        output("  (none registered)")
        return
    for index, (_, label) in enumerate(options, start=1):
        output(f"  {index:>2}. {label}")


def print_required_repository_list(
    options: Sequence[str],
    output: Callable[[str], None] = print,
) -> None:
    """Print required repositories and their current setup status."""
    output("Required repositories:")
    for index, option in enumerate(options, start=1):
        output(f"  {index:>2}. {option}")


def select_action(
    input_function: Callable[[str], str] = input,
    output: Callable[[str], None] = print,
) -> str:
    """Ask what setup operation the user wants to perform."""
    output("")
    options = [
        ("configure", "Configure repositories and workspace"),
        ("git-config", "Show global Git configuration"),
        ("refresh-packages", "Refresh locked Python packages"),
        ("extension", "Install the optional VS Code Tasks extension"),
        ("exit", "Exit setup"),
    ]
    output("Workspace setup actions:")
    for index, (_, label) in enumerate(options, start=1):
        output(f"  {index}. {label}")
    while True:
        value = input_function("Action [1-5]: ").strip().lower()
        if value in {"1", "configure", "c"}:
            return "configure"
        if value in {"2", "git-config", "config", "g"}:
            return "git-config"
        if value in {"3", "refresh-packages", "refresh", "packages", "p"}:
            return "refresh-packages"
        if value in {"4", "extension", "e"}:
            return "extension"
        if value in {"5", "exit", "q", "quit"}:
            return "exit"
        output("Enter 1, 2, 3, 4, or 5.")


def ask_yes_no(
    prompt: str,
    default: bool = False,
    input_function: Callable[[str], str] = input,
) -> bool:
    suffix = "Y/n" if default else "y/N"
    value = input_function(f"{prompt} [{suffix}] ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes"}


def _workspace_path(parent: Path, workspace_name: str) -> Path:
    return parent / workspace_name


def _load_existing_workspace(
    parent: Path, workspace_name: str
) -> tuple[Path, dict[str, Any]]:
    workspace_file = _workspace_path(parent, workspace_name)
    return workspace_file, load_workspace(workspace_file)


def _resolved_workspace_entry(workspace_file: Path, value: str) -> Path:
    entry = Path(value)
    if not entry.is_absolute():
        entry = workspace_file.parent / entry
    return entry.resolve()


def load_workspace(workspace_file: Path) -> dict[str, Any]:
    if not workspace_file.exists():
        return {"folders": [], "settings": {}}
    try:
        document = json.loads(workspace_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupError(
            f"Could not read workspace file {workspace_file}: {exc}"
        ) from exc
    if not isinstance(document, dict) or not isinstance(
        document.get("folders", []), list
    ):
        raise SetupError(
            f"Workspace file must contain a folders list: {workspace_file}"
        )
    document.setdefault("settings", {})
    return document


def write_workspace(
    workspace_file: Path,
    selected_paths: Sequence[Path],
    existing: dict[str, Any],
    managed_paths: Sequence[Path] | None = None,
) -> None:
    selected: list[Path] = []
    selected_resolved: set[Path] = set()
    for path in selected_paths:
        resolved = path.resolve()
        if resolved not in selected_resolved:
            selected.append(resolved)
            selected_resolved.add(resolved)
    managed = {
        path.resolve()
        for path in (managed_paths if managed_paths is not None else selected_paths)
    }
    folders: list[dict[str, str]] = []
    for folder in existing.get("folders", []):
        if not isinstance(folder, dict):
            continue
        if not isinstance(folder.get("path"), str):
            if isinstance(folder.get("uri"), str):
                folders.append(folder)
            continue
        resolved = _resolved_workspace_entry(workspace_file, folder["path"])
        if resolved not in managed:
            folders.append(folder)
    for path in selected:
        relative = os.path.relpath(path, workspace_file.parent).replace(os.sep, "/")
        folders.append({"name": path.name, "path": relative})
    settings = existing.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    settings["git.autofetch"] = True
    document = {
        key: value
        for key, value in existing.items()
        if key not in {"folders", "settings"}
    }
    document["folders"] = folders
    document["settings"] = settings
    workspace_file.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def _source_id_values(values: Sequence[str], known_ids: set[str]) -> set[str]:
    selected: set[str] = set()
    for value in values:
        selected.update(part.strip() for part in value.split(",") if part.strip())
    unknown = selected - known_ids
    if unknown:
        names = ", ".join(sorted(unknown))
        raise SetupError(f"Unknown content source ID(s): {names}.")
    return selected


def _offer_extension(code_available: bool) -> None:
    if not code_available:
        raise SetupError(
            "The VS Code CLI ('code') is not available. "
            "Install or enable it before installing the optional extension."
        )
    if ask_yes_no(
        f"Install optional VS Code Tasks extension ({TASKS_EXTENSION_ID})?", False
    ):
        result = _run(
            _code_command("--install-extension", TASKS_EXTENSION_ID),
            check=False,
            stream_output=True,
        )
        if result.returncode == 0:
            print(f"Installed or verified VS Code extension {TASKS_EXTENSION_ID}.")
        else:
            detail = (result.stderr or "").strip() or (result.stdout or "").strip()
            raise SetupError(
                f"Could not install {TASKS_EXTENSION_ID}."
                + (f"\n{detail}" if detail else "")
            )


def _open_workspace(workspace_file: Path) -> None:
    _run(_code_command("--reuse-window", str(workspace_file)), stream_output=True)


def refresh_packages() -> None:
    """Synchronize the locked project environment."""
    _run(
        ["uv", "sync", "--locked"],
        cwd=_dashboard_root(),
        stream_output=True,
    )


def _remove_readonly_entry(
    function: Callable[[str], None], path: str, exc: BaseException
) -> None:
    if not isinstance(exc, PermissionError):
        raise exc
    os.chmod(path, stat.S_IWRITE)
    function(path)


def _remove_optional_clones(
    removed_ids: Sequence[str],
    source_by_id: dict[str, Any],
    parent: Path,
    confirm_each: bool = True,
) -> None:
    for identifier in removed_ids:
        source = source_by_id[identifier]
        path = _repository_path(parent, source.repository)
        if not path.exists():
            continue
        if confirm_each and not ask_yes_no(f"Delete the clean clone {path}?", False):
            continue
        state = checkout_state(path, source.repository)
        if state.dirty:
            print(f"Refusing to delete {path}: working tree has changes.")
            continue
        shutil.rmtree(path, onexc=_remove_readonly_entry)
        print(f"Deleted {path}.")


def _managed_main(
    arguments: argparse.Namespace,
    action: str = "configure",
    interactive: bool = True,
) -> int:
    dashboard_root = _dashboard_root()
    parent = (
        Path(arguments.parent).expanduser().resolve()
        if arguments.parent
        else dashboard_root.parent
    )
    if dashboard_root.parent != parent:
        raise SetupError(
            f"Dashboard must be a direct child of the workspace parent {parent}; "
            f"found {dashboard_root}."
        )

    if action == "git-config":
        print_global_git_configuration()
        return 0
    if action == "refresh-packages":
        refresh_packages()
        print("Locked Python packages refreshed.")
        return 0
    if action == "extension":
        _offer_extension(bool(shutil.which("code")))
        return 0
    if action != "configure":
        raise SetupError(f"Unsupported workspace setup action: {action}")

    if not _is_git_checkout(dashboard_root):
        raise SetupError(f"Dashboard is not a Git checkout: {dashboard_root}")
    dashboard_state = fetch_and_fast_forward(dashboard_repository(), dashboard_root)

    from content_assembly import (
        discover_sibling_checkouts,
        load_repository_registry,
        workspace_repositories,
    )

    repositories = workspace_repositories(load_repository_registry())
    repository_by_id = {
        repository.identifier: repository for repository in repositories
    }
    required = {
        repository.identifier
        for repository in repositories
        if repository.workspace == "required"
    }

    for identifier in sorted(required):
        repository = repository_by_id[identifier]
        path = _repository_path(parent, repository.repository)
        if not path.exists():
            print(f"Cloning required repository {repository.repository}...")
            clone_repository(repository.repository, path)
        if not _is_git_checkout(path):
            raise SetupError(f"Required repository is not a Git checkout: {path}")

    checkouts = discover_sibling_checkouts(repositories, parent)
    checkout_states: dict[str, CheckoutState] = {}
    for identifier, path in sorted(checkouts.items()):
        # Discovery matches folder names, so a sibling may not be a clone at all.
        if _is_git_checkout(path):
            checkout_states[identifier] = fetch_and_fast_forward(
                repository_by_id[identifier].repository, path
            )
        else:
            print(f"Skipped update for {path.name}: not a Git checkout.")

    required_options = [
        (
            f"dashboard: {dashboard_repository()} [cloned, {dashboard_state.branch}; "
            f"{'modified' if dashboard_state.dirty else 'clean'}; in workspace]"
        )
    ]
    for identifier in sorted(required):
        repository = repository_by_id[identifier]
        state = checkout_states[identifier]
        status = f"cloned, {state.branch}"
        if state.dirty:
            status += ", modified"
        elif state.ahead or state.behind:
            status += f", ahead {state.ahead}/behind {state.behind}"
        else:
            status += ", clean"
        purpose = f", {repository.purpose}" if repository.purpose else ""
        required_options.append(
            f"{identifier}: {repository.repository}{purpose} [{status}; in workspace]"
        )

    workspace_file, existing_workspace = _load_existing_workspace(
        parent, arguments.workspace_name
    )
    dashboard_path = dashboard_root.resolve()
    selected_paths: list[Path] = [dashboard_path]
    selected_paths.extend(
        _repository_path(parent, repository.repository).resolve()
        for repository in repositories
        if repository.identifier in required
    )
    selected_ids: set[str] = set(required)
    for identifier, repository in repository_by_id.items():
        path = _repository_path(parent, repository.repository)
        if any(
            _resolved_workspace_entry(workspace_file, folder.get("path", ""))
            == path.resolve()
            and path.exists()
            for folder in existing_workspace.get("folders", [])
            if isinstance(folder, dict) and isinstance(folder.get("path"), str)
        ):
            if path.resolve() not in selected_paths:
                selected_paths.append(path.resolve())
            selected_ids.add(identifier)

    optional = [
        repository
        for repository in repositories
        if repository.identifier not in required
    ]
    optional_ids = {repository.identifier for repository in optional}
    explicit_add = _source_id_values(
        getattr(arguments, "add_sources", []), optional_ids
    )
    explicit_remove = _source_id_values(
        getattr(arguments, "remove_sources", []), optional_ids
    )
    all_optional = bool(getattr(arguments, "all_optional", False))
    none_optional = bool(getattr(arguments, "none_optional", False))
    if all_optional and none_optional:
        raise SetupError("Use either --all-optional or --none-optional, not both.")
    if all_optional:
        explicit_add = optional_ids
    if none_optional:
        explicit_add = set()

    options: list[tuple[str, str]] = []
    for repository in repositories:
        if repository.identifier in required:
            continue
        path = _repository_path(parent, repository.repository)
        state = checkout_states.get(repository.identifier)
        if state is not None:
            local_status = f"cloned, {state.branch}"
            if state.dirty:
                local_status += ", modified"
            elif state.ahead or state.behind:
                local_status += f", ahead {state.ahead}/behind {state.behind}"
            else:
                local_status += ", clean"
        elif path.exists():
            local_status = "present, not a Git checkout"
        else:
            local_status = "not cloned, clone on selection"
        workspace_status = (
            "in workspace"
            if repository.identifier in selected_ids
            else "not in workspace"
        )
        purpose = f", {repository.purpose}" if repository.purpose else ""
        label = (
            f"{repository.identifier}: {repository.repository}{purpose} "
            f"[{local_status}; "
            f"{workspace_status}]"
        )
        options.append((repository.identifier, label))

    option_labels = [label for _, label in options]
    print_required_repository_list(required_options)
    if interactive:
        print_optional_repository_list(options)
        add_indices = select_multiple(
            "Repositories to add to the workspace:",
            option_labels,
            display_options=False,
        )
        selected_add_ids = {options[index][0] for index in add_indices}
    elif all_optional:
        selected_add_ids = optional_ids
    elif none_optional:
        selected_add_ids = set()
    else:
        selected_add_ids = explicit_add

    for repository in optional:
        if repository.identifier not in selected_add_ids:
            continue
        path = _repository_path(parent, repository.repository)
        if not path.exists():
            print(f"Cloning {repository.repository}...")
            clone_repository(repository.repository, path)
        if path.resolve() not in selected_paths:
            selected_paths.append(path.resolve())
        selected_ids.add(repository.identifier)

    if interactive:
        remove_indices = select_multiple(
            "Repositories to remove from the workspace:",
            option_labels,
            display_options=False,
        )
        removed_ids = sorted(
            {
                options[index][0]
                for index in remove_indices
                if options[index][0] in selected_ids
            }
        )
    else:
        removed_ids = sorted(explicit_remove)
    for identifier in removed_ids:
        removed_path = _repository_path(
            parent, repository_by_id[identifier].repository
        ).resolve()
        selected_paths = [path for path in selected_paths if path != removed_path]

    managed_paths = {
        dashboard_path,
        *(
            _repository_path(parent, repository.repository).resolve()
            for repository in repositories
        ),
    }
    write_workspace(
        workspace_file,
        selected_paths,
        existing_workspace,
        managed_paths,
    )
    print(f"Workspace written: {workspace_file}")
    if removed_ids and getattr(arguments, "delete_removed", False):
        _remove_optional_clones(
            removed_ids, repository_by_id, parent, confirm_each=interactive
        )
    elif (
        interactive
        and removed_ids
        and ask_yes_no(
            "Delete any removed optional clones as a separate action?", False
        )
    ):
        _remove_optional_clones(removed_ids, repository_by_id, parent)
    should_open = getattr(arguments, "open", None)
    if should_open is True or (
        interactive
        and should_open is not False
        and shutil.which("code")
        and ask_yes_no("Open the generated workspace now?", True)
    ):
        _open_workspace(workspace_file)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--action",
        choices=("menu", "configure", "git-config", "refresh-packages", "extension"),
        default="menu",
        help="Run an action directly instead of opening the interactive menu.",
    )
    parser.add_argument(
        "--parent", type=Path, help="Common parent directory for sibling repositories."
    )
    parser.add_argument("--workspace-name", default=workspace_filename())
    open_group = parser.add_mutually_exclusive_group()
    open_group.add_argument(
        "--open", dest="open", action="store_true", help="Open the generated workspace."
    )
    open_group.add_argument(
        "--no-open",
        dest="open",
        action="store_false",
        help="Do not open the workspace.",
    )
    parser.set_defaults(open=None)
    parser.add_argument(
        "--add-source",
        dest="add_sources",
        action="append",
        default=[],
        metavar="SOURCE_ID",
        help="Add a registered optional source; repeat or use comma-separated IDs.",
    )
    parser.add_argument(
        "--remove-source",
        dest="remove_sources",
        action="append",
        default=[],
        metavar="SOURCE_ID",
        help="Remove a registered optional source from the workspace.",
    )
    optional_group = parser.add_mutually_exclusive_group()
    optional_group.add_argument(
        "--all-optional",
        action="store_true",
        help="Add every registered optional source without prompting.",
    )
    optional_group.add_argument(
        "--none-optional",
        action="store_true",
        help="Add no optional sources without prompting.",
    )
    parser.add_argument(
        "--delete-removed",
        action="store_true",
        help="Delete explicitly removed clean optional clones without another prompt.",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Do not prompt for optional source selection or workspace opening.",
    )
    parser.add_argument(
        "--install-extension",
        action="store_true",
        help="Compatibility alias for --action extension.",
    )
    parser.add_argument("--managed", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = _parser().parse_args(argv)
        if arguments.install_extension:
            arguments.action = "extension"
        check_prerequisites(require_code=arguments.open is True)
        if not arguments.managed:
            dashboard_root = _dashboard_root()
            _run(["uv", "sync", "--locked"], cwd=dashboard_root, stream_output=True)
            forwarded = [
                value
                for value in (list(argv) if argv is not None else sys.argv[1:])
                if value != "--managed"
            ]
            command = [
                "uv",
                "run",
                "--locked",
                "python",
                str(Path(__file__)),
                "--managed",
                *forwarded,
            ]
            return _run(command, cwd=dashboard_root, stream_output=True).returncode
        check_prerequisites(require_code=arguments.open is True, announce=True)
        configure_git_longpaths(
            pause_on_warning=(
                not arguments.non_interactive
                and (arguments.action == "menu" or arguments.action == "configure")
            )
        )
        if arguments.action == "menu":
            while True:
                action = select_action()
                print("")
                if action == "exit":
                    print("Setup cancelled.")
                    return 0
                try:
                    _managed_main(arguments, action, interactive=action == "configure")
                except (OSError, SetupError, ValueError) as exc:
                    print(f"Workspace action failed: {exc}", file=sys.stderr)
                print("")
        return _managed_main(
            arguments,
            arguments.action,
            interactive=not arguments.non_interactive
            and arguments.action == "configure",
        )
    except (OSError, SetupError, ValueError) as exc:
        print(f"Workspace setup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
