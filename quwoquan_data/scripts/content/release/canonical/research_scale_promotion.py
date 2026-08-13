"""Write create-once cumulative research scale promotion receipts."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.release.canonical.campaign_scale_cumulative import (
    release_refs_by_carrier,
)
from content.release.canonical.campaign_scale_evidence import (
    CampaignScaleEvidenceError,
    load_campaign_scale_evidence,
)
from content.release.canonical.object_transaction_contract import _read_json
from content.release.canonical.release_header import validate_release_header
from content.release.canonical.research_scale_capacity import (
    ResearchScaleCapacityEvidenceError,
    project_capacity_throughput,
)
from content.release.canonical.research_scale_predecessor import (
    ResearchScalePredecessorError,
    load_predecessor_promotion,
)
from content.release.canonical.research_scale_promotion_statistics import (
    article_media_statistics,
    automatic_recovery_statistics,
    professional_image_source_mix_statistics,
    video_popularity_statistics,
)
from content.release.canonical.research_scale_promotion_statistics import (
    rate_statistic as _rate_statistic,
)
from content.release.canonical.research_scale_promotion_timing import (
    ResearchScalePromotionTimingError,
    validate_promotion_timing,
)
from content.release.canonical.research_scale_video_popularity import (
    VIDEO_POPULARITY_EVIDENCE_ERROR,
    VIDEO_POPULARITY_SIGNALS,
)
from core.io import write_json
from core.paths import OUTPUT_ROOT, RELEASE_ROOT, research_scale_promotions_root
from core.release_layout import payload_digest, payload_file
from core.schema import assert_valid
from governance.coverage.distribution import load_content_distribution_policy


class ResearchScalePromotionError(RuntimeError):
    pass


def _safe_segment(value: str, *, label: str) -> str:
    normalized = str(value or "").strip()
    path = Path(normalized)
    if (
        not normalized
        or normalized in {".", ".."}
        or path.is_absolute()
        or len(path.parts) != 1
        or "/" in normalized
        or "\\" in normalized
    ):
        raise ResearchScalePromotionError(f"{label} must be one safe segment")
    return normalized


def _evidence_ref(path: Path, *, output_root: Path) -> str:
    try:
        return path.resolve().relative_to(output_root.resolve()).as_posix()
    except ValueError as exc:
        raise ResearchScalePromotionError(
            "campaign evidence must be an audited file below QWQ_OUTPUT_ROOT"
        ) from exc


def _resolve_output_ref(raw_ref: object, *, output_root: Path, label: str) -> Path:
    ref = Path(str(raw_ref or ""))
    if ref.is_absolute() or not ref.parts or ".." in ref.parts:
        raise ResearchScalePromotionError(f"{label} must be one safe output ref")
    path = (output_root / ref).resolve()
    try:
        path.relative_to(output_root.resolve())
    except ValueError as exc:
        raise ResearchScalePromotionError(
            f"{label} must remain below QWQ_OUTPUT_ROOT"
        ) from exc
    return path


def _count(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ResearchScalePromotionError(f"{label} must be a non-negative integer")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _collect_m100_video_popularity(
    release: Path,
    *,
    expected_video_count: int,
) -> dict[str, Any]:
    return video_popularity_statistics(
        release, expected_video_count=expected_video_count
    )


def write_research_scale_promotion(
    *,
    release_id: str,
    promotion_id: str,
    campaign_evidence_path: Path,
    target_scale: str = "M100",
    predecessor_promotion_path: Path | None = None,
    release_root: Path = RELEASE_ROOT,
    output_root: Path = OUTPUT_ROOT,
) -> tuple[dict[str, Any], Path]:
    release_id = _safe_segment(release_id, label="releaseId")
    promotion_id = _safe_segment(promotion_id, label="promotionId")
    target_scale = str(target_scale or "").strip().upper()
    if target_scale not in {"M100", "M1000", "M10000"}:
        raise ResearchScalePromotionError(
            f"unsupported research milestone: {target_scale}"
        )
    release = release_root / release_id
    header = _read_json(payload_file(release, "release.json"))
    try:
        validate_release_header(header, label=f"research {target_scale} release")
    except (TypeError, ValueError) as exc:
        raise ResearchScalePromotionError(str(exc)) from exc
    admission = _read_json(payload_file(release, "asset_admission.json"))
    manifest_digest = payload_digest(release)
    if (
        header.get("releaseClass") != "research"
        or header.get("productLifecycleState") != "research"
        or admission.get("releaseClass") != "research"
        or admission.get("productLifecycleState") != "research"
    ):
        raise ResearchScalePromotionError("M100 promotion requires one research release")
    source_digests = header.get("sourceDigests")
    if not isinstance(source_digests, list) or not source_digests:
        raise ResearchScalePromotionError(
            "research promotion requires frozen sourceDigests"
        )
    source_digest_values = {
        str(row.get("digest") or "")
        for row in source_digests
        if isinstance(row, Mapping)
    }
    if len(source_digest_values) != len(source_digests):
        raise ResearchScalePromotionError("release sourceDigests are invalid")
    try:
        evidence, resource_evidence, fault_evidence = load_campaign_scale_evidence(
            campaign_evidence_path,
            output_root=output_root,
        )
    except CampaignScaleEvidenceError as exc:
        raise ResearchScalePromotionError(str(exc)) from exc
    if (
        evidence.get("releaseId") != release_id
        or evidence.get("manifestDigest") != manifest_digest
    ):
        raise ResearchScalePromotionError("campaign evidence release identity drift")
    try:
        promotion_timing = validate_promotion_timing(
            target_scale=target_scale,
            evidence=evidence,
            resource_evidence=resource_evidence,
        )
    except ResearchScalePromotionTimingError as exc:
        raise ResearchScalePromotionError(str(exc)) from exc
    capacity_issues: list[str] = []
    try:
        capacity_throughput = project_capacity_throughput(
            evidence=evidence,
            resource_evidence=resource_evidence,
        )
    except ResearchScaleCapacityEvidenceError as exc:
        capacity_throughput = []
        capacity_issues.append(str(exc))
    source_revision = str(evidence.get("sourceRevision") or "")
    evidence_source_digest = str(evidence.get("sourceDigest") or "")
    entity_catalog_digest = str(evidence.get("entityCatalogDigest") or "")
    if (
        evidence_source_digest not in source_digest_values
        or not source_revision.startswith("sha256:")
        or not entity_catalog_digest.startswith("sha256:")
    ):
        raise ResearchScalePromotionError(
            "campaign sourceRevision/sourceDigest/entityCatalogDigest drift"
        )
    try:
        predecessor_reference, predecessor_counts = load_predecessor_promotion(
            predecessor_promotion_path,
            target_scale=target_scale,
            source_revision=source_revision,
            source_digest=evidence_source_digest,
            entity_catalog_digest=entity_catalog_digest,
            output_root=output_root,
        )
    except ResearchScalePredecessorError as exc:
        raise ResearchScalePromotionError(str(exc)) from exc
    policy = load_content_distribution_policy()
    if policy.video_popularity_signals != tuple(
        signal for signal, _field in VIDEO_POPULARITY_SIGNALS
    ):
        raise ResearchScalePromotionError(
            "video popularity policy signals differ from promotion statistics"
        )
    carrier_rows = admission.get("carrierCounts")
    if not isinstance(carrier_rows, list):
        raise ResearchScalePromotionError("release carrierCounts are missing")
    carrier_admission = {
        str(row.get("carrier") or ""): row
        for row in carrier_rows
        if isinstance(row, Mapping)
    }
    carriers = ("homepage", "article", "image", "video")
    expected_carriers = set(carriers)
    targets = {
        carrier: policy.scale_target(target_scale, carrier)
        for carrier in carriers
    }
    if (
        header.get("milestone") != target_scale
        or header.get("targetEnvironment") is not None
        or header.get("releaseMode") != "research"
        or header.get("milestoneTargets") != targets
        or not isinstance(header.get("sourceIdentities"), list)
        or not str(header.get("sourceIdentitySetDigest") or "")
    ):
        raise ResearchScalePromotionError(
            "research promotion requires an environment-neutral exact milestone release"
        )
    lanes = {
        str(row.get("carrier") or ""): row
        for row in evidence.get("lanes") or []
        if isinstance(row, Mapping)
    }
    if (
        set(carrier_admission) != expected_carriers
        or set(lanes) != expected_carriers
        or set(targets) != expected_carriers
    ):
        raise ResearchScalePromotionError(
            f"{target_scale} requires complete homepage/article/image/video evidence"
        )
    promotion_counts: list[dict[str, Any]] = []
    campaign_wave_counts: list[dict[str, Any]] = []
    release_refs = release_refs_by_carrier(release)
    for carrier in carriers:
        lane = lanes[carrier]
        admission_row = carrier_admission[carrier]
        receipt_path = _resolve_output_ref(
            lane.get("publishReceiptRef"),
            output_root=output_root,
            label=f"{carrier} publish receipt",
        )
        if _file_sha256(receipt_path) != lane.get("publishReceiptSha256"):
            raise ResearchScalePromotionError(
                f"{carrier} publish receipt digest drift"
            )
        receipt = _read_json(receipt_path)
        target = targets[carrier]
        qualified = _count(
            receipt.get("qualifiedCount"), label=f"{carrier} qualifiedCount"
        )
        finalized = _count(
            receipt.get("finalizedCount"), label=f"{carrier} finalizedCount"
        )
        selected = _count(
            receipt.get("selectedCount"), label=f"{carrier} selectedCount"
        )
        discarded = _count(
            receipt.get("discardedCount"), label=f"{carrier} discardedCount"
        )
        receipt_shortfall = _count(
            receipt.get("shortfallCount"), label=f"{carrier} shortfallCount"
        )
        approved_quota = _count(
            receipt.get("approvedQuota"), label=f"{carrier} approvedQuota"
        )
        accepted = _count(
            admission_row.get("researchAcceptedCount"),
            label=f"{carrier} researchAcceptedCount",
        )
        carried = predecessor_counts[carrier]
        required_delta = max(0, target - carried)
        discards = receipt.get("discards")
        if (
            receipt.get("carrier") != carrier
            or receipt.get("executionId") != lane.get("executionId")
            or receipt.get("phase") != "publish"
            or receipt.get("status") not in {"finalized", "partial"}
            or approved_quota < 1
            or selected != qualified + discarded
            or not isinstance(discards, list)
            or len(discards) != discarded
            or finalized != qualified
            or receipt_shortfall != max(0, approved_quota - qualified)
            or qualified < 1
        ):
            raise ResearchScalePromotionError(
                f"{carrier} promotion count/receipt closure is inconsistent"
            )
        release_count = len(release_refs[carrier])
        object_count = _count(
            admission_row.get("objectCount"),
            label=f"{carrier} objectCount",
        )
        if accepted != target or object_count != target or release_count != target:
            raise ResearchScalePromotionError(
                "DATA.SCALE.ATTAINMENT_SHORTFALL: "
                f"{carrier} requires exact immutable cohort={target} "
                f"admission={accepted}/{object_count} releaseRefs={release_count}"
            )
        if (
            _count(lane.get("finalizedCount"), label=f"{carrier} lane finalizedCount")
            != finalized
            or _count(
                lane.get("researchAcceptedCount"),
                label=f"{carrier} lane researchAcceptedCount",
            )
            != qualified
        ):
            raise ResearchScalePromotionError(
                f"{carrier} campaign/release accepted count drift"
            )
        promotion_counts.append(
            {
                "carrier": carrier,
                "targetCount": target,
                "qualifiedCount": accepted,
                "finalizedCount": accepted,
                "predecessorCarriedCount": carried,
                "newFinalizedCount": required_delta,
                "totalUniqueFinalizedCount": accepted,
                "selectedCount": accepted,
                "discardedCount": 0,
                "shortfallCount": 0,
                "researchAcceptedCount": accepted,
            }
        )
        campaign_wave_counts.append(
            {
                "carrier": carrier,
                "approvedQuota": approved_quota,
                "selectedCount": selected,
                "qualifiedCount": qualified,
                "finalizedCount": finalized,
                "discardedCount": discarded,
                "shortfallCount": receipt_shortfall,
            }
        )
    article_coverage = admission.get("articleMediaCoverage")
    article_lane = next(row for row in promotion_counts if row["carrier"] == "article")
    try:
        illustrated_statistic, text_only_statistic = article_media_statistics(
            article_coverage,
            expected_article_count=int(article_lane["totalUniqueFinalizedCount"]),
        )
    except ValueError as exc:
        raise ResearchScalePromotionError(str(exc)) from exc
    duplicate_count = _count(
        evidence.get("duplicateAssetCount"), label="campaign duplicateAssetCount"
    )
    cross_lane_count = _count(
        evidence.get("crossLaneWriteCount"), label="campaign crossLaneWriteCount"
    )
    if duplicate_count or cross_lane_count:
        raise ResearchScalePromotionError(
            "M100 duplicateAssetCount and crossLaneWriteCount must both be zero"
        )
    object_pass_numerator = sum(
        int(row["qualifiedCount"]) for row in campaign_wave_counts
    )
    object_pass_denominator = sum(
        int(row["selectedCount"]) for row in campaign_wave_counts
    )
    discarded_count = sum(
        int(row["discardedCount"]) for row in campaign_wave_counts
    )
    first_pass_lane_count = sum(
        1
        for lane in lanes.values()
        if isinstance(lane.get("retryChain"), list)
        and len(lane["retryChain"]) == 1
    )
    try:
        video_popularity = _collect_m100_video_popularity(
            release,
            expected_video_count=next(
                int(row["researchAcceptedCount"])
                for row in promotion_counts
                if row["carrier"] == "video"
            ),
        )
    except (OSError, ResearchScalePromotionError, TypeError, ValueError) as exc:
        video_count = next(
            int(row["researchAcceptedCount"])
            for row in promotion_counts
            if row["carrier"] == "video"
        )
        video_popularity = {
            "signalAvailability": [
                {"signal": signal, **_rate_statistic(0, video_count)}
                for signal, _field in VIDEO_POPULARITY_SIGNALS
            ],
            "rankingCoverage": _rate_statistic(0, video_count),
            "observations": [],
            "observationIssues": [
                f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: {exc}"
            ],
        }
    video_popularity.setdefault("observationIssues", [])
    professional_image_source_mix = professional_image_source_mix_statistics(
        admission
    )
    try:
        automatic_recovery = automatic_recovery_statistics(
            fault_evidence,
            target_rate=policy.automatic_recovery_rate_target,
        )
    except ValueError as exc:
        raise ResearchScalePromotionError(str(exc)) from exc
    statistics = {
        "objectPassRate": _rate_statistic(
            object_pass_numerator, object_pass_denominator
        ),
        "illustratedRate": illustrated_statistic,
        "textOnlyRate": text_only_statistic,
        "videoPopularity": {
            "statistical": policy.video_popularity_statistical,
            "nonBlocking": policy.video_popularity_non_blocking,
            **video_popularity,
        },
        "automaticRecoveryRate": automatic_recovery,
        "capacityPlanning": {
            "statistical": True,
            "nonBlocking": True,
            "status": "MEASURED" if capacity_throughput else "UNAVAILABLE",
            "evidenceCount": len(capacity_throughput),
            "observationIssues": capacity_issues,
        },
        "resourceSoak": {
            "statistical": True,
            "nonBlocking": True,
            "status": str(resource_evidence.get("status") or "failed"),
            "durationSeconds": int(resource_evidence.get("durationSeconds") or 0),
            "fourLaneOverlapDurationSeconds": int(
                resource_evidence.get("fourLaneOverlapDurationSeconds") or 0
            ),
        },
        "firstPassRate": _rate_statistic(first_pass_lane_count, len(carriers)),
        "discardRate": _rate_statistic(
            discarded_count, object_pass_denominator
        ),
        "quotaAttainmentByCarrier": [
            {
                "carrier": carrier,
                **_rate_statistic(
                    int(row["totalUniqueFinalizedCount"]),
                    int(row["targetCount"]),
                ),
            }
            for carrier, row in zip(carriers, promotion_counts, strict=True)
        ],
    }
    source_identity_fields: dict[str, Any]
    if isinstance(header.get("sourceIdentities"), list):
        source_identity_fields = {
            "sourceIdentities": list(header["sourceIdentities"]),
            "sourceIdentitySetDigest": str(header.get("sourceIdentitySetDigest") or ""),
        }
    else:
        if len(source_digests) != 1:
            raise ResearchScalePromotionError(
                "single-source promotion requires exactly one sourceDigest"
            )
        source_identity_fields = {
            "sourceRevision": source_revision,
            "sourceDigest": evidence_source_digest,
            "entityCatalogDigest": entity_catalog_digest,
        }
    document: dict[str, Any] = {
        "schema": "quwoquan_data.research_scale_promotion",
        "promotionId": promotion_id,
        "releaseId": release_id,
        "releaseClass": "research",
        "productLifecycleState": "research",
        "manifestDigest": manifest_digest,
        **source_identity_fields,
        "targetScale": target_scale,
        "sourcePoolDigest": str(evidence["sourcePoolDigest"]),
        "predecessorSourcePoolDigests": list(evidence["predecessorSourcePoolDigests"]),
        **promotion_timing,
        "capacityThroughputByCarrier": capacity_throughput,
        "carrierCounts": promotion_counts,
        "campaignWaveStatistics": campaign_wave_counts,
        "statistics": statistics,
        "professionalImageSourceMix": professional_image_source_mix,
        "duplicateAssetCount": 0,
        "crossLaneWriteCount": 0,
        "resourceIsolationPassed": resource_evidence.get("status") == "passed",
        "soakDurationSeconds": int(resource_evidence["durationSeconds"]),
        "semanticJobsByLane": list(resource_evidence["semanticJobsByLane"]),
        "semanticCalibrationByLane": [
            dict(lane["semanticCalibration"])
            for lane in evidence["lanes"]
        ],
        "fourLaneOverlapSampleCount": int(
            resource_evidence["fourLaneOverlapSampleCount"]
        ),
        "fourLaneOverlapDurationSeconds": int(
            resource_evidence["fourLaneOverlapDurationSeconds"]
        ),
        "fourLaneLongestContinuousOverlapSeconds": int(
            resource_evidence["fourLaneLongestContinuousOverlapSeconds"]
        ),
        "allSemanticJobsTerminalAt": resource_evidence[
            "allSemanticJobsTerminalAt"
        ],
        "terminalResidualSampleAt": str(
            resource_evidence["terminalResidualSampleAt"]
        ),
        "campaignEvidenceRef": _evidence_ref(
            campaign_evidence_path, output_root=output_root
        ),
        "campaignEvidenceDigest": str(evidence["evidenceDigest"]),
        "resourceSoakEvidenceRef": str(evidence["resourceSoakEvidenceRef"]),
        "resourceSoakEvidenceDigest": str(
            evidence["resourceSoakEvidenceDigest"]
        ),
        "faultInjectionEvidenceRef": str(
            evidence["faultInjectionEvidenceRef"]
        ),
        "faultInjectionEvidenceDigest": str(
            evidence["faultInjectionEvidenceDigest"]
        ),
        "nextScaleEligible": {
            "M100": "M1000",
            "M1000": "M10000",
            "M10000": "COMPLETE",
        }[target_scale],
        "recordedAt": datetime.now(timezone.utc).isoformat(),
    }
    if predecessor_reference is not None:
        document["predecessorPromotion"] = predecessor_reference
    assert_valid(
        document,
        "release",
        "research_scale_promotion",
        label=f"research {target_scale} promotion",
    )
    path = (
        research_scale_promotions_root(output_root=output_root)
        / release_id
        / promotion_id
        / f"research-{target_scale.lower()}.json"
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ResearchScalePromotionError(
            f"append-only promotion already exists: {path.parent}"
        ) from exc
    write_json(path, document)
    return document, path
__all__ = ["ResearchScalePromotionError", "write_research_scale_promotion"]
