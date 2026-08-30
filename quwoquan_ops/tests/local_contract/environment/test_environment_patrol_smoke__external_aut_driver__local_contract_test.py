"""Contracts for production external-AUT homepage evidence.

spec_ref: specs/feature-tree/spec.md#uat-001
spec_ref: specs/feature-tree/spec.md#uat-009
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.commands.app_preflight_uat_binding import (
    _app_content_page_artifact_binding,
)
from quwoquan_ops.cli.commands.app_preflight_uat_process import (
    observe_canonical_app_process_id,
)
from quwoquan_ops.cli.smoke.environment_patrol_smoke.artifact_binding import (
    TESTED_APP_ARTIFACT_BINDING_SET_SCHEMA,
    build_tested_app_artifact_binding,
)
from quwoquan_ops.cli.smoke.environment_patrol_smoke.artifact_binding import (
    tested_app_artifact_comparison as _tested_app_artifact_comparison,
)
from quwoquan_ops.cli.smoke.environment_patrol_smoke.external_aut_driver import (
    APP_PAGE_ARTIFACT_BINDING_BLOCKER,
    EXTERNAL_AUT_HOMEPAGE_SCHEMA,
    EXTERNAL_AUT_JOURNEY_SET_SCHEMA,
    EXTERNAL_AUT_MARKER,
    HOME_SURFACE_ACCESSIBILITY_IDENTIFIER,
    PATROL_ANDROID_DRIVER_APPLICATION_ID,
    PATROL_ANDROID_HOST_APPLICATION_ID,
    PATROL_IOS_HOST_APPLICATION_ID,
    PATROL_IOS_XCTEST_BUNDLE_ID,
    PATROL_IOS_XCTRUNNER_BUNDLE_ID,
    ExternalAutDriverEvidenceError,
    android_external_aut_instrumentation_command,
    attach_external_aut_journey,
    build_external_aut_homepage_journey,
    build_ios_external_aut_driver_artifact_binding,
    collect_android_external_aut_driver_artifact_binding,
    collect_external_aut_homepage_evidence,
    decode_external_aut_canonical_binding,
    encode_external_aut_canonical_binding,
    external_aut_native_test_inputs,
    ios_external_aut_xcodebuild_command,
    materialize_ios_external_aut_xctestrun,
    new_external_aut_journey_set,
    parse_external_aut_homepage_evidence,
    resolve_ios_external_aut_xctestrun,
    settle_external_aut_journey_report,
    validate_external_aut_driver_artifact_binding,
    validate_external_aut_homepage_evidence,
    validate_external_aut_homepage_journey,
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


def _test_host_binding_set(platform: str = "android") -> dict[str, object]:
    ios = platform == "ios"
    binding = build_tested_app_artifact_binding(
        platform=platform,
        device_id="ios-simulator-1" if ios else "emulator-5556",
        command_application_id="com.quwoquan.testhost.patrol",
        build_application_id="com.quwoquan.testhost.patrol",
        build_artifact_path=(
            "build/ios_integ/Runner.app" if ios else "build/app-debug.apk"
        ),
        build_artifact_digest=_digest("f"),
        installed_application_id="com.quwoquan.testhost.patrol",
        installed_artifact_digest=_digest("f"),
        installed_readback_method="simctl-app-container" if ios else "adb-pull",
        installed_locator_digest=_digest("1"),
        host_source={
            "root": "quwoquan_app/test_host/patrol",
            "rootIdentityDigest": _digest("2"),
            "sourceDigest": _digest("3"),
            "sourceFileCount": 1,
        },
    )
    return {
        "schema": TESTED_APP_ARTIFACT_BINDING_SET_SCHEMA,
        "status": "passed",
        "provenance": "test_host_patrol",
        "bindings": [binding],
        "comparisonProjections": [_tested_app_artifact_comparison(binding)],
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


class EnvironmentPatrolExternalAutDriverTest(unittest.TestCase):
    def test_android_and_ios_accept_exact_identity_pid_and_home_assertion(self) -> None:
        for platform, application_id in (
            ("android", PRODUCTION_ANDROID_ID),
            ("ios", PRODUCTION_IOS_ID),
        ):
            with self.subTest(platform=platform):
                validated = validate_external_aut_homepage_evidence(
                    _evidence(platform),
                    platform=platform,
                    production_application_id=application_id,
                )

                self.assertEqual(
                    validated["provenance"],
                    "external_production_aut_native_accessibility",
                )
                self.assertRegex(
                    str(validated["evidenceDigest"]), r"^sha256:[0-9a-f]{64}$"
                )

    def test_native_inputs_do_not_relabel_the_patrol_host(self) -> None:
        android = external_aut_native_test_inputs(
            platform="android", production_application_id=PRODUCTION_ANDROID_ID
        )
        ios = external_aut_native_test_inputs(
            platform="ios", production_application_id=PRODUCTION_IOS_ID
        )

        self.assertEqual(
            android["instrumentationArguments"],
            {
                "qwqTargetPackage": PRODUCTION_ANDROID_ID,
                "qwqExpectedPackage": PRODUCTION_ANDROID_ID,
            },
        )
        self.assertNotIn("packageName", android)
        self.assertNotIn("bundleId", ios)
        self.assertEqual(
            ios["testEnvironment"],
            {
                "QWQ_IOS_TARGET_BUNDLE_ID": PRODUCTION_IOS_ID,
                "QWQ_IOS_EXPECTED_BUNDLE_ID": PRODUCTION_IOS_ID,
            },
        )

    def test_native_commands_target_only_the_independent_driver(self) -> None:
        android = android_external_aut_instrumentation_command(
            adb="/sdk/platform-tools/adb",
            device_id="emulator-5556",
            production_application_id=PRODUCTION_ANDROID_ID,
        )
        self.assertEqual(
            android[-1],
            (
                "com.quwoquan.testhost.patrol.test/"
                "pl.leancode.patrol.PatrolJUnitRunner"
            ),
        )
        self.assertEqual(android.count(PRODUCTION_ANDROID_ID), 2)
        self.assertNotIn("--package-name", android)
        self.assertNotIn("--bundle-id", android)
        self.assertNotIn("force-stop", android)

        with tempfile.TemporaryDirectory() as temporary_directory:
            xctestrun = Path(temporary_directory) / "driver.xctestrun"
            xctestrun.write_bytes(b"driver")
            ios = ios_external_aut_xcodebuild_command(
                xctestrun=xctestrun,
                device_id="ios-simulator-1",
            )
        self.assertIn("test-without-building", ios)
        self.assertIn("QWQProductionHomepageExternalAUTTests", " ".join(ios))
        self.assertNotIn("--bundle-id", ios)
        self.assertNotIn("launch", ios)

    def test_canonical_pid_observer_is_read_only_and_rejects_ambiguity(self) -> None:
        observed: list[list[str]] = []

        def android_runner(command, **_kwargs):
            observed.append(list(command))
            return subprocess.CompletedProcess(command, 0, "4312\n", "")

        android_pid = observe_canonical_app_process_id(
            platform="android",
            device_id="emulator-5556",
            application_id=PRODUCTION_ANDROID_ID,
            runner=android_runner,
            adb_resolver=lambda: "/sdk/platform-tools/adb",
        )
        self.assertEqual(android_pid, 4312)
        self.assertEqual(observed[0][-2:], ["pidof", PRODUCTION_ANDROID_ID])
        self.assertFalse(
            any(
                token in {"start", "launch", "force-stop", "monkey"}
                for token in observed[0]
            )
        )

        def ambiguous_runner(command, **_kwargs):
            return subprocess.CompletedProcess(command, 0, "4312 4313\n", "")

        with self.assertRaisesRegex(ValueError, "one canonical process"):
            observe_canonical_app_process_id(
                platform="android",
                device_id="emulator-5556",
                application_id=PRODUCTION_ANDROID_ID,
                runner=ambiguous_runner,
                adb_resolver=lambda: "/sdk/platform-tools/adb",
            )

        def ios_runner(command, **_kwargs):
            observed.append(list(command))
            return subprocess.CompletedProcess(
                command,
                0,
                (
                    "  4312      -  UIKitApplication:"
                    + PRODUCTION_IOS_ID
                    + "[cafe][rb-legacy]\n"
                ),
                "",
            )

        ios_pid = observe_canonical_app_process_id(
            platform="ios-simulator",
            device_id="ios-simulator-1",
            application_id=PRODUCTION_IOS_ID,
            runner=ios_runner,
        )
        self.assertEqual(ios_pid, 4312)
        self.assertEqual(observed[-1][1:4], ["simctl", "spawn", "ios-simulator-1"])
        self.assertIn("print", observed[-1])
        self.assertNotIn("launch", observed[-1])

    def test_ios_physical_pid_observer_uses_devicectl_not_simctl(self) -> None:
        observed: list[list[str]] = []

        def runner(command, **_kwargs):
            observed.append(list(command))
            output_path = Path(command[command.index("--json-output") + 1])
            if "apps" in command:
                payload = {
                    "result": {
                        "apps": [
                            {
                                "bundleIdentifier": PRODUCTION_IOS_ID,
                                "url": "/private/var/containers/Bundle/Application/A/Runner.app",
                            }
                        ]
                    }
                }
            else:
                payload = {
                    "result": {
                        "runningProcesses": [
                            {
                                "processIdentifier": 4312,
                                "executable": (
                                    "/private/var/containers/Bundle/Application/A/"
                                    "Runner.app/Runner"
                                ),
                            }
                        ]
                    }
                }
            output_path.write_text(json.dumps(payload), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as temporary_directory, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": temporary_directory},
            clear=False,
        ), patch(
            "quwoquan_ops.cli.commands.app_preflight_uat_process.shutil.which",
            return_value="/usr/bin/xcrun",
        ):
            process_id = observe_canonical_app_process_id(
                platform="ios-physical",
                device_id="physical-ios-udid",
                application_id=PRODUCTION_IOS_ID,
                runner=runner,
            )

        self.assertEqual(process_id, 4312)
        self.assertEqual(len(observed), 2)
        self.assertTrue(all(command[1:3] == ["devicectl", "device"] for command in observed))
        self.assertFalse(any("simctl" in command for command in observed))
        self.assertFalse(any("launch" in command for command in observed))

    def test_canonical_binding_handoff_rejects_noncanonical_bytes(self) -> None:
        binding = _canonical_binding()
        encoded = encode_external_aut_canonical_binding(binding)

        self.assertEqual(decode_external_aut_canonical_binding(encoded), binding)

        noncanonical = base64.b64encode(
            json.dumps(binding, indent=2).encode("utf-8")
        ).decode("ascii")
        with self.assertRaisesRegex(
            ExternalAutDriverEvidenceError, "JSON bytes are not canonical"
        ):
            decode_external_aut_canonical_binding(noncanonical)

    def test_ios_xctestrun_injects_identity_only_into_the_driver_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            patrol_host = Path(temporary_directory)
            products = patrol_host / "build/ios_integ/Build/Products"
            products.mkdir(parents=True)
            source = products / "Runner_iphonesimulator.xctestrun"
            source_payload = {
                "RunnerUITests": {
                    "TestHostBundleIdentifier": PATROL_IOS_XCTRUNNER_BUNDLE_ID,
                    "EnvironmentVariables": {"SAFE_DRIVER_INPUT": "1"},
                    "TestBundlePath": "__TESTROOT__/RunnerUITests.xctest",
                }
            }
            source.write_bytes(plistlib.dumps(source_payload))
            source_bytes = source.read_bytes()

            resolved = resolve_ios_external_aut_xctestrun(
                patrol_host_dir=patrol_host,
                patrol_output=(
                    str(source.relative_to(patrol_host)) + " (xctestrun file)"
                ),
            )
            materialized, digest = materialize_ios_external_aut_xctestrun(
                source=resolved,
                production_application_id=PRODUCTION_IOS_ID,
            )
            try:
                injected = plistlib.loads(materialized.read_bytes())
                environment = injected["RunnerUITests"]["EnvironmentVariables"]
                self.assertEqual(environment["SAFE_DRIVER_INPUT"], "1")
                self.assertEqual(
                    environment["QWQ_IOS_TARGET_BUNDLE_ID"], PRODUCTION_IOS_ID
                )
                self.assertEqual(
                    environment["QWQ_IOS_EXPECTED_BUNDLE_ID"], PRODUCTION_IOS_ID
                )
                self.assertEqual(source.read_bytes(), source_bytes)
                self.assertEqual(materialized.parent, source.resolve().parent)
                self.assertRegex(digest, r"^sha256:[0-9a-f]{64}$")
            finally:
                materialized.unlink(missing_ok=True)

    def test_android_driver_binding_uses_android_test_apk_not_host_apk(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            patrol_host = Path(temporary_directory)
            expected_path = (
                patrol_host
                / "build/app/outputs/apk/androidTest/debug/"
                "app-debug-androidTest.apk"
            ).resolve()
            raw = build_tested_app_artifact_binding(
                platform="android",
                device_id="emulator-5556",
                command_application_id=PATROL_ANDROID_DRIVER_APPLICATION_ID,
                build_application_id=PATROL_ANDROID_DRIVER_APPLICATION_ID,
                build_artifact_path=str(expected_path),
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

            def collector(**kwargs):
                self.assertEqual(kwargs["artifact_path"], expected_path)
                self.assertEqual(kwargs["android_adb"], "/sdk/adb")
                self.assertEqual(
                    kwargs["patrol_command"][-1],
                    PATROL_ANDROID_DRIVER_APPLICATION_ID,
                )
                return raw

            with patch(
                "quwoquan_ops.cli.smoke.environment_patrol_smoke."
                "external_aut_driver_artifact.host_source_identity",
                return_value=raw["hostSource"],
            ):
                binding = collect_android_external_aut_driver_artifact_binding(
                    patrol_host_dir=patrol_host,
                    device={
                        "id": "emulator-5556",
                        "targetPlatform": "android-arm64",
                    },
                    command_env={},
                    adb="/sdk/adb",
                    collector=collector,
                )

        validated = validate_external_aut_driver_artifact_binding(
            binding,
            expected_platform="android",
            expected_device_id="emulator-5556",
        )
        self.assertEqual(
            validated["driverApplicationId"],
            PATROL_ANDROID_DRIVER_APPLICATION_ID,
        )
        self.assertNotEqual(
            validated["driverApplicationId"],
            validated["testHostApplicationId"],
        )

    def test_ios_driver_binding_covers_xctest_and_xctrunner_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            patrol_host = Path(temporary_directory)
            products = patrol_host / "build/ios_integ/Build/Products"
            host = products / "debug-iphonesimulator/RunnerUITests-Runner.app"
            test_bundle = host / "PlugIns/RunnerUITests.xctest"
            test_bundle.mkdir(parents=True)
            (host / "Info.plist").write_bytes(
                plistlib.dumps(
                    {"CFBundleIdentifier": PATROL_IOS_XCTRUNNER_BUNDLE_ID}
                )
            )
            (host / "RunnerUITests").write_bytes(b"xctrunner-bytes")
            (test_bundle / "Info.plist").write_bytes(
                plistlib.dumps(
                    {"CFBundleIdentifier": PATROL_IOS_XCTEST_BUNDLE_ID}
                )
            )
            test_binary = test_bundle / "RunnerUITests"
            test_binary.write_bytes(b"xctest-bytes")
            source = products / "Runner_iphonesimulator.xctestrun"
            source.parent.mkdir(parents=True, exist_ok=True)
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

            binding = build_ios_external_aut_driver_artifact_binding(
                source=source,
                patrol_host_dir=patrol_host,
                device_id="ios-simulator-1",
            )
            validated = validate_external_aut_driver_artifact_binding(
                binding,
                expected_platform="ios",
                expected_device_id="ios-simulator-1",
                patrol_host_dir=patrol_host,
            )
            self.assertEqual(
                validated["evidence"]["testBundleIdentifier"],
                PATROL_IOS_XCTEST_BUNDLE_ID,
            )
            test_binary.write_bytes(b"replaced-xctest-bytes")
            with self.assertRaisesRegex(
                ExternalAutDriverEvidenceError,
                "artifact bytes changed",
            ):
                validate_external_aut_driver_artifact_binding(
                    binding,
                    expected_platform="ios",
                    expected_device_id="ios-simulator-1",
                    patrol_host_dir=patrol_host,
                )

    def test_parser_requires_exactly_one_machine_marker(self) -> None:
        payload = json.dumps(_evidence(), separators=(",", ":"), sort_keys=True)
        output = f"log prefix {EXTERNAL_AUT_MARKER}{payload}\n"

        parsed = parse_external_aut_homepage_evidence(output)
        collected = collect_external_aut_homepage_evidence(
            output,
            platform="android",
            production_application_id=PRODUCTION_ANDROID_ID,
        )

        self.assertEqual(parsed, _evidence())
        self.assertEqual(
            collected["evidence"]["productionApplicationId"],
            PRODUCTION_ANDROID_ID,
        )
        with self.assertRaisesRegex(
            ExternalAutDriverEvidenceError, "observed 0"
        ):
            parse_external_aut_homepage_evidence("no marker")
        with self.assertRaisesRegex(
            ExternalAutDriverEvidenceError, "observed 2"
        ):
            parse_external_aut_homepage_evidence(output + output)

    def test_proxy_identity_and_canonical_identity_drift_fail_closed(self) -> None:
        proxy = _evidence()
        proxy["productionApplicationId"] = proxy["testHostApplicationId"]
        with self.assertRaisesRegex(
            ExternalAutDriverEvidenceError, "canonical artifact identity"
        ) as identity_error:
            validate_external_aut_homepage_evidence(
                proxy,
                platform="android",
                production_application_id=PRODUCTION_ANDROID_ID,
            )
        self.assertEqual(identity_error.exception.code, APP_PAGE_ARTIFACT_BINDING_BLOCKER)

        drifted = _evidence()
        with self.assertRaisesRegex(
            ExternalAutDriverEvidenceError, "canonical artifact identity"
        ):
            validate_external_aut_homepage_evidence(
                drifted,
                platform="android",
                production_application_id="com.quwoquan.changed",
            )

        same_driver = _evidence()
        same_driver["driverApplicationId"] = PRODUCTION_ANDROID_ID
        with self.assertRaisesRegex(
            ExternalAutDriverEvidenceError, "driver identity mismatch"
        ):
            validate_external_aut_homepage_evidence(
                same_driver,
                platform="android",
                production_application_id=PRODUCTION_ANDROID_ID,
            )
        with self.assertRaisesRegex(
            ExternalAutDriverEvidenceError, "driver/test host identity"
        ):
            external_aut_native_test_inputs(
                platform="android",
                production_application_id="com.quwoquan.testhost.patrol.test",
            )

    def test_pid_replacement_or_driver_launch_fails_closed(self) -> None:
        replaced = _evidence()
        replaced["processIdAfter"] = 4313
        with self.assertRaisesRegex(
            ExternalAutDriverEvidenceError, "process was replaced"
        ):
            validate_external_aut_homepage_evidence(
                replaced,
                platform="android",
                production_application_id=PRODUCTION_ANDROID_ID,
            )

        with self.assertRaisesRegex(
            ExternalAutDriverEvidenceError, "canonical safe-terminal process"
        ):
            validate_external_aut_homepage_evidence(
                _evidence(),
                platform="android",
                production_application_id=PRODUCTION_ANDROID_ID,
                canonical_process_id=4313,
            )

        launched = _evidence("ios")
        launched["launchPerformed"] = True
        with self.assertRaisesRegex(
            ExternalAutDriverEvidenceError, "must not launch"
        ):
            validate_external_aut_homepage_evidence(
                launched,
                platform="ios",
                production_application_id=PRODUCTION_IOS_ID,
            )

    def test_stopped_ios_aut_or_missing_home_identity_fails_closed(self) -> None:
        stopped = _evidence("ios")
        stopped["stateBefore"] = "not_running"
        with self.assertRaisesRegex(
            ExternalAutDriverEvidenceError, "was not already running"
        ):
            validate_external_aut_homepage_evidence(
                stopped,
                platform="ios",
                production_application_id=PRODUCTION_IOS_ID,
            )

        missing_home = copy.deepcopy(_evidence())
        missing_home["homepageAccessibilityIdentifier"] = "home-feed-card-0"
        with self.assertRaisesRegex(
            ExternalAutDriverEvidenceError, "home accessibility/visible-frame assertion"
        ):
            validate_external_aut_homepage_evidence(
                missing_home,
                platform="android",
                production_application_id=PRODUCTION_ANDROID_ID,
            )

        non_intersecting = copy.deepcopy(_evidence("ios"))
        non_intersecting["homepageFrameIntersectsVisibleWindow"] = False
        with self.assertRaisesRegex(
            ExternalAutDriverEvidenceError, "visible-frame assertion"
        ):
            validate_external_aut_homepage_evidence(
                non_intersecting,
                platform="ios",
                production_application_id=PRODUCTION_IOS_ID,
            )

    def test_journey_binds_application_artifact_candidate_and_pid_evidence(self) -> None:
        binding = _canonical_binding()
        native_driver = _native_driver_binding()
        journey = build_external_aut_homepage_journey(
            native_evidence=_evidence(),
            native_driver_artifact_binding=native_driver,
            canonical_binding=binding,
            patrol_target="test/home_page_content_patrol_test.dart",
            environment_alias="alpha-local",
            platform="android",
            device_id="emulator-5556",
            target="alpha-local",
            environment="alpha",
        )
        validated = validate_external_aut_homepage_journey(
            journey,
            launch_binding=binding,
            native_driver_artifact_binding=native_driver,
            expected_patrol_target="test/home_page_content_patrol_test.dart",
            expected_environment_alias="alpha-local",
            expected_platform="android",
            expected_device_id="emulator-5556",
        )

        self.assertEqual(
            validated["comparisonKeys"],
            [
                "applicationId",
                "artifactDigest",
                "candidateDigest",
                "launchAttemptId",
                "canonicalProcessId",
            ],
        )
        self.assertEqual(validated["tested"], validated["canonical"])

        for field, changed in (
            ("applicationId", "com.quwoquan.changed"),
            ("artifactDigest", _digest("d")),
            ("candidateDigest", _digest("e")),
            ("launchAttemptId", "canonical-launch-attempt-2"),
            ("canonicalProcessId", 4313),
        ):
            with self.subTest(field=field):
                drifted = {**binding, field: changed}
                with self.assertRaisesRegex(
                    ExternalAutDriverEvidenceError,
                    "application/artifact/candidate binding drifted",
                ):
                    validate_external_aut_homepage_journey(
                        journey,
                        launch_binding=drifted,
                        native_driver_artifact_binding=native_driver,
                        expected_patrol_target=(
                            "test/home_page_content_patrol_test.dart"
                        ),
                        expected_environment_alias="alpha-local",
                        expected_platform="android",
                        expected_device_id="emulator-5556",
                    )

    def test_canonical_page_binding_accepts_external_aut_not_driver_as_page(self) -> None:
        binding = _canonical_binding()
        native_driver = _native_driver_binding()
        journey = build_external_aut_homepage_journey(
            native_evidence=_evidence(),
            native_driver_artifact_binding=native_driver,
            canonical_binding=binding,
            patrol_target="test/home_page_content_patrol_test.dart",
            environment_alias="alpha-local",
            platform="android",
            device_id="emulator-5556",
            target="alpha-local",
            environment="alpha",
        )
        page_evidence = {
            "patrolTarget": "test/home_page_content_patrol_test.dart",
            "environmentAlias": "alpha-local",
            "platform": "android",
            "deviceId": "emulator-5556",
            "testedAppArtifactBinding": _test_host_binding_set(),
            "externalProductionAutDriverArtifact": native_driver,
            "externalProductionAutJourneys": {
                "schema": EXTERNAL_AUT_JOURNEY_SET_SCHEMA,
                "status": "passed",
                "required": True,
                "journeys": [journey],
            },
        }

        result = _app_content_page_artifact_binding(
            page_evidence=page_evidence,
            launch_binding=binding,
            expected_patrol_target="test/home_page_content_patrol_test.dart",
            expected_environment_alias="alpha-local",
            expected_platform="android",
            expected_device_id="emulator-5556",
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["tested"]["applicationId"], PRODUCTION_ANDROID_ID)
        self.assertEqual(
            result["nativeDriver"]["applicationId"],
            PATROL_ANDROID_DRIVER_APPLICATION_ID,
        )
        self.assertEqual(
            result["testHost"]["applicationId"],
            PATROL_ANDROID_HOST_APPLICATION_ID,
        )
        self.assertNotEqual(
            result["tested"]["applicationId"],
            "com.quwoquan.testhost.patrol",
        )

        drifted_driver = copy.deepcopy(page_evidence)
        drifted_driver["testedAppArtifactBinding"]["bindings"][0][
            "deviceId"
        ] = "emulator-replaced"
        with self.assertRaisesRegex(
            ValueError, "Patrol test-host identity drifted"
        ):
            _app_content_page_artifact_binding(
                page_evidence=drifted_driver,
                launch_binding=binding,
                expected_patrol_target="test/home_page_content_patrol_test.dart",
                expected_environment_alias="alpha-local",
                expected_platform="android",
                expected_device_id="emulator-5556",
            )

        substituted_driver = copy.deepcopy(page_evidence)
        substituted_driver["externalProductionAutDriverArtifact"] = (
            substituted_driver["testedAppArtifactBinding"]["bindings"][0]
        )
        with self.assertRaisesRegex(ValueError, "native driver artifact"):
            _app_content_page_artifact_binding(
                page_evidence=substituted_driver,
                launch_binding=binding,
                expected_patrol_target="test/home_page_content_patrol_test.dart",
                expected_environment_alias="alpha-local",
                expected_platform="android",
                expected_device_id="emulator-5556",
            )

    def test_report_settles_only_one_passed_named_external_journey(self) -> None:
        report = {
            "status": "passed",
            "externalProductionAutJourneys": new_external_aut_journey_set(
                required=True
            ),
            "externalProductionAutDriverArtifact": _native_driver_binding(),
        }
        settle_external_aut_journey_report(report)
        self.assertEqual(report["status"], "gate_block")
        self.assertEqual(
            report["externalProductionAutJourneys"]["errorCode"],
            APP_PAGE_ARTIFACT_BINDING_BLOCKER,
        )

        report = {
            "status": "passed",
            "externalProductionAutJourneys": new_external_aut_journey_set(
                required=True
            ),
            "externalProductionAutDriverArtifact": _native_driver_binding(),
        }
        attach_external_aut_journey(
            report,
            build_external_aut_homepage_journey(
                native_evidence=_evidence(),
                native_driver_artifact_binding=_native_driver_binding(),
                canonical_binding=_canonical_binding(),
                patrol_target="test/home_page_content_patrol_test.dart",
                environment_alias="alpha-local",
                platform="android",
                device_id="emulator-5556",
                target="alpha-local",
                environment="alpha",
            ),
        )
        settle_external_aut_journey_report(report)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(
            report["externalProductionAutJourneys"]["status"], "passed"
        )

if __name__ == "__main__":
    unittest.main()
