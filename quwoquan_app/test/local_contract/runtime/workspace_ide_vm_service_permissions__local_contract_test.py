# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
#
# Layer: local_contract.  The controlled IDE projection may expose a VM-service
# auth URI only through an owner-private attempt and projection directory.  The
# canonical child must fail closed if it replaces the pre-created secret file
# with a symlink or a broader mode.

from __future__ import annotations

import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

APP_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = APP_ROOT.parent
IDE_LAUNCHER = (
    APP_ROOT / "scripts/tools/flutter_facade/run_workspace_ide_debug.py"
)
CANONICAL_INSTANCE = APP_ROOT / "scripts/device/run_app_instance.py"
DEVICE_SCRIPTS = APP_ROOT / "scripts/device"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(DEVICE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DEVICE_SCRIPTS))

from canonical_app_instance.vm_service_info_file import (
    VmServiceInfoSecurityError,
    workspace_projection_vm_service_allowed_root,
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ide_launcher = _load_module("workspace_ide_debug_under_test", IDE_LAUNCHER)
canonical_instance = _load_module(
    "canonical_instance_permissions_under_test", CANONICAL_INSTANCE
)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


class _ExecObserved(RuntimeError):
    pass


class _ImmediateThread:
    def __init__(self, *, target, daemon: bool) -> None:
        del daemon
        self._target = target

    def start(self) -> None:
        self._target()


class _AttachProcess:
    def __init__(self, output: str) -> None:
        self.stdout = io.StringIO(output)
        self.pid = 98765
        self.returncode = 0

    def poll(self) -> int:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        return self.returncode


class WorkspaceIdeVmServicePermissionsContractTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.runs_root = self.root / ".qwq_output/env/repo/runs"
        self.ide_root = self.root / ".qwq_output/env/repo/local/ide"
        self.app_root = self.root / "quwoquan_app"
        self.app_root.mkdir()
        self.launcher = self.app_root / "run.sh"
        self.launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.launcher.chmod(0o700)

    def _ide_constants(self):
        return mock.patch.multiple(
            ide_launcher,
            APP_ROOT=self.app_root,
            LAUNCHER=self.launcher,
            RUNS_ROOT=self.runs_root,
            IDE_LOCAL_ROOT=self.ide_root,
            CURRENT_SERVICE_INFO=self.ide_root / "current-vm-service-info.json",
            CURRENT_ATTEMPT=self.ide_root / "current-attempt.json",
        )

    def _write_current_attempt_projection(self) -> dict[str, object]:
        attempt_root = self.runs_root / "attempt-a"
        attempt_root.mkdir(parents=True, mode=0o700)
        payload = {
            "schema": "quwoquan.workspace_ide_attempt_projection",
            "environment": "alpha",
            "deviceId": "device-a",
            "attemptRoot": str(attempt_root),
            "vmServiceInfoFile": str(attempt_root / "vm-service-info.json"),
            "launchReceipt": str(attempt_root / "attempt.json"),
            "launchLog": str(attempt_root / "launch.log"),
            "processId": 4242,
        }
        self.ide_root.mkdir(parents=True, mode=0o700)
        (self.ide_root / "current-attempt.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
        return payload

    def test_malformed_current_attempt_is_not_treated_as_absent(self) -> None:
        self.ide_root.mkdir(parents=True, mode=0o700)
        (self.ide_root / "current-attempt.json").write_text(
            "{malformed",
            encoding="utf-8",
        )
        with self._ide_constants(), self.assertRaisesRegex(
            ide_launcher.WorkspaceIdeProjectionError,
            "projection is malformed",
        ):
            ide_launcher._active_attempt()

    def test_indeterminate_owner_probe_preserves_current_projection(self) -> None:
        payload = self._write_current_attempt_projection()
        projection = self.ide_root / "current-attempt.json"
        before = projection.read_bytes()
        with self._ide_constants(), mock.patch.object(
            ide_launcher.subprocess,
            "run",
            return_value=mock.Mock(returncode=2, stdout="", stderr="ps failed"),
        ), self.assertRaisesRegex(
            ide_launcher.WorkspaceIdeProjectionError,
            "indeterminate",
        ):
            ide_launcher._active_attempt()
        self.assertEqual(projection.read_bytes(), before)
        self.assertEqual(payload["processId"], 4242)

    def test_only_confirmed_absent_or_reused_owner_allows_replacement(self) -> None:
        payload = self._write_current_attempt_projection()
        with self._ide_constants(), mock.patch.object(
            ide_launcher.subprocess,
            "run",
            return_value=mock.Mock(returncode=1, stdout="", stderr="not found"),
        ):
            self.assertIsNone(ide_launcher._active_attempt())
        with self._ide_constants(), mock.patch.object(
            ide_launcher.subprocess,
            "run",
            return_value=mock.Mock(
                returncode=0,
                stdout="/usr/bin/unrelated-process\n",
                stderr="",
            ),
        ):
            self.assertIsNone(ide_launcher._active_attempt())
        with self._ide_constants(), mock.patch.object(
            ide_launcher.subprocess,
            "run",
            return_value=mock.Mock(
                returncode=0,
                stdout=f"python launcher {payload['attemptRoot']}\n",
                stderr="",
            ),
        ):
            self.assertEqual(ide_launcher._active_attempt(), payload)

    def test_ide_executor_precreates_owner_private_projection_and_secret_file(
        self,
    ) -> None:
        original_cwd = Path.cwd()
        original_umask = os.umask(0)
        self.addCleanup(os.umask, original_umask)
        self.addCleanup(os.chdir, original_cwd)
        with self._ide_constants(), mock.patch.object(
            ide_launcher.os,
            "execve",
            side_effect=_ExecObserved,
        ), self.assertRaises(_ExecObserved):
            ide_launcher.main(["--env", "alpha", "--device", "device-a"])

        attempts = list(self.runs_root.iterdir())
        self.assertEqual(len(attempts), 1)
        attempt_root = attempts[0]
        vm_service_info = attempt_root / "vm-service-info.json"
        current_projection = self.ide_root / "current-vm-service-info.json"

        self.assertEqual(_mode(attempt_root), 0o700)
        self.assertEqual(_mode(self.ide_root), 0o700)
        self.assertTrue(stat.S_ISREG(vm_service_info.lstat().st_mode))
        self.assertFalse(vm_service_info.is_symlink())
        self.assertEqual(vm_service_info.lstat().st_uid, os.geteuid())
        self.assertEqual(_mode(vm_service_info), 0o600)
        self.assertTrue(current_projection.is_symlink())
        self.assertEqual(current_projection.resolve(), vm_service_info)
        self.assertEqual(_mode(current_projection.parent), 0o700)

    def test_existing_projection_directory_is_tightened_before_symlink_publish(
        self,
    ) -> None:
        self.ide_root.mkdir(parents=True, mode=0o755)
        self.ide_root.chmod(0o755)
        attempt_root = self.runs_root / "attempt-a"
        attempt_root.mkdir(parents=True, mode=0o700)
        target = attempt_root / "vm-service-info.json"
        target.touch(mode=0o600)
        target.chmod(0o600)

        with self._ide_constants():
            ide_launcher._publish_service_info_projection(target)

        self.assertEqual(_mode(self.ide_root), 0o700)
        self.assertEqual(_mode(target), 0o600)
        self.assertEqual(
            (self.ide_root / "current-vm-service-info.json").resolve(),
            target,
        )

    def _secure_vm_service_file(self) -> Path:
        attempt_root = self.runs_root / "attempt-a"
        attempt_root.mkdir(parents=True, mode=0o700)
        attempt_root.chmod(0o700)
        path = attempt_root / "vm-service-info.json"
        path.touch(mode=0o600)
        path.chmod(0o600)
        return path

    def test_canonical_preflight_rejects_absent_broad_or_foreign_secret_file(
        self,
    ) -> None:
        secure_path = self._secure_vm_service_file()
        with mock.patch.object(canonical_instance, "ROOT", self.root):
            self.assertEqual(
                canonical_instance._validated_vm_service_info_file(
                    secure_path,
                    self.runs_root,
                ),
                secure_path,
            )

            secure_path.chmod(0o644)
            with self.assertRaisesRegex(
                canonical_instance.CanonicalExecutorError,
                "APP.LAUNCH.workspace_entrypoint_inactive.*0600",
            ):
                canonical_instance._validated_vm_service_info_file(
                    secure_path,
                    self.runs_root,
                )

            secure_path.chmod(0o600)
            with mock.patch.object(
                canonical_instance.os,
                "geteuid",
                return_value=os.geteuid() + 1,
            ), self.assertRaisesRegex(
                canonical_instance.CanonicalExecutorError,
                "APP.LAUNCH.workspace_entrypoint_inactive.*owner",
            ):
                canonical_instance._validated_vm_service_info_file(
                    secure_path,
                    self.runs_root,
                )

            secure_path.unlink()
            with self.assertRaisesRegex(
                canonical_instance.CanonicalExecutorError,
                "APP.LAUNCH.workspace_entrypoint_inactive.*pre-created",
            ):
                canonical_instance._validated_vm_service_info_file(
                    secure_path,
                    self.runs_root,
                )

    def test_original_workspace_allow_root_survives_projection_and_rejects_drift(
        self,
    ) -> None:
        projection_attempt = self.runs_root / "projection-attempt"
        capsule = projection_attempt / "input-capsule"
        projection = projection_attempt / "repo"
        capsule.mkdir(parents=True, mode=0o700)
        projection.mkdir(mode=0o700)
        manifest = capsule / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")
        vm_service_info = self._secure_vm_service_file()

        allowed_root = workspace_projection_vm_service_allowed_root(
            source_capsule_manifest=manifest,
            projection_root=projection,
            output_root=self.root / ".qwq_output",
        )

        self.assertEqual(allowed_root, self.runs_root.resolve())
        self.assertEqual(
            canonical_instance._validated_vm_service_info_file(
                vm_service_info,
                allowed_root,
            ),
            vm_service_info,
        )
        projected_runs = projection / ".qwq_output/env/repo/runs"
        projected_runs.mkdir(parents=True)
        with self.assertRaisesRegex(
            canonical_instance.CanonicalExecutorError,
            "attempt-scoped",
        ):
            canonical_instance._validated_vm_service_info_file(
                vm_service_info,
                projected_runs,
            )

        foreign_projection = self.runs_root / "foreign" / "repo"
        foreign_projection.mkdir(parents=True)
        with self.assertRaisesRegex(
            VmServiceInfoSecurityError,
            "does not bind one original output runs root",
        ):
            workspace_projection_vm_service_allowed_root(
                source_capsule_manifest=manifest,
                projection_root=foreign_projection,
                output_root=self.root / ".qwq_output",
            )

    def _attach_driver(self, path: Path):
        return canonical_instance.AndroidPlatformDriver(
            device_id="device-a",
            application_id="com.leadwise.quwoquan.nonprod.debug",
            entrypoint="lib/main_prod.dart",
            vm_service_info_file=path,
            vm_service_info_allowed_root=self.runs_root,
        )

    def _attach_with_child_write(self, path: Path, mutate) -> mock.Mock:
        process = _AttachProcess(
            '[{"event":"app.started","params":{"appId":"app-a"}}]\n'
        )
        callback = mock.Mock()

        def popen(*args, **kwargs):
            del args, kwargs
            mutate()
            return process

        with mock.patch.object(
            canonical_instance,
            "ROOT",
            self.root,
        ), mock.patch.object(
            canonical_instance.subprocess,
            "Popen",
            side_effect=popen,
        ), mock.patch.object(
            canonical_instance.threading,
            "Thread",
            _ImmediateThread,
        ):
            self._attach_driver(path).attach(
                (), timeout_seconds=1.0, on_attached=callback
            )
        return callback

    def test_child_write_is_revalidated_before_launch_milestone(self) -> None:
        path = self._secure_vm_service_file()

        callback = self._attach_with_child_write(
            path,
            lambda: path.write_text('{"uri":"secret"}', encoding="utf-8"),
        )

        callback.assert_called_once_with()
        self.assertEqual(_mode(path), 0o600)

    def test_child_mode_drift_fails_closed_before_launch_milestone(self) -> None:
        path = self._secure_vm_service_file()

        def broaden() -> None:
            path.write_text('{"uri":"secret"}', encoding="utf-8")
            path.chmod(0o644)

        with self.assertRaisesRegex(
            canonical_instance.CanonicalExecutorError,
            "APP.LAUNCH.workspace_entrypoint_inactive.*0600",
        ):
            self._attach_with_child_write(path, broaden)

    def test_child_symlink_replacement_fails_closed_before_launch_milestone(
        self,
    ) -> None:
        path = self._secure_vm_service_file()
        alternate = path.parent / "alternate.json"
        alternate.write_text('{"uri":"secret"}', encoding="utf-8")
        alternate.chmod(0o600)

        def replace_with_symlink() -> None:
            path.unlink()
            path.symlink_to(alternate)

        with self.assertRaisesRegex(
            canonical_instance.CanonicalExecutorError,
            "APP.LAUNCH.workspace_entrypoint_inactive.*non-symlink",
        ):
            self._attach_with_child_write(path, replace_with_symlink)


if __name__ == "__main__":
    unittest.main()
