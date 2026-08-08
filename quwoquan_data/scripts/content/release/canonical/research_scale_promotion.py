"""Write create-once cumulative research scale promotion receipts."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.release.canonical.campaign_scale_contract import MIN_SOAK_SECONDS
from content.release.canonical.campaign_scale_evidence import (
    CampaignScaleEvidenceError,
    load_campaign_scale_evidence,
)
from content.release.canonical.object_transaction_contract import _read_json
from content.release.canonical.research_scale_capacity import ResearchScaleCapacityEvidenceError, project_capacity_throughput
from content.release.canonical.research_scale_predecessor import (
    ResearchScalePredecessorError,
    load_predecessor_promotion,
)
from content.release.canonical.research_scale_promotion_timing import ResearchScalePromotionTimingError, validate_promotion_timing
from content.release.canonical.research_scale_source_mix import ResearchScaleSourceMixError, validate_research_scale_source_mix
from content.release.canonical.research_scale_video_popularity import (
    VIDEO_POPULARITY_EVIDENCE_ERROR,
    VIDEO_POPULARITY_SIGNALS,
    ResearchScaleVideoPopularityError,
    collect_m100_video_popularity_observations,
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


def _rate_statistic(numerator: int, denominator: int) -> dict[str, int | float]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": round(numerator / denominator, 6) if denominator else 0.0,
    }


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
    """Validate and project truthful milestone popularity observations."""
    try:
        observations = collect_m100_video_popularity_observations(
            release,
            expected_video_count=expected_video_count,
        )
    except ResearchScaleVideoPopularityError as exc:
        raise ResearchScalePromotionError(str(exc)) from exc
    denominator = len(observations)
    return {
        "signalAvailability": [
            {
                "signal": signal,
                **_rate_statistic(
                    sum(row[field] is not None for row in observations),
                    denominator,
                ),
            }
            for signal, field in VIDEO_POPULARITY_SIGNALS
        ],
        "rankingCoverage": _rate_statistic(
            sum(row["rankingEligible"] is True for row in observations),
            denominator,
        ),
        "observations": observations,
    }


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
    if not isinstance(source_digests, list) or len(source_digests) != 1:
        raise ResearchScalePromotionError(
            "M100 promotion requires exactly one frozen sourceDigest"
        )
    source_digest = source_digests[0]
    if not isinstance(source_digest, Mapping):
        raise ResearchScalePromotionError("release sourceDigest is invalid")
    source_digest_value = str(source_digest.get("digest") or "")
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
    if resource_evidence.get("status") != "passed":
        raise ResearchScalePromotionError(
            "canonical campaign resource isolation evidence is not passed"
        )
    try:
        promotion_timing = validate_promotion_timing(target_scale=target_scale, evidence=evidence, resource_evidence=resource_evidence)
        capacity_throughput = project_capacity_throughput(evidence=evidence, resource_evidence=resource_evidence)
    except (ResearchScalePromotionTimingError, ResearchScaleCapacityEvidenceError) as exc:
        raise ResearchScalePromotionError(str(exc)) from exc
    source_revision = str(evidence.get("sourceRevision") or "")
    entity_catalog_digest = str(evidence.get("entityCatalogDigest") or "")
    if (
        evidence.get("sourceDigest") != source_digest_value
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
            source_digest=source_digest_value,
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
            or approved_quota != required_delta
            or selected != qualified + discarded
            or not isinstance(discards, list)
            or len(discards) != discarded
            or finalized != qualified
            or accepted != carried + qualified
            or receipt_shortfall != max(0, required_delta - qualified)
            or qualified < 1
        ):
            raise ResearchScalePromotionError(
                f"{carrier} promotion count/receipt closure is inconsistent"
            )
        if receipt_shortfall != 0 or accepted < target:
            raise ResearchScalePromotionError(
                f"DATA.SCALE.ATTAINMENT_SHORTFALL: {carrier} requires {target} cumulative finalized objects"
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
                "qualifiedCount": qualified,
                "finalizedCount": finalized,
                "predecessorCarriedCount": carried,
                "newFinalizedCount": finalized,
                "totalUniqueFinalizedCount": accepted,
                "selectedCount": selected,
                "discardedCount": discarded,
                "shortfallCount": 0,
                "researchAcceptedCount": accepted,
            }
        )
    article_coverage = admission.get("articleMediaCoverage")
    if not isinstance(article_coverage, Mapping):
        raise ResearchScalePromotionError("release article media statistics are missing")
    article_count = _count(
        article_coverage.get("articleCount"), label="articleMediaCoverage.articleCount"
    )
    illustrated_count = _count(
        article_coverage.get("illustratedCount"),
        label="articleMediaCoverage.illustratedCount",
    )
    text_only_count = _count(
        article_coverage.get("textOnlyCount"),
        label="articleMediaCoverage.textOnlyCount",
    )
    illustrated_statistic = _rate_statistic(illustrated_count, article_count)
    text_only_statistic = _rate_statistic(text_only_count, article_count)
    article_lane = next(row for row in promotion_counts if row["carrier"] == "article")
    if (
        article_count != article_lane["totalUniqueFinalizedCount"]
        or illustrated_count + text_only_count != article_count
        or float(article_coverage.get("illustratedRate") or 0.0)
        != illustrated_statistic["rate"]
        or float(article_coverage.get("textOnlyRate") or 0.0)
        != text_only_statistic["rate"]
        or float(evidence.get("articleIllustratedRate") or 0.0)
        != illustrated_statistic["rate"]
    ):
        raise ResearchScalePromotionError("campaign article coverage evidence drift")
    if illustrated_statistic["rate"] < policy.illustrated_rate_target:
        raise ResearchScalePromotionError(
            "DATA.SCALE.ATTAINMENT_SHORTFALL: article illustrated rate is below 0.9"
        )
    duplicate_count = _count(
        evidence.get("duplicateAssetCount"), label="campaign duplicateAssetCount"
    )
    cross_lane_count = _count(
        evidence.get("crossLaneWriteCount"), label="campaign crossLaneWriteCount"
    )
    raw_recovery_rate = fault_evidence["automaticRecoveryRate"]
    recovery_eligible = _count(
        fault_evidence.get("recoveryEligibleCount"), label="recoveryEligibleCount"
    )
    automatic_recovered = _count(
        fault_evidence.get("automaticRecoveredCount"),
        label="automaticRecoveredCount",
    )
    expected_recovery_status = (
        "NOT_EXERCISED" if recovery_eligible == 0 else "MEASURED"
    )
    expected_recovery_rate = (
        round(automatic_recovered / recovery_eligible, 6)
        if recovery_eligible
        else None
    )
    if (
        automatic_recovered > recovery_eligible
        or (
            recovery_eligible == 0
            and raw_recovery_rate is not None
        )
        or (
            recovery_eligible > 0
            and (
                isinstance(raw_recovery_rate, bool)
                or not isinstance(raw_recovery_rate, (int, float))
                or float(raw_recovery_rate) != expected_recovery_rate
            )
        )
        or fault_evidence.get("automaticRecoveryStatus") != expected_recovery_status
    ):
        raise ResearchScalePromotionError("automatic recovery statistics drift")
    minimum_recovery_samples = {"M100": 20, "M1000": 50, "M10000": 100}[target_scale]
    if (
        recovery_eligible < minimum_recovery_samples
        or expected_recovery_rate is None
        or expected_recovery_rate < policy.automatic_recovery_rate_target
    ):
        raise ResearchScalePromotionError(
            "DATA.SCALE.ATTAINMENT_SHORTFALL: automatic recovery hard gate failed"
        )
    if duplicate_count or cross_lane_count:
        raise ResearchScalePromotionError(
            "M100 duplicateAssetCount and crossLaneWriteCount must both be zero"
        )
    if (
        int(resource_evidence.get("fourLaneLongestContinuousOverlapSeconds") or 0)
        < MIN_SOAK_SECONDS
        or not resource_evidence.get("allSemanticJobsTerminalAt")
        or not resource_evidence.get("terminalResidualMeasuredAfterAllJobs")
    ):
        raise ResearchScalePromotionError(
            "M100 requires 60 continuous four-lane minutes and post-terminal cleanup"
        )
    object_pass_numerator = sum(
        int(row["qualifiedCount"]) for row in promotion_counts
    )
    object_pass_denominator = sum(
        int(row["selectedCount"]) for row in promotion_counts
    )
    discarded_count = sum(int(row["discardedCount"]) for row in promotion_counts)
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
    except ResearchScalePromotionError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise ResearchScalePromotionError(
            f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: "
            f"release video evidence is unreadable: {exc}"
        ) from exc
    if (
        video_popularity["rankingCoverage"]["rate"] != 1
        or any(
            row["rate"] != 1
            for row in video_popularity["signalAvailability"]
        )
    ):
        raise ResearchScalePromotionError(
            "DATA.SCALE.ATTAINMENT_SHORTFALL: milestone videos require complete popularity signals and percentile"
        )
    try:
        professional_image_source_mix = validate_research_scale_source_mix(admission)
    except ResearchScaleSourceMixError as exc:
        raise ResearchScalePromotionError(str(exc)) from exc
    image_total = next(
        int(row["totalUniqueFinalizedCount"])
        for row in promotion_counts
        if row["carrier"] == "image"
    )
    if professional_image_source_mix["acceptedImageAssetCount"] != image_total:
        raise ResearchScalePromotionError(
            "DATA.SOURCE.POOL_SHORTFALL: image provider evidence count differs from cumulative finalized count"
        )
    statistics = {
        "objectPassRate": _rate_statistic(
            object_pass_numerator, object_pass_denominator
        ),
        "illustratedRate": illustrated_statistic,
        "videoPopularity": {
            "statistical": policy.video_popularity_statistical,
            "nonBlocking": policy.video_popularity_non_blocking,
            **video_popularity,
        },
        "automaticRecoveryRate": {
            "statistical": policy.automatic_recovery_statistical,
            "nonBlocking": policy.automatic_recovery_non_blocking,
            "status": expected_recovery_status,
            "eligibleCount": recovery_eligible,
            "automaticCount": automatic_recovered,
            "targetRate": policy.automatic_recovery_rate_target,
            "rate": expected_recovery_rate,
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
    document: dict[str, Any] = {
        "schema": "quwoquan_data.research_scale_promotion",
        "promotionId": promotion_id,
        "releaseId": release_id,
        "releaseClass": "research",
        "productLifecycleState": "research",
        "manifestDigest": manifest_digest,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest_value,
        "entityCatalogDigest": entity_catalog_digest,
        "targetScale": target_scale,
        "sourcePoolDigest": str(evidence["sourcePoolDigest"]),
        "predecessorSourcePoolDigests": list(evidence["predecessorSourcePoolDigests"]),
        **promotion_timing,
        "capacityThroughputByCarrier": capacity_throughput,
        "carrierCounts": promotion_counts,
        "statistics": statistics,
        "professionalImageSourceMix": professional_image_source_mix,
        "duplicateAssetCount": 0,
        "crossLaneWriteCount": 0,
        "resourceIsolationPassed": True,
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
        "allSemanticJobsTerminalAt": str(
            resource_evidence["allSemanticJobsTerminalAt"]
        ),
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
