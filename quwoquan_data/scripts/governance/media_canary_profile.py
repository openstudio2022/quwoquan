"""Typed repository-owned profile for deterministic media canary fixtures."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from core.paths import REPO_DATA_ROOT


PROFILE_PATH = REPO_DATA_ROOT / "reference/media_canary/video_playback.yaml"


@dataclass(frozen=True, slots=True)
class MediaCanaryAsset:
    asset_id: str
    asset_version: int
    duration_ms: int
    frames_per_second: int
    expected_processing_status: str
    storyboard: bool
    public_slice_prefix: str


@dataclass(frozen=True, slots=True)
class MediaCanaryProfile:
    profile_id: str
    processor_profile: str
    product_maximum_duration_ms: int
    keyframe_interval_ms: int
    width: int
    height: int
    audio_sample_rate_hz: int
    audio_bitrate: str
    preview_frame_interval_ms: int
    preview_frame_width: int
    preview_frame_height: int
    preview_columns: int
    assets: tuple[MediaCanaryAsset, ...]


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"media canary {label} must be a positive integer")
    return value


def load_media_canary_profile(path: Path = PROFILE_PATH) -> MediaCanaryProfile:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("media canary profile must be an object")
    video = raw.get("video")
    audio = raw.get("audio")
    preview = raw.get("preview")
    assets_raw = raw.get("assets")
    if not isinstance(video, dict) or not isinstance(audio, dict) or not isinstance(preview, dict):
        raise ValueError("media canary video/audio/preview sections are required")
    if not isinstance(assets_raw, list) or not assets_raw:
        raise ValueError("media canary assets must be a non-empty list")
    if str(video.get("codec") or "") != "h264" or str(video.get("container") or "") != "mp4":
        raise ValueError("media canary P0 requires H.264 MP4")
    if str(audio.get("codec") or "") != "aac":
        raise ValueError("media canary P0 requires AAC audio")

    assets: list[MediaCanaryAsset] = []
    seen: set[str] = set()
    for item in assets_raw:
        if not isinstance(item, dict):
            raise ValueError("media canary asset entry must be an object")
        asset_id = str(item.get("assetId") or "").strip()
        prefix = str(item.get("publicSlicePrefix") or "").strip()
        status = str(item.get("expectedProcessingStatus") or "").strip()
        if not asset_id or asset_id in seen:
            raise ValueError(f"media canary assetId is missing or duplicated: {asset_id}")
        if not prefix.startswith("media/video/s/") or ".." in prefix:
            raise ValueError(f"media canary public slice prefix is invalid: {prefix}")
        if status not in {"ready", "rejected"}:
            raise ValueError(f"media canary processing status is invalid: {status}")
        seen.add(asset_id)
        assets.append(
            MediaCanaryAsset(
                asset_id=asset_id,
                asset_version=_positive_int(item.get("assetVersion"), label="assetVersion"),
                duration_ms=_positive_int(item.get("durationMs"), label="durationMs"),
                frames_per_second=_positive_int(
                    item.get("framesPerSecond"), label="framesPerSecond"
                ),
                expected_processing_status=status,
                storyboard=bool(item.get("storyboard")),
                public_slice_prefix=prefix,
            )
        )

    profile = MediaCanaryProfile(
        profile_id=str(raw.get("profileId") or "").strip(),
        processor_profile=str(raw.get("processorProfile") or "").strip(),
        product_maximum_duration_ms=_positive_int(
            raw.get("productMaximumDurationMs"), label="productMaximumDurationMs"
        ),
        keyframe_interval_ms=_positive_int(
            raw.get("keyframeIntervalMs"), label="keyframeIntervalMs"
        ),
        width=_positive_int(video.get("width"), label="video.width"),
        height=_positive_int(video.get("height"), label="video.height"),
        audio_sample_rate_hz=_positive_int(
            audio.get("sampleRateHz"), label="audio.sampleRateHz"
        ),
        audio_bitrate=str(audio.get("bitrate") or "").strip(),
        preview_frame_interval_ms=_positive_int(
            preview.get("frameIntervalMs"), label="preview.frameIntervalMs"
        ),
        preview_frame_width=_positive_int(
            preview.get("frameWidth"), label="preview.frameWidth"
        ),
        preview_frame_height=_positive_int(
            preview.get("frameHeight"), label="preview.frameHeight"
        ),
        preview_columns=_positive_int(preview.get("columns"), label="preview.columns"),
        assets=tuple(assets),
    )
    if not profile.profile_id or not profile.processor_profile or not profile.audio_bitrate:
        raise ValueError("media canary profile identity and audio bitrate are required")
    if profile.keyframe_interval_ms > 2000:
        raise ValueError("media canary keyframe interval must not exceed 2000ms")
    for asset in profile.assets:
        expected = (
            "ready"
            if asset.duration_ms <= profile.product_maximum_duration_ms
            else "rejected"
        )
        if asset.expected_processing_status != expected:
            raise ValueError(
                f"media canary {asset.asset_id} status must be {expected} at the product boundary"
            )
        if asset.storyboard and asset.expected_processing_status != "ready":
            raise ValueError("rejected media canary cannot publish a storyboard")
    return profile


__all__ = ["MediaCanaryAsset", "MediaCanaryProfile", "load_media_canary_profile"]
