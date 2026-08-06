# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from quwoquan_ops.ci.provider_conformance import b10_prod_remote_uat
from quwoquan_ops.ci.provider_conformance import run_b10_prod_remote_patrol_uat
from quwoquan_ops.ci.render_provider_conformance_source import render as render_source
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
        self.assertNotIn("version", schema["required"])
        self.assertNotIn("version", schema["properties"])
        for required in (
            "adapterId",
            "capabilityId",
            "artifactRef",
            "artifactDigest",
            "artifactAttestation",
            "nonPromotable",
            "sourceTreeState",
            "commitReview",
            "candidateStatus",
            "candidateReceiptRef",
            "candidateReceiptDigest",
            "attestationAuthority",
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

    def test_message_transport_p95_refs_bind_recording_rules(self) -> None:
        refs = provider_conformance.required_metric_refs(
            provider_conformance.MESSAGE_TRANSPORT_CAPABILITY_ID
        )
        self.assertIn("promql://qwq_message_transport_publish_p95", refs)
        self.assertIn("promql://qwq_message_transport_consume_p95", refs)
        self.assertNotIn(
            "provider-conformance://runtime.message.transport/metrics/publish_p95",
            refs,
        )

    def test_nonprod_active_candidate_requires_current_startup_identity(self) -> None:
        baseline = "sha256:" + "1" * 64
        runtime_image = "sha256:" + "2" * 64
        runtime_config = "sha256:" + "3" * 64
        package_image = "sha256:" + "4" * 64
        build_input = "sha256:" + "5" * 64
        provider_image = "sha256:" + "6" * 64
        contract_graph = "sha256:" + "7" * 64
        commit = "a" * 40
        startup = {
            "target": "alpha-local",
            "env": "alpha",
            "status": "running",
            "workload": "full",
            "candidateDigest": baseline,
            "configurationDigest": runtime_config,
            "imageTransportTag": provider_conformance.immutable_image_digest(
                {"assistant-service": runtime_image}
            ),
            "imageComposition": {
                "images": {"assistant-service": {"ref": runtime_image}}
            },
        }
        active = {"baselineId": baseline}
        manifest = {
            "baselineId": baseline,
            "sourceRevision": commit,
            "runtimeConfigDigest": runtime_config,
            "imageDigest": package_image,
            "buildInputDigest": build_input,
        }
        oci = {
            "schema": "stackctl-package-oci-images",
            "environment": "alpha",
            "target": "alpha-local",
            "configurationDigest": runtime_config,
            "imageDigest": package_image,
            "buildInputDigest": build_input,
            "images": {
                "assistant-service": {
                    "ref": "qwq/assistant-service:build",
                    "imageDigest": runtime_image,
                }
            },
        }

        def issues(receipt: dict[str, object]) -> list[str]:
            return provider_conformance._nonprod_active_candidate_issues(
                environment="alpha",
                target="alpha-local",
                startup=receipt,
                active=active,
                manifest=manifest,
                oci=oci,
                commit=commit,
                image_digest=provider_image,
                contract_graph_digest=contract_graph,
                expected_image_digest=provider_image,
                expected_contract_graph_digest=contract_graph,
            )

        self.assertEqual(issues(startup), [])
        stopped = {**startup, "status": "stopped"}
        self.assertTrue(any("not running" in issue for issue in issues(stopped)))
        missing_candidate = {**startup, "candidateDigest": None}
        self.assertTrue(
            any("candidateDigest" in issue for issue in issues(missing_candidate))
        )
        stale_config = {
            **startup,
            "configurationDigest": "sha256:" + "8" * 64,
        }
        self.assertTrue(
            any("configuration digest is stale" in issue for issue in issues(stale_config))
        )
        stale_image = deepcopy(startup)
        stale_image["imageComposition"]["images"]["assistant-service"]["ref"] = (
            "sha256:" + "9" * 64
        )
        self.assertTrue(
            any("runtime image is stale" in issue for issue in issues(stale_image))
        )

        with mock.patch.object(
            provider_conformance,
            "load_startup_attempt",
            return_value=None,
        ):
            resolved = provider_conformance.resolve_nonprod_active_candidate(
                environment="alpha",
                registry={},
                commit=commit,
                image_digest=provider_image,
                contract_graph_digest=contract_graph,
            )
        self.assertFalse(resolved["active"])
        self.assertIn("missing", str(resolved["reason"]))
        with (
            mock.patch.object(
                provider_conformance,
                "load_startup_attempt",
                return_value=startup,
            ),
            mock.patch.object(
                provider_conformance,
                "can_reuse_package",
                return_value=(False, "package content digest mismatch"),
            ),
        ):
            stale_package = provider_conformance.resolve_nonprod_active_candidate(
                environment="alpha",
                registry={},
                commit=commit,
                image_digest=provider_image,
                contract_graph_digest=contract_graph,
            )
        self.assertFalse(stale_package["active"])
        self.assertIn("package content digest mismatch", str(stale_package["reason"]))
        claimed_active = {
            "candidateStatus": "active_immutable",
            "candidateReceiptRef": ".qwq_output/env/alpha/process/startup_attempt.json",
            "candidateReceiptDigest": "sha256:" + "9" * 64,
            "environment": "alpha",
            "commit": commit,
            "imageDigest": provider_image,
            "contractGraphDigest": contract_graph,
        }
        with mock.patch.object(
            provider_conformance,
            "resolve_nonprod_active_candidate",
            return_value={
                "active": False,
                "receiptRef": "",
                "receiptDigest": "",
                "reason": "startup receipt status is not running",
            },
        ):
            receipt_issues = provider_conformance.active_candidate_receipt_issues(
                claimed_active,
                registry={},
                root=Path("/tmp"),
            )
        self.assertTrue(
            any("not backed by the current canonical startup receipt" in issue for issue in receipt_issues)
        )

    def test_prod_active_candidate_requires_matching_native_readback(self) -> None:
        digest = "sha256:" + "a" * 64
        readiness = {"bindingPreflightReceiptRef": "receipt:preflight"}
        case_result = {"releaseReadiness": readiness}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / ".qwq_output"
            run_root = root / "env/prod/runs/provider"
            run_root.mkdir(parents=True)
            case_path = run_root / "case-results.json"
            readback_path = run_root / "provider.native-device-readback.json"
            payload = {
                "schema": provider_conformance.B10_REMOTE_READBACK_SCHEMA,
                "status": "passed",
                "capabilityId": "rtc.room.transport",
                "adapterId": "infra.livekit_sfu",
                "imageDigest": digest,
                "configDigest": digest,
                "contractGraphDigest": digest,
                "adapterDigest": digest,
                "releaseReadiness": readiness,
            }
            raw = json.dumps(payload, sort_keys=True).encode("utf-8")
            readback_path.write_bytes(raw)
            case_result["nativeReadback"] = {
                "artifactName": readback_path.name,
                "artifactDigest": "sha256:" + hashlib.sha256(raw).hexdigest(),
            }
            with mock.patch.dict(
                os.environ,
                {"QWQ_OUTPUT_ROOT": str(root)},
                clear=False,
            ):
                valid = provider_conformance.resolve_prod_active_candidate(
                    case_result_path=case_path,
                    case_result=case_result,
                    capability_id="rtc.room.transport",
                    adapter_id="infra.livekit_sfu",
                    image_digest=digest,
                    config_digest=digest,
                    contract_graph_digest=digest,
                    adapter_digest=digest,
                )
                missing = provider_conformance.resolve_prod_active_candidate(
                    case_result_path=case_path,
                    case_result={"releaseReadiness": readiness},
                    capability_id="rtc.room.transport",
                    adapter_id="infra.livekit_sfu",
                    image_digest=digest,
                    config_digest=digest,
                    contract_graph_digest=digest,
                    adapter_digest=digest,
                )
                stale = provider_conformance.resolve_prod_active_candidate(
                    case_result_path=case_path,
                    case_result=case_result,
                    capability_id="rtc.room.transport",
                    adapter_id="infra.livekit_sfu",
                    image_digest="sha256:" + "b" * 64,
                    config_digest=digest,
                    contract_graph_digest=digest,
                    adapter_digest=digest,
                )
        self.assertTrue(valid["active"])
        self.assertRegex(str(valid["receiptDigest"]), r"^sha256:[a-f0-9]{64}$")
        self.assertFalse(missing["active"])
        self.assertFalse(stale["active"])

    def test_release_cell_set_is_exactly_140_and_rejects_legacy_duplicates(
        self,
    ) -> None:
        compiled = {
            "providerConformanceCapabilityIds": [
                f"provider.capability.{index:02d}" for index in range(14)
            ]
        }
        expected = provider_conformance.expected_required_cell_keys(compiled)
        self.assertEqual(len(expected), 140)
        evidence = []
        for capability_id, environment, layer in sorted(expected):
            item = {
                field: "value"
                for field in provider_conformance.REQUIRED_FIELDS
            }
            item.update(
                {
                    "schema": "provider-conformance-evidence",
                    "capabilityId": capability_id,
                    "environment": environment,
                    "testLayer": layer,
                }
            )
            evidence.append(item)
        self.assertEqual(
            provider_conformance.exact_required_cell_issues(
                evidence,
                compiled=compiled,
            ),
            [],
        )
        missing = provider_conformance.exact_required_cell_issues(
            evidence[:-1],
            compiled=compiled,
        )
        self.assertTrue(any("exactly 140" in issue for issue in missing))
        duplicate = provider_conformance.exact_required_cell_issues(
            [*evidence, evidence[0]],
            compiled=compiled,
        )
        self.assertTrue(any("duplicate" in issue for issue in duplicate))
        legacy = dict(evidence[0])
        legacy.pop("candidateReceiptDigest")
        legacy_issues = provider_conformance.exact_required_cell_issues(
            [legacy, *evidence[1:]],
            compiled=compiled,
        )
        self.assertTrue(any("legacy" in issue for issue in legacy_issues))

    def test_empty_evidence_cannot_satisfy_release_readiness(self) -> None:
        report = {
            "schema": "provider-conformance-readiness",
            "evidenceCount": 0,
            "readiness": {},
            "issues": [],
        }
        for environment in ("gamma", "prod"):
            issues = provider_conformance.readiness_issues(
                report, environment=environment
            )
            self.assertTrue(any("zero Provider Conformance evidence" in issue for issue in issues))

    def test_online_readiness_projection_rejects_historical_version_field(self) -> None:
        report = {
            "schema": "provider-conformance-readiness",
            "version": 1,
            "evidenceCount": 1,
            "executableSourceCount": 1,
            "sourceCoverageIssues": [],
            "readiness": {},
            "issues": [],
        }
        with self.assertRaisesRegex(ValueError, "fields are not canonical"):
            render_source(report, validation_issues=[], environment="prod")

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
                "applicationDigest": "sha256:" + "1" * 64,
                "caseDirection": "ios_to_android",
            },
            {
                "platform": "android",
                "deviceHash": b10_prod_remote_uat._device_hash("android-device"),
                "applicationDigest": "sha256:" + "2" * 64,
                "caseDirection": "ios_to_android",
            },
        ]
        environment.update(
            {
                "QWQ_B10_IOS_APPLICATION_DIGEST": "sha256:" + "1" * 64,
                "QWQ_B10_ANDROID_APPLICATION_DIGEST": "sha256:" + "2" * 64,
            }
        )
        with mock.patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(ValueError, "both iOS-to-Android"):
                b10_prod_remote_uat._validate_device_evidence(evidence)

    def test_b10_remote_rejects_one_device_masquerading_as_two_platforms(self) -> None:
        device_id = "physical-device"
        evidence = [
            {
                "platform": "ios",
                "deviceHash": b10_prod_remote_uat._device_hash(device_id),
                "applicationDigest": "sha256:" + "1" * 64,
                "caseDirection": "ios_to_android",
            },
            {
                "platform": "android",
                "deviceHash": b10_prod_remote_uat._device_hash(device_id),
                "applicationDigest": "sha256:" + "2" * 64,
                "caseDirection": "android_to_ios",
            },
        ]
        with mock.patch.dict(
            os.environ,
            {
                "QWQ_B10_IOS_DEVICE_ID": device_id,
                "QWQ_B10_ANDROID_DEVICE_ID": device_id,
                "QWQ_B10_IOS_APPLICATION_DIGEST": "sha256:" + "1" * 64,
                "QWQ_B10_ANDROID_APPLICATION_DIGEST": "sha256:" + "2" * 64,
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
        self.assertEqual(
            coverage,
            [],
            "all 14 external Provider capabilities must have three-layer sources; "
            "first-party HTTP authority bindings are outside Provider Conformance",
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
                        "applicationDigest": "sha256:" + "1" * 64,
                        "caseDirection": "ios_to_android",
                    },
                    {
                        "platform": "android",
                        "deviceHash": android_hash,
                        "applicationDigest": "sha256:" + "2" * 64,
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
                "QWQ_B10_IOS_APPLICATION_DIGEST": "sha256:" + "1" * 64,
                "QWQ_B10_ANDROID_APPLICATION_DIGEST": "sha256:" + "2" * 64,
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
            case_result.pop("nativeReadback")
            result_path.write_text(json.dumps(case_result), encoding="utf-8")
            loaded_without_readback, case_issues = provider_conformance.load_case_results(
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
            self.assertIsNotNone(loaded_without_readback)
            case_result["nativeReadback"] = native_readback
            case_result["version"] = 1
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
            self.assertTrue(any("unknown fields" in issue for issue in case_issues))
            case_result.pop("version")
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

        capability_ids = set(compiled["providerConformanceCapabilityIds"])
        self.assertEqual(len(issues), len(capability_ids))
        for capability_id in capability_ids:
            self.assertTrue(
                any(issue.startswith(f"source_coverage.{capability_id}:") for issue in issues),
                capability_id,
            )
        for capability_id in {
            "chat.conversation.membership.read",
            "circle.membership.self.read",
            "integration.connector_grant.read",
        }:
            self.assertFalse(
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

    def test_ci_attestation_cannot_be_silently_accepted_without_authority(self) -> None:
        report = {
            field: "value"
            for field in provider_conformance.EXECUTION_REPORT_REQUIRED_FIELDS
        }
        report.update(
            {
                "schema": provider_conformance.EXECUTION_REPORT_SCHEMA,
                "exitCode": 0,
                "testSource": None,
                "testCommand": "python3 provider-test.py",
                "commit": "a" * 40,
                "attestationAuthority": "ci",
                "nonPromotable": False,
                "sourceTreeState": "clean",
                "commitReview": "reviewed",
                "candidateStatus": "active_immutable",
                "candidateReceiptRef": ".qwq_output/env/prod/runs/readback.json",
                "candidateReceiptDigest": "sha256:" + "1" * 64,
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"
            raw = json.dumps(report, sort_keys=True).encode("utf-8")
            path.write_bytes(raw)
            evidence = {
                **report,
                "artifactDigest": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "artifactAttestation": "hmac-sha256:" + "2" * 64,
            }
            with mock.patch.dict(os.environ, {}, clear=True):
                issues = provider_conformance._validate_execution_report(
                    artifact_path=path,
                    evidence=evidence,
                    expected_source=None,
                )
        self.assertTrue(
            any("CI attestation authority is unavailable" in issue for issue in issues)
        )

    def test_dirty_worktree_and_local_key_cannot_be_promoted(self) -> None:
        commit = "a" * 40
        with (
            mock.patch.dict(
                os.environ,
                {"QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY": "developer-key"},
                clear=True,
            ),
            mock.patch.object(
                provider_conformance,
                "current_source_tree_state",
                return_value="dirty",
            ),
        ):
            identity = provider_conformance.evidence_identity(
                commit=commit,
                candidate_receipt_bound=True,
                candidate_receipt_ref=".qwq_output/env/alpha/runs/startup.json",
                candidate_receipt_digest="sha256:" + "9" * 64,
            )
            attestation = provider_conformance.attest_execution_report(
                b"local execution report",
                identity=identity,
            )

        self.assertEqual(
            identity,
            {
                "nonPromotable": True,
                "sourceTreeState": "dirty",
                "commitReview": "unreviewed",
                "candidateStatus": "active_immutable",
                "candidateReceiptRef": ".qwq_output/env/alpha/runs/startup.json",
                "candidateReceiptDigest": "sha256:" + "9" * 64,
                "attestationAuthority": "local",
            },
        )
        self.assertRegex(attestation, r"^local-sha256:[a-f0-9]{64}$")
        self.assertFalse(
            provider_conformance.evidence_is_promotable(
                {**identity, "commit": commit},
                require_runtime_authority=False,
            )
        )
        non_promotable_cell = {
            **identity,
            "status": "passed",
            "commit": commit,
            "imageDigest": "sha256:" + "1" * 64,
            "contractGraphDigest": "sha256:" + "2" * 64,
            "adapterDigest": "sha256:" + "3" * 64,
            "configDigest": "sha256:" + "4" * 64,
            "assertionIds": sorted(provider_conformance.PUBLIC_ASSERTION_IDS),
            "typedPort": "ExamplePort",
            "contractRef": "example/operations.yaml",
            "environment": "alpha",
        }
        with mock.patch.object(
            provider_conformance,
            "ci_attestation_authority_available",
            return_value=True,
        ):
            self.assertFalse(
                provider_conformance._cells_share_release(
                    [non_promotable_cell],
                    expected_environments=["alpha"],
                    require_adapter_digest=True,
                )
            )
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(
                provider_conformance,
                "current_source_tree_state",
                return_value="dirty",
            ),
        ):
            no_key_identity = provider_conformance.evidence_identity(
                commit=commit,
                candidate_receipt_bound=False,
            )
            self.assertRegex(
                provider_conformance.attest_execution_report(
                    b"no CI key local report",
                    identity=no_key_identity,
                ),
                r"^local-sha256:[a-f0-9]{64}$",
            )

        forged_local_key_identity = {
            "nonPromotable": False,
            "sourceTreeState": "clean",
            "commitReview": "reviewed",
            "candidateStatus": "active_immutable",
            "candidateReceiptRef": "",
            "candidateReceiptDigest": "",
            "attestationAuthority": "ci",
            "commit": commit,
        }
        with (
            mock.patch.dict(
                os.environ,
                {"QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY": "developer-key"},
                clear=True,
            ),
            mock.patch.object(
                provider_conformance,
                "current_source_tree_state",
                return_value="clean",
            ),
        ):
            self.assertFalse(
                provider_conformance.evidence_is_promotable(
                    forged_local_key_identity,
                )
            )
        with (
            mock.patch.dict(
                os.environ,
                {
                    "GITHUB_ACTIONS": "true",
                    "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_AUTHORITY": "ci",
                    "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY": "forged-local-key",
                    "QWQ_PROVIDER_CONFORMANCE_REVIEWED_COMMIT": commit,
                },
                clear=True,
            ),
            mock.patch.object(
                provider_conformance,
                "current_source_tree_state",
                return_value="clean",
            ),
        ):
            spoofed_context = provider_conformance.evidence_identity(
                commit=commit,
                candidate_receipt_bound=False,
            )
            self.assertTrue(spoofed_context["nonPromotable"])
            self.assertEqual(spoofed_context["candidateStatus"], "unverified")
            self.assertFalse(
                provider_conformance.evidence_is_promotable(
                    {**spoofed_context, "commit": commit},
                )
            )

    def test_reviewed_clean_ci_identity_is_promotable(self) -> None:
        commit = "b" * 40
        with (
            mock.patch.dict(
                os.environ,
                {
                    "GITHUB_ACTIONS": "true",
                    "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_AUTHORITY": "ci",
                    "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY": "ci-owned-key",
                    "QWQ_PROVIDER_CONFORMANCE_REVIEWED_COMMIT": commit,
                },
                clear=True,
            ),
            mock.patch.object(
                provider_conformance,
                "current_source_tree_state",
                return_value="clean",
            ),
        ):
            identity = provider_conformance.evidence_identity(
                commit=commit,
                candidate_receipt_bound=True,
                candidate_receipt_ref=".qwq_output/env/alpha/runs/startup.json",
                candidate_receipt_digest="sha256:" + "9" * 64,
            )
            self.assertFalse(identity["nonPromotable"])
            self.assertEqual(identity["attestationAuthority"], "ci")
            self.assertTrue(
                provider_conformance.evidence_is_promotable(
                    {**identity, "commit": commit},
                )
            )
            promotable_cell = {
                **identity,
                "status": "passed",
                "commit": commit,
                "imageDigest": "sha256:" + "1" * 64,
                "contractGraphDigest": "sha256:" + "2" * 64,
                "adapterDigest": "sha256:" + "3" * 64,
                "configDigest": "sha256:" + "4" * 64,
                "assertionIds": sorted(provider_conformance.PUBLIC_ASSERTION_IDS),
                "typedPort": "ExamplePort",
                "contractRef": "example/operations.yaml",
                "environment": "alpha",
            }
            self.assertTrue(
                provider_conformance._cells_share_release(
                    [promotable_cell],
                    expected_environments=["alpha"],
                    require_adapter_digest=True,
                )
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
                        '# provider_conformance: {"adapterId":"ext.llm.protocol_fixture","capabilityId":"assistant.model.generation","testLayer":"api_integration","typedPort":"ModelCompletionPort","contractRef":"quwoquan_service/services/assistant-service/contracts/assistant/assistant_session/operations.yaml","assertionIds":["provider.success","provider.validation","provider.auth","provider.network_dns","provider.timeout","provider.throttle","provider.retry","provider.idempotency","provider.callback_ordering","provider.redaction","provider.observability","provider.model_generation"],"command":["python3","remote_provider_test.py"],"target":"real-provider","networkBoundary":"remote_protocol"}',
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
                        '# provider_conformance: {"adapterId":"ext.llm.protocol_fixture","capabilityId":"assistant.model.generation","testLayer":"local_contract","typedPort":"ModelCompletionPort","contractRef":"quwoquan_service/services/assistant-service/contracts/assistant/assistant_session/operations.yaml","assertionIds":["provider.success","provider.validation","provider.auth","provider.network_dns","provider.timeout","provider.throttle","provider.retry","provider.idempotency","provider.callback_ordering","provider.redaction","provider.observability","provider.model_generation"],"command":["python3","delegated_provider_conformance.py"],"target":"delegated-provider","networkBoundary":"offline_harness"}',
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
