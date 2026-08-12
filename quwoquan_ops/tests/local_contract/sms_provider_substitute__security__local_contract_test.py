from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from quwoquan_ops.cli.lib.local_environment_auth import (
    prepare_local_environment_auth,
)
from quwoquan_ops.cli.lib.local_sms_provider_debug import ProtectedDebugOTP


ROOT = Path(__file__).resolve().parents[3]
WORKLOAD = ROOT / "quwoquan_ops/external/sms-provider-substitute"


class SMSProviderSubstituteSecurityTest(unittest.TestCase):
    def test_in_process_otp_value_is_redacted_from_repr(self) -> None:
        value = ProtectedDebugOTP(
            request_id="request-1",
            expires_at="2026-08-02T08:05:00Z",
            code="482731",
        )
        self.assertNotIn("482731", repr(value))

    def test_prod_has_no_substitute_workload_or_binding(self) -> None:
        self.assertFalse((WORKLOAD / "environments/prod").exists())
        prod_config = (
            ROOT
            / "quwoquan_service/services/integration-service/environments/prod/config.yaml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("ext.sms.debug_protocol_substitute", prod_config)
        generated = (
            ROOT
            / "quwoquan_service/services/integration-service/generated/"
            "external_integration/external_interaction/external_provider_bindings.g.go"
        ).read_text(encoding="utf-8")
        prod_scope = generated.split('"prod": {', 1)[1]
        self.assertNotIn("ext.sms.debug_protocol_substitute", prod_scope)
        self.assertEqual(
            generated.count('AdapterID:   "ext.sms.local_capture"'),
            3,
        )
        self.assertEqual(
            generated.count('AdapterID:   "ext.sms.aliyun"'),
            1,
        )
        integration_compose = (
            ROOT
            / "quwoquan_service/services/integration-service/deploy/compose.yaml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("INTEGRATION_SMS_DEBUG_SUBSTITUTE_ENABLED", integration_compose)
        self.assertNotIn("sms-provider-substitute/ca.crt", integration_compose)

        debug_compose = (WORKLOAD / "deploy/compose.yaml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("INTEGRATION_SMS_DEBUG_SUBSTITUTE_ENABLED", debug_compose)
        self.assertNotIn("ext.sms.", debug_compose)
        self.assertNotIn("debug-sms-disabled", debug_compose)
        self.assertIn("/usr/local/bin/sms-provider-substitute", debug_compose)
        self.assertIn('"healthcheck"', debug_compose)
        self.assertNotIn("--no-check-certificate", debug_compose)
        healthcheck_source = (
            WORKLOAD
            / "cmd/sms-provider-substitute/main.go"
        ).read_text(encoding="utf-8")
        self.assertIn("https://127.0.0.1:9443/healthz", healthcheck_source)
        self.assertIn(
            "/run/secrets/sms-provider-substitute/ca.crt",
            healthcheck_source,
        )
        healthcheck_impl = (
            WORKLOAD
            / "cmd/sms-provider-substitute/healthcheck.go"
        ).read_text(encoding="utf-8")
        self.assertIn("tls.VersionTLS13", healthcheck_impl)
        self.assertNotIn("InsecureSkipVerify", healthcheck_impl)

    def test_target_credentials_are_isolated_and_capture_key_is_not_otp_key(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            alpha = prepare_local_environment_auth(
                "alpha",
                "alpha-local",
                deployment_work_root=temporary_directory,
            )
            beta = prepare_local_environment_auth(
                "beta",
                "beta-local",
                deployment_work_root=temporary_directory,
            )
        self.assertNotEqual(
            alpha.environment["SMS_SUBSTITUTE_PROVIDER_TOKEN"],
            beta.environment["SMS_SUBSTITUTE_PROVIDER_TOKEN"],
        )
        self.assertNotEqual(
            alpha.environment["SMS_SUBSTITUTE_OPERATOR_TOKEN"],
            alpha.environment["SMS_SUBSTITUTE_PROVIDER_TOKEN"],
        )
        self.assertNotEqual(
            alpha.environment["PROVIDER_SUBSTITUTE_OPERATOR_TOKEN"],
            alpha.environment["SMS_SUBSTITUTE_OPERATOR_TOKEN"],
        )
        self.assertNotEqual(
            alpha.environment["SMS_SUBSTITUTE_CAPTURE_KEY_B64"],
            alpha.environment["OTP_CODE_REF_KEYS_JSON"],
        )


if __name__ == "__main__":
    unittest.main()
