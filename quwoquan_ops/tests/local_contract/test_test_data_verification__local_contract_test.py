"""stackctl selected typed test-data request handoff contracts.

spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t3
spec_ref: specs/feature-tree/runtime/runtime-testinfra/test-data-provisioning-and-isolation/spec.md#gwt-001
"""

from __future__ import annotations

import json
import tempfile
import unittest
from enum import StrEnum
from pathlib import Path
from threading import Event, Lock
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.test_data.api import (
    AssertionStatus,
    BusinessCaseRunner,
    CaseAssertion,
    CaseExecution,
    CaseRef,
    ExecutedCase,
    ReceiptRef,
)
from quwoquan_ops.cli.lib.test_data.cases import canonical_acceptance_suite
from quwoquan_ops.cli.lib.test_data.capabilities.assistant_service import (
    ASSISTANT_PROMPT_RUN,
)
from quwoquan_ops.cli.lib.test_data.capabilities.common import (
    AcceptanceActorSet,
    ActorRole,
)
from quwoquan_ops.cli.lib.test_data.capabilities.user_service import (
    AUTHENTICATED_ACTORS,
    AuthenticatedActorsParams,
)
from quwoquan_ops.cli.lib.test_data.serialization import (
    case_request_document,
    collect_request_graph,
    load_case_requests,
    request_graph_document,
)
from quwoquan_ops.cli.lib.test_data_verification import (
    build_candidate_binding,
    build_provider_evidence_document,
    load_provider_evidence,
    run_test_data_verification,
)


def _manifest() -> dict[str, object]:
    return {
        "baselineId": "sha256:" + "1" * 64,
        "packageDigest": "sha256:" + "2" * 64,
        "runtimeConfigDigest": "sha256:" + "3" * 64,
        "release": {
            "candidate": {
                "releaseId": "release-1",
                "releaseDigest": "sha256:" + "4" * 64,
            }
        },
    }


def _readiness() -> dict[str, object]:
    return {
        "passed": True,
        "environment": "gamma",
        "releaseId": "release-1",
        "manifestDigest": "sha256:" + "4" * 64,
        "importRunId": "import-1",
        "postIds": ["post-1"],
    }


class VerificationCaseId(StrEnum):
    ACTORS_READY = "actors-ready"
    ACTORS_READY_2 = "actors-ready-2"
    ACTORS_READY_3 = "actors-ready-3"
    ACTORS_READY_4 = "actors-ready-4"


class ActorsReadyBusinessCase(BusinessCaseRunner[AcceptanceActorSet]):
    result_type = AcceptanceActorSet

    @classmethod
    def execute(cls, value, context):
        return CaseExecution(
            (CaseAssertion("actor-authenticated", AssertionStatus.PASSED),)
        )


class _Session:
    def __init__(self, receipt: ReceiptRef) -> None:
        self._receipt = receipt

    def execute(self, case):
        return ExecutedCase(
            case_id=str(case.case_id.value),
            execution=CaseExecution(
                (CaseAssertion("actor-authenticated", AssertionStatus.PASSED),)
            ),
            provision_receipt=self._receipt,
            test_body_receipt=ReceiptRef(
                self._receipt.path.with_name("test-body.json"),
                "sha256:" + "b" * 64,
            ),
        )


class _ParallelSession:
    def __init__(self, tracker: "_ParallelTracker", receipt: ReceiptRef) -> None:
        self._tracker = tracker
        self._receipt = receipt

    def execute(self, case):
        self._tracker.enter()
        try:
            return _Session(self._receipt).execute(case)
        finally:
            self._tracker.exit()


class _ParallelTracker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._overlap = Event()
        self.active = 0
        self.peak = 0

    def enter(self) -> None:
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            if self.active >= 2:
                self._overlap.set()
        if not self._overlap.wait(timeout=1):
            raise RuntimeError("selected roots did not overlap")

    def exit(self) -> None:
        with self._lock:
            self.active -= 1


def _run_summary(*, executed: int = 1) -> tuple[dict[str, object], ...]:
    return (
        {
            "loadedProviders": ["user_service"],
            "requiredProviders": ["user_service"],
            "operationCount": 2 * executed,
            "executed": executed,
            "dataPreparationMs": 1,
            "criticalPathMs": 1,
            "maxObservedConcurrency": min(executed, 4),
        },
    )


class TestDataVerificationContractTest(unittest.TestCase):
    def test_provider_evidence_uses_canonical_ids_and_exact_request_closure(
        self,
    ) -> None:
        candidate = build_candidate_binding(
            environment="gamma",
            target="gamma-local",
            manifest=_manifest(),
            readiness=_readiness(),
        )
        request_document = case_request_document(
            (canonical_acceptance_suite()[0],)
        )
        identity_provider_capability = (
            AUTHENTICATED_ACTORS.required_provider_capabilities[0].value
        )
        assistant_provider_capability = (
            ASSISTANT_PROMPT_RUN.required_provider_capabilities[0].value
        )
        readiness_report = {
            "schema": "provider-conformance-readiness",
            "sourceCoverageIssues": [],
            "readiness": {
                "gamma": {
                    identity_provider_capability: {
                        "adapter_id": "ext.sms.local_capture",
                        "capability_ready": True,
                        "provider_conformance_required": True,
                    },
                    assistant_provider_capability: {
                        "adapter_id": "ext.llm.protocol_fixture",
                        "capability_ready": False,
                        "provider_conformance_required": True,
                    },
                }
            },
        }
        evidence = build_provider_evidence_document(
            request_document=request_document,
            candidate=candidate,
            readiness_report=readiness_report,
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evidence.json"
            path.write_text(json.dumps(evidence), encoding="utf-8")
            loaded = load_provider_evidence(
                path,
                candidate,
                request_digest=str(request_document["requestDigest"]),
                required_capabilities=(identity_provider_capability,),
            )

        self.assertEqual(set(loaded), {identity_provider_capability})
        self.assertNotIn(assistant_provider_capability, loaded)

        blocked = {
            **readiness_report,
            "readiness": {
                "gamma": {
                    identity_provider_capability: {
                        "adapter_id": "ext.sms.local_capture",
                        "capability_ready": False,
                        "provider_conformance_required": True,
                    }
                }
            },
        }
        with self.assertRaisesRegex(RuntimeError, identity_provider_capability):
            build_provider_evidence_document(
                request_document=request_document,
                candidate=candidate,
                readiness_report=blocked,
            )

    def test_release_accepts_only_the_canonical_typed_journey_set(self) -> None:
        canonical = case_request_document(canonical_acceptance_suite())
        stackctl._validate_test_data_request_for_profile(
            stackctl.VerificationProfile.RELEASE,
            canonical,
        )

        focused = case_request_document((canonical_acceptance_suite()[0],))
        with self.assertRaisesRegex(ValueError, "canonical seven-domain"):
            stackctl._validate_test_data_request_for_profile(
                stackctl.VerificationProfile.RELEASE,
                focused,
            )
        stackctl._validate_test_data_request_for_profile(
            stackctl.VerificationProfile.INTEGRATION,
            focused,
        )

    def test_stackctl_generates_the_typed_canonical_request_without_manual_json(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            args = stackctl.build_parser().parse_args(
                ["test-data-request", "--report-dir", temporary]
            )
            result = stackctl.command_test_data_request(args)
            document = json.loads(
                (Path(temporary) / "request.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(len(document["cases"]), 7)
        self.assertEqual(len(document["requests"]), 17)
        self.assertEqual(result["requestPath"], str(Path(temporary) / "request.json"))

    def test_stackctl_projects_only_selected_current_provider_evidence(self) -> None:
        document = case_request_document(canonical_acceptance_suite())
        required_capabilities = sorted(
            {
                provider_key.value
                for case in canonical_acceptance_suite()
                for request in collect_request_graph((case.request,)).values()
                for provider_key in request.capability.required_provider_capabilities
            }
        )
        readiness_report = {
            "schema": "provider-conformance-readiness",
            "sourceCoverageIssues": [],
            "readiness": {
                "gamma": {
                    capability_id: {
                        "adapter_id": "ext.test.current",
                        "capability_ready": True,
                        "provider_conformance_required": True,
                    }
                    for capability_id in required_capabilities
                }
            },
        }
        provider_conformance = mock.Mock()
        provider_conformance.load_validate_and_derive.return_value = (
            readiness_report,
            ["an unselected global Provider issue"],
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path = root / "request.json"
            request_path.write_text(json.dumps(document), encoding="utf-8")
            report_dir = root / "evidence"
            args = stackctl.build_parser().parse_args(
                [
                    "test-data-evidence",
                    "--env",
                    "gamma",
                    "--target",
                    "gamma-local",
                    "--data-release-id",
                    "release-1",
                    "--data-verify-run-id",
                    "verify-1",
                    "--data-manifest-digest",
                    "sha256:" + "4" * 64,
                    "--test-data-request",
                    str(request_path),
                    "--report-dir",
                    str(report_dir),
                ]
            )
            with (
                mock.patch.object(
                    stackctl,
                    "active_deployment_candidate",
                    return_value={"baselineId": _manifest()["baselineId"]},
                ),
                mock.patch.object(
                    stackctl,
                    "load_candidate_manifest",
                    return_value=_manifest(),
                ),
                mock.patch.object(
                    stackctl,
                    "_load_test_data_release_readiness",
                    return_value=(_readiness(), root / "readiness.json"),
                ),
                mock.patch.object(
                    stackctl,
                    "_provider_conformance",
                    return_value=provider_conformance,
                ),
                mock.patch.object(stackctl, "output_root", return_value=root),
            ):
                result = stackctl.command_test_data_evidence(args)
            evidence = json.loads(
                (report_dir / "evidence.json").read_text(encoding="utf-8")
            )
            summary = json.loads(
                (report_dir / "report.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(
            sorted(evidence["providerConformance"]),
            required_capabilities,
        )
        self.assertEqual(summary["providerReadinessIssueCount"], 1)

    def test_test_data_readiness_uses_the_receipt_lifecycle_validator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt_path = Path(temporary) / "release-readiness.json"
            receipt_path.write_text(
                json.dumps({"readinessPhase": "research"}),
                encoding="utf-8",
            )
            strict_loader = mock.Mock(return_value=(_readiness(), receipt_path))
            with (
                mock.patch.object(
                    stackctl,
                    "_data_release_readiness_path",
                    return_value=receipt_path,
                ),
                mock.patch.object(
                    stackctl,
                    "_load_data_release_readiness",
                    strict_loader,
                ),
            ):
                loaded, loaded_path = stackctl._load_test_data_release_readiness(
                    environment="gamma",
                    release_id="release-1",
                    verify_run_id="verify-1",
                    manifest_digest="sha256:" + "4" * 64,
                )

        self.assertEqual(loaded, _readiness())
        self.assertEqual(loaded_path, receipt_path)
        self.assertIs(
            strict_loader.call_args.kwargs["readiness_phase"],
            stackctl.ReadinessPhase.RESEARCH,
        )

    def test_parser_exposes_only_typed_test_data_handoff(self) -> None:
        args = stackctl.build_parser().parse_args(
            [
                "verify",
                "--target",
                "gamma-local",
                "--profile",
                "integration",
                "--test-data-request",
                "request.json",
                "--test-data-evidence",
                "evidence.json",
            ]
        )
        self.assertEqual(args.test_data_request, "request.json")
        self.assertEqual(args.test_data_evidence, "evidence.json")
        self.assertNotIn("nonprod-data-evidence", stackctl.build_parser().format_help())

    def test_request_graph_without_business_case_is_rejected_before_mutation(
        self,
    ) -> None:
        request = AUTHENTICATED_ACTORS.bind(
            AuthenticatedActorsParams((ActorRole.SENDER,))
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path = root / "request.json"
            request_path.write_text(
                json.dumps(request_graph_document((request,))),
                encoding="utf-8",
            )
            with mock.patch(
                "quwoquan_ops.cli.lib.test_data_verification.TestDataSession.for_case",
                side_effect=AssertionError("Session must not start"),
            ):
                blocked = run_test_data_verification(
                    environment="gamma",
                    target="gamma-local",
                    base_url="https://gamma.local.quwoquan.invalid",
                    candidate_manifest=_manifest(),
                    release_readiness=_readiness(),
                    request_path=request_path,
                    evidence_path=None,
                    report_dir=root / "blocked-request",
                    static_gate_ms=17,
                )
            self.assertEqual(blocked["status"], "GATE_BLOCK")
            self.assertEqual(blocked["preparationStatus"], "GATE_BLOCK")
            self.assertFalse(blocked["baselineEligible"])
            self.assertEqual(blocked["preparedRequestCount"], 0)
            self.assertEqual(blocked["executed"], 0)
            self.assertEqual(blocked["caseResults"], [])

    def test_prod_request_is_rejected_before_package_provider_or_operation(self) -> None:
        args = stackctl.build_parser().parse_args(
            [
                "verify",
                "--target",
                "prod-hosted",
                "--profile",
                "integration",
                "--test-data-request",
                "must-not-be-read.json",
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "can_reuse_package",
                    side_effect=AssertionError("package must not be inspected"),
                ),
                mock.patch.object(
                    stackctl,
                    "_run_provider_readiness_preflight",
                    side_effect=AssertionError("Provider must not be discovered"),
                ),
            ):
                result = stackctl.command_verify(args)
            case_result = json.loads(
                (report_dir / "test-data/case-result.json").read_text(
                    encoding="utf-8"
                )
            )
        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(case_result["status"], "GATE_BLOCK")
        self.assertEqual(case_result["operationCount"], 0)
        self.assertEqual(case_result["loadedProviders"], [])

    def test_business_case_executes_inside_session_and_is_baseline_eligible(
        self,
    ) -> None:
        request = AUTHENTICATED_ACTORS.bind(
            AuthenticatedActorsParams((ActorRole.SENDER,))
        )
        case = CaseRef(
            case_id=VerificationCaseId.ACTORS_READY,
            request=request,
            runner_type=ActorsReadyBusinessCase,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path = root / "request.json"
            request_path.write_text(
                json.dumps(case_request_document((case,))),
                encoding="utf-8",
            )
            receipt = ReceiptRef(root / "receipt.json", "sha256:" + "a" * 64)
            with (
                mock.patch(
                    "quwoquan_ops.cli.lib.test_data_verification.TestDataSession.for_case",
                    return_value=_Session(receipt),
                ),
                mock.patch(
                    "quwoquan_ops.cli.lib.test_data_verification._load_run_summaries",
                    return_value=_run_summary(),
                ),
                mock.patch(
                    "quwoquan_ops.cli.lib.test_data_verification.load_provider_evidence",
                    return_value={},
                ),
            ):
                passed = run_test_data_verification(
                    environment="gamma",
                    target="gamma-local",
                    base_url="https://gamma.local.quwoquan.invalid",
                    candidate_manifest=_manifest(),
                    release_readiness=_readiness(),
                    request_path=request_path,
                    evidence_path=None,
                    report_dir=root / "passed",
                    static_gate_ms=17,
                )
            self.assertEqual(passed["status"], "passed")
            self.assertEqual(passed["preparationStatus"], "passed")
            self.assertTrue(passed["baselineEligible"])
            self.assertEqual(passed["preparedRequestCount"], 1)
            self.assertEqual(passed["executed"], 1)
            self.assertEqual(passed["caseResults"][0]["status"], "passed")
            self.assertEqual(len(passed["preparationResults"]), 1)
            self.assertEqual(passed["staticGateMs"], 17)
            self.assertEqual(passed["environmentStartSource"], "prestarted-environment")
            self.assertEqual(passed["loadedProviders"], ["user_service"])
            self.assertEqual(passed["requiredProviders"], ["user_service"])
            self.assertRegex(passed["machineFingerprint"], r"^sha256:[0-9a-f]{64}$")

            blocked_readiness = {**_readiness(), "passed": False}
            blocked = run_test_data_verification(
                environment="gamma",
                target="gamma-local",
                base_url="https://gamma.local.quwoquan.invalid",
                candidate_manifest=_manifest(),
                release_readiness=blocked_readiness,
                request_path=request_path,
                evidence_path=None,
                report_dir=root / "blocked-readiness",
            )
            self.assertEqual(blocked["status"], "GATE_BLOCK")
            self.assertFalse(blocked["baselineEligible"])
            self.assertEqual(blocked["executed"], 0)

    def test_independent_roots_overlap_and_keep_request_order(self) -> None:
        requests = tuple(
            AUTHENTICATED_ACTORS.bind(
                AuthenticatedActorsParams((ActorRole.SENDER,))
            )
            for _ in range(4)
        )
        case_ids = (
            VerificationCaseId.ACTORS_READY,
            VerificationCaseId.ACTORS_READY_2,
            VerificationCaseId.ACTORS_READY_3,
            VerificationCaseId.ACTORS_READY_4,
        )
        cases = tuple(
            CaseRef(
                case_id=case_id,
                request=request,
                runner_type=ActorsReadyBusinessCase,
            )
            for case_id, request in zip(case_ids, requests)
        )
        serialized_cases = load_case_requests(case_request_document(cases))
        tracker = _ParallelTracker()
        session_index = 0
        session_lock = Lock()

        def session_for_case(*args, **kwargs):
            nonlocal session_index
            with session_lock:
                index = session_index
                session_index += 1
            return _ParallelSession(
                tracker,
                ReceiptRef(
                    Path(f"receipt-{index}.json"),
                    "sha256:" + f"{index + 1:x}" * 64,
                ),
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path = root / "request.json"
            request_path.write_text(
                json.dumps(case_request_document(cases)),
                encoding="utf-8",
            )
            with (
                mock.patch(
                    "quwoquan_ops.cli.lib.test_data_verification.TestDataSession.for_case",
                    side_effect=session_for_case,
                ),
                mock.patch(
                    "quwoquan_ops.cli.lib.test_data_verification._load_run_summaries",
                    return_value=_run_summary(executed=4),
                ),
                mock.patch(
                    "quwoquan_ops.cli.lib.test_data_verification.load_provider_evidence",
                    return_value={},
                ),
            ):
                result = run_test_data_verification(
                    environment="gamma",
                    target="gamma-local",
                    base_url="https://gamma.local.quwoquan.invalid",
                    candidate_manifest=_manifest(),
                    release_readiness=_readiness(),
                    request_path=request_path,
                    evidence_path=None,
                    report_dir=root / "parallel",
                )

        self.assertEqual(result["preparationStatus"], "passed")
        self.assertEqual(result["preparedRequestCount"], 4)
        self.assertEqual(result["rootWorkerCount"], 4)
        self.assertGreaterEqual(result["dataPreparationMs"], 0)
        self.assertEqual(
            result["dataPreparationMs"], result["caseSessionWallMs"]
        )
        self.assertEqual(result["maxCaseDataPreparationMs"], 1)
        self.assertGreaterEqual(
            result["dataPreparationMs"], result["criticalPathMs"]
        )
        self.assertGreaterEqual(tracker.peak, 2)
        self.assertLessEqual(tracker.peak, 4)
        self.assertEqual(
            [item["requestId"] for item in result["preparationResults"]],
            [case.request.request_id.value for case in serialized_cases],
        )
        self.assertEqual(result["executed"], 4)
        self.assertTrue(result["baselineEligible"])

    def test_unrequested_loaded_provider_blocks_baseline(self) -> None:
        request = AUTHENTICATED_ACTORS.bind(
            AuthenticatedActorsParams((ActorRole.SENDER,))
        )
        case = CaseRef(
            case_id=VerificationCaseId.ACTORS_READY,
            request=request,
            runner_type=ActorsReadyBusinessCase,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path = root / "request.json"
            request_path.write_text(
                json.dumps(case_request_document((case,))),
                encoding="utf-8",
            )
            summary = dict(_run_summary()[0])
            summary["loadedProviders"] = ["rtc_service", "user_service"]
            with (
                mock.patch(
                    "quwoquan_ops.cli.lib.test_data_verification.TestDataSession.for_case",
                    return_value=_Session(
                        ReceiptRef(root / "receipt.json", "sha256:" + "a" * 64)
                    ),
                ),
                mock.patch(
                    "quwoquan_ops.cli.lib.test_data_verification._load_run_summaries",
                    return_value=(summary,),
                ),
                mock.patch(
                    "quwoquan_ops.cli.lib.test_data_verification.load_provider_evidence",
                    return_value={},
                ),
            ):
                result = run_test_data_verification(
                    environment="gamma",
                    target="gamma-local",
                    base_url="https://gamma.local.quwoquan.invalid",
                    candidate_manifest=_manifest(),
                    release_readiness=_readiness(),
                    request_path=request_path,
                    evidence_path=None,
                    report_dir=root / "extra-provider",
                )
        self.assertEqual(result["status"], "GATE_BLOCK")
        self.assertFalse(result["baselineEligible"])
        self.assertIn("selected request closure", result["issues"][0])


if __name__ == "__main__":
    unittest.main()
