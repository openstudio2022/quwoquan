"""Local contract for Cursor terminal surface readiness receipts."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
ACTIVATION_SCRIPT = (
    REPO_ROOT / "quwoquan_app/scripts/tools/flutter_facade/activate_cursor_workspace.py"
)


def _load_activation_module():
    spec = importlib.util.spec_from_file_location(
        "qwq_cursor_terminal_receipt_activation", ACTIVATION_SCRIPT
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


class WorkspaceFlutterFacadeTerminalReceiptLocalContractTest(unittest.TestCase):
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

    def _write_surface_receipt(
        self,
        *,
        surface: str,
        shell_pid: int | None = None,
        shell_start: str | None = None,
        written_at_epoch_ms: int | None = None,
        generation: str | None = None,
        logical_root: Path | None = None,
    ) -> Path:
        binding = self.module._resolved_sdk_binding(self.sdk_environment)
        receipt_root = self.root / "receipts"
        receipt_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        pid = os.getpid() if shell_pid is None else shell_pid
        start = self.module._load_receipt_module().process_start(os.getpid())
        payload = {
            "schema": "qwq.flutter-facade-terminal-receipt.v1",
            "surface": surface,
            "workspaceUri": str(logical_root or self.module.REPO_ROOT),
            "workspaceLogicalRoot": str(logical_root or self.module.REPO_ROOT),
            "workspacePhysicalRoot": str(self.module.REPO_ROOT.resolve()),
            "shellPid": pid,
            "shellStart": shell_start or start,
            "writtenAtEpochMs": (
                time.time_ns() // 1_000_000
                if written_at_epoch_ms is None
                else written_at_epoch_ms
            ),
            "finalStateValidated": True,
            "facadeRealpath": str(
                (
                    self.module.REPO_ROOT
                    / "quwoquan_app/scripts/tools/flutter_facade/bin/flutter"
                ).resolve()
            ),
            "qwqIdentity": {
                "facadeBinRealpath": str(
                    (
                        self.module.REPO_ROOT
                        / "quwoquan_app/scripts/tools/flutter_facade/bin"
                    ).resolve()
                ),
                "realFlutterRealpath": binding["executable"],
                "realFlutterVersion": binding["flutterVersion"],
                "commandResolutionDigest": binding["commandResolutionDigest"],
            },
            "projectionSeal": self.module._projection_seal(
                binding, self.pod_binding, self.python_binding
            ),
            "projectionGeneration": generation or self.module._projection_generation(
                binding, self.pod_binding, self.python_binding
            ),
        }
        target = receipt_root / f"{surface}--fixture.json"
        target.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        target.chmod(0o600)
        return receipt_root

    def test_status_requires_fresh_receipt_for_the_exact_requested_surface(self) -> None:
        self.settings.write_text("{}\n", encoding="utf-8")
        self.module.activate(
            self.settings,
            self.tasks,
            self.launch,
            environ=self.sdk_environment,
        )
        receipt_root = self._write_surface_receipt(surface="folder-new-terminal")
        folder = self.module.status(
            self.settings,
            self.tasks,
            self.launch,
            environ=self.sdk_environment,
            surface="folder-new-terminal",
            receipt_root=receipt_root,
        )
        agents = self.module.status(
            self.settings,
            self.tasks,
            self.launch,
            environ=self.sdk_environment,
            surface="agents-window",
            receipt_root=receipt_root,
        )
        self.assertEqual(folder["effectiveState"], "active")
        self.assertEqual(folder["targetSurfaceReceiptState"], "active")
        self.assertEqual(agents["effectiveState"], "probe_required")
        self.assertEqual(agents["targetSurfaceReceiptState"], "missing")

    def test_status_rejects_stale_pid_start_generation_and_root_receipts(self) -> None:
        self.settings.write_text("{}\n", encoding="utf-8")
        self.module.activate(
            self.settings,
            self.tasks,
            self.launch,
            environ=self.sdk_environment,
        )
        stale_cases = {
            "pid": {"shell_pid": 999999},
            "start": {"shell_start": "stale-start"},
            "generation": {"generation": "sha256:" + "0" * 64},
            "age": {"written_at_epoch_ms": 1},
            "root": {"logical_root": self.root},
        }
        for name, kwargs in stale_cases.items():
            with self.subTest(case=name):
                receipt_root = self._write_surface_receipt(
                    surface="folder-new-terminal",
                    **kwargs,
                )
                result = self.module.status(
                    self.settings,
                    self.tasks,
                    self.launch,
                    environ=self.sdk_environment,
                    surface="folder-new-terminal",
                    receipt_root=receipt_root,
                )
                self.assertEqual(result["effectiveState"], "probe_required")
                self.assertEqual(
                    result["targetSurfaceReceiptState"],
                    "invalid_or_stale",
                )
                for candidate in receipt_root.glob("*.json"):
                    candidate.unlink()

    def test_receipt_create_once_rejects_same_identity_with_different_bytes(self) -> None:
        receipt_module = self.module._load_receipt_module()
        binding = self.module._resolved_sdk_binding(self.sdk_environment)
        environment = {
            **self.sdk_environment,
            "QWQ_WORKSPACE_FLUTTER_FACADE_BIN": str(
                self.module.REPO_ROOT
                / "quwoquan_app/scripts/tools/flutter_facade/bin"
            ),
            "QWQ_REAL_FLUTTER": binding["executable"],
            "QWQ_REAL_FLUTTER_VERSION": binding["flutterVersion"],
            "QWQ_REAL_FLUTTER_COMMAND_RESOLUTION_DIGEST": binding[
                "commandResolutionDigest"
            ],
            "QWQ_TERMINAL_FINAL_FLUTTER_COMMAND_REALPATH": str(
                self.module.REPO_ROOT
                / "quwoquan_app/scripts/tools/flutter_facade/bin/flutter"
            ),
            "QWQ_TERMINAL_FINAL_POD_COMMAND_REALPATH": str(self.fake_pod.resolve()),
            **self.pod_binding,
            "QWQ_WORKSPACE_PYTHON": self.python_binding["executable"],
            "QWQ_WORKSPACE_PYTHON_VERSION": self.python_binding["version"],
            "QWQ_TERMINAL_PROJECTION_SEAL": self.module._projection_seal(
                binding, self.pod_binding, self.python_binding
            ),
            "QWQ_TERMINAL_PROJECTION_GENERATION": self.module._projection_generation(
                binding, self.pod_binding, self.python_binding
            ),
        }
        receipt_root = self.root / "create-once"
        first = receipt_module.write_receipt(
            surface="unknown",
            shell_pid=os.getpid(),
            workspace_uri=str(self.module.REPO_ROOT),
            logical_root=str(self.module.REPO_ROOT),
            physical_root=str(self.module.REPO_ROOT.resolve()),
            environ=environment,
            receipt_root=receipt_root,
        )
        payload = json.loads(first.read_text(encoding="utf-8"))
        payload["writtenAtEpochMs"] += 1
        first.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(receipt_module.ReceiptError):
            receipt_module.write_receipt(
                surface="unknown",
                shell_pid=os.getpid(),
                workspace_uri=str(self.module.REPO_ROOT),
                logical_root=str(self.module.REPO_ROOT),
                physical_root=str(self.module.REPO_ROOT.resolve()),
                environ=environment,
                receipt_root=receipt_root,
            )

    def test_receipt_reuse_cannot_cross_projection_generation(self) -> None:
        self.settings.write_text("{}\n", encoding="utf-8")
        self.module.activate(
            self.settings,
            self.tasks,
            self.launch,
            environ=self.sdk_environment,
        )
        receipt_root = self._write_surface_receipt(surface="agents-window")
        binding = self.module._resolved_sdk_binding(self.sdk_environment)
        for candidate in receipt_root.glob("*.json"):
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            payload["projectionGeneration"] = "sha256:" + "f" * 64
            candidate.write_text(
                json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
        result = self.module.status(
            self.settings,
            self.tasks,
            self.launch,
            environ=self.sdk_environment,
            surface="agents-window",
            receipt_root=receipt_root,
        )
        self.assertEqual(result["targetSurfaceReceiptState"], "invalid_or_stale")
        self.assertNotEqual(result["effectiveState"], "active")
        self.assertRegex(binding["commandResolutionDigest"], r"^sha256:")



if __name__ == "__main__":
    import unittest

    unittest.main()
