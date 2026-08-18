from __future__ import annotations

import importlib.util
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "quwoquan_app").is_dir() and (
            candidate / "quwoquan_service"
        ).is_dir():
            return candidate
    raise RuntimeError("cannot locate quwoquan repo root")


ROOT = _repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.local_environment_auth import LocalAcceptanceSession


def _load_runner():
    path = (
        ROOT
        / "quwoquan_ops"
        / "tests"
        / "acceptance"
        / "user_acceptance"
        / "service_ops"
        / "assistant-service"
        / "ci"
        / "run_assistant_device_matrix.py"
    )
    spec = importlib.util.spec_from_file_location(
        "assistant_device_matrix_local_contract",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load assistant device matrix runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AssistantDeviceMatrixLocalContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = _load_runner()

    def test_environment_uses_current_canonical_test_tree(self) -> None:
        for environment in ("alpha", "beta", "gamma"):
            self.assertEqual(
                self.runner.test_path_for_environment(environment),
                self.runner.USER_ACCEPTANCE_TEST_PATH,
            )
        self.assertTrue(
            (
                ROOT / "quwoquan_app" / self.runner.USER_ACCEPTANCE_TEST_PATH
            ).is_file()
        )
        with self.assertRaisesRegex(ValueError, "unsupported env"):
            self.runner.test_path_for_environment("prod")

    def test_private_defines_are_owner_only_and_receipt_is_redacted(self) -> None:
        path = self.runner.write_private_flutter_defines(
            {
                "TEST_AUTH_TOKEN": "access-secret",
                "TEST_PERSONA_ID": "persona-secret",
            }
        )
        self.addCleanup(path.unlink, missing_ok=True)

        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(
            json.loads(path.read_text(encoding="utf-8"))["TEST_AUTH_TOKEN"],
            "access-secret",
        )
        public = self.runner.public_command(
            ["flutter", "test", f"--dart-define-from-file={path}"]
        )
        self.assertEqual(
            public[-1],
            "--dart-define-from-file=" + self.runner.PRIVATE_DEFINES_PLACEHOLDER,
        )
        self.assertNotIn("access-secret", json.dumps(public))
        self.assertNotIn(str(path), json.dumps(public))

    def test_beta_remote_matrix_uses_temporary_actor_and_always_cleans_up(self) -> None:
        actor = self.runner.LocalAcceptanceActor(
            role="assistant-device-matrix",
            session=LocalAcceptanceSession(
                owner_id="owner-id",
                persona_id="persona-secret",
                access_token="access-secret",
                refresh_token="refresh-secret",
            ),
            challenge_id="challenge-id",
            account_state="active",
            identity_origin="test-data",
        )
        device = {
            "id": "ios-device",
            "name": "iPhone",
            "targetPlatform": "ios",
            "screenClass": "phone",
            "gatewayBaseUrl": "https://api.beta.quwoquan.com:18000",
        }
        args = SimpleNamespace(
            gateway_health_url="https://api.beta.quwoquan.com:18000",
            gateway_port=18000,
            test_timeout_seconds=30,
            remote_retry_attempts=0,
            retry_wait_timeout_seconds=1,
            retry_sleep_seconds=0,
        )
        captured_private_path: list[Path] = []
        captured_defines: list[dict[str, str]] = []
        captured_receipts: list[dict[str, object]] = []

        def fake_run(command, **_kwargs):
            private_argument = next(
                item for item in command if item.startswith("--dart-define-from-file=")
            )
            private_path = Path(private_argument.split("=", 1)[1])
            captured_private_path.append(private_path)
            captured_defines.append(json.loads(private_path.read_text(encoding="utf-8")))
            return {
                "command": command,
                "cwd": str(ROOT / "quwoquan_app"),
                "exitCode": 0,
                "durationMs": 1,
                "timedOut": False,
                "outputSummary": "passed",
                "logPath": "flutter-test.log",
            }

        def fake_write_json(_path, document):
            captured_receipts.append(document)
            return "command.json"

        local_root = ROOT / ".qwq_output" / "env" / "repo" / "local"
        local_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as temporary:
            with (
                mock.patch.object(
                    self.runner,
                    "open_test_actor",
                    return_value=(actor, "assistant-device-beta-instance"),
                ),
                mock.patch.object(
                    self.runner,
                    "close_test_data_acceptance_actor",
                ) as close_actor,
                mock.patch.object(
                    self.runner,
                    "write_device_manifest",
                    return_value="device.json",
                ),
                mock.patch.object(
                    self.runner,
                    "capture_device_screenshot",
                    return_value={"status": "captured"},
                ),
                mock.patch.object(self.runner, "write_json", side_effect=fake_write_json),
                mock.patch.object(self.runner, "run_command", side_effect=fake_run),
            ):
                result = self.runner.run_matrix_test(
                    "beta",
                    device,
                    args,
                    evidence_root=Path(temporary),
                )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["testDataLifecycle"]["cleanupStatus"], "passed")
        self.assertEqual(
            captured_defines,
            [
                {
                    "APP_RUNTIME_ENV": "beta",
                    "API_CONTRACT_BASE_URL": device["gatewayBaseUrl"],
                    "API_CONTRACT_ENV": "beta",
                    "APP_CURRENT_OWNER_ID": "owner-id",
                    "APP_CURRENT_PERSONA_ID": "persona-secret",
                    "CLOUD_GATEWAY_BASE_URL": device["gatewayBaseUrl"],
                    "RUN_PATROL_ACCEPTANCE": "true",
                    "TEST_AUTH_TOKEN": "access-secret",
                    "TEST_REFRESH_TOKEN": "refresh-secret",
                    "VALIDATION_SCREEN_CLASS": "phone",
                }
            ],
        )
        self.assertFalse(captured_private_path[0].exists())
        close_actor.assert_called_once_with(
            args.gateway_health_url,
            actor=actor,
            test_data_instance_id="assistant-device-beta-instance",
        )
        serialized_result = json.dumps(result, ensure_ascii=False)
        serialized_receipts = json.dumps(captured_receipts, ensure_ascii=False)
        for secret in ("access-secret", "persona-secret", "refresh-secret"):
            self.assertNotIn(secret, serialized_result)
            self.assertNotIn(secret, serialized_receipts)
        self.assertIn(
            self.runner.PRIVATE_DEFINES_PLACEHOLDER,
            serialized_result,
        )
        self.assertIn(self.runner.USER_ACCEPTANCE_TEST_PATH, serialized_result)

    def test_cleanup_failure_blocks_an_otherwise_successful_remote_run(self) -> None:
        actor = self.runner.LocalAcceptanceActor(
            role="assistant-device-matrix",
            session=LocalAcceptanceSession(
                owner_id="owner-id",
                persona_id="persona-id",
                access_token="access-token",
            ),
            challenge_id="challenge-id",
            account_state="active",
            identity_origin="test-data",
        )
        device = {
            "id": "ios-device",
            "name": "iPhone",
            "targetPlatform": "ios",
            "screenClass": "phone",
            "gatewayBaseUrl": "https://api.beta.quwoquan.com:18000",
        }
        args = SimpleNamespace(
            gateway_health_url="https://api.beta.quwoquan.com:18000",
            gateway_port=18000,
            test_timeout_seconds=30,
            remote_retry_attempts=0,
            retry_wait_timeout_seconds=1,
            retry_sleep_seconds=0,
        )
        command_result = {
            "command": [],
            "cwd": str(ROOT / "quwoquan_app"),
            "exitCode": 0,
            "durationMs": 1,
            "timedOut": False,
            "outputSummary": "passed",
            "logPath": "flutter-test.log",
        }
        local_root = ROOT / ".qwq_output" / "env" / "repo" / "local"
        local_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as temporary:
            with (
                mock.patch.object(
                    self.runner,
                    "open_test_actor",
                    return_value=(actor, "assistant-device-beta-instance"),
                ),
                mock.patch.object(
                    self.runner,
                    "close_test_data_acceptance_actor",
                    side_effect=RuntimeError("cleanup failed"),
                ),
                mock.patch.object(
                    self.runner,
                    "write_device_manifest",
                    return_value="device.json",
                ),
                mock.patch.object(
                    self.runner,
                    "capture_device_screenshot",
                    return_value={"status": "captured"},
                ),
                mock.patch.object(
                    self.runner,
                    "write_json",
                    return_value="command.json",
                ),
                mock.patch.object(
                    self.runner,
                    "run_command",
                    return_value=command_result,
                ),
            ):
                result = self.runner.run_matrix_test(
                    "beta",
                    device,
                    args,
                    evidence_root=Path(temporary),
                )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["failureCategory"], "test_actor_cleanup_failed")
        self.assertEqual(result["testDataLifecycle"]["cleanupStatus"], "failed")

    def test_receipt_failure_removes_private_defines_and_closes_actor(self) -> None:
        actor = self.runner.LocalAcceptanceActor(
            role="assistant-device-matrix",
            session=LocalAcceptanceSession(
                owner_id="owner-id",
                persona_id="persona-id",
                access_token="access-token",
                refresh_token="refresh-token",
            ),
            challenge_id="challenge-id",
            account_state="active",
            identity_origin="test-data",
        )
        device = {
            "id": "ios-device",
            "name": "iPhone",
            "targetPlatform": "ios",
            "screenClass": "phone",
            "gatewayBaseUrl": "https://api.beta.quwoquan.com:18000",
        }
        args = SimpleNamespace(
            gateway_health_url="https://api.beta.quwoquan.com:18000",
            gateway_port=18000,
            test_timeout_seconds=30,
            remote_retry_attempts=0,
            retry_wait_timeout_seconds=1,
            retry_sleep_seconds=0,
        )
        private_paths: list[Path] = []
        original_write_private = self.runner.write_private_flutter_defines

        def capture_private(defines):
            path = original_write_private(defines)
            private_paths.append(path)
            return path

        local_root = ROOT / ".qwq_output" / "env" / "repo" / "local"
        local_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as temporary:
            with (
                mock.patch.object(
                    self.runner,
                    "open_test_actor",
                    return_value=(actor, "assistant-device-beta-instance"),
                ),
                mock.patch.object(
                    self.runner,
                    "close_test_data_acceptance_actor",
                ) as close_actor,
                mock.patch.object(
                    self.runner,
                    "write_private_flutter_defines",
                    side_effect=capture_private,
                ),
                mock.patch.object(
                    self.runner,
                    "write_device_manifest",
                    return_value="device.json",
                ),
                mock.patch.object(
                    self.runner,
                    "capture_device_screenshot",
                    return_value={"status": "captured"},
                ),
                mock.patch.object(
                    self.runner,
                    "write_json",
                    side_effect=OSError("receipt unavailable"),
                ),
            ):
                with self.assertRaisesRegex(OSError, "receipt unavailable"):
                    self.runner.run_matrix_test(
                        "beta",
                        device,
                        args,
                        evidence_root=Path(temporary),
                    )

        self.assertEqual(len(private_paths), 1)
        self.assertFalse(private_paths[0].exists())
        close_actor.assert_called_once_with(
            args.gateway_health_url,
            actor=actor,
            test_data_instance_id="assistant-device-beta-instance",
        )

    def test_interrupt_and_cleanup_failures_are_both_preserved(self) -> None:
        actor = self.runner.LocalAcceptanceActor(
            role="assistant-device-matrix",
            session=LocalAcceptanceSession(
                owner_id="owner-id",
                persona_id="persona-id",
                access_token="access-token",
                refresh_token="refresh-token",
            ),
            challenge_id="challenge-id",
            account_state="active",
            identity_origin="test-data",
        )
        device = {
            "id": "ios-device",
            "name": "iPhone",
            "targetPlatform": "ios",
            "screenClass": "phone",
            "gatewayBaseUrl": "https://api.beta.quwoquan.com:18000",
        }
        args = SimpleNamespace(
            gateway_health_url="https://api.beta.quwoquan.com:18000",
            gateway_port=18000,
            test_timeout_seconds=30,
            remote_retry_attempts=0,
            retry_wait_timeout_seconds=1,
            retry_sleep_seconds=0,
        )
        private_paths: list[Path] = []
        original_write_private = self.runner.write_private_flutter_defines

        def capture_private(defines):
            path = original_write_private(defines)
            private_paths.append(path)
            return path

        local_root = ROOT / ".qwq_output" / "env" / "repo" / "local"
        local_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as temporary:
            with (
                mock.patch.object(
                    self.runner,
                    "open_test_actor",
                    return_value=(actor, "assistant-device-beta-instance"),
                ),
                mock.patch.object(
                    self.runner,
                    "close_test_data_acceptance_actor",
                    side_effect=RuntimeError("cleanup failed"),
                ),
                mock.patch.object(
                    self.runner,
                    "write_private_flutter_defines",
                    side_effect=capture_private,
                ),
                mock.patch.object(
                    self.runner,
                    "write_device_manifest",
                    return_value="device.json",
                ),
                mock.patch.object(
                    self.runner,
                    "capture_device_screenshot",
                    return_value={"status": "captured"},
                ),
                mock.patch.object(
                    self.runner,
                    "write_json",
                    return_value="command.json",
                ),
                mock.patch("builtins.print", side_effect=KeyboardInterrupt()),
            ):
                with self.assertRaises(BaseExceptionGroup) as raised:
                    self.runner.run_matrix_test(
                        "beta",
                        device,
                        args,
                        evidence_root=Path(temporary),
                    )

        self.assertEqual(len(private_paths), 1)
        self.assertFalse(private_paths[0].exists())
        self.assertEqual(len(raised.exception.exceptions), 2)
        self.assertIsInstance(raised.exception.exceptions[0], KeyboardInterrupt)
        self.assertRegex(
            str(raised.exception.exceptions[1]),
            "candidate-bound assistant test actor cleanup failed",
        )


if __name__ == "__main__":
    unittest.main()
