"""App content UAT artifact blocker and runner-policy contracts."""

from __future__ import annotations

from quwoquan_ops.cli.commands import app_preflight_uat as uat
from quwoquan_ops.tests.support.app_content_preflight_test_support import (
    Path,
    patch,
    stackctl,
    subprocess,
    tempfile,
    unittest,
)


class AppContentPreflightUatArtifactTest(unittest.TestCase):
    def test_android_content_uat_preserves_child_artifact_blocker_order(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_dir = Path(temporary_directory) / "android-uat"
            readiness_path = Path(temporary_directory) / "readiness.json"
            call_order: list[str] = []
            baseline = "sha256:" + "8" * 64
            preflight = {
                "exitCode": 0,
                "target": "beta-local",
                "environment": "beta",
                "purpose": "content_live",
                "launchPolicy": "immutable_candidate",
                "nonPromotable": False,
                "status": "passed",
                "contentLive": "passed",
                "contentBindingState": "bound",
                "packageBaseline": baseline,
                "releaseId": "beta-research-pool8",
                "manifestDigest": "sha256:" + "5" * 64,
                "readinessReceiptRef": str(readiness_path),
                "readinessReceiptDigest": "sha256:" + "6" * 64,
                "appUatEnvelope": {
                    "releaseId": "beta-research-pool8",
                    "videoWorkId": "video-01",
                },
                "appUatPlan": {
                    "releaseId": "beta-research-pool8",
                    "videoPagination": {"expectedWorkIds": ["video-01"]},
                },
            }
            page_comparison = {
                "applicationId": "com.leadwise.quwoquan.nonprod.debug",
                "artifactDigest": "sha256:" + "a" * 64,
                "sourceProjectionDigest": "sha256:" + "e" * 64,
                "runtimeConfigPackageDigest": "sha256:" + "c" * 64,
                "trustDigest": "sha256:" + "b" * 64,
                "launchAttemptId": "launch-attempt-beta",
            }
            artifact_blocker = {
                "errorCode": "APP.UAT.page_artifact_binding_missing",
                "sourceOperationId": (
                    "environment_page_smoke.tested_app_artifact_binding"
                ),
                "httpStatus": None,
            }
            typed_missing = [
                {
                    "field": field,
                    "errorCode": "APP.UAT.page_artifact_binding_missing",
                    "reason": f"test_host_patrol does not own canonical {field}",
                }
                for field in (
                    "sourceProjectionDigest",
                    "runtimeConfigPackageDigest",
                    "trustDigest",
                    "launchAttemptId",
                )
            ]
            page_evidence = {
                "patrolTarget": stackctl.DISCOVERY_FEED_UAT_TEST_TARGET,
                "environmentAlias": "beta-local",
                "platform": "android",
                "deviceId": "emulator-5556",
                "testedAppArtifactBinding": {
                    "status": "gate_block",
                    "errorCode": "APP.UAT.page_artifact_binding_missing",
                    "bindings": [
                        {
                            "status": "gate_block",
                            "errorCode": "APP.UAT.page_artifact_binding_missing",
                            "canonicalComparison": {
                                **page_comparison,
                                "sourceProjectionDigest": "",
                                "runtimeConfigPackageDigest": "",
                                "trustDigest": "",
                                "launchAttemptId": "",
                                "typedMissing": typed_missing,
                            },
                        }
                    ],
                    "comparisonProjections": [],
                },
                "typedBlocker": dict(artifact_blocker),
                "artifactBindingBlocker": dict(artifact_blocker),
            }

            def smoke_command(
                _environment: str,
                target: str,
                _report_dir: Path,
                **kwargs: object,
            ) -> dict[str, object]:
                suite_name = str(kwargs["suite_name"])
                argv = ["patrol", suite_name]
                if suite_name == "app-content-controlled-edge-recovery":
                    argv.extend(("--gateway-base-url", "http://127.0.0.1:12345"))
                return {
                    "argv": argv,
                    "cwd": Path(temporary_directory),
                    "reportPath": f"reports/{target}-{suite_name}.json",
                }

            def execute(
                argv: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
                self.assertEqual(
                    argv[:2],
                    ["bash", str(stackctl.ROOT / "quwoquan_app/run.sh")],
                )
                self.assertIn("--exit-after-launch", argv)
                call_order.append("launcher")
                return subprocess.CompletedProcess(argv, 0, "", "")

            def run_patrol(
                *_args: object, **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
                call_order.append("patrol")
                return subprocess.CompletedProcess(["patrol"], 2, "", "")

            with (
                patch.object(
                    stackctl,
                    "command_app_debug_preflight",
                    return_value=preflight,
                ),
                patch.object(
                    stackctl,
                    "_app_content_test_live_runtime_binding",
                    return_value={
                        "target": "beta-local",
                        "candidateDigest": baseline,
                        "releaseTrainId": "sha256:" + "9" * 64,
                    },
                ),
                patch.object(
                    uat,
                    "materialize_app_content_launch_projection",
                    return_value={
                        "sourceProjectionRoot": str(stackctl.ROOT),
                        "sourceCapsuleManifestRef": "/candidate/manifest.json",
                        "sourceCapsuleManifestDigest": "sha256:" + "1" * 64,
                        "sourceProjectionEvidenceDigest": "sha256:" + "2" * 64,
                        "sourceProjectionEvidenceRef": "/evidence/projection.json",
                    },
                ),
                patch.object(
                    uat,
                    "verify_app_content_launch_projection",
                    return_value={},
                ),
                patch.object(
                    uat,
                    "write_app_content_launch_control",
                    return_value={
                        "sourceCapsuleManifestRef": "/candidate/manifest.json",
                        "controlRef": "/evidence/control.json",
                        "controlDigest": "sha256:" + "3" * 64,
                        "startupTerminalReceiptRef": "/evidence/terminal.json",
                    },
                ),
                patch.object(
                    uat,
                    "_app_content_readiness_path",
                    return_value=readiness_path,
                ),
                patch.object(
                    stackctl,
                    "_run_app_content_release_probe",
                    return_value={
                        "target": "beta-local",
                        "suite": "release-bound-readback",
                        "exitCode": 0,
                    },
                ),
                patch.object(
                    uat,
                    "_app_content_launch_binding",
                    return_value={
                        "target": "beta-local",
                        "platform": "android",
                        "deviceId": "emulator-5556",
                        "launchAttemptId": "launch-attempt-beta",
                        "launchProvenance": "canonical_launcher",
                        "applicationId": page_comparison["applicationId"],
                        "artifactDigest": "sha256:" + "a" * 64,
                        "runtimeConfigTrustEnvelopeDigest": "sha256:" + "b" * 64,
                        "runtimeConfigPackageDigest": "sha256:" + "c" * 64,
                        "sourceProjectionDigest": page_comparison[
                            "sourceProjectionDigest"
                        ],
                        "launchAttemptDigest": "sha256:" + "d" * 64,
                        "launchAttemptRef": str(
                            report_dir
                            / "beta-local/canonical-launch/attempt-1/attempt.json"
                        ),
                        "launchReportRef": str(
                            report_dir
                            / "beta-local/canonical-launch/attempt-1/report.json"
                        ),
                    },
                ),
                patch.object(
                    stackctl,
                    "_app_content_test_live_actor_context",
                    return_value=None,
                ),
                patch.object(
                    stackctl,
                    "_environment_page_smoke_profile_command",
                    side_effect=smoke_command,
                ),
                patch.object(
                    stackctl,
                    "_run_profile_command",
                    side_effect=run_patrol,
                ),
                patch.object(
                    stackctl,
                    "_run_app_content_message_home_command",
                    side_effect=lambda *_args, **_kwargs: (run_patrol(), {}),
                ),
                patch.object(
                    uat,
                    "execute_patrol_with_dependency_cas",
                    side_effect=lambda **_kwargs: (
                        run_patrol(),
                        None,
                        {"schema": "test-patrol-dependency-readback"},
                    ),
                ),
                patch.object(
                    stackctl,
                    "_app_content_patrol_evidence",
                    return_value=page_evidence,
                ),
                patch.object(
                    uat,
                    "_controlled_edge_recovery_evidence_issue",
                    return_value="",
                ),
                patch.object(
                    stackctl,
                    "_app_content_experience_screenshot_digests",
                    return_value={
                        "homepage-feed": "sha256:" + "1" * 64,
                        "app-core-readback": "sha256:" + "2" * 64,
                        "message-home": "sha256:" + "3" * 64,
                        "profile-journey": "sha256:" + "4" * 64,
                    },
                ),
                patch.object(stackctl, "run", side_effect=execute),
            ):
                artifact_blocked_result = stackctl._command_app_content_uat(
                    stackctl.argparse.Namespace(
                        targets="beta-local",
                        platform="android",
                        device_id="emulator-5556",
                        dry_run=False,
                        report_dir=str(report_dir),
                    )
                )
                page_evidence["typedBlocker"] = {
                    "errorCode": "CONTENT.SYSTEM.required_dependency_unavailable",
                    "sourceOperationId": "content.feed.read",
                    "httpStatus": 503,
                }
                earlier_blocked_result = stackctl._command_app_content_uat(
                    stackctl.argparse.Namespace(
                        targets="beta-local",
                        platform="android",
                        device_id="emulator-5556",
                        dry_run=False,
                        report_dir=str(report_dir),
                    )
                )

        self.assertEqual(
            call_order,
            ["launcher", "patrol", "launcher", "patrol"],
        )
        self.assertEqual(
            artifact_blocked_result["launchBindings"]["beta-local"]["artifactDigest"],
            "sha256:" + "a" * 64,
        )
        self.assertEqual(artifact_blocked_result["exitCode"], 2)
        self.assertEqual(
            artifact_blocked_result["firstBlocker"],
            "APP.UAT.page_artifact_binding_missing",
        )
        artifact_run = next(
            item for item in artifact_blocked_result["runs"] if item.get("errorCode")
        )
        self.assertEqual(artifact_run["exitCode"], 2)
        self.assertEqual(
            artifact_run["errorCode"],
            "APP.UAT.page_artifact_binding_missing",
        )
        self.assertEqual(
            artifact_run["pageArtifactBinding"]["status"],
            "gate_block",
        )
        self.assertEqual(
            artifact_run["evidence"]["testedAppArtifactBinding"]["bindings"][0][
                "canonicalComparison"
            ]["typedMissing"],
            typed_missing,
        )
        self.assertEqual(earlier_blocked_result["exitCode"], 2)
        self.assertEqual(
            earlier_blocked_result["firstBlocker"],
            "CONTENT.SYSTEM.required_dependency_unavailable",
        )
        earlier_run = next(
            item for item in earlier_blocked_result["runs"] if item.get("errorCode")
        )
        self.assertEqual(earlier_run["exitCode"], 2)
        self.assertEqual(
            earlier_run["errorCode"],
            "CONTENT.SYSTEM.required_dependency_unavailable",
        )
        self.assertEqual(
            earlier_run["pageArtifactBinding"]["status"],
            "gate_block",
        )

    def test_app_content_uat_rejects_test_live_binding(self) -> None:
        preflight = {
            "launchPolicy": "test_live",
            "target": "alpha-local",
            "environment": "alpha",
            "packageBaseline": "",
        }
        with self.assertRaisesRegex(
            ValueError,
            "immutable content_live preflight",
        ):
            stackctl._app_content_test_live_runtime_binding(preflight)

    def test_app_content_uat_typed_actor_policy_matches_runner_contract(self) -> None:
        alpha_targets = {
            stackctl.DISCOVERY_FEED_UAT_TEST_TARGET,
            stackctl.PROFILE_JOURNEY_UAT_TEST_TARGET,
            stackctl.MESSAGE_HOME_UAT_TEST_TARGET,
            stackctl.APP_CORE_READBACK_UAT_TEST_TARGET,
            stackctl.HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET,
            stackctl.VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET,
            stackctl.CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET,
        }
        for target in alpha_targets:
            self.assertTrue(
                stackctl._app_content_uat_requires_typed_actor("alpha", target)
            )
        for environment in ("beta", "gamma"):
            for target in (
                stackctl.PROFILE_JOURNEY_UAT_TEST_TARGET,
                stackctl.MESSAGE_HOME_UAT_TEST_TARGET,
                stackctl.APP_CORE_READBACK_UAT_TEST_TARGET,
                stackctl.HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET,
            ):
                self.assertTrue(
                    stackctl._app_content_uat_requires_typed_actor(
                        environment,
                        target,
                    )
                )
            for target in (
                stackctl.DISCOVERY_FEED_UAT_TEST_TARGET,
                stackctl.VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET,
                stackctl.CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET,
            ):
                self.assertFalse(
                    stackctl._app_content_uat_requires_typed_actor(
                        environment,
                        target,
                    )
                )

    def test_experience_screenshots_are_complete_and_distinct(self) -> None:
        suites = (
            "homepage-feed",
            "app-core-readback",
            "message-home",
            "profile-journey",
        )
        runs = [
            {
                "target": "alpha-local",
                "suite": suite,
                "exitCode": 0,
                "evidence": {
                    "screenshotDigest": f"sha256:{index:064x}",
                    "screenshotMarker": {
                        "environment": "alpha",
                        "suite": suite,
                        "route": f"/terminal/{suite}",
                        "terminalKey": f"terminal-{suite}",
                    },
                },
            }
            for index, suite in enumerate(suites, start=1)
        ]
        self.assertEqual(
            set(
                stackctl._app_content_experience_screenshot_digests(
                    runs,
                    target="alpha-local",
                )
            ),
            set(suites),
        )
        runs[-1]["evidence"]["screenshotDigest"] = runs[0]["evidence"][
            "screenshotDigest"
        ]
        with self.assertRaisesRegex(ValueError, "must be distinct"):
            stackctl._app_content_experience_screenshot_digests(
                runs,
                target="alpha-local",
            )
        runs[-1]["evidence"] = {"screenshotDigest": ""}
        with self.assertRaisesRegex(ValueError, "route/key marker"):
            stackctl._app_content_experience_screenshot_digests(
                runs,
                target="alpha-local",
            )
        runs[-1]["evidence"] = {
            "screenshotDigest": "sha256:" + "4" * 64,
            "screenshotMarker": {
                "environment": "alpha",
                "suite": suites[-1],
                "route": "/user/example",
                "terminalKey": "profile-header-avatar",
            },
        }
        runs[-1]["evidence"]["screenshotDigest"] = ""
        with self.assertRaisesRegex(ValueError, "digest is missing"):
            stackctl._app_content_experience_screenshot_digests(
                runs,
                target="alpha-local",
            )
