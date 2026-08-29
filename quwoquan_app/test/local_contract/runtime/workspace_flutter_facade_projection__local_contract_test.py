#!/usr/bin/env python3
"""Local contract for the exact Cursor workspace Flutter projection."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[4]
ACTIVATION_SCRIPT = (
    REPO_ROOT
    / "quwoquan_app/scripts/tools/flutter_facade/activate_cursor_workspace.py"
)


def _load_activation_module():
    spec = importlib.util.spec_from_file_location("qwq_cursor_activation", ACTIVATION_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load workspace activation module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WorkspaceFlutterFacadeProjectionLocalContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.settings = self.root / ".vscode/settings.json"
        self.tasks = self.settings.with_name("tasks.json")
        self.launch = self.settings.with_name("launch.json")
        self.settings.parent.mkdir(parents=True)
        self.module = _load_activation_module()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_activation_projects_exact_managed_settings_and_restores_bytes(self) -> None:
        original = '{\n    "editor.formatOnSave": true\n}\n'
        self.settings.write_text(original, encoding="utf-8")

        outcome = self.module.activate(self.settings, self.tasks, self.launch)

        self.assertEqual(outcome, "activated")
        parsed = self.module._parse_settings(
            self.settings.read_text(encoding="utf-8")
        )
        self.assertIs(parsed["dart.addSdkToTerminalPath"], False)
        self.assertEqual(
            parsed["terminal.integrated.env.osx"],
            {
                "PATH": self.module.FACADE_PATH_VALUE,
                "QWQ_WORKSPACE_FLUTTER_FACADE_BIN": self.module.FACADE_BIN_VALUE,
                "QWQ_WORKSPACE_ORIGINAL_ZDOTDIR": "${env:ZDOTDIR}",
                "ZDOTDIR": self.module.ZDOTDIR_VALUE,
            },
        )
        self.assertEqual(self.tasks.read_text(encoding="utf-8"), self.module._tasks_projection())
        self.assertEqual(self.launch.read_text(encoding="utf-8"), self.module._launch_projection())

        self.assertEqual(
            self.module.deactivate(self.settings, self.tasks, self.launch),
            "deactivated",
        )
        self.assertEqual(self.settings.read_text(encoding="utf-8"), original)
        self.assertFalse(self.tasks.exists())
        self.assertFalse(self.launch.exists())

    def test_activation_refuses_all_foreign_managed_keys_before_any_write(self) -> None:
        original = '{\n    "dart.addSdkToTerminalPath": true\n}\n'
        self.settings.write_text(original, encoding="utf-8")

        with self.assertRaises(SystemExit) as raised:
            self.module.activate(self.settings, self.tasks, self.launch)

        self.assertIn("GATE_BLOCK", str(raised.exception))
        self.assertEqual(self.settings.read_text(encoding="utf-8"), original)
        self.assertFalse(self.tasks.exists())
        self.assertFalse(self.launch.exists())

    def test_deactivation_refuses_marker_owned_but_drifted_projection_atomically(self) -> None:
        original = '{\n    "editor.formatOnSave": true\n}\n'
        self.settings.write_text(original, encoding="utf-8")
        self.module.activate(self.settings, self.tasks, self.launch)
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

    def test_deactivation_refuses_malformed_settings_marker_before_deleting_ide_files(self) -> None:
        self.settings.write_text("{}\n", encoding="utf-8")
        self.module.activate(self.settings, self.tasks, self.launch)
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
        self.module.activate(self.settings, self.tasks, self.launch)
        expected = (
            self.module.REPO_ROOT
            / "quwoquan_app/scripts/tools/flutter_facade/bin/flutter"
        )
        with mock.patch.object(self.module.shutil, "which", return_value=str(expected)):
            active = self.module.status(self.settings, self.tasks, self.launch)
        self.assertEqual(active["effectiveState"], "active")

        self.tasks.write_text(
            self.tasks.read_text(encoding="utf-8") + "// marker-only drift\n",
            encoding="utf-8",
        )
        with mock.patch.object(self.module.shutil, "which", return_value=str(expected)):
            drifted = self.module.status(self.settings, self.tasks, self.launch)
        self.assertEqual(drifted["projectionState"], "partial")
        self.assertEqual(drifted["effectiveState"], "inconsistent")

    def test_status_cli_fails_closed_without_disclosing_raw_path(self) -> None:
        self.settings.write_text("{}\n", encoding="utf-8")
        self.module.activate(self.settings, self.tasks, self.launch)
        real_sdk = self.root / "real-sdk"
        real_sdk.mkdir()
        flutter = real_sdk / "flutter"
        flutter.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        flutter.chmod(flutter.stat().st_mode | stat.S_IXUSR)
        environment = dict(os.environ)
        environment["PATH"] = f"{real_sdk}:/usr/bin:/bin"

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
        self.assertIn("command -v flutter", result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["effectiveState"], "reload_required")
        self.assertNotIn(str(real_sdk), result.stdout + result.stderr)
        self.assertNotIn(environment["PATH"], result.stdout + result.stderr)

    def test_operator_docs_only_publish_canonical_flutter_startup_recovery(self) -> None:
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
