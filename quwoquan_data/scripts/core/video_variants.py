"""下载截面的视频派生体：把超预算或容器不在发布闭集的源体转成装进预算的 H.264 mp4。

与 `image_variants.derive_budget_compliant_variant` 对称：输入源体字节与预算，输出一个
装进预算的派生体（字节、mime、几何、时长）或 None。码率按「目标字节 / 时长」派生，
每次不达标就减半重试，直到装进预算或用尽尝试。不改任何策略数值：预算来自
`objectStorageBudgetBytesByCarrier`，目标字节由调用方传入。
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

PUBLISHABLE_VIDEO_MIMES = frozenset({"video/mp4", "video/webm"})
DERIVED_VIDEO_MIME = "video/mp4"
DERIVED_VIDEO_EXTENSION = ".mp4"
_MAX_HEIGHT = 720
_AUDIO_KBPS = 96
_MIN_VIDEO_KBPS = 300
_MAX_VIDEO_KBPS = 4000
_ATTEMPTS = 4
_HEADROOM = 0.92


def probe_video(path: Path) -> dict[str, Any]:
    """ffprobe 一个视频文件，返回时长/几何/编码/容器/是否有音轨；不可探测抛 ValueError。"""
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ValueError(f"video not probeable: {path.name}")
    probe = json.loads(proc.stdout or "{}")
    streams = probe.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError(f"video has no video stream: {path.name}")
    duration = float((probe.get("format") or {}).get("duration") or 0)
    if duration <= 0:
        raise ValueError(f"video has no duration: {path.name}")
    return {
        "durationMs": int(duration * 1000),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "codec": str(video.get("codec_name") or ""),
        "container": str((probe.get("format") or {}).get("format_name") or ""),
        "hasAudio": any(s.get("codec_type") == "audio" for s in streams),
    }


def _video_kbps_for(target_bytes: int, duration_ms: int, *, has_audio: bool) -> int:
    total_kbps = (target_bytes * 8 * _HEADROOM) / max(1, duration_ms)
    video_kbps = total_kbps - (_AUDIO_KBPS if has_audio else 0)
    return int(min(_MAX_VIDEO_KBPS, max(_MIN_VIDEO_KBPS, video_kbps)))


def _transcode(source: Path, destination: Path, *, video_kbps: int, has_audio: bool) -> bool:
    audio = ["-c:a", "aac", "-b:a", f"{_AUDIO_KBPS}k", "-ac", "2"] if has_audio else ["-an"]
    proc = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y", "-i", str(source),
            "-map_metadata", "-1",
            "-vf", f"scale=-2:'min({_MAX_HEIGHT},ih)'",
            "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
            "-b:v", f"{video_kbps}k", "-maxrate", f"{int(video_kbps * 1.2)}k", "-bufsize", f"{video_kbps * 2}k",
            *audio,
            "-movflags", "+faststart",
            str(destination),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0 and destination.is_file() and destination.stat().st_size > 0


def derive_budget_compliant_video(
    body: bytes,
    *,
    budget_bytes: int,
    target_bytes: int,
) -> dict[str, Any] | None:
    """把源体转成装进 ``budget_bytes`` 的 H.264 mp4 派生体；每档都装不进返回 None。

    返回 {"bytes", "mimeType", "width", "height", "durationMs", "codec", "container", "hasAudio"}。
    """
    target = max(1, min(int(target_bytes), int(budget_bytes)))
    with tempfile.TemporaryDirectory(prefix="qwq-video-variant.") as workdir:
        source = Path(workdir) / "source.bin"
        source.write_bytes(body)
        probe = probe_video(source)
        kbps = _video_kbps_for(target, probe["durationMs"], has_audio=probe["hasAudio"])
        for attempt in range(_ATTEMPTS):
            destination = Path(workdir) / f"derived-{attempt}.mp4"
            if not _transcode(source, destination, video_kbps=kbps, has_audio=probe["hasAudio"]):
                return None
            derived = destination.read_bytes()
            if len(derived) <= budget_bytes:
                derived_probe = probe_video(destination)
                return {
                    "bytes": derived,
                    "mimeType": DERIVED_VIDEO_MIME,
                    "width": derived_probe["width"],
                    "height": derived_probe["height"],
                    "durationMs": derived_probe["durationMs"],
                    "codec": derived_probe["codec"],
                    "container": derived_probe["container"],
                    "hasAudio": derived_probe["hasAudio"],
                }
            if kbps <= _MIN_VIDEO_KBPS:
                return None
            kbps = max(_MIN_VIDEO_KBPS, kbps // 2)
    return None


def video_needs_derivative(*, mime: str, size_bytes: int, budget_bytes: int) -> bool:
    """源体超预算，或容器不在发布闭集（如 video/ogg、video/mpeg），都需要派生体。"""
    return size_bytes > budget_bytes or str(mime or "").lower() not in PUBLISHABLE_VIDEO_MIMES


__all__ = [
    "DERIVED_VIDEO_EXTENSION",
    "DERIVED_VIDEO_MIME",
    "PUBLISHABLE_VIDEO_MIMES",
    "derive_budget_compliant_video",
    "probe_video",
    "video_needs_derivative",
]
