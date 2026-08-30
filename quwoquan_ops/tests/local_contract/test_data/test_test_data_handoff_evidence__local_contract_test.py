"""stackctl typed test-data handoff 与 provider evidence 合约。

spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t3
spec_ref: specs/feature-tree/runtime/runtime-testinfra/test-data-provisioning-and-isolation/spec.md#gwt-001
"""
from __future__ import annotations

from quwoquan_ops.tests.support.test_data_verification_test_support import (
    ASSISTANT_PROMPT_RUN,
    AUTHENTICATED_ACTORS,
    Path,
    _manifest,
    _readiness,
    _with_checksum,
    build_candidate_binding,
    build_provider_evidence_document,
    build_test_data_handoff,
    canonical_acceptance_suite,
    canonical_digest,
    case_request_document,
    collect_request_graph,
    json,
    load_provider_evidence,
    load_test_data_handoff,
    mock,
    stackctl,
    tempfile,
    unittest,
)


class TestDataHandoffEvidenceContractTest(unittest.TestCase):
    def test_handoff_freezes_exact_candidate_request_evidence_and_operation_closure(
        self,
    ) -> None:
        candidate = build_candidate_binding(
            environment="gamma",
            target="gamma-local",
            manifest=_manifest(),
            readiness=_readiness(),
        )
        request_document = case_request_document(canonical_acceptance_suite())
        provider_capabilities = {
            provider_key.value
            for case in canonical_acceptance_suite()
            for request in collect_request_graph((case.request,)).values()
            for provider_key in request.capability.required_provider_capabilities
        }
        readiness_report = {
            "schema": "provider-conformance-readiness",
            "sourceCoverageIssues": [],
            "readiness": {
                "gamma": {
                    capability: {
                        "capability_ready": True,
                        "provider_conformance_required": True,
                        "adapter_id": f"adapter-{index}",
                    }
                    for index, capability in enumerate(
                        sorted(provider_capabilities),
                        start=1,
                    )
                }
            },
        }
        evidence = build_provider_evidence_document(
            request_document=request_document,
            candidate=candidate,
            readiness_report=readiness_report,
        )

        handoff = build_test_data_handoff(
            candidate=candidate,
            readiness=_readiness(),
            request_document=request_document,
            evidence=evidence,
        )

        self.assertEqual(handoff["environment"], "gamma")
        self.assertEqual(handoff["target"], "gamma-local")
        self.assertEqual(handoff["sourceRevision"], "a" * 40)
        self.assertEqual(handoff["candidateBindingDigest"], candidate.digest)
        self.assertEqual(handoff["requestDigest"], request_document["requestDigest"])
        self.assertEqual(handoff["evidenceDigest"], evidence["evidenceDigest"])
        self.assertEqual(len(handoff["expectedCases"]), 15)
        self.assertEqual(
            handoff["expectedProviderOwners"],
            [
                "assistant_service",
                "chat_service",
                "circle_service",
                "content_service",
                "notification_service",
                "rtc_service",
                "user_service",
            ],
        )
        self.assertIn(
            "chat.message.RecallMessage",
            handoff["allowedOperations"],
        )
        self.assertTrue(str(handoff["handoffDigest"]).startswith("sha256:"))
        with tempfile.TemporaryDirectory() as temporary:
            handoff_path = Path(temporary) / "handoff.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            loaded = load_test_data_handoff(
                handoff_path,
                candidate=candidate,
                readiness=_readiness(),
                request_document=request_document,
                evidence=evidence,
            )
            self.assertEqual(loaded["handoffDigest"], handoff["handoffDigest"])
            handoff_path.write_text(
                json.dumps({**handoff, "evidenceDigest": "sha256:" + "f" * 64}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "exact candidate/request/evidence"):
                load_test_data_handoff(
                    handoff_path,
                    candidate=candidate,
                    readiness=_readiness(),
                    request_document=request_document,
                    evidence=evidence,
                )

    def test_handoff_rejects_readiness_without_explicit_source_revision(self) -> None:
        candidate = build_candidate_binding(
            environment="gamma",
            target="gamma-local",
            manifest=_manifest(),
            readiness=_readiness(),
        )
        request_document = case_request_document(canonical_acceptance_suite())
        evidence = {
            "schema": "qwq.test_data_evidence.v1",
            "environment": "gamma",
            "target": "gamma-local",
            "candidateBindingDigest": candidate.digest,
            "requestDigest": request_document["requestDigest"],
            "providerReadinessDigest": "sha256:" + "a" * 64,
            "providerConformance": {},
        }
        evidence["evidenceDigest"] = canonical_digest(evidence)
        readiness = _readiness()
        readiness.pop("sourceRevision")
        readiness = _with_checksum(readiness)

        with self.assertRaisesRegex(ValueError, "sourceRevision"):
            build_test_data_handoff(
                candidate=candidate,
                readiness=readiness,
                request_document=request_document,
                evidence=evidence,
            )

    def test_candidate_binding_accepts_source_identities_readiness(self) -> None:
        """新 Data 溯源模型：readiness 以 sourceIdentities/
        sourceIdentitySetDigest 表达来源，顶层 sourceRevision 已退役。"""
        readiness = _readiness()
        readiness.pop("sourceRevision")
        readiness["sourceIdentities"] = [
            {"owner": "content", "revision": "c" * 40}
        ]
        readiness["sourceIdentitySetDigest"] = "sha256:" + "5" * 64
        readiness = _with_checksum(readiness)

        candidate = build_candidate_binding(
            environment="gamma",
            target="gamma-local",
            manifest=_manifest(),
            readiness=readiness,
        )
        self.assertEqual(candidate.source_revision, "a" * 40)

        request_document = case_request_document(canonical_acceptance_suite())
        evidence = {
            "schema": "qwq.test_data_evidence.v1",
            "environment": "gamma",
            "target": "gamma-local",
            "candidateBindingDigest": candidate.digest,
            "requestDigest": request_document["requestDigest"],
            "providerReadinessDigest": "sha256:" + "a" * 64,
            "providerConformance": {},
        }
        evidence["evidenceDigest"] = canonical_digest(evidence)
        handoff = build_test_data_handoff(
            candidate=candidate,
            readiness=readiness,
            request_document=request_document,
            evidence=evidence,
        )
        self.assertEqual(handoff["sourceRevision"], "a" * 40)

    def test_candidate_binding_rejects_source_identities_without_set_digest(
        self,
    ) -> None:
        readiness = _readiness()
        readiness.pop("sourceRevision")
        readiness["sourceIdentities"] = [
            {"owner": "content", "revision": "c" * 40}
        ]
        readiness = _with_checksum(readiness)

        with self.assertRaisesRegex(ValueError, "sourceRevision"):
            build_candidate_binding(
                environment="gamma",
                target="gamma-local",
                manifest=_manifest(),
                readiness=readiness,
            )

    def test_candidate_binding_contains_a_complete_receipt_bound_release_closure(
        self,
    ) -> None:
        candidate = build_candidate_binding(
            environment="gamma",
            target="gamma-local",
            manifest=_manifest(),
            readiness=_readiness(),
        )

        self.assertEqual(candidate.readiness_phase, "research")
        self.assertEqual(candidate.readiness_receipt_digest, _readiness()["verificationChecksum"])
        self.assertEqual(
            tuple(item.object_id for item in candidate.release_posts),
            ("post-1",),
        )
        self.assertEqual(
            tuple(item.object_type for item in candidate.release_homepages),
            ("EntityHomepage",),
        )
        self.assertNotEqual(candidate.digest, "sha256:" + "0" * 64)

    def test_candidate_binding_rejects_lifecycle_checksum_and_closure_drift(
        self,
    ) -> None:
        for label, readiness in (
            (
                "phase",
                _with_checksum({**_readiness(), "readinessPhase": "consumer"}),
            ),
            (
                "lifecycle",
                _with_checksum({**_readiness(), "releaseClass": "commercial"}),
            ),
            (
                "closure",
                _with_checksum({**_readiness(), "mediaAssetIds": []}),
            ),
            (
                "source",
                _with_checksum({**_readiness(), "sourceRevision": "b" * 40}),
            ),
            ("checksum", {**_readiness(), "verificationChecksum": "sha256:" + "0" * 64}),
        ):
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    build_candidate_binding(
                        environment="gamma",
                        target="gamma-local",
                        manifest=_manifest(),
                        readiness=readiness,
                    )

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
        self.assertEqual(len(document["cases"]), 15)
        self.assertEqual(len(document["requests"]), 39)
        self.assertEqual(result["requestPath"], str(Path(temporary) / "request.json"))

    def test_evidence_rejects_stale_typed_request_before_environment_owner_reads(
        self,
    ) -> None:
        document = case_request_document(canonical_acceptance_suite())
        document["cases"][0][
            "runnerModule"
        ] = "quwoquan_ops.cli.lib.test_data.cases.canonical"
        document["cases"][0]["runnerType"] = "RetiredUserRelationshipCase"
        unsigned = {
            key: value for key, value in document.items() if key != "requestDigest"
        }
        document["requestDigest"] = canonical_digest(unsigned)
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
                    "release-must-not-be-read",
                    "--data-verify-run-id",
                    "verify-must-not-be-read",
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
                    side_effect=AssertionError("candidate must not be read"),
                ),
                mock.patch.object(
                    stackctl,
                    "_load_test_data_release_readiness",
                    side_effect=AssertionError("Data readiness must not be read"),
                ),
                mock.patch.object(
                    stackctl,
                    "_provider_conformance",
                    side_effect=AssertionError("Provider readiness must not be read"),
                ),
                mock.patch.object(stackctl, "output_root", return_value=root),
            ):
                result = stackctl.command_test_data_evidence(args)
            summary = json.loads(
                (report_dir / "report.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(summary["status"], "GATE_BLOCK")
        self.assertIn("RetiredUserRelationshipCase", summary["issues"][0])
        self.assertFalse((report_dir / "evidence.json").exists())
        self.assertFalse((report_dir / "handoff.json").exists())

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
                "--test-data-handoff",
                "handoff.json",
            ]
        )
        self.assertEqual(args.test_data_request, "request.json")
        self.assertEqual(args.test_data_evidence, "evidence.json")
        self.assertEqual(args.test_data_handoff, "handoff.json")
        self.assertNotIn("nonprod-data-evidence", stackctl.build_parser().format_help())

