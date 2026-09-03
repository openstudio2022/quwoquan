"""Per-asset professional video acquisition and admission."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from governance.coverage.distribution import (
    AcquisitionStatus,
    DistributionDecision,
    RightsStatus,
    distribution_decision,
)

from content.source.professional_video_popularity import initial_popularity_signals
from content.source.professional_video_store import (
    ProfessionalVideoCasCollision,
    put_video_cas,
)
from content.source.professional_video_transport import (
    copy_manual_video,
    redact_sensitive_video_url,
)
from content.source.research.text_match import _normalized_title
from content.source.video_media_probe import extract_video_poster
from core.image_decode import probe_image_path


def _video_mime_type(path: Path) -> str:
    mime_by_suffix = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".ogv": "video/ogg",
        ".mov": "video/quicktime",
    }
    mime = mime_by_suffix.get(path.suffix.lower(), "")
    if not mime:
        raise ValueError(f"unsupported professional video CAS suffix: {path.suffix}")
    return mime


def pre_acquisition_block(item: Mapping[str, Any]) -> tuple[str, str]:
    access = item["accessEvidence"]
    if any(
        bool(access[field])
        for field in (
            "loginRequired", "captchaRequired", "paywallRequired",
            "drmProtected", "accessControlBypass",
        )
    ):
        return "DATA.SOURCE.ACCESS_CONTROL_BLOCKED", "access barrier or bypass declared"
    if item["acquisitionPath"] != "manual_file" and not access["anonymousAssetAccess"]:
        return "DATA.SOURCE.ANONYMOUS_ACCESS_REQUIRED", "network video is not anonymously accessible"
    review = item["safetyReview"]
    if review["status"] != "passed":
        return "DATA.SOURCE.SAFETY_REVIEW_BLOCKED", "safety review is not passed"
    if review["entityMatch"] != "matched":
        return "DATA.SOURCE.ENTITY_MISMATCH", "safety review entity does not match"
    if any(
        review[field] != "none"
        for field in ("privacyRisk", "minorRisk", "maliciousMediaRisk")
    ):
        return "DATA.SOURCE.SAFETY_RISK_BLOCKED", "privacy, minor or malicious-media risk"
    if review["watermarkStatus"] != "absent":
        return "DATA.SOURCE.WATERMARK_BLOCKED", "watermark is present or unknown"
    entity_key = _normalized_title(str(item["entityId"]))
    observed_key = _normalized_title(str(item["observedEntityId"]))
    if not entity_key or observed_key != entity_key:
        return "DATA.SOURCE.ENTITY_MISMATCH", "observedEntityId does not match entityId"
    evidence_key = _normalized_title(f"{item['title']} {item['relevance']}")
    aliases = [
        _normalized_title(value)
        for value in [item["entityId"], *item["entityAliases"]]
        if _normalized_title(value)
    ]
    if not any(alias in evidence_key for alias in aliases):
        return "DATA.SOURCE.ENTITY_MISMATCH", "title and relevance do not identify entity"
    return "", ""


def empty_video_row(item: Mapping[str, Any], *, rights: RightsStatus) -> dict[str, Any]:
    row = {
        **{key: item[key] for key in (
            "assetId", "entityId", "observedEntityId", "provider", "platform",
            "displayName", "sourceKind", "acquisitionPath", "sourceUrl", "assetUrl",
            "manualFile", "apiEvidence", "accessEvidence", "title", "relevance",
            "creator", "capturedAt", "license", "termsUrl", "authorizationProof",
            "rightsIssues", "modelReleaseStatus", "propertyReleaseStatus", "safetyReview",
        )},
        "acquisitionStatus": AcquisitionStatus.BLOCKED.value,
        "rightsStatus": rights.value,
        "authorizationRequired": rights is not RightsStatus.VERIFIED or not str(item["authorizationProof"]).strip(),
        "distributionDecision": DistributionDecision.BLOCKED.value,
        "contentSha256": "", "assetRef": "", "bytes": 0, "mediaProbe": None,
        "mimeType": "",
        "posterAssetRef": "", "posterContentSha256": "", "posterBytes": 0,
        "posterMimeType": "", "posterRights": None,
        "duplicateOf": "", "failureCode": "", "failure": "",
        "popularitySignals": initial_popularity_signals(dict(item["popularitySignals"])),
        "planVideoSpec": None,
    }
    for field in ("sourceUrl", "assetUrl", "apiEvidence", "termsUrl", "authorizationProof"):
        row[field] = redact_sensitive_video_url(str(row[field]))
    return row


def acquire_video_item(
    item: Mapping[str, Any],
    *,
    rights: RightsStatus,
    safety_evidence: Mapping[str, Any],
    manual_root: Path | None,
    output_root: Path,
    temporary_root: Path,
    safety_validator: Callable[..., None],
    network_fetcher: Callable[..., str],
    media_probe: Callable[[Path], dict[str, Any]],
    frozen_asset: Path | None = None,
    poster_extractor: Callable[[Path, Path], None] = extract_video_poster,
) -> dict[str, Any]:
    row = empty_video_row(item, rights=rights)
    failure_code, failure = pre_acquisition_block(item)
    if failure_code:
        row.update(failureCode=failure_code, failure=failure)
        return row
    temporary = temporary_root / f"{item['assetId']}.download"
    try:
        if frozen_asset is not None:
            expected = item.get("frozenAsset")
            if not isinstance(expected, Mapping):
                raise ValueError("frozen CAS object requires frozenAsset binding")
            expected_ref = str(expected.get("assetRef") or "")
            expected_digest = str(expected.get("contentSha256") or "")
            expected_bytes = expected.get("bytes")
            try:
                relative = frozen_asset.resolve().relative_to(output_root.resolve())
            except (OSError, ValueError) as exc:
                raise ValueError("frozen CAS object is missing or unsafe") from exc
            if (
                frozen_asset.is_symlink()
                or not frozen_asset.is_file()
                or relative.as_posix() != expected_ref
                or expected_bytes != frozen_asset.stat().st_size
            ):
                raise ValueError("frozen CAS object is missing or unsafe")
            from content.source.professional_video_receipt import file_digest

            if file_digest(frozen_asset) != expected_digest:
                raise ValueError("frozen CAS object digest drift")
            cas_path = frozen_asset
            content_sha256 = expected_digest
        elif item["acquisitionPath"] == "manual_file":
            if manual_root is None:
                raise ValueError("manual_root is required by manual_file acquisition")
            suffix = copy_manual_video(
                str(item["manualFile"]), temporary, manual_root=manual_root
            )
        else:
            suffix = network_fetcher(
                str(item["assetUrl"]), temporary,
                supported_api=item["acquisitionPath"] == "supported_api",
            )
        if frozen_asset is None:
            cas_path, content_sha256 = put_video_cas(
                temporary, suffix, output_root=output_root
            )
    except ProfessionalVideoCasCollision:
        raise
    except (FileNotFoundError, OSError, TimeoutError, ValueError) as exc:
        row.update(
            acquisitionStatus=AcquisitionStatus.FAILED.value,
            failureCode="DATA.SOURCE.ACQUISITION_FAILED",
            failure=f"{type(exc).__name__}: {exc}",
        )
        return row
    finally:
        temporary.unlink(missing_ok=True)
    decision = distribution_decision(
        acquisition_status=AcquisitionStatus.ACQUIRED,
        rights_status=rights,
        authorization_proof=str(item["authorizationProof"]),
    )
    poster_temporary = temporary_root / f"{item['assetId']}.poster.png"
    try:
        poster_extractor(cas_path, poster_temporary)
        poster_cas_path, poster_content_sha256 = put_video_cas(
            poster_temporary,
            ".png",
            output_root=output_root,
        )
        poster_probe = probe_image_path(poster_cas_path)
        if not poster_probe.succeeded or poster_probe.mime_type != "image/png":
            raise ValueError("extracted video poster is not a decodable PNG")
    except ProfessionalVideoCasCollision:
        raise
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError) as exc:
        row.update(
            acquisitionStatus=AcquisitionStatus.FAILED.value,
            failureCode="DATA.SOURCE.POSTER_EXTRACTION_FAILED",
            failure=f"{type(exc).__name__}: {exc}",
        )
        return row
    finally:
        poster_temporary.unlink(missing_ok=True)
    row.update(
        acquisitionStatus=AcquisitionStatus.ACQUIRED.value,
        contentSha256=content_sha256,
        assetRef=cas_path.relative_to(output_root).as_posix(),
        bytes=cas_path.stat().st_size,
        mimeType=_video_mime_type(cas_path),
        posterAssetRef=poster_cas_path.relative_to(output_root).as_posix(),
        posterContentSha256=poster_content_sha256,
        posterBytes=poster_cas_path.stat().st_size,
        posterMimeType=poster_probe.mime_type,
        posterRights={
            "derivation": "frame_from_licensed_video",
            "sourceAssetId": str(item["assetId"]),
            "sourceUrl": str(row["sourceUrl"]),
            "license": str(row["license"]),
            "termsUrl": str(row["termsUrl"]),
            "authorizationProof": str(row["authorizationProof"]),
            "rightsStatus": rights.value,
            "authorizationRequired": row["authorizationRequired"],
            "distributionDecision": decision.value,
            "rightsIssues": list(row["rightsIssues"]),
        },
    )
    try:
        probe = media_probe(cas_path)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        row.update(
            distributionDecision=DistributionDecision.BLOCKED.value,
            failureCode="DATA.SOURCE.MEDIA_PROBE_FAILED",
            failure=f"{type(exc).__name__}: {exc}",
        )
        return row
    try:
        safety_validator(
            safety_evidence, item, content_sha256=content_sha256,
            size_bytes=cas_path.stat().st_size, media_probe=probe,
        )
        row["mediaProbe"] = probe
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        row.update(
            distributionDecision=DistributionDecision.BLOCKED.value,
            failureCode="DATA.SOURCE.SOURCE_BYTES_DRIFT",
            failure=f"{type(exc).__name__}: {exc}",
        )
        return row
    if not probe["playable"] or not probe["motionVideo"]:
        row.update(
            distributionDecision=DistributionDecision.BLOCKED.value,
            failureCode="DATA.SOURCE.NOT_PLAYABLE_MOTION_VIDEO",
            failure="video is unplayable or a static-image sequence",
        )
        return row
    if decision is DistributionDecision.BLOCKED:
        row.update(
            failureCode="DATA.SOURCE.RIGHTS_RESTRICTED",
            failure="restricted rights block research and commercial distribution",
        )
        return row
    row["distributionDecision"] = decision.value
    return row


__all__ = ["acquire_video_item", "empty_video_row", "pre_acquisition_block"]
