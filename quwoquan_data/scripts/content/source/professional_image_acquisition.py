"""Governed Pinterest/Tuchong image acquisition into a local content CAS.

The connector accepts only three explicit paths: anonymous public HTTPS,
platform-supported API output expressed as an HTTPS asset URL, or a file under
an operator-provided manual root.  It never accepts cookies, credentials,
browser state, custom headers, DRM or access-control bypass instructions.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from core.image_decode import probe_image_bytes
from core.image_rules import pixel_size_issue
from core.io import read_json
from core.paths import SOURCE_ACQUISITION_ROOT
from core.schema import assert_valid
from governance.coverage.distribution import (
    AcquisitionStatus,
    DistributionDecision,
    RightsStatus,
    image_distribution_decision,
)

from content.source.image_payload import sniff_image_ext
from content.source.professional_image_admission import pre_acquisition_block
from content.source.professional_image_discovery_binding import (
    load_discovery_candidates,
    validate_discovery_binding,
)
from content.source.professional_image_receipt_validation import (
    validate_image_receipt_inventory,
)
from content.source.professional_image_transport import fetch_public_image
from content.source.research.image_provider_compliance import classify_image_provider
from content.source.research.text_match import _normalized_title
from content.execution.controller.execute.pre_acquisition_handoff import (
    guard_acquisition_source_identity,
)

ACQUISITION_ROOT = SOURCE_ACQUISITION_ROOT
_MAX_IMAGE_BYTES = 64 * 1024 * 1024
_MIN_IMAGE_BYTES = 3_000


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _content_digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _manual_payload(relative_ref: str, *, manual_root: Path) -> dict[str, Any] | None:
    if not relative_ref or Path(relative_ref).is_absolute():
        raise ValueError("manualFile must be a non-empty relative path")
    root = manual_root.resolve()
    path = (root / relative_ref).resolve()
    if path != root and root not in path.parents:
        raise ValueError("manualFile escapes the declared manual root")
    if not path.is_file():
        return None
    body = path.read_bytes()
    if len(body) < _MIN_IMAGE_BYTES or len(body) > _MAX_IMAGE_BYTES:
        return None
    ext = sniff_image_ext(body, "")
    if ext is None:
        return None
    return {
        "bytes": body,
        "ext": ext,
        "contentType": "",
        "requestedUrl": "",
        "normalizedFromUrl": "",
    }


def _network_payload(
    url: str,
    *,
    supported_api: bool,
) -> dict[str, Any] | None:
    return fetch_public_image(
        url,
        supported_api=supported_api,
        min_bytes=_MIN_IMAGE_BYTES,
        max_bytes=_MAX_IMAGE_BYTES,
    )


def _put_cas(payload: bytes, ext: str, *, output_root: Path) -> Path:
    digest = hashlib.sha256(payload).hexdigest()
    destination = output_root / "cas" / "sha256" / digest[:2] / f"{digest}{ext}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        if _content_digest(destination.read_bytes()) != f"sha256:{digest}":
            raise ValueError(f"image CAS collision: {destination}")
        return destination
    temporary = ""
    with tempfile.NamedTemporaryFile(
        "wb",
        dir=destination.parent,
        prefix=f".{digest}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = handle.name
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)
    return destination


def _portable_ref(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _write_create_once_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    body = json.dumps(receipt, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        if read_json(path) != receipt:
            raise ValueError(
                f"professional image acquisition receipt collision: {path}"
            )
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())


def _require_timestamp(value: object, *, label: str) -> None:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")


def _validate_item(item: Mapping[str, Any]) -> tuple[RightsStatus, dict[str, Any]]:
    asset_id = str(item.get("assetId") or "")
    for field in ("licenseSnapshot", "usageScope", "modelReleaseStatus"):
        if not str(item.get(field) or "").strip():
            raise ValueError(f"{asset_id}.{field} must be frozen and non-empty")
    rights_status = RightsStatus(str(item.get("rightsStatus") or ""))
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
        raise ValueError(
            f"{item.get('assetId')}: image provider is not registered: {source_id}"
        )
    path = str(item.get("acquisitionPath") or "")
    asset_url = str(item.get("assetUrl") or "").strip()
    manual_file = str(item.get("manualFile") or "").strip()
    api_evidence = str(item.get("apiEvidence") or "").strip()
    if path == "manual_file":
        if not manual_file or asset_url:
            raise ValueError(
                f"{item.get('assetId')}: manual_file requires manualFile and forbids assetUrl"
            )
    else:
        if not asset_url.startswith("https://") or manual_file:
            raise ValueError(
                f"{item.get('assetId')}: {path} requires HTTPS assetUrl and forbids manualFile"
            )
    if path == "supported_api" and not api_evidence:
        raise ValueError(f"{item.get('assetId')}: supported_api requires apiEvidence")
    if path != "supported_api" and api_evidence:
        raise ValueError(
            f"{item.get('assetId')}: apiEvidence is only valid for supported_api"
        )
    if not str(item.get("sourceUrl") or "").startswith("https://"):
        raise ValueError(f"{item.get('assetId')}: sourceUrl must use HTTPS")
    if path not in set(provider["acquisitionPaths"]):
        return rights_status, {**provider, "pathAllowed": False}
    return rights_status, {**provider, "pathAllowed": True}


def _provider_counts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["displayName"]), str(row["provider"]))].append(row)
    result: list[dict[str, Any]] = []
    for (display_name, provider), assets in sorted(grouped.items()):
        rights = Counter(str(row["rightsStatus"]) for row in assets)
        downloaded = sum(row["acquisitionStatus"] == "acquired" for row in assets)
        accepted = sum(
            row["distributionDecision"] in {"research_allowed", "commercial_allowed"}
            for row in assets
        )
        result.append(
            {
                "displayName": display_name,
                "provider": provider,
                "plannedAssetCount": len(assets),
                "discoveredAssetCount": len(assets),
                "downloadedAssetCount": downloaded,
                "acceptedAssetCount": accepted,
                "rejectedAssetCount": len(assets) - accepted,
                "verifiedAssetCount": rights["verified"],
                "unverifiedAssetCount": rights["unverified"],
                "restrictedAssetCount": rights["restricted"],
                "unknownAssetCount": rights["unknown"],
            }
        )
    return result


def acquire_professional_images(
    manifest_path: Path,
    *,
    handoff_ref: Path,
    repo_root: Path | None = None,
    manual_root: Path | None = None,
    output_root: Path = ACQUISITION_ROOT,
) -> tuple[dict[str, Any], Path]:
    """Acquire every manifest item and write a create-once auditable receipt."""
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise TypeError("professional image acquisition manifest must be an object")
    assert_valid(
        manifest,
        "source",
        "professional_image_acquisition_manifest",
        label="professional image acquisition manifest",
    )
    guard_acquisition_source_identity(
        manifest,
        handoff_ref=handoff_ref,
        repo_root=repo_root,
    )
    asset_ids = [str(item["assetId"]) for item in manifest["items"]]
    if len(asset_ids) != len(set(asset_ids)):
        raise ValueError("professional image acquisition assetId values must be unique")
    discovery_candidates = load_discovery_candidates(
        manifest,
        output_root=output_root,
    )
    manifest_digest = _digest(manifest)
    rows: list[dict[str, Any]] = []
    seen_content: dict[str, str] = {}
    for raw in manifest["items"]:
        item = dict(raw)
        validate_discovery_binding(item, candidates=discovery_candidates)
        rights_status, provider = _validate_item(item)
        path_allowed = bool(provider["pathAllowed"])
        payload: dict[str, Any] | None = None
        failure_code = ""
        failure = ""
        if not path_allowed:
            acquisition_status = AcquisitionStatus.BLOCKED
            failure_code = "DATA.SOURCE.ACQUISITION_PATH_BLOCKED"
            failure = failure_code
        else:
            failure_code, failure_detail = pre_acquisition_block(item)
            if failure_code:
                acquisition_status = AcquisitionStatus.BLOCKED
                failure = f"{failure_code}:{failure_detail}"
            else:
                if item["acquisitionPath"] == "manual_file":
                    if manual_root is None:
                        raise ValueError(
                            "manual_root is required by manual_file acquisition"
                        )
                    payload = _manual_payload(
                        str(item["manualFile"]),
                        manual_root=manual_root,
                    )
                else:
                    payload = _network_payload(
                        str(item["assetUrl"]),
                        supported_api=item["acquisitionPath"] == "supported_api",
                    )
                acquisition_status = (
                    AcquisitionStatus.ACQUIRED
                    if payload is not None
                    else AcquisitionStatus.FAILED
                )
                if payload is None:
                    failure_code = "DATA.SOURCE.ACQUISITION_FAILED"
                    failure = failure_code
        authorization_proof = str(item.get("authorizationProof") or "").strip()
        decision = image_distribution_decision(
            acquisition_status=acquisition_status,
            rights_status=rights_status,
            authorization_proof=authorization_proof,
            usage_scope=str(item["usageScope"]),
            model_release_status=str(item["modelReleaseStatus"]),
        )
        content_sha256 = ""
        asset_ref = ""
        width = 0
        height = 0
        plan_spec: dict[str, Any] | None = None
        if payload is not None:
            body = bytes(payload["bytes"])
            probe = probe_image_bytes(body)
            if not probe.succeeded:
                acquisition_status = AcquisitionStatus.FAILED
                decision = DistributionDecision.BLOCKED
                failure_code = "DATA.SOURCE.IMAGE_DECODE_FAILED"
                failure = f"{failure_code}:{probe.failure.value}"
            else:
                content_sha256 = _content_digest(body)
                duplicate_of = seen_content.get(content_sha256)
                cas_path = _put_cas(body, str(payload["ext"]), output_root=output_root)
                asset_ref = _portable_ref(cas_path, output_root)
                width, height = probe.width, probe.height
                if duplicate_of:
                    decision = DistributionDecision.BLOCKED
                    failure_code = "DATA.SOURCE.DUPLICATE_ASSET"
                    failure = f"{failure_code}:{duplicate_of}"
                else:
                    seen_content[content_sha256] = str(item["assetId"])
                    quality_issue = pixel_size_issue(
                        width,
                        height,
                        asset_id=str(item["assetId"]),
                    )
                    if quality_issue:
                        decision = DistributionDecision.BLOCKED
                        failure_code = "DATA.SOURCE.IMAGE_QUALITY_BLOCKED"
                        failure = f"{failure_code}:{quality_issue}"
                if decision in {
                    DistributionDecision.RESEARCH_ALLOWED,
                    DistributionDecision.COMMERCIAL_ALLOWED,
                }:
                    plan_spec = {
                        "url": cas_path.resolve().as_uri(),
                        "sourceUrl": str(item["sourceUrl"]),
                        "collectionPageUrl": str(item["sourceUrl"]),
                        "originalAssetUrl": str(
                            item.get("assetUrl") or item["sourceUrl"]
                        ),
                        "platform": str(provider["platform"]),
                        "sourceId": str(provider["sourceId"]),
                        "discoveryCandidateId": str(item["discoveryCandidateId"]),
                        "discoveryUrl": str(item["discoveryUrl"]),
                        "creator": str(item["creator"]),
                        "credit": str(item["creator"]),
                        "capturedAt": str(item["capturedAt"]),
                        "contentSha256": content_sha256,
                        "acquisitionStatus": acquisition_status.value,
                        "rightsStatus": rights_status.value,
                        "authorizationRequired": (
                            rights_status is not RightsStatus.VERIFIED
                            or not authorization_proof
                        ),
                        "distributionDecision": decision.value,
                        "rightsAuditStatus": rights_status.value,
                        "rightsIssues": list(item["rightsIssues"]),
                        "license": str(item["license"]),
                        "licenseSnapshot": str(item["licenseSnapshot"]),
                        "usageScope": str(item["usageScope"]),
                        "modelReleaseStatus": str(item["modelReleaseStatus"]),
                        "termsUrl": str(item["termsUrl"]),
                        "authorizationProof": authorization_proof,
                        "caption": str(item["caption"]),
                        "relevance": str(item["relevance"]),
                        "width": width,
                        "height": height,
                    }
        rows.append(
            {
                "assetId": str(item["assetId"]),
                "entityId": str(item["entityId"]),
                "observedEntityId": str(item["observedEntityId"]),
                "entityAliases": list(item["entityAliases"]),
                "displayName": str(item["displayName"]),
                "discoveryCandidateId": str(item["discoveryCandidateId"]),
                "discoveryUrl": str(item["discoveryUrl"]),
                "provider": str(provider["sourceId"]),
                "platform": str(provider["platform"]),
                "acquisitionPath": str(item["acquisitionPath"]),
                "assetUrl": str(item.get("assetUrl") or ""),
                "manualFile": str(item.get("manualFile") or ""),
                "apiEvidence": str(item.get("apiEvidence") or ""),
                "accessEvidence": dict(item["accessEvidence"]),
                "acquisitionStatus": acquisition_status.value,
                "rightsStatus": rights_status.value,
                "authorizationRequired": (
                    rights_status is not RightsStatus.VERIFIED
                    or not authorization_proof
                ),
                "distributionDecision": decision.value,
                "sourceUrl": str(item["sourceUrl"]),
                "creator": str(item["creator"]),
                "capturedAt": str(item["capturedAt"]),
                "contentSha256": content_sha256,
                "assetRef": asset_ref,
                "bytes": len(payload["bytes"]) if payload is not None else 0,
                "width": width,
                "height": height,
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
                "withdrawalRequired": rights_status is not RightsStatus.VERIFIED,
                "failureCode": failure_code,
                "failure": failure,
                "planImageSpec": plan_spec,
            }
        )
    provider_counts = _provider_counts(rows)
    downloaded = sum(row["acquisitionStatus"] == "acquired" for row in rows)
    accepted = sum(
        row["distributionDecision"] in {"research_allowed", "commercial_allowed"}
        for row in rows
    )
    stable = {
        "schema": "quwoquan_data.professional_image_acquisition_receipt",
        "manifestId": str(manifest["manifestId"]),
        "manifestDigest": manifest_digest,
        "sourceRevision": str(manifest["sourceRevision"]),
        "sourceDigest": str(manifest["sourceDigest"]),
        "entityCatalogDigest": str(manifest["entityCatalogDigest"]),
        "discoveryPlanRef": str(manifest["discoveryPlanRef"]),
        "discoveryPlanDigest": str(manifest["discoveryPlanDigest"]),
        "plannedAssetCount": len(rows),
        "discoveredAssetCount": len(rows),
        "downloadedAssetCount": downloaded,
        "acceptedAssetCount": accepted,
        "rejectedAssetCount": len(rows) - accepted,
        "providerAssetCounts": provider_counts,
        "assets": rows,
    }
    receipt = {**stable, "receiptDigest": _digest(stable)}
    assert_valid(
        receipt,
        "source",
        "professional_image_acquisition_receipt",
        label="professional image acquisition receipt",
    )
    validate_image_receipt_inventory(
        receipt,
        resolved_root=output_root.resolve(),
        min_image_bytes=_MIN_IMAGE_BYTES,
        max_image_bytes=_MAX_IMAGE_BYTES,
        validate_item=_validate_item,
        pre_acquisition_block=pre_acquisition_block,
        provider_counts=_provider_counts,
    )
    receipt_path = (
        output_root / "receipts" / f"{manifest_digest.removeprefix('sha256:')}.json"
    )
    _write_create_once_receipt(receipt_path, receipt)
    return receipt, receipt_path


def load_professional_image_acquisition_receipt(
    receipt_ref: str,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Read a relative receipt and re-verify its digest plus every acquired CAS file."""
    relative = Path(str(receipt_ref or "").strip())
    if not str(relative) or relative.is_absolute():
        raise ValueError("professional image acquisition receiptRef must be relative")
    resolved_root = (root or ACQUISITION_ROOT).resolve()
    path = (resolved_root / relative).resolve()
    if path != resolved_root and resolved_root not in path.parents:
        raise ValueError(
            "professional image acquisition receiptRef escapes acquisition root"
        )
    receipt = read_json(path)
    if not isinstance(receipt, dict):
        raise TypeError("professional image acquisition receipt must be an object")
    assert_valid(
        receipt,
        "source",
        "professional_image_acquisition_receipt",
        label="professional image acquisition receipt",
    )
    stable = {key: value for key, value in receipt.items() if key != "receiptDigest"}
    if receipt.get("receiptDigest") != _digest(stable):
        raise ValueError("professional image acquisition receipt digest mismatch")
    expected_name = f"{str(receipt['manifestDigest']).removeprefix('sha256:')}.json"
    if path.name != expected_name or path.parent.name != "receipts":
        raise ValueError("professional image acquisition receipt path is not canonical")
    validate_image_receipt_inventory(
        receipt,
        resolved_root=resolved_root,
        min_image_bytes=_MIN_IMAGE_BYTES,
        max_image_bytes=_MAX_IMAGE_BYTES,
        validate_item=_validate_item,
        pre_acquisition_block=pre_acquisition_block,
        provider_counts=_provider_counts,
    )
    return receipt


def acquired_image_specs_for_entity(
    receipt_refs: list[str],
    *,
    entity_id: str,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Project accepted receipt assets into the ordinary image-plan contract."""
    specs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for receipt_ref in receipt_refs:
        receipt = load_professional_image_acquisition_receipt(receipt_ref, root=root)
        for row in receipt["assets"]:
            if (
                not isinstance(row, Mapping)
                or str(row.get("entityId") or "") != entity_id
            ):
                continue
            if row.get("distributionDecision") not in {
                "research_allowed",
                "commercial_allowed",
            }:
                continue
            if row.get("acquisitionStatus") != "acquired":
                raise ValueError(
                    "professional image acquisition accepted asset was not acquired: "
                    f"{row.get('assetId')}"
                )
            plan_spec = row.get("planImageSpec")
            if not isinstance(plan_spec, Mapping):
                raise TypeError(
                    f"professional image acquisition accepted asset lacks planImageSpec: {row.get('assetId')}"
                )
            content_sha256 = str(row.get("contentSha256") or "")
            if content_sha256 in seen:
                raise ValueError(
                    f"professional image acquisition cross-receipt duplicate: {content_sha256}"
                )
            seen.add(content_sha256)
            specs.append(
                {
                    **dict(plan_spec),
                    "sourceCollectionId": (
                        f"acquisition:{receipt['manifestId']}:{row['assetId']}"
                    ),
                    "acquisitionReceiptRef": receipt_ref,
                    "professionalAssetId": str(row["assetId"]),
                    "professionalContentSha256": content_sha256,
                    "researchLane": "image",
                }
            )
    return specs


__all__ = [
    "ACQUISITION_ROOT",
    "acquire_professional_images",
    "acquired_image_specs_for_entity",
    "load_professional_image_acquisition_receipt",
]
