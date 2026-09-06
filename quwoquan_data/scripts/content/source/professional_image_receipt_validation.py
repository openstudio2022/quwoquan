"""Strict reload-time validation for professional image acquisition receipts."""

from __future__ import annotations

import hashlib
import urllib.parse
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from core.image_decode import probe_image_bytes
from core.image_rules import pixel_size_issue
from governance.coverage.distribution import (
    AcquisitionStatus,
    RightsStatus,
    image_distribution_decision,
)

from content.source.acquisition_body_state import (
    AcquiredBody,
    ReclaimedBody,
    assert_unit_reclamation_is_total,
)
from content.source.image_payload import sniff_image_ext
from content.source.professional_image_source_attribution import (
    bound_image_source_attribution,
)

ValidateItem = Callable[
    [Mapping[str, Any]],
    tuple[RightsStatus, dict[str, Any]],
]
PreAcquisitionBlock = Callable[[Mapping[str, Any]], tuple[str, str]]
ProviderCounts = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]


def _content_digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _resolved_cas_asset(
    row: Mapping[str, Any],
    *,
    resolved_root: Path,
    min_image_bytes: int,
    max_image_bytes: int,
    require_bodies: bool,
) -> AcquiredBody:
    asset_id = str(row.get("assetId") or "")
    content_sha256 = str(row.get("contentSha256") or "")
    asset_ref = str(row.get("assetRef") or "")
    digest = content_sha256.removeprefix("sha256:")
    relative = Path(asset_ref)
    if (
        not asset_ref
        or relative.is_absolute()
        or len(digest) != 64
        or relative.parent.as_posix() != f"cas/sha256/{digest[:2]}"
        or relative.stem != digest
        or relative.suffix not in {".gif", ".jpg", ".png", ".webp"}
    ):
        raise ValueError(
            f"professional image acquisition CAS identity mismatch: {asset_id}"
        )
    recorded_mime = str(row.get("mimeType") or "").strip().casefold()
    expected_ext_by_mime = {
        "image/gif": ".gif",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    if expected_ext_by_mime.get(recorded_mime) != relative.suffix:
        raise ValueError(
            f"professional image acquisition MIME/extension drift: {asset_ref}"
        )
    unresolved_path = resolved_root / relative
    asset_path = unresolved_path.resolve()
    # A symlink or an escaping path is never a reclamation outcome: the collector
    # only unlinks bodies in place, so these stay hard failures regardless of
    # whether the caller tolerates a reclaimed unit.
    if (
        unresolved_path.is_symlink()
        or asset_path == resolved_root
        or resolved_root not in asset_path.parents
    ):
        raise ValueError(
            f"professional image acquisition CAS asset is invalid: {asset_ref}"
        )
    if not asset_path.is_file():
        if require_bodies:
            raise ValueError(
                f"professional image acquisition CAS asset is missing: {asset_ref}"
            )
        return ReclaimedBody(asset_ref=asset_ref)
    body = asset_path.read_bytes()
    if not min_image_bytes <= len(body) <= max_image_bytes:
        raise ValueError(
            f"professional image acquisition CAS size is invalid: {asset_ref}"
        )
    if _content_digest(body) != content_sha256:
        raise ValueError(
            f"professional image acquisition CAS digest mismatch: {asset_ref}"
        )
    if len(body) != int(row.get("bytes") or 0):
        raise ValueError(
            f"professional image acquisition CAS byte count mismatch: {asset_ref}"
        )
    body_ext = sniff_image_ext(body, "")
    if body_ext != relative.suffix:
        raise ValueError(
            f"professional image acquisition CAS extension mismatch: {asset_ref}"
        )
    probe = probe_image_bytes(body)
    if not probe.succeeded:
        raise ValueError(
            f"professional image acquisition CAS quality drift: {asset_ref}"
        )
    if recorded_mime != probe.mime_type:
        raise ValueError(
            f"professional image acquisition CAS MIME drift: {asset_ref}"
        )
    if (
        probe.width != int(row.get("width") or 0)
        or probe.height != int(row.get("height") or 0)
    ):
        raise ValueError(
            f"professional image acquisition CAS quality drift: {asset_ref}"
        )
    return asset_path


def _validate_accepted_asset(
    row: Mapping[str, Any],
    *,
    asset_path: AcquiredBody | None,
    validate_item: ValidateItem,
    pre_acquisition_block: PreAcquisitionBlock,
) -> None:
    asset_id = str(row.get("assetId") or "")
    decision = str(row.get("distributionDecision") or "")
    accepted = decision in {"research_allowed", "commercial_allowed"}
    if not accepted:
        if row.get("planImageSpec") is not None:
            raise ValueError(
                "professional image acquisition blocked asset must not carry "
                f"planImageSpec: {asset_id}"
            )
        return
    if row.get("acquisitionStatus") != "acquired" or asset_path is None:
        raise ValueError(
            "professional image acquisition accepted asset was not acquired: "
            f"{asset_id}"
        )
    quality_issue = pixel_size_issue(
        int(row.get("width") or 0),
        int(row.get("height") or 0),
        asset_id=asset_id,
    )
    if quality_issue:
        raise ValueError(
            "professional image acquisition CAS quality admission failed: "
            f"{asset_id}:{quality_issue}"
        )
    rights_status, provider = validate_item(
        {**dict(row), "sourceId": str(row.get("provider") or "")}
    )
    if row.get("platform") != provider["platform"]:
        raise ValueError(
            f"professional image acquisition provider platform drift: {asset_id}"
        )
    failure_code, failure_detail = pre_acquisition_block(row)
    if failure_code:
        raise ValueError(
            "professional image acquisition accepted asset fails admission: "
            f"{asset_id}:{failure_code}:{failure_detail}"
        )
    authorization_proof = str(row.get("authorizationProof") or "").strip()
    expected_decision = image_distribution_decision(
        acquisition_status=AcquisitionStatus.ACQUIRED,
        rights_status=rights_status,
        authorization_proof=authorization_proof,
        usage_scope=str(row["usageScope"]),
        model_release_status=str(row["modelReleaseStatus"]),
    ).value
    if decision != expected_decision:
        raise ValueError(
            f"professional image acquisition accepted decision drift: {asset_id}"
        )
    expected_authorization_required = (
        rights_status is not RightsStatus.VERIFIED or not authorization_proof
    )
    if row.get("authorizationRequired") is not expected_authorization_required:
        raise ValueError(
            f"professional image acquisition authorizationRequired drift: {asset_id}"
        )
    if row.get("withdrawalRequired") is not (
        rights_status is not RightsStatus.VERIFIED
    ):
        raise ValueError(
            f"professional image acquisition withdrawalRequired drift: {asset_id}"
        )
    if row.get("failureCode") or row.get("failure"):
        raise ValueError(
            f"professional image acquisition accepted asset records failure: {asset_id}"
        )
    plan_spec = row.get("planImageSpec")
    if not isinstance(plan_spec, Mapping):
        raise TypeError(
            "professional image acquisition accepted asset lacks planImageSpec: "
            f"{asset_id}"
        )
    plan_url = urllib.parse.urlparse(str(plan_spec.get("url") or ""))
    plan_path = Path(urllib.parse.unquote(plan_url.path))
    if (
        plan_url.scheme != "file"
        or plan_url.netloc not in {"", "localhost"}
        or plan_url.params
        or plan_url.query
        or plan_url.fragment
        or not plan_path.is_absolute()
        or not plan_path.as_posix().endswith(f"/{row['assetRef']}")
    ):
        raise ValueError(
            f"professional image acquisition planImageSpec CAS drift: {asset_id}"
        )
    expected = {
        "sourceUrl": str(row["sourceUrl"]),
        "originalAssetUrl": str(row.get("assetUrl") or row["sourceUrl"]),
        "platform": str(provider["platform"]),
        "sourceId": str(provider["sourceId"]),
        "creator": str(row["creator"]),
        "credit": str(row["creator"]),
        "capturedAt": str(row["capturedAt"]),
        "contentSha256": str(row["contentSha256"]),
        "acquisitionStatus": "acquired",
        "rightsStatus": rights_status.value,
        "authorizationRequired": expected_authorization_required,
        "distributionDecision": decision,
        "rightsAuditStatus": rights_status.value,
        "rightsIssues": list(row["rightsIssues"]),
        "license": str(row["license"]),
        "licenseSnapshot": str(row["licenseSnapshot"]),
        "usageScope": str(row["usageScope"]),
        "modelReleaseStatus": str(row["modelReleaseStatus"]),
        "termsUrl": str(row["termsUrl"]),
        "authorizationProof": authorization_proof,
        "caption": str(row["caption"]),
        "relevance": str(row["relevance"]),
        "width": int(row["width"]),
        "height": int(row["height"]),
        "sourceAttribution": bound_image_source_attribution(
            row,
            platform=str(provider["platform"]),
            distribution_decision=decision,
        ),
    }
    drifted = [key for key, value in expected.items() if plan_spec.get(key) != value]
    if drifted:
        raise ValueError(
            "professional image acquisition planImageSpec field drift: "
            f"{asset_id}:{','.join(sorted(drifted))}"
        )


def validate_image_receipt_inventory(
    receipt: Mapping[str, Any],
    *,
    resolved_root: Path,
    min_image_bytes: int,
    max_image_bytes: int,
    validate_item: ValidateItem,
    pre_acquisition_block: PreAcquisitionBlock,
    provider_counts: ProviderCounts,
    require_bodies: bool = True,
) -> None:
    """Re-derive CAS, admission and funnel truth from one strict receipt.

    ``require_bodies`` is for readers that inspect receipts long after the fact,
    such as the collector: with it disabled a unit whose bodies were all
    reclaimed still validates, because the receipt remains a complete record of
    what was fetched. A unit that is only partly reclaimed fails either way.
    """

    rows = [dict(row) for row in receipt["assets"]]
    asset_ids = [str(row["assetId"]) for row in rows]
    if len(asset_ids) != len(set(asset_ids)):
        raise ValueError(
            "professional image acquisition receipt assetId values must be unique"
        )
    downloaded = 0
    accepted = 0
    accepted_digests: set[str] = set()
    bodies: list[AcquiredBody] = []
    for row in rows:
        acquired = row["acquisitionStatus"] == "acquired"
        asset_path: AcquiredBody | None = None
        if acquired:
            downloaded += 1
            asset_path = _resolved_cas_asset(
                row,
                resolved_root=resolved_root,
                min_image_bytes=min_image_bytes,
                max_image_bytes=max_image_bytes,
                require_bodies=require_bodies,
            )
            bodies.append(asset_path)
        elif any(
            (
                row["assetRef"],
                row["contentSha256"],
                row["mimeType"],
                row["width"],
                row["height"],
            )
        ):
            raise ValueError(
                "professional image acquisition non-acquired asset carries CAS "
                f"identity: {row['assetId']}"
            )
        _validate_accepted_asset(
            row,
            asset_path=asset_path,
            validate_item=validate_item,
            pre_acquisition_block=pre_acquisition_block,
        )
        if row["distributionDecision"] in {
            "research_allowed",
            "commercial_allowed",
        }:
            accepted += 1
            content_sha256 = str(row["contentSha256"])
            if content_sha256 in accepted_digests:
                raise ValueError(
                    "professional image acquisition accepted contentSha256 values "
                    f"must be unique: {content_sha256}"
                )
            accepted_digests.add(content_sha256)
    assert_unit_reclamation_is_total(
        bodies,
        label="professional image acquisition receipt",
    )
    expected_counts = {
        "plannedAssetCount": len(rows),
        "discoveredAssetCount": len(rows),
        "downloadedAssetCount": downloaded,
        "acceptedAssetCount": accepted,
        "rejectedAssetCount": len(rows) - accepted,
    }
    drifted_counts = [
        key for key, value in expected_counts.items() if receipt.get(key) != value
    ]
    if drifted_counts:
        raise ValueError(
            "professional image acquisition receipt funnel count drift: "
            + ",".join(sorted(drifted_counts))
        )
    expected_status = (
        "ready"
        if accepted == len(rows)
        else ("partial" if accepted else "blocked")
    )
    recorded_status = receipt.get("status")
    if recorded_status is not None and recorded_status != expected_status:
        raise ValueError(
            "professional image acquisition receipt status drift: "
            f"expected={expected_status} actual={recorded_status}"
        )
    if list(receipt["providerAssetCounts"]) != provider_counts(rows):
        raise ValueError("professional image acquisition providerAssetCounts drift")


__all__ = ["validate_image_receipt_inventory"]
