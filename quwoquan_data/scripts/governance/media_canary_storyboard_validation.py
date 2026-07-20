"""Validation for a media canary storyboard derived from a video asset."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from governance.media_canary_profile import MediaCanaryAsset, MediaCanaryProfile


def validate_storyboard(
    *,
    asset: MediaCanaryAsset,
    profile: MediaCanaryProfile,
    descriptor: Mapping[str, Any],
    manifest_path: Path,
    sprite_path: Path,
) -> list[str]:
    """Return all descriptor and frame-level storyboard drift findings."""
    issues: list[str] = []
    if not manifest_path.is_file() or not sprite_path.is_file():
        return [f"{asset.asset_id}: storyboard files are missing"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [f"{asset.asset_id}: storyboard manifest is invalid JSON"]
    if not isinstance(manifest, dict):
        return [f"{asset.asset_id}: storyboard manifest must be an object"]

    expected_frame_count = (
        (asset.duration_ms - 1) // profile.preview_frame_interval_ms + 1
    )
    expected_manifest_fields = {
        "schema": "quwoquan.content.preview_track_manifest",
        "assetId": asset.asset_id,
        "assetVersion": asset.asset_version,
        "trackVersion": 1,
        "processorProfile": profile.processor_profile,
        "accessPolicy": "public",
        "frameIntervalMs": profile.preview_frame_interval_ms,
    }
    for field, expected_value in expected_manifest_fields.items():
        if manifest.get(field) != expected_value:
            issues.append(f"{asset.asset_id}: storyboard {field} differs from profile")

    frames = manifest.get("frames")
    if not isinstance(frames, list) or len(frames) != expected_frame_count:
        issues.append(f"{asset.asset_id}: storyboard frame count drifted")
    sprites = manifest.get("sprites")
    if (
        not isinstance(sprites, list)
        or len(sprites) != 1
        or not isinstance(sprites[0], dict)
    ):
        issues.append(f"{asset.asset_id}: storyboard sprite digest drifted")
    else:
        expected_sprite_fields = {
            "spriteId": "sprite-main",
            "publicSliceKey": f"{asset.public_slice_prefix}/preview/sprite.webp",
            "mimeType": "image/webp",
            "sha256": _sha256(sprite_path),
            "width": profile.preview_frame_width * profile.preview_columns,
            "height": profile.preview_frame_height
            * ((expected_frame_count + profile.preview_columns - 1)
               // profile.preview_columns),
        }
        for field, expected_value in expected_sprite_fields.items():
            if sprites[0].get(field) != expected_value:
                issues.append(
                    f"{asset.asset_id}: storyboard sprite {field} drifted",
                )

    if isinstance(frames, list) and len(frames) == expected_frame_count:
        for index, frame in enumerate(frames):
            expected_frame = {
                "timeMs": index * profile.preview_frame_interval_ms,
                "spriteId": "sprite-main",
                "x": (index % profile.preview_columns) * profile.preview_frame_width,
                "y": (index // profile.preview_columns) * profile.preview_frame_height,
                "width": profile.preview_frame_width,
                "height": profile.preview_frame_height,
            }
            if frame != expected_frame:
                issues.append(f"{asset.asset_id}: storyboard frame {index} drifted")
                break

    expected_descriptor_fields = {
        "previewTrackVersion": 1,
        "previewTrackManifestSliceKey": (
            f"{asset.public_slice_prefix}/preview/manifest.json"
        ),
        "previewSpriteSha256": _sha256(sprite_path),
        "previewSpriteSizeBytes": sprite_path.stat().st_size,
        "previewManifestSha256": _sha256(manifest_path),
        "previewManifestSizeBytes": manifest_path.stat().st_size,
    }
    for field, expected_value in expected_descriptor_fields.items():
        if descriptor.get(field) != expected_value:
            issues.append(f"{asset.asset_id}: descriptor {field} drifted")
    return issues


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"
