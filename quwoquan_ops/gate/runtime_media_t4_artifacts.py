"""runtime-media T4 归档证据的可重放校验。"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from quwoquan_ops.gate.runtime_media_t4_qoe import validate_qoe_payload


NATIVE_EVIDENCE_PREFIX = "QWQ_VIDEO_PLAYBACK_EVIDENCE "
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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

    actual_status: object = payload.get("rangeStatus")
    actual_mime: object = payload.get("contentType")
    actual_slice: object = payload.get("publicSliceKey")
    checks = payload.get("checks")
    if isinstance(checks, list):
        actual_status = None
        actual_mime = None
        for check in checks:
            if not isinstance(check, dict):
                continue
            if check.get("name") != "media-public-content-video-primary":
                continue
            actual_status = check.get("statusCode")
            actual_mime = check.get("contentType")
            break

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


def _validate_perfetto_artifacts(
    report: dict[str, Any],
    artifact_root: Path,
    issues: list[str],
    prefix: str,
) -> None:
    ui = report.get("uiEvidence")
    ui = ui if isinstance(ui, dict) else {}
    trace = _require_artifact(
        artifact_root,
        ui.get("perfettoTracePath"),
        f"{prefix}.uiEvidence.perfettoTracePath",
        issues,
    )
    summary_path = _require_artifact(
        artifact_root,
        ui.get("perfettoSummaryPath"),
        f"{prefix}.uiEvidence.perfettoSummaryPath",
        issues,
    )
    if trace is None or summary_path is None:
        return
    if trace.stat().st_size <= 0:
        issues.append(f"{prefix}.Perfetto trace 不能为空")
        return
    summary = _load_json_object(summary_path, f"{prefix}.Perfetto summary", issues)
    if summary is None:
        return
    actual_hash = hashlib.sha256(trace.read_bytes()).hexdigest()
    declared_hash = _normalized_sha256(summary.get("sourceTraceSha256"))
    if not SHA256_RE.fullmatch(declared_hash) or declared_hash != actual_hash:
        issues.append(f"{prefix}.Perfetto summary.sourceTraceSha256 与 trace 不一致")

    stall_ms = _number(summary.get("mainThreadStallMaxMs"))
    ownership_errors = _integer(summary.get("bufferOwnershipErrorCount"))
    sampled_frames = _integer(summary.get("sampledFrames"))
    janky_frames = _integer(summary.get("jankyFrames"))
    if stall_ms is None or stall_ms < 0 or stall_ms >= 1000:
        issues.append(f"{prefix}.Perfetto mainThreadStallMaxMs 必须在 [0,1000) 内")
    if ownership_errors != 0:
        issues.append(f"{prefix}.Perfetto bufferOwnershipErrorCount 必须为 0")
    if sampled_frames is None or sampled_frames <= 0:
        issues.append(f"{prefix}.Perfetto sampledFrames 必须为正整数")
    if janky_frames is None or janky_frames < 0:
        issues.append(f"{prefix}.Perfetto jankyFrames 必须为非负整数")
    if (
        sampled_frames is not None
        and sampled_frames > 0
        and janky_frames is not None
        and janky_frames >= 0
        and janky_frames / sampled_frames >= 0.01
    ):
        issues.append(f"{prefix}.Perfetto jankyFrames/sampledFrames 必须小于 1%")


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
    _validate_perfetto_artifacts(report, artifact_root, issues, prefix)
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
