"""Rebind verified historical video bytes to one fresh source identity.

The historical acquisition supplies physical bytes and provenance only.  Every
rebound asset is probed again and receives a fresh host source-scoped review;
historical safety or semantic decisions are never copied into the new manifest.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid, load_schema, validate_strict

from content.source.pre_acquisition_handoff import (
    load_pre_acquisition_handoff,
)
from content.source.professional_commons_video_input_evidence import (
    digest,
    safe_ref,
    write_once,
)
from content.source.professional_safety_evidence import file_sha256
from content.source.host_source_review import (
    prepare_host_source_review_request,
    read_host_source_review_result,
)
from content.source.professional_video_manual_input_media import render_contact_sheet
from content.source.professional_video_probe import probe_professional_video
from content.source.professional_video_rebind_historical import (
    HISTORICAL_PROVENANCE_FIELDS,
    HistoricalVideoEvidenceError,
    index_historical_video_assets,
    validate_historical_video_manifest,
    validate_historical_video_pair,
    validate_historical_video_receipt,
    validate_historical_video_receipt_path,
)
from content.source.professional_video_rebind_storage import (
    safe_rebind_destination,
    write_rebind_manifest_once,
)
from content.source.professional_video_receipt import (
    ACCEPTED_DECISIONS,
    canonical_child,
    document_digest,
    file_digest,
)
from content.source.sourced_video_admission import scan_sourced_video_watermark


class ProfessionalVideoRebindError(RuntimeError):
    """One global rebind input or one asset closure is invalid."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> None:
    raise ProfessionalVideoRebindError(code, detail)


def _load_source_receipt(
    receipt_ref: str,
    *,
    root: Path,
) -> tuple[dict[str, Any], Path, str]:
    """Validate immutable receipt identity while deferring CAS checks per asset."""
    try:
        path = canonical_child(root, receipt_ref, label="source video receiptRef")
        receipt = validate_historical_video_receipt(read_json(path))
        validate_historical_video_receipt_path(
            path, manifest_digest=str(receipt["manifestDigest"])
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        _fail("DATA.SOURCE.REBIND_RECEIPT_INVALID", str(exc))
    return receipt, path, file_digest(path)


_PROVENANCE_FIELDS = HISTORICAL_PROVENANCE_FIELDS


def _verify_source_asset(
    *,
    item: Mapping[str, Any],
    row: Mapping[str, Any],
    root: Path,
) -> Path:
    asset_id = str(item.get("assetId") or "")
    if (
        row.get("acquisitionStatus") != "acquired"
        or row.get("distributionDecision") not in ACCEPTED_DECISIONS
    ):
        _fail(
            "DATA.SOURCE.REBIND_ASSET_NOT_ADMITTED",
            f"historical asset is not acquired and admitted: {asset_id}",
        )
    missing = [
        field for field in _PROVENANCE_FIELDS if field not in item or field not in row
    ]
    if missing:
        _fail(
            "DATA.SOURCE.REBIND_PROVENANCE_UNPROVEN",
            f"historical provenance is incomplete for {asset_id}: "
            + ", ".join(missing),
        )
    drift = [field for field in _PROVENANCE_FIELDS if row.get(field) != item.get(field)]
    if drift:
        _fail(
            "DATA.SOURCE.REBIND_PROVENANCE_DRIFT",
            f"historical receipt differs from manifest for {asset_id}: "
            + ", ".join(drift),
        )
    content_sha = row.get("contentSha256")
    byte_count = row.get("bytes")
    if (
        not isinstance(content_sha, str)
        or not content_sha.startswith("sha256:")
        or len(content_sha) != 71
        or isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count < 1
        or not isinstance(row.get("authorizationRequired"), bool)
        or not isinstance(row.get("rightsIssues"), list)
    ):
        _fail(
            "DATA.SOURCE.REBIND_CAS_BINDING_INVALID",
            f"historical receipt lacks a provable CAS/rights binding: {asset_id}",
        )
    try:
        asset = canonical_child(
            root,
            str(row.get("assetRef") or ""),
            label=f"{asset_id}.assetRef",
        )
    except ValueError as exc:
        _fail("DATA.SOURCE.REBIND_CAS_BINDING_INVALID", str(exc))
    if asset.is_symlink() or not asset.is_file():
        _fail(
            "DATA.SOURCE.REBIND_ASSET_MISSING",
            f"historical CAS object is missing: {asset_id}",
        )
    if file_digest(asset) != content_sha or asset.stat().st_size != byte_count:
        _fail(
            "DATA.SOURCE.SOURCE_BYTES_DRIFT",
            f"historical CAS bytes differ from receipt: {asset_id}",
        )
    return asset


def _assert_current_rebound_item(item: Mapping[str, Any]) -> None:
    """Keep one retired-shape item from cancelling valid rebound siblings."""
    schema = load_schema("source", "professional_video_acquisition_manifest")
    item_schema = schema.get("$defs", {}).get("item")
    if not isinstance(item_schema, dict):
        _fail(
            "DATA.SOURCE.REBIND_CURRENT_ITEM_INVALID",
            "current professional video item schema is unavailable",
        )
    issues = validate_strict(dict(item), item_schema, _root_schema=schema)
    if issues:
        _fail(
            "DATA.SOURCE.REBIND_CURRENT_ITEM_INVALID",
            "; ".join(issues[:5]),
        )


def _source_attribution(item: Mapping[str, Any]) -> dict[str, str]:
    return {
        "provider": str(item["provider"]),
        "sourcePostUrl": str(item["sourceUrl"]),
        "originalAssetUrl": str(item["assetUrl"]),
        "creator": str(item["creator"]),
        "license": str(item["license"]),
        "termsUrl": str(item["termsUrl"]),
        "authorizationProof": str(item["authorizationProof"]),
    }


def _safety_attribution_supported(attribution: Mapping[str, str]) -> bool:
    return all(
        str(attribution.get(field) or "").startswith("https://")
        for field in (
            "sourcePostUrl",
            "originalAssetUrl",
            "termsUrl",
            "authorizationProof",
        )
    )


def _rebind_one(
    *,
    item: Mapping[str, Any],
    row: Mapping[str, Any],
    root: Path,
    receipt_ref: str,
    receipt_digest: str,
    receipt_file_sha: str,
    source_identity: Mapping[str, str],
) -> dict[str, Any]:
    asset_id = str(item["assetId"])
    asset = _verify_source_asset(item=item, row=row, root=root)
    token = digest(
        {
            "assetId": asset_id,
            "contentSha256": row["contentSha256"],
            "sourceReceiptDigest": receipt_digest,
            "sourceIdentity": dict(source_identity),
        }
    ).removeprefix("sha256:")[:24]
    evidence_root = root / "video-rebind" / token
    try:
        probe = probe_professional_video(asset)
        if not (
            probe.get("playable") is True
            and probe.get("motionVideo") is True
            and probe.get("premiumPlayableEligible") is True
        ):
            _fail(
                "DATA.SOURCE.NOT_PLAYABLE_MOTION_VIDEO",
                f"fresh probe rejected historical bytes: {asset_id}",
            )
        watermark = scan_sourced_video_watermark(asset)
        if watermark.get("decision") != "passed":
            _fail(
                "DATA.SOURCE.WATERMARK_BLOCKED",
                f"fresh OCR/watermark scan rejected historical bytes: {asset_id}",
            )
        contact_sheet = evidence_root / "contact-sheet.jpg"
        if not contact_sheet.is_file():
            evidence_root.mkdir(parents=True, exist_ok=True)
            render_contact_sheet(
                asset,
                contact_sheet,
                frame_count=int(probe["frameCount"]),
                fail=lambda detail: _fail(
                    "DATA.SOURCE.MEDIA_PROBE_FAILED", str(detail)
                ),
            )
    except ProfessionalVideoRebindError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        _fail(
            "DATA.SOURCE.MEDIA_PROBE_FAILED",
            f"{asset_id}: {type(exc).__name__}",
        )
    preflight = {
        "schema": "quwoquan_data.professional_video_rebind_preflight",
        "assetId": asset_id,
        "contentSha256": str(row["contentSha256"]),
        "bytes": int(row["bytes"]),
        "mediaProbe": dict(probe),
        "watermarkEvidence": dict(watermark),
        "contactSheetRef": safe_ref(contact_sheet, root),
        "contactSheetSha256": file_sha256(contact_sheet),
    }
    write_once(evidence_root / "preflight.json", preflight)
    attribution = _source_attribution(item)
    acquisition_evidence = {
        "schema": "quwoquan_data.host_review_video_rebind_acquisition_evidence",
        "assetId": asset_id,
        "entityId": str(item["entityId"]),
        "observedEntityId": str(item["observedEntityId"]),
        "contentSha256": str(row["contentSha256"]),
        "assetRef": safe_ref(asset, root),
        "sourceReceiptRef": receipt_ref,
        "sourceReceiptDigest": receipt_digest,
        "sourceReceiptFileSha256": receipt_file_sha,
    }
    acquisition_path = write_once(evidence_root / "acquisition-evidence.json", acquisition_evidence)
    probe_evidence = {
        "schema": "quwoquan_data.host_review_video_rebind_probe_evidence",
        "assetId": asset_id,
        "entityId": str(item["entityId"]),
        "contentSha256": str(row["contentSha256"]),
        "mediaProbe": dict(probe),
        "contactSheetRef": safe_ref(contact_sheet, root),
        "contactSheetSha256": file_sha256(contact_sheet),
    }
    probe_path = write_once(evidence_root / "media-probe-evidence.json", probe_evidence)
    safety_scan = {
        "schema": "quwoquan_data.host_review_safety_scan_evidence",
        "assetId": asset_id,
        "entityId": str(item["entityId"]),
        "contentSha256": str(row["contentSha256"]),
        "watermarkEvidence": dict(watermark),
    }
    safety_scan_path = write_once(evidence_root / "safety-scan-evidence.json", safety_scan)
    rights_evidence = {
        "schema": "quwoquan_data.host_review_rights_evidence",
        "assetId": asset_id,
        "entityId": str(item["entityId"]),
        "contentSha256": str(row["contentSha256"]),
        "sourceAttribution": attribution,
        "rightsSnapshot": {
            "rightsStatus": str(row["rightsStatus"]),
            "authorizationRequired": bool(row["authorizationRequired"]),
            "distributionDecision": str(row["distributionDecision"]),
            "rightsIssues": list(row["rightsIssues"]),
            "modelReleaseStatus": str(row["modelReleaseStatus"]),
            "propertyReleaseStatus": str(row["propertyReleaseStatus"]),
        },
    }
    rights_path = write_once(evidence_root / "rights-evidence.json", rights_evidence)
    request, request_ref = prepare_host_source_review_request(
        evidence_root=root,
        source_identity=source_identity,
        asset_kind="video",
        asset_id=asset_id,
        asset_ref=safe_ref(asset, root),
        content_sha256=str(row["contentSha256"]),
        entity_id=str(item["entityId"]),
        observed_entity_id=str(item["observedEntityId"]),
        content_ref=str(item["sourceUrl"]),
        evidence_refs={
            "acquisition": safe_ref(acquisition_path, root),
            "media_probe": safe_ref(probe_path, root),
            "safety_scan": safe_ref(safety_scan_path, root),
            "rights_attribution": safe_ref(rights_path, root),
        },
    )
    result = read_host_source_review_result(evidence_root=root, request_ref=request_ref)
    judgment = result["verdict"]
    accepted = judgment["status"] == "passed"
    result_ref = (
        Path("host-source-reviews") / "results"
        / f"{request['requestDigest'].removeprefix('sha256:')}.json"
    ).as_posix()
    safety_payload: dict[str, Any] = {
        "schema": "quwoquan_data.manual_asset_safety_evidence",
        "assetId": asset_id,
        "entityId": str(item["entityId"]),
        "observedEntityId": str(item["observedEntityId"]),
        "sourcePageUrl": str(item["sourceUrl"]),
        "fileRef": "",
        "fileSha256": str(row["contentSha256"]),
        "bytes": int(row["bytes"]),
        "contactSheetRef": safe_ref(contact_sheet, root),
        "contactSheetSha256": file_sha256(contact_sheet),
        "mediaProbe": dict(probe),
        "status": "passed" if accepted else "blocked",
        "entityMatch": str(judgment["entityMatch"]),
        "privacyRisk": str(judgment["privacyRisk"]),
        "minorRisk": str(judgment["minorRisk"]),
        "maliciousMediaRisk": str(judgment["maliciousMediaRisk"]),
        "watermarkStatus": str(judgment["watermarkStatus"]),
        "reviewedAt": str(result["reviewedAt"]),
        "reviewer": "host:" + str(result["actor"]["auditRunId"]),
        "reviewEvidence": {
            "contractVersion": result["contractVersion"],
            "requestRef": request_ref,
            "requestDigest": request["requestDigest"],
            "resultRef": result_ref,
            "resultDigest": result["resultDigest"],
            "actor": dict(result["actor"]),
        },
    }
    if _safety_attribution_supported(attribution):
        safety_payload["sourceAttribution"] = attribution
    assert_valid(
        safety_payload,
        "source",
        "professional_video_safety_evidence",
        label=f"rebound professional video safety evidence:{asset_id}",
    )
    safety_path = write_once(evidence_root / "safety-evidence.json", safety_payload)
    if not accepted:
        _fail(
            "DATA.SOURCE.REBIND_FRESH_REVIEW_BLOCKED",
            f"fresh host safety review blocked historical bytes: {asset_id}; "
            f"evidence={safe_ref(safety_path, root)}",
        )
    safety = {
        "status": safety_payload["status"],
        "entityMatch": safety_payload["entityMatch"],
        "privacyRisk": safety_payload["privacyRisk"],
        "minorRisk": safety_payload["minorRisk"],
        "maliciousMediaRisk": safety_payload["maliciousMediaRisk"],
        "watermarkStatus": safety_payload["watermarkStatus"],
        "reviewedAt": safety_payload["reviewedAt"],
        "reviewer": safety_payload["reviewer"],
        "evidenceRef": safe_ref(safety_path, root),
        "safetyEvidenceFileSha256": file_sha256(safety_path),
    }
    rebound = {
        key: value
        for key, value in dict(item).items()
        if key
        not in {
            "safetyReview",
            "popularCandidateId",
            "popularCatalogRef",
            "popularCatalogDigest",
            "popularCatalogFileSha256",
        }
    }
    rebound["safetyReview"] = safety
    rebound["frozenAsset"] = {
        "assetRef": safe_ref(asset, root),
        "contentSha256": str(row["contentSha256"]),
        "bytes": int(row["bytes"]),
        "sourceReceiptRef": receipt_ref,
        "sourceReceiptDigest": receipt_digest,
        "sourceReceiptFileSha256": receipt_file_sha,
    }
    _assert_current_rebound_item(rebound)
    return rebound


def _typed_exclusion(asset_id: str, exc: BaseException) -> dict[str, str]:
    code = getattr(exc, "code", "")
    if not isinstance(code, str) or not code:
        code = "DATA.SOURCE.REBIND_ASSET_EXCLUDED"
    detail = getattr(exc, "detail", "")
    if not isinstance(detail, str) or not detail:
        detail = f"{type(exc).__name__} while rebinding exact asset"
    return {"assetId": asset_id, "failureCode": code, "failure": detail}


def rebind_professional_video_acquisition_manifest(
    source_manifest_path: Path,
    *,
    source_receipt_ref: str,
    handoff_ref: Path,
    destination: Path,
    output_root: Path,
    asset_ids: Sequence[str] = (),
) -> tuple[dict[str, Any], Path | None]:
    """Create one current manifest from independently admitted historical bytes.

    Global document/identity failures fail closed.  Asset-local failures are
    returned as typed exclusions and never cancel successful siblings.
    """
    root = output_root.expanduser().resolve()
    try:
        source = validate_historical_video_manifest(
            read_json(source_manifest_path.expanduser().resolve())
        )
    except (OSError, TypeError, ValueError) as exc:
        _fail("DATA.SOURCE.REBIND_MANIFEST_INVALID", str(exc))
    receipt, _receipt_path, receipt_file_sha = _load_source_receipt(
        source_receipt_ref, root=root
    )
    source_manifest_digest = document_digest(source)
    try:
        validate_historical_video_pair(source, receipt)
    except HistoricalVideoEvidenceError as exc:
        _fail(
            "DATA.SOURCE.REBIND_RECEIPT_MANIFEST_DRIFT",
            str(exc),
        )
    handoff_path = handoff_ref.expanduser().resolve()
    handoff = load_pre_acquisition_handoff(handoff_path)
    source_identity = {
        "sourceRevision": str(handoff["sourceRevision"]),
        "sourceDigest": str(handoff["sourceDigest"]["digest"]),
        "entityCatalogDigest": str(handoff["entityCatalogDigest"]),
        "executionBundleDigest": str(handoff["executionBundle"]["digest"]),
        "handoffDigest": file_sha256(handoff_path),
    }
    requested = tuple(str(value).strip() for value in asset_ids)
    if requested and (
        any(not value for value in requested) or len(requested) != len(set(requested))
    ):
        _fail(
            "DATA.SOURCE.REBIND_ASSET_SELECTION_INVALID",
            "asset ids must be non-empty and unique",
        )
    items, manifest_order, ambiguous_items = index_historical_video_assets(
        source["items"]
    )
    rows, _receipt_order, ambiguous_rows = index_historical_video_assets(
        receipt["assets"]
    )
    selected = requested or manifest_order
    rebound_items: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    work = [asset_id for asset_id in selected if asset_id in items and asset_id in rows]
    for asset_id in selected:
        if asset_id not in items or asset_id not in rows:
            ambiguity = asset_id in ambiguous_items or asset_id in ambiguous_rows
            exclusions.append(
                {
                    "assetId": asset_id,
                    "failureCode": "DATA.SOURCE.REBIND_ASSET_MISSING",
                    "failure": (
                        "asset is ambiguous in source manifest or receipt"
                        if ambiguity
                        else "asset is absent from source manifest or receipt"
                    ),
                }
            )
    if work:
        with ThreadPoolExecutor(
            max_workers=len(work), thread_name_prefix="professional-video-rebind"
        ) as executor:
            futures = [
                (
                    asset_id,
                    executor.submit(
                        _rebind_one,
                        item=items[asset_id],
                        row=rows[asset_id],
                        root=root,
                        receipt_ref=source_receipt_ref,
                        receipt_digest=str(receipt["receiptDigest"]),
                        receipt_file_sha=receipt_file_sha,
                        source_identity=source_identity,
                    ),
                )
                for asset_id in work
            ]
            completed: dict[str, dict[str, Any]] = {}
            for asset_id, future in futures:
                try:
                    completed[asset_id] = future.result()
                except Exception as exc:  # noqa: BLE001 - one asset is isolated.
                    exclusions.append(_typed_exclusion(asset_id, exc))
            rebound_items.extend(
                completed[value] for value in selected if value in completed
            )

    if not rebound_items:
        codes = sorted({row["failureCode"] for row in exclusions})
        _fail(
            "DATA.SOURCE.REBIND_NO_SUCCESS",
            "no video asset reached current manifest admission; exclusions="
            + ",".join(codes),
        )
    manifest_path: Path | None = None
    manifest: dict[str, Any] | None = None
    if rebound_items:
        token = digest(
            {
                "sourceReceiptDigest": receipt["receiptDigest"],
                "handoffDigest": source_identity["handoffDigest"],
                "assetIds": [item["assetId"] for item in rebound_items],
            }
        ).removeprefix("sha256:")[:24]
        manifest = {
            "schema": "quwoquan_data.professional_video_acquisition_manifest",
            "manifestId": f"video-rebind-{token}",
            "sourceRevision": source_identity["sourceRevision"],
            "sourceDigest": source_identity["sourceDigest"],
            "entityCatalogDigest": source_identity["entityCatalogDigest"],
            "executionBundle": dict(handoff["executionBundle"]),
            "frozenPhysicalInput": {
                "sourceRevision": str(source["sourceRevision"]),
                "sourceDigest": str(source["sourceDigest"]),
                "entityCatalogDigest": str(source["entityCatalogDigest"]),
                "sourceManifestDigest": source_manifest_digest,
                "sourceReceiptRef": source_receipt_ref,
                "sourceReceiptDigest": str(receipt["receiptDigest"]),
                "sourceReceiptFileSha256": receipt_file_sha,
            },
            "items": rebound_items,
        }
        assert_valid(
            manifest,
            "source",
            "professional_video_acquisition_manifest",
            label="rebound professional video acquisition manifest",
        )
        manifest_path = write_rebind_manifest_once(
            safe_rebind_destination(destination, root=root, fail=_fail),
            manifest,
            fail=_fail,
        )
    result = {
        "schema": "quwoquan_data.professional_video_rebind_result",
        "requestedCount": len(selected),
        "reboundCount": len(rebound_items),
        "excludedCount": len(exclusions),
        "manifestId": str(manifest.get("manifestId") or "") if manifest else "",
        "manifestRef": safe_ref(manifest_path, root) if manifest_path else "",
        "items": [
            {
                "assetId": str(item["assetId"]),
                "status": "rebound",
                "contentSha256": str(item["frozenAsset"]["contentSha256"]),
            }
            for item in rebound_items
        ],
        "exclusions": exclusions,
    }
    return result, manifest_path


__all__ = [
    "ProfessionalVideoRebindError",
    "rebind_professional_video_acquisition_manifest",
]
