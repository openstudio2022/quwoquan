"""Deterministic renderer and validator for formal short-video work packages."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import cv2
import numpy as np

from core.asset_identity import compute_post_asset_id
from core.io import read_json, write_json
from core.schema import validate_result
from content.post.video.package_common import (
    cas_object_key as _cas_object_key,
    sha256_file as _sha256,
    subtitles as _subtitles,
)
from content.post.video.source_video import SourcedVideoAsset
from governance.content_supply_policy import (
    VideoDeliveryPolicy,
    load_content_supply_policy,
)
from governance.coverage.license import RightsAuditStatus, rights_proof_required
from content.execution.identity import parse_execution_id


class VideoSourceBasis(StrEnum):
    SELF_GENERATED = "self_generated"
    RIGHTS_CLEARED = "rights_cleared"


@dataclass(frozen=True, slots=True)
class VideoSourceFrame:
    path: Path
    asset_ref: str
    source_url: str
    rights_ref: str
    creator: str
    license: str
    basis: VideoSourceBasis
    source_use_mode: str
    rights_audit_status: RightsAuditStatus
    rights_audit_issues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VideoRenderRequest:
    output_dir: Path
    execution_id: str
    execution_sequence: int
    topic_id: str
    entity_ref: str
    tag_refs: tuple[str, ...]
    title: str
    caption: str
    script_lines: tuple[str, ...]
    source_frames: tuple[VideoSourceFrame, ...]
    author_id: str
    creator_profile_id: str
    agent_run_id: str
    agent_model: str
    created_at: str
    source_video: SourcedVideoAsset | None = None


def _validate_request(
    request: VideoRenderRequest,
    policy: VideoDeliveryPolicy,
    *,
    require_rights_proof: bool,
) -> int:
    if not request.source_frames:
        raise ValueError("video render requires at least one source frame")
    if not request.title.strip() or not request.caption.strip():
        raise ValueError("video title and caption are required")
    if not request.agent_run_id.strip() or not request.agent_model.strip():
        raise ValueError("video script must carry Agent run and model evidence")
    for frame in request.source_frames:
        if not frame.path.is_file():
            raise ValueError(f"video source frame is missing: {frame.path}")
        if not all(
            value.strip()
            for value in (
                frame.asset_ref,
                frame.source_url,
                frame.rights_ref,
                frame.creator,
                frame.license,
            )
        ):
            raise ValueError(f"video source frame rights evidence is incomplete: {frame.path}")
        if frame.source_use_mode not in {
            "licensed_adaptation",
            "factual_reference_only",
        }:
            raise ValueError(
                f"video source frame sourceUseMode is invalid: {frame.path}"
            )
        if not isinstance(frame.rights_audit_status, RightsAuditStatus):
            raise ValueError(
                f"video source frame rightsAuditStatus is invalid: {frame.path}"
            )
        if (
            frame.rights_audit_status is RightsAuditStatus.UNVERIFIED
            and not frame.rights_audit_issues
        ):
            raise ValueError(
                f"unverified video source frame must record rightsAuditIssues: {frame.path}"
            )
        if require_rights_proof and (
            frame.rights_audit_status is not RightsAuditStatus.VERIFIED
            or frame.rights_audit_issues
        ):
            raise ValueError(
                f"commercial video source frame rights are not verified: {frame.path}"
            )
    minimum_segments = policy.minimum_segment_count
    segment_count = max(len(request.source_frames), minimum_segments)
    duration_seconds = segment_count * policy.segment_duration_seconds
    if duration_seconds > policy.maximum_duration_seconds:
        raise ValueError(
            f"video duration exceeds policy: {duration_seconds}>"
            f"{policy.maximum_duration_seconds} seconds"
        )
    if len(request.script_lines) != segment_count:
        raise ValueError(
            f"video script line count must equal rendered segments: "
            f"{len(request.script_lines)}!={segment_count}"
        )
    if any(not line.strip() for line in request.script_lines):
        raise ValueError("video script lines must be non-empty")
    return segment_count


def _portrait_frame(path: Path, policy: VideoDeliveryPolicy) -> np.ndarray:
    source = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if source is None or source.size == 0:
        raise ValueError(f"video source frame is unreadable: {path}")
    source_height, source_width = source.shape[:2]
    scale = min(policy.width / source_width, policy.height / source_height)
    resized = cv2.resize(
        source,
        (
            max(1, round(source_width * scale)),
            max(1, round(source_height * scale)),
        ),
        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
    )
    canvas = np.zeros((policy.height, policy.width, 3), dtype=np.uint8)
    y = (policy.height - resized.shape[0]) // 2
    x = (policy.width - resized.shape[1]) // 2
    canvas[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return canvas


def render_video_work_package(request: VideoRenderRequest) -> Path:
    identity = parse_execution_id(request.execution_id)
    policy = load_content_supply_policy(identity.vertical).video_delivery
    if request.source_video is not None:
        if request.source_frames:
            raise ValueError(
                "sourced video and image-sequence frames are mutually exclusive"
            )
        if not request.title.strip() or not request.caption.strip():
            raise ValueError("video title and caption are required")
        if not request.agent_run_id.strip() or not request.agent_model.strip():
            raise ValueError("video script must carry Agent run and model evidence")
        if len(request.script_lines) != policy.minimum_segment_count:
            raise ValueError(
                "sourced video script line count must equal delivery policy"
            )
        from content.post.video.sourced_package import (
            SourcedVideoPackageRequest,
            render_sourced_video_package,
        )

        package = render_sourced_video_package(
            SourcedVideoPackageRequest(
                output_dir=request.output_dir,
                execution_id=request.execution_id,
                execution_sequence=request.execution_sequence,
                topic_id=request.topic_id,
                entity_ref=request.entity_ref,
                tag_refs=request.tag_refs,
                title=request.title,
                caption=request.caption,
                script_lines=request.script_lines,
                source=request.source_video,
                author_id=request.author_id,
                creator_profile_id=request.creator_profile_id,
                agent_run_id=request.agent_run_id,
                agent_model=request.agent_model,
                created_at=request.created_at,
            ),
            policy=policy,
        )
        issues = validate_video_work_package(package)
        if issues:
            raise ValueError(
                "sourced video package validation failed: " + "; ".join(issues)
            )
        return package
    segment_count = _validate_request(
        request,
        policy,
        require_rights_proof=rights_proof_required(identity.vertical),
    )
    assets_dir = request.output_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    video_path = assets_dir / "video.mp4"
    poster_path = assets_dir / "poster.webp"
    subtitles_path = request.output_dir / "subtitles.vtt"
    provenance_path = request.output_dir / "provenance.json"

    rendered_frames = [
        _portrait_frame(
            request.source_frames[index % len(request.source_frames)].path,
            policy,
        )
        for index in range(segment_count)
    ]
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"avc1"),
        float(policy.frames_per_second),
        (policy.width, policy.height),
    )
    if not writer.isOpened():
        raise RuntimeError("H.264 video encoder is unavailable")
    try:
        frames_per_segment = policy.frames_per_second * policy.segment_duration_seconds
        for frame in rendered_frames:
            for _ in range(frames_per_segment):
                writer.write(frame)
    finally:
        writer.release()
    if not cv2.imwrite(str(poster_path), rendered_frames[0]):
        raise RuntimeError("video poster encoding failed")
    subtitles_path.write_text(
        _subtitles(
            request.script_lines,
            segment_count * policy.segment_duration_seconds,
        ),
        encoding="utf-8",
    )
    provenance = {
        "executionId": request.execution_id,
        "agentRunId": request.agent_run_id,
        "agentModel": request.agent_model,
        "renderStrategy": "rights_cleared_image_sequence",
        "sources": [
            {
                "assetRef": frame.asset_ref,
                "sourceUrl": frame.source_url,
                "rightsRef": frame.rights_ref,
                "creator": frame.creator,
                "license": frame.license,
                "basis": frame.basis.value,
                "sourceUseMode": frame.source_use_mode,
                "rightsAuditStatus": frame.rights_audit_status.value,
                "rightsAuditIssues": list(frame.rights_audit_issues),
                "sha256": _sha256(frame.path),
            }
            for frame in request.source_frames
        ],
    }
    write_json(provenance_path, provenance)
    video_sha = _sha256(video_path)
    poster_sha = _sha256(poster_path)
    subtitles_sha = _sha256(subtitles_path)
    duration_ms = (
        segment_count * policy.segment_duration_seconds * 1000
    )
    asset_id = compute_post_asset_id(
        entity_name=request.entity_ref.rstrip("/").rsplit("/", 1)[-1],
        role="detail",
        execution_sequence=request.execution_sequence,
        ref=request.topic_id,
        caption=request.caption,
    )
    poster_asset_id = compute_post_asset_id(
        entity_name=request.entity_ref.rstrip("/").rsplit("/", 1)[-1],
        role="cover",
        execution_sequence=request.execution_sequence,
        ref=request.topic_id,
        caption=request.caption,
    )
    source_asset_refs = [frame.asset_ref for frame in request.source_frames]
    rights_refs = [frame.rights_ref for frame in request.source_frames]
    rights_audit_issues = list(
        dict.fromkeys(
            issue
            for frame in request.source_frames
            for issue in frame.rights_audit_issues
            if issue
        )
    )
    rights_audit_status = (
        RightsAuditStatus.VERIFIED
        if all(
            frame.rights_audit_status is RightsAuditStatus.VERIFIED
            and not frame.rights_audit_issues
            for frame in request.source_frames
        )
        else RightsAuditStatus.UNVERIFIED
    )
    manifest = {
        "schema": "quwoquan_data.post_manifest",
        "vertical": identity.vertical,
        "topicId": request.topic_id,
        "contentType": "video",
        "carrier": "video",
        "title": request.title,
        "caption": request.caption,
        "entityRefs": [request.entity_ref],
        "tagRefs": list(request.tag_refs),
        "sourceUrls": [frame.source_url for frame in request.source_frames],
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
                "objectKey": _cas_object_key(video_sha, "mp4"),
                "sha256": video_sha,
                "mimeType": "video/mp4",
                "durationMs": duration_ms,
                "width": policy.width,
                "height": policy.height,
                "container": policy.container,
                "codec": policy.codec,
                "pixelFormat": policy.pixel_format,
                "posterFileName": "assets/poster.webp",
                "posterAssetId": poster_asset_id,
                "subtitlesFileName": "subtitles.vtt",
                "posterSha256": poster_sha,
                "subtitlesSha256": subtitles_sha,
                "provenanceRef": "provenance.json",
                "sourceAssetRefs": source_asset_refs,
                "rightsRefs": rights_refs,
                "rightsAuditStatus": rights_audit_status.value,
                "rightsAuditIssues": rights_audit_issues,
                "coverStrategy": "manual",
            },
            {
                "assetId": poster_asset_id,
                "fileName": "assets/poster.webp",
                "kind": "image",
                "role": "cover",
                "objectKey": _cas_object_key(poster_sha, "webp"),
                "sha256": poster_sha,
                "mimeType": "image/webp",
                "width": policy.width,
                "height": policy.height,
                "caption": request.caption,
                "sourceAssetRefs": source_asset_refs,
                "rightsRefs": rights_refs,
                "rightsAuditStatus": rights_audit_status.value,
                "rightsAuditIssues": rights_audit_issues,
            },
        ],
        "videoBindings": [{"assetId": asset_id, "role": "shortVideo"}],
    }
    schema_issues = validate_result(manifest, "content", "post_manifest")
    if schema_issues:
        raise ValueError("video manifest contract failed: " + "; ".join(schema_issues))
    write_json(request.output_dir / "manifest.json", manifest)
    validation_issues = validate_video_work_package(request.output_dir)
    if validation_issues:
        raise ValueError("video package validation failed: " + "; ".join(validation_issues))
    return request.output_dir


def _video_codec(capture: cv2.VideoCapture) -> str:
    fourcc = int(capture.get(cv2.CAP_PROP_FOURCC))
    return "".join(chr((fourcc >> (8 * index)) & 0xFF) for index in range(4)).lower()


def validate_video_work_package(package_dir: Path) -> list[str]:
    manifest_path = package_dir / "manifest.json"
    if not manifest_path.is_file():
        return ["video manifest is missing"]
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        return ["video manifest must be an object"]
    try:
        vertical = parse_execution_id(
            str(manifest.get("executionId") or "")
        ).vertical
        policy = load_content_supply_policy(vertical).video_delivery
        require_rights_proof = rights_proof_required(vertical)
    except (TypeError, ValueError) as exc:
        return [f"video manifest execution identity is invalid: {exc}"]
    issues = validate_result(manifest, "content", "post_manifest")
    assets = manifest.get("assets") if isinstance(manifest, dict) else None
    video_assets = [
        asset
        for asset in (assets or [])
        if isinstance(asset, dict) and asset.get("kind") == "video"
    ]
    if len(video_assets) != 1:
        return [*issues, "video package must contain exactly one video asset"]
    asset = video_assets[0]
    poster_asset_id = str(asset.get("posterAssetId") or "").strip()
    poster_assets = [
        item
        for item in (assets or [])
        if isinstance(item, dict)
        and item.get("assetId") == poster_asset_id
        and item.get("kind") == "image"
        and item.get("role") == "cover"
    ]
    if len(poster_assets) != 1:
        issues.append("video posterAssetId must resolve to exactly one cover image asset")
    elif str(poster_assets[0].get("sha256") or "") != str(asset.get("posterSha256") or ""):
        issues.append("video poster asset digest does not match posterSha256")
    for media_asset in (asset, *poster_assets):
        status = str(media_asset.get("rightsAuditStatus") or "").strip()
        if status not in {item.value for item in RightsAuditStatus}:
            issues.append("video asset rightsAuditStatus is invalid")
        elif (
            status == RightsAuditStatus.UNVERIFIED.value
            and not media_asset.get("rightsAuditIssues")
        ):
            issues.append("unverified video asset must record rightsAuditIssues")
        elif require_rights_proof and (
            status != RightsAuditStatus.VERIFIED.value
            or bool(media_asset.get("rightsAuditIssues"))
        ):
            issues.append("commercial video asset rights must be verified without issues")
        elif (
            status == RightsAuditStatus.VERIFIED.value
            and media_asset.get("rightsAuditIssues")
        ):
            issues.append("verified video asset must not record rightsAuditIssues")
    file_fields = {
        "fileName": "sha256",
        "posterFileName": "posterSha256",
        "subtitlesFileName": "subtitlesSha256",
        "provenanceRef": None,
    }
    resolved: dict[str, Path] = {}
    for field, hash_field in file_fields.items():
        relative = str(asset.get(field) or "").strip()
        path = (package_dir / relative).resolve()
        try:
            path.relative_to(package_dir.resolve())
        except ValueError:
            issues.append(f"video {field} escapes package root")
            continue
        resolved[field] = path
        if not path.is_file():
            issues.append(f"video {field} is missing: {relative}")
        elif hash_field and _sha256(path) != str(asset.get(hash_field) or ""):
            issues.append(f"video {hash_field} mismatch")
    video_path = resolved.get("fileName")
    if video_path and video_path.is_file():
        capture = cv2.VideoCapture(str(video_path))
        try:
            if not capture.isOpened():
                issues.append("video file is not decodable")
            else:
                width = round(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                if (width, height) != (policy.width, policy.height):
                    issues.append(f"video dimensions mismatch: {width}x{height}")
                if _video_codec(capture) not in {"h264", "avc1"}:
                    issues.append("video codec is not H.264")
        finally:
            capture.release()
    subtitles_path = resolved.get("subtitlesFileName")
    if subtitles_path and subtitles_path.is_file():
        text = subtitles_path.read_text(encoding="utf-8")
        if not text.startswith("WEBVTT\n") or " --> " not in text:
            issues.append("video subtitles are not a valid non-empty WebVTT document")
    provenance_path = resolved.get("provenanceRef")
    if provenance_path and provenance_path.is_file():
        provenance = read_json(provenance_path)
        sources = provenance.get("sources") if isinstance(provenance, dict) else None
        if not isinstance(sources, list) or not sources:
            issues.append("video provenance sources are missing")
        elif provenance.get("renderStrategy") == "sourced_video_transcode":
            attribution = manifest.get("sourceAttribution")
            required = (
                "originalCreatorName",
                "platform",
                "sourcePostUrl",
                "originalAssetUrl",
                "attributionText",
                "rightsBasis",
                "commercialAuthorizationStatus",
                "publicationAdmission",
                "watermarkStatus",
                "audioRightsStatus",
                "collectedAt",
                "takedownPolicy",
            )
            if len(sources) != 1 or not isinstance(sources[0], dict):
                issues.append(
                    "sourced video provenance must contain exactly one source"
                )
            elif any(not sources[0].get(field) for field in required):
                issues.append(
                    "sourced video provenance attribution is incomplete"
                )
            if not isinstance(attribution, dict) or any(
                not attribution.get(field) for field in required
            ):
                issues.append("sourced video manifest attribution is incomplete")
            elif attribution.get("watermarkStatus") != "absent":
                issues.append("sourced video manifest watermark is not absent")
        elif any(
            not isinstance(source, dict)
            or not source.get("rightsRef")
            or source.get("basis") not in {item.value for item in VideoSourceBasis}
            for source in sources
        ):
            issues.append("video provenance contains an invalid source rights record")
    return issues


__all__ = [
    "VideoRenderRequest",
    "VideoSourceBasis",
    "VideoSourceFrame",
    "render_video_work_package",
    "validate_video_work_package",
]
