"""Acquire governed professional videos into an immutable local CAS."""
from __future__ import annotations

import tempfile
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from core.content_source_registry import load_content_source_registry
from core.io import read_json
from core.runtime_policy import active_runtime_policy
from core.schema import assert_valid
from core.video_source_admission import assert_video_source_admitted
from governance.coverage.distribution import (
    AcquisitionStatus,
    DistributionDecision,
    ProductLifecycleState,
    RightsStatus,
    distribution_decision,
    load_content_distribution_policy,
)

from content.source.professional_video_popularity import (
    apply_popularity_percentiles,
    initial_popularity_signals,
)
from content.source.professional_video_probe import probe_professional_video
from content.source.professional_video_receipt import (
    ACCEPTED_DECISIONS,
    ACQUISITION_ROOT,
    acquired_video_specs_for_entity,
    assert_funnel_consistent,
    document_digest,
    load_professional_video_acquisition_receipt,
    provider_counts,
    resolve_professional_video_candidate,
)
from content.source.professional_video_store import (
    put_video_cas,
    write_create_once_video_receipt,
)
from content.source.professional_video_transport import (
    copy_manual_video,
    fetch_public_video,
    redact_sensitive_video_url,
)
from content.source.research.text_match import _normalized_title


def _registered_video_source(
    provider: str,
    *,
    registry: Mapping[str, Any],
) -> dict[str, str]:
    rows: list[Mapping[str, Any]] = []
    common = registry.get("common")
    if isinstance(common, Mapping) and isinstance(common.get("video"), list):
        rows.extend(row for row in common["video"] if isinstance(row, Mapping))
    verticals = registry.get("verticals")
    travel = verticals.get("travel") if isinstance(verticals, Mapping) else None
    if isinstance(travel, Mapping) and isinstance(travel.get("video"), list):
        rows.extend(row for row in travel["video"] if isinstance(row, Mapping))
    matches = [row for row in rows if str(row.get("sourceId") or "") == provider]
    if len(matches) != 1:
        raise ValueError(f"professional video provider is not uniquely registered: {provider}")
    return {
        "sourceId": provider,
        "platform": str(matches[0].get("platform") or ""),
    }


def _require_timestamp(value: object, *, label: str) -> None:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")


def _validate_item(
    item: Mapping[str, Any],
    *,
    registry: Mapping[str, Any],
    lifecycle: ProductLifecycleState,
) -> tuple[RightsStatus, str]:
    asset_id = str(item["assetId"])
    rights = RightsStatus(str(item["rightsStatus"]))
    if rights is not RightsStatus.VERIFIED and not item["rightsIssues"]:
        raise ValueError(f"{asset_id}: non-verified video must record rightsIssues")
    alias_keys = [_normalized_title(value) for value in item["entityAliases"]]
    if not all(alias_keys) or len(alias_keys) != len(set(alias_keys)):
        raise ValueError(f"{asset_id}: entityAliases must be normalized-unique")
    rights_issues = [str(value).strip() for value in item["rightsIssues"]]
    if len(rights_issues) != len(set(rights_issues)):
        raise ValueError(f"{asset_id}: rightsIssues must be unique")
    _require_timestamp(item["capturedAt"], label=f"{asset_id}.capturedAt")
    _require_timestamp(
        item["safetyReview"]["reviewedAt"],
        label=f"{asset_id}.safetyReview.reviewedAt",
    )
    _require_timestamp(
        item["popularitySignals"]["observedAt"],
        label=f"{asset_id}.popularitySignals.observedAt",
    )
    terms_url = str(item["termsUrl"]).strip()
    if terms_url and not terms_url.startswith("https://"):
        raise ValueError(f"{asset_id}: termsUrl must be empty or use HTTPS")
    source = _registered_video_source(str(item["provider"]), registry=registry)
    if str(item["platform"]) != source["platform"]:
        raise ValueError(f"{asset_id}: platform does not match registered provider")
    publication = (
        "research_release"
        if lifecycle is ProductLifecycleState.RESEARCH
        else "commercial_release"
    )
    assert_video_source_admitted(
        registry,
        source_id=str(item["provider"]),
        source_kind=str(item["sourceKind"]),
        publication_admission=publication,
    )
    path = str(item["acquisitionPath"])
    asset_url = str(item["assetUrl"]).strip()
    manual_file = str(item["manualFile"]).strip()
    api_evidence = str(item["apiEvidence"]).strip()
    if path == "manual_file":
        if not manual_file or asset_url:
            raise ValueError(f"{asset_id}: manual_file requires manualFile and forbids assetUrl")
    elif not asset_url.startswith("https://") or manual_file:
        raise ValueError(f"{asset_id}: {path} requires HTTPS assetUrl and forbids manualFile")
    if path == "supported_api" and not api_evidence.startswith("https://"):
        raise ValueError(f"{asset_id}: supported_api requires HTTPS apiEvidence")
    if path != "supported_api" and api_evidence:
        raise ValueError(f"{asset_id}: apiEvidence is only valid for supported_api")
    signals = item["popularitySignals"]
    if str(signals["provider"]) != str(item["provider"]):
        raise ValueError(f"{asset_id}: popularity provider must match asset provider")
    for field in (
        "playCount",
        "likeCount",
        "commentCount",
        "shareCount",
        "favoriteCount",
    ):
        value = signals[field]
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            raise ValueError(
                f"{asset_id}: popularitySignals.{field} must be null or non-negative integer"
            )
    return rights, publication


def _pre_acquisition_block(item: Mapping[str, Any]) -> tuple[str, str]:
    access = item["accessEvidence"]
    if any(
        bool(access[field])
        for field in (
            "loginRequired",
            "captchaRequired",
            "paywallRequired",
            "drmProtected",
            "accessControlBypass",
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


def _source_identity(document: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(document["sourceRevision"]),
        str(document["sourceDigest"]),
        str(document["entityCatalogDigest"]),
    )


def _receipt_source_identity_header(path: Path) -> tuple[str, str, str]:
    """Read only the immutable identity header before current-schema validation.

    Historical receipts from another source identity are not candidates for
    deduplication and may predate the current receipt body schema.  A malformed
    header still fails closed because its identity cannot be proven foreign.
    """
    document = read_json(path)
    if not isinstance(document, Mapping):
        raise TypeError(
            f"professional video acquisition receipt header must be an object: {path}"
        )
    if document.get("schema") != "quwoquan_data.professional_video_acquisition_receipt":
        raise ValueError(
            f"professional video acquisition receipt header schema is invalid: {path}"
        )
    values: list[str] = []
    for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest"):
        value = document.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                "professional video acquisition receipt identity header is invalid: "
                f"{path} field={field}"
            )
        values.append(value)
    return values[0], values[1], values[2]


def _prior_content_index(
    output_root: Path,
    *,
    current_receipt: Path,
    source_identity: tuple[str, str, str],
) -> dict[str, str]:
    index: dict[str, str] = {}
    receipts = output_root / "receipts"
    if not receipts.is_dir():
        return index
    for path in sorted(receipts.glob("*.json")):
        if path.resolve() == current_receipt.resolve():
            continue
        ref = path.relative_to(output_root).as_posix()
        if _receipt_source_identity_header(path) != source_identity:
            continue
        receipt = load_professional_video_acquisition_receipt(ref, root=output_root)
        for row in receipt["assets"]:
            digest = str(row.get("contentSha256") or "")
            if row.get("acquisitionStatus") == "acquired" and digest:
                index.setdefault(digest, f"{ref}#{row['assetId']}")
    return index


def _empty_row(item: Mapping[str, Any], *, rights: RightsStatus) -> dict[str, Any]:
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
        "contentSha256": "",
        "assetRef": "",
        "bytes": 0,
        "mediaProbe": None,
        "duplicateOf": "",
        "failureCode": "",
        "failure": "",
        "popularitySignals": initial_popularity_signals(dict(item["popularitySignals"])),
        "planVideoSpec": None,
    }
    for field in ("sourceUrl", "assetUrl", "apiEvidence", "termsUrl", "authorizationProof"):
        row[field] = redact_sensitive_video_url(str(row[field]))
    return row


def _acquire_item(
    item: Mapping[str, Any],
    *,
    rights: RightsStatus,
    manual_root: Path | None,
    output_root: Path,
    temporary_root: Path,
    lifecycle: ProductLifecycleState,
) -> dict[str, Any]:
    row = _empty_row(item, rights=rights)
    failure_code, failure = _pre_acquisition_block(item)
    if failure_code:
        row.update(failureCode=failure_code, failure=failure)
        return row
    temporary = temporary_root / f"{item['assetId']}.download"
    try:
        if item["acquisitionPath"] == "manual_file":
            if manual_root is None:
                raise ValueError("manual_root is required by manual_file acquisition")
            suffix = copy_manual_video(str(item["manualFile"]), temporary, manual_root=manual_root)
        else:
            suffix = fetch_public_video(
                str(item["assetUrl"]),
                temporary,
                supported_api=item["acquisitionPath"] == "supported_api",
            )
        cas_path, content_sha256 = put_video_cas(
            temporary,
            suffix,
            output_root=output_root,
        )
    except (FileNotFoundError, OSError, TimeoutError, ValueError) as exc:
        row.update(
            acquisitionStatus=AcquisitionStatus.FAILED.value,
            failureCode="DATA.SOURCE.ACQUISITION_FAILED",
            failure=f"{type(exc).__name__}: {exc}",
        )
        return row
    finally:
        temporary.unlink(missing_ok=True)
    row.update(
        acquisitionStatus=AcquisitionStatus.ACQUIRED.value,
        contentSha256=content_sha256,
        assetRef=cas_path.relative_to(output_root).as_posix(),
        bytes=cas_path.stat().st_size,
    )
    decision = distribution_decision(
        acquisition_status=AcquisitionStatus.ACQUIRED,
        rights_status=rights,
        authorization_proof=str(item["authorizationProof"]),
    )
    try:
        probe = probe_professional_video(cas_path)
        row["mediaProbe"] = probe
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        row.update(
            distributionDecision=DistributionDecision.BLOCKED.value,
            failureCode="DATA.SOURCE.MEDIA_PROBE_FAILED",
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
    commercial_proof = str(row["authorizationProof"]).startswith("https://")
    if lifecycle is ProductLifecycleState.COMMERCIAL and (
        decision is not DistributionDecision.COMMERCIAL_ALLOWED or not commercial_proof
    ):
        row.update(
            distributionDecision=DistributionDecision.BLOCKED.value,
            failureCode="DATA.SOURCE.COMMERCIAL_RIGHTS_REQUIRED",
            failure="commercial lifecycle rejects research-only video",
        )
        return row
    row["distributionDecision"] = decision.value
    return row


def _plan_spec(row: Mapping[str, Any], *, receipt_ref: str, publication: str) -> dict[str, Any]:
    digest = str(row["contentSha256"])
    proof = str(row["authorizationProof"]).strip()
    original_asset = str(row["assetUrl"] or row["sourceUrl"])
    probe = row["mediaProbe"]
    assert isinstance(probe, Mapping)
    return {
        "sourceId": str(row["provider"]),
        "sourceKind": str(row["sourceKind"]),
        "ordinal": 1,
        "title": str(row["title"]),
        "relevance": str(row["relevance"]),
        "platform": str(row["platform"]),
        "assetUrl": f"cas://sha256/{digest.removeprefix('sha256:')}",
        "originalAssetUrl": original_asset,
        "sourcePostUrl": str(row["sourceUrl"]),
        "authorizationProofUrl": proof if proof.startswith("https://") else "",
        "termsUrl": str(row["termsUrl"]),
        "rightsBasis": str(row["license"]),
        "originalCreatorName": str(row["creator"]),
        "attributionText": f"{row['title']} — {row['creator']} — {row['license']} — {row['sourceUrl']}",
        "commercialAuthorizationStatus": (
            "verified" if row["distributionDecision"] == "commercial_allowed" else "unverified"
        ),
        "rightsStatus": str(row["rightsStatus"]),
        "rightsIssues": list(row["rightsIssues"]),
        "publicationAdmission": publication,
        "modelReleaseStatus": str(row["modelReleaseStatus"]),
        "propertyReleaseStatus": str(row["propertyReleaseStatus"]),
        "takedownPolicy": "quwoquan_standard_notice_and_takedown",
        "durationSeconds": int(probe["durationMs"]) / 1000,
        "sizeBytes": int(row["bytes"]),
        "mediaProbe": dict(probe),
        "popularitySignals": dict(row["popularitySignals"]),
        "professionalAcquisitionReceiptRef": receipt_ref,
        "professionalAssetId": str(row["assetId"]),
        "professionalContentSha256": digest,
        "premiumPlayableEligible": True,
    }


def acquire_professional_videos(
    manifest_path: Path,
    *,
    manual_root: Path | None = None,
    output_root: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Acquire every declared file without bypassing platform access controls."""
    root = (output_root or ACQUISITION_ROOT).resolve()
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise TypeError("professional video acquisition manifest must be an object")
    assert_valid(manifest, "source", "professional_video_acquisition_manifest", label="professional video acquisition manifest")
    if not manifest["items"]:
        raise ValueError("professional video acquisition manifest must contain items")
    asset_ids = [str(item["assetId"]) for item in manifest["items"]]
    if len(asset_ids) != len(set(asset_ids)):
        raise ValueError("professional video acquisition assetId values must be unique")
    provider_labels: dict[str, tuple[str, str]] = {}
    validated: list[tuple[dict[str, Any], RightsStatus, str]] = []
    registry = load_content_source_registry()
    lifecycle = load_content_distribution_policy().product_lifecycle_state
    for raw in manifest["items"]:
        item = dict(raw)
        rights, publication = _validate_item(
            item,
            registry=registry,
            lifecycle=lifecycle,
        )
        label = (str(item["displayName"]), str(item["platform"]))
        if str(item["provider"]) in provider_labels and provider_labels[str(item["provider"])] != label:
            raise ValueError(f"{item['assetId']}: provider displayName/platform are inconsistent")
        provider_labels[str(item["provider"])] = label
        validated.append((item, rights, publication))
    manifest_digest = document_digest(manifest)
    receipt_ref = f"receipts/{manifest_digest.removeprefix('sha256:')}.json"
    receipt_path = root / receipt_ref
    if receipt_path.is_file():
        receipt = load_professional_video_acquisition_receipt(receipt_ref, root=root)
        if receipt["manifestDigest"] != manifest_digest:
            raise ValueError(f"professional video acquisition receipt collision: {receipt_path}")
        return receipt, receipt_path
    prior = _prior_content_index(
        root,
        current_receipt=receipt_path,
        source_identity=_source_identity(manifest),
    )
    rows: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="professional-video-", dir=root) as temporary:
        temporary_root = Path(temporary)
        max_workers = min(
            len(validated),
            active_runtime_policy().download_concurrency,
        )
        with ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="professional-video",
        ) as executor:
            futures = [
                executor.submit(
                    _acquire_item,
                    item,
                    rights=rights,
                    manual_root=manual_root,
                    output_root=root,
                    temporary_root=temporary_root,
                    lifecycle=lifecycle,
                )
                for item, rights, _publication in validated
            ]
            acquired_rows = [future.result() for future in futures]
        for row in acquired_rows:
            digest = str(row["contentSha256"])
            duplicate_of = seen.get(digest) or prior.get(digest) if digest else ""
            if duplicate_of:
                row.update(
                    distributionDecision=DistributionDecision.BLOCKED.value,
                    duplicateOf=duplicate_of,
                    failureCode="DATA.SOURCE.DUPLICATE_ASSET",
                    failure=f"duplicate professional video: {duplicate_of}",
                )
            elif digest:
                seen[digest] = str(row["assetId"])
            rows.append(row)
    apply_popularity_percentiles(rows)
    publication = validated[0][2]
    for row in rows:
        if row["distributionDecision"] in ACCEPTED_DECISIONS:
            row["planVideoSpec"] = _plan_spec(row, receipt_ref=receipt_ref, publication=publication)
    planned = len(rows)
    downloaded = sum(row["acquisitionStatus"] == "acquired" for row in rows)
    accepted = sum(row["distributionDecision"] in ACCEPTED_DECISIONS for row in rows)
    stable = {
        "schema": "quwoquan_data.professional_video_acquisition_receipt",
        "manifestId": str(manifest["manifestId"]),
        "manifestDigest": manifest_digest,
        "sourceRevision": str(manifest["sourceRevision"]),
        "sourceDigest": str(manifest["sourceDigest"]),
        "entityCatalogDigest": str(manifest["entityCatalogDigest"]),
        "plannedAssetCount": planned,
        "discoveredAssetCount": planned,
        "downloadedAssetCount": downloaded,
        "acceptedAssetCount": accepted,
        "rejectedAssetCount": planned - accepted,
        "providerAssetCounts": provider_counts(rows),
        "assets": rows,
    }
    receipt = {**stable, "receiptDigest": document_digest(stable)}
    assert_valid(receipt, "source", "professional_video_acquisition_receipt", label="professional video acquisition receipt")
    assert_funnel_consistent(receipt)
    frozen = write_create_once_video_receipt(
        receipt_path,
        receipt,
        output_root=root,
    )
    return frozen, receipt_path


__all__ = [
    "ACQUISITION_ROOT",
    "acquire_professional_videos",
    "acquired_video_specs_for_entity",
    "load_professional_video_acquisition_receipt",
    "resolve_professional_video_candidate",
]
