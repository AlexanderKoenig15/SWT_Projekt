from __future__ import annotations

import json
import subprocess
import sys
import unittest
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import workspace_bootstrap  # noqa: E402

WORKSPACE_FILENAME = "Modul-Example.code-workspace"


class DashboardRepositoryTests(unittest.TestCase):
    """Kept separate so 'dashboard_repository' stays unpatched here."""

    def test_dashboard_repository_reads_owner_and_name_from_origin(self) -> None:
        for remote in (
            "https://github.example.test/AS-IO/Modul-Example.git",
            "git@github.example.test:AS-IO/Modul-Example.git",
            "https://github.example.test/AS-IO/Modul-Example/",
        ):
            with patch.object(workspace_bootstrap, "_git", return_value=remote):
                self.assertEqual(
                    "AS-IO/Modul-Example", workspace_bootstrap.dashboard_repository()
                )


class WorkspaceBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch.object(
            workspace_bootstrap,
            "dashboard_repository",
            return_value="AS-IO/Modul-Example",
        )
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_selection_parser_supports_multiple_values_and_all(self) -> None:
        self.assertEqual({0, 2}, workspace_bootstrap._parse_selection("1,3", 3))
        self.assertEqual({0, 1, 2}, workspace_bootstrap._parse_selection("all", 3))
        self.assertEqual(set(), workspace_bootstrap._parse_selection("none", 3))

    def test_selection_parser_rejects_invalid_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside"):
            workspace_bootstrap._parse_selection("4", 3)
        with self.assertRaisesRegex(ValueError, "numbers"):
            workspace_bootstrap._parse_selection("first", 3)

    def test_select_multiple_retries_after_invalid_input(self) -> None:
        answers = iter(["bad", "2,3"])
        output: list[str] = []
        prompts: list[str] = []

        selection = workspace_bootstrap.select_multiple(
            "Choose:",
            ["one", "two", "three"],
            input_function=lambda prompt: (prompts.append(prompt) or next(answers)),
            output=output.append,
        )

        self.assertEqual({1, 2}, selection)
        self.assertTrue(any("Invalid selection" in line for line in output))
        self.assertEqual(
            "Selection (comma-separated, 'all', or 'NONE'; default: NONE): ",
            prompts[0],
        )

    def test_shared_optional_selection_supports_multiple_and_keep(self) -> None:
        options = ["SecLog", "Other"]
        self.assertEqual(
            {0, 1},
            workspace_bootstrap.select_multiple(
                "Add:", options, input_function=lambda _: "1,2", output=lambda _: None
            ),
        )
        self.assertEqual(
            set(),
            workspace_bootstrap.select_multiple(
                "Remove:",
                options,
                input_function=lambda _: "none",
                output=lambda _: None,
            ),
        )

    def test_print_optional_repository_list_numbers_all_options(self) -> None:
        output: list[str] = []
        workspace_bootstrap.print_optional_repository_list(
            [("first", "First"), ("second", "Second")], output.append
        )
        self.assertEqual(
            ["Optional repositories:", "   1. First", "   2. Second"], output
        )

    def test_print_required_repository_list_includes_all_required_repositories(
        self,
    ) -> None:
        output: list[str] = []
        workspace_bootstrap.print_required_repository_list(
            [
                "dashboard: AS-IO/Modul-Dashboard [cloned, main; clean; in workspace]",
                "agents: AS-IO/Modul-Agents, VS Code Agent Skills [cloned, main; clean; in workspace]",
            ],
            output.append,
        )

        self.assertEqual("Required repositories:", output[0])
        self.assertIn("AS-IO/Modul-Dashboard", output[1])
        self.assertIn("AS-IO/Modul-Agents", output[2])

    def test_select_action_returns_requested_operation(self) -> None:
        output: list[str] = []
        self.assertEqual(
            "git-config",
            workspace_bootstrap.select_action(
                input_function=lambda _: "2", output=output.append
            ),
        )
        self.assertTrue(any("Configure repositories" in line for line in output))

    def test_select_action_retries_invalid_input(self) -> None:
        answers = iter(["9", "1"])
        output: list[str] = []
        self.assertEqual(
            "configure",
            workspace_bootstrap.select_action(
                input_function=lambda _: next(answers), output=output.append
            ),
        )
        self.assertTrue(any("Enter 1, 2, 3, 4, or 5" in line for line in output))

    def test_menu_main_returns_to_menu_until_exit(self) -> None:
        actions = iter(["git-config", "extension", "exit"])
        with patch.object(workspace_bootstrap, "check_prerequisites"):
            with patch.object(
                workspace_bootstrap, "select_action", side_effect=lambda: next(actions)
            ):
                with patch.object(workspace_bootstrap, "_managed_main") as managed:
                    self.assertEqual(0, workspace_bootstrap.main(["--managed"]))

        self.assertEqual(2, managed.call_count)
        self.assertEqual("git-config", managed.call_args_list[0].args[1])
        self.assertEqual("extension", managed.call_args_list[1].args[1])

    def test_direct_action_bypasses_menu(self) -> None:
        with patch.object(workspace_bootstrap, "check_prerequisites"):
            with patch.object(
                workspace_bootstrap, "_managed_main", return_value=0
            ) as managed:
                self.assertEqual(
                    0,
                    workspace_bootstrap.main(["--managed", "--action", "git-config"]),
                )

        managed.assert_called_once()
        self.assertEqual("git-config", managed.call_args.args[1])

    def test_run_streaming_failure_has_actionable_error_without_captured_streams(
        self,
    ) -> None:
        completed = subprocess.CompletedProcess(
            ["example"], 1, stdout=None, stderr=None
        )
        with patch.object(
            workspace_bootstrap.subprocess, "run", return_value=completed
        ):
            with self.assertRaisesRegex(
                workspace_bootstrap.SetupError, "Command failed"
            ):
                workspace_bootstrap._run(["example"], stream_output=True)

    def test_code_command_wraps_windows_batch_launcher(self) -> None:
        with patch.object(
            workspace_bootstrap.shutil,
            "which",
            return_value=r"C:\Program Files\Microsoft VS Code\bin\code.cmd",
        ):
            with patch.object(workspace_bootstrap.os, "name", "nt"):
                self.assertEqual(
                    [
                        "cmd.exe",
                        "/d",
                        "/c",
                        r"C:\Program Files\Microsoft VS Code\bin\code.cmd",
                        "--version",
                    ],
                    workspace_bootstrap._code_command("--version"),
                )

    def test_extension_action_fails_when_code_cli_is_missing(self) -> None:
        arguments = SimpleNamespace(parent=None)
        with patch.object(
            workspace_bootstrap, "_dashboard_root", return_value=Path("C:/Dashboard")
        ):
            with patch.object(workspace_bootstrap, "configure_git_longpaths"):
                with patch.object(
                    workspace_bootstrap.shutil, "which", return_value=None
                ):
                    with self.assertRaisesRegex(workspace_bootstrap.SetupError, "code"):
                        workspace_bootstrap._managed_main(arguments, "extension")

    def test_extension_action_fails_when_install_command_fails(self) -> None:
        arguments = SimpleNamespace(parent=None)
        failed = subprocess.CompletedProcess(["code"], 1, "", "install failed")
        with patch.object(
            workspace_bootstrap, "_dashboard_root", return_value=Path("C:/Dashboard")
        ):
            with patch.object(workspace_bootstrap, "configure_git_longpaths"):
                with patch.object(
                    workspace_bootstrap.shutil, "which", return_value="code"
                ):
                    with patch.object(
                        workspace_bootstrap, "ask_yes_no", return_value=True
                    ):
                        with patch.object(
                            workspace_bootstrap, "_run", return_value=failed
                        ):
                            with self.assertRaisesRegex(
                                workspace_bootstrap.SetupError, "install failed"
                            ):
                                workspace_bootstrap._managed_main(
                                    arguments, "extension"
                                )

    def test_refresh_packages_runs_locked_uv_sync(self) -> None:
        with patch.object(workspace_bootstrap, "_run") as run:
            workspace_bootstrap.refresh_packages()
        run.assert_called_once_with(
            ["uv", "sync", "--locked"],
            cwd=workspace_bootstrap._dashboard_root(),
            stream_output=True,
        )

    def test_remove_readonly_entry_clears_attribute_and_retries(self) -> None:
        remove = unittest.mock.Mock()
        permission_error = PermissionError("access denied")
        with patch.object(workspace_bootstrap.os, "chmod") as chmod:
            workspace_bootstrap._remove_readonly_entry(
                remove, "C:/clone/.git/objects/example", permission_error
            )

        chmod.assert_called_once_with(
            "C:/clone/.git/objects/example", workspace_bootstrap.stat.S_IWRITE
        )
        remove.assert_called_once_with("C:/clone/.git/objects/example")

    def test_remove_readonly_entry_reraises_other_errors(self) -> None:
        remove = unittest.mock.Mock()
        error = OSError("cannot remove")
        with self.assertRaises(OSError) as raised:
            workspace_bootstrap._remove_readonly_entry(remove, "C:/clone/file", error)
        self.assertIs(error, raised.exception)

    def test_remove_optional_clones_uses_readonly_retry(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "Modul-Feature-SecLog"
            path.mkdir()
            source = SimpleNamespace(repository="AS-IO/Modul-Feature-SecLog")
            state = workspace_bootstrap.CheckoutState(
                path, "main", False, 0, 0, "remote"
            )
            with patch.object(
                workspace_bootstrap, "checkout_state", return_value=state
            ):
                with patch.object(
                    workspace_bootstrap.shutil, "rmtree"
                ) as remove_tree:
                    workspace_bootstrap._remove_optional_clones(
                        ["seclog"],
                        {"seclog": source},
                        Path(temporary_directory),
                        confirm_each=False,
                    )

        remove_tree.assert_called_once_with(
            path, onexc=workspace_bootstrap._remove_readonly_entry
        )

    def test_check_prerequisites_reports_missing_tools(self) -> None:
        with patch.object(workspace_bootstrap.shutil, "which", return_value=None):
            with self.assertRaisesRegex(workspace_bootstrap.SetupError, "git, uv"):
                workspace_bootstrap.check_prerequisites()

    def test_check_prerequisites_requires_code_only_when_requested(self) -> None:
        def which(name: str) -> str | None:
            return None if name == "code" else name

        with patch.object(workspace_bootstrap.shutil, "which", side_effect=which):
            workspace_bootstrap.check_prerequisites()
            with self.assertRaisesRegex(workspace_bootstrap.SetupError, "code"):
                workspace_bootstrap.check_prerequisites(require_code=True)

    def test_check_prerequisites_announces_passed_tools(self) -> None:
        output: list[str] = []
        with patch.object(
            workspace_bootstrap.shutil,
            "which",
            side_effect=lambda name: name,
        ):
            with patch("builtins.print", side_effect=output.append):
                workspace_bootstrap.check_prerequisites(announce=True)

        self.assertEqual(
            "Prerequisites passed: Python 3.14+, Git, uv. VS Code CLI: available.",
            output[0],
        )

    def test_redacts_sensitive_configuration_values(self) -> None:
        self.assertEqual(
            "global	http.extraheader\t<redacted>",
            workspace_bootstrap._redact_config_line(
                "global\thttp.extraheader\tAUTHORIZATION: bearer secret"
            ),
        )
        self.assertEqual(
            "remote.origin.url=https://<redacted>@example.test/repo.git",
            workspace_bootstrap._redact_config_line(
                "remote.origin.url=https://user:password@example.test/repo.git"
            ),
        )

    def test_configure_git_longpaths_sets_missing_user_value(self) -> None:
        calls: list[list[str]] = []

        def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            return subprocess.CompletedProcess(
                command, 1 if "--get" in command else 0, "", ""
            )

        with patch.object(workspace_bootstrap, "_run", side_effect=run):
            with patch.object(workspace_bootstrap, "os") as operating_system:
                operating_system.name = "posix"
                workspace_bootstrap.configure_git_longpaths()

        self.assertIn(
            ["git", "config", "--global", "core.longpaths", "true"],
            calls,
        )

    def test_checkout_state_reads_branch_dirty_and_divergence(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory)
            values = iter(
                [
                    "https://github.siemens.cloud/AS-IO/example.git",
                    "main",
                    "",
                    "2 0",
                ]
            )
            with patch.object(
                workspace_bootstrap, "_is_git_checkout", return_value=True
            ):
                with patch.object(
                    workspace_bootstrap,
                    "_git",
                    side_effect=lambda *_args, **_kwargs: next(values),
                ):
                    state = workspace_bootstrap.checkout_state(path, "AS-IO/example")

        self.assertEqual("main", state.branch)
        self.assertFalse(state.dirty)
        self.assertEqual(2, state.ahead)
        self.assertEqual(0, state.behind)

    def test_fetch_fast_forwards_clean_main_checkout(self) -> None:
        path = Path("C:/work/example")
        before = workspace_bootstrap.CheckoutState(path, "main", False, 0, 2, "remote")
        after = workspace_bootstrap.CheckoutState(path, "main", False, 0, 0, "remote")
        git_calls: list[tuple[str, ...]] = []

        with patch.object(
            workspace_bootstrap, "checkout_state", side_effect=[before, before, after]
        ):
            with patch.object(
                workspace_bootstrap,
                "_git",
                side_effect=lambda _path, *arguments, **_kwargs: (
                    git_calls.append(arguments) or ""
                ),
            ):
                workspace_bootstrap.fetch_and_fast_forward("AS-IO/example", path)

        self.assertIn(("fetch", "origin"), git_calls)
        self.assertIn(("merge", "--ff-only", "origin/main"), git_calls)

    def test_fetch_does_not_update_dirty_checkout(self) -> None:
        path = Path("C:/work/example")
        dirty = workspace_bootstrap.CheckoutState(path, "main", True, 0, 2, "remote")
        git_calls: list[tuple[str, ...]] = []

        with patch.object(
            workspace_bootstrap, "checkout_state", side_effect=[dirty, dirty]
        ):
            with patch.object(
                workspace_bootstrap,
                "_git",
                side_effect=lambda _path, *arguments, **_kwargs: (
                    git_calls.append(arguments) or ""
                ),
            ):
                workspace_bootstrap.fetch_and_fast_forward("AS-IO/example", path)

        self.assertIn(("fetch", "origin"), git_calls)
        self.assertNotIn(("merge", "--ff-only", "origin/main"), git_calls)

    def test_write_workspace_preserves_unrelated_entries_and_enables_autofetch(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            dashboard = parent / "Modul-Dashboard"
            documents = parent / "Modul-Documents"
            unrelated = parent / "notes"
            dashboard.mkdir()
            documents.mkdir()
            workspace_file = parent / WORKSPACE_FILENAME
            existing = {
                "folders": [{"path": "notes", "name": "Notes"}],
                "settings": {"editor.wordWrap": "on"},
                "extensions": {"recommendations": ["ms-python.python"]},
            }

            workspace_bootstrap.write_workspace(
                workspace_file,
                [dashboard, documents],
                existing,
            )
            document = json.loads(workspace_file.read_text(encoding="utf-8"))

        self.assertEqual("on", document["settings"]["editor.wordWrap"])
        self.assertTrue(document["settings"]["git.autofetch"])
        self.assertEqual(
            ["ms-python.python"], document["extensions"]["recommendations"]
        )
        self.assertEqual(
            {"Notes", "Modul-Dashboard", "Modul-Documents"},
            {folder["name"] for folder in document["folders"]},
        )
        self.assertEqual(unrelated.name, "notes")

    def test_write_workspace_preserves_uri_folder_entries(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            dashboard = parent / "Modul-Dashboard"
            dashboard.mkdir()
            workspace_file = parent / WORKSPACE_FILENAME

            workspace_bootstrap.write_workspace(
                workspace_file,
                [dashboard],
                {"folders": [{"uri": "file:///external/project", "name": "External"}]},
            )
            document = json.loads(workspace_file.read_text(encoding="utf-8"))

        self.assertIn(
            {"uri": "file:///external/project", "name": "External"},
            document["folders"],
        )

    def test_write_workspace_preserves_selected_repository_order(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            paths = [
                parent / "Modul-Dashboard",
                parent / "Modul-Documents",
                parent / "Modul-Agents",
                parent / "Modul-Feature-SecLog",
            ]
            for path in paths:
                path.mkdir()
            workspace_file = parent / WORKSPACE_FILENAME

            workspace_bootstrap.write_workspace(
                workspace_file,
                paths,
                {"folders": []},
            )
            document = json.loads(workspace_file.read_text(encoding="utf-8"))

        self.assertEqual(
            [path.name for path in paths],
            [folder["name"] for folder in document["folders"]],
        )

    def test_load_workspace_rejects_invalid_json(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            workspace_file = Path(temporary_directory) / "workspace.code-workspace"
            workspace_file.write_text("not json", encoding="utf-8")
            with self.assertRaisesRegex(
                workspace_bootstrap.SetupError, "Could not read"
            ):
                workspace_bootstrap.load_workspace(workspace_file)

    def test_managed_main_clones_required_and_selected_optional_sources(self) -> None:
        import content_assembly

        with TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            dashboard = parent / "Modul-Dashboard"
            dashboard.mkdir()
            documents = SimpleNamespace(
                identifier="documents",
                repository="AS-IO/Modul-Documents",
                workspace="required",
                mount_path=Path("."),
                purpose="Shared documentation root",
            )
            agents = SimpleNamespace(
                identifier="agents",
                repository="AS-IO/Modul-Agents",
                workspace="required",
                mount_path=None,
                purpose="VS Code Agent Skills",
            )
            optional = SimpleNamespace(
                identifier="seclog",
                repository="AS-IO/Modul-Feature-SecLog",
                workspace="optional",
                mount_path=Path("Features/SecLog"),
                purpose="Feature content",
            )
            repositories = [documents, agents, optional]

            def clone(repository: str, destination: Path) -> None:
                destination.mkdir()

            arguments = SimpleNamespace(
                parent=parent,
                workspace_name=WORKSPACE_FILENAME,
                install_extension=True,
                open=False,
            )
            with patch.object(
                workspace_bootstrap, "_dashboard_root", return_value=dashboard
            ):
                with patch.object(workspace_bootstrap, "configure_git_longpaths"):
                    with patch.object(
                        workspace_bootstrap, "select_action", return_value="configure"
                    ):
                        with patch.object(
                            workspace_bootstrap,
                            "_is_git_checkout",
                            return_value=True,
                        ):
                            with patch.object(
                                content_assembly,
                                "load_repository_registry",
                                return_value=repositories,
                            ), patch.object(
                                content_assembly,
                                "workspace_repositories",
                                side_effect=lambda entries: entries,
                            ):
                                with patch.object(
                                    content_assembly,
                                    "discover_sibling_checkouts",
                                    return_value={
                                        "documents": parent / "Modul-Documents",
                                        "agents": parent / "Modul-Agents",
                                    },
                                ):
                                    with patch.object(
                                        workspace_bootstrap,
                                        "clone_repository",
                                        side_effect=clone,
                                    ):
                                        with patch.object(
                                            workspace_bootstrap,
                                            "fetch_and_fast_forward",
                                        ):
                                            with patch.object(
                                                workspace_bootstrap,
                                                "select_multiple",
                                                side_effect=[{0}, set()],
                                            ):
                                                with patch.object(
                                                    workspace_bootstrap,
                                                    "ask_yes_no",
                                                    return_value=False,
                                                ):
                                                    with patch.object(
                                                        workspace_bootstrap.shutil,
                                                        "which",
                                                        return_value=None,
                                                    ):
                                                        result = workspace_bootstrap._managed_main(
                                                            arguments
                                                        )

            workspace = json.loads(
                (parent / WORKSPACE_FILENAME).read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(0, result)
        self.assertEqual(
            {"Modul-Dashboard", "Modul-Documents", "Modul-Agents", "Modul-Feature-SecLog"},
            {folder["name"] for folder in workspace["folders"]},
        )

    def test_managed_main_removes_optional_workspace_entry_without_deleting_clone(
        self,
    ) -> None:
        import content_assembly

        with TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            dashboard = parent / "Modul-Dashboard"
            documents = parent / "Modul-Documents"
            agents = parent / "Modul-Agents"
            optional_path = parent / "Modul-Feature-SecLog"
            dashboard.mkdir()
            documents.mkdir()
            agents.mkdir()
            optional_path.mkdir()
            workspace_file = parent / WORKSPACE_FILENAME
            workspace_file.write_text(
                json.dumps(
                    {
                        "folders": [
                            {"path": "Modul-Dashboard"},
                            {"path": "Modul-Documents"},
                            {"path": "Modul-Feature-SecLog"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            documents_source = SimpleNamespace(
                identifier="documents",
                repository="AS-IO/Modul-Documents",
                workspace="required",
                mount_path=Path("."),
                purpose="Shared documentation root",
            )
            optional_source = SimpleNamespace(
                identifier="seclog",
                repository="AS-IO/Modul-Feature-SecLog",
                workspace="optional",
                mount_path=Path("Features/SecLog"),
                purpose="Feature content",
            )
            agents_source = SimpleNamespace(
                identifier="agents",
                repository="AS-IO/Modul-Agents",
                workspace="required",
                mount_path=None,
                purpose="VS Code Agent Skills",
            )
            arguments = SimpleNamespace(
                parent=parent,
                workspace_name=WORKSPACE_FILENAME,
                install_extension=False,
                open=False,
            )
            with patch.object(
                workspace_bootstrap, "_dashboard_root", return_value=dashboard
            ):
                with patch.object(workspace_bootstrap, "configure_git_longpaths"):
                    with patch.object(
                        workspace_bootstrap, "select_action", return_value="configure"
                    ):
                        with patch.object(
                            workspace_bootstrap,
                            "_is_git_checkout",
                            return_value=True,
                        ):
                            with patch.object(
                                content_assembly,
                                "load_repository_registry",
                                return_value=[
                                    documents_source,
                                    agents_source,
                                    optional_source,
                                ],
                            ), patch.object(
                                content_assembly,
                                "workspace_repositories",
                                side_effect=lambda entries: entries,
                            ):
                                with patch.object(
                                    content_assembly,
                                    "discover_sibling_checkouts",
                                    return_value={
                                        "documents": documents,
                                        "agents": agents,
                                        "seclog": optional_path,
                                    },
                                ):
                                    with patch.object(
                                        workspace_bootstrap, "fetch_and_fast_forward"
                                    ):
                                        with patch.object(
                                            workspace_bootstrap,
                                            "select_multiple",
                                            side_effect=[set(), {0}],
                                        ):
                                            with patch.object(
                                                workspace_bootstrap,
                                                "ask_yes_no",
                                                side_effect=[True, False, False],
                                            ):
                                                result = (
                                                    workspace_bootstrap._managed_main(
                                                        arguments
                                                    )
                                                )

            workspace = json.loads(workspace_file.read_text(encoding="utf-8"))
            clone_was_preserved = optional_path.exists()

        self.assertEqual(0, result)
        self.assertTrue(clone_was_preserved)
        self.assertNotIn(
            "Modul-Feature-SecLog",
            {folder["name"] for folder in workspace["folders"]},
        )

    def test_managed_main_accepts_already_selected_optional_repository(self) -> None:
        import content_assembly

        with TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            dashboard = parent / "Modul-Dashboard"
            documents = parent / "Modul-Documents"
            agents = parent / "Modul-Agents"
            seclog = parent / "Modul-Feature-SecLog"
            dashboard.mkdir()
            documents.mkdir()
            agents.mkdir()
            seclog.mkdir()
            workspace_file = parent / WORKSPACE_FILENAME
            workspace_file.write_text(
                json.dumps(
                    {
                        "folders": [
                            {"path": "Modul-Dashboard"},
                            {"path": "Modul-Documents"},
                            {"path": "Modul-Feature-SecLog"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            sources = [
                SimpleNamespace(
                    identifier="documents",
                    repository="AS-IO/Modul-Documents",
                    workspace="required",
                    mount_path=Path("."),
                    purpose="Shared documentation root",
                ),
                SimpleNamespace(
                    identifier="agents",
                    repository="AS-IO/Modul-Agents",
                    workspace="required",
                    mount_path=None,
                    purpose="VS Code Agent Skills",
                ),
                SimpleNamespace(
                    identifier="seclog",
                    repository="AS-IO/Modul-Feature-SecLog",
                    workspace="optional",
                    mount_path=Path("Features/SecLog"),
                    purpose="Feature content",
                ),
            ]
            arguments = SimpleNamespace(
                parent=parent,
                workspace_name=WORKSPACE_FILENAME,
                install_extension=False,
                open=False,
            )
            with patch.object(
                workspace_bootstrap, "_dashboard_root", return_value=dashboard
            ):
                with patch.object(workspace_bootstrap, "configure_git_longpaths"):
                    with patch.object(
                        workspace_bootstrap, "_is_git_checkout", return_value=True
                    ):
                        with patch.object(
                            content_assembly,
                            "load_repository_registry",
                            return_value=sources,
                        ), patch.object(
                            content_assembly,
                            "workspace_repositories",
                            side_effect=lambda entries: entries,
                        ), patch.object(
                            content_assembly,
                            "discover_sibling_checkouts",
                            return_value={
                                "documents": documents,
                                "agents": agents,
                                "seclog": seclog,
                            },
                        ):
                                with patch.object(
                                    workspace_bootstrap, "fetch_and_fast_forward"
                                ):
                                    with patch.object(
                                        workspace_bootstrap,
                                        "select_multiple",
                                        side_effect=[{0}, set()],
                                    ) as select:
                                        with patch.object(
                                            workspace_bootstrap, "clone_repository"
                                        ) as clone:
                                            workspace_bootstrap._managed_main(
                                                arguments, "configure"
                                            )

            self.assertEqual(2, select.call_count)
            clone.assert_not_called()
            self.assertEqual(
                "Repositories to add to the workspace:",
                select.call_args_list[0].args[0],
            )
            self.assertEqual(
                "Repositories to remove from the workspace:",
                select.call_args_list[1].args[0],
            )

    def test_managed_main_keeps_sibling_directory_that_is_not_a_checkout(
        self,
    ) -> None:
        import content_assembly

        with TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            dashboard = parent / "Modul-Dashboard"
            documents = parent / "Modul-Documents"
            dummy = parent / "Modul-Dummy"
            dashboard.mkdir()
            documents.mkdir()
            dummy.mkdir()
            workspace_file = parent / WORKSPACE_FILENAME
            sources = [
                SimpleNamespace(
                    identifier="documents",
                    repository="AS-IO/Modul-Documents",
                    workspace="required",
                    mount_path=Path("."),
                    purpose="Shared documentation root",
                ),
                SimpleNamespace(
                    identifier="dummy",
                    repository="AS-IO/Modul-Dummy",
                    workspace="optional",
                    mount_path=None,
                    purpose="Planned repository",
                ),
            ]
            arguments = SimpleNamespace(
                parent=parent,
                workspace_name=WORKSPACE_FILENAME,
                install_extension=False,
                open=False,
            )
            labels: list[str] = []
            selections = iter([{0}, set()])

            def select(
                _prompt: str, options: list[str], **_kwargs: object
            ) -> set[int]:
                labels.extend(options)
                return next(selections)

            with patch.object(
                workspace_bootstrap, "_dashboard_root", return_value=dashboard
            ):
                with patch.object(
                    workspace_bootstrap,
                    "_is_git_checkout",
                    side_effect=lambda path: path != dummy,
                ):
                    with patch.object(
                        content_assembly,
                        "load_repository_registry",
                        return_value=sources,
                    ), patch.object(
                        content_assembly,
                        "workspace_repositories",
                        side_effect=lambda entries: entries,
                    ), patch.object(
                        content_assembly,
                        "discover_sibling_checkouts",
                        return_value={"documents": documents, "dummy": dummy},
                    ):
                        with patch.object(
                            workspace_bootstrap, "fetch_and_fast_forward"
                        ):
                            with patch.object(
                                workspace_bootstrap,
                                "select_multiple",
                                side_effect=select,
                            ):
                                with patch.object(
                                    workspace_bootstrap, "clone_repository"
                                ) as clone:
                                    result = workspace_bootstrap._managed_main(
                                        arguments, "configure"
                                    )

            workspace = json.loads(workspace_file.read_text(encoding="utf-8"))

        self.assertEqual(0, result)
        clone.assert_not_called()
        self.assertIn("present, not a Git checkout", labels[0])
        self.assertEqual(
            {"Modul-Dashboard", "Modul-Documents", "Modul-Dummy"},
            {folder["name"] for folder in workspace["folders"]},
        )

    def test_main_reexecutes_through_uv_when_not_managed(self) -> None:
        completed = subprocess.CompletedProcess(["uv"], 0, "", "")
        with patch.object(workspace_bootstrap, "check_prerequisites"):
            with patch.object(workspace_bootstrap, "configure_git_longpaths"):
                with patch.object(
                    workspace_bootstrap, "_run", return_value=completed
                ) as run:
                    result = workspace_bootstrap.main([])

        self.assertEqual(0, result)
        self.assertEqual(2, run.call_count)
        self.assertEqual("sync", run.call_args_list[0].args[0][1])
        self.assertIn("--managed", run.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
