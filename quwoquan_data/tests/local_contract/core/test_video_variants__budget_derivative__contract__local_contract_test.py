"""视频派生体契约：超预算或容器不在发布闭集的源体在下载截面转成装进预算的 H.264 mp4。

spec_ref: discovery-content/object-homepage-coverage-scaling/multi-carrier-release/GWT-020
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.video_variants import (  # noqa: E402
    DERIVED_VIDEO_MIME,
    derive_budget_compliant_video,
    probe_video,
    video_needs_derivative,
)

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not on PATH",
)


def _synthetic_source(tmp_path: Path, *, container: str, seconds: int = 4, size: str = "1280x720") -> bytes:
    """用 lavfi 合成一段高熵源体；testsrc2 的噪点纹理让文件体积可控地偏大。

    `mpg`（MPEG-1 program stream，mime video/mpeg）代表发布闭集之外的容器。
    """
    destination = tmp_path / f"source.{container}"
    if container == "mpg":
        codec = ["-c:v", "mpeg1video", "-q:v", "2", "-c:a", "mp2"]
    else:
        codec = ["-c:v", "libx264", "-crf", "10", "-preset", "ultrafast", "-c:a", "aac"]
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:duration={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            *codec, "-shortest",
            str(destination),
        ],
        check=True,
        capture_output=True,
    )
    return destination.read_bytes()


def test_video_needs_derivative_only_when_over_budget_or_container_outside_closed_set():
    assert video_needs_derivative(mime="video/webm", size_bytes=10, budget_bytes=100) is False
    assert video_needs_derivative(mime="video/mp4", size_bytes=10, budget_bytes=100) is False
    assert video_needs_derivative(mime="video/webm", size_bytes=101, budget_bytes=100) is True
    assert video_needs_derivative(mime="video/ogg", size_bytes=10, budget_bytes=100) is True
    assert video_needs_derivative(mime="video/mpeg", size_bytes=10, budget_bytes=100) is True


def test_over_budget_source_is_transcoded_into_budget_as_mp4(tmp_path: Path):
    source = _synthetic_source(tmp_path, container="mp4")
    budget = len(source) // 2
    assert budget > 64 * 1024

    variant = derive_budget_compliant_video(source, budget_bytes=budget, target_bytes=budget // 2)

    assert variant is not None
    assert variant["mimeType"] == DERIVED_VIDEO_MIME
    assert 0 < len(variant["bytes"]) <= budget
    assert variant["codec"] == "h264"
    assert variant["height"] <= 720
    assert variant["durationMs"] > 0
    derived_path = tmp_path / "derived.mp4"
    derived_path.write_bytes(variant["bytes"])
    assert probe_video(derived_path)["container"].startswith("mov,mp4")


def test_container_outside_closed_set_is_normalized_to_mp4_even_within_budget(tmp_path: Path):
    source = _synthetic_source(tmp_path, container="mpg", seconds=2, size="640x360")
    budget = len(source) * 4

    assert video_needs_derivative(mime="video/mpeg", size_bytes=len(source), budget_bytes=budget)
    variant = derive_budget_compliant_video(source, budget_bytes=budget, target_bytes=budget)

    assert variant is not None
    assert variant["mimeType"] == DERIVED_VIDEO_MIME
    assert len(variant["bytes"]) <= budget


def test_unreachable_budget_returns_none(tmp_path: Path):
    source = _synthetic_source(tmp_path, container="mp4", seconds=2, size="640x360")

    assert derive_budget_compliant_video(source, budget_bytes=4096, target_bytes=4096) is None


def test_non_video_bytes_are_rejected_as_not_probeable():
    with pytest.raises(ValueError):
        derive_budget_compliant_video(b"not a video", budget_bytes=1024 * 1024, target_bytes=1024)
