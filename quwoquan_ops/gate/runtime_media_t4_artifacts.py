"""runtime-media T4 归档证据的可重放校验。"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import yaml

from quwoquan_ops.gate.runtime_media_t4_qoe import validate_qoe_payload


NATIVE_EVIDENCE_PREFIX = "QWQ_VIDEO_PLAYBACK_EVIDENCE "
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_METRIC_CATALOG = (
    REPO_ROOT
    / "quwoquan_service/services/product-ops-service/contracts/product_ops/"
    "event_record/golden_metric_catalog.yaml"
)


def _resolve_artifact_path(artifact_root: Path, raw_value: object) -> Path:
    raw = str(raw_value or "").strip()
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (artifact_root.resolve() / candidate).resolve()


def _require_artifact(
    artifact_root: Path,
    raw_value: object,
    label: str,
    issues: list[str],
) -> Path | None:
    raw = str(raw_value or "").strip()
    if not raw:
        issues.append(f"{label} 不能为空")
        return None
    root = artifact_root.resolve()
    path = _resolve_artifact_path(root, raw)
    try:
        path.relative_to(root)
    except ValueError:
        issues.append(f"{label} 必须位于证据根目录内")
        return None
    if not path.is_file():
        issues.append(f"{label} 文件不存在: {raw}")
        return None
    return path


def _load_json_object(path: Path, label: str, issues: list[str]) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        issues.append(f"{label} 不是可解析 JSON: {error}")
        return None
    if not isinstance(value, dict):
        issues.append(f"{label} 顶层必须是 object")
        return None
    return value


def _native_playback_facts(path: Path) -> dict[str, bool]:
    native_first_frame = False
    native_seek_settled = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        marker_index = line.find(NATIVE_EVIDENCE_PREFIX)
        if marker_index < 0:
            continue
        raw_payload = line[marker_index + len(NATIVE_EVIDENCE_PREFIX) :].strip()
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        native_first_frame = native_first_frame or payload.get("nativeFirstFrame") is True
        native_seek_settled = native_seek_settled or payload.get("nativeSeekSettled") is True
    return {
        "nativeFirstFrame": native_first_frame,
        "nativeSeekSettled": native_seek_settled,
    }


def _validate_range_artifact(
    report: dict[str, Any],
    artifact_root: Path,
    issues: list[str],
    prefix: str,
) -> None:
    service = report.get("serviceEvidence")
    service = service if isinstance(service, dict) else {}
    video_range = service.get("videoRange")
    video_range = video_range if isinstance(video_range, dict) else {}
    artifact = _require_artifact(
        artifact_root,
        video_range.get("reportPath"),
        f"{prefix}.serviceEvidence.videoRange.reportPath",
        issues,
    )
    if artifact is None:
        return
    payload = _load_json_object(artifact, f"{prefix}.Range report", issues)
    if payload is None:
        return

    if payload.get("schema") != "quwoquan_ops.release_video_delivery_evidence":
        issues.append(
            f"{prefix}.Range report 必须是 release-bound video delivery evidence"
        )
    if payload.get("status") != "passed":
        issues.append(f"{prefix}.Range report.status 必须为 passed")

    release = payload.get("release")
    release = release if isinstance(release, dict) else {}
    if release.get("sourceOwner") != "qwq_data":
        issues.append(f"{prefix}.Range report.release.sourceOwner 必须为 qwq_data")
    for field in ("manifestDigest", "mediaManifestDigest"):
        if not re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            str(release.get(field) or ""),
        ):
            issues.append(f"{prefix}.Range report.release.{field} 必须为 sha256 digest")
    if not str(release.get("releaseId") or "").strip():
        issues.append(f"{prefix}.Range report.release.releaseId 不能为空")
    if not str(release.get("verifyRunId") or "").strip():
        issues.append(f"{prefix}.Range report.release.verifyRunId 不能为空")

    report_release = report.get("release")
    report_release = report_release if isinstance(report_release, dict) else {}
    for field in (
        "releaseId",
        "sourceOwner",
        "manifestDigest",
        "mediaManifestDigest",
        "importRunId",
        "verifyRunId",
        "readinessReceiptRef",
    ):
        if release.get(field) != report_release.get(field):
            issues.append(
                f"{prefix}.Range report.release.{field} 与 T4 release 不一致"
            )

    delivery = payload.get("delivery")
    delivery = delivery if isinstance(delivery, dict) else {}
    playback = payload.get("playback")
    playback = playback if isinstance(playback, dict) else {}
    video = payload.get("video")
    video = video if isinstance(video, dict) else {}
    if delivery.get("tlsSystemTrust") is not True:
        issues.append(f"{prefix}.Range report 未证明系统 TLS 信任链")
    if delivery.get("fullStatus") != 200:
        issues.append(f"{prefix}.Range report 未证明 HTTP 200 完整对象")
    if delivery.get("rangeStatus") != 206:
        issues.append(f"{prefix}.Range report 未证明 HTTP 206")
    expected_cache_key = "/" + str(video.get("publicSliceKey") or "").lstrip("/")
    if delivery.get("requestPath") != expected_cache_key or delivery.get(
        "requestQuery"
    ) not in {"", None}:
        issues.append(f"{prefix}.Range report 公开 URL 不是唯一 path-version cache identity")
    for field in ("cacheControl", "rangeCacheControl"):
        directives = {
            item.strip().lower()
            for item in str(delivery.get(field) or "").split(",")
            if item.strip()
        }
        if not {
            "public",
            "immutable",
            "max-age=31536000",
        }.issubset(directives) or "no-store" in directives:
            issues.append(f"{prefix}.Range report.{field} 未证明 public immutable")
    for field in ("corsAllowOrigin", "rangeCorsAllowOrigin"):
        if delivery.get(field) != "*":
            issues.append(f"{prefix}.Range report.{field} 未证明 public CORS")
    for field in ("cacheKey", "rangeCacheKey"):
        if delivery.get(field) != expected_cache_key:
            issues.append(f"{prefix}.Range report.{field} 与 publicSliceKey 不一致")
    signed_cache_control = {
        item.strip().lower()
        for item in str(delivery.get("signedQueryCacheControl") or "").split(",")
        if item.strip()
    }
    if (
        "no-store" not in signed_cache_control
        or str(delivery.get("signedQueryCacheKey") or "")
    ):
        issues.append(f"{prefix}.Range report 未证明 signed query 与 public cache 隔离")
    expected_bytes = video.get("expectedBytes")
    if (
        not isinstance(expected_bytes, int)
        or isinstance(expected_bytes, bool)
        or expected_bytes <= 0
        or delivery.get("contentLength") != expected_bytes
        or delivery.get("observedBytes") != expected_bytes
    ):
        issues.append(f"{prefix}.Range report 完整对象长度未绑定 immutable release")
    expected_hash = str(video.get("expectedHash") or "")
    if (
        not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_hash)
        or delivery.get("observedHash") != expected_hash
    ):
        issues.append(f"{prefix}.Range report 完整对象 hash 未绑定 immutable release")
    etag = str(delivery.get("etag") or "").strip()
    range_etag = str(delivery.get("rangeEtag") or "").strip()
    if not etag or not range_etag or etag != range_etag:
        issues.append(f"{prefix}.Range report 未证明稳定 ETag")
    if not str(delivery.get("contentRange") or "").startswith("bytes 0-"):
        issues.append(f"{prefix}.Range report 未证明 Content-Range")
    duration_ms = playback.get("durationMs")
    if (
        not isinstance(duration_ms, int)
        or isinstance(duration_ms, bool)
        or duration_ms <= 0
    ):
        issues.append(f"{prefix}.Range report 未证明正数视频时长")
    if playback.get("firstFrameDecoded") is not True:
        issues.append(f"{prefix}.Range report 未证明服务侧解码首帧")

    report_environment = report.get("environment")
    report_environment = (
        report_environment if isinstance(report_environment, dict) else {}
    )
    if payload.get("target") != report_environment.get("target"):
        issues.append(f"{prefix}.Range report.target 与 T4 target 不一致")
    report_media = report.get("media")
    report_media = report_media if isinstance(report_media, dict) else {}
    report_post = report.get("post")
    report_post = report_post if isinstance(report_post, dict) else {}
    for evidence_field, report_field in (
        ("publicSliceKey", "publicSliceKey"),
        ("assetId", "assetId"),
        ("assetVersion", "assetVersion"),
        ("expectedHash", "probeHash"),
    ):
        if video.get(evidence_field) != report_media.get(report_field):
            issues.append(
                f"{prefix}.Range report.video.{evidence_field} 与 T4 media 不一致"
            )
    if video.get("postId") != report_post.get("postId"):
        issues.append(f"{prefix}.Range report.video.postId 与 T4 post 不一致")

    actual_status: object = delivery.get("rangeStatus", payload.get("rangeStatus"))
    actual_mime: object = delivery.get("mimeType", payload.get("contentType"))
    actual_slice: object = video.get("publicSliceKey", payload.get("publicSliceKey"))

    if actual_status != 206:
        issues.append(f"{prefix}.Range report 未证明 HTTP 206")
    if not str(actual_mime or "").lower().startswith("video/"):
        issues.append(f"{prefix}.Range report 未证明 video/* MIME")
    if video_range.get("statusCode") != actual_status:
        issues.append(f"{prefix}.videoRange.statusCode 与 Range report 不一致")
    if str(video_range.get("mimeType") or "") != str(actual_mime or ""):
        issues.append(f"{prefix}.videoRange.mimeType 与 Range report 不一致")
    if actual_slice is not None:
        media = report.get("media")
        media = media if isinstance(media, dict) else {}
        if str(actual_slice or "") != str(media.get("publicSliceKey") or ""):
            issues.append(f"{prefix}.Range report publicSliceKey 与 media 不一致")


def _validate_patrol_artifact(
    report: dict[str, Any],
    artifact_root: Path,
    issues: list[str],
    prefix: str,
) -> None:
    ui = report.get("uiEvidence")
    ui = ui if isinstance(ui, dict) else {}
    artifact = _require_artifact(
        artifact_root,
        ui.get("reportPath"),
        f"{prefix}.uiEvidence.reportPath",
        issues,
    )
    if artifact is None:
        return
    payload = _load_json_object(artifact, f"{prefix}.Patrol report", issues)
    if payload is None:
        return
    if payload.get("status") != "passed":
        issues.append(f"{prefix}.Patrol report.status 必须为 passed")
    runs = payload.get("runs")
    if not isinstance(runs, list):
        issues.append(f"{prefix}.Patrol report.runs 必须是数组")
        return

    physical_android_runs: list[dict[str, Any]] = []
    physical_ios_runs: list[dict[str, Any]] = []
    for run in runs:
        if not isinstance(run, dict) or run.get("exitCode") != 0:
            continue
        device = run.get("device")
        if not isinstance(device, dict) or device.get("emulator") is not False:
            continue
        platform = str(device.get("targetPlatform") or "").lower()
        if platform.startswith("android"):
            physical_android_runs.append(run)
        elif platform.startswith("ios"):
            physical_ios_runs.append(run)

    if not physical_android_runs:
        issues.append(f"{prefix}.Patrol report 缺少物理 Android 成功 run")
    if not physical_ios_runs:
        issues.append(f"{prefix}.Patrol report 缺少物理 iOS 成功 run")
    if ui.get("physicalIosPatrolPassed") is not True:
        issues.append(f"{prefix}.uiEvidence.physicalIosPatrolPassed 必须为 true")

    declared_raw_log = _require_artifact(
        artifact_root,
        ui.get("nativePlaybackRawLogPath"),
        f"{prefix}.uiEvidence.nativePlaybackRawLogPath",
        issues,
    )
    native_run_verified = False
    for run in physical_android_runs:
        evidence = run.get("evidence")
        if not isinstance(evidence, dict):
            continue
        raw_log = _require_artifact(
            artifact_root,
            evidence.get("rawLogPath"),
            f"{prefix}.Patrol Android run.evidence.rawLogPath",
            issues,
        )
        if raw_log is None:
            continue
        facts = _native_playback_facts(raw_log)
        if (
            facts["nativeFirstFrame"]
            and facts["nativeSeekSettled"]
            and declared_raw_log is not None
            and raw_log.resolve() == declared_raw_log.resolve()
        ):
            native_run_verified = True
            break
    if not native_run_verified:
        issues.append(
            f"{prefix}.Patrol report 物理 Android run 未从声明的原始日志证明首帧与 seek settle"
        )


def _normalized_sha256(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized.startswith("sha256:"):
        normalized = normalized.removeprefix("sha256:")
    return normalized


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _homepage_jank_ratio_target() -> float:
    catalog = yaml.safe_load(GOLDEN_METRIC_CATALOG.read_text(encoding="utf-8"))
    metrics = catalog.get("metrics") if isinstance(catalog, dict) else None
    if not isinstance(metrics, list):
        raise ValueError("golden metric catalog missing metrics")
    for metric in metrics:
        if isinstance(metric, dict) and metric.get("metric_id") == "app_jank_frame_rate":
            target = metric.get("target")
            value = target.get("value") if isinstance(target, dict) else None
            if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value < 1:
                return float(value)
    raise ValueError("golden metric catalog missing app_jank_frame_rate target")


def _validate_homepage_performance_artifacts(
    report: dict[str, Any],
    artifact_root: Path,
    issues: list[str],
    prefix: str,
    *,
    trace_field: str,
    summary_field: str,
    label: str,
    platform: str,
) -> None:
    ui = report.get("uiEvidence")
    ui = ui if isinstance(ui, dict) else {}
    trace = _require_artifact(
        artifact_root,
        ui.get(trace_field),
        f"{prefix}.uiEvidence.{trace_field}",
        issues,
    )
    summary_path = _require_artifact(
        artifact_root,
        ui.get(summary_field),
        f"{prefix}.uiEvidence.{summary_field}",
        issues,
    )
    if trace is None or summary_path is None:
        return
    if trace.stat().st_size <= 0:
        issues.append(f"{prefix}.{label} trace 不能为空")
        return
    summary = _load_json_object(summary_path, f"{prefix}.{label} summary", issues)
    if summary is None:
        return
    actual_hash = hashlib.sha256(trace.read_bytes()).hexdigest()
    declared_hash = _normalized_sha256(summary.get("sourceTraceSha256"))
    if not SHA256_RE.fullmatch(declared_hash) or declared_hash != actual_hash:
        issues.append(f"{prefix}.{label} summary.sourceTraceSha256 与 trace 不一致")

    if summary.get("schema") != "homepage-content-performance-evidence":
        issues.append(
            f"{prefix}.{label} summary.schema 必须为 "
            "homepage-content-performance-evidence"
        )
    if summary.get("scenario") != "homepage_long_scroll_video":
        issues.append(
            f"{prefix}.{label} summary.scenario 必须为 homepage_long_scroll_video"
        )
    if summary.get("status") != "passed" or summary.get("skipped") is not False:
        issues.append(f"{prefix}.{label} summary 必须为非 skip 的 passed 场景")

    environment = report.get("environment")
    environment = environment if isinstance(environment, dict) else {}
    release = report.get("release")
    release = release if isinstance(release, dict) else {}
    if summary.get("commitSha") != environment.get("commitSha"):
        issues.append(f"{prefix}.{label} summary.commitSha 与候选报告不一致")
    if summary.get("releaseId") != release.get("releaseId"):
        issues.append(f"{prefix}.{label} summary.releaseId 与候选报告不一致")
    device = summary.get("device")
    device = device if isinstance(device, dict) else {}
    if not str(device.get("id") or "").strip():
        issues.append(f"{prefix}.{label} summary.device.id 必须非空")
    if device.get("platform") != platform or device.get("physical") is not True:
        issues.append(
            f"{prefix}.{label} summary.device 必须绑定物理 {platform} 设备"
        )
    if summary.get("samplesFromProductionReporter") is not True:
        issues.append(
            f"{prefix}.{label} summary 必须证明样本来自生产 typed reporter"
        )

    required_scenarios = {
        "scrollPages": 8,
        "retainedBoundaryCrossed": True,
        "prependVerified": True,
        "channelSwitchVerified": True,
        "viewerRoundTripVerified": True,
        "memoryPressureVerified": True,
    }
    for field, expected in required_scenarios.items():
        value = summary.get(field)
        if isinstance(expected, int) and not isinstance(expected, bool):
            if _integer(value) is None or int(value) < expected:
                issues.append(f"{prefix}.{label} summary.{field} 必须 >= {expected}")
        elif value is not expected:
            issues.append(f"{prefix}.{label} summary.{field} 必须为 true")

    stall_ms = _number(summary.get("mainThreadStallMaxMs"))
    ownership_errors = _integer(summary.get("bufferOwnershipErrorCount"))
    sampled_frames = _integer(summary.get("sampledFrames"))
    janky_frames = _integer(summary.get("jankyFrames"))
    worst_frame_ms = _number(summary.get("worstFrameMs"))
    worst_build_ms = _number(summary.get("worstBuildFrameMs"))
    worst_raster_ms = _number(summary.get("worstRasterFrameMs"))
    if stall_ms is None or stall_ms < 0 or stall_ms >= 1000:
        issues.append(f"{prefix}.{label} mainThreadStallMaxMs 必须在 [0,1000) 内")
    if ownership_errors != 0:
        issues.append(f"{prefix}.{label} bufferOwnershipErrorCount 必须为 0")
    if sampled_frames is None or sampled_frames <= 0:
        issues.append(f"{prefix}.{label} sampledFrames 必须为正整数")
    if janky_frames is None or janky_frames < 0:
        issues.append(f"{prefix}.{label} jankyFrames 必须为非负整数")
    for field, value in (
        ("worstFrameMs", worst_frame_ms),
        ("worstBuildFrameMs", worst_build_ms),
        ("worstRasterFrameMs", worst_raster_ms),
    ):
        if value is None or value < 0:
            issues.append(f"{prefix}.{label} {field} 必须为非负数值")
    if (
        worst_frame_ms is not None
        and worst_build_ms is not None
        and worst_raster_ms is not None
        and worst_frame_ms < max(worst_build_ms, worst_raster_ms)
    ):
        issues.append(f"{prefix}.{label} worstFrameMs 不得小于 build/raster 分项")
    if (
        sampled_frames is not None
        and sampled_frames > 0
        and janky_frames is not None
        and janky_frames >= 0
        and janky_frames / sampled_frames >= _homepage_jank_ratio_target()
    ):
        target = _homepage_jank_ratio_target()
        issues.append(
            f"{prefix}.{label} jankyFrames/sampledFrames 必须小于 "
            f"canonical target {target:.2%}",
        )

    for current_field, limit_field in (
        ("peakResidentMemoryBytes", "memoryBudgetBytes"),
        ("activeVideoControllerMax", "activeVideoControllerLimit"),
        ("mediaDownloadActiveMax", "mediaDownloadActiveLimit"),
        ("cacheSizeBytesMax", "cacheSizeBytesLimit"),
    ):
        current = _integer(summary.get(current_field))
        limit = _integer(summary.get(limit_field))
        if current is None or current < 0:
            issues.append(f"{prefix}.{label} {current_field} 必须为非负整数")
        if limit is None or limit <= 0:
            issues.append(f"{prefix}.{label} {limit_field} 必须为正整数")
        if current is not None and limit is not None and limit > 0 and current > limit:
            issues.append(f"{prefix}.{label} {current_field} 超过 {limit_field}")
    for field in ("mediaDownloadQueuedMax", "mediaDownloadInflightMax"):
        value = _integer(summary.get(field))
        if value is None or value < 0:
            issues.append(f"{prefix}.{label} {field} 必须为非负整数")


def _validate_performance_artifacts(
    report: dict[str, Any],
    artifact_root: Path,
    issues: list[str],
    prefix: str,
) -> None:
    _validate_homepage_performance_artifacts(
        report,
        artifact_root,
        issues,
        prefix,
        trace_field="perfettoTracePath",
        summary_field="perfettoSummaryPath",
        label="Perfetto",
        platform="android",
    )
    _validate_homepage_performance_artifacts(
        report,
        artifact_root,
        issues,
        prefix,
        trace_field="iosPerformanceTracePath",
        summary_field="iosPerformanceSummaryPath",
        label="iOS performance",
        platform="ios",
    )


def _validate_qoe_readback(
    report: dict[str, Any],
    artifact_root: Path,
    issues: list[str],
    prefix: str,
) -> None:
    ui = report.get("uiEvidence")
    ui = ui if isinstance(ui, dict) else {}
    artifact = _require_artifact(
        artifact_root,
        ui.get("qoeReadbackPath"),
        f"{prefix}.uiEvidence.qoeReadbackPath",
        issues,
    )
    if artifact is None:
        return
    payload = _load_json_object(artifact, f"{prefix}.QoE readback", issues)
    if payload is None:
        return
    validate_qoe_payload(payload, issues, prefix)


def validate_report_artifacts(
    report: dict[str, Any],
    artifact_root: Path,
    issues: list[str],
    prefix: str,
) -> None:
    _validate_range_artifact(report, artifact_root, issues, prefix)
    _validate_patrol_artifact(report, artifact_root, issues, prefix)
    _validate_performance_artifacts(report, artifact_root, issues, prefix)
    _validate_qoe_readback(report, artifact_root, issues, prefix)
    ui = report.get("uiEvidence")
    ui = ui if isinstance(ui, dict) else {}
    _require_artifact(
        artifact_root,
        ui.get("screenshotPath"),
        f"{prefix}.uiEvidence.screenshotPath",
        issues,
    )
    _require_artifact(
        artifact_root,
        ui.get("recordingPath"),
        f"{prefix}.uiEvidence.recordingPath",
        issues,
    )
