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

from content.execution.controller.execute.pre_acquisition_handoff import (
    guard_acquisition_source_identity,
    load_pre_acquisition_handoff,
)
from content.source.image_payload import sniff_image_ext
from content.source.professional_image_admission import pre_acquisition_block
from content.source.professional_image_discovery_binding import (
    load_discovery_candidates,
    validate_discovery_binding,
)
from content.source.professional_image_receipt_counts import (
    provider_counts as _provider_counts,
)
from content.source.professional_image_receipt_validation import (
    validate_image_receipt_inventory,
)
from content.source.professional_image_source_attribution import (
    bound_image_source_attribution,
    build_image_plan_spec,
)
from content.source.professional_image_transport import fetch_public_image
from content.source.professional_safety_evidence import (
    file_sha256,
    load_bound_safety_evidence,
    validate_image_safety_payload,
)
from content.source.research.image_provider_compliance import classify_image_provider
from content.source.research.text_match import _normalized_title

_EXTRACTED_DEPENDENCIES = (
    AcquisitionStatus,
    DistributionDecision,
    bound_image_source_attribution,
    build_image_plan_spec,
    image_distribution_decision,
    load_discovery_candidates,
    pixel_size_issue,
    probe_image_bytes,
    validate_discovery_binding,
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


def _frozen_supported_api_payload(
    item: Mapping[str, Any],
    *,
    output_root: Path,
) -> dict[str, Any]:
    """Read exact provider bytes already admitted by supported-API evidence."""
    relative = Path(str(item.get("apiEvidence") or ""))
    root = output_root.resolve()
    evidence_path = (root / relative).resolve()
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or root not in evidence_path.parents
        or evidence_path.is_symlink()
        or not evidence_path.is_file()
    ):
        raise ValueError("supported_api evidence ref is unsafe or missing")
    evidence = read_json(evidence_path)
    if not isinstance(evidence, Mapping):
        raise TypeError("supported_api evidence must be an object")
    assert_valid(
        evidence,
        "source",
        "professional_image_supported_api_evidence",
        label="professional image supported API evidence",
    )
    asset_relative = Path(str(evidence.get("originalAssetRef") or ""))
    asset_path = (root / asset_relative).resolve()
    if (
        asset_relative.is_absolute()
        or ".." in asset_relative.parts
        or root not in asset_path.parents
        or asset_path.is_symlink()
        or not asset_path.is_file()
    ):
        raise ValueError("supported_api original asset ref is unsafe or missing")
    descriptor = os.open(asset_path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        body = os.read(descriptor, _MAX_IMAGE_BYTES + 1)
    finally:
        os.close(descriptor)
    ext = sniff_image_ext(body, "")
    if (
        evidence.get("status") != "accepted"
        or evidence.get("candidateId") != item.get("assetId")
        or evidence.get("sourcePageUrl") != item.get("sourceUrl")
        or evidence.get("originalAssetUrl") != item.get("assetUrl")
        or evidence.get("contentSha256") != _content_digest(body)
        or len(body) < _MIN_IMAGE_BYTES
        or len(body) > _MAX_IMAGE_BYTES
        or ext is None
    ):
        raise ValueError("supported_api frozen physical input binding drift")
    return {
        "bytes": body,
        "ext": ext,
        "contentType": "",
        "requestedUrl": str(item["assetUrl"]),
        "normalizedFromUrl": str(item["assetUrl"]),
        "externalInputEvidenceSha256": file_sha256(evidence_path),
    }


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


def rebind_professional_image_acquisition_manifest(
    source_manifest_path: Path,
    *,
    handoff_ref: Path,
    destination: Path,
) -> tuple[dict[str, Any], Path]:
    """Rebind a verified frozen physical closure to one newer execution identity."""
    source = read_json(source_manifest_path)
    if not isinstance(source, dict):
        raise TypeError(
            "source professional image acquisition manifest must be an object"
        )
    assert_valid(
        source,
        "source",
        "professional_image_acquisition_manifest",
        label="source professional image acquisition manifest",
    )
    handoff = load_pre_acquisition_handoff(handoff_ref)
    frozen = source.get("frozenPhysicalInput")
    if not isinstance(frozen, Mapping):
        frozen = {
            "sourceRevision": source["sourceRevision"],
            "sourceDigest": source["sourceDigest"],
            "entityCatalogDigest": source["entityCatalogDigest"],
            "metadataCatalogDigest": source["discoveryPlanDigest"],
            "externalInputsDigest": _digest(source),
        }
    rebound = {
        **source,
        "sourceRevision": handoff["sourceRevision"],
        "sourceDigest": handoff["sourceDigest"]["digest"],
        "entityCatalogDigest": handoff["entityCatalogDigest"],
        "executionBundle": handoff["executionBundle"],
        "frozenPhysicalInput": dict(frozen),
    }
    assert_valid(
        rebound,
        "source",
        "professional_image_acquisition_manifest",
        label="rebound professional image acquisition manifest",
    )
    body = json.dumps(rebound, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if (
            destination.is_symlink()
            or not destination.is_file()
            or destination.read_bytes() != body
        ):
            raise ValueError(
                f"rebound acquisition manifest create-once collision: {destination}"
            ) from None
        return rebound, destination
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    return rebound, destination


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


def acquire_professional_images(
    manifest_path: Path,
    *,
    handoff_ref: Path,
    repo_root: Path | None = None,
    manual_root: Path | None = None,
    output_root: Path = ACQUISITION_ROOT,
) -> tuple[dict[str, Any], Path]:
    from content.source.professional_image_acquisition_execution import (
        acquire_professional_images as acquire,
    )

    return acquire(
        manifest_path,
        handoff_ref=handoff_ref,
        repo_root=repo_root,
        manual_root=manual_root,
        output_root=output_root,
        schema_validator=assert_valid,
        network_payload=_network_payload,
        source_identity_guard=guard_acquisition_source_identity,
        safety_evidence_loader=load_bound_safety_evidence,
        safety_payload_validator=validate_image_safety_payload,
    )


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
    "rebind_professional_image_acquisition_manifest",
]
