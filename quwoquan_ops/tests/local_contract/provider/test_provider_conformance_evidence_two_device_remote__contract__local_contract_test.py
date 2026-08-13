# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003
"""prod 两设备 remote UAT 证据链的本地契约。

由 test_provider_conformance_evidence__contract__local_contract_test.py
（Python 1000 行硬顶治理）按场景拆出：remote 测试源发现、双设备双向
证据、operator readback 摘要绑定、source-owned Patrol 命令与 test-owned
case results。测试逐字搬移。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from quwoquan_ops.ci.provider_conformance import run_prod_remote_uat
from quwoquan_ops.ci.provider_conformance import run_prod_remote_patrol_uat
from quwoquan_ops.cli.lib import provider_conformance


class ProviderConformanceEvidenceContractTest(unittest.TestCase):
    def test_provider_two_device_prod_remote_sources_are_discovered(self) -> None:
        sources, issues = provider_conformance.discover_test_sources()
        self.assertEqual(issues, [])
        self.assertEqual(
            sources[
                ("rtc.room.transport", "infra.livekit_sfu", "user_acceptance")
            ]["target"],
            "provider-remote-rtc.room.transport",
        )
        self.assertEqual(
            sources[
                ("integration.push.delivery", "ext.push.dispatch", "user_acceptance")
            ]["target"],
            "provider-remote-integration.push.delivery",
        )
        self.assertEqual(
            sources[
                (
                    "runtime.message.transport",
                    "infra.redis.message_transport",
                    "user_acceptance",
                )
            ]["target"],
            "provider-remote-runtime.message.transport",
        )

    def test_provider_two_device_remote_readback_requires_both_device_directions(self) -> None:
        environment = {
            "QWQ_PROVIDER_UAT_IOS_DEVICE_ID": "ios-device",
            "QWQ_PROVIDER_UAT_ANDROID_DEVICE_ID": "android-device",
        }
        evidence = [
            {
                "platform": "ios",
                "deviceHash": run_prod_remote_uat._device_hash("ios-device"),
                "applicationDigest": "sha256:" + "1" * 64,
                "caseDirection": "ios_to_android",
            },
            {
                "platform": "android",
                "deviceHash": run_prod_remote_uat._device_hash("android-device"),
                "applicationDigest": "sha256:" + "2" * 64,
                "caseDirection": "ios_to_android",
            },
        ]
        environment.update(
            {
                "QWQ_PROVIDER_UAT_IOS_APPLICATION_DIGEST": "sha256:" + "1" * 64,
                "QWQ_PROVIDER_UAT_ANDROID_APPLICATION_DIGEST": "sha256:" + "2" * 64,
            }
        )
        with mock.patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(ValueError, "both iOS-to-Android"):
                run_prod_remote_uat._validate_device_evidence(evidence)

    def test_provider_two_device_remote_rejects_one_device_masquerading_as_two_platforms(self) -> None:
        device_id = "physical-device"
        evidence = [
            {
                "platform": "ios",
                "deviceHash": run_prod_remote_uat._device_hash(device_id),
                "applicationDigest": "sha256:" + "1" * 64,
                "caseDirection": "ios_to_android",
            },
            {
                "platform": "android",
                "deviceHash": run_prod_remote_uat._device_hash(device_id),
                "applicationDigest": "sha256:" + "2" * 64,
                "caseDirection": "android_to_ios",
            },
        ]
        with mock.patch.dict(
            os.environ,
            {
                "QWQ_PROVIDER_UAT_IOS_DEVICE_ID": device_id,
                "QWQ_PROVIDER_UAT_ANDROID_DEVICE_ID": device_id,
                "QWQ_PROVIDER_UAT_IOS_APPLICATION_DIGEST": "sha256:" + "1" * 64,
                "QWQ_PROVIDER_UAT_ANDROID_APPLICATION_DIGEST": "sha256:" + "2" * 64,
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "distinct iOS and Android"):
                run_prod_remote_uat._validate_device_evidence(evidence)

    def test_provider_two_device_operator_readback_is_bound_to_active_candidate_digests(self) -> None:
        digest = "sha256:" + "a" * 64
        receipt_id = "b" * 64
        assertion_ids = ["provider.success", "provider.rtc_transport"]
        call_id = "call-1"
        call_digest = run_prod_remote_patrol_uat._sha256(call_id.encode("utf-8"))
        payload = {
            "schema": "provider-prod-operator-readback",
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
            "assertions": [
                {
                    "assertionId": assertion_id,
                    "status": "passed",
                    "sceneReceiptRef": f"receipt:scene-{index}",
                    "logRef": "log:provider-uat",
                    "traceRef": "trace:provider-uat",
                    "metricRefs": ["metric:provider-uat"],
                }
                for index, assertion_id in enumerate(assertion_ids)
            ],
            "observabilityRefs": {
                "logs": ["log:provider-uat"],
                "traces": ["trace:provider-uat"],
                "metrics": ["metric:provider-uat"],
            },
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
                "QWQ_PROVIDER_UAT_OPERATOR_READBACK_PATH": str(path),
                "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST": digest,
                "QWQ_PROVIDER_CONFORMANCE_CONFIG_DIGEST": digest,
                "QWQ_PROVIDER_CONFORMANCE_CONTRACT_GRAPH_DIGEST": digest,
                "QWQ_PROVIDER_CONFORMANCE_ADAPTER_DIGEST": digest,
                "QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS": json.dumps(
                    assertion_ids
                ),
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
                run_prod_remote_patrol_uat.subprocess,
                "run",
                side_effect=hosted_receipt_readback,
            ):
                self.assertEqual(
                    run_prod_remote_patrol_uat._load_operator_receipts(
                        call_ids=(call_id,),
                    ),
                    payload,
                )
                payload["adapterDigest"] = "sha256:" + "b" * 64
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "active image, config"):
                    run_prod_remote_patrol_uat._load_operator_receipts(
                        call_ids=(call_id,),
                    )
                payload["adapterDigest"] = digest
                payload["callIdDigests"] = [
                    run_prod_remote_patrol_uat._sha256(b"stale-call"),
                ]
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "every executed call"):
                    run_prod_remote_patrol_uat._load_operator_receipts(
                        call_ids=(call_id,),
                    )
                payload["callIdDigests"] = [call_digest]
                payload["assertions"] = []
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "observed scene"):
                    run_prod_remote_patrol_uat._load_operator_receipts(
                        call_ids=(call_id,),
                    )

    def test_provider_two_device_remote_rejects_dynamic_patrol_command(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"QWQ_PROVIDER_UAT_REMOTE_UAT_COMMAND_JSON": '["untrusted-runner"]'},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "source-owned Patrol"):
                run_prod_remote_uat._load_command()
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                run_prod_remote_uat._load_command(),
                list(run_prod_remote_uat.SOURCE_OWNED_PATROL_COMMAND),
            )

    def test_provider_two_device_remote_patrol_passes_only_role_required_dart_defines(self) -> None:
        caller_command = run_prod_remote_patrol_uat._patrol_command(
            "ios",
            role="caller",
        )
        callee_command = run_prod_remote_patrol_uat._patrol_command(
            "android",
            role="callee",
        )
        self.assertIn("QWQ_PROVIDER_UAT_CALL_ID", caller_command)
        self.assertNotIn(
            "QWQ_PROVIDER_UAT_EXPECTED_CALLER_NAME",
            caller_command,
        )
        self.assertIn(
            "QWQ_PROVIDER_UAT_EXPECTED_CALLER_NAME",
            callee_command,
        )
        self.assertNotIn("QWQ_PROVIDER_UAT_CALL_ID", callee_command)

    def test_provider_two_device_remote_readback_emits_only_test_owned_case_results(self) -> None:
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
            ios_hash = run_prod_remote_uat._device_hash("ios-device")
            android_hash = run_prod_remote_uat._device_hash("android-device")
            refs = {
                "logs": ["log:provider-uat"],
                "traces": ["trace:provider-uat"],
                "metrics": ["metric:provider-uat"],
            }
            call_digests = ["sha256:" + "d" * 64, "sha256:" + "e" * 64]
            readback = {
                "schema": run_prod_remote_uat.READBACK_SCHEMA,
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
                        "logRef": "log:provider-uat",
                        "traceRef": "trace:provider-uat",
                        "metricRefs": ["metric:provider-uat"],
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
                Path(env["QWQ_PROVIDER_UAT_REMOTE_UAT_READBACK_PATH"]).write_text(
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
                "QWQ_PROVIDER_UAT_IOS_DEVICE_ID": "ios-device",
                "QWQ_PROVIDER_UAT_ANDROID_DEVICE_ID": "android-device",
                "QWQ_PROVIDER_UAT_IOS_APPLICATION_DIGEST": "sha256:" + "1" * 64,
                "QWQ_PROVIDER_UAT_ANDROID_APPLICATION_DIGEST": "sha256:" + "2" * 64,
            }
            with (
                mock.patch.dict(os.environ, environment, clear=True),
                mock.patch.object(
                    run_prod_remote_uat.subprocess,
                    "run",
                    side_effect=write_native_readback,
                ),
            ):
                self.assertEqual(
                    run_prod_remote_uat.run(
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
                run_prod_remote_uat.READBACK_SCHEMA,
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


if __name__ == "__main__":
    unittest.main()
