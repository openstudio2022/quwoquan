"""Real-media probe and sampled watermark/OCR admission for sourced videos."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile

import cv2
import imageio_ffmpeg

from core.image_safety import assess_image


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


def _sample_frames(
    path: Path,
    *,
    sample_count: int,
    output_dir: Path,
) -> list[Path]:
    probe = probe_sourced_video(path)
    frame_count = int(probe["frameCount"])
    positions = sorted(
        {
            round(index * (frame_count - 1) / max(1, sample_count - 1))
            for index in range(sample_count)
        }
    )
    capture = cv2.VideoCapture(str(path))
    samples: list[Path] = []
    try:
        for index, position in enumerate(positions):
            capture.set(cv2.CAP_PROP_POS_FRAMES, position)
            ok, frame = capture.read()
            if not ok or frame is None:
                raise ValueError(
                    f"source video sample frame is unreadable: {position}"
                )
            target = output_dir / f"sample-{index:03d}.jpg"
            if not cv2.imwrite(str(target), frame):
                raise RuntimeError("source video sample frame encoding failed")
            samples.append(target)
    finally:
        capture.release()
    return samples


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
        timeout=60,
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
) -> dict[str, object]:
    probe = probe_audio_stream(path)
    has_audio = probe["hasAudio"] is True
    if not has_audio:
        status = "no_audio"
        passed = declared_status == status
    else:
        status = declared_status
        passed = (
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
