"""Object-local professional image acquisition and typed exclusion rows."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from core.image_decode import probe_image_bytes
from core.image_rules import pixel_size_issue
from governance.coverage.distribution import (
    AcquisitionStatus,
    DistributionDecision,
    RightsStatus,
    image_distribution_decision,
)

from content.source.professional_image_admission import pre_acquisition_block
from content.source.professional_image_source_attribution import (
    bound_image_source_attribution,
    build_image_plan_spec,
)
from content.source.professional_safety_evidence import (
    load_bound_safety_evidence as default_safety_loader,
    validate_image_safety_payload as default_safety_validator,
)
from content.source.research.image_provider_compliance import classify_image_provider
from content.source.research.text_match import _normalized_title


PayloadLoader = Callable[..., dict[str, Any] | None]
CasWriter = Callable[..., Path]


def _require_timestamp(value: object, *, label: str) -> None:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")


def validate_professional_image_item(
    item: Mapping[str, Any],
) -> tuple[RightsStatus, dict[str, Any]]:
    asset_id = str(item.get("assetId") or "")
    for field in ("licenseSnapshot", "usageScope", "modelReleaseStatus"):
        if not str(item.get(field) or "").strip():
            raise ValueError(f"{asset_id}.{field} must be frozen and non-empty")
    rights_status = RightsStatus(str(item.get("rightsStatus") or ""))
    terms_url = str(item.get("termsUrl") or "").strip()
    authorization_proof = str(item.get("authorizationProof") or "").strip()
    if terms_url and not terms_url.startswith("https://"):
        raise ValueError(f"{asset_id}: termsUrl must be empty or use HTTPS")
    if authorization_proof and not authorization_proof.startswith("https://"):
        raise ValueError(f"{asset_id}: authorizationProof must be empty or use HTTPS")
    if rights_status is RightsStatus.VERIFIED and (
        not terms_url.startswith("https://")
        or not authorization_proof.startswith("https://")
    ):
        raise ValueError(
            f"{asset_id}: verified rights require HTTPS termsUrl and authorizationProof"
        )
    rights_issues = [
        str(value).strip()
        for value in (item.get("rightsIssues") or [])
        if str(value).strip()
    ]
    if rights_status is not RightsStatus.VERIFIED and not rights_issues:
        raise ValueError(f"{asset_id}: non-verified asset must record rightsIssues")
    alias_keys = [_normalized_title(value) for value in item["entityAliases"]]
    if not all(alias_keys) or len(alias_keys) != len(set(alias_keys)):
        raise ValueError(f"{asset_id}: entityAliases must be normalized-unique")
    _require_timestamp(item["capturedAt"], label=f"{asset_id}.capturedAt")
    _require_timestamp(
        item["safetyReview"]["reviewedAt"],
        label=f"{asset_id}.safetyReview.reviewedAt",
    )
    source_id = str(item.get("sourceId") or "").strip()
    provider = classify_image_provider(source_id=source_id)
    if not provider["registered"]:
        raise ValueError(f"{asset_id}: image provider is not registered: {source_id}")
    path = str(item.get("acquisitionPath") or "")
    asset_url = str(item.get("assetUrl") or "").strip()
    manual_file = str(item.get("manualFile") or "").strip()
    api_evidence = str(item.get("apiEvidence") or "").strip()
    if path == "manual_file":
        if not manual_file or asset_url:
            raise ValueError(
                f"{asset_id}: manual_file requires manualFile and forbids assetUrl"
            )
    elif not asset_url.startswith("https://") or manual_file:
        raise ValueError(
            f"{asset_id}: {path} requires HTTPS assetUrl and forbids manualFile"
        )
    if path == "supported_api" and not api_evidence:
        raise ValueError(f"{asset_id}: supported_api requires apiEvidence")
    if path != "supported_api" and api_evidence:
        raise ValueError(f"{asset_id}: apiEvidence is only valid for supported_api")
    if not str(item.get("sourceUrl") or "").startswith("https://"):
        raise ValueError(f"{asset_id}: sourceUrl must use HTTPS")
    return rights_status, {
        **provider,
        "pathAllowed": path in set(provider["acquisitionPaths"]),
    }


def _row_base(
    item: Mapping[str, Any],
    *,
    rights_status: RightsStatus,
    provider: Mapping[str, Any],
) -> dict[str, Any]:
    authorization_proof = str(item.get("authorizationProof") or "").strip()
    source_attribution = item.get("sourceAttribution")
    return {
        "assetId": str(item["assetId"]),
        "entityId": str(item["entityId"]),
        "observedEntityId": str(item["observedEntityId"]),
        "entityAliases": list(item["entityAliases"]),
        "displayName": str(item["displayName"]),
        "provider": str(provider.get("sourceId") or item.get("sourceId") or "unknown"),
        "platform": str(provider.get("platform") or "unregistered"),
        "acquisitionPath": str(item["acquisitionPath"]),
        "assetUrl": str(item.get("assetUrl") or ""),
        "manualFile": str(item.get("manualFile") or ""),
        "apiEvidence": str(item.get("apiEvidence") or ""),
        "accessEvidence": dict(item["accessEvidence"]),
        "rightsStatus": rights_status.value,
        "authorizationRequired": (
            rights_status is not RightsStatus.VERIFIED or not authorization_proof
        ),
        "sourceUrl": str(item["sourceUrl"]),
        "creator": str(item["creator"]),
        "capturedAt": str(item["capturedAt"]),
        "license": str(item["license"]),
        "licenseSnapshot": str(item["licenseSnapshot"]),
        "usageScope": str(item["usageScope"]),
        "modelReleaseStatus": str(item["modelReleaseStatus"]),
        "termsUrl": str(item["termsUrl"]),
        "authorizationProof": authorization_proof,
        "rightsIssues": list(item["rightsIssues"]),
        "caption": str(item["caption"]),
        "relevance": str(item["relevance"]),
        "safetyReview": dict(item["safetyReview"]),
        "sourceAttribution": (
            dict(source_attribution)
            if isinstance(source_attribution, Mapping)
            else None
        ),
        "withdrawalRequired": rights_status is not RightsStatus.VERIFIED,
    }


def _excluded_row(
    item: Mapping[str, Any],
    *,
    code: str,
    detail: str,
    acquisition_status: AcquisitionStatus = AcquisitionStatus.BLOCKED,
    rights_status: RightsStatus | None = None,
    provider: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rights = rights_status or RightsStatus(str(item["rightsStatus"]))
    source = provider or classify_image_provider(source_id=str(item["sourceId"]))
    return {
        **_row_base(item, rights_status=rights, provider=source),
        "acquisitionStatus": acquisition_status.value,
        "distributionDecision": DistributionDecision.BLOCKED.value,
        "contentSha256": "",
        "assetRef": "",
        "bytes": 0,
        "mimeType": "",
        "width": 0,
        "height": 0,
        "failureCode": code,
        "failure": f"{code}:{detail}",
        "planImageSpec": None,
    }


def acquire_professional_image_item(
    item: Mapping[str, Any],
    *,
    manual_root: Path | None,
    output_root: Path,
    seen_content: dict[str, str],
    manual_loader: PayloadLoader,
    network_loader: PayloadLoader,
    cas_writer: CasWriter,
    content_digest: Callable[[bytes], str],
    portable_ref: Callable[[Path, Path], str],
    safety_loader: Callable[..., Mapping[str, Any]] = default_safety_loader,
    safety_validator: Callable[..., None] = default_safety_validator,
) -> dict[str, Any]:
    """Return one accepted row or one typed exclusion; CAS errors remain fatal."""
    try:
        rights_status, provider = validate_professional_image_item(item)
    except (KeyError, TypeError, ValueError) as exc:
        return _excluded_row(
            item,
            code="DATA.SOURCE.ASSET_ADMISSION_FAILED",
            detail=str(exc),
        )
    try:
        safety_evidence = safety_loader(
            item,
            evidence_root=output_root,
            kind="image",
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        return _excluded_row(
            item,
            code="DATA.SOURCE.SAFETY_EVIDENCE_FAILED",
            detail=str(exc),
            rights_status=rights_status,
            provider=provider,
        )
    if not bool(provider["pathAllowed"]):
        return _excluded_row(
            item,
            code="DATA.SOURCE.ACQUISITION_PATH_BLOCKED",
            detail="provider does not allow the requested acquisition path",
            rights_status=rights_status,
            provider=provider,
        )
    failure_code, failure_detail = pre_acquisition_block(item)
    if failure_code:
        return _excluded_row(
            item,
            code=failure_code,
            detail=failure_detail,
            rights_status=rights_status,
            provider=provider,
        )
    try:
        if item["acquisitionPath"] == "manual_file":
            if manual_root is None:
                raise ValueError("manual_root is required by manual_file acquisition")
            payload = manual_loader(str(item["manualFile"]), manual_root=manual_root)
        else:
            payload = network_loader(
                str(item["assetUrl"]),
                supported_api=item["acquisitionPath"] == "supported_api",
            )
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return _excluded_row(
            item,
            code="DATA.SOURCE.ACQUISITION_FAILED",
            detail=str(exc),
            acquisition_status=AcquisitionStatus.FAILED,
            rights_status=rights_status,
            provider=provider,
        )
    if payload is None:
        return _excluded_row(
            item,
            code="DATA.SOURCE.ACQUISITION_FAILED",
            detail="provider returned no admissible image bytes",
            acquisition_status=AcquisitionStatus.FAILED,
            rights_status=rights_status,
            provider=provider,
        )
    body = bytes(payload["bytes"])
    probe = probe_image_bytes(body)
    if not probe.succeeded:
        return _excluded_row(
            item,
            code="DATA.SOURCE.IMAGE_DECODE_FAILED",
            detail=probe.failure.value,
            acquisition_status=AcquisitionStatus.FAILED,
            rights_status=rights_status,
            provider=provider,
        )
    payload_ext = str(payload.get("ext") or "").strip().casefold()
    transport_mime = (
        str(payload.get("contentType") or "").split(";", 1)[0].strip().casefold()
    )
    if not probe.mime_type.startswith("image/"):
        return _excluded_row(
            item,
            code="DATA.SOURCE.IMAGE_MIME_INVALID",
            detail="decoded image MIME type is unavailable",
            acquisition_status=AcquisitionStatus.FAILED,
            rights_status=rights_status,
            provider=provider,
        )
    expected_ext_by_mime = {
        "image/gif": ".gif",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    expected_ext = expected_ext_by_mime.get(probe.mime_type, "")
    if not expected_ext or payload_ext != expected_ext:
        return _excluded_row(
            item,
            code="DATA.SOURCE.IMAGE_EXTENSION_DRIFT",
            detail=(
                f"payload extension {payload_ext or '<empty>'} does not match "
                f"decoded MIME {probe.mime_type}"
            ),
            acquisition_status=AcquisitionStatus.FAILED,
            rights_status=rights_status,
            provider=provider,
        )
    if transport_mime and transport_mime != probe.mime_type:
        return _excluded_row(
            item,
            code="DATA.SOURCE.IMAGE_MIME_DRIFT",
            detail=(
                f"transport MIME {transport_mime} does not match "
                f"decoded MIME {probe.mime_type}"
            ),
            acquisition_status=AcquisitionStatus.FAILED,
            rights_status=rights_status,
            provider=provider,
        )
    try:
        safety_validator(
            safety_evidence,
            item,
            body=body,
            width=probe.width,
            height=probe.height,
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        return _excluded_row(
            item,
            code="DATA.SOURCE.SAFETY_EVIDENCE_FAILED",
            detail=str(exc),
            acquisition_status=AcquisitionStatus.FAILED,
            rights_status=rights_status,
            provider=provider,
        )
    content_sha256 = content_digest(body)
    cas_path = cas_writer(body, str(payload["ext"]), output_root=output_root)
    asset_ref = portable_ref(cas_path, output_root)
    duplicate_of = seen_content.get(content_sha256)
    quality_issue = pixel_size_issue(
        probe.width,
        probe.height,
        asset_id=str(item["assetId"]),
    )
    authorization_proof = str(item.get("authorizationProof") or "").strip()
    decision = image_distribution_decision(
        acquisition_status=AcquisitionStatus.ACQUIRED,
        rights_status=rights_status,
        authorization_proof=authorization_proof,
        usage_scope=str(item["usageScope"]),
        model_release_status=str(item["modelReleaseStatus"]),
    )
    failure_code = ""
    failure = ""
    if duplicate_of:
        decision = DistributionDecision.BLOCKED
        failure_code = "DATA.SOURCE.DUPLICATE_ASSET"
        failure = f"{failure_code}:{duplicate_of}"
    elif quality_issue:
        decision = DistributionDecision.BLOCKED
        failure_code = "DATA.SOURCE.IMAGE_QUALITY_BLOCKED"
        failure = f"{failure_code}:{quality_issue}"
    elif decision == DistributionDecision.BLOCKED:
        failure_code = "DATA.SOURCE.RIGHTS_DISTRIBUTION_BLOCKED"
        failure = (
            f"{failure_code}:asset rights, usage scope, or release evidence "
            "does not admit distribution"
        )
    else:
        seen_content[content_sha256] = str(item["assetId"])
    row = {
        **_row_base(item, rights_status=rights_status, provider=provider),
        "acquisitionStatus": AcquisitionStatus.ACQUIRED.value,
        "distributionDecision": decision.value,
        "contentSha256": content_sha256,
        "assetRef": asset_ref,
        "bytes": len(body),
        "mimeType": probe.mime_type,
        "width": probe.width,
        "height": probe.height,
        "failureCode": failure_code,
        "failure": failure,
        "planImageSpec": None,
    }
    if decision not in {
        DistributionDecision.RESEARCH_ALLOWED,
        DistributionDecision.COMMERCIAL_ALLOWED,
    }:
        return row
    try:
        source_attribution = bound_image_source_attribution(
            item,
            platform=str(provider["platform"]),
            distribution_decision=decision.value,
        )
        row["sourceAttribution"] = source_attribution
        row["planImageSpec"] = build_image_plan_spec(
            item,
            platform=str(provider["platform"]),
            source_id=str(provider["sourceId"]),
            cas_uri=cas_path.resolve().as_uri(),
            content_sha256=content_sha256,
            acquisition_status=AcquisitionStatus.ACQUIRED.value,
            rights_status=rights_status.value,
            authorization_required=row["authorizationRequired"],
            distribution_decision=decision.value,
            width=probe.width,
            height=probe.height,
        )
    except (KeyError, TypeError, ValueError) as exc:
        row.update(
            distributionDecision=DistributionDecision.BLOCKED.value,
            failureCode="DATA.SOURCE.OUTPUT_BINDING_FAILED",
            failure=f"DATA.SOURCE.OUTPUT_BINDING_FAILED:{exc}",
            planImageSpec=None,
        )
    return row


__all__ = [
    "acquire_professional_image_item",
    "validate_professional_image_item",
]
