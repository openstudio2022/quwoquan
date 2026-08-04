from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.verify_runtime_media_t4_evidence import (
    MATRIX_SCHEMA,
    MATRIX_SCENARIO,
    REPORT_SCHEMA,
    SCENARIO,
    validate_evidence_document,
)


def _sha256_digest(payload: str) -> str:
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _report(
    *,
    target: str = "gamma-local",
    env: str = "gamma",
    stage: str | None = None,
) -> dict[str, object]:
    return {
        "schema": REPORT_SCHEMA,
        "scenario": SCENARIO,
        "status": "passed",
        "dryRun": False,
        "startedAt": "2026-07-16T00:00:00Z",
        "endedAt": "2026-07-16T00:01:00Z",
        "environment": {
            "target": target,
            "env": env,
            "rolloutStage": stage or ("gray-initial" if target == "prod-hosted" else "local"),
            "mediaVideoBaseUrl": "https://cdn.gamma.example.invalid/media/video",
            "commitSha": "abcdef0123456789",
            "configHash": _sha256_digest(f"runtime-media-config:{target}"),
        },
        "release": {
            "releaseId": "release-video-a",
            "sourceOwner": "qwq_data",
            "manifestDigest": f"sha256:{'2' * 64}",
            "mediaManifestDigest": f"sha256:{'3' * 64}",
            "importRunId": f"import-{env}",
            "verifyRunId": f"verify-{env}",
            "readinessReceiptRef": (
                f"env/{env}/runs/data-release/release-video-a/verify-{env}/"
                "release-readiness.json"
            ),
        },
        "media": {
            "publicSliceKey": "media/video/s/release-video/post/v1/canary.mp4",
            "assetId": "media-canary-seek-125s",
            "assetVersion": 1,
            "probeHash": f"sha256:{'1' * 64}",
        },
        "post": {
            "postId": "release_video_canary",
        },
        "serviceEvidence": {
            "videoRange": {
                "statusCode": 206,
                "mimeType": "video/mp4",
                "reportPath": ".qwq_output/env/gamma/runs/range.json",
            },
        },
        "uiEvidence": {
            "stageRendered": True,
            "playerReady": True,
            "playerError": False,
            "reportPath": ".qwq_output/env/gamma/runs/report.json",
            "screenshotPath": ".qwq_output/env/gamma/runs/after.png",
            "recordingPath": ".qwq_output/env/gamma/runs/playback.mp4",
            "seekTargetsVerified": True,
            "nativeFirstFrame": True,
            "nativeSeekSettled": True,
            "nativeEvidenceFromPhysicalAndroidDevice": True,
            "nativeEvidenceDevicePlatform": "android",
            "nativeEvidenceDeviceEmulator": False,
            "nativePlaybackRawLogPath": ".qwq_output/env/gamma/runs/patrol.log",
            "physicalIosPatrolPassed": True,
            "seekEvidenceSource": "native_settled",
            "qoeReadbackPath": ".qwq_output/env/gamma/runs/qoe.json",
            "perfettoTracePath": ".qwq_output/env/gamma/runs/perfetto.trace",
            "perfettoSummaryPath": ".qwq_output/env/gamma/runs/perfetto-summary.json",
            "iosPerformanceTracePath": (
                ".qwq_output/env/gamma/runs/ios-performance.trace"
            ),
            "iosPerformanceSummaryPath": (
                ".qwq_output/env/gamma/runs/ios-performance-summary.json"
            ),
        },
    }


def _qoe_row(network_class: str) -> dict[str, object]:
    return {
        "devicePlatform": "android",
        "networkClass": network_class,
        "sampleCount": 200,
        "nativeFirstFrameSuccessCount": 200,
        "nativeFirstFrameSuccessRate": 1.0,
        "ttffP95Ms": 900 if network_class == "wifi" else 1800,
        "seekCount": 200,
        "seekFailureCount": 0,
        "seekFailureRate": 0.0,
        "seekSettleP95Ms": 800 if network_class == "wifi" else 1600,
        "droppedFrames": 1,
        "processedVideoFrames": 1000,
        "audioUnderrunCount": 0,
        "rebufferSessionCount": 1,
        "rebufferSessionRate": 0.005,
        "rebufferMs": 1000,
        "effectivePlaybackMs": 200000,
        "rebufferTimeRatio": 0.005,
        "terminalFailureCount": 0,
        "terminalFailureRate": 0.0,
        "durationMismatchCount": 0,
        "seekEvidenceSource": "native_settled",
    }


def _materialize_valid_artifacts(
    artifact_root: Path,
    evidence: dict[str, object],
) -> None:
    ui = evidence["uiEvidence"]
    service = evidence["serviceEvidence"]
    assert isinstance(ui, dict)
    assert isinstance(service, dict)
    video_range = service["videoRange"]
    assert isinstance(video_range, dict)

    def resolve(value: object) -> Path:
        path = artifact_root / str(value)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    resolve(video_range["reportPath"]).write_text(
        json.dumps(
            {
                "schema": "quwoquan_ops.release_video_delivery_evidence",
                "status": "passed",
                "capturedAt": "2026-07-16T00:00:30Z",
                "environment": evidence["environment"]["env"],
                "target": evidence["environment"]["target"],
                "rolloutStage": evidence["environment"]["rolloutStage"],
                "release": {
                    **evidence["release"],
                },
                "video": {
                    "workId": evidence["post"]["postId"],
                    "postId": evidence["post"]["postId"],
                    "postRef": "video/travel/canary/1",
                    "assetId": evidence["media"]["assetId"],
                    "assetVersion": evidence["media"]["assetVersion"],
                    "publicSliceKey": evidence["media"]["publicSliceKey"],
                    "publicUrl": "https://cdn.gamma.example.invalid/media/video/s/release-video/post/v1/canary.mp4",
                    "expectedMimeType": "video/mp4",
                    "expectedBytes": 4,
                    "expectedHash": evidence["media"]["probeHash"],
                },
                "delivery": {
                    "tlsSystemTrust": True,
                    "requestPath": "/media/video/s/release-video/post/v1/canary.mp4",
                    "requestQuery": "",
                    "fullStatus": 200,
                    "rangeStatus": 206,
                    "mimeType": "video/mp4",
                    "rangeMimeType": "video/mp4",
                    "contentLength": 4,
                    "observedBytes": 4,
                    "contentRange": "bytes 0-3/4",
                    "rangeBytes": 4,
                    "etag": "release-video-a",
                    "rangeEtag": "release-video-a",
                    "observedHash": evidence["media"]["probeHash"],
                    "rangeSha256": f"sha256:{'4' * 64}",
                    "cacheControl": "public, max-age=31536000, immutable",
                    "rangeCacheControl": "public, max-age=31536000, immutable",
                    "corsAllowOrigin": "*",
                    "rangeCorsAllowOrigin": "*",
                    "cacheKey": "/media/video/s/release-video/post/v1/canary.mp4",
                    "rangeCacheKey": "/media/video/s/release-video/post/v1/canary.mp4",
                    "signedQueryStatus": 200,
                    "signedQueryCacheControl": "no-store",
                    "signedQueryCacheKey": "",
                },
                "playback": {
                    "durationMs": 12_500,
                    "firstFrameDecoded": True,
                },
                "rangeStatus": 206,
                "contentType": "video/mp4",
                "publicSliceKey": evidence["media"]["publicSliceKey"],
                "videoAuthority": evidence["environment"]["mediaVideoBaseUrl"],
            }
        ),
        encoding="utf-8",
    )
    native_log = resolve(ui["nativePlaybackRawLogPath"])
    native_log.write_text(
        (
            "QWQ_VIDEO_PLAYBACK_EVIDENCE "
            '{"nativeFirstFrame":true,"nativeSeekSettled":true}\n'
        ),
        encoding="utf-8",
    )
    resolve(ui["reportPath"]).write_text(
        json.dumps(
            {
                "status": "passed",
                "runs": [
                    {
                        "exitCode": 0,
                        "device": {
                            "targetPlatform": "android-arm64",
                            "emulator": False,
                        },
                        "evidence": {
                            "rawLogPath": ui["nativePlaybackRawLogPath"],
                        },
                    },
                    {
                        "exitCode": 0,
                        "device": {
                            "targetPlatform": "ios",
                            "emulator": False,
                        },
                        "evidence": {},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    resolve(ui["screenshotPath"]).write_bytes(b"png")
    resolve(ui["recordingPath"]).write_bytes(b"mp4")
    trace = resolve(ui["perfettoTracePath"])
    trace.write_bytes(b"perfetto-trace")
    performance_summary = {
        "schema": "homepage-content-performance-evidence",
        "scenario": "homepage_long_scroll_video",
        "status": "passed",
        "skipped": False,
        "commitSha": evidence["environment"]["commitSha"],
        "releaseId": evidence["release"]["releaseId"],
        "samplesFromProductionReporter": True,
        "scrollPages": 8,
        "retainedBoundaryCrossed": True,
        "prependVerified": True,
        "channelSwitchVerified": True,
        "viewerRoundTripVerified": True,
        "memoryPressureVerified": True,
        "mainThreadStallMaxMs": 120,
        "bufferOwnershipErrorCount": 0,
        "sampledFrames": 1000,
        "jankyFrames": 2,
        "worstFrameMs": 28,
        "worstBuildFrameMs": 11,
        "worstRasterFrameMs": 13,
        "peakResidentMemoryBytes": 180_000_000,
        "memoryBudgetBytes": 256_000_000,
        "activeVideoControllerMax": 2,
        "activeVideoControllerLimit": 2,
        "mediaDownloadActiveMax": 2,
        "mediaDownloadActiveLimit": 2,
        "mediaDownloadQueuedMax": 3,
        "mediaDownloadInflightMax": 2,
        "cacheSizeBytesMax": 80_000_000,
        "cacheSizeBytesLimit": 96_000_000,
    }
    android_summary = dict(performance_summary)
    android_summary.update(
        {
            "device": {
                "id": "physical-android-1",
                "platform": "android",
                "physical": True,
            },
            "sourceTraceSha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
        }
    )
    resolve(ui["perfettoSummaryPath"]).write_text(
        json.dumps(android_summary), encoding="utf-8"
    )
    ios_trace = resolve(ui["iosPerformanceTracePath"])
    ios_trace.write_bytes(b"ios-instruments-trace")
    ios_summary = dict(performance_summary)
    ios_summary.update(
        {
            "device": {
                "id": "physical-ios-1",
                "platform": "ios",
                "physical": True,
            },
            "sourceTraceSha256": hashlib.sha256(
                ios_trace.read_bytes()
            ).hexdigest(),
        }
    )
    resolve(ui["iosPerformanceSummaryPath"]).write_text(
        json.dumps(ios_summary), encoding="utf-8"
    )
    resolve(ui["qoeReadbackPath"]).write_text(
        json.dumps(
            {
                "source": "elasticsearch",
                "eventType": "video_playback_qoe",
                "status": "passed",
                "rows": [_qoe_row("wifi"), _qoe_row("cellular")],
            }
        ),
        encoding="utf-8",
    )


class RuntimeMediaT4EvidenceContractTest(unittest.TestCase):
    def test_accepts_non_dry_run_gamma_ready_report(self) -> None:
        self.assertEqual(validate_evidence_document(_report()), [])

    def test_release_gate_rejects_single_environment_report(self) -> None:
        issues = validate_evidence_document(_report(), require_matrix=True)

        self.assertTrue(any("四环境矩阵报告" in issue for issue in issues), issues)

    def test_rejects_missing_native_player_ready_evidence(self) -> None:
        evidence = _report()
        evidence["uiEvidence"]["playerReady"] = False  # type: ignore[index]

        issues = validate_evidence_document(evidence)

        self.assertTrue(any("playerReady" in issue for issue in issues), issues)

    def test_rejects_emulator_or_controller_only_native_evidence(self) -> None:
        evidence = _report()
        evidence["uiEvidence"]["nativeFirstFrame"] = False  # type: ignore[index]
        evidence["uiEvidence"]["nativeSeekSettled"] = False  # type: ignore[index]
        evidence["uiEvidence"]["nativeEvidenceFromPhysicalAndroidDevice"] = False  # type: ignore[index]
        evidence["uiEvidence"]["nativeEvidenceDeviceEmulator"] = True  # type: ignore[index]
        evidence["uiEvidence"]["seekEvidenceSource"] = "controller_command_completion"  # type: ignore[index]

        issues = validate_evidence_document(evidence)

        self.assertTrue(any("nativeFirstFrame" in issue for issue in issues), issues)
        self.assertTrue(any("nativeSeekSettled" in issue for issue in issues), issues)
        self.assertTrue(
            any("nativeEvidenceFromPhysicalAndroidDevice" in issue for issue in issues),
            issues,
        )
        self.assertTrue(any("seekEvidenceSource" in issue for issue in issues), issues)

    def test_artifact_validation_requires_device_owned_patrol_log(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            artifact_root = Path(temporary_dir)
            evidence = _report()
            ui = evidence["uiEvidence"]  # type: ignore[index]
            assert isinstance(ui, dict)
            _materialize_valid_artifacts(artifact_root, evidence)
            native_log = artifact_root / str(ui["nativePlaybackRawLogPath"])

            self.assertEqual(
                validate_evidence_document(
                    evidence,
                    check_artifacts=True,
                    artifact_root=artifact_root,
                ),
                [],
            )

            native_log.write_text("controller ready\n", encoding="utf-8")
            issues = validate_evidence_document(
                evidence,
                check_artifacts=True,
                artifact_root=artifact_root,
            )

        self.assertTrue(
            any("未从声明的原始日志证明首帧与 seek settle" in issue for issue in issues),
            issues,
        )

    def test_rejects_missing_or_noncanonical_release_receipt_identity(self) -> None:
        evidence = _report()
        evidence["release"]["importRunId"] = ""  # type: ignore[index]
        evidence["release"]["readinessReceiptRef"] = "parallel/t4.json"  # type: ignore[index]

        issues = validate_evidence_document(evidence)

        self.assertTrue(any("release.importRunId" in issue for issue in issues), issues)
        self.assertTrue(any("canonical receipt" in issue for issue in issues), issues)

    def test_artifact_validation_rejects_preflight_release_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            artifact_root = Path(temporary_dir)
            evidence = _report()
            _materialize_valid_artifacts(artifact_root, evidence)
            range_ref = evidence["serviceEvidence"]["videoRange"]["reportPath"]  # type: ignore[index]
            range_path = artifact_root / str(range_ref)
            range_report = json.loads(range_path.read_text(encoding="utf-8"))
            range_report["release"]["importRunId"] = "parallel-import"
            range_path.write_text(json.dumps(range_report), encoding="utf-8")

            issues = validate_evidence_document(
                evidence,
                check_artifacts=True,
                artifact_root=artifact_root,
            )

        self.assertTrue(
            any("Range report.release.importRunId 与 T4 release 不一致" in issue for issue in issues),
            issues,
        )

    def test_artifact_validation_requires_physical_ios_success_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            artifact_root = Path(temporary_dir)
            evidence = _report()
            _materialize_valid_artifacts(artifact_root, evidence)
            ui = evidence["uiEvidence"]
            assert isinstance(ui, dict)
            patrol_path = artifact_root / str(ui["reportPath"])
            patrol = json.loads(patrol_path.read_text(encoding="utf-8"))
            patrol["runs"] = patrol["runs"][:1]
            patrol_path.write_text(json.dumps(patrol), encoding="utf-8")

            issues = validate_evidence_document(
                evidence,
                check_artifacts=True,
                artifact_root=artifact_root,
            )

        self.assertTrue(any("缺少物理 iOS 成功 run" in issue for issue in issues), issues)

    def test_artifact_validation_requires_physical_ios_performance_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            artifact_root = Path(temporary_dir)
            evidence = _report()
            _materialize_valid_artifacts(artifact_root, evidence)
            ui = evidence["uiEvidence"]
            assert isinstance(ui, dict)
            summary_path = artifact_root / str(ui["iosPerformanceSummaryPath"])
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["device"] = {
                "id": "ios-simulator",
                "platform": "ios",
                "physical": False,
            }
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            issues = validate_evidence_document(
                evidence,
                check_artifacts=True,
                artifact_root=artifact_root,
            )

        self.assertTrue(
            any("iOS performance summary.device 必须绑定物理 ios 设备" in issue for issue in issues),
            issues,
        )

    def test_artifact_validation_recomputes_perfetto_hash_and_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            artifact_root = Path(temporary_dir)
            evidence = _report()
            _materialize_valid_artifacts(artifact_root, evidence)
            ui = evidence["uiEvidence"]
            assert isinstance(ui, dict)
            summary_path = artifact_root / str(ui["perfettoSummaryPath"])
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["sourceTraceSha256"] = "0" * 64
            summary["mainThreadStallMaxMs"] = 1000
            summary["bufferOwnershipErrorCount"] = 1
            summary["jankyFrames"] = 10
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            issues = validate_evidence_document(
                evidence,
                check_artifacts=True,
                artifact_root=artifact_root,
            )

        self.assertTrue(any("sourceTraceSha256" in issue for issue in issues), issues)
        self.assertTrue(any("mainThreadStallMaxMs" in issue for issue in issues), issues)
        self.assertTrue(any("bufferOwnershipErrorCount" in issue for issue in issues), issues)
        self.assertTrue(any("jankyFrames/sampledFrames" in issue for issue in issues), issues)

    def test_artifact_validation_rejects_incomplete_or_skipped_performance_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            artifact_root = Path(temporary_dir)
            evidence = _report()
            _materialize_valid_artifacts(artifact_root, evidence)
            ui = evidence["uiEvidence"]
            assert isinstance(ui, dict)
            summary_path = artifact_root / str(ui["perfettoSummaryPath"])
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["skipped"] = True
            summary.pop("worstBuildFrameMs")
            summary["activeVideoControllerMax"] = 3
            summary["peakResidentMemoryBytes"] = 300_000_000
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            issues = validate_evidence_document(
                evidence,
                check_artifacts=True,
                artifact_root=artifact_root,
            )

        self.assertTrue(any("非 skip" in issue for issue in issues), issues)
        self.assertTrue(any("worstBuildFrameMs" in issue for issue in issues), issues)
        self.assertTrue(any("activeVideoControllerMax" in issue for issue in issues), issues)
        self.assertTrue(any("peakResidentMemoryBytes" in issue for issue in issues), issues)

    def test_artifact_validation_recomputes_sls_qoe_rates_and_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            artifact_root = Path(temporary_dir)
            evidence = _report()
            _materialize_valid_artifacts(artifact_root, evidence)
            ui = evidence["uiEvidence"]
            assert isinstance(ui, dict)
            qoe_path = artifact_root / str(ui["qoeReadbackPath"])
            qoe = json.loads(qoe_path.read_text(encoding="utf-8"))
            qoe["rows"][0].pop("effectivePlaybackMs")
            qoe["rows"][1]["droppedFrames"] = 10
            qoe["rows"][1]["seekFailureRate"] = 0.5
            qoe_path.write_text(json.dumps(qoe), encoding="utf-8")

            issues = validate_evidence_document(
                evidence,
                check_artifacts=True,
                artifact_root=artifact_root,
            )

        self.assertTrue(any("effectivePlaybackMs" in issue for issue in issues), issues)
        self.assertTrue(
            any("droppedFrames/processedVideoFrames" in issue for issue in issues),
            issues,
        )
        self.assertTrue(any("seekFailureRate" in issue for issue in issues), issues)

    def test_artifact_validation_rejects_paths_outside_evidence_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            base = Path(temporary_dir)
            artifact_root = base / "evidence-root"
            artifact_root.mkdir()
            evidence = _report()
            _materialize_valid_artifacts(artifact_root, evidence)
            outside = base / "forged.png"
            outside.write_bytes(b"png")
            evidence["uiEvidence"]["screenshotPath"] = str(outside)  # type: ignore[index]

            issues = validate_evidence_document(
                evidence,
                check_artifacts=True,
                artifact_root=artifact_root,
            )

        self.assertTrue(any("必须位于证据根目录内" in issue for issue in issues), issues)

    def test_artifact_validation_rejects_legacy_range_only_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            artifact_root = Path(temporary_dir)
            evidence = _report()
            _materialize_valid_artifacts(artifact_root, evidence)
            range_ref = evidence["serviceEvidence"]["videoRange"]["reportPath"]  # type: ignore[index]
            range_path = artifact_root / str(range_ref)
            range_path.write_text(
                json.dumps({"rangeStatus": 206, "contentType": "video/mp4"}),
                encoding="utf-8",
            )

            issues = validate_evidence_document(
                evidence,
                check_artifacts=True,
                artifact_root=artifact_root,
            )

        self.assertTrue(
            any("release-bound video delivery evidence" in issue for issue in issues),
            issues,
        )
        self.assertTrue(any("HTTP 200" in issue for issue in issues), issues)
        self.assertTrue(any("解码首帧" in issue for issue in issues), issues)

    def test_rejects_missing_video_stage_evidence(self) -> None:
        evidence = _report()
        evidence["uiEvidence"]["stageRendered"] = False  # type: ignore[index]

        issues = validate_evidence_document(evidence)

        self.assertTrue(any("stageRendered" in issue for issue in issues), issues)

    def test_rejects_dry_run_and_non_range_video_evidence(self) -> None:
        evidence = _report()
        evidence["dryRun"] = True
        evidence["serviceEvidence"]["videoRange"]["statusCode"] = 200  # type: ignore[index]

        issues = validate_evidence_document(evidence)

        self.assertTrue(any("dryRun" in issue for issue in issues), issues)
        self.assertTrue(any("statusCode" in issue for issue in issues), issues)

    def test_rejects_production_fixture_and_wrong_rollout_stage(self) -> None:
        evidence = _report(target="prod-hosted", env="prod")
        evidence["environment"]["rolloutStage"] = "local"  # type: ignore[index]
        evidence["media"]["publicSliceKey"] = "media/video/s/fixture-video/post/sample.mp4"  # type: ignore[index]

        issues = validate_evidence_document(evidence)

        self.assertTrue(any("gray-initial|carry-on|full" in issue for issue in issues), issues)
        self.assertTrue(any("fixture/mock/seed/test" in issue for issue in issues), issues)

    def test_matrix_validates_every_report(self) -> None:
        alpha = _report(target="alpha-local", env="alpha")
        beta = _report(target="beta-local", env="beta")
        gamma = _report()
        production = [
            _report(target="prod-hosted", env="prod", stage=stage)
            for stage in ("gray-initial", "carry-on", "full")
        ]
        alpha["environment"]["configHash"] = _sha256_digest("matrix-config")  # type: ignore[index]
        beta["environment"]["configHash"] = _sha256_digest("matrix-config")  # type: ignore[index]
        gamma["environment"]["configHash"] = _sha256_digest("matrix-config")  # type: ignore[index]
        matrix = {
            "schema": MATRIX_SCHEMA,
            "scenario": MATRIX_SCENARIO,
            "reports": [alpha, beta, gamma, *production],
        }

        self.assertEqual(validate_evidence_document(matrix, require_matrix=True), [])

        broken = copy.deepcopy(matrix)
        broken["reports"][1]["uiEvidence"]["playerError"] = True
        issues = validate_evidence_document(broken)
        self.assertTrue(any("reports[1].uiEvidence.playerError" in issue for issue in issues))

        broken_prod = copy.deepcopy(matrix)
        broken_prod["reports"][-1]["environment"]["configHash"] = _sha256_digest(
            "different-matrix-config"
        )
        broken_prod["reports"][-1]["post"]["postId"] = "another_release_canary"
        issues = validate_evidence_document(broken_prod)
        self.assertTrue(any("production configHash" in issue for issue in issues), issues)
        self.assertTrue(any("同一 postId" in issue for issue in issues), issues)

        broken_release = copy.deepcopy(matrix)
        broken_release["reports"][2]["release"]["manifestDigest"] = f"sha256:{'9' * 64}"
        issues = validate_evidence_document(broken_release)
        self.assertTrue(any("同一 releaseId/manifestDigest" in issue for issue in issues), issues)

    def test_matrix_rejects_missing_and_duplicate_targets(self) -> None:
        duplicate = _report(target="alpha-local", env="alpha")
        matrix = {
            "schema": MATRIX_SCHEMA,
            "scenario": MATRIX_SCENARIO,
            "reports": [duplicate, copy.deepcopy(duplicate)],
        }

        issues = validate_evidence_document(matrix)

        self.assertTrue(any("重复 target/stage" in issue for issue in issues), issues)
        self.assertTrue(any("beta-local/local" in issue for issue in issues), issues)
        self.assertTrue(any("prod-hosted/carry-on" in issue for issue in issues), issues)


if __name__ == "__main__":
    unittest.main()
