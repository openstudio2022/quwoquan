"""受控视频 canary 的确定性生成、真实 probe 与 storyboard 封装。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

import imageio_ffmpeg
from governance.media_canary_profile import (
    MediaCanaryAsset,
    MediaCanaryProfile,
    load_media_canary_profile,
)
from governance.media_canary_storyboard_validation import validate_storyboard
_DURATION_PATTERN = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_VIDEO_PATTERN = re.compile(r"Video:\s*([^,\s]+).*?(\d{2,5})x(\d{2,5})")
_AUDIO_PATTERN = re.compile(r"Audio:\s*([^,\s]+)")
_KEYFRAME_PATTERN = re.compile(r"pts_time:([0-9.]+)")
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "")[-2000:]
        raise RuntimeError(f"media canary command failed ({completed.returncode}): {detail}")
    return completed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _descriptor_probe_hash(descriptor: dict[str, Any]) -> str:
    canonical_descriptor = dict(descriptor)
    canonical_descriptor.pop("probeHash", None)
    canonical_probe = json.dumps(
        canonical_descriptor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical_probe).hexdigest()}"


def _asset_root(output_root: Path, asset: MediaCanaryAsset) -> Path:
    return (output_root / asset.public_slice_prefix).resolve()


def _generate_video(
    *,
    ffmpeg: str,
    profile: MediaCanaryProfile,
    asset: MediaCanaryAsset,
    video_path: Path,
) -> None:
    duration_seconds = asset.duration_ms / 1000
    source = (
        f"testsrc2=size={profile.width}x{profile.height}:"
        f"rate={asset.frames_per_second}:duration={duration_seconds}"
    )
    keyframe_frames = max(
        1,
        round(asset.frames_per_second * profile.keyframe_interval_ms / 1000),
    )
    video_only_path = video_path.with_suffix(".video.mp4")
    audio_only_path = video_path.with_suffix(".audio.m4a")
    common = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-fflags",
        "+bitexact",
    ]
    try:
        _run(
            [
                *common,
                "-filter_threads",
                "1",
                "-f",
                "lavfi",
                "-i",
                source,
                "-map",
                "0:v:0",
                "-map_metadata",
                "-1",
                "-an",
                "-c:v",
                "libx264",
                "-threads:v",
                "1",
                "-x264-params",
                "threads=1:lookahead_threads=1:sliced_threads=0:sync-lookahead=0",
                "-preset",
                "veryfast",
                "-crf",
                "32",
                "-pix_fmt",
                "yuv420p",
                "-g",
                str(keyframe_frames),
                "-keyint_min",
                str(keyframe_frames),
                "-sc_threshold",
                "0",
                "-flags:v",
                "+bitexact",
                "-t",
                str(duration_seconds),
                "-movflags",
                "+faststart",
                str(video_only_path),
            ]
        )
        _run(
            [
                *common,
                "-filter_threads",
                "1",
                "-f",
                "lavfi",
                "-i",
                (
                    f"sine=frequency=440:sample_rate={profile.audio_sample_rate_hz}:"
                    f"duration={duration_seconds}"
                ),
                "-map",
                "0:a:0",
                "-map_metadata",
                "-1",
                "-vn",
                "-c:a",
                "aac",
                "-threads:a",
                "1",
                "-b:a",
                profile.audio_bitrate,
                "-flags:a",
                "+bitexact",
                "-t",
                str(duration_seconds),
                str(audio_only_path),
            ]
        )
        _run(
            [
                *common,
                "-i",
                str(video_only_path),
                "-i",
                str(audio_only_path),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-map_metadata",
                "-1",
                "-c",
                "copy",
                "-t",
                str(duration_seconds),
                "-movflags",
                "+faststart",
                str(video_path),
            ]
        )
    finally:
        video_only_path.unlink(missing_ok=True)
        audio_only_path.unlink(missing_ok=True)


def _generate_cover(
    *,
    ffmpeg: str,
    profile: MediaCanaryProfile,
    video_path: Path,
    cover_path: Path,
) -> None:
    _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            "0",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-vf",
            f"scale={profile.preview_frame_width}:{profile.preview_frame_height}",
            str(cover_path),
        ]
    )


def _probe_media(
    *,
    ffmpeg: str,
    profile: MediaCanaryProfile,
    video_path: Path,
) -> dict[str, Any]:
    metadata = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-i",
            str(video_path),
            "-map",
            "0",
            "-c",
            "copy",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    stderr = metadata.stderr or ""
    duration_match = _DURATION_PATTERN.search(stderr)
    video_match = _VIDEO_PATTERN.search(stderr)
    audio_match = _AUDIO_PATTERN.search(stderr)
    if duration_match is None or video_match is None or audio_match is None:
        raise ValueError("media canary probe could not read duration/video/audio streams")
    hours, minutes, seconds = duration_match.groups()
    duration_ms = round(
        (int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000
    )
    keyframes = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "info",
            "-i",
            str(video_path),
            "-vf",
            "select='eq(pict_type,I)',showinfo",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    keyframe_times = [
        float(value)
        for value in _KEYFRAME_PATTERN.findall(keyframes.stderr or "")
    ]
    intervals = [
        round((current - previous) * 1000)
        for previous, current in zip(keyframe_times, keyframe_times[1:])
    ]
    max_keyframe_interval_ms = max(intervals, default=profile.keyframe_interval_ms)
    with video_path.open("rb") as media_file:
        header = media_file.read(4 * 1024 * 1024)
    moov_offset = header.find(b"moov")
    mdat_offset = header.find(b"mdat")
    return {
        "durationMs": duration_ms,
        "width": int(video_match.group(2)),
        "height": int(video_match.group(3)),
        "videoCodec": video_match.group(1).lower(),
        "videoContainer": "mp4",
        "videoAudioCodec": audio_match.group(1).lower(),
        "videoKeyframeIntervalMs": max_keyframe_interval_ms,
        "videoFastStart": 0 <= moov_offset < mdat_offset,
        "sha256": _sha256(video_path),
        "sizeBytes": video_path.stat().st_size,
    }


def _generate_storyboard(
    *,
    ffmpeg: str,
    profile: MediaCanaryProfile,
    asset: MediaCanaryAsset,
    video_path: Path,
    asset_root: Path,
) -> tuple[Path, Path]:
    frame_count = (asset.duration_ms - 1) // profile.preview_frame_interval_ms + 1
    rows = (frame_count + profile.preview_columns - 1) // profile.preview_columns
    preview_root = asset_root / "preview"
    preview_root.mkdir(parents=True, exist_ok=True)
    sprite_path = preview_root / "sprite.webp"
    manifest_path = preview_root / "manifest.json"
    _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            (
                f"fps=1000/{profile.preview_frame_interval_ms},"
                f"scale={profile.preview_frame_width}:{profile.preview_frame_height},"
                f"tile={profile.preview_columns}x{rows}"
            ),
            "-frames:v",
            "1",
            str(sprite_path),
        ]
    )
    sprite_key = f"{asset.public_slice_prefix}/preview/sprite.webp"
    sprite_id = "sprite-main"
    manifest = {
        "schema": "quwoquan.content.preview_track_manifest",
        "assetId": asset.asset_id,
        "assetVersion": asset.asset_version,
        "trackVersion": 1,
        "processorProfile": profile.processor_profile,
        "accessPolicy": "public",
        "frameIntervalMs": profile.preview_frame_interval_ms,
        "sprites": [
            {
                "spriteId": sprite_id,
                "publicSliceKey": sprite_key,
                "mimeType": "image/webp",
                "sha256": _sha256(sprite_path),
                "width": profile.preview_frame_width * profile.preview_columns,
                "height": profile.preview_frame_height * rows,
            }
        ],
        "frames": [
            {
                "timeMs": index * profile.preview_frame_interval_ms,
                "spriteId": sprite_id,
                "x": (index % profile.preview_columns) * profile.preview_frame_width,
                "y": (index // profile.preview_columns) * profile.preview_frame_height,
                "width": profile.preview_frame_width,
                "height": profile.preview_frame_height,
            }
            for index in range(frame_count)
        ],
    }
    _write_json(manifest_path, manifest)
    return sprite_path, manifest_path


def prepare_media_canary_assets(
    *,
    output_root: Path,
    asset_ids: set[str] | None = None,
) -> dict[str, Any]:
    profile = load_media_canary_profile()
    selected = [
        asset
        for asset in profile.assets
        if not asset_ids or asset.asset_id in asset_ids
    ]
    if not selected:
        raise ValueError("no media canary assets matched the requested asset IDs")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    results: list[dict[str, Any]] = []
    for asset in selected:
        root = _asset_root(output_root, asset)
        root.mkdir(parents=True, exist_ok=True)
        video_path = root / "source.mp4"
        cover_path = root / "cover.webp"
        _generate_video(
            ffmpeg=ffmpeg,
            profile=profile,
            asset=asset,
            video_path=video_path,
        )
        _generate_cover(
            ffmpeg=ffmpeg,
            profile=profile,
            video_path=video_path,
            cover_path=cover_path,
        )
        probe = _probe_media(
            ffmpeg=ffmpeg,
            profile=profile,
            video_path=video_path,
        )
        expected_status = (
            "ready"
            if probe["durationMs"] <= profile.product_maximum_duration_ms
            else "rejected"
        )
        if expected_status != asset.expected_processing_status:
            raise ValueError(
                f"{asset.asset_id} probed status {expected_status} differs from profile"
            )
        duration_tolerance_ms = max(1000, asset.duration_ms * 2 // 100)
        if abs(int(probe["durationMs"]) - asset.duration_ms) > duration_tolerance_ms:
            raise ValueError(f"{asset.asset_id} probed duration differs from requested duration")
        descriptor: dict[str, Any] = {
            "schema": "quwoquan.content.media_canary_descriptor",
            "assetId": asset.asset_id,
            "assetVersion": asset.asset_version,
            "processorProfile": profile.processor_profile,
            "expectedProcessingStatus": expected_status,
            **probe,
            "videoPublicSliceKey": f"{asset.public_slice_prefix}/source.mp4",
            "coverPublicSliceKey": f"{asset.public_slice_prefix}/cover.webp",
            "coverSha256": _sha256(cover_path),
            "coverSizeBytes": cover_path.stat().st_size,
        }
        if asset.storyboard:
            sprite_path, manifest_path = _generate_storyboard(
                ffmpeg=ffmpeg,
                profile=profile,
                asset=asset,
                video_path=video_path,
                asset_root=root,
            )
            descriptor.update(
                {
                    "previewTrackVersion": 1,
                    "previewTrackManifestSliceKey": (
                        f"{asset.public_slice_prefix}/preview/manifest.json"
                    ),
                    "previewSpriteSha256": _sha256(sprite_path),
                    "previewSpriteSizeBytes": sprite_path.stat().st_size,
                    "previewManifestSha256": _sha256(manifest_path),
                    "previewManifestSizeBytes": manifest_path.stat().st_size,
                }
            )
        descriptor["probeHash"] = _descriptor_probe_hash(descriptor)
        _write_json(root / "descriptor.json", descriptor)
        results.append(descriptor)
    return {
        "schema": "quwoquan_data.media_canary_result",
        "profileId": profile.profile_id,
        "outputRoot": str(output_root.resolve()),
        "assets": results,
    }


def validate_media_canary_assets(
    *,
    output_root: Path,
    asset_ids: set[str] | None = None,
) -> list[str]:
    profile = load_media_canary_profile()
    issues: list[str] = []
    selected = [
        asset
        for asset in profile.assets
        if not asset_ids or asset.asset_id in asset_ids
    ]
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    for asset in selected:
        root = _asset_root(output_root, asset)
        descriptor_path = root / "descriptor.json"
        if not descriptor_path.is_file():
            issues.append(f"{asset.asset_id}: descriptor.json is missing")
            continue
        try:
            descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            issues.append(f"{asset.asset_id}: descriptor.json is invalid JSON")
            continue
        if not isinstance(descriptor, dict):
            issues.append(f"{asset.asset_id}: descriptor.json must be an object")
            continue
        expected_descriptor_fields = {
            "schema": "quwoquan.content.media_canary_descriptor",
            "assetId": asset.asset_id,
            "assetVersion": asset.asset_version,
            "processorProfile": profile.processor_profile,
            "videoPublicSliceKey": f"{asset.public_slice_prefix}/source.mp4",
            "coverPublicSliceKey": f"{asset.public_slice_prefix}/cover.webp",
        }
        for field, expected_value in expected_descriptor_fields.items():
            if descriptor.get(field) != expected_value:
                issues.append(
                    f"{asset.asset_id}: descriptor {field} differs from profile",
                )
        video_path = root / "source.mp4"
        cover_path = root / "cover.webp"
        if not video_path.is_file() or not cover_path.is_file():
            issues.append(f"{asset.asset_id}: source.mp4 or cover.webp is missing")
            continue
        try:
            probe = _probe_media(
                ffmpeg=ffmpeg,
                profile=profile,
                video_path=video_path,
            )
        except (RuntimeError, ValueError) as error:
            issues.append(f"{asset.asset_id}: video probe failed: {error}")
            continue
        for field, actual_value in probe.items():
            if descriptor.get(field) != actual_value:
                issues.append(
                    f"{asset.asset_id}: descriptor {field} differs from real media probe",
                )
        if descriptor.get("coverSha256") != _sha256(cover_path):
            issues.append(f"{asset.asset_id}: cover sha256 drifted")
        probe_hash = str(descriptor.get("probeHash") or "")
        if not _SHA256_PATTERN.fullmatch(probe_hash):
            issues.append(f"{asset.asset_id}: probeHash is invalid")
        elif probe_hash != _descriptor_probe_hash(descriptor):
            issues.append(f"{asset.asset_id}: probeHash does not bind descriptor fields")
        if descriptor.get("expectedProcessingStatus") != asset.expected_processing_status:
            issues.append(f"{asset.asset_id}: processing status drifted")
        expected_status = (
            "ready"
            if int(probe["durationMs"]) <= profile.product_maximum_duration_ms
            else "rejected"
        )
        if expected_status != asset.expected_processing_status:
            issues.append(
                f"{asset.asset_id}: real media probe status {expected_status} "
                "differs from profile",
            )
        duration_tolerance_ms = max(1000, asset.duration_ms * 2 // 100)
        if abs(int(probe["durationMs"]) - asset.duration_ms) > duration_tolerance_ms:
            issues.append(
                f"{asset.asset_id}: real media probe duration differs from requested duration",
            )
        if asset.expected_processing_status == "ready":
            if probe["videoCodec"] not in {"h264", "avc1"}:
                issues.append(f"{asset.asset_id}: video codec is not H.264")
            if probe["videoAudioCodec"] != "aac":
                issues.append(f"{asset.asset_id}: audio codec is not AAC")
            if probe["videoFastStart"] is not True:
                issues.append(f"{asset.asset_id}: MP4 is not fast-start")
            if int(probe["videoKeyframeIntervalMs"]) > 2000:
                issues.append(f"{asset.asset_id}: keyframe interval exceeds 2000ms")
        if asset.storyboard:
            manifest_path = root / "preview/manifest.json"
            sprite_path = root / "preview/sprite.webp"
            issues.extend(
                validate_storyboard(
                    asset=asset,
                    profile=profile,
                    descriptor=descriptor,
                    manifest_path=manifest_path,
                    sprite_path=sprite_path,
                )
            )
        elif any(str(key).startswith("preview") for key in descriptor):
            issues.append(f"{asset.asset_id}: non-storyboard asset carries preview fields")
    return issues


__all__ = [
    "MediaCanaryAsset",
    "MediaCanaryProfile",
    "load_media_canary_profile",
    "prepare_media_canary_assets",
    "validate_media_canary_assets",
]
