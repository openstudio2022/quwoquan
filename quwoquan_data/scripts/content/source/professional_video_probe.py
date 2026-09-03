"""Deterministic real-media and motion admission for acquired videos."""
from __future__ import annotations

import hashlib
import math
import tempfile
from itertools import pairwise
from pathlib import Path

import cv2
import numpy as np

from content.source.video_media_probe import (
    probe_audio_stream,
    probe_sourced_video,
    sample_video_frame_files,
)

_MIN_DURATION_MS = 3_000
_MAX_DURATION_MS = 180_000
_MIN_WIDTH = 320
_MIN_HEIGHT = 180
_MIN_FRAMES_PER_SECOND = 5.0
_SAMPLE_COUNT = 18
_MOTION_DELTA_THRESHOLD = 0.012
# 8-bit 灰度容差：吸收编码噪声，不吸收真实运动。
_BORDER_TOLERANCE = 2
_MIN_CONTENT_AREA_FRACTION = 0.05


def _moving_content_bounds(frames: list[object]) -> tuple[int, int, int, int] | None:
    """Locate the region inside any padding that never changes across samples.

    交付策略把素材投影到固定竖屏画布并补黑边。在成品全幅上算帧差，等于按黑边
    面积比例稀释运动信号，把「素材是横屏」误判成「素材是静态图」。运动是素材
    属性而不是画布属性，所以先剥掉恒定边框，让同一阈值对源与成品同结论。
    真幻灯片全幅都恒定，这里返回缺席，判定退回全幅、结论不变。
    """
    shapes = {getattr(frame, "shape", None) for frame in frames}
    if len(shapes) != 1 or None in shapes:
        return None
    stack = np.stack(frames)
    variation = stack.max(axis=0) - stack.min(axis=0)
    active = variation > _BORDER_TOLERANCE
    rows = np.flatnonzero(active.any(axis=1))
    columns = np.flatnonzero(active.any(axis=0))
    if rows.size == 0 or columns.size == 0:
        return None
    top, bottom = int(rows[0]), int(rows[-1]) + 1
    left, right = int(columns[0]), int(columns[-1]) + 1
    height, width = variation.shape
    if (bottom - top) * (right - left) < _MIN_CONTENT_AREA_FRACTION * height * width:
        return None
    return top, bottom, left, right


def _sample_frames(path: Path) -> list[object]:
    """Load motion-probe samples via the shared direction-safe frame sampler.

    Container frame counts for Commons WebM/VP8/VP9 are estimates: seeking to
    an estimated CAP_PROP_POS_FRAMES position can fail on files that decode
    cleanly end to end.  The shared sampler retries by ffmpeg timestamp before
    declaring a frame unreadable, so real motion videos are not misblocked.
    """
    with tempfile.TemporaryDirectory(prefix="qwq_professional_video_probe_") as temp:
        files = sample_video_frame_files(
            path, sample_count=_SAMPLE_COUNT, output_dir=Path(temp)
        )
        grays: list[object] = []
        for file in files:
            frame = cv2.imread(str(file))
            if frame is None:
                raise ValueError(
                    f"professional video sample frame is unreadable: {file.name}"
                )
            grays.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        bounds = _moving_content_bounds(grays)
        if bounds is not None:
            top, bottom, left, right = bounds
            grays = [gray[top:bottom, left:right] for gray in grays]
        return [
            cv2.resize(gray, (64, 36), interpolation=cv2.INTER_AREA)
            for gray in grays
        ]


def _motion_facts(samples: list[object]) -> dict[str, object]:
    if len(samples) < 3:
        return {
            "sampleCount": len(samples),
            "distinctFrameCount": len(samples),
            "movingTransitionCount": 0,
            "meanTransitionDelta": 0.0,
            "motionVideo": False,
            "staticImageSequence": True,
        }
    frame_hashes = {
        hashlib.sha256(sample.tobytes()).hexdigest()  # type: ignore[attr-defined]
        for sample in samples
    }
    deltas = [
        float(cv2.mean(cv2.absdiff(left, right))[0]) / 255.0
        for left, right in pairwise(samples)
    ]
    moving = sum(delta >= _MOTION_DELTA_THRESHOLD for delta in deltas)
    # A slideshow can have several distinct frames and a few abrupt cuts.  A
    # sourced/Premium video must show sustained temporal movement across most
    # of the sampled timeline, not merely three different stills.
    required_moving = max(4, math.ceil(len(deltas) * 0.6))
    motion_video = len(frame_hashes) >= 6 and moving >= required_moving
    return {
        "sampleCount": len(samples),
        "distinctFrameCount": len(frame_hashes),
        "movingTransitionCount": moving,
        "meanTransitionDelta": round(sum(deltas) / len(deltas), 6),
        "motionVideo": motion_video,
        "staticImageSequence": not motion_video,
    }


def probe_professional_video(path: Path) -> dict[str, object]:
    """Prove the file is a playable motion video, not a still/slideshow asset."""
    base = probe_sourced_video(path)
    frame_count = int(base["frameCount"])
    frames_per_second = float(base["framesPerSecond"])
    duration_ms = int(base["durationMs"])
    samples = _sample_frames(path)
    motion = _motion_facts(samples)
    has_audio = probe_audio_stream(path).get("hasAudio") is True
    playable = (
        int(base["width"]) >= _MIN_WIDTH
        and int(base["height"]) >= _MIN_HEIGHT
        and frames_per_second >= _MIN_FRAMES_PER_SECOND
        and _MIN_DURATION_MS <= duration_ms <= _MAX_DURATION_MS
    )
    premium_eligible = playable and bool(motion["motionVideo"])
    return {
        "width": int(base["width"]),
        "height": int(base["height"]),
        "frameCount": frame_count,
        "framesPerSecond": frames_per_second,
        "durationMs": duration_ms,
        "codec": str(base.get("codec") or ""),
        "hasAudio": has_audio,
        **motion,
        "playable": playable,
        "premiumPlayableEligible": premium_eligible,
    }


__all__ = ["probe_professional_video"]
