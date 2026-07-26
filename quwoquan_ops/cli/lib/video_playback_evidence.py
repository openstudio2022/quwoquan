"""解析由 Patrol 设备进程写出的原生视频播放证据。"""

from __future__ import annotations

import json
from pathlib import Path

VIDEO_PLAYBACK_EVIDENCE_MARKER = "QWQ_VIDEO_PLAYBACK_EVIDENCE "


def read_native_video_playback_evidence(patrol_log: Path) -> dict[str, bool]:
    """只接受 Patrol 原始日志中最后一条格式正确的原生证据标记。"""

    if not patrol_log.is_file():
        return {}
    try:
        lines = patrol_log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    for line in reversed(lines):
        marker_index = line.find(VIDEO_PLAYBACK_EVIDENCE_MARKER)
        if marker_index < 0:
            continue
        raw_payload = line[marker_index + len(VIDEO_PLAYBACK_EVIDENCE_MARKER) :].strip()
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        return {
            "nativeFirstFrame": payload.get("nativeFirstFrame") is True,
            "nativeSeekSettled": payload.get("nativeSeekSettled") is True,
        }
    return {}


__all__ = [
    "VIDEO_PLAYBACK_EVIDENCE_MARKER",
    "read_native_video_playback_evidence",
]
