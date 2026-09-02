"""Alpha app-content-uat 受控 Edge suite 编排与恢复证据合约。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-004.t3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import app_preflight_uat as uat
from quwoquan_ops.cli.commands.app_preflight_uat_patrol_dependency import (
    PatrolDependencyFailure,
    PatrolDependencyFailureDetail,
)

_CONFIGURATION_DIGEST = "sha256:" + "a" * 64
_MANIFEST_DIGEST = "sha256:" + "b" * 64
_BASELINE = "sha256:" + "f" * 64
_RELEASE_TRAIN = "sha256:" + "9" * 64
_CONTRACT_GRAPH_DIGEST = "sha256:" + "7" * 64
_HEALTH_URL = "https://alpha-api.example.test/healthz"


def _launch_binding(report_dir: Path) -> dict[str, str]:
    attempt_dir = report_dir / "alpha-local/canonical-launch/attempt-1"
    return {
        "target": "alpha-local",
        "launchAttemptId": "launch-attempt-alpha",
        "launchProvenance": "canonical_launcher",
        "artifactDigest": "sha256:" + "6" * 64,
        "runtimeConfigTrustEnvelopeDigest": "sha256:" + "7" * 64,
        "runtimeConfigPackageDigest": "sha256:" + "8" * 64,
        "launchAttemptDigest": "sha256:" + "a" * 64,
        "launchAttemptRef": str(attempt_dir / "attempt.json"),
        "launchReportRef": str(attempt_dir / "report.json"),
        "contractGraphDigest": _CONTRACT_GRAPH_DIGEST,
        "contractGraphRef": str(report_dir / "source-projection/contract_graph.json"),
        "contractGraphOperationCount": 1,
        "sourceProjectionRoot": str(report_dir / "source-projection"),
    }


def _sample_plan() -> dict[str, object]:
    return {
        "schema": "quwoquan_data.release_uat_sample_plan",
        "releaseId": "release-alpha",
        "releaseDigest": "sha256:" + "b" * 64,
        "selectionEvidence": {"sourceIdentitySetDigest": "sha256:" + "d" * 64},
    }


def _preflight(report_dir: Path) -> dict[str, object]:
    sample_plan = _sample_plan()
    sample_plan_path = report_dir / "uat" / "sample_plan.json"
    sample_plan_path.parent.mkdir(parents=True, exist_ok=True)
    sample_plan_path.write_bytes(
        json.dumps(sample_plan, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    sample_plan_digest = (
        "sha256:" + hashlib.sha256(sample_plan_path.read_bytes()).hexdigest()
    )
    return {
        "exitCode": 0,
        "target": "alpha-local",
        "environment": "alpha",
        "purpose": "content_live",
        "launchPolicy": "immutable_candidate",
        "nonPromotable": False,
        "status": "passed",
        "contentLive": "passed",
        "contentBindingState": "bound",
        "packageBaseline": _BASELINE,
        "releaseId": "release-alpha",
        "manifestDigest": _MANIFEST_DIGEST,
        "readinessReceiptRef": "env/alpha/runs/readiness.json",
        "readinessReceiptDigest": "sha256:" + "c" * 64,
        "releaseUatSamplePlan": sample_plan,
        "releaseUatSamplePlanRef": str(sample_plan_path),
        "releaseUatSamplePlanDigest": sample_plan_digest,
        "appUatPlan": {
            "releaseIdentity": {
                "releaseId": "release-alpha",
                "payloadSha256": _MANIFEST_DIGEST,
            },
            "releaseUatSamplePlanRef": str(sample_plan_path),
            "releaseUatSamplePlanDigest": sample_plan_digest,
            "carrierIdentities": {"video": "video-alpha"},
            "orderedSamples": [
                {
                    "sampleId": "canary-video-001",
                    "carrier": "video",
                    "objectId": "video-alpha",
                    "objectRef": "objects/posts/video/video-alpha",
                    "objectDigest": "sha256:" + "8" * 64,
                }
            ],
            "requiredCasePlan": [],
            "videoPagination": {"expectedWorkIds": ["video-alpha"]},
        },
    }


def _runtime_binding(report_dir: Path) -> dict[str, object]:
    return {
        "launchPolicy": "immutable_candidate",
        "nonPromotable": False,
        "environment": "alpha",
        "target": "alpha-local",
        "packageBaseline": _BASELINE,
        "candidateDigest": _BASELINE,
        "releaseTrainId": _RELEASE_TRAIN,
        "composeProject": "quwoquan_alpha_test_live",
        "sourceCapsuleManifestRef": str(
            report_dir / "candidate/input-capsule/manifest.json"
        ),
        "startupIdentity": {
            "candidateDigest": _BASELINE,
            "configurationDigest": _CONFIGURATION_DIGEST,
        },
    }


def _controlled_edge_evidence(*, restored: bool = True) -> dict[str, object]:
    return {
        "status": "passed",
        "controlledEdgeFault": {
            "environment": "alpha",
            "copyKey": "serviceUnavailable",
            "singlePrimaryAction": True,
            "forbiddenBrandAbsent": True,
            "technicalDetailsAbsent": True,
            "blockedRetryCount": 5,
            "blockingErrorRetained": True,
            "sameInstallRecovery": True,
            "recoveredVisibleCardCount": 3,
        },
        "controlledEdgeFaultReceipt": {
            "schema": "quwoquan_ops.controlled_edge_fault",
            "status": "restored" if restored else "fault_active",
            "target": "alpha-local",
            "environment": "alpha",
            "composeProject": "quwoquan_alpha_test_live",
            "configurationDigest": _CONFIGURATION_DIGEST,
            "healthUrl": _HEALTH_URL,
            "services": [
                {
                    "service": service,
                    "containerId": f"{service}-container",
                    "imageRef": f"quwoquan/{service}:candidate",
                    "runtimeImageId": "sha256:" + marker * 64,
                    "statusBefore": "running",
                    "statusAfter": "running",
                }
                for service, marker in (("api-edge", "d"), ("gamma-proxy", "e"))
            ],
            "faultStartedAt": "2026-08-28T00:00:00Z",
            "restoredAt": "2026-08-28T00:00:01Z" if restored else None,
        },
    }


def _smoke_command(
    _environment: str,
    target: str,
    report_dir: Path,
    **kwargs: object,
) -> dict[str, object]:
    suite_name = str(kwargs["suite_name"])
    return {
        "argv": [
            "patrol",
            suite_name,
            "--gateway-base-url",
            "https://alpha-api.example.test",
        ],
        "cwd": report_dir,
        "reportPath": str(report_dir / suite_name / f"{target}.json"),
    }


class AppContentPreflightUatControlledEdgeTest(unittest.TestCase):
    def _run(
        self,
        report_dir: Path,
        *,
        restored: bool,
        dependency_failure: BaseException | None = None,
        child_blocker: dict[str, object] | None = None,
        child_returncode: int = 0,
    ) -> tuple[dict[str, object], object, object, object]:
        report_dir = Path(report_dir).resolve()
        report_dir.mkdir(parents=True, exist_ok=True)
        candidate_manifest = report_dir / "candidate/manifest.json"
        candidate_manifest.parent.mkdir(parents=True, exist_ok=True)
        candidate_manifest.write_text("candidate-manifest\n", encoding="utf-8")
        contract_graph = report_dir / "source-projection/contract_graph.json"
        contract_graph.parent.mkdir(parents=True, exist_ok=True)
        contract_graph.write_text("contract-graph\n", encoding="utf-8")
        raw_source = {
            "slotId": "sha256:" + "1" * 64,
            "ref": "raw-readiness-case-results/alpha.json",
            "digest": "sha256:" + "2" * 64,
        }
        raw_projection = {
            "rawResultRefs": {
                "alpha-local": [
                    {"slotId": raw_source["slotId"], "ref": raw_source["ref"]}
                ]
            },
            "rawResultDigests": {
                "alpha-local": [
                    {
                        "slotId": raw_source["slotId"],
                        "digest": raw_source["digest"],
                    }
                ]
            },
            "rawCoverage": {
                "alpha-local": {"expected": 1, "present": 1, "missing": 0}
            },
            "rawGaps": {"alpha-local": []},
        }
        successful = subprocess.CompletedProcess(["patrol"], 0, "", "")
        patrol_result = subprocess.CompletedProcess(
            ["patrol"],
            child_returncode,
            "token=child-secret" if child_returncode else "",
            "path=/private/child-secret" if child_returncode else "",
        )

        def evidence(
            report_ref: str,
            *,
            contract_graph_binding: dict[str, object],
        ) -> dict[str, object]:
            self.assertEqual(
                contract_graph_binding["contractGraphDigest"],
                _CONTRACT_GRAPH_DIGEST,
            )
            if child_blocker is not None:
                return {
                    "status": "passed",
                    "typedBlocker": dict(child_blocker),
                    "testedAppArtifactBinding": {"status": "passed"},
                    "contractGraphDigest": _CONTRACT_GRAPH_DIGEST,
                }
            if "controlled-edge-recovery" in report_ref:
                return {
                    **_controlled_edge_evidence(restored=restored),
                    "contractGraphDigest": _CONTRACT_GRAPH_DIGEST,
                }
            return {"contractGraphDigest": _CONTRACT_GRAPH_DIGEST}

        def dependency_bound(
            **kwargs: object,
        ) -> tuple[
            subprocess.CompletedProcess[str],
            dict[str, object] | None,
            dict[str, object],
        ]:
            command = kwargs["profile_command"]
            if kwargs["message_home"]:
                result, scope = stackctl._run_app_content_message_home_command(
                    command,
                    target_name=kwargs["target_name"],
                    actor_context=kwargs["actor_context"],
                )
            else:
                result = stackctl._run_profile_command(
                    command,
                    target_name=kwargs["target_name"],
                    actor_context=kwargs["actor_context"],
                )
                scope = None
            return result, scope, {"schema": "test-patrol-dependency-readback"}

        patchers = [
            patch.object(
                stackctl,
                "output_root",
                return_value=report_dir,
            ),
            patch.object(
                stackctl,
                "command_app_debug_preflight",
                return_value=_preflight(report_dir),
            ),
            patch.object(
                stackctl,
                "_app_content_test_live_runtime_binding",
                return_value=_runtime_binding(report_dir),
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
                stackctl,
                "_run_app_content_release_probe",
                return_value={
                    "target": "alpha-local",
                    "suite": "release-bound-readback",
                    "exitCode": 0,
                    "sampleExecution": {
                        "samples": [
                            {
                                "sampleId": "canary-video-001",
                                "carrier": "video",
                                "sourceObjectId": "video-alpha",
                                "readObjectId": "video-alpha",
                            }
                        ]
                    },
                },
            ),
            patch.object(
                uat,
                "_target_uat_binding_for_execution",
                return_value=(
                    {"schema": "fixture-target-uat-binding"},
                    {
                        "ref": "target-uat-bindings/alpha-local.json",
                        "digest": "sha256:" + "4" * 64,
                    },
                ),
            ),
            patch.object(
                uat,
                "expected_app_uat_raw_coverage",
                return_value=1,
            ),
            patch.object(
                uat,
                "collect_app_uat_case_execution_reports",
                return_value=[],
            ),
            patch.object(
                uat,
                "emit_app_uat_raw_results",
                return_value=[dict(raw_source)],
            ),
            patch.object(
                uat,
                "project_app_content_uat_raw_authority",
                return_value=(raw_projection, []),
            ),
            patch.object(
                stackctl,
                "run",
                return_value=successful,
            ),
            patch.object(
                uat,
                "_app_content_launch_binding",
                return_value=_launch_binding(report_dir),
            ),
            patch.object(
                stackctl,
                "_app_content_test_live_actor_context",
                return_value=object(),
            ),
            patch.object(
                uat,
                "_app_content_readiness_path",
                return_value=report_dir / "readiness.json",
            ),
            patch.object(
                uat,
                "execute_patrol_with_dependency_cas",
                side_effect=(
                    dependency_failure
                    if dependency_failure is not None
                    else dependency_bound
                ),
            ),
            patch.object(
                stackctl,
                "_app_content_patrol_evidence",
                side_effect=evidence,
            ),
            patch.object(
                uat,
                "_app_content_page_artifact_binding",
                return_value={"status": "passed"},
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
        ]
        with ExitStack() as stack:
            for patcher in patchers:
                stack.enter_context(patcher)
            smoke_profile = stack.enter_context(
                patch.object(
                    stackctl,
                    "_environment_page_smoke_profile_command",
                    side_effect=_smoke_command,
                )
            )
            profile_runner = stack.enter_context(
                patch.object(
                    stackctl,
                    "_run_profile_command",
                    return_value=patrol_result,
                )
            )
            message_runner = stack.enter_context(
                patch.object(
                    stackctl,
                    "_run_app_content_message_home_command",
                    return_value=(patrol_result, {}),
                )
            )
            result = stackctl._command_app_content_uat(
                argparse.Namespace(
                    targets="alpha-local",
                    platform="android",
                    device_id="emulator-5554",
                    dry_run=False,
                    report_dir=str(report_dir),
                )
            )
        return result, smoke_profile, profile_runner, message_runner

    def test_alpha_suite_runs_receipt_bound_fault_and_aggregates_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result, smoke_profile, profile_runner, message_runner = self._run(
                Path(temporary_directory) / "passed",
                restored=True,
            )

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["launchPolicy"], "immutable_candidate")
        self.assertTrue(result["nonPromotable"])
        self.assertEqual(result["packageBaselines"], {"alpha-local": _BASELINE})
        self.assertEqual(result["releaseTrainId"], _RELEASE_TRAIN)
        controlled_calls = [
            call
            for call in profile_runner.call_args_list
            if "controlled-edge-recovery" in str(call.args[0].get("argv"))
        ]
        self.assertEqual(len(controlled_calls), 1)
        self.assertIn(
            "--stackctl-controlled-edge-fault",
            controlled_calls[0].args[0]["argv"],
        )
        self.assertEqual(smoke_profile.call_count, 7)
        self.assertEqual(message_runner.call_count, 1)
        recovery = result["controlledEdgeRecoveries"]["alpha-local"]
        self.assertTrue(recovery["evidence"]["sameInstallRecovery"])
        self.assertEqual(recovery["receipt"]["status"], "restored")
        self.assertEqual(recovery["receipt"]["healthUrl"], _HEALTH_URL)
        suite_run = next(
            item
            for item in result["runs"]
            if item.get("suite") == "controlled-edge-recovery"
        )
        self.assertEqual(suite_run["exitCode"], 0)
        self.assertEqual(
            suite_run["evidence"]["controlledEdgeFaultReceipt"]["composeProject"],
            "quwoquan_alpha_test_live",
        )

    def test_missing_restore_receipt_is_first_failure_and_stops_later_suites(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result, smoke_profile, profile_runner, message_runner = self._run(
                Path(temporary_directory) / "blocked",
                restored=False,
            )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["status"], "gate_block")
        self.assertEqual(
            result["details"],
            [
                (
                    "alpha-local: controlled-edge-recovery failed: controlled edge "
                    "recovery receipt does not match current runtime binding"
                )
            ],
        )
        self.assertEqual(smoke_profile.call_count, 2)
        self.assertEqual(profile_runner.call_count, 2)
        self.assertEqual(message_runner.call_count, 0)
        self.assertEqual(
            [item.get("suite") for item in result["runs"]],
            [
                "release-bound-readback",
                "canonical-launch",
                "release-sample-matrix",
                "controlled-edge-recovery",
            ],
        )
        self.assertEqual(result["runs"][-1]["exitCode"], 1)

    def test_zero_exit_page_cannot_override_child_receipt_blocker(self) -> None:
        blocker = {
            "errorCode": "APP.LAUNCH.runtime_config_activation_failed",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            result, smoke_profile, profile_runner, message_runner = self._run(
                Path(temporary_directory) / "child-blocked",
                restored=True,
                child_blocker=blocker,
            )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["status"], "gate_block")
        self.assertEqual(result["firstBlocker"], blocker["errorCode"])
        self.assertEqual(result["runs"][-1]["exitCode"], 2)
        self.assertEqual(result["runs"][-1]["typedBlocker"], blocker)
        self.assertEqual(
            result["details"],
            [
                (
                    "alpha-local: release-sample-matrix failed: "
                    "APP.LAUNCH.runtime_config_activation_failed"
                )
            ],
        )
        self.assertEqual(smoke_profile.call_count, 1)
        self.assertEqual(profile_runner.call_count, 1)
        self.assertEqual(message_runner.call_count, 0)

    def test_nonzero_child_uses_typed_blocker_without_raw_output_leak(self) -> None:
        blocker = {"errorCode": "APP.LAUNCH.runtime_config_activation_failed"}
        with tempfile.TemporaryDirectory() as temporary_directory:
            result, *_ = self._run(
                Path(temporary_directory) / "child-nonzero",
                restored=True,
                child_blocker=blocker,
                child_returncode=2,
            )

        self.assertEqual(result["firstBlocker"], blocker["errorCode"])
        self.assertEqual(
            result["details"],
            [
                (
                    "alpha-local: release-sample-matrix failed: "
                    "APP.LAUNCH.runtime_config_activation_failed"
                )
            ],
        )
        self.assertNotIn("child-secret", str(result))

    def test_post_only_dependency_failure_receipt_keeps_its_original_stage(
        self,
    ) -> None:
        failure = PatrolDependencyFailure(
            PatrolDependencyFailureDetail(
                error_code="APP.DEPENDENCY.projection_cas_drift",
                stage="post-command-cas",
                cause_type="ValueError",
                diagnostic_digest="sha256:" + "1" * 64,
            )
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            result, *_ = self._run(
                Path(temporary_directory) / "post-only",
                restored=True,
                dependency_failure=failure,
            )

        blocker = result["runs"][-1]["typedBlocker"]
        self.assertEqual(result["firstBlocker"], failure.error_code)
        self.assertEqual(blocker["stage"], "post-command-cas")
        self.assertEqual(blocker["diagnosticDigest"], "sha256:" + "1" * 64)
        self.assertNotIn("secondaryFailures", blocker)

    def test_dependency_failure_receipt_preserves_ordered_secondary_failure(
        self,
    ) -> None:
        failure = PatrolDependencyFailure(
            PatrolDependencyFailureDetail(
                error_code="APP.DEPENDENCY.projection_expectation_invalid",
                stage="post-command-cwd",
                cause_type="ValueError",
                diagnostic_digest="sha256:" + "2" * 64,
            ),
            (
                PatrolDependencyFailureDetail(
                    error_code="APP.DEPENDENCY.projection_cas_drift",
                    stage="post-command-cas",
                    cause_type="RuntimeError",
                    diagnostic_digest="sha256:" + "3" * 64,
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            result, *_ = self._run(
                Path(temporary_directory) / "secondary",
                restored=True,
                dependency_failure=failure,
            )

        blocker = result["runs"][-1]["typedBlocker"]
        self.assertEqual(blocker["stage"], "post-command-cwd")
        self.assertEqual(
            blocker["secondaryFailures"],
            [failure.secondary[0].as_dict()],
        )

    def test_unknown_dependency_exception_is_wrapped_as_safe_command_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result, *_ = self._run(
                Path(temporary_directory) / "unknown",
                restored=True,
                dependency_failure=RuntimeError(
                    "token=private-value path=/private/patrol-command.log"
                ),
            )

        blocker = result["runs"][-1]["typedBlocker"]
        self.assertEqual(
            blocker["errorCode"],
            "APP.DEPENDENCY.projection_execution_failed",
        )
        self.assertEqual(blocker["stage"], "command")
        persisted = str(result)
        self.assertNotIn("private-value", persisted)
        self.assertNotIn("/private/patrol-command.log", persisted)


if __name__ == "__main__":
    unittest.main()
