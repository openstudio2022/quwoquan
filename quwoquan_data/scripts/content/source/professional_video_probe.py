"""Deterministic real-media and motion admission for acquired videos."""
from __future__ import annotations

import hashlib
import math
from itertools import pairwise
from pathlib import Path

import cv2

from content.source.sourced_video_admission import (
    probe_audio_stream,
    probe_sourced_video,
)

_MIN_DURATION_MS = 3_000
_MAX_DURATION_MS = 180_000
_MIN_WIDTH = 320
_MIN_HEIGHT = 180
_MIN_FRAMES_PER_SECOND = 5.0
_SAMPLE_COUNT = 18
_MOTION_DELTA_THRESHOLD = 0.012


def _sample_frames(path: Path, *, frame_count: int) -> list[object]:
    positions = sorted(
        {
            round(index * (frame_count - 1) / max(1, _SAMPLE_COUNT - 1))
            for index in range(_SAMPLE_COUNT)
        }
    )
    capture = cv2.VideoCapture(str(path))
    samples: list[object] = []
    try:
        if not capture.isOpened():
            raise ValueError("professional video sample decoder did not open")
        for position in positions:
            capture.set(cv2.CAP_PROP_POS_FRAMES, position)
            ok, frame = capture.read()
            if not ok or frame is None:
                raise ValueError(
                    f"professional video sample frame is unreadable: {position}"
                )
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            samples.append(cv2.resize(gray, (64, 36), interpolation=cv2.INTER_AREA))
    finally:
        capture.release()
    return samples


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
    samples = _sample_frames(path, frame_count=frame_count)
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
