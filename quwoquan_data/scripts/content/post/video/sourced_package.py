"""Transcode one admitted source video into the canonical video package."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

import cv2
import imageio_ffmpeg

from content.post.video.package_common import (
    cas_object_key,
    sha256_file,
    subtitles,
)
from content.post.video.source_video import SourcedVideoAsset
from content.execution.identity import parse_execution_id
from core.asset_identity import compute_post_asset_id
from core.io import write_json
from core.runtime_policy import active_runtime_policy
from core.schema import validate_result
from governance.content_supply_policy import VideoDeliveryPolicy
from governance.coverage.license import RightsAuditStatus


@dataclass(frozen=True, slots=True)
class SourcedVideoPackageRequest:
    output_dir: Path
    execution_id: str
    execution_sequence: int
    topic_id: str
    entity_ref: str
    tag_refs: tuple[str, ...]
    title: str
    caption: str
    script_lines: tuple[str, ...]
    source: SourcedVideoAsset
    author_id: str
    creator_profile_id: str
    agent_run_id: str
    agent_model: str
    created_at: str


def _probe(path: Path) -> tuple[int, int, int]:
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError(f"sourced video is not decodable: {path}")
        width = round(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frames = round(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if width <= 0 or height <= 0 or frames <= 0 or fps <= 0:
            raise ValueError(f"sourced video probe is incomplete: {path}")
        return width, height, max(1, round(frames / fps * 1000))
    finally:
        capture.release()


def _transcode(
    source: Path,
    target: Path,
    *,
    policy: VideoDeliveryPolicy,
    preserve_authorized_audio: bool,
) -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    scale = (
        f"scale={policy.width}:{policy.height}:"
        "force_original_aspect_ratio=decrease,"
        f"pad={policy.width}:{policy.height}:(ow-iw)/2:(oh-ih)/2:black,"
        "setsar=1"
    )
    command = [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-vf",
            scale,
            "-r",
            str(policy.frames_per_second),
            "-t",
            str(policy.maximum_duration_seconds),
            "-c:v",
            "libx264",
            "-pix_fmt",
            policy.pixel_format,
            "-movflags",
            "+faststart",
    ]
    if preserve_authorized_audio:
        command.extend(["-map", "0:a?", "-c:a", "aac", "-b:a", "128k"])
    else:
        command.append("-an")
    command.append(str(target))
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=active_runtime_policy().video_transcode_timeout_seconds,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()
        raise RuntimeError(
            "sourced video transcode failed: "
            + (detail[-1] if detail else "unknown ffmpeg failure")
        )


def _poster(video_path: Path, poster_path: Path) -> None:
    capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            raise ValueError("transcoded sourced video is not decodable")
        ok, frame = capture.read()
        if not ok or frame is None:
            raise ValueError("transcoded sourced video has no poster frame")
        if not cv2.imwrite(str(poster_path), frame):
            raise RuntimeError("sourced video poster encoding failed")
    finally:
        capture.release()


def render_sourced_video_package(
    request: SourcedVideoPackageRequest,
    *,
    policy: VideoDeliveryPolicy,
) -> Path:
    identity = parse_execution_id(request.execution_id)
    evidence = request.source.evidence
    issues = evidence.admission_issues()
    if issues:
        raise ValueError("sourced video admission failed: " + "; ".join(issues))
    if not request.source.path.is_file():
        raise ValueError(f"sourced video asset is missing: {request.source.path}")
    if sha256_file(request.source.path) != evidence.sha256:
        raise ValueError("sourced video sha256 differs from admitted evidence")
    if not request.script_lines or any(
        not line.strip() for line in request.script_lines
    ):
        raise ValueError("sourced video script lines must be non-empty")
    _, _, source_duration_ms = _probe(request.source.path)
    if source_duration_ms < policy.minimum_duration_seconds * 1000:
        raise ValueError("sourced video is shorter than delivery minimum")

    assets_dir = request.output_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    video_path = assets_dir / "video.mp4"
    poster_path = assets_dir / "poster.webp"
    subtitles_path = request.output_dir / "subtitles.vtt"
    provenance_path = request.output_dir / "provenance.json"
    preserve_authorized_audio = (
        evidence.audio_rights_status != "no_audio"
    )
    _transcode(
        request.source.path,
        video_path,
        policy=policy,
        preserve_authorized_audio=preserve_authorized_audio,
    )
    width, height, duration_ms = _probe(video_path)
    if not (
        policy.minimum_duration_seconds * 1000
        <= duration_ms
        <= policy.maximum_duration_seconds * 1000 + 1000
    ):
        raise ValueError("transcoded sourced video duration violates policy")
    _poster(video_path, poster_path)
    subtitles_path.write_text(
        subtitles(request.script_lines, duration_ms / 1000),
        encoding="utf-8",
    )

    provenance = {
        "executionId": request.execution_id,
        "agentRunId": request.agent_run_id,
        "agentModel": request.agent_model,
        "renderStrategy": "sourced_video_transcode",
        "outputAudioStatus": (
            "preserved_authorized"
            if preserve_authorized_audio
            else "none"
        ),
        "sources": [
            {
                **evidence.to_dict(),
                "basis": evidence.rights_basis,
            }
        ],
    }
    write_json(provenance_path, provenance)

    video_sha = sha256_file(video_path)
    poster_sha = sha256_file(poster_path)
    subtitles_sha = sha256_file(subtitles_path)
    entity_name = request.entity_ref.rstrip("/").rsplit("/", 1)[-1]
    asset_id = compute_post_asset_id(
        entity_name=entity_name,
        role="detail",
        execution_sequence=request.execution_sequence,
        ref=request.topic_id,
        caption=request.caption,
    )
    poster_asset_id = compute_post_asset_id(
        entity_name=entity_name,
        role="cover",
        execution_sequence=request.execution_sequence,
        ref=request.topic_id,
        caption=request.caption,
    )
    manifest = {
        "schema": "quwoquan_data.post_manifest",
        "vertical": identity.vertical,
        "topicId": request.topic_id,
        "contentType": "video",
        "contentIdentity": "work",
        "carrier": "video",
        "title": request.title,
        "caption": request.caption,
        "entityRefs": [request.entity_ref],
        "tagRefs": list(request.tag_refs),
        "sourceUrls": [evidence.source_post_url],
        "sourceAttribution": evidence.post_attribution_dict(),
        "authorId": request.author_id,
        "creatorProfileId": request.creator_profile_id,
        "generator": "agent",
        "generatorModel": request.agent_model,
        "agentRunId": request.agent_run_id,
        "createdAt": request.created_at,
        "updatedAt": request.created_at,
        "executionId": request.execution_id,
        "assets": [
            {
                "assetId": asset_id,
                "fileName": "assets/video.mp4",
                "kind": "video",
                "objectKey": cas_object_key(video_sha, "mp4"),
                "sha256": video_sha,
                "mimeType": "video/mp4",
                "durationMs": duration_ms,
                "width": width,
                "height": height,
                "container": policy.container,
                "codec": policy.codec,
                "pixelFormat": policy.pixel_format,
                "posterFileName": "assets/poster.webp",
                "posterAssetId": poster_asset_id,
                "subtitlesFileName": "subtitles.vtt",
                "posterSha256": poster_sha,
                "subtitlesSha256": subtitles_sha,
                "provenanceRef": "provenance.json",
                "sourceAssetRefs": [evidence.asset_ref],
                "rightsRefs": [evidence.rights_ref],
                "rightsAuditStatus": RightsAuditStatus.VERIFIED.value,
                "rightsAuditIssues": [],
                "coverStrategy": "manual",
            },
            {
                "assetId": poster_asset_id,
                "fileName": "assets/poster.webp",
                "kind": "image",
                "role": "cover",
                "objectKey": cas_object_key(poster_sha, "webp"),
                "sha256": poster_sha,
                "mimeType": "image/webp",
                "width": width,
                "height": height,
                "caption": request.caption,
                "sourceAssetRefs": [evidence.asset_ref],
                "rightsRefs": [evidence.rights_ref],
                "rightsAuditStatus": RightsAuditStatus.VERIFIED.value,
                "rightsAuditIssues": [],
            },
        ],
        "videoBindings": [{"assetId": asset_id, "role": "shortVideo"}],
    }
    schema_issues = validate_result(manifest, "content", "post_manifest")
    if schema_issues:
        raise ValueError(
            "sourced video manifest contract failed: "
            + "; ".join(schema_issues)
        )
    write_json(request.output_dir / "manifest.json", manifest)
    return request.output_dir


__all__ = ["SourcedVideoPackageRequest", "render_sourced_video_package"]
