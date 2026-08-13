"""test-data 会话执行、请求图闭合与 baseline 资格合约。

spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t3
spec_ref: specs/feature-tree/runtime/runtime-testinfra/test-data-provisioning-and-isolation/spec.md#gwt-001
"""
from __future__ import annotations

from quwoquan_ops.tests.support.test_data_verification_test_support import (
    AUTHENTICATED_ACTORS,
    ActorRole,
    ActorsReadyBusinessCase,
    AuthenticatedActorsParams,
    CaseRef,
    Lock,
    Path,
    ReceiptRef,
    VerificationCaseId,
    _FailedSession,
    _ParallelSession,
    _ParallelTracker,
    _Session,
    _manifest,
    _readiness,
    _run_summary,
    build_candidate_binding,
    build_provider_evidence_document,
    build_test_data_handoff,
    case_request_document,
    json,
    load_case_requests,
    mock,
    request_graph_document,
    run_test_data_verification,
    stackctl,
    tempfile,
    unittest,
)


class TestDataSessionBaselineContractTest(unittest.TestCase):
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
            request_document = case_request_document((case,))
            request_path.write_text(
                json.dumps(request_document),
                encoding="utf-8",
            )
            candidate = build_candidate_binding(
                environment="gamma",
                target="gamma-local",
                manifest=_manifest(),
                readiness=_readiness(),
            )
            provider_capability = (
                AUTHENTICATED_ACTORS.required_provider_capabilities[0].value
            )
            evidence = build_provider_evidence_document(
                request_document=request_document,
                candidate=candidate,
                readiness_report={
                    "schema": "provider-conformance-readiness",
                    "sourceCoverageIssues": [],
                    "readiness": {
                        "gamma": {
                            provider_capability: {
                                "adapter_id": "ext.sms.local_capture",
                                "capability_ready": True,
                                "provider_conformance_required": True,
                            }
                        }
                    },
                },
            )
            evidence_path = root / "evidence.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            handoff = build_test_data_handoff(
                candidate=candidate,
                readiness=_readiness(),
                request_document=request_document,
                evidence=evidence,
            )
            handoff_path = root / "handoff.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            receipt = ReceiptRef(
                root / "passed" / "receipt.json",
                "sha256:" + "a" * 64,
            )
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
                    evidence_path=evidence_path,
                    report_dir=root / "passed",
                    handoff_path=handoff_path,
                    static_gate_ms=17,
                )
            self.assertEqual(passed["status"], "passed")
            self.assertEqual(passed["preparationStatus"], "passed")
            self.assertTrue(passed["baselineEligible"])
            self.assertEqual(passed["preparedRequestCount"], 1)
            self.assertEqual(passed["executed"], 1)
            self.assertEqual(passed["caseResults"][0]["status"], "passed")
            self.assertEqual(
                passed["caseResults"][0]["provisionReceiptPath"],
                "receipt.json",
            )
            self.assertEqual(
                passed["caseResults"][0]["testBodyReceiptPath"],
                "test-body.json",
            )
            self.assertEqual(
                passed["caseResults"][0]["readbackReceiptPaths"],
                ["readback.json"],
            )
            self.assertEqual(
                passed["caseResults"][0]["cleanupReceiptPaths"],
                ["cleanup.json"],
            )
            self.assertEqual(len(passed["preparationResults"]), 1)
            self.assertEqual(passed["staticGateMs"], 17)
            self.assertEqual(passed["environmentStartSource"], "prestarted-environment")
            self.assertEqual(passed["benchmarkPolicy"], "normal")
            self.assertFalse(passed["benchmarkOnly"])
            self.assertEqual(passed["evidenceDigest"], evidence["evidenceDigest"])
            self.assertEqual(passed["handoffDigest"], handoff["handoffDigest"])
            self.assertEqual(passed["executedOperationIds"], [])
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

    def test_business_failure_never_promotes_successful_preparation_to_baseline(
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
            receipt = ReceiptRef(
                root / "failed-business" / "receipt.json",
                "sha256:" + "a" * 64,
            )
            with (
                mock.patch(
                    "quwoquan_ops.cli.lib.test_data_verification.TestDataSession.for_case",
                    return_value=_FailedSession(receipt),
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
                result = run_test_data_verification(
                    environment="gamma",
                    target="gamma-local",
                    base_url="https://gamma.local.quwoquan.invalid",
                    candidate_manifest=_manifest(),
                    release_readiness=_readiness(),
                    request_path=request_path,
                    evidence_path=None,
                    report_dir=root / "failed-business",
                )

        self.assertEqual(result["preparationStatus"], "passed")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["executed"], 1)
        self.assertFalse(result["baselineEligible"])
        self.assertEqual(result["caseResults"][0]["status"], "failed")

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
                    kwargs["context"].output_root / f"receipt-{index}.json",
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
                        ReceiptRef(
                            root / "extra-provider" / "receipt.json",
                            "sha256:" + "a" * 64,
                        )
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

