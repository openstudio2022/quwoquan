"""Native-entry and source contracts for external production AUT evidence."""

from __future__ import annotations

import hashlib
import json
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.smoke.environment_patrol_smoke import (
    external_aut_driver as external_driver_module,
)
from quwoquan_ops.cli.smoke.environment_patrol_smoke import external_aut_entry
from quwoquan_ops.cli.smoke.environment_patrol_smoke.artifact_binding import (
    build_tested_app_artifact_binding,
)
from quwoquan_ops.cli.smoke.environment_patrol_smoke.external_aut_driver import (
    EXTERNAL_AUT_HOMEPAGE_SCHEMA,
    EXTERNAL_AUT_MARKER,
    HOME_SURFACE_ACCESSIBILITY_IDENTIFIER,
    PATROL_ANDROID_DRIVER_APPLICATION_ID,
    PATROL_ANDROID_HOST_APPLICATION_ID,
    PATROL_IOS_HOST_APPLICATION_ID,
    PATROL_IOS_XCTEST_BUNDLE_ID,
    PATROL_IOS_XCTRUNNER_BUNDLE_ID,
)

PRODUCTION_ANDROID_ID = "com.quwoquan.alpha"
PRODUCTION_IOS_ID = "com.quwoquan.beta"


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


def _canonical_binding(platform: str = "android") -> dict[str, object]:
    ios = platform == "ios"
    return {
        "environment": "beta" if ios else "alpha",
        "target": "beta-local" if ios else "alpha-local",
        "platform": platform,
        "deviceId": "ios-simulator-1" if ios else "emulator-5556",
        "applicationId": PRODUCTION_IOS_ID if ios else PRODUCTION_ANDROID_ID,
        "artifactDigest": _digest("a"),
        "candidateDigest": _digest("b"),
        "launchAttemptId": "canonical-launch-attempt-1",
        "canonicalProcessId": 4312,
        "runtimeConfigTrustEnvelopeDigest": _digest("c"),
    }


def _document_digest(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _native_driver_binding(platform: str = "android") -> dict[str, object]:
    ios = platform == "ios"
    device_id = "ios-simulator-1" if ios else "emulator-5556"
    if ios:
        evidence: dict[str, object] = {
            "xctestrunPath": "/tmp/Runner_iphonesimulator.xctestrun",
            "xctestrunDigest": _digest("4"),
            "testBundlePath": "/tmp/RunnerUITests-Runner.app/PlugIns/RunnerUITests.xctest",
            "testBundleDigest": _digest("5"),
            "testHostPath": "/tmp/RunnerUITests-Runner.app",
            "testHostDigest": _digest("6"),
            "testHostBundleIdentifier": PATROL_IOS_XCTRUNNER_BUNDLE_ID,
            "testBundleIdentifier": PATROL_IOS_XCTEST_BUNDLE_ID,
        }
        artifact_digest = _digest("6")
        driver_id = PATROL_IOS_XCTRUNNER_BUNDLE_ID
        host_id = PATROL_IOS_HOST_APPLICATION_ID
        artifact_kind = "ios_xctrunner_test_bundle_tree"
    else:
        raw = build_tested_app_artifact_binding(
            platform="android",
            device_id=device_id,
            command_application_id=PATROL_ANDROID_DRIVER_APPLICATION_ID,
            build_application_id=PATROL_ANDROID_DRIVER_APPLICATION_ID,
            build_artifact_path=(
                "build/app/outputs/apk/androidTest/debug/"
                "app-debug-androidTest.apk"
            ),
            build_artifact_digest=_digest("6"),
            installed_application_id=PATROL_ANDROID_DRIVER_APPLICATION_ID,
            installed_artifact_digest=_digest("6"),
            installed_readback_method="adb_pm_path_pull_base_apk",
            installed_locator_digest=_digest("7"),
            host_source={
                "root": "quwoquan_app/test_host/patrol",
                "rootIdentityDigest": _digest("8"),
                "sourceDigest": _digest("9"),
                "sourceFileCount": 3,
            },
        )
        evidence = {"testedDriverArtifactBinding": raw}
        artifact_digest = _digest("6")
        driver_id = PATROL_ANDROID_DRIVER_APPLICATION_ID
        host_id = PATROL_ANDROID_HOST_APPLICATION_ID
        artifact_kind = "android_test_apk_installed_readback"
    return {
        "schema": "environment-page-smoke.external-aut-native-driver-artifact.v1",
        "status": "passed",
        "provenance": "external_aut_native_driver_artifact_readback",
        "platform": platform,
        "deviceId": device_id,
        "driverApplicationId": driver_id,
        "testHostApplicationId": host_id,
        "artifactKind": artifact_kind,
        "artifactDigest": artifact_digest,
        "evidenceDigest": _document_digest(evidence),
        "evidence": evidence,
    }


def _evidence(platform: str = "android") -> dict[str, object]:
    ios = platform == "ios"
    return {
        "schema": EXTERNAL_AUT_HOMEPAGE_SCHEMA,
        "platform": platform,
        "driverApplicationId": (
            "com.quwoquan.testhost.patrol.RunnerUITests.xctrunner"
            if ios
            else "com.quwoquan.testhost.patrol.test"
        ),
        "testHostApplicationId": "com.quwoquan.testhost.patrol",
        "productionApplicationId": (
            PRODUCTION_IOS_ID if ios else PRODUCTION_ANDROID_ID
        ),
        "processIdBefore": 4312,
        "processIdAfter": 4312,
        "stateBefore": "running_background" if ios else "running_foreground",
        "stateAfter": "running_foreground",
        "activationMode": (
            "activate_existing_process"
            if ios
            else "observe_existing_foreground_process"
        ),
        "launchPerformed": False,
        "homepageAccessibilityIdentifier": HOME_SURFACE_ACCESSIBILITY_IDENTIFIER,
        "homepageVisible": True,
        "homepageFrameIntersectsVisibleWindow": True,
    }



class EnvironmentPatrolExternalAutEntryTest(unittest.TestCase):
    def test_canonical_entry_executes_named_android_external_aut_journey(self) -> None:
        binding = _canonical_binding()
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory)
            observed_command: list[str] = []

            def fake_run_command(command, *, cwd, timeout_seconds, log_path):
                del cwd, timeout_seconds
                observed_command.extend(command)
                payload = json.dumps(
                    _evidence(), separators=(",", ":"), sort_keys=True
                )
                log_path.write_text(
                    EXTERNAL_AUT_MARKER + payload + "\n", encoding="utf-8"
                )
                return {
                    "exitCode": 0,
                    "command": list(command),
                    "outputSummary": "passed",
                }

            with (
                patch.object(
                    external_aut_entry,
                    "resolve_android_debug_bridge",
                    return_value="/sdk/platform-tools/adb",
                ),
                patch.object(
                    external_aut_entry,
                    "run_command",
                    side_effect=fake_run_command,
                ),
                patch.object(
                    external_aut_entry,
                    "capture_device_screenshot",
                    return_value={"status": "captured", "path": "home.png"},
                ),
                patch.object(
                    external_driver_module,
                    "collect_android_external_aut_driver_artifact_binding",
                    return_value=_native_driver_binding(),
                ),
            ):
                journey, driver, screenshot = (
                    external_aut_entry.run_external_production_aut_homepage(
                        args=SimpleNamespace(
                            env_name="alpha-local",
                            target="test/home_page_content_patrol_test.dart",
                            timeout_seconds=30,
                        ),
                        device={
                            "id": "emulator-5556",
                            "targetPlatform": "android-arm64",
                        },
                        run_dir=run_dir,
                        patrol_output="",
                        canonical_binding=binding,
                        runtime_env="alpha",
                        command_env={},
                    )
                )

        self.assertEqual(journey["status"], "passed")
        self.assertEqual(journey["journeyId"], "production-startup-homepage")
        self.assertEqual(driver["exitCode"], 0)
        self.assertEqual(screenshot["status"], "captured")
        self.assertEqual(
            observed_command[-1],
            (
                "com.quwoquan.testhost.patrol.test/"
                "pl.leancode.patrol.PatrolJUnitRunner"
            ),
        )

    def test_canonical_entry_executes_named_ios_external_aut_journey(self) -> None:
        binding = _canonical_binding("ios")
        with tempfile.TemporaryDirectory() as temporary_directory:
            patrol_host = Path(temporary_directory) / "patrol"
            products = patrol_host / "build/ios_integ/Build/Products"
            products.mkdir(parents=True)
            xctrunner = (
                products
                / "debug-iphonesimulator/RunnerUITests-Runner.app"
            )
            xctest = xctrunner / "PlugIns/RunnerUITests.xctest"
            xctest.mkdir(parents=True)
            (xctrunner / "Info.plist").write_bytes(
                plistlib.dumps(
                    {"CFBundleIdentifier": PATROL_IOS_XCTRUNNER_BUNDLE_ID}
                )
            )
            (xctrunner / "RunnerUITests").write_bytes(b"xctrunner")
            (xctest / "Info.plist").write_bytes(
                plistlib.dumps(
                    {"CFBundleIdentifier": PATROL_IOS_XCTEST_BUNDLE_ID}
                )
            )
            (xctest / "RunnerUITests").write_bytes(b"xctest")
            source = products / "Runner_iphonesimulator.xctestrun"
            source.write_bytes(
                plistlib.dumps(
                    {
                        "RunnerUITests": {
                            "TestHostBundleIdentifier": (
                                PATROL_IOS_XCTRUNNER_BUNDLE_ID
                            ),
                            "TestHostPath": (
                                "__TESTROOT__/debug-iphonesimulator/"
                                "RunnerUITests-Runner.app"
                            ),
                            "TestBundlePath": (
                                "__TESTHOST__/PlugIns/RunnerUITests.xctest"
                            ),
                            "EnvironmentVariables": {},
                        }
                    }
                )
            )
            run_dir = Path(temporary_directory) / "evidence"
            run_dir.mkdir()
            observed_xctestrun: Path | None = None

            def fake_run_command(command, *, cwd, timeout_seconds, log_path):
                nonlocal observed_xctestrun
                del timeout_seconds
                self.assertEqual(cwd, patrol_host)
                observed_xctestrun = Path(command[command.index("-xctestrun") + 1])
                self.assertTrue(observed_xctestrun.is_file())
                payload = json.dumps(
                    _evidence("ios"), separators=(",", ":"), sort_keys=True
                )
                log_path.write_text(
                    "XCTest " + EXTERNAL_AUT_MARKER + payload + "\n",
                    encoding="utf-8",
                )
                return {
                    "exitCode": 0,
                    "command": list(command),
                    "outputSummary": "passed",
                }

            with (
                patch.object(external_aut_entry, "PATROL_HOST_DIR", patrol_host),
                patch.object(
                    external_aut_entry,
                    "run_command",
                    side_effect=fake_run_command,
                ),
                patch.object(
                    external_aut_entry,
                    "capture_device_screenshot",
                    return_value={"status": "captured", "path": "home.png"},
                ),
            ):
                journey, driver, screenshot = (
                    external_aut_entry.run_external_production_aut_homepage(
                        args=SimpleNamespace(
                            env_name="beta-local",
                            target="test/home_page_content_patrol_test.dart",
                            timeout_seconds=30,
                        ),
                        device={
                            "id": "ios-simulator-1",
                            "targetPlatform": "ios",
                        },
                        run_dir=run_dir,
                        patrol_output=(
                            str(source.relative_to(patrol_host))
                            + " (xctestrun file)"
                        ),
                        canonical_binding=binding,
                        runtime_env="beta",
                        command_env={},
                    )
                )

            self.assertIsNotNone(observed_xctestrun)
            assert observed_xctestrun is not None
            self.assertFalse(observed_xctestrun.exists())

        self.assertEqual(journey["status"], "passed")
        self.assertEqual(driver["xctestrun"]["status"], "materialized")
        self.assertEqual(screenshot["status"], "captured")

    def test_native_sources_share_product_semantics_and_preserve_process(self) -> None:
        dart_source = (
            ROOT
            / "quwoquan_app/lib/design_system/semantics/navigation_semantic_constants.dart"
        ).read_text(encoding="utf-8")
        android_source = (
            ROOT
            / "quwoquan_app/test_host/patrol/android/app/src/androidTest/java/"
            "com/quwoquan/testhost/patrol/ProductionHomepageExternalAutTest.java"
        ).read_text(encoding="utf-8")
        ios_source = (
            ROOT
            / "quwoquan_app/test_host/patrol/ios/RunnerUITests/RunnerUITests.m"
        ).read_text(encoding="utf-8")
        ios_homepage_class = ios_source.split(
            "@implementation QWQProductionHomepageExternalAUTTests", maxsplit=1
        )[1].split("@end", maxsplit=1)[0]

        for source in (dart_source, android_source, ios_source):
            self.assertIn(HOME_SURFACE_ACCESSIBILITY_IDENTIFIER, source)
        self.assertIn("QWQHomeSurfaceIdentifier", ios_homepage_class)
        for forbidden in (
            "getLaunchIntentForPackage",
            "startActivity(",
            'executeShellCommand("am start',
            'executeShellCommand("am force-stop',
            'executeShellCommand("monkey',
        ):
            self.assertNotIn(forbidden, android_source)
        self.assertIn("isVisibleToUser()", android_source)
        self.assertIn("getRootInActiveWindow()", android_source)
        self.assertIn("Instrumentation.REPORT_KEY_STREAMRESULT", android_source)
        self.assertNotIn("System.out.println(marker)", android_source)
        self.assertIn("pidBefore", android_source)
        self.assertIn("pidAfter", android_source)
        self.assertIn("[app activate]", ios_homepage_class)
        self.assertNotIn("[app launch]", ios_homepage_class)
        self.assertNotIn("[app terminate]", ios_homepage_class)
        self.assertIn("CGRectIntersection", ios_homepage_class)
        self.assertIn("app.windows.firstMatch", ios_homepage_class)
        self.assertIn("XCUIApplicationStateRunningForeground", ios_homepage_class)



if __name__ == "__main__":
    unittest.main()
