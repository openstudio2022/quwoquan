"""Acquire governed professional videos into an immutable local CAS."""
from __future__ import annotations

import tempfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from core.content_source_registry import load_content_source_registry
from core.io import read_json
from core.schema import assert_valid
from core.video_source_admission import assert_video_acquisition_path_allowed
from governance.coverage.distribution import (
    AcquisitionStatus,
    DistributionDecision,
    RightsStatus,
)

from content.source.professional_safety_evidence import (
    load_bound_safety_evidence,
    validate_video_safety_payload,
)
from content.source.professional_video_asset_acquisition import (
    acquire_video_item,
    empty_video_row,
)
from content.source.professional_video_plan_spec import build_video_plan_spec
from content.source.professional_video_popularity import initial_popularity_signals
from content.source.professional_video_probe import probe_professional_video
from content.source.professional_video_receipt import (
    ACCEPTED_DECISIONS,
    ACQUISITION_ROOT,
    assert_funnel_consistent,
    document_digest,
    load_professional_video_acquisition_receipt,
    provider_counts,
    resolve_professional_video_candidate,
)
from content.source.professional_video_spec_index import (
    acquired_video_specs_for_entity,
)
from content.source.professional_video_store import (
    ProfessionalVideoCasCollision,
    write_create_once_video_receipt,
)
from content.source.professional_video_transport import fetch_public_video
from content.source.research.text_match import _normalized_title


class ProfessionalVideoAcquisitionBlocked(ValueError):
    """A valid batch froze its evidence but admitted no video object."""

    code = "DATA.SOURCE.VIDEO_BATCH_NO_SUCCESS"

    def __init__(self, receipt: dict[str, Any], receipt_path: Path) -> None:
        self.receipt = receipt
        self.receipt_path = receipt_path
        failures = [
            f"{row['assetId']}={row['failureCode']}:{row['failure']}"
            for row in receipt["assets"]
        ]
        super().__init__(
            f"{self.code}: no professional video was admitted; "
            + "; ".join(failures)
        )


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
) -> RightsStatus:
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
    authorization_proof = str(item["authorizationProof"]).strip()
    if terms_url and not terms_url.startswith("https://"):
        raise ValueError(f"{asset_id}: termsUrl must be empty or use HTTPS")
    if authorization_proof and not authorization_proof.startswith("https://"):
        raise ValueError(f"{asset_id}: authorizationProof must be empty or use HTTPS")
    if rights is RightsStatus.VERIFIED and (
        not terms_url.startswith("https://")
        or not authorization_proof.startswith("https://")
    ):
        raise ValueError(
            f"{asset_id}: verified rights require HTTPS termsUrl and authorizationProof"
        )
    source = _registered_video_source(str(item["provider"]), registry=registry)
    if str(item["platform"]) != source["platform"]:
        raise ValueError(f"{asset_id}: platform does not match registered provider")
    assert_video_acquisition_path_allowed(
        registry,
        source_id=str(item["provider"]),
        source_kind=str(item["sourceKind"]),
        acquisition_path=str(item["acquisitionPath"]),
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
    return rights


def _excluded_item_row(
    item: Mapping[str, Any],
    *,
    rights: RightsStatus,
    code: str,
    error: BaseException,
) -> dict[str, Any]:
    detail = str(error).strip() or f"{type(error).__name__} excluded this asset"
    row = empty_video_row(item, rights=rights)
    row.update(failureCode=code, failure=detail)
    return row


def _build_plan_specs(rows: list[dict[str, Any]], *, receipt_ref: str) -> None:
    """Project admitted rows without semantic ranking or orchestration."""
    for row in rows:
        row["planVideoSpec"] = None
        row["popularitySignals"] = initial_popularity_signals(
            dict(row["popularitySignals"])
        )
        row["popularitySignals"].update(
            ineligibleReason=(
                "incomplete_popularity_signals"
                if row["popularitySignals"]["popularityScore"] is None
                else "insufficient_comparable_candidates"
            ),
            comparisonCandidateCount=(
                0 if row["popularitySignals"]["popularityScore"] is None else 1
            ),
        )
        if row["distributionDecision"] not in ACCEPTED_DECISIONS:
            row["popularitySignals"].update(
                ineligibleReason="asset_not_accepted",
                comparisonCandidateCount=0,
            )
            continue
        try:
            row["planVideoSpec"] = build_video_plan_spec(row, receipt_ref=receipt_ref)
        except (KeyError, TypeError, ValueError) as exc:
            row.update(
                distributionDecision=DistributionDecision.BLOCKED.value,
                failureCode="DATA.SOURCE.PLAN_SPEC_INVALID",
                failure=str(exc).strip() or "video plan projection failed",
                planVideoSpec=None,
            )
            row["popularitySignals"].update(
                ineligibleReason="asset_not_accepted",
                comparisonCandidateCount=0,
            )


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
    if manifest["posterPolicy"] != {
        "required": True,
        "format": "image/png",
        "rightsInheritance": "licensed_video_derivative",
    }:
        raise ValueError("professional video posterPolicy must require a licensed PNG derivative")
    if not manifest["items"]:
        raise ValueError("professional video acquisition manifest must contain items")
    asset_ids = [str(item["assetId"]) for item in manifest["items"]]
    if len(asset_ids) != len(set(asset_ids)):
        raise ValueError("professional video acquisition assetId values must be unique")
    provider_labels: dict[str, tuple[str, str]] = {}
    prepared: list[tuple[int, dict[str, Any], RightsStatus, dict[str, Any]]] = []
    rows_by_index: dict[int, dict[str, Any]] = {}
    registry = load_content_source_registry()
    for index, raw in enumerate(manifest["items"]):
        item = dict(raw)
        rights = RightsStatus(str(item["rightsStatus"]))
        try:
            rights = _validate_item(item, registry=registry)
        except Exception as exc:  # noqa: BLE001 - one manifest item is isolated.
            rows_by_index[index] = _excluded_item_row(
                item,
                rights=rights,
                code="DATA.SOURCE.ITEM_PREVALIDATION_FAILED",
                error=exc,
            )
            continue
        try:
            safety_evidence = load_bound_safety_evidence(
                item,
                evidence_root=root,
                kind="video",
                manual_root=manual_root,
            )
        except Exception as exc:  # noqa: BLE001 - one safety binding is isolated.
            rows_by_index[index] = _excluded_item_row(
                item,
                rights=rights,
                code="DATA.SOURCE.SAFETY_EVIDENCE_INVALID",
                error=exc,
            )
            continue
        label = (str(item["displayName"]), str(item["platform"]))
        provider = str(item["provider"])
        if provider in provider_labels and provider_labels[provider] != label:
            rows_by_index[index] = _excluded_item_row(
                item,
                rights=rights,
                code="DATA.SOURCE.ITEM_PREVALIDATION_FAILED",
                error=ValueError(
                    f"{item['assetId']}: provider displayName/platform are inconsistent"
                ),
            )
            continue
        provider_labels[provider] = label
        prepared.append((index, item, rights, safety_evidence))
    manifest_digest = document_digest(manifest)
    manifest_token = manifest_digest.removeprefix("sha256:")
    receipt_ref = f"receipts/{manifest_token}.json"
    receipt_path = root / receipt_ref
    if receipt_path.is_file():
        receipt = load_professional_video_acquisition_receipt(receipt_ref, root=root)
        if receipt["manifestDigest"] != manifest_digest:
            raise ValueError(f"professional video acquisition receipt collision: {receipt_path}")
        if int(receipt["acceptedAssetCount"]) == 0:
            raise ProfessionalVideoAcquisitionBlocked(receipt, receipt_path)
        return receipt, receipt_path
    seen: dict[str, str] = {}
    root.mkdir(parents=True, exist_ok=True)
    if prepared:
        with tempfile.TemporaryDirectory(prefix="professional-video-", dir=root) as temporary:
            temporary_root = Path(temporary)
            for index, item, rights, safety_evidence in prepared:
                try:
                    rows_by_index[index] = acquire_video_item(
                        item,
                        rights=rights,
                        safety_evidence=safety_evidence,
                        manual_root=manual_root,
                        output_root=root,
                        temporary_root=temporary_root,
                        safety_validator=validate_video_safety_payload,
                        network_fetcher=fetch_public_video,
                        media_probe=probe_professional_video,
                    )
                except ProfessionalVideoCasCollision:
                    raise
                except Exception as exc:  # noqa: BLE001 - one asset is isolated.
                    row = empty_video_row(item, rights=rights)
                    row.update(
                        acquisitionStatus=AcquisitionStatus.FAILED.value,
                        failureCode="DATA.SOURCE.ACQUISITION_FAILED",
                        failure=f"{type(exc).__name__}: {exc}",
                    )
                    rows_by_index[index] = row
    rows = [rows_by_index[index] for index in range(len(manifest["items"]))]
    for row in rows:
        digest = str(row["contentSha256"])
        duplicate_of = seen.get(digest, "") if digest else ""
        if duplicate_of:
            row.update(
                distributionDecision=DistributionDecision.BLOCKED.value,
                duplicateOf=duplicate_of,
                failureCode="DATA.SOURCE.DUPLICATE_ASSET",
                failure=f"duplicate professional video: {duplicate_of}",
            )
        elif digest:
            seen[digest] = str(row["assetId"])
    _build_plan_specs(rows, receipt_ref=receipt_ref)
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
        "posterPolicy": dict(manifest["posterPolicy"]),
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
    if accepted == 0:
        raise ProfessionalVideoAcquisitionBlocked(frozen, receipt_path)
    return frozen, receipt_path


__all__ = [
    "ACQUISITION_ROOT",
    "ProfessionalVideoAcquisitionBlocked",
    "acquire_professional_videos",
    "acquired_video_specs_for_entity",
    "load_professional_video_acquisition_receipt",
    "resolve_professional_video_candidate",
]
