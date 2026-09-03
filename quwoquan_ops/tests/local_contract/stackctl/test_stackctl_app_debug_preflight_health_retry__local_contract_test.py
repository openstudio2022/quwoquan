"""App preflight uses a bounded endpoint health retry policy.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.cli import stackctl


class StackctlAppDebugPreflightHealthRetryContract(unittest.TestCase):
    def test_each_health_check_uses_the_bounded_retry_policy(self) -> None:
        configuration_digest = "sha256:" + "a" * 64
        provider_digest = "sha256:" + "b" * 64
        composition = {
            "runtimeCompositionDigest": provider_digest,
            "workloads": [
                {
                    "role": "provider-protocol-substitute",
                    "adapterIds": ["ext.model.local"],
                },
                {
                    "role": "sms-provider-substitute",
                    "adapterIds": ["ext.sms.local_capture"],
                    "capabilityIds": ["identity.sms.otp"],
                },
            ],
        }
        startup = {
            "status": "running",
            "environment": "alpha",
            "target": "alpha-local",
            "workload": "full",
            "configurationDigest": configuration_digest,
            "providerRuntimeDigest": provider_digest,
        }
        checked_urls: list[str] = []

        def fetch(url: str, **kwargs: object) -> tuple[bool, int, str, str]:
            checked_urls.append(url)
            if url.endswith("/auth/otp/readiness"):
                self.assertEqual(kwargs["retry_attempts"], 1)
                self.assertEqual(kwargs["retry_sleep_seconds"], 0.0)
                return (
                    True,
                    200,
                    '{"availability":"ready","retryAfterSeconds":0}',
                    "application/json",
                )
            self.assertEqual(kwargs["retry_attempts"], 3)
            self.assertEqual(kwargs["retry_sleep_seconds"], 0.5)
            if ":17330/healthz" in url:
                return (
                    True,
                    200,
                    json.dumps(
                        {
                            "status": "ready",
                            "adapterId": "ext.sms.local_capture",
                            "environment": "alpha",
                            "configurationDigest": configuration_digest,
                            "profile": "success",
                            "nonPromotable": True,
                        }
                    ),
                    "application/json",
                )
            return True, 200, '{"status":"ok"}', "application/json"

        with tempfile.TemporaryDirectory() as temporary_directory, patch.object(
            stackctl,
            "compile_provider_runtime_composition",
            return_value=composition,
        ), patch.object(
            stackctl,
            "load_test_live_startup_attempt",
            return_value=startup,
        ), patch.object(
            stackctl,
            "verify_certificate",
            return_value={"profile": "local-managed", "status": "ready"},
        ), patch.object(
            stackctl,
            "fetch_url",
            side_effect=fetch,
        ), patch.object(
            stackctl,
            "_execute_otp_login_journey",
            return_value={"status": "passed"},
        ), patch.object(
            stackctl,
            "load_test_live_content_binding",
            return_value=None,
        ):
            result = stackctl.command_app_debug_preflight(
                argparse.Namespace(
                    target="alpha-local",
                    runtime_mode="test_live",
                    report_dir=str(Path(temporary_directory) / "report"),
                )
            )

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["status"], "warning")
        self.assertTrue(any(":17210/healthz" in url for url in checked_urls))
        self.assertTrue(
            any(url.endswith("/auth/otp/readiness") for url in checked_urls)
        )


if __name__ == "__main__":
    unittest.main()
