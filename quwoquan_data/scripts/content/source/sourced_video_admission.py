"""Real-media probe and sampled watermark/OCR admission for sourced videos."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile

import cv2
import imageio_ffmpeg

from core.image_safety import assess_image
from core.runtime_policy import active_runtime_policy


def probe_sourced_video(path: Path) -> dict[str, object]:
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError(f"source video is not decodable: {path}")
        width = round(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = round(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        frames_per_second = float(capture.get(cv2.CAP_PROP_FPS))
        fourcc = round(capture.get(cv2.CAP_PROP_FOURCC))
        codec = "".join(
            chr((fourcc >> (8 * index)) & 0xFF)
            for index in range(4)
        ).lower()
        if (
            width <= 0
            or height <= 0
            or frame_count <= 0
            or frames_per_second <= 0
        ):
            raise ValueError("source video media probe is incomplete")
        return {
            "schema": "quwoquan_data.sourced_video_media_probe",
            "width": width,
            "height": height,
            "frameCount": frame_count,
            "framesPerSecond": frames_per_second,
            "durationMs": max(
                1,
                round(frame_count / frames_per_second * 1000),
            ),
            "codec": codec,
        }
    finally:
        capture.release()


def _sample_frames_with_opencv(
    path: Path,
    *,
    positions: list[int],
    output_dir: Path,
) -> list[Path] | None:
    """Best-effort OpenCV seek. WebM/VP9 often fails CAP_PROP_POS_FRAMES."""
    capture = cv2.VideoCapture(str(path))
    samples: list[Path] = []
    try:
        if not capture.isOpened():
            return None
        for index, position in enumerate(positions):
            capture.set(cv2.CAP_PROP_POS_FRAMES, position)
            ok, frame = capture.read()
            if not ok or frame is None:
                return None
            target = output_dir / f"sample-{index:03d}.jpg"
            if not cv2.imwrite(str(target), frame):
                return None
            samples.append(target)
    finally:
        capture.release()
    return samples


def _sample_frames_with_ffmpeg(
    path: Path,
    *,
    timestamps_sec: list[float],
    output_dir: Path,
) -> list[Path]:
    """Decode sample frames by timestamp; reliable for Commons WebM/VP8/VP9."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    timeout = active_runtime_policy().video_probe_timeout_seconds
    samples: list[Path] = []
    for index, timestamp in enumerate(timestamps_sec):
        # PNG avoids mjpeg encoder strictness failures on some VP9/WebM sources.
        target = output_dir / f"sample-{index:03d}.png"
        completed = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(path),
                "-ss",
                f"{max(0.0, timestamp):.3f}",
                "-frames:v",
                "1",
                "-y",
                str(target),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if completed.returncode != 0 or not target.is_file() or target.stat().st_size < 1:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise ValueError(
                f"source video sample frame is unreadable: {timestamp:.3f}"
                + (f" ({detail})" if detail else "")
            )
        samples.append(target)
    return samples


def _sample_frames(
    path: Path,
    *,
    sample_count: int,
    output_dir: Path,
) -> list[Path]:
    probe = probe_sourced_video(path)
    frame_count = int(probe["frameCount"])
    frames_per_second = float(probe["framesPerSecond"])
    positions = sorted(
        {
            round(index * (frame_count - 1) / max(1, sample_count - 1))
            for index in range(sample_count)
        }
    )
    opencv_samples = _sample_frames_with_opencv(
        path,
        positions=positions,
        output_dir=output_dir,
    )
    if opencv_samples is not None:
        return opencv_samples
    duration_sec = max(frame_count / frames_per_second, 0.001)
    # Keep clear of EOF; late-keyframe WebM seeks often fail near the final frame.
    last_safe = max(0.0, min(duration_sec * 0.85, duration_sec - 0.25))
    timestamps = [
        min(last_safe, max(0.0, position / frames_per_second))
        for position in positions
    ]
    return _sample_frames_with_ffmpeg(
        path,
        timestamps_sec=timestamps,
        output_dir=output_dir,
    )


def scan_sourced_video_watermark(
    path: Path,
    *,
    sample_count: int = 12,
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="qwq_sourced_video_scan_") as temp:
        samples = _sample_frames(
            path,
            sample_count=sample_count,
            output_dir=Path(temp),
        )
        verdicts = [assess_image(sample, require_ocr=True) for sample in samples]
    ocr_reviewed = all(
        "ocr" in verdict.backends
        for verdict in verdicts
    )
    watermark_detected = any(verdict.has_watermark for verdict in verdicts)
    return {
        "schema": "quwoquan_data.sourced_video_watermark_evidence",
        "sampleCount": len(verdicts),
        "ocrReviewed": ocr_reviewed,
        "watermarkDetected": watermark_detected,
        "decision": (
            "passed"
            if ocr_reviewed and not watermark_detected
            else "blocked"
        ),
        "samples": [
            {
                "status": verdict.status,
                "hasWatermark": verdict.has_watermark,
                "ocrText": verdict.ocr_text,
                "reasons": list(verdict.reasons),
                "backends": list(verdict.backends),
            }
            for verdict in verdicts
        ],
    }


def probe_audio_stream(path: Path) -> dict[str, object]:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    completed = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=active_runtime_policy().video_probe_timeout_seconds,
    )
    detail = completed.stderr
    has_audio = bool(re.search(r"Stream #.+Audio:", detail))
    return {
        "schema": "quwoquan_data.sourced_video_audio_probe",
        "hasAudio": has_audio,
        "streamSummary": [
            line.strip()
            for line in detail.splitlines()
            if "Stream #" in line
        ],
    }


def admitted_audio_evidence(
    path: Path,
    *,
    declared_status: str,
    authorization_proof_url: str | None,
    allow_unverified_rights: bool = False,
) -> dict[str, object]:
    probe = probe_audio_stream(path)
    has_audio = probe["hasAudio"] is True
    if not has_audio:
        status = "no_audio"
        passed = declared_status == status
    else:
        status = declared_status
        passed = status == "unverified" and allow_unverified_rights
        passed = passed or (
            status
            in {
                "licensed",
                "original_authorized",
                "replaced_with_licensed_track",
            }
            and bool(str(authorization_proof_url or "").strip())
        )
    return {
        **probe,
        "status": status,
        "authorizationProofUrl": authorization_proof_url,
        "decision": "passed" if passed else "blocked",
    }


__all__ = [
    "admitted_audio_evidence",
    "probe_sourced_video",
    "scan_sourced_video_watermark",
]
