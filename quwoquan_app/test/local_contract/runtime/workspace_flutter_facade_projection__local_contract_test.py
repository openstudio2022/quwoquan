"""Local contract for the exact Cursor workspace Flutter projection."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[4]
ACTIVATION_SCRIPT = (
    REPO_ROOT / "quwoquan_app/scripts/tools/flutter_facade/activate_cursor_workspace.py"
)
GENERATED_APP_LAUNCH_CONTRACT = (
    REPO_ROOT
    / "quwoquan_app/tool/app_launch_contract_codegen/app_launch_contract.generated.json"
)


def _load_activation_module():
    spec = importlib.util.spec_from_file_location(
        "qwq_cursor_activation", ACTIVATION_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load workspace activation module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_fake_flutter_sdk(
    root: Path,
    name: str,
    *,
    version: str = "3.47.0",
    revision: str | None = None,
) -> Path:
    executable = root / name / "bin/flutter"
    executable.parent.mkdir(parents=True)
    payload = json.dumps(
        {
            "frameworkVersion": version,
            "frameworkRevision": revision or f"{name}-framework",
            "engineRevision": f"{name}-engine",
            "dartSdkVersion": f"{name}-dart",
            "channel": "stable",
        },
        separators=(",", ":"),
    )
    executable.write_text(
        "#!/bin/sh\n"
        'if [ "$*" = "--version --machine" ]; then\n'
        f"  printf '%s' {json.dumps(payload)}\n"
        "  exit 0\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    executable.chmod(
        executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    )
    return executable


def _legacy_managed_segment(
    module,
    executable: Path,
    *,
    env_overrides: dict[str, str] | None = None,
    extra_env: dict[str, str] | None = None,
    dart_value: bool = False,
    binding_marker_count: int = 0,
) -> str:
    physical_flutter = executable.resolve()
    flutter_root = physical_flutter.parents[1]
    terminal_env = {
        "PATH": (
            f"{module.FACADE_BIN_VALUE}:{flutter_root / 'bin'}:${{env:PATH}}"
        ),
        "QWQ_WORKSPACE_FLUTTER_FACADE_BIN": module.FACADE_BIN_VALUE,
        "QWQ_WORKSPACE_ORIGINAL_ZDOTDIR": "${env:ZDOTDIR}",
        "ZDOTDIR": module.ZDOTDIR_VALUE,
        "FLUTTER_ROOT": str(flutter_root),
        "QWQ_REAL_FLUTTER": str(physical_flutter),
    }
    terminal_env.update(env_overrides or {})
    terminal_env.update(extra_env or {})
    env_items = list(terminal_env.items())
    env_lines = [
        "        "
        + json.dumps(key)
        + ": "
        + json.dumps(value)
        + ("," if index < len(env_items) - 1 else "")
        for index, (key, value) in enumerate(env_items)
    ]
    binding_markers = [
        f"    {module.SDK_BINDING_MARKER_PREFIX}sha256:{index:064x}"
        for index in range(binding_marker_count)
    ]
    lines = [
        f"    {module.BEGIN_MARKER}",
        (
            "    // 由 activate_cursor_workspace.py 管理，勿手改；"
            "回退：--deactivate 后重载窗口。"
        ),
        *binding_markers,
        f'    "{module.MANAGED_DART_KEY}": {json.dumps(dart_value)},',
        f'    "{module.MANAGED_ENV_KEY}": {{',
        *env_lines,
        "    },",
        f"    {module.END_MARKER}",
    ]
    return "\n" + "\n".join(lines) + "\n"


class WorkspaceFlutterFacadeProjectionLocalContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.settings = self.root / ".vscode/settings.json"
        self.tasks = self.settings.with_name("tasks.json")
        self.launch = self.settings.with_name("launch.json")
        self.settings.parent.mkdir(parents=True)
        self.module = _load_activation_module()
        self.real_flutter = _write_fake_flutter_sdk(self.root, "real-sdk")
        self.fake_pod = self.root / "cocoapods/bin/pod"
        self.fake_pod.parent.mkdir(parents=True)
        self.fake_pod.write_text(
            "#!/bin/sh\n"
            'SELF="$(cd "$(dirname "$0")" && pwd -P)/$(basename "$0")"\n'
            'if [ "$1" = "--version" ]; then\n'
            "  printf '%s\\n' '1.16.2'\n"
            "  exit 0\n"
            "fi\n"
            'if [ "$1" = "env" ]; then\n'
            "  printf '### Stack\\nCocoaPods : 1.16.2\\nRuby : 3.3.0\\n"
            "RubyGems : 3.5.0\\n### Plugins\\n"
            "cocoapods-deintegrate : 1.0.5\\nExecutable Path: %s\\n' "
            '"$SELF"\n'
            "  exit 0\n"
            "fi\n"
            "exit 64\n",
            encoding="utf-8",
        )
        self.fake_pod.chmod(0o755)
        self.sdk_environment = {
            "QWQ_REAL_FLUTTER": str(self.real_flutter),
            "PATH": f"{self.fake_pod.parent}:/usr/bin:/bin",
        }
        self.pod_binding = self.module._resolved_cocoapods_binding(
            self.sdk_environment
        )
        self.python_binding = self.module._resolved_python_binding(
            self.sdk_environment
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_python_resolution_skips_path_python_3_9_and_selects_trusted_3_13(
        self,
    ) -> None:
        system_bin = self.root / "system-python/bin"
        trusted_bin = self.root / "trusted-python/bin"
        system_bin.mkdir(parents=True)
        trusted_bin.mkdir(parents=True)

        def write_python(directory: Path, version: tuple[int, int, int]) -> Path:
            executable = directory / "python3"
            payload = {
                "executable": str(executable.resolve()),
                "version": list(version),
            }
            executable.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' {json.dumps(json.dumps(payload))}\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)
            return executable

        system_python = write_python(system_bin, (3, 9, 6))
        trusted_python = write_python(trusted_bin, (3, 13, 3))
        with mock.patch.object(
            self.module.sys, "executable", str(trusted_python)
        ):
            binding = self.module._resolved_python_binding(
                {"PATH": f"{system_bin}:/usr/bin:/bin"}
            )

        self.assertEqual(binding["executable"], str(trusted_python.resolve()))
        self.assertEqual(binding["version"], "3.13.3")
        self.assertNotEqual(binding["executable"], str(system_python.resolve()))

    def test_python_resolution_rejects_arbitrary_path_python_3_13(
        self,
    ) -> None:
        hostile_bin = self.root / "hostile-python/bin"
        trusted_bin = self.root / "trusted-host-python/bin"
        hostile_bin.mkdir(parents=True)
        trusted_bin.mkdir(parents=True)

        def write_python(directory: Path) -> Path:
            executable = directory / "python3"
            payload = {
                "executable": str(executable.resolve()),
                "version": [3, 13, 3],
            }
            executable.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' {json.dumps(json.dumps(payload))}\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)
            return executable

        hostile_python = write_python(hostile_bin)
        trusted_python = write_python(trusted_bin)
        with mock.patch.object(
            self.module.sys, "executable", str(trusted_python)
        ):
            binding = self.module._resolved_python_binding(
                {"PATH": f"{hostile_bin}:/usr/bin:/bin"}
            )

        self.assertEqual(binding["executable"], str(trusted_python.resolve()))
        self.assertNotEqual(binding["executable"], str(hostile_python.resolve()))

    def test_declared_python_identity_must_match_physical_version(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            self.module._resolved_python_binding(
                {
                    self.module.PYTHON_EXECUTABLE_KEY: self.python_binding[
                        "executable"
                    ],
                    self.module.PYTHON_VERSION_KEY: "3.10.0",
                    "PATH": "",
                }
            )

    def test_activation_fails_atomically_when_cocoapods_resolution_fails(self) -> None:
        original = '{\n    "editor.formatOnSave": true\n}\n'
        self.settings.write_text(original, encoding="utf-8")
        error = self.module._CANONICAL_COCOAPODS.AppDependencyToolchainError(
            "APP.DEPENDENCY.cocoapods_missing: pod executable not found"
        )

        with (
            mock.patch.object(
                self.module,
                "_resolved_cocoapods_binding",
                side_effect=error,
            ),
            self.assertRaises(SystemExit) as raised,
        ):
            self.module.activate(
                self.settings,
                self.tasks,
                self.launch,
                environ=self.sdk_environment,
            )

        self.assertIn("APP.DEPENDENCY.cocoapods_missing", str(raised.exception))
        self.assertEqual(self.settings.read_text(encoding="utf-8"), original)
        self.assertFalse(self.tasks.exists())
        self.assertFalse(self.launch.exists())

    def test_missing_cocoapods_fields_and_seal_drift_fail_closed(self) -> None:
        for name, mutate in {
            "missing-field": lambda content: content.replace(
                next(
                    line + "\n"
                    for line in content.splitlines()
                    if json.dumps("QWQ_COCOAPODS_VERSION") in line
                ),
                "",
                1,
            ),
            "seal-drift": lambda content: content.replace(
                self.pod_binding["QWQ_COCOAPODS_BINDING_SEAL"],
                "sha256:" + "0" * 64,
                1,
            ),
        }.items():
            with self.subTest(case=name):
                scope = self.root / name
                settings = scope / "settings.json"
                tasks = scope / "tasks.json"
                launch = scope / "launch.json"
                settings.parent.mkdir(parents=True)
                settings.write_text("{}\n", encoding="utf-8")
                self.module.activate(
                    settings, tasks, launch, environ=self.sdk_environment
                )
                settings.write_text(
                    mutate(settings.read_text(encoding="utf-8")),
                    encoding="utf-8",
                )
                before = (
                    settings.read_bytes(),
                    tasks.read_bytes(),
                    launch.read_bytes(),
                )

                result = self.module.status(
                    settings, tasks, launch, environ=self.sdk_environment
                )
                self.assertEqual(
                    result["cocoaPodsResolutionState"],
                    "invalid_projection",
                )
                self.assertNotEqual(result["effectiveState"], "active")
                with self.assertRaises(SystemExit):
                    self.module.deactivate(settings, tasks, launch)
                self.assertEqual(
                    (
                        settings.read_bytes(),
                        tasks.read_bytes(),
                        launch.read_bytes(),
                    ),
                    before,
                )

    def test_activation_projects_exact_managed_settings_and_restores_bytes(
        self,
    ) -> None:
        original = '{\n    "editor.formatOnSave": true\n}\n'
        self.settings.write_text(original, encoding="utf-8")

        outcome = self.module.activate(
            self.settings,
            self.tasks,
            self.launch,
            environ=self.sdk_environment,
        )

        self.assertEqual(outcome, "activated")
        parsed = self.module._parse_settings(self.settings.read_text(encoding="utf-8"))
        self.assertIs(parsed["dart.addSdkToTerminalPath"], False)
        sdk_binding = self.module._resolved_sdk_binding(self.sdk_environment)
        self.assertEqual(
            parsed["terminal.integrated.env.osx"],
            self.module._managed_terminal_env(
                sdk_binding, self.pod_binding, self.python_binding
            ),
        )
        self.assertEqual(
            parsed[self.module.MANAGED_PROFILES_KEY],
            self.module._managed_profiles(
                sdk_binding, self.pod_binding, self.python_binding
            ),
        )
        self.assertEqual(
            parsed[self.module.MANAGED_DEFAULT_PROFILE_KEY],
            self.module.PROFILE_NAME,
        )
        profile = parsed[self.module.MANAGED_PROFILES_KEY][self.module.PROFILE_NAME]
        self.assertEqual(profile["path"], self.module.PROFILE_LAUNCHER_VALUE)
        self.assertEqual(profile["args"], [])
        self.assertEqual(profile["env"]["QWQ_TERMINAL_SURFACE"], "unknown")
        self.assertEqual(
            profile["env"]["QWQ_TERMINAL_PROJECTION_GENERATION"],
            self.module._projection_generation(
                sdk_binding, self.pod_binding, self.python_binding
            ),
        )
        self.assertEqual(
            profile["env"]["QWQ_TERMINAL_PROJECTION_SEAL"],
            self.module._projection_seal(
                sdk_binding, self.pod_binding, self.python_binding
            ),
        )
        terminal_env = parsed["terminal.integrated.env.osx"]
        physical_flutter = self.real_flutter.resolve()
        self.assertEqual(terminal_env["FLUTTER_ROOT"], str(physical_flutter.parents[1]))
        self.assertEqual(terminal_env["QWQ_REAL_FLUTTER"], str(physical_flutter))
        self.assertEqual(terminal_env["QWQ_REAL_FLUTTER_VERSION"], "3.47.0")
        self.assertRegex(
            terminal_env["QWQ_REAL_FLUTTER_COMMAND_RESOLUTION_DIGEST"],
            r"^sha256:[0-9a-f]{64}$",
        )
        self.assertEqual(
            terminal_env[self.module.PYTHON_EXECUTABLE_KEY],
            self.python_binding["executable"],
        )
        self.assertEqual(
            terminal_env[self.module.PYTHON_VERSION_KEY],
            self.python_binding["version"],
        )
        self.assertTrue(
            terminal_env["PATH"].startswith(self.module.FACADE_BIN_VALUE + ":"),
            "facade bin 必须仍在 PATH 首位",
        )
        self.assertIn("${env:PATH}", terminal_env["PATH"])
        self.assertEqual(
            self.tasks.read_text(encoding="utf-8"), self.module._tasks_projection()
        )
        self.assertEqual(
            self.launch.read_text(encoding="utf-8"), self.module._launch_projection()
        )

        self.assertEqual(
            self.module.deactivate(self.settings, self.tasks, self.launch),
            "deactivated",
        )
        self.assertEqual(self.settings.read_text(encoding="utf-8"), original)
        self.assertFalse(self.tasks.exists())
        self.assertFalse(self.launch.exists())

    def test_activation_refreshes_exact_pre_python_identity_projection(
        self,
    ) -> None:
        baseline = '{\n    "editor.formatOnSave": true\n}\n'
        sdk_binding = self.module._resolved_sdk_binding(self.sdk_environment)
        legacy = (
            baseline[:1]
            + self.module._pre_python_identity_managed_segment(
                sdk_binding, self.pod_binding, self.python_binding
            )
            + baseline[1:]
        )
        self.settings.write_text(legacy, encoding="utf-8")

        self.assertEqual(
            self.module.activate(
                self.settings,
                self.tasks,
                self.launch,
                environ=self.sdk_environment,
            ),
            "refreshed",
        )
        refreshed = self.settings.read_text(encoding="utf-8")
        parsed = self.module._parse_settings(refreshed)
        profile = parsed[self.module.MANAGED_PROFILES_KEY][
            self.module.PROFILE_NAME
        ]
        self.assertEqual(
            profile["env"]["QWQ_TERMINAL_PROJECTION_SEAL"],
            self.module._projection_seal(
                sdk_binding, self.pod_binding, self.python_binding
            ),
        )
        self.assertEqual(
            profile["env"]["QWQ_TERMINAL_PROJECTION_GENERATION"],
            self.module._projection_generation(
                sdk_binding, self.pod_binding, self.python_binding
            ),
        )

    def test_activation_refuses_drifted_pre_python_identity_projection(
        self,
    ) -> None:
        sdk_binding = self.module._resolved_sdk_binding(self.sdk_environment)
        legacy = (
            "{"
            + self.module._pre_python_identity_managed_segment(
                sdk_binding, self.pod_binding, self.python_binding
            ).replace(self.python_binding["version"], "3.10.0", 1)
            + "}\n"
        )
        self.settings.write_text(legacy, encoding="utf-8")

        with self.assertRaises(SystemExit) as raised:
            self.module.activate(
                self.settings,
                self.tasks,
                self.launch,
                environ=self.sdk_environment,
            )

        self.assertIn("GATE_BLOCK", str(raised.exception))
        self.assertEqual(self.settings.read_text(encoding="utf-8"), legacy)
        self.assertFalse(self.tasks.exists())
        self.assertFalse(self.launch.exists())

    def test_activation_refreshes_exact_pre_python_projection(self) -> None:
        baseline = '{\n    "editor.formatOnSave": true\n}\n'
        sdk_binding = self.module._resolved_sdk_binding(self.sdk_environment)
        legacy = (
            baseline[:1]
            + self.module._pre_python_managed_segment(
                sdk_binding, self.pod_binding
            )
            + baseline[1:]
        )
        self.settings.write_text(legacy, encoding="utf-8")

        self.assertEqual(
            self.module.activate(
                self.settings,
                self.tasks,
                self.launch,
                environ=self.sdk_environment,
            ),
            "refreshed",
        )
        refreshed = self.settings.read_text(encoding="utf-8")
        self.assertEqual(
            refreshed.count(self.module.PYTHON_BINDING_MARKER_PREFIX), 1
        )
        parsed = self.module._parse_settings(refreshed)
        terminal_env = parsed[self.module.MANAGED_ENV_KEY]
        self.assertEqual(
            terminal_env[self.module.PYTHON_EXECUTABLE_KEY],
            self.python_binding["executable"],
        )
        self.assertEqual(
            terminal_env[self.module.PYTHON_VERSION_KEY],
            self.python_binding["version"],
        )
        self.assertEqual(
            self.module.deactivate(self.settings, self.tasks, self.launch),
            "deactivated",
        )
        self.assertEqual(self.settings.read_text(encoding="utf-8"), baseline)

    def test_activation_refuses_drifted_pre_python_projection(self) -> None:
        sdk_binding = self.module._resolved_sdk_binding(self.sdk_environment)
        legacy = (
            "{"
            + self.module._pre_python_managed_segment(
                sdk_binding, self.pod_binding
            ).replace(self.module.PROFILE_LAUNCHER_VALUE, "/bin/zsh", 1)
            + "}\n"
        )
        self.settings.write_text(legacy, encoding="utf-8")

        with self.assertRaises(SystemExit) as raised:
            self.module.activate(
                self.settings,
                self.tasks,
                self.launch,
                environ=self.sdk_environment,
            )

        self.assertIn("GATE_BLOCK", str(raised.exception))
        self.assertEqual(self.settings.read_text(encoding="utf-8"), legacy)
        self.assertFalse(self.tasks.exists())
        self.assertFalse(self.launch.exists())

    def test_activation_refreshes_exact_legacy_managed_settings(self) -> None:
        baseline = (
            "{\n"
            "\n"
            "    // 用户配置必须逐字保留\n"
            '    "editor.formatOnSave": true\n'
            "}\n"
        )
        legacy = baseline[:1] + _legacy_managed_segment(
            self.module, self.real_flutter
        ) + baseline[1:]
        self.settings.write_text(legacy, encoding="utf-8")

        outcome = self.module.activate(
            self.settings,
            self.tasks,
            self.launch,
            environ=self.sdk_environment,
        )

        self.assertEqual(outcome, "refreshed")
        refreshed = self.settings.read_text(encoding="utf-8")
        self.assertEqual(refreshed.count(self.module.BEGIN_MARKER), 1)
        self.assertEqual(refreshed.count(self.module.END_MARKER), 1)
        self.assertEqual(refreshed.count(self.module.SDK_BINDING_MARKER_PREFIX), 1)
        parsed = self.module._parse_settings(refreshed)
        self.assertEqual(
            parsed[self.module.MANAGED_ENV_KEY],
            self.module._managed_terminal_env(
                self.module._resolved_sdk_binding(self.sdk_environment),
                self.pod_binding,
                self.python_binding,
            ),
        )
        self.assertIn("用户配置必须逐字保留", refreshed)

        self.assertEqual(
            self.module.deactivate(self.settings, self.tasks, self.launch),
            "deactivated",
        )
        self.assertEqual(self.settings.read_text(encoding="utf-8"), baseline)

    def test_deactivation_refuses_exact_legacy_projection_atomically(self) -> None:
        legacy = "{" + _legacy_managed_segment(
            self.module, self.real_flutter
        ) + "}\n"
        self.settings.write_text(legacy, encoding="utf-8")
        self.tasks.write_text(self.module._tasks_projection(), encoding="utf-8")
        self.launch.write_text(self.module._launch_projection(), encoding="utf-8")
        before = (
            self.settings.read_bytes(),
            self.tasks.read_bytes(),
            self.launch.read_bytes(),
        )

        with self.assertRaises(SystemExit) as raised:
            self.module.deactivate(self.settings, self.tasks, self.launch)

        self.assertIn("GATE_BLOCK", str(raised.exception))
        self.assertEqual(
            (self.settings.read_bytes(), self.tasks.read_bytes(), self.launch.read_bytes()),
            before,
        )

    def test_activation_refuses_pseudo_legacy_managed_settings(self) -> None:
        cases = {
            "foreign-env-key": _legacy_managed_segment(
                self.module,
                self.real_flutter,
                extra_env={"QWQ_FOREIGN_MANAGED_KEY": "forged"},
            ),
            "invalid-path-relation": _legacy_managed_segment(
                self.module,
                self.real_flutter,
                env_overrides={"PATH": "/foreign/bin:${env:PATH}"},
            ),
            "invalid-dart-value": _legacy_managed_segment(
                self.module,
                self.real_flutter,
                dart_value=True,
            ),
            "multiple-sdk-markers": _legacy_managed_segment(
                self.module,
                self.real_flutter,
                binding_marker_count=2,
            ),
        }
        for name, segment in cases.items():
            with self.subTest(case=name):
                scope = self.root / f"pseudo-legacy-{name}"
                settings = scope / "settings.json"
                tasks = scope / "tasks.json"
                launch = scope / "launch.json"
                settings.parent.mkdir(parents=True)
                original = "{" + segment + "}\n"
                settings.write_text(original, encoding="utf-8")

                with self.assertRaises(SystemExit) as raised:
                    self.module.activate(
                        settings,
                        tasks,
                        launch,
                        environ=self.sdk_environment,
                    )

                self.assertIn("GATE_BLOCK", str(raised.exception))
                self.assertEqual(settings.read_text(encoding="utf-8"), original)
                self.assertFalse(tasks.exists())
                self.assertFalse(launch.exists())

    def test_activation_refuses_current_projection_with_duplicate_sdk_marker(self) -> None:
        self.settings.write_text("{}\n", encoding="utf-8")
        self.module.activate(
            self.settings,
            self.tasks,
            self.launch,
            environ=self.sdk_environment,
        )
        current = self.settings.read_text(encoding="utf-8")
        marker_line = next(
            line
            for line in current.splitlines()
            if self.module.SDK_BINDING_MARKER_PREFIX in line
        )
        forged = current.replace(marker_line, marker_line + "\n" + marker_line, 1)
        self.settings.write_text(forged, encoding="utf-8")
        before = (
            self.settings.read_bytes(),
            self.tasks.read_bytes(),
            self.launch.read_bytes(),
        )

        with self.assertRaises(SystemExit) as raised:
            self.module.activate(
                self.settings,
                self.tasks,
                self.launch,
                environ=self.sdk_environment,
            )

        self.assertIn("GATE_BLOCK", str(raised.exception))
        self.assertEqual(
            (self.settings.read_bytes(), self.tasks.read_bytes(), self.launch.read_bytes()),
            before,
        )

    def test_activation_refuses_all_foreign_managed_keys_before_any_write(self) -> None:
        original = '{\n    "dart.addSdkToTerminalPath": true\n}\n'
        self.settings.write_text(original, encoding="utf-8")

        with self.assertRaises(SystemExit) as raised:
            self.module.activate(
                self.settings,
                self.tasks,
                self.launch,
                environ=self.sdk_environment,
            )

        self.assertIn("GATE_BLOCK", str(raised.exception))
        self.assertEqual(self.settings.read_text(encoding="utf-8"), original)
        self.assertFalse(self.tasks.exists())
        self.assertFalse(self.launch.exists())

    def test_deactivation_refuses_marker_owned_but_drifted_projection_atomically(
        self,
    ) -> None:
        original = '{\n    "editor.formatOnSave": true\n}\n'
        self.settings.write_text(original, encoding="utf-8")
        self.module.activate(
            self.settings,
            self.tasks,
            self.launch,
            environ=self.sdk_environment,
        )
        settings_before = self.settings.read_bytes()
        self.tasks.write_text(
            self.tasks.read_text(encoding="utf-8") + "// foreign drift\n",
            encoding="utf-8",
        )
        tasks_before = self.tasks.read_bytes()
        launch_before = self.launch.read_bytes()

        with self.assertRaises(SystemExit) as raised:
            self.module.deactivate(self.settings, self.tasks, self.launch)

        self.assertIn("GATE_BLOCK", str(raised.exception))
        self.assertEqual(self.settings.read_bytes(), settings_before)
        self.assertEqual(self.tasks.read_bytes(), tasks_before)
        self.assertEqual(self.launch.read_bytes(), launch_before)

    def test_deactivation_refuses_malformed_settings_marker_before_deleting_ide_files(
        self,
    ) -> None:
        self.settings.write_text("{}\n", encoding="utf-8")
        self.module.activate(
            self.settings,
            self.tasks,
            self.launch,
            environ=self.sdk_environment,
        )
        self.settings.write_text(
            self.settings.read_text(encoding="utf-8").replace(
                self.module.END_MARKER, "// marker-drift"
            ),
            encoding="utf-8",
        )
        settings_before = self.settings.read_bytes()
        tasks_before = self.tasks.read_bytes()
        launch_before = self.launch.read_bytes()

        with self.assertRaises(SystemExit) as raised:
            self.module.deactivate(self.settings, self.tasks, self.launch)

        self.assertIn("GATE_BLOCK", str(raised.exception))
        self.assertEqual(self.settings.read_bytes(), settings_before)
        self.assertEqual(self.tasks.read_bytes(), tasks_before)
        self.assertEqual(self.launch.read_bytes(), launch_before)

    def test_status_requires_exact_projection_and_exact_current_facade(self) -> None:
        self.settings.write_text("{}\n", encoding="utf-8")
        self.module.activate(
            self.settings,
            self.tasks,
            self.launch,
            environ=self.sdk_environment,
        )
        expected = (
            self.module.REPO_ROOT
            / "quwoquan_app/scripts/tools/flutter_facade/bin/flutter"
        )
        original_which = self.module.shutil.which

        def facade_which(command, *, path=None):
            if command == "flutter":
                return str(expected)
            return original_which(command, path=path)

        with mock.patch.object(self.module.shutil, "which", side_effect=facade_which):
            projection = self.module.status(
                self.settings,
                self.tasks,
                self.launch,
                environ=self.sdk_environment,
            )
        self.assertEqual(projection["effectiveState"], "surface_required")
        self.assertEqual(projection["callerCommandResolution"], "facade")
        self.assertEqual(projection["sdkResolutionState"], "active")
        self.assertEqual(projection["targetSurfaceReceiptState"], "not_requested")

        self.tasks.write_text(
            self.tasks.read_text(encoding="utf-8") + "// marker-only drift\n",
            encoding="utf-8",
        )
        with mock.patch.object(self.module.shutil, "which", side_effect=facade_which):
            drifted = self.module.status(
                self.settings,
                self.tasks,
                self.launch,
                environ=self.sdk_environment,
            )
        self.assertEqual(drifted["projectionState"], "partial")
        self.assertEqual(drifted["effectiveState"], "inconsistent")

    def test_status_cli_fails_closed_without_disclosing_raw_path(self) -> None:
        self.settings.write_text("{}\n", encoding="utf-8")
        self.module.activate(
            self.settings,
            self.tasks,
            self.launch,
            environ=self.sdk_environment,
        )
        real_sdk_bin = self.real_flutter.parent
        environment = dict(os.environ)
        environment.pop("QWQ_REAL_FLUTTER", None)
        environment.pop("FLUTTER_ROOT", None)
        environment["PATH"] = f"{real_sdk_bin}:{self.fake_pod.parent}:/usr/bin:/bin"
        environment.update(self.pod_binding)

        result = subprocess.run(
            [
                sys.executable,
                str(ACTIVATION_SCRIPT),
                "--settings",
                str(self.settings),
                "--tasks",
                str(self.tasks),
                "--launch",
                str(self.launch),
                "--status",
            ],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("APP.LAUNCH.workspace_entrypoint_inactive", result.stderr)
        self.assertIn("make app-activate-flutter-facade", result.stderr)
        self.assertIn("Reload Window", result.stderr)
        self.assertNotIn("command -v flutter", result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["effectiveState"], "surface_required")
        self.assertNotIn(str(real_sdk_bin), result.stdout + result.stderr)
        self.assertNotIn(environment["PATH"], result.stdout + result.stderr)

    def test_activation_fails_before_any_write_without_canonical_real_sdk(self) -> None:
        original = '{\n    "editor.formatOnSave": true\n}\n'
        self.settings.write_text(original, encoding="utf-8")

        with (
            mock.patch.object(
                self.module._CANONICAL_FACADE.shutil, "which", return_value=None
            ),
            self.assertRaises(SystemExit) as raised,
        ):
            self.module.activate(
                self.settings,
                self.tasks,
                self.launch,
                environ={"PATH": ""},
            )

        self.assertIn(
            self.module.WORKSPACE_FLUTTER_SDK_UNAVAILABLE_BLOCKER,
            str(raised.exception),
        )
        self.assertEqual(self.settings.read_text(encoding="utf-8"), original)
        self.assertFalse(self.tasks.exists())
        self.assertFalse(self.launch.exists())

    def test_sdk_unavailable_blocker_comes_from_generated_canonical_closure(
        self,
    ) -> None:
        generated = json.loads(
            GENERATED_APP_LAUNCH_CONTRACT.read_text(encoding="utf-8")
        )
        canonical_blockers = generated["launchBlockers"]
        self.assertEqual(
            self.module.CANONICAL_LAUNCH_BLOCKERS,
            frozenset(canonical_blockers),
        )
        self.assertIn(
            self.module.WORKSPACE_FLUTTER_SDK_UNAVAILABLE_BLOCKER,
            canonical_blockers,
        )

    def test_canonical_resolution_precedence_and_symlink_physicalization(self) -> None:
        explicit = _write_fake_flutter_sdk(self.root, "explicit-sdk")
        rooted = _write_fake_flutter_sdk(self.root, "root-sdk")
        pathed = _write_fake_flutter_sdk(self.root, "path-sdk")
        environment = {
            "QWQ_REAL_FLUTTER": str(explicit),
            "FLUTTER_ROOT": str(rooted.parents[1]),
            "PATH": f"{pathed.parent}:/usr/bin:/bin",
        }
        self.assertEqual(
            self.module._resolved_sdk_binding(environment)["executable"],
            str(explicit.resolve()),
        )
        environment.pop("QWQ_REAL_FLUTTER")
        self.assertEqual(
            self.module._resolved_sdk_binding(environment)["executable"],
            str(rooted.resolve()),
        )
        environment.pop("FLUTTER_ROOT")
        self.assertEqual(
            self.module._resolved_sdk_binding(environment)["executable"],
            str(pathed.resolve()),
        )

        linked_sdk = self.root / "linked-sdk/flutter"
        linked_sdk.parent.mkdir()
        linked_sdk.symlink_to(explicit)
        self.assertEqual(
            self.module._resolved_sdk_binding(
                {"QWQ_REAL_FLUTTER": str(linked_sdk), "PATH": ""}
            )["executable"],
            str(explicit.resolve()),
        )

    def test_canonical_path_skips_facade_symlink_and_rejects_wrong_version(
        self,
    ) -> None:
        facade_bin = self.root / "facade-link-bin"
        facade_bin.mkdir()
        (facade_bin / "flutter").symlink_to(
            self.module._CANONICAL_FACADE.FACADE_EXECUTABLE
        )
        pathed = _write_fake_flutter_sdk(self.root, "path-after-facade")
        binding = self.module._resolved_sdk_binding(
            {"PATH": f"{facade_bin}:{pathed.parent}"}
        )
        self.assertEqual(binding["executable"], str(pathed.resolve()))

        wrong = _write_fake_flutter_sdk(self.root, "wrong-sdk", version="3.46.0")
        original = "{}\n"
        self.settings.write_text(original, encoding="utf-8")
        with self.assertRaises(SystemExit) as raised:
            self.module.activate(
                self.settings,
                self.tasks,
                self.launch,
                environ={"QWQ_REAL_FLUTTER": str(wrong), "PATH": ""},
            )
        self.assertIn("3.47.0", str(raised.exception))
        self.assertEqual(self.settings.read_text(encoding="utf-8"), original)
        self.assertFalse(self.tasks.exists())
        self.assertFalse(self.launch.exists())

    def test_status_detects_moved_sdk_while_deactivate_remains_recoverable(
        self,
    ) -> None:
        original = "{}\n"
        self.settings.write_text(original, encoding="utf-8")
        self.module.activate(
            self.settings,
            self.tasks,
            self.launch,
            environ=self.sdk_environment,
        )
        moved_root = self.root / "moved-real-sdk"
        shutil.move(str(self.real_flutter.parents[1]), moved_root)
        with mock.patch.object(
            self.module._CANONICAL_FACADE.shutil, "which", return_value=None
        ):
            result = self.module.status(
                self.settings,
                self.tasks,
                self.launch,
                environ=self.sdk_environment,
            )
        self.assertEqual(result["sdkResolutionState"], "unavailable")
        self.assertNotEqual(result["effectiveState"], "active")
        self.assertEqual(
            self.module.deactivate(self.settings, self.tasks, self.launch),
            "deactivated",
        )
        self.assertEqual(self.settings.read_text(encoding="utf-8"), original)

    def test_sdk_status_field_drift_is_not_active_or_deletable(self) -> None:
        replacements = {
            "executable": (
                str(self.real_flutter.resolve()),
                str(self.root / "other/flutter"),
            ),
            "version": (
                '"QWQ_REAL_FLUTTER_VERSION": "3.47.0"',
                '"QWQ_REAL_FLUTTER_VERSION": "3.46.0"',
            ),
            "identity": ("sha256:", "sha256:f"),
        }
        for name, (old, new) in replacements.items():
            with self.subTest(field=name):
                scope = self.root / name
                settings = scope / "settings.json"
                tasks = scope / "tasks.json"
                launch = scope / "launch.json"
                settings.parent.mkdir(parents=True)
                settings.write_text("{}\n", encoding="utf-8")
                self.module.activate(
                    settings,
                    tasks,
                    launch,
                    environ=self.sdk_environment,
                )
                settings.write_text(
                    settings.read_text(encoding="utf-8").replace(old, new, 1),
                    encoding="utf-8",
                )
                result = self.module.status(
                    settings,
                    tasks,
                    launch,
                    environ=self.sdk_environment,
                )
                self.assertNotEqual(result["effectiveState"], "active")
                before = (
                    settings.read_bytes(),
                    tasks.read_bytes(),
                    launch.read_bytes(),
                )
                with self.assertRaises(SystemExit):
                    self.module.deactivate(settings, tasks, launch)
                self.assertEqual(
                    (settings.read_bytes(), tasks.read_bytes(), launch.read_bytes()),
                    before,
                )

    def test_missing_sdk_status_fields_are_not_active_or_deletable(self) -> None:
        for key in self.module.SDK_STATUS_KEYS:
            with self.subTest(field=key):
                scope = self.root / f"missing-{key.lower()}"
                settings = scope / "settings.json"
                tasks = scope / "tasks.json"
                launch = scope / "launch.json"
                settings.parent.mkdir(parents=True)
                settings.write_text("{}\n", encoding="utf-8")
                self.module.activate(
                    settings,
                    tasks,
                    launch,
                    environ=self.sdk_environment,
                )
                terminal_env = self.module._parse_settings(
                    settings.read_text(encoding="utf-8")
                )[self.module.MANAGED_ENV_KEY]
                line = next(
                    candidate
                    for candidate in settings.read_text(encoding="utf-8").splitlines()
                    if json.dumps(key) in candidate
                    and json.dumps(terminal_env[key]) in candidate
                )
                settings.write_text(
                    settings.read_text(encoding="utf-8").replace(line + "\n", "", 1),
                    encoding="utf-8",
                )
                result = self.module.status(
                    settings,
                    tasks,
                    launch,
                    environ=self.sdk_environment,
                )
                self.assertEqual(result["sdkResolutionState"], "invalid_projection")
                self.assertNotEqual(result["effectiveState"], "active")
                before = (
                    settings.read_bytes(),
                    tasks.read_bytes(),
                    launch.read_bytes(),
                )
                with self.assertRaises(SystemExit):
                    self.module.deactivate(settings, tasks, launch)
                self.assertEqual(
                    (settings.read_bytes(), tasks.read_bytes(), launch.read_bytes()),
                    before,
                )

    def test_coherent_wrong_version_binding_cannot_self_certify(self) -> None:
        wrong_root = self.root / "coherent-wrong-sdk"
        wrong_binding = {
            "flutterRoot": str(wrong_root),
            "executable": str(wrong_root / "bin/flutter"),
            "flutterVersion": "3.46.0",
            "commandResolutionDigest": "sha256:" + "a" * 64,
        }
        self.settings.write_text(
            "{"
            + self.module._managed_segment(
                wrong_binding, self.pod_binding, self.python_binding
            )
            + "}\n",
            encoding="utf-8",
        )
        self.tasks.write_text(self.module._tasks_projection(), encoding="utf-8")
        self.launch.write_text(self.module._launch_projection(), encoding="utf-8")

        result = self.module.status(
            self.settings,
            self.tasks,
            self.launch,
            environ=self.sdk_environment,
        )
        self.assertEqual(result["sdkResolutionState"], "invalid_projection")
        self.assertNotEqual(result["effectiveState"], "active")
        before = (
            self.settings.read_bytes(),
            self.tasks.read_bytes(),
            self.launch.read_bytes(),
        )
        with self.assertRaises(SystemExit):
            self.module.deactivate(self.settings, self.tasks, self.launch)
        self.assertEqual(
            (
                self.settings.read_bytes(),
                self.tasks.read_bytes(),
                self.launch.read_bytes(),
            ),
            before,
        )


    def test_activation_refuses_foreign_profile_or_default_profile_before_writes(self) -> None:
        cases = {
            self.module.MANAGED_PROFILES_KEY: {"Foreign": {"path": "/bin/zsh"}},
            self.module.MANAGED_DEFAULT_PROFILE_KEY: "zsh",
        }
        for key, value in cases.items():
            with self.subTest(key=key):
                scope = self.root / key.replace(".", "-")
                settings = scope / "settings.json"
                tasks = scope / "tasks.json"
                launch = scope / "launch.json"
                settings.parent.mkdir(parents=True)
                original = json.dumps({key: value}, indent=2) + "\n"
                settings.write_text(original, encoding="utf-8")
                with self.assertRaises(SystemExit) as raised:
                    self.module.activate(
                        settings,
                        tasks,
                        launch,
                        environ=self.sdk_environment,
                    )
                self.assertIn("GATE_BLOCK", str(raised.exception))
                self.assertEqual(settings.read_text(encoding="utf-8"), original)
                self.assertFalse(tasks.exists())
                self.assertFalse(launch.exists())

    def test_profile_drift_is_neither_active_nor_deletable(self) -> None:
        self.settings.write_text("{}\n", encoding="utf-8")
        self.module.activate(
            self.settings,
            self.tasks,
            self.launch,
            environ=self.sdk_environment,
        )
        current = self.settings.read_text(encoding="utf-8")
        drifted = current.replace(
            self.module.PROFILE_LAUNCHER_VALUE,
            "/bin/zsh",
            1,
        )
        self.settings.write_text(drifted, encoding="utf-8")
        before = (
            self.settings.read_bytes(),
            self.tasks.read_bytes(),
            self.launch.read_bytes(),
        )
        result = self.module.status(
            self.settings,
            self.tasks,
            self.launch,
            environ=self.sdk_environment,
        )
        self.assertEqual(result["projectionState"], "partial")
        self.assertNotEqual(result["effectiveState"], "active")
        with self.assertRaises(SystemExit):
            self.module.deactivate(self.settings, self.tasks, self.launch)
        self.assertEqual(
            (self.settings.read_bytes(), self.tasks.read_bytes(), self.launch.read_bytes()),
            before,
        )

    def test_known_sdk_env_projection_migrates_to_profile_and_restores_baseline(self) -> None:
        baseline = '{\n    "editor.formatOnSave": true\n}\n'
        binding = self.module._resolved_sdk_binding(self.sdk_environment)
        legacy = baseline[:1] + "\n" + self.module._managed_sdk_env_block(binding) + "\n" + baseline[1:]
        self.settings.write_text(legacy, encoding="utf-8")
        self.assertEqual(
            self.module.activate(
                self.settings,
                self.tasks,
                self.launch,
                environ=self.sdk_environment,
            ),
            "refreshed",
        )
        parsed = self.module._parse_settings(self.settings.read_text(encoding="utf-8"))
        self.assertIn(self.module.MANAGED_PROFILES_KEY, parsed)
        self.assertEqual(
            self.module.deactivate(self.settings, self.tasks, self.launch),
            "deactivated",
        )
        self.assertEqual(self.settings.read_text(encoding="utf-8"), baseline)

    def test_operator_docs_only_publish_canonical_flutter_startup_recovery(
        self,
    ) -> None:
        documents = [
            REPO_ROOT / "quwoquan_app/docs/FLUTTER_DEBUG_PROXY.md",
            REPO_ROOT / "quwoquan_app/ios/CODE_SIGNING_SETUP.md",
            REPO_ROOT / "quwoquan_app/ios/Flutter/README_SDKROOT.md",
        ]
        for document in documents:
            with self.subTest(document=document.name):
                text = document.read_text(encoding="utf-8")
                self.assertIn("make app-activate-flutter-facade", text)
                self.assertIn("Reload Window", text)
                self.assertIn("command -v flutter", text)

        debug_proxy = documents[0].read_text(encoding="utf-8")
        self.assertNotIn("flutter run --host-vmservice-port", debug_proxy)
        self.assertNotIn("flutter run --no-pub", debug_proxy)
        signing = documents[1].read_text(encoding="utf-8")
        self.assertNotIn('flutter run -d "iPhone', signing)


if __name__ == "__main__":
    unittest.main()
