# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-002

import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[3]
TOOLS_DIR = APP_DIR / "scripts/tools/device"
sys.path.insert(0, str(TOOLS_DIR))

from inspect_ios_native_startup import (
    public_web_identity,
    verify_web_cta_with_xcuitest,
)


class IosNativeStartupInspectorContractTest(unittest.TestCase):
    def test_public_web_identity_binds_exact_trusted_https_url(self) -> None:
        url = "https://alpha.quwoquan.com:17000"
        identity = public_web_identity({"publicWebURL": url})
        self.assertEqual(identity["publicWebURL"], url)
        self.assertEqual(
            identity["publicWebURLDigest"],
            "sha256:" + hashlib.sha256(url.encode("utf-8")).hexdigest(),
        )

        for invalid in (
            "",
            "http://alpha.quwoquan.com:17000",
            "https://user@alpha.quwoquan.com:17000",
            "https://alpha.quwoquan.com:17000/#fragment",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "trusted HTTPS"):
                    public_web_identity({"publicWebURL": invalid})

    def test_xcuitest_proves_click_safari_exact_url_and_same_process(self) -> None:
        digest = f"sha256:{'a' * 64}"
        xcode_output = """
QWQNativeStartupUITest recovery_web_cta_safari_foreground
QWQNativeStartupUITest recovery_web_cta_returned_app_foreground
** TEST SUCCEEDED **
"""
        app_log = f"""
QWQStartup ios_native_recovery_external_open_requested urlDigest={digest} processId=41
QWQStartup ios_native_recovery_external_open_completed urlDigest={digest} opened=true
QWQStartup ios_native_recovery_external_returned processId=41
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch.dict(
                os.environ,
                {
                    "QWQ_APP_RUNTIME_ENV": "stale",
                    "QWQ_LAUNCH_TARGET": "stale-local",
                },
            ), patch(
                "inspect_ios_native_startup.subprocess.run",
                return_value=subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout=xcode_output,
                    stderr="",
                ),
            ) as xcode, patch(
                "inspect_ios_native_startup.run",
                return_value=subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout=app_log,
                    stderr="",
                ),
            ):
                result = verify_web_cta_with_xcuitest(
                    simulator_udid="SIMULATOR-UDID",
                    environment="alpha",
                    expected_url_digest=digest,
                    output_dir=output_dir,
                )

        self.assertTrue(result["xcodeTestPassed"])
        self.assertTrue(result["trustedExactPublicWebURLRequested"])
        self.assertTrue(result["safariForegroundObserved"])
        self.assertTrue(result["trustedExactPublicWebURLOpened"])
        self.assertTrue(result["sameAppProcessAfterReturn"])
        command = xcode.call_args.args[0]
        self.assertIn(
            "-only-testing:RunnerUITests/"
            "QWQNativeStartupRecoveryWebUITests/"
            "testRecoveryWebCTAOpensSafariAndReturnsToSameProcess",
            command,
        )
        environment = xcode.call_args.kwargs["env"]
        self.assertEqual(environment["QWQ_ENVIRONMENT"], "alpha")
        self.assertNotIn("QWQ_APP_RUNTIME_ENV", environment)
        self.assertNotIn("QWQ_LAUNCH_TARGET", environment)

    def test_xcuitest_rejects_a_different_opened_url_digest(self) -> None:
        expected = f"sha256:{'a' * 64}"
        observed = f"sha256:{'b' * 64}"
        xcode_output = """
QWQNativeStartupUITest recovery_web_cta_safari_foreground
QWQNativeStartupUITest recovery_web_cta_returned_app_foreground
"""
        app_log = f"""
QWQStartup ios_native_recovery_external_open_requested urlDigest={observed} processId=41
QWQStartup ios_native_recovery_external_open_completed urlDigest={observed} opened=true
QWQStartup ios_native_recovery_external_returned processId=41
"""
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "inspect_ios_native_startup.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0, stdout=xcode_output, stderr=""
            ),
        ), patch(
            "inspect_ios_native_startup.run",
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0, stdout=app_log, stderr=""
            ),
        ):
            result = verify_web_cta_with_xcuitest(
                simulator_udid="SIMULATOR-UDID",
                environment="gamma",
                expected_url_digest=expected,
                output_dir=Path(temp_dir),
            )

        self.assertFalse(result["trustedExactPublicWebURLRequested"])
        self.assertFalse(result["trustedExactPublicWebURLOpened"])


if __name__ == "__main__":
    unittest.main()
