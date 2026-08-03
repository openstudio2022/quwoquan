"""runtime-media T4 Elasticsearch QoE readback 阈值与重算合同。"""

from __future__ import annotations

import math
from typing import Any


REQUIRED_NETWORK_BUCKETS = frozenset({"wifi", "cellular"})


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _required_int(
    row: dict[str, Any],
    field: str,
    *,
    minimum: int,
    label: str,
    issues: list[str],
) -> int | None:
    value = _integer(row.get(field))
    if value is None or value < minimum:
        issues.append(f"{label}.{field} 必须是 >= {minimum} 的整数")
        return None
    return value


def _required_rate(
    row: dict[str, Any],
    field: str,
    *,
    label: str,
    issues: list[str],
) -> float | None:
    value = _number(row.get(field))
    if value is None or value < 0 or value > 1:
        issues.append(f"{label}.{field} 必须是 [0,1] 内的数值")
        return None
    return value


def _assert_rate_matches(
    *,
    actual: float | None,
    numerator: int | None,
    denominator: int | None,
    field: str,
    label: str,
    issues: list[str],
) -> None:
    if actual is None or numerator is None or denominator is None or denominator <= 0:
        return
    expected = numerator / denominator
    if not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9):
        issues.append(f"{label}.{field} 与计数重算结果不一致")


def _validate_qoe_bucket(
    row: dict[str, Any],
    network_class: str,
    issues: list[str],
    prefix: str,
) -> None:
    label = f"{prefix}.QoE[{network_class}]"
    for forbidden in ("deviceManufacturer", "deviceModel", "postId", "assetId"):
        if forbidden in row:
            issues.append(f"{label} 禁止包含高基数维度 {forbidden}")

    sample_count = _required_int(row, "sampleCount", minimum=100, label=label, issues=issues)
    seek_count = _required_int(row, "seekCount", minimum=100, label=label, issues=issues)
    effective_ms = _required_int(
        row,
        "effectivePlaybackMs",
        minimum=1,
        label=label,
        issues=issues,
    )
    first_frame_count = _required_int(
        row,
        "nativeFirstFrameSuccessCount",
        minimum=0,
        label=label,
        issues=issues,
    )
    seek_failure_count = _required_int(
        row,
        "seekFailureCount",
        minimum=0,
        label=label,
        issues=issues,
    )
    dropped_frames = _required_int(
        row,
        "droppedFrames",
        minimum=0,
        label=label,
        issues=issues,
    )
    processed_frames = _required_int(
        row,
        "processedVideoFrames",
        minimum=1,
        label=label,
        issues=issues,
    )
    audio_underruns = _required_int(
        row,
        "audioUnderrunCount",
        minimum=0,
        label=label,
        issues=issues,
    )
    rebuffer_sessions = _required_int(
        row,
        "rebufferSessionCount",
        minimum=0,
        label=label,
        issues=issues,
    )
    rebuffer_ms = _required_int(row, "rebufferMs", minimum=0, label=label, issues=issues)
    terminal_failures = _required_int(
        row,
        "terminalFailureCount",
        minimum=0,
        label=label,
        issues=issues,
    )
    duration_mismatches = _required_int(
        row,
        "durationMismatchCount",
        minimum=0,
        label=label,
        issues=issues,
    )

    first_frame_rate = _required_rate(
        row,
        "nativeFirstFrameSuccessRate",
        label=label,
        issues=issues,
    )
    seek_failure_rate = _required_rate(
        row,
        "seekFailureRate",
        label=label,
        issues=issues,
    )
    rebuffer_session_rate = _required_rate(
        row,
        "rebufferSessionRate",
        label=label,
        issues=issues,
    )
    rebuffer_time_ratio = _required_rate(
        row,
        "rebufferTimeRatio",
        label=label,
        issues=issues,
    )
    terminal_failure_rate = _required_rate(
        row,
        "terminalFailureRate",
        label=label,
        issues=issues,
    )
    ttff_p95 = _number(row.get("ttffP95Ms"))
    seek_settle_p95 = _number(row.get("seekSettleP95Ms"))

    _assert_rate_matches(
        actual=first_frame_rate,
        numerator=first_frame_count,
        denominator=sample_count,
        field="nativeFirstFrameSuccessRate",
        label=label,
        issues=issues,
    )
    _assert_rate_matches(
        actual=seek_failure_rate,
        numerator=seek_failure_count,
        denominator=seek_count,
        field="seekFailureRate",
        label=label,
        issues=issues,
    )
    _assert_rate_matches(
        actual=rebuffer_session_rate,
        numerator=rebuffer_sessions,
        denominator=sample_count,
        field="rebufferSessionRate",
        label=label,
        issues=issues,
    )
    _assert_rate_matches(
        actual=rebuffer_time_ratio,
        numerator=rebuffer_ms,
        denominator=effective_ms,
        field="rebufferTimeRatio",
        label=label,
        issues=issues,
    )
    _assert_rate_matches(
        actual=terminal_failure_rate,
        numerator=terminal_failures,
        denominator=sample_count,
        field="terminalFailureRate",
        label=label,
        issues=issues,
    )

    if first_frame_rate is not None and first_frame_rate < 0.995:
        issues.append(f"{label}.nativeFirstFrameSuccessRate 必须 >= 99.5%")
    ttff_limit = 1500 if network_class == "wifi" else 2500
    if ttff_p95 is None or ttff_p95 < 0 or ttff_p95 > ttff_limit:
        issues.append(f"{label}.ttffP95Ms 必须在 [0,{ttff_limit}] 内")
    seek_limit = 1000 if network_class == "wifi" else 2000
    if seek_settle_p95 is None or seek_settle_p95 < 0 or seek_settle_p95 > seek_limit:
        issues.append(f"{label}.seekSettleP95Ms 必须在 [0,{seek_limit}] 内")
    if seek_failure_rate is not None and seek_failure_rate >= 0.005:
        issues.append(f"{label}.seekFailureRate 必须 < 0.5%")
    if (
        dropped_frames is not None
        and processed_frames is not None
        and processed_frames > 0
        and dropped_frames / processed_frames >= 0.01
    ):
        issues.append(f"{label}.droppedFrames/processedVideoFrames 必须 < 1%")
    if audio_underruns is not None and audio_underruns != 0:
        issues.append(f"{label}.audioUnderrunCount 必须为 0")
    if rebuffer_session_rate is not None and rebuffer_session_rate >= 0.02:
        issues.append(f"{label}.rebufferSessionRate 必须 < 2%")
    if rebuffer_time_ratio is not None and rebuffer_time_ratio >= 0.01:
        issues.append(f"{label}.rebufferTimeRatio 必须 < 1%")
    if terminal_failure_rate is not None and terminal_failure_rate >= 0.005:
        issues.append(f"{label}.terminalFailureRate 必须 < 0.5%")
    if duration_mismatches is not None and duration_mismatches != 0:
        issues.append(f"{label}.durationMismatchCount 必须为 0")
    if row.get("seekEvidenceSource") != "native_settled":
        issues.append(f"{label}.seekEvidenceSource 必须为 native_settled")


def validate_qoe_payload(
    payload: dict[str, Any],
    issues: list[str],
    prefix: str,
) -> None:
    if payload.get("source") != "elasticsearch":
        issues.append(f"{prefix}.QoE readback.source 必须为 elasticsearch")
    if payload.get("eventType") != "video_playback_qoe":
        issues.append(f"{prefix}.QoE readback.eventType 必须为 video_playback_qoe")
    if payload.get("status") != "passed":
        issues.append(f"{prefix}.QoE readback.status 必须为 passed")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        issues.append(f"{prefix}.QoE readback.rows 必须是数组")
        return

    buckets: dict[str, list[dict[str, Any]]] = {
        network: [] for network in REQUIRED_NETWORK_BUCKETS
    }
    for row in rows:
        if not isinstance(row, dict):
            issues.append(f"{prefix}.QoE readback.rows 元素必须是 object")
            continue
        if row.get("devicePlatform") != "android":
            continue
        network_class = str(row.get("networkClass") or "")
        if network_class in buckets:
            buckets[network_class].append(row)
    for network_class, bucket_rows in sorted(buckets.items()):
        if len(bucket_rows) != 1:
            issues.append(
                f"{prefix}.QoE readback 必须恰有一个 Android {network_class} bucket"
            )
            continue
        _validate_qoe_bucket(bucket_rows[0], network_class, issues, prefix)
