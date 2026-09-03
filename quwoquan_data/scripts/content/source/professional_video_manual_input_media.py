"""Deterministic media operations for governed manual-video preparation."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

import cv2
import imageio_ffmpeg
import numpy as np

_CONTACT_COLUMNS = 4
_CONTACT_ROWS = 3
_CONTACT_WIDTH = 320
_CONTACT_HEIGHT = 180
_VIDEO_PROBE_TIMEOUT_SECONDS = 60
_VIDEO_TRANSCODE_TIMEOUT_SECONDS = 300


def ffmpeg_executable() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def ffmpeg_version(executable: str, *, fail: Any) -> str:
    completed = subprocess.run(
        [executable, "-version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=_VIDEO_PROBE_TIMEOUT_SECONDS,
    )
    first = completed.stdout.splitlines()[0].strip() if completed.stdout else ""
    if completed.returncode != 0 or not first:
        fail("ffmpeg version probe failed")
    return first


def command_profile(*, start_ms: int, duration_ms: int) -> list[str]:
    return [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start_ms / 1000:.3f}",
        "-i",
        "<sourceRef>",
        "-t",
        f"{duration_ms / 1000:.3f}",
        "-map",
        "0:v:0",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-bf",
        "0",
        "-pix_fmt",
        "yuv420p",
        "-threads",
        "1",
        "-movflags",
        "+faststart",
        "-an",
        "-n",
        "<videoRef>",
    ]


def transformation(*, start_ms: int, duration_ms: int) -> str:
    return (
        f"trim startMs={start_ms} durationMs={duration_ms}; "
        "ffmpeg libx264 crf=20 preset=medium pix_fmt=yuv420p faststart; "
        "audio removed; timestamps reset; no frame interpolation or synthetic frames"
    )


def run_transcode(
    source: Path,
    target: Path,
    *,
    executable: str,
    start_ms: int,
    duration_ms: int,
    fail: Any,
) -> None:
    profile = command_profile(start_ms=start_ms, duration_ms=duration_ms)
    command = [
        executable,
        *[
            str(source)
            if value == "<sourceRef>"
            else str(target)
            if value == "<videoRef>"
            else value
            for value in profile[1:]
        ],
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=_VIDEO_TRANSCODE_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()
        fail(
            "video transcode failed: "
            + (detail[-1] if detail else "unknown ffmpeg failure")
        )
    if not target.is_file() or target.stat().st_size <= 0:
        fail("video transcode produced no regular output file")


def _letterbox(frame: Any) -> Any:
    height, width = frame.shape[:2]
    scale = min(_CONTACT_WIDTH / width, _CONTACT_HEIGHT / height)
    resized = cv2.resize(
        frame,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    tile = np.zeros((_CONTACT_HEIGHT, _CONTACT_WIDTH, 3), dtype=np.uint8)
    y = (_CONTACT_HEIGHT - resized.shape[0]) // 2
    x = (_CONTACT_WIDTH - resized.shape[1]) // 2
    tile[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return tile


def render_contact_sheet(
    video: Path,
    target: Path,
    *,
    frame_count: int,
    fail: Any,
) -> None:
    """Render the review contact sheet via the shared direction-safe sampler.

    Container frame counts for Commons WebM/VP8/VP9 are estimates; OpenCV
    CAP_PROP_POS_FRAMES seeks near the estimated tail fail on files that
    decode cleanly, so sampling shares the ffmpeg timestamp fallback with the
    admission/motion probes instead of a second seek-only chain.
    """
    from content.source.video_media_probe import sample_video_frame_files

    sample_count = _CONTACT_COLUMNS * _CONTACT_ROWS
    positions = sorted(
        {
            round(index * (frame_count - 1) / max(1, sample_count - 1))
            for index in range(sample_count)
        }
    )
    if len(positions) < 6:
        fail("prepared video has too few distinct sample positions")
    frames: list[Any] = []
    with tempfile.TemporaryDirectory(prefix="qwq_contact_sheet_") as temp:
        try:
            files = sample_video_frame_files(
                video, sample_count=sample_count, output_dir=Path(temp)
            )
        except (OSError, ValueError) as exc:
            fail(f"contact-sheet sample frame is unreadable: {exc}")
        for file in files:
            frame = cv2.imread(str(file))
            if frame is None:
                fail(f"contact-sheet sample frame is unreadable: {file.name}")
            frames.append(_letterbox(frame))
    sheet = np.zeros(
        (
            _CONTACT_ROWS * _CONTACT_HEIGHT,
            _CONTACT_COLUMNS * _CONTACT_WIDTH,
            3,
        ),
        dtype=np.uint8,
    )
    for index, frame in enumerate(frames):
        row, column = divmod(index, _CONTACT_COLUMNS)
        y = row * _CONTACT_HEIGHT
        x = column * _CONTACT_WIDTH
        sheet[y : y + _CONTACT_HEIGHT, x : x + _CONTACT_WIDTH] = frame
    if not cv2.imwrite(str(target), sheet, [cv2.IMWRITE_JPEG_QUALITY, 92]):
        fail("contact-sheet encoding failed")


__all__ = [
    "command_profile",
    "ffmpeg_executable",
    "ffmpeg_version",
    "render_contact_sheet",
    "run_transcode",
    "transformation",
]
