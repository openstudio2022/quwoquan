from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import sys
from pathlib import Path

import imageio_ffmpeg


SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from governance import media_probe
from governance.media_probe import (
    MediaProbeAsset,
    _generate_video,
    load_media_probe_profile,
)


def test_media_probe_freezes_minute_hour_and_rejection_boundaries() -> None:
    profile = load_media_probe_profile()

    assets = {asset.asset_id: asset for asset in profile.assets}
    minute = assets["media-probe-seek-125s"]
    near_hour = assets["media-probe-hour-boundary-3595s"]
    over_limit = assets["media-probe-over-limit-3605s"]

    assert profile.product_maximum_duration_ms == 3_600_000
    assert profile.keyframe_interval_ms == 2_000
    assert minute.duration_ms == 125_000
    assert minute.storyboard is True
    assert minute.expected_processing_status == "ready"
    assert near_hour.duration_ms == 3_595_000
    assert near_hour.expected_processing_status == "ready"
    assert over_limit.duration_ms == 3_605_000
    assert over_limit.expected_processing_status == "rejected"


def test_media_probe_public_slices_are_canonical_and_unique() -> None:
    profile = load_media_probe_profile()

    prefixes = [asset.public_slice_prefix for asset in profile.assets]
    assert len(prefixes) == len(set(prefixes))
    assert all(prefix.startswith("media/video/s/") for prefix in prefixes)
    assert all("fixture" not in prefix and "mock" not in prefix for prefix in prefixes)


def test_media_probe_encoder_is_byte_deterministic(tmp_path: Path) -> None:
    profile = load_media_probe_profile()
    asset = MediaProbeAsset(
        asset_id="media-probe-determinism-2s",
        asset_version=1,
        duration_ms=2_000,
        frames_per_second=2,
        expected_processing_status="ready",
        storyboard=False,
        public_slice_prefix="media/video/s/media-probe-determinism-2s/v1",
    )
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"

    _generate_video(
        ffmpeg=ffmpeg,
        profile=profile,
        asset=asset,
        video_path=first,
    )
    _generate_video(
        ffmpeg=ffmpeg,
        profile=profile,
        asset=asset,
        video_path=second,
    )

    assert first.stat().st_size == second.stat().st_size
    assert hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(
        second.read_bytes()
    ).digest()


def test_media_probe_validation_reprobes_descriptor_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base_profile = load_media_probe_profile()
    asset = MediaProbeAsset(
        asset_id="media-probe-probe-5s",
        asset_version=1,
        duration_ms=5_000,
        frames_per_second=2,
        expected_processing_status="ready",
        storyboard=True,
        public_slice_prefix="media/video/s/media-probe-probe-5s/v1",
    )
    profile = replace(
        base_profile,
        assets=(asset,),
        preview_frame_width=24,
        preview_frame_height=42,
        preview_columns=1,
    )
    monkeypatch.setattr(media_probe, "load_media_probe_profile", lambda: profile)

    media_probe.prepare_media_probe_assets(output_root=tmp_path)

    assert media_probe.validate_media_probe_assets(output_root=tmp_path) == []

    descriptor_path = tmp_path / asset.public_slice_prefix / "descriptor.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    descriptor["durationMs"] = 1
    descriptor["probeHash"] = media_probe._descriptor_probe_hash(descriptor)
    descriptor_path.write_text(
        json.dumps(descriptor, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    issues = media_probe.validate_media_probe_assets(output_root=tmp_path)

    assert any(
        "descriptor durationMs differs from real media probe" in issue
        for issue in issues
    )

    manifest_path = tmp_path / asset.public_slice_prefix / "preview" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assetVersion"] = 99
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    issues = media_probe.validate_media_probe_assets(output_root=tmp_path)

    assert any(
        "storyboard assetVersion differs from profile" in issue for issue in issues
    )
