from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[4]


def _load_module(name: str, relative_path: str) -> ModuleType:
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _managed_chat_avatar_environment(env_name: str = "gamma") -> dict[str, str]:
    values = {
        "QWQ_TEST_DATA_ENVIRONMENT": env_name,
        "QWQ_TEST_DATA_TARGET": f"{env_name}-local",
        "QWQ_TEST_DATA_CASE_RESULT_ID": "chat-avatar-current-run",
        "QWQ_TEST_DATA_INSTANCE_ID": f"{env_name}-chat-avatar-instance",
        "QWQ_TEST_DATA_CANDIDATE_BINDING_DIGEST": "sha256:" + "1" * 64,
        "QWQ_TEST_DATA_REQUEST_DIGEST": "sha256:" + "2" * 64,
        "QWQ_TEST_DATA_ACTOR_LEASE_ID": f"{env_name}-chat-avatar-lease",
        "QWQ_TEST_DATA_ACTOR_LEASE_GENERATION": "7",
        "QWQ_TEST_DATA_ACTOR_LEASE_STATE": "active",
        "QWQ_TEST_DATA_ACTOR_LEASE_EXPIRES_AT": "2099-01-01T00:00:00Z",
    }
    for index, role in enumerate(("PRIMARY", "SENDER", "RECEIVER", "MEMBER"), 1):
        prefix = f"QWQ_TEST_DATA_{role}"
        values.update(
            {
                f"{prefix}_OWNER_ID": f"managed-owner-{index}",
                f"{prefix}_PERSONA_ID": f"managed-persona-{index}",
                f"{prefix}_ACCESS_TOKEN": f"secret-access-{index}",
                f"{prefix}_REFRESH_TOKEN": f"secret-refresh-{index}",
            }
        )
    return values


class DeviceMatrixDomainProjectionLocalContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.assistant = _load_module(
            "assistant_device_matrix_ci_domain_contract",
            (
                "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
                "assistant-service/ci/run_assistant_device_matrix_ci.py"
            ),
        )
        cls.chat = _load_module(
            "chat_avatar_device_matrix_domain_contract",
            (
                "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
                "chat-service/ci/run_chat_avatar_device_matrix.py"
            ),
        )
        cls.chat_probe = _load_module(
            "chat_avatar_probe_domain_contract",
            (
                "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
                "chat-service/smoke/run_chat_avatar_e2e_probe.py"
            ),
        )
        cls.chat_ci = _load_module(
            "chat_avatar_device_matrix_ci_domain_contract",
            (
                "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
                "chat-service/ci/run_chat_avatar_device_matrix_ci.py"
            ),
        )
        cls.chat_gamma = _load_module(
            "chat_avatar_gamma_domain_contract",
            (
                "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
                "chat-service/gamma/run_local_gamma_avatar_e2e.py"
            ),
        )
        cls.chat_handoff = sys.modules["managed_chat_avatar_handoff"]

    def test_assistant_matrix_resolves_every_environment_from_topology(self) -> None:
        self.assertEqual(
            self.assistant.canonical_gateway_base_url("alpha"),
            "https://api.alpha.quwoquan.com:17000",
        )
        self.assertEqual(
            self.assistant.canonical_gateway_base_url("beta"),
            "https://api.beta.quwoquan.com:18000",
        )
        self.assertEqual(
            self.assistant.canonical_gateway_base_url("gamma"),
            "https://api.gamma.quwoquan.com:19000",
        )

    def test_assistant_wrapper_supplies_all_required_canonical_urls(self) -> None:
        with (
            mock.patch.object(
                self.assistant,
                "parse_args",
                return_value=SimpleNamespace(platform="android"),
            ),
            mock.patch.object(
                self.assistant,
                "discover_device_ids",
                return_value=["emulator-5554"],
            ),
            mock.patch.object(
                self.assistant.subprocess,
                "call",
                return_value=0,
            ) as call,
            mock.patch.object(
                self.assistant,
                "root_certificate_path",
                return_value=Path("/managed/beta-local/root.crt"),
            ),
            mock.patch.dict(
                self.assistant.os.environ,
                {"API_CONTRACT_ENV": "beta"},
                clear=True,
            ),
        ):
            self.assertEqual(self.assistant.main(), 0)

        command = call.call_args.args[0]
        canonical = "https://api.beta.quwoquan.com:18000"
        for argument in (
            "--gateway-base-url",
            "--ios-gateway-base-url",
            "--android-gateway-base-url",
            "--gateway-health-url",
        ):
            self.assertEqual(command[command.index(argument) + 1], canonical)
        self.assertNotIn("--skip-beta-services", command)

    def test_assistant_host_probe_uses_the_canonical_local_managed_ca(self) -> None:
        root = Path("/managed/beta-local/root.crt")
        with (
            mock.patch.object(
                self.assistant,
                "root_certificate_path",
                return_value=root,
            ) as resolve_root,
            mock.patch.dict(self.assistant.os.environ, {}, clear=True),
        ):
            self.assertEqual(self.assistant.configure_gateway_tls("beta"), root)
            self.assertEqual(self.assistant.os.environ["SSL_CERT_FILE"], str(root))

        resolve_root.assert_called_once_with("beta-local")

    def test_assistant_wrapper_blocks_before_device_execution_when_ca_is_missing(
        self,
    ) -> None:
        error = self.assistant.PublicDomainTlsError(
            "GATE_BLOCK: local-managed root certificate is missing for beta-local"
        )
        stderr = io.StringIO()
        with (
            mock.patch.object(
                self.assistant,
                "parse_args",
                return_value=SimpleNamespace(platform="ios"),
            ),
            mock.patch.object(
                self.assistant,
                "root_certificate_path",
                side_effect=error,
            ),
            mock.patch.object(self.assistant.subprocess, "call") as call,
            mock.patch.dict(
                self.assistant.os.environ,
                {"API_CONTRACT_ENV": "beta"},
                clear=True,
            ),
            mock.patch.object(self.assistant.sys, "stderr", stderr),
        ):
            self.assertEqual(self.assistant.main(), 2)

        call.assert_not_called()
        self.assertIn("GATE_BLOCK", stderr.getvalue())

    def test_chat_android_reverses_canonical_local_authority_ports(self) -> None:
        device = {"id": "emulator-5554", "targetPlatform": "android-arm64"}
        with mock.patch.object(
            self.chat,
            "run_command",
            return_value={"exitCode": 0},
        ) as run_command:
            results = self.chat.adb_reverse_if_needed(
                "gamma",
                device,
                [
                    "https://api.gamma.quwoquan.com:19000",
                    "https://cdn.gamma.quwoquan.com:19100/media/avatar",
                ],
            )

        self.assertEqual(len(results), 2)
        commands = [call.args[0] for call in run_command.call_args_list]
        self.assertIn(
            [
                "adb",
                "-s",
                "emulator-5554",
                "reverse",
                "tcp:19000",
                "tcp:19000",
            ],
            commands,
        )
        self.assertIn(
            [
                "adb",
                "-s",
                "emulator-5554",
                "reverse",
                "tcp:19100",
                "tcp:19100",
            ],
            commands,
        )

    def test_chat_prod_never_installs_local_port_reverse(self) -> None:
        with mock.patch.object(self.chat, "run_command") as run_command:
            self.assertEqual(
                self.chat.adb_reverse_if_needed(
                    "prod",
                    {"id": "device", "targetPlatform": "android-arm64"},
                    ["https://api.quwoquan.com"],
                ),
                [],
            )
        run_command.assert_not_called()

    def test_chat_probe_rejects_noncanonical_endpoint_arguments(self) -> None:
        valid = SimpleNamespace(
            env="gamma",
            base_url="https://api.gamma.quwoquan.com:19000",
            media_avatar_base_url=(
                "https://cdn.gamma.quwoquan.com:19100/media/avatar"
            ),
        )
        self.chat_probe.validate_topology_endpoints(valid)

        invalid = SimpleNamespace(
            env="gamma",
            base_url="https://untrusted.example.invalid",
            media_avatar_base_url=valid.media_avatar_base_url,
        )
        with self.assertRaisesRegex(ValueError, "canonical topology projection"):
            self.chat_probe.validate_topology_endpoints(invalid)

    def test_chat_avatar_actor_handoff_is_current_run_bound_and_secret_free(
        self,
    ) -> None:
        environment = _managed_chat_avatar_environment()
        handoff = self.chat_handoff.load_managed_handoff_from_environment(
            environment
        )

        self.assertEqual(handoff.environment, "gamma")
        self.assertEqual(handoff.target, "gamma-local")
        self.assertEqual(len(handoff.actors), 4)
        command = handoff.command_arguments()
        public = json.dumps(handoff.public_document(), sort_keys=True)
        for secret in handoff.secret_values():
            self.assertNotIn(secret, command)
            self.assertNotIn(secret, public)
        for required in (
            "--test-data-case-result-id",
            "--test-data-instance-id",
            "--candidate-binding-digest",
            "--request-digest",
            "--actor-lease-id",
            "--actor-lease-generation",
            "--actor-lease-state",
            "--actor-lease-expires-at",
            "--creator-id",
            "--initial-member-id",
            "--added-member-id",
            "--removed-member-id",
        ):
            self.assertIn(required, command)

        incomplete = dict(environment)
        incomplete.pop("QWQ_TEST_DATA_REQUEST_DIGEST")
        with self.assertRaisesRegex(ValueError, "handoff is incomplete"):
            self.chat_handoff.load_managed_handoff_from_environment(incomplete)

    def test_chat_avatar_probe_has_no_fixed_identity_or_secret_argument(
        self,
    ) -> None:
        paths = (
            "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
            "chat-service/smoke/run_chat_avatar_e2e_probe.py",
            "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
            "chat-service/ci/run_chat_avatar_device_matrix.py",
            "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
            "chat-service/ci/run_chat_avatar_device_matrix_ci.py",
            "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
            "chat-service/gamma/run_local_gamma_avatar_e2e.py",
        )
        sources = [(ROOT / path).read_text(encoding="utf-8") for path in paths]
        for source in sources:
            self.assertNotIn("user_test_00", source)
            self.assertNotIn("--test-auth-token", source)

        with (
            mock.patch.object(
                self.chat_probe.sys,
                "argv",
                [
                    "run_chat_avatar_e2e_probe.py",
                    "--env",
                    "gamma",
                    "--base-url",
                    "https://api.gamma.quwoquan.com:19000",
                ],
            ),
            mock.patch("sys.stderr", new=io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as raised:
                self.chat_probe.parse_args()
        self.assertEqual(raised.exception.code, 2)

    def test_chat_avatar_wrappers_project_only_managed_handoff_arguments(
        self,
    ) -> None:
        handoff = self.chat_handoff.load_managed_handoff_from_environment(
            _managed_chat_avatar_environment()
        )
        ci_command = self.chat_ci.build_matrix_command(
            platform="android",
            env_name="gamma",
            device_ids=["emulator-5554"],
            handoff=handoff,
        )
        gamma_args = SimpleNamespace(
            base_url="https://api.gamma.quwoquan.com:19000",
            media_avatar_base_url=(
                "https://cdn.gamma.quwoquan.com:19100/media/avatar"
            ),
            platform="android",
            device_id=["emulator-5554"],
            dry_run=False,
        )
        gamma_probe_command = self.chat_gamma.build_probe_command(
            gamma_args,
            Path("/tmp/chat-avatar-probe.json"),
            handoff,
        )
        gamma_matrix_command = self.chat_gamma.build_matrix_command(
            gamma_args,
            Path("/tmp/chat-avatar-matrix.json"),
            handoff,
        )
        for command in (ci_command, gamma_probe_command, gamma_matrix_command):
            joined = "\n".join(command)
            for argument in handoff.command_arguments():
                self.assertIn(argument, command)
            for secret in handoff.secret_values():
                self.assertNotIn(secret, joined)

    def test_chat_avatar_patrol_secret_file_is_ephemeral_and_not_reported(
        self,
    ) -> None:
        handoff = self.chat_handoff.load_managed_handoff_from_environment(
            _managed_chat_avatar_environment()
        )
        args = SimpleNamespace(
            test_timeout_seconds=30,
            dry_run=True,
            _managed_chat_avatar_handoff=handoff,
        )
        device = {
            "id": "dry-run-device",
            "targetPlatform": "android-arm64",
        }
        probe_report = {
            "conversation": {
                "conversationId": "managed-conversation",
                "finalAvatarUrl": "/media/avatar/managed.png",
            }
        }
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                self.chat.shutil,
                "which",
                return_value="/usr/local/bin/patrol",
            ),
        ):
            result = self.chat.run_patrol(
                "gamma",
                "https://api.gamma.quwoquan.com:19000",
                "https://cdn.gamma.quwoquan.com:19100/media/avatar",
                args,
                device,
                probe_report,
                Path(temporary),
            )

        command = result["command"]
        define_argument = next(
            item for item in command if item.startswith("--dart-define-from-file=")
        )
        private_path = Path(define_argument.split("=", 1)[1])
        self.assertFalse(private_path.exists())
        joined = "\n".join(command)
        for secret in handoff.secret_values():
            self.assertNotIn(secret, joined)


if __name__ == "__main__":
    unittest.main()
