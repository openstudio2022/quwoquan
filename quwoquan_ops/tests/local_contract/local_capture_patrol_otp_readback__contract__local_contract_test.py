"""Lock local-capture Patrol UAT to protected OTP readback.

spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#req-002
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


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
    / "quwoquan_app/test/user_acceptance/patrol/user"
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

    def test_managed_nonprod_uat_still_allows_argv_otp(self) -> None:
        command = _literal_command(ALIYUN_UAT)
        self.assertNotIn("--local-capture-otp-broker", command)
        self.assertIn("QWQ_PROVIDER_UAT_SMS_OTP", command)

    def test_patrol_runner_rejects_argv_otp_when_broker_enabled(self) -> None:
        source = PATROL_RUNNER.read_text(encoding="utf-8")
        self.assertIn("local-capture OTP UAT must not preload an OTP", source)
        self.assertIn("ProtectedOTPBroker", source)
        self.assertIn("read_latest_debug_otp", source)

    def test_patrol_dart_forbids_argv_when_broker_is_bound(self) -> None:
        source = PATROL_DART.read_text(encoding="utf-8")
        self.assertIn(
            "local-capture OTP UAT must use protected readback, not argv OTP",
            source,
        )
        self.assertIn("QWQ_PROVIDER_UAT_OTP_BROKER_URL", source)


if __name__ == "__main__":
    unittest.main()
