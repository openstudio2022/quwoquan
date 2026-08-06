"""Asset admission checks for content execution readiness."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.control_types import ContentType
from core.io import read_json
from governance.coverage.distribution import (
    DistributionDecision,
    RightsStatus,
    project_asset_admission,
)


def _object_document(path: Path, issues: list[str]) -> dict[str, Any]:
    if not path.is_file():
        issues.append(f"{path}: required immutable object evidence is missing")
        return {}
    try:
        payload = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        issues.append(f"{path}: invalid immutable object evidence ({exc})")
        return {}
    if not isinstance(payload, dict):
        issues.append(f"{path}: immutable object evidence must be an object")
        return {}
    return payload


def _asset_admission_issues(
    object_root: Path,
    *,
    content_type: ContentType,
    mode: str,
) -> tuple[list[str], str]:
    label = object_root.as_posix()
    issues: list[str] = []
    package = _object_document(object_root.parent / "object_transaction_package.json", issues)
    target = package.get("target") if isinstance(package.get("target"), Mapping) else {}
    if (
        package.get("schema") != "quwoquan_data.object_transaction_package"
        or not object_root.parent.name.startswith(f"{package.get('executionId')}--")
        or target.get("packageObjectRef") != "object"
        or not str(package.get("objectClosureDigest") or "").startswith("sha256:")
    ):
        issues.append(f"{label}: immutable transaction package binding is invalid")
    manifest = _object_document(object_root / "manifest.json", issues)
    rights = _object_document(object_root / "rights.json", issues)
    manifest_rows = manifest.get("assets")
    rights_rows = rights.get("assets")
    if not isinstance(manifest_rows, list) or not isinstance(rights_rows, list):
        issues.append(f"{label}: manifest/rights assets must both be arrays")
        return issues, "invalid"
    manifest_assets = [row for row in manifest_rows if isinstance(row, Mapping)]
    raw_rights = [row for row in rights_rows if isinstance(row, Mapping)]
    if len(manifest_assets) != len(manifest_rows) or len(raw_rights) != len(rights_rows):
        issues.append(f"{label}: manifest/rights assets must contain only objects")
    manifest_ids = [str(row.get("assetId") or "").strip() for row in manifest_assets]
    rights_ids = [str(row.get("assetId") or "").strip() for row in raw_rights]
    if any(not value for value in (*manifest_ids, *rights_ids)):
        issues.append(f"{label}: manifest/rights assetId is missing")
    if len(manifest_ids) != len(set(manifest_ids)) or len(rights_ids) != len(set(rights_ids)):
        issues.append(f"{label}: manifest/rights asset IDs must be unique")
    if set(manifest_ids) != set(rights_ids):
        issues.append(f"{label}: manifest/rights asset closure drift")

    raw_by_id = {str(row.get("assetId") or "").strip(): row for row in raw_rights}
    physical_paths: dict[str, Path] = {}
    for asset_id, raw in raw_by_id.items():
        try:
            projected = project_asset_admission(raw, object_ref=label)
        except (TypeError, ValueError) as exc:
            issues.append(str(exc))
            continue
        for field in ("sourceUrl", "platform", "creator", "capturedAt", "contentSha256", "license", "termsUrl"):
            if not str(projected.get(field) or "").strip():
                issues.append(f"{label}: asset {asset_id} lacks provenance field {field}")
        if "authorizationProof" not in raw or not any(key in raw for key in ("rightsIssues", "rightsAuditIssues")):
            issues.append(f"{label}: asset {asset_id} lacks authorizationProof/rightsIssues fields")
        for field in ("acquisitionStatus", "rightsStatus", "authorizationRequired", "distributionDecision"):
            if field in raw and raw.get(field) != projected.get(field):
                issues.append(f"{label}: asset {asset_id} declared {field} drifts from evidence")
        if projected["generated"]:
            issues.append(f"{label}: generated image/video asset is blocked: {asset_id}")
        decision = str(projected["distributionDecision"])
        if mode == "research" and decision not in {
            DistributionDecision.RESEARCH_ALLOWED.value,
            DistributionDecision.COMMERCIAL_ALLOWED.value,
        }:
            issues.append(f"{label}: research asset is blocked: {asset_id}")
        if mode == "commercial" and (
            decision != DistributionDecision.COMMERCIAL_ALLOWED.value
            or projected["rightsStatus"] != RightsStatus.VERIFIED.value
            or bool(projected["authorizationRequired"])
        ):
            issues.append(f"{label}: commercial asset requires verified commercial_allowed: {asset_id}")
        physical = raw.get("asset") if isinstance(raw.get("asset"), Mapping) else {}
        physical_ref = str(physical.get("ref") or "").strip()
        relative = Path(physical_ref)
        if not physical_ref or relative.is_absolute() or ".." in relative.parts:
            issues.append(f"{label}: asset {asset_id} lacks a safe acquired blob ref")
            continue
        physical_path = object_root.parent / relative
        if not physical_path.is_file() or physical_path.stat().st_size != int(physical.get("bytes") or 0):
            issues.append(f"{label}: acquired blob is missing or size-drifted: {asset_id}")
            continue
        physical_paths[asset_id] = physical_path

    for row in manifest_assets:
        asset_id = str(row.get("assetId") or "").strip()
        raw = raw_by_id.get(asset_id, {})
        physical = raw.get("asset") if isinstance(raw.get("asset"), Mapping) else {}
        if not str(row.get("sha256") or "").startswith("sha256:") or row.get("sha256") != physical.get("sha256"):
            issues.append(f"{label}: manifest/blob digest closure drift: {asset_id}")

    if content_type is ContentType.ARTICLE:
        text_only = str(manifest.get("publishMediaMode") or "").strip() == "text_only"
        if text_only:
            if manifest_assets or raw_rights:
                issues.append(f"{label}: text_only article must not bind media assets")
            return issues, "text_only"
        images = [row for row in manifest_assets if str(row.get("kind") or "image") == "image"]
        roles = {str(row.get("role") or "").strip() for row in images}
        source_units = {
            str(row.get("sourceUnitRef") or row.get("sourceRef") or "").strip()
            for row in images
        }
        bindings = [row for row in (manifest.get("imageBindings") or []) if isinstance(row, Mapping)]
        if not (
            len(images) >= 2
            and "cover" in roles
            and (roles.intersection({"detail", "embedded"}) or len(bindings) >= 2)
            and len(source_units) == 1
            and "" not in source_units
        ):
            issues.append(f"{label}: article requires same-source cover and body images")
            return issues, "invalid"
        return issues, "illustrated"
    if content_type in {ContentType.HOMEPAGE, ContentType.IMAGE}:
        if not any(str(row.get("kind") or "image") == "image" for row in manifest_assets):
            issues.append(f"{label}: {content_type.value} requires an acquired image")
        return issues, "media"
    if content_type is ContentType.VIDEO:
        by_id = {str(row.get("assetId") or "").strip(): row for row in manifest_assets}
        playable = False
        for row in manifest_assets:
            if str(row.get("kind") or "") != "video":
                continue
            poster = by_id.get(str(row.get("posterAssetId") or "").strip(), {})
            path = physical_paths.get(str(row.get("assetId") or "").strip())
            if not (
                str(row.get("mimeType") or "").lower() in {"video/mp4", "video/webm"}
                and int(row.get("durationMs") or 0) > 0
                and int(row.get("width") or 0) > 0
                and int(row.get("height") or 0) > 0
                and str(row.get("codec") or "").strip()
                and str(poster.get("kind") or "") == "image"
                and str(poster.get("role") or "") == "cover"
                and path is not None
            ):
                continue
            with path.open("rb") as stream:
                header = stream.read(64)
            playable = b"ftyp" in header or header.startswith(b"\x1a\x45\xdf\xa3")
            if playable:
                break
        if not playable:
            issues.append(f"{label}: video requires an acquired playable MP4/WebM with cover")
        return issues, "media"
    return issues, "invalid"


