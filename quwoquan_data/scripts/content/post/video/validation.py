"""Validate canonical sourced-video work packages."""
from __future__ import annotations

from pathlib import Path

import cv2

from content.execution.identity import parse_execution_id
from content.post.video.package_common import sha256_file
from core.io import read_json
from core.schema import validate_result
from governance.content_supply_policy import load_content_supply_policy
from governance.coverage.license import RightsAuditStatus


def _video_codec(capture: cv2.VideoCapture) -> str:
    fourcc = int(capture.get(cv2.CAP_PROP_FOURCC))
    return "".join(
        chr((fourcc >> (8 * index)) & 0xFF) for index in range(4)
    ).lower()


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
    except (TypeError, ValueError) as exc:
        return [f"video manifest execution identity is invalid: {exc}"]
    issues = validate_result(manifest, "content", "post_manifest")
    assets = manifest.get("assets")
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
        issues.append(
            "video posterAssetId must resolve to exactly one cover image asset"
        )
    elif str(poster_assets[0].get("sha256") or "") != str(
        asset.get("posterSha256") or ""
    ):
        issues.append("video poster asset digest does not match posterSha256")
    for media_asset in (asset, *poster_assets):
        status = str(media_asset.get("rightsAuditStatus") or "").strip()
        if status not in {item.value for item in RightsAuditStatus}:
            issues.append("video asset rightsAuditStatus is invalid")
        elif status != RightsAuditStatus.VERIFIED.value and not media_asset.get(
            "rightsAuditIssues"
        ):
            issues.append("unverified video asset must record rightsAuditIssues")
        elif (
            status == RightsAuditStatus.VERIFIED.value
            and media_asset.get("rightsAuditIssues")
        ):
            issues.append("verified video asset must not record rightsAuditIssues")
    resolved: dict[str, Path] = {}
    for field, hash_field in {
        "fileName": "sha256",
        "posterFileName": "posterSha256",
        "subtitlesFileName": "subtitlesSha256",
        "provenanceRef": None,
    }.items():
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
        elif hash_field and sha256_file(path) != str(asset.get(hash_field) or ""):
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
            issues.append(
                "video subtitles are not a valid non-empty WebVTT document"
            )
    provenance_path = resolved.get("provenanceRef")
    if provenance_path and provenance_path.is_file():
        provenance = read_json(provenance_path)
        sources = (
            provenance.get("sources") if isinstance(provenance, dict) else None
        )
        provenance_required = (
            "originalCreatorName",
            "platform",
            "sourcePostUrl",
            "originalAssetUrl",
            "attributionText",
            "rightsBasis",
            "commercialAuthorizationStatus",
            "distributionDecision",
            "watermarkStatus",
            "audioRightsStatus",
            "takedownPolicy",
            "collectedAt",
        )
        attribution_required = tuple(
            "publicationAdmission" if field == "distributionDecision" else field
            for field in provenance_required
        )
        if provenance.get("renderStrategy") != "sourced_video_transcode":
            issues.append("video provenance must use sourced_video_transcode")
        if (
            not isinstance(sources, list)
            or len(sources) != 1
            or not isinstance(sources[0], dict)
        ):
            issues.append("sourced video provenance must contain exactly one source")
        elif any(not sources[0].get(field) for field in provenance_required):
            issues.append("sourced video provenance attribution is incomplete")
        attribution = manifest.get("sourceAttribution")
        if not isinstance(attribution, dict) or any(
            not attribution.get(field) for field in attribution_required
        ):
            issues.append("video manifest sourceAttribution is incomplete")
        elif "derivedModifications" not in attribution:
            # 在场为空（空数组 = 逐字节原样）是合法事实，缺席不是：缺席时读不出
            # 交付副本到底有没有被改过，所以不能与空数组同路放行。
            issues.append(
                "video manifest sourceAttribution omits derivedModifications"
            )
        elif attribution.get("watermarkStatus") != "absent":
            issues.append("video manifest watermark is not absent")
    return issues


__all__ = ["validate_video_work_package"]
