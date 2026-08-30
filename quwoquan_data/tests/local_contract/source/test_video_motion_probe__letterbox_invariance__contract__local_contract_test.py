"""运动判定是素材属性：竖屏投影补的黑边不得把横屏素材降级成静态图序列。"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from content.source.professional_video_probe import (  # noqa: E402
    probe_professional_video,
)

_FPS = 12
_SECONDS = 5


def _write(path: Path, frames: list[np.ndarray]) -> Path:
    height, width = frames[0].shape[:2]
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), _FPS, (width, height)
    )
    assert writer.isOpened()
    for frame in frames:
        writer.write(frame)
    writer.release()
    assert path.is_file()
    return path


def _moving_frames(width: int, height: int) -> list[np.ndarray]:
    frames: list[np.ndarray] = []
    for index in range(_FPS * _SECONDS):
        frame = np.full((height, width, 3), 40, dtype=np.uint8)
        cv2.circle(
            frame,
            (int(width * 0.1) + index * 7 % int(width * 0.8), height // 2),
            max(8, height // 8),
            (230, 200, 90),
            -1,
        )
        frames.append(frame)
    return frames


def _letterboxed(frames: list[np.ndarray], *, canvas: tuple[int, int]) -> list[np.ndarray]:
    """把素材按 decrease+pad 投影到固定画布，与交付转码同一几何。"""
    canvas_width, canvas_height = canvas
    source_height, source_width = frames[0].shape[:2]
    ratio = min(canvas_width / source_width, canvas_height / source_height)
    scaled = (max(2, int(source_width * ratio)), max(2, int(source_height * ratio)))
    top = (canvas_height - scaled[1]) // 2
    left = (canvas_width - scaled[0]) // 2
    projected: list[np.ndarray] = []
    for frame in frames:
        canvas_frame = np.zeros((canvas_height, canvas_width, 3), dtype=np.uint8)
        resized = cv2.resize(frame, scaled, interpolation=cv2.INTER_AREA)
        canvas_frame[top : top + scaled[1], left : left + scaled[0]] = resized
        projected.append(canvas_frame)
    return projected


def test_letterboxed_delivery_keeps_the_source_motion_verdict(tmp_path: Path) -> None:
    """成品在竖屏画布上只占三成面积；按全幅算帧差会把运动稀释到阈值以下。"""
    frames = _moving_frames(640, 360)
    source = probe_professional_video(_write(tmp_path / "source.mp4", frames))
    delivered = probe_professional_video(
        _write(
            tmp_path / "delivered.mp4",
            _letterboxed(frames, canvas=(360, 640)),
        )
    )

    assert source["motionVideo"] is True
    assert source["staticImageSequence"] is False
    assert delivered["motionVideo"] is True, delivered
    assert delivered["staticImageSequence"] is False
    assert delivered["premiumPlayableEligible"] is True
    # 剥掉恒定边框后两者看的是同一有效画面，运动强度必须落在同一量级。
    assert delivered["meanTransitionDelta"] >= float(source["meanTransitionDelta"]) * 0.5


def test_padded_still_sequence_is_still_rejected(tmp_path: Path) -> None:
    """边框剥离不得放过真幻灯片：内容区恒定时判定必须仍然收紧。"""
    still = np.full((360, 640, 3), 70, dtype=np.uint8)
    cv2.rectangle(still, (100, 80), (300, 260), (200, 180, 60), -1)
    frames = [still.copy() for _ in range(_FPS * _SECONDS)]
    probe = probe_professional_video(
        _write(tmp_path / "still.mp4", _letterboxed(frames, canvas=(360, 640)))
    )

    assert probe["motionVideo"] is False
    assert probe["staticImageSequence"] is True
    assert probe["premiumPlayableEligible"] is False
