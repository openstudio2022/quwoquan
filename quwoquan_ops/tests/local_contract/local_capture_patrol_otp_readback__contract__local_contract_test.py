"""Lock local-capture Patrol UAT to protected OTP readback.

spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#req-002
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from quwoquan_ops.ci.provider_conformance import run_provider_patrol_uat


ROOT = Path(__file__).resolve().parents[3]
OPS_ROOT = Path(__file__).resolve().parents[2]
LOCAL_CAPTURE_UAT = (
    OPS_ROOT
    / "tests/acceptance/user_acceptance/service_ops/integration-service/ci"
    / "ext_sms_local_capture_provider_conformance.py"
)
ALIYUN_UAT = (
    OPS_ROOT
    / "tests/acceptance/user_acceptance/service_ops/integration-service/ci"
    / "ext_sms_aliyun_provider_conformance.py"
)
PATROL_RUNNER = (
    OPS_ROOT / "ci/provider_conformance/run_provider_patrol_uat.py"
)
PATROL_DART = (
    ROOT
    / "quwoquan_app/test/user_acceptance/service/user_service/account/authentication_challenge"
    / "sms_otp_provider__user_acceptance_test.dart"
)


def _literal_command(path: Path) -> tuple[str, ...]:
    module = ast.parse(path.read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "COMMAND":
                    value = ast.literal_eval(node.value)
                    return tuple(str(item) for item in value)
    raise AssertionError(f"COMMAND not found in {path}")


class LocalCapturePatrolOtpReadbackContractTest(unittest.TestCase):
    def test_local_capture_uat_uses_broker_not_argv_otp(self) -> None:
        command = _literal_command(LOCAL_CAPTURE_UAT)
        self.assertIn("--local-capture-otp-broker", command)
        self.assertIn("QWQ_PROVIDER_UAT_SMS_PHONE", command)
        self.assertNotIn("QWQ_PROVIDER_UAT_SMS_OTP", command)
        platform_index = command.index("--platform")
        self.assertEqual(command[platform_index + 1], "all")

    def test_managed_nonprod_uat_still_allows_argv_otp(self) -> None:
        command = _literal_command(ALIYUN_UAT)
        self.assertNotIn("--local-capture-otp-broker", command)
        self.assertIn("QWQ_PROVIDER_UAT_SMS_OTP", command)

    def test_patrol_runner_rejects_argv_otp_when_broker_enabled(self) -> None:
        source = PATROL_RUNNER.read_text(encoding="utf-8")
        self.assertIn("local-capture OTP UAT must not preload an OTP", source)
        self.assertIn("ProtectedOTPBroker", source)
        self.assertIn("read_latest_debug_otp", source)
        self.assertIn("materialize_local_capture_ui_acceptance_phone", source)

    def test_local_capture_phone_separates_app_input_and_provider_recipient(
        self,
    ) -> None:
        for raw in ("19912345678", "+8619912345678"):
            self.assertEqual(
                run_provider_patrol_uat._local_capture_phone_values(raw),
                ("19912345678", "+8619912345678"),
            )
        for invalid in ("", "+99912345678", "+86138123", "1991234567a"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                run_provider_patrol_uat._local_capture_phone_values(invalid)

    def test_local_capture_actor_selection_is_bounded_and_report_stable(self) -> None:
        first = Path("/tmp/qwq/provider-uat/run-a/report.json")
        second = Path("/tmp/qwq/provider-uat/run-b/report.json")

        selected = run_provider_patrol_uat._local_capture_ui_actor_index(first)
        self.assertEqual(
            selected,
            run_provider_patrol_uat._local_capture_ui_actor_index(first),
        )
        self.assertGreaterEqual(selected, 0)
        self.assertLess(selected, 128)
        self.assertGreaterEqual(
            run_provider_patrol_uat._local_capture_ui_actor_index(second),
            0,
        )

    def test_patrol_dart_forbids_argv_when_broker_is_bound(self) -> None:
        source = PATROL_DART.read_text(encoding="utf-8")
        self.assertIn(
            "local-capture OTP UAT must use protected readback, not argv OTP",
            source,
        )
        self.assertIn("QWQ_PROVIDER_UAT_OTP_BROKER_URL", source)
        self.assertIn("QWQ_PROVIDER_UAT_OTP_BROKER_CA_B64", source)
        self.assertIn("SecurityContext(withTrustedRoots: false)", source)
        self.assertIn("setTrustedCertificatesBytes", source)
        self.assertNotIn("FoundationText.loginPhoneSubmit", source)

    def test_patrol_dart_accepts_only_exact_https_loopback_broker(self) -> None:
        source = PATROL_DART.read_text(encoding="utf-8")
        for required in (
            "uri.scheme != 'https'",
            "uri?.host == '127.0.0.1'",
            "uri?.host == 'localhost'",
            "!uri.hasAuthority",
            "!uri.hasPort",
            "uri.userInfo.isNotEmpty",
            "uri.path != '/v1/otp'",
            "uri.hasQuery",
            "uri.hasFragment",
            "_validatedOtpBrokerUri(brokerUrl)",
        ):
            self.assertIn(required, source)
        self.assertNotIn("badCertificateCallback", source)
        self.assertNotIn("http://127.0.0.1", source)
        self.assertNotIn("http://localhost", source)


if __name__ == "__main__":
    unittest.main()
