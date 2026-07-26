# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from quwoquan_ops.ci.provider_conformance import b10_prod_remote_uat
from quwoquan_ops.ci.provider_conformance import run_b10_prod_remote_patrol_uat
from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib import provider_conformance


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = (
    ROOT
    / "quwoquan_ops"
    / "environments"
    / "provider_conformance_evidence.schema.json"
)


class ProviderConformanceEvidenceContractTest(unittest.TestCase):
    def test_schema_is_evidence_only_and_fail_closed(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["properties"]["environment"]["enum"],
            ["alpha", "beta", "gamma", "prod"],
        )
        self.assertEqual(
            schema["properties"]["testLayer"]["enum"],
            ["local_contract", "api_integration", "user_acceptance"],
        )
        self.assertEqual(schema["properties"]["version"]["const"], 4)
        for required in (
            "adapterId",
            "capabilityId",
            "artifactRef",
            "artifactDigest",
            "artifactAttestation",
            "testArtifactRef",
            "testArtifactDigest",
            "testSource",
            "testSourceDigest",
            "testCommand",
            "testTarget",
            "typedPort",
            "contractRef",
            "commit",
            "imageDigest",
            "configDigest",
            "contractGraphDigest",
            "assertionCount",
            "assertionIds",
            "observabilityRefs",
        ):
            self.assertIn(required, schema["required"])

    def test_adapter_digest_covers_directory_paths_and_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source_root = Path(temporary)
            first = source_root / "adapter.go"
            first.write_text("package adapter\n", encoding="utf-8")
            initial = provider_conformance.implementation_digest(source_root)

            first.write_text("package adapter\nconst Version = 2\n", encoding="utf-8")
            content_changed = provider_conformance.implementation_digest(source_root)
            first.rename(source_root / "renamed_adapter.go")
            path_changed = provider_conformance.implementation_digest(source_root)

        self.assertIsNotNone(initial)
        self.assertNotEqual(initial, content_changed)
        self.assertNotEqual(content_changed, path_changed)

    def test_empty_evidence_cannot_satisfy_release_readiness(self) -> None:
        report = {
            "schema": "provider-conformance-readiness",
            "version": 1,
            "evidenceCount": 0,
            "readiness": {},
            "issues": [],
        }
        for environment in ("gamma", "prod"):
            issues = provider_conformance.readiness_issues(
                report, environment=environment
            )
            self.assertTrue(any("zero Provider Conformance evidence" in issue for issue in issues))

    def test_only_prod_remote_receipts_require_release_readiness(self) -> None:
        self.assertEqual(
            provider_conformance.execution_profile_for("prod", "user_acceptance"),
            "release",
        )
        self.assertIsNone(
            provider_conformance.execution_profile_for("prod", "api_integration")
        )
        self.assertEqual(
            provider_conformance.execution_profile_for("gamma", "user_acceptance"),
            "release",
        )
        self.assertFalse(
            provider_conformance.requires_release_readiness(
                "gamma",
                "user_acceptance",
            )
        )
        self.assertTrue(
            provider_conformance.requires_release_readiness(
                "prod",
                "user_acceptance",
            )
        )
        self.assertFalse(
            provider_conformance.requires_release_readiness(
                "beta",
                "user_acceptance",
            )
        )

    def test_release_assertions_do_not_change_nine_cell_base_semantics(self) -> None:
        base = {
            "assertionIds": sorted(provider_conformance.PUBLIC_ASSERTION_IDS),
        }
        release = {
            "assertionIds": sorted(
                provider_conformance.PUBLIC_ASSERTION_IDS
                | provider_conformance.RELEASE_ASSERTION_IDS
            ),
        }
        self.assertEqual(
            provider_conformance._assertion_semantics(base),
            provider_conformance._assertion_semantics(release),
        )

    def test_b10_prod_remote_sources_are_discovered(self) -> None:
        sources, issues = provider_conformance.discover_test_sources()
        self.assertEqual(issues, [])
        self.assertEqual(
            sources[
                ("rtc.room.transport", "infra.livekit_sfu", "user_acceptance")
            ]["target"],
            "b10-remote-rtc.room.transport",
        )
        self.assertEqual(
            sources[
                ("integration.push.delivery", "ext.push.dispatch", "user_acceptance")
            ]["target"],
            "b10-remote-integration.push.delivery",
        )
        self.assertEqual(
            sources[
                (
                    "runtime.message.transport",
                    "infra.redis.message_transport",
                    "user_acceptance",
                )
            ]["target"],
            "b10-remote-runtime.message.transport",
        )

    def test_b10_remote_readback_requires_both_device_directions(self) -> None:
        environment = {
            "QWQ_B10_IOS_DEVICE_ID": "ios-device",
            "QWQ_B10_ANDROID_DEVICE_ID": "android-device",
        }
        evidence = [
            {
                "platform": "ios",
                "deviceHash": b10_prod_remote_uat._device_hash("ios-device"),
                "appVersion": "1.0",
                "caseDirection": "ios_to_android",
            },
            {
                "platform": "android",
                "deviceHash": b10_prod_remote_uat._device_hash("android-device"),
                "appVersion": "1.0",
                "caseDirection": "ios_to_android",
            },
        ]
        with mock.patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(ValueError, "both iOS-to-Android"):
                b10_prod_remote_uat._validate_device_evidence(evidence)

    def test_b10_remote_rejects_one_device_masquerading_as_two_platforms(self) -> None:
        device_id = "physical-device"
        evidence = [
            {
                "platform": "ios",
                "deviceHash": b10_prod_remote_uat._device_hash(device_id),
                "appVersion": "1.0",
                "caseDirection": "ios_to_android",
            },
            {
                "platform": "android",
                "deviceHash": b10_prod_remote_uat._device_hash(device_id),
                "appVersion": "1.0",
                "caseDirection": "android_to_ios",
            },
        ]
        with mock.patch.dict(
            os.environ,
            {
                "QWQ_B10_IOS_DEVICE_ID": device_id,
                "QWQ_B10_ANDROID_DEVICE_ID": device_id,
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "distinct iOS and Android"):
                b10_prod_remote_uat._validate_device_evidence(evidence)

    def test_b10_operator_readback_is_bound_to_active_candidate_digests(self) -> None:
        digest = "sha256:" + "a" * 64
        receipt_id = "b" * 64
        call_id = "call-1"
        call_digest = run_b10_prod_remote_patrol_uat._sha256(call_id.encode("utf-8"))
        payload = {
            "schema": "b10-prod-operator-readback",
            "version": 1,
            "imageDigest": digest,
            "configDigest": digest,
            "contractGraphDigest": digest,
            "adapterDigest": digest,
            "callIdDigests": [call_digest],
            "providerReceipts": {},
            "deliveryTimelines": [
                {
                    "callIdDigest": call_digest,
                    "deviceTimelineCount": 1,
                    "ringExternalAccepted": True,
                    "ringProviderAccepted": True,
                    "presentationAcknowledged": True,
                    "cancelExternalAccepted": True,
                    "cancelProviderAccepted": True,
                }
            ],
            "realtimeReadback": {
                "callIdDigests": [call_digest],
                "receiptRefs": ["receipt:realtime-ok"],
            },
            "chatProjection": {
                "systemCallLogs": [{"callIdDigest": call_digest, "count": 1}]
            },
            "qoeReadback": {
                "calls": [
                    {
                        "callIdDigest": call_digest,
                        "sessionDigest": digest,
                        "terminalState": "ended",
                        "mediaConnected": True,
                        "connectLatencyMs": 100,
                        "reconnectCount": 0,
                    }
                ],
                "effectiveSampleCount": 50,
                "alertReceiptRef": "receipt:alert-ok",
                "rollbackReceiptRef": "receipt:rollback-ok",
            },
            "observabilityRefs": {},
            "releaseReadiness": {
                "bindingPreflightReceiptRef": "receipt:binding-preflight",
                "adapterHealthReceiptRef": "receipt:adapter-health",
                "switchCompatibilityReceiptRef": "receipt:switch-compatible",
                "callbackDrainReceiptRef": "receipt:callback-drain",
                "lastGoodReceiptRef": f"receipt:hosted:{receipt_id}",
                "rollbackReceiptRef": f"receipt:hosted:{receipt_id}",
            },
            "cleanupReceipt": "receipt:cleanup-ok",
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "operator-readback.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            environment = {
                "QWQ_B10_OPERATOR_READBACK_PATH": str(path),
                "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST": digest,
                "QWQ_PROVIDER_CONFORMANCE_CONFIG_DIGEST": digest,
                "QWQ_PROVIDER_CONFORMANCE_CONTRACT_GRAPH_DIGEST": digest,
                "QWQ_PROVIDER_CONFORMANCE_ADAPTER_DIGEST": digest,
            }
            def hosted_receipt_readback(
                command: list[str],
                **_: object,
            ) -> subprocess.CompletedProcess[str]:
                purpose = command[command.index("--purpose") + 1]
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=json.dumps(
                        {
                            "receiptRef": f"receipt:hosted:{receipt_id}",
                            "candidate": {
                                "imageDigest": digest,
                                "configDigest": digest,
                                "contractGraphDigest": digest,
                                "adapterDigest": digest,
                            },
                            "purpose": purpose,
                        }
                    ),
                    stderr="",
                )

            with mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(
                run_b10_prod_remote_patrol_uat.subprocess,
                "run",
                side_effect=hosted_receipt_readback,
            ):
                self.assertEqual(
                    run_b10_prod_remote_patrol_uat._load_operator_receipts(
                        call_ids=(call_id,),
                    ),
                    payload,
                )
                payload["adapterDigest"] = "sha256:" + "b" * 64
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "active image, config"):
                    run_b10_prod_remote_patrol_uat._load_operator_receipts(
                        call_ids=(call_id,),
                    )
                payload["adapterDigest"] = digest
                payload["callIdDigests"] = [
                    run_b10_prod_remote_patrol_uat._sha256(b"stale-call"),
                ]
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "every executed call"):
                    run_b10_prod_remote_patrol_uat._load_operator_receipts(
                        call_ids=(call_id,),
                    )

    def test_b10_remote_rejects_dynamic_patrol_command(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"QWQ_B10_REMOTE_UAT_COMMAND_JSON": '["untrusted-runner"]'},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "source-owned Patrol"):
                b10_prod_remote_uat._load_command()
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                b10_prod_remote_uat._load_command(),
                list(b10_prod_remote_uat.SOURCE_OWNED_PATROL_COMMAND),
            )

    def test_b10_remote_patrol_passes_only_role_required_dart_defines(self) -> None:
        caller_command = run_b10_prod_remote_patrol_uat._patrol_command(
            "ios",
            role="caller",
        )
        callee_command = run_b10_prod_remote_patrol_uat._patrol_command(
            "android",
            role="callee",
        )
        self.assertIn("QWQ_PROVIDER_UAT_B10_CALL_ID", caller_command)
        self.assertNotIn(
            "QWQ_PROVIDER_UAT_B10_EXPECTED_CALLER_NAME",
            caller_command,
        )
        self.assertIn(
            "QWQ_PROVIDER_UAT_B10_EXPECTED_CALLER_NAME",
            callee_command,
        )
        self.assertNotIn("QWQ_PROVIDER_UAT_B10_CALL_ID", callee_command)

    def test_source_coverage_gaps_are_preserved_in_release_readiness(self) -> None:
        compiled, compile_issues = governance.load_and_compile()
        self.assertEqual(compile_issues, [])
        sources, discovery_issues = provider_conformance.discover_test_sources()
        self.assertEqual(discovery_issues, [])
        coverage = provider_conformance.source_coverage_issues(
            compiled=compiled,
            sources=sources,
        )
        with tempfile.TemporaryDirectory() as temporary:
            report, issues = provider_conformance.load_validate_and_derive(
                root=Path(temporary),
            )
        self.assertEqual(issues, [])
        self.assertEqual(report["sourceCoverageIssues"], coverage)
        readiness = provider_conformance.readiness_issues(
            report,
            environment="gamma",
        )
        for issue in coverage:
            self.assertIn(issue, readiness)

    def test_b10_remote_readback_emits_only_test_owned_case_results(self) -> None:
        assertion_ids = [
            "provider.success",
            "provider.validation",
            "provider.auth",
            "provider.network_dns",
            "provider.timeout",
            "provider.throttle",
            "provider.retry",
            "provider.idempotency",
            "provider.callback_ordering",
            "provider.redaction",
            "provider.observability",
            "provider.rtc_transport",
            "provider.adapter_health",
            "provider.adapter_switch",
            "provider.adapter_rollback",
        ]
        with tempfile.TemporaryDirectory() as temporary:
            result_path = Path(temporary) / "case-results.json"
            ios_hash = b10_prod_remote_uat._device_hash("ios-device")
            android_hash = b10_prod_remote_uat._device_hash("android-device")
            refs = {
                "logs": ["log:b10-uat"],
                "traces": ["trace:b10-uat"],
                "metrics": ["metric:b10-uat"],
            }
            call_digests = ["sha256:" + "d" * 64, "sha256:" + "e" * 64]
            readback = {
                "schema": b10_prod_remote_uat.READBACK_SCHEMA,
                "version": b10_prod_remote_uat.READBACK_VERSION,
                "status": "passed",
                "capabilityId": "rtc.room.transport",
                "adapterId": "infra.livekit_sfu",
                "imageDigest": "sha256:" + "a" * 64,
                "configDigest": "sha256:" + "b" * 64,
                "contractGraphDigest": "sha256:" + "c" * 64,
                "adapterDigest": "sha256:" + "f" * 64,
                "deviceEvidence": [
                    {
                        "platform": "ios",
                        "deviceHash": ios_hash,
                        "appVersion": "1.0",
                        "caseDirection": "ios_to_android",
                    },
                    {
                        "platform": "android",
                        "deviceHash": android_hash,
                        "appVersion": "1.0",
                        "caseDirection": "android_to_ios",
                    },
                ],
                "providerReceipts": [
                    {"providerKind": "livekit", "receiptRef": "receipt:livekit-ok"}
                ],
                "deliveryTimelines": [
                    {
                        "callIdDigest": call_digest,
                        "deviceTimelineCount": 1,
                        "ringExternalAccepted": True,
                        "ringProviderAccepted": True,
                        "presentationAcknowledged": True,
                        "cancelExternalAccepted": True,
                        "cancelProviderAccepted": True,
                    }
                    for call_digest in call_digests
                ],
                "pushReadback": {
                    "ios": "pushkit_callkit",
                    "android": "fcm_full_screen_or_heads_up",
                },
                "callReadback": {
                    "terminalState": "ended",
                    "participantCount": 2,
                    "mediaConnected": True,
                    "screenShareCompleted": True,
                    "pipHangup": True,
                    "cancelRaceResolved": True,
                },
                "realtimeReadback": {
                    "callIdDigests": call_digests,
                    "receiptRefs": [
                        "receipt:realtime-one",
                        "receipt:realtime-two",
                    ],
                },
                "chatProjection": {
                    "systemCallLogs": [
                        {"callIdDigest": call_digest, "count": 1}
                        for call_digest in call_digests
                    ]
                },
                "qoeReadback": {
                    "calls": [
                        {
                            "callIdDigest": call_digest,
                            "sessionDigest": "sha256:" + ("1" if index == 0 else "2") * 64,
                            "terminalState": "ended",
                            "mediaConnected": True,
                            "connectLatencyMs": 100,
                            "reconnectCount": 0,
                        }
                        for index, call_digest in enumerate(call_digests)
                    ],
                    "effectiveSampleCount": 50,
                    "alertReceiptRef": "receipt:alert-ok",
                    "rollbackReceiptRef": "receipt:rollback-ok",
                },
                "assertions": [
                    {
                        "assertionId": assertion_id,
                        "status": "passed",
                        "logRef": "log:b10-uat",
                        "traceRef": "trace:b10-uat",
                        "metricRefs": ["metric:b10-uat"],
                    }
                    for assertion_id in assertion_ids
                ],
                "dataDigest": "sha256:" + "c" * 64,
                "cleanupReceipt": "receipt:cleanup-ok",
                "observabilityRefs": refs,
                "releaseReadiness": {
                    "bindingPreflightReceiptRef": "receipt:preflight-ok",
                    "adapterHealthReceiptRef": "receipt:health-ok",
                    "switchCompatibilityReceiptRef": "receipt:switch-ok",
                    "callbackDrainReceiptRef": "receipt:drain-ok",
                    "lastGoodReceiptRef": "receipt:hosted:" + "d" * 64,
                    "rollbackReceiptRef": "receipt:hosted:" + "e" * 64,
                },
            }

            def write_native_readback(
                _command: list[str], *, env: dict[str, str], **_kwargs: object
            ) -> mock.Mock:
                Path(env["QWQ_B10_REMOTE_UAT_READBACK_PATH"]).write_text(
                    json.dumps(readback),
                    encoding="utf-8",
                )
                return mock.Mock(returncode=0)

            environment = {
                "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH": str(result_path),
                "QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT": "prod",
                "QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS": json.dumps(assertion_ids),
                "QWQ_PROVIDER_CONFORMANCE_CONFIG_DIGEST": "sha256:" + "b" * 64,
                "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST": "sha256:" + "a" * 64,
                "QWQ_PROVIDER_CONFORMANCE_CONTRACT_GRAPH_DIGEST": "sha256:" + "c" * 64,
                "QWQ_PROVIDER_CONFORMANCE_ADAPTER_DIGEST": "sha256:" + "f" * 64,
                "QWQ_PROVIDER_CONFORMANCE_TYPED_PORT": "MediaTransportPort",
                "QWQ_PROVIDER_CONFORMANCE_CONTRACT_REF": "quwoquan_service/services/rtc-service/contracts/rtc/call_session/operations.yaml",
                "QWQ_B10_IOS_DEVICE_ID": "ios-device",
                "QWQ_B10_ANDROID_DEVICE_ID": "android-device",
            }
            with (
                mock.patch.dict(os.environ, environment, clear=True),
                mock.patch.object(
                    b10_prod_remote_uat.subprocess,
                    "run",
                    side_effect=write_native_readback,
                ),
            ):
                self.assertEqual(
                    b10_prod_remote_uat.run(
                        "rtc.room.transport",
                        "infra.livekit_sfu",
                    ),
                    0,
                )
            case_result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(case_result["status"], "passed")
            self.assertEqual(case_result["assertionIds"], assertion_ids)
            self.assertEqual(case_result["cleanupReceipt"], "receipt:cleanup-ok")
            native_readback = dict(case_result["nativeReadback"])
            self.assertEqual(
                native_readback["schema"],
                b10_prod_remote_uat.READBACK_SCHEMA,
            )
            self.assertTrue(
                (
                    result_path.parent / native_readback["artifactName"]
                ).is_file()
            )
            sources, issues = provider_conformance.discover_test_sources()
            self.assertEqual(issues, [])
            loaded, case_issues = provider_conformance.load_case_results(
                result_path,
                source=sources[
                    (
                        "rtc.room.transport",
                        "infra.livekit_sfu",
                        "user_acceptance",
                    )
                ],
                environment="prod",
                config_digest="sha256:" + "b" * 64,
            )
            self.assertEqual(case_issues, [])
            self.assertIsNotNone(loaded)
            case_result["nativeReadback"]["artifactDigest"] = "sha256:" + "d" * 64
            result_path.write_text(json.dumps(case_result), encoding="utf-8")
            _, case_issues = provider_conformance.load_case_results(
                result_path,
                source=sources[
                    (
                        "rtc.room.transport",
                        "infra.livekit_sfu",
                        "user_acceptance",
                    )
                ],
                environment="prod",
                config_digest="sha256:" + "b" * 64,
            )
            self.assertTrue(any("native-device readback" in issue for issue in case_issues))
            case_result["nativeReadback"] = native_readback
            case_result.pop("releaseReadiness")
            result_path.write_text(json.dumps(case_result), encoding="utf-8")
            _, case_issues = provider_conformance.load_case_results(
                result_path,
                source=sources[
                    (
                        "rtc.room.transport",
                        "infra.livekit_sfu",
                        "user_acceptance",
                    )
                ],
                environment="prod",
                config_digest="sha256:" + "b" * 64,
            )
            self.assertTrue(any("missing fields" in issue for issue in case_issues))

    def test_release_readiness_reports_missing_executable_source_coverage(self) -> None:
        compiled, compile_issues = governance.load_and_compile()
        self.assertEqual(compile_issues, [])

        issues = provider_conformance.source_coverage_issues(
            compiled=compiled,
            sources={},
        )

        capability_ids = {
            capability["capability_id"]
            for capability in governance.load_registry()["capabilities"]
        }
        self.assertEqual(len(issues), len(capability_ids))
        for capability_id in capability_ids:
            self.assertTrue(
                any(issue.startswith(f"source_coverage.{capability_id}:") for issue in issues),
                capability_id,
            )
        self.assertTrue(
            any(
                "infra.livekit_sfu/user_acceptance" in issue
                for issue in issues
            ),
            "prod Remote RTC evidence source is mandatory",
        )

    def test_missing_fields_are_rejected_before_readiness(self) -> None:
        compiled, compile_issues = governance.load_and_compile()
        self.assertEqual(compile_issues, [])
        issues = provider_conformance.validate_evidence(
            [{"schema": "provider-conformance-evidence"}],
            registry=governance.load_registry(),
            compiled=compiled,
        )
        self.assertTrue(any("missing required fields" in issue for issue in issues))

    def test_attestation_is_bound_to_execution_report_bytes(self) -> None:
        raw = b'{"case_results":[],"exit_code":0}'
        signature = provider_conformance.sign_execution_report(
            raw, key="local-contract-attestation-key"
        )
        self.assertRegex(signature, r"^hmac-sha256:[a-f0-9]{64}$")
        self.assertNotEqual(
            signature,
            provider_conformance.sign_execution_report(
                raw + b" ", key="local-contract-attestation-key"
            ),
        )

    def test_evidence_loader_reads_only_disposable_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / ".qwq_output"
            evidence, issues = provider_conformance.load_evidence(output_root)
        self.assertEqual(evidence, [])
        self.assertEqual(issues, [])

    def test_attestation_key_is_not_defined_by_repository_config(self) -> None:
        self.assertNotIn(
            "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY",
            governance.load_bindings(),
        )
        value = os.environ.get("QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY")
        if value is not None:
            self.assertTrue(value)

    def test_remote_source_rejects_static_gate_block_assertion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "quwoquan_ops" / "tests" / "acceptance" / "api_integration"
            source_root.mkdir(parents=True)
            source = source_root / "remote_provider_test.py"
            source.write_text(
                "\n".join(
                    (
                        "# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003",
                        '# provider_conformance: {"adapterId":"ext.llm.protocol_fixture","capabilityId":"assistant.model.generation","testLayer":"api_integration","typedPort":"ModelCompletionPort","contractRef":"quwoquan_service/services/assistant-service/contracts/assistant/assistant_conversation/operations.yaml","assertionIds":["provider.success","provider.validation","provider.auth","provider.network_dns","provider.timeout","provider.throttle","provider.retry","provider.idempotency","provider.callback_ordering","provider.redaction","provider.observability","provider.model_generation"],"command":["python3","remote_provider_test.py"],"target":"real-provider","networkBoundary":"remote_protocol"}',
                        "result_path = 'QWQ_PROVIDER_CONFORMANCE_RESULT_PATH'",
                        "assert False, 'GATE_BLOCK'",
                    )
                ),
                encoding="utf-8",
            )
            roots = {
                **provider_conformance.TEST_LAYER_ROOTS,
                "api_integration": source_root,
            }
            with (
                mock.patch.object(provider_conformance, "ROOT", root),
                mock.patch.object(provider_conformance, "TEST_LAYER_ROOTS", roots),
                self.assertRaisesRegex(ValueError, "static should-block/GATE_BLOCK"),
            ):
                provider_conformance.load_test_source(source)

    def test_source_rejects_runtime_selected_executor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "quwoquan_ops" / "tests" / "local_contract"
            source_root.mkdir(parents=True)
            source = source_root / "delegated_provider_conformance.py"
            source.write_text(
                "\n".join(
                    (
                        "# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003",
                        '# provider_conformance: {"adapterId":"ext.llm.protocol_fixture","capabilityId":"assistant.model.generation","testLayer":"local_contract","typedPort":"ModelCompletionPort","contractRef":"quwoquan_service/services/assistant-service/contracts/assistant/assistant_conversation/operations.yaml","assertionIds":["provider.success","provider.validation","provider.auth","provider.network_dns","provider.timeout","provider.throttle","provider.retry","provider.idempotency","provider.callback_ordering","provider.redaction","provider.observability","provider.model_generation"],"command":["python3","delegated_provider_conformance.py"],"target":"delegated-provider","networkBoundary":"offline_harness"}',
                        "import os",
                        "result_path = os.environ['QWQ_PROVIDER_CONFORMANCE_RESULT_PATH']",
                        "command = os.environ['QWQ_PROVIDER_CONFORMANCE_EXECUTOR_COMMAND_JSON']",
                    )
                ),
                encoding="utf-8",
            )
            roots = {
                **provider_conformance.TEST_LAYER_ROOTS,
                "local_contract": source_root,
            }
            with (
                mock.patch.object(provider_conformance, "ROOT", root),
                mock.patch.object(provider_conformance, "TEST_LAYER_ROOTS", roots),
                self.assertRaisesRegex(
                    ValueError,
                    "runtime-selected executor",
                ),
            ):
                provider_conformance.load_test_source(source)


if __name__ == "__main__":
    unittest.main()
