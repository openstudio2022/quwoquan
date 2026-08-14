# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-004
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
#
# 由 1000 行硬顶从 startup_probe_parser__local_contract_test.py 拆出：
# 本文件承接 launcher handoff 与 TTID 门场景组（effective launch manifest
# digest、flutter run defines/transport receipts 校验、TTID ratchet 结构模式
# 与自比较阻断、commercial UAT 真机 20 次门）；测试逐字搬移。

import sys
import unittest
from pathlib import Path
from unittest import mock


APP_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR / "scripts/device"))
sys.path.insert(0, str(APP_DIR / "scripts/runtime/platform"))
sys.path.insert(0, str(APP_DIR / "test/support/runtime/launcher"))

from build_launcher_handoff import (
    dart_defines_digest,
    effective_launch_manifest_digest,
)
from launcher_package_fixture import fixture_runtime_config_digest
from verify_flutter_run_defines import validate_flutter_run_defines
from verify_startup_ttid_baseline import main as verify_startup_ttid_main
from verify_startup_ttid_baseline import validate_commercial_uat


class StartupProbeParserContractTest(unittest.TestCase):
    def test_effective_launch_manifest_digest_is_order_independent(self) -> None:
        left = {"schema": "app-effective-launch-manifest", "target": "prod-hosted"}
        right = {"target": "prod-hosted", "schema": "app-effective-launch-manifest"}
        self.assertEqual(
            effective_launch_manifest_digest(left),
            effective_launch_manifest_digest(right),
        )

    def test_launcher_handoff_validates_target_runner_and_digests(self) -> None:
        defines = {
            "APP_RUNTIME_ENV": "prod",
            "CLOUD_GATEWAY_BASE_URL": "https://api.quwoquan.com",
            "APP_LEGAL_BASE_URL": "https://quwoquan.com/legal",
            "PUBLIC_WEB_BASE_URL": "https://quwoquan.com",
            "MEDIA_AVATAR_CDN_BASE_URL": "https://cdn.quwoquan.com",
            "MEDIA_IMAGE_CDN_BASE_URL": "https://cdn.quwoquan.com",
            "MEDIA_VIDEO_CDN_BASE_URL": "https://cdn.quwoquan.com",
            "MEDIA_UPLOAD_BASE_URL": "https://upload.quwoquan.com",
            "RTC_MEDIA_CONNECTION_URL": "wss://rtc.quwoquan.com",
        }
        self.assertEqual(
            validate_flutter_run_defines(
                defines,
                expected_env="prod",
                target="prod-sim",
                entrypoint="lib/main_prod.dart",
                defines_digest=dart_defines_digest(defines),
                runtime_config_digest=fixture_runtime_config_digest(
                    "prod",
                    "prod-sim",
                ),
            ),
            [],
        )
        self.assertIn(
            "target alpha-local requires APP_RUNTIME_ENV=alpha",
            validate_flutter_run_defines(defines, target="alpha-local"),
        )
        alpha_defines = {**defines, "APP_RUNTIME_ENV": "alpha"}
        self.assertEqual(
            validate_flutter_run_defines(
                alpha_defines,
                expected_env="alpha",
                target="alpha-local",
                entrypoint="lib/main_prod.dart",
                defines_digest=dart_defines_digest(alpha_defines),
                runtime_config_digest=fixture_runtime_config_digest(
                    "alpha",
                    "alpha-local",
                ),
            ),
            [],
        )

    def test_launcher_handoff_validates_local_transport_receipts(self) -> None:
        defines = {
            "APP_RUNTIME_ENV": "beta",
            "CLOUD_GATEWAY_BASE_URL": "https://api.example.test",
            "APP_LEGAL_BASE_URL": "https://legal.example.test",
            "PUBLIC_WEB_BASE_URL": "https://web.example.test",
            "MEDIA_AVATAR_CDN_BASE_URL": "https://cdn.example.test",
            "MEDIA_IMAGE_CDN_BASE_URL": "https://cdn.example.test",
            "MEDIA_VIDEO_CDN_BASE_URL": "https://cdn.example.test",
            "MEDIA_UPLOAD_BASE_URL": "https://upload.example.test",
            "RTC_MEDIA_CONNECTION_URL": "wss://rtc.example.test",
        }
        digest = "sha256:" + "a" * 64
        self.assertEqual(
            validate_flutter_run_defines(
                defines,
                expected_env="beta",
                target="beta-local",
                entrypoint="lib/main_prod.dart",
                transport_required=True,
                reverse_expected_ports="7443,7444",
                reverse_actual_ports="7444,7443",
                reverse_receipt_digest=digest,
                consumer_lease_id=digest,
            ),
            [],
        )
        self.assertIn(
            "Android reverse expected/actual ports do not match",
            validate_flutter_run_defines(
                defines,
                target="beta-local",
                entrypoint="lib/main_prod.dart",
                transport_required=True,
                reverse_expected_ports="7443",
                reverse_actual_ports="7444",
                reverse_receipt_digest=digest,
                consumer_lease_id=digest,
            ),
        )

    def test_ttid_ratchet_default_mode_is_structural_and_self_compare_is_blocked(
        self,
    ) -> None:
        ratchet = APP_DIR.parent / "quwoquan_ops/policies/gates/startup_ttid_ratchet_baseline.json"
        with mock.patch.object(sys, "argv", ["verify_startup_ttid_baseline.py"]):
            self.assertEqual(verify_startup_ttid_main(), 0)
        with mock.patch.object(
            sys,
            "argv",
            [
                "verify_startup_ttid_baseline.py",
                "--baseline",
                str(ratchet),
                "--ratchet",
                str(ratchet),
            ],
        ):
            self.assertEqual(verify_startup_ttid_main(), 1)

    def test_commercial_gate_rejects_simulator_or_fewer_than_twenty_runs(self) -> None:
        sample = {
            "welcomeExitMs": 2800,
            "exitReason": "ready_primary",
        }
        baseline = {
            "deviceKind": "true_device",
            "samples": [dict(sample) for _ in range(20)],
            "p95": {"firstVisibleMs": 900, "shellFirstPaintMs": 2600},
        }
        self.assertEqual(validate_commercial_uat(baseline), [])

        baseline["samples"] = baseline["samples"][:19]
        self.assertIn("at least 20 samples", validate_commercial_uat(baseline)[0])
        baseline["samples"] = [dict(sample) for _ in range(20)]
        baseline["deviceKind"] = "simulator"
        self.assertTrue(
            any("true_device" in error for error in validate_commercial_uat(baseline))
        )


if __name__ == "__main__":
    unittest.main()
