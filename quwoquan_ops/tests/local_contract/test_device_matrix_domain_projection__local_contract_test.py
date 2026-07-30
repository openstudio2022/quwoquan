from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]


def _load_module(name: str, relative_path: str) -> ModuleType:
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        self.assertIn("--skip-beta-services", command)

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


if __name__ == "__main__":
    unittest.main()
