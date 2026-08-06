"""Write the create-once research M100 promotion receipt."""
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
from content.source.professional_video_receipt import (
    assert_publishable_popularity_signals,
)
from core.io import write_json
from core.paths import OUTPUT_ROOT, RELEASE_ROOT
from core.release_layout import payload_digest, payload_file
from core.schema import assert_valid
from governance.coverage.distribution import load_content_distribution_policy


class ResearchScalePromotionError(RuntimeError):
    pass


_VIDEO_POPULARITY_BLOCKER = "DATA.RELEASE.VIDEO_POPULARITY_INCOMPLETE"


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


def _assert_m100_video_popularity(
    release: Path,
    *,
    expected_video_count: int,
) -> None:
    """Recheck strict ranking evidence only at the M100 promotion boundary."""
    desired = _read_json(payload_file(release, "desired_state.json"))
    desired_refs = desired.get("desiredRefs")
    post_refs = desired_refs.get("posts") if isinstance(desired_refs, Mapping) else None
    if not isinstance(post_refs, list):
        raise ResearchScalePromotionError(
            f"{_VIDEO_POPULARITY_BLOCKER}: release desired video refs are missing"
        )
    objects_root = payload_file(release, "objects")
    video_count = 0
    for raw_ref in post_refs:
        post_ref = Path(str(raw_ref or ""))
        if post_ref.is_absolute() or not post_ref.parts or ".." in post_ref.parts:
            raise ResearchScalePromotionError(
                f"{_VIDEO_POPULARITY_BLOCKER}: release post ref is unsafe"
            )
        object_root = objects_root / "posts" / post_ref
        manifest = _read_json(object_root / "manifest.json")
        if str(manifest.get("contentType") or "").strip() != "video":
            continue
        video_count += 1
        rights = _read_json(object_root / "rights.json")
        rights_assets = rights.get("assets")
        if not isinstance(rights_assets, list):
            raise ResearchScalePromotionError(
                f"{_VIDEO_POPULARITY_BLOCKER}: {raw_ref} rights assets are missing"
            )
        ranked_video_assets = 0
        for raw_asset in rights_assets:
            if not isinstance(raw_asset, Mapping):
                continue
            binding = raw_asset.get("independentAssetReview")
            if not isinstance(binding, Mapping) or binding.get("assetKind") != "video":
                continue
            receipt_ref = Path(str(binding.get("receiptRef") or ""))
            if (
                receipt_ref.is_absolute()
                or not receipt_ref.parts
                or ".." in receipt_ref.parts
            ):
                raise ResearchScalePromotionError(
                    f"{_VIDEO_POPULARITY_BLOCKER}: {raw_ref} review receipt ref is unsafe"
                )
            receipt = _read_json(object_root / receipt_ref)
            snapshot = receipt.get("assetSnapshot")
            if (
                receipt.get("assetKind") != "video"
                or receipt.get("reviewDecision") != "accepted"
                or not isinstance(snapshot, Mapping)
                or snapshot.get("assetId") != binding.get("acquisitionAssetId")
            ):
                raise ResearchScalePromotionError(
                    f"{_VIDEO_POPULARITY_BLOCKER}: {raw_ref} review binding is invalid"
                )
            try:
                assert_publishable_popularity_signals(
                    snapshot.get("popularitySignals"),
                    asset_id=str(snapshot.get("assetId") or "<missing>"),
                )
            except (TypeError, ValueError) as exc:
                raise ResearchScalePromotionError(
                    f"{_VIDEO_POPULARITY_BLOCKER}: {exc}"
                ) from exc
            ranked_video_assets += 1
        if ranked_video_assets < 1:
            raise ResearchScalePromotionError(
                f"{_VIDEO_POPULARITY_BLOCKER}: {raw_ref} has no ranked video asset"
            )
    if video_count != expected_video_count:
        raise ResearchScalePromotionError(
            f"{_VIDEO_POPULARITY_BLOCKER}: release video object count "
            f"{video_count} != admitted {expected_video_count}"
        )


def write_research_scale_promotion(
    *,
    release_id: str,
    promotion_id: str,
    campaign_evidence_path: Path,
    release_root: Path = RELEASE_ROOT,
    output_root: Path = OUTPUT_ROOT,
) -> tuple[dict[str, Any], Path]:
    release_id = _safe_segment(release_id, label="releaseId")
    promotion_id = _safe_segment(promotion_id, label="promotionId")
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
    policy = load_content_distribution_policy()
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
    targets = dict(policy.m100_targets)
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
            "M100 requires complete homepage/article/image/video evidence"
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
        shortfall = _count(
            receipt.get("shortfallCount"), label=f"{carrier} shortfallCount"
        )
        approved_quota = _count(
            receipt.get("approvedQuota"), label=f"{carrier} approvedQuota"
        )
        accepted = _count(
            admission_row.get("researchAcceptedCount"),
            label=f"{carrier} researchAcceptedCount",
        )
        discards = receipt.get("discards")
        if (
            receipt.get("carrier") != carrier
            or receipt.get("executionId") != lane.get("executionId")
            or receipt.get("phase") != "publish"
            or receipt.get("status") not in {"finalized", "partial"}
            or approved_quota != target
            or selected != qualified + discarded
            or not isinstance(discards, list)
            or len(discards) != discarded
            or finalized != qualified
            or accepted != qualified
            or shortfall != max(0, target - qualified)
            or qualified < 1
        ):
            raise ResearchScalePromotionError(
                f"{carrier} promotion count/receipt closure is inconsistent"
            )
        if (
            _count(lane.get("finalizedCount"), label=f"{carrier} lane finalizedCount")
            != finalized
            or _count(
                lane.get("researchAcceptedCount"),
                label=f"{carrier} lane researchAcceptedCount",
            )
            != accepted
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
                "selectedCount": selected,
                "discardedCount": discarded,
                "shortfallCount": shortfall,
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
    article_lane = next(
        row for row in promotion_counts if row["carrier"] == "article"
    )
    if (
        article_count != article_lane["qualifiedCount"]
        or illustrated_count + text_only_count != article_count
        or float(article_coverage.get("illustratedRate") or 0.0)
        != illustrated_statistic["rate"]
        or float(article_coverage.get("textOnlyRate") or 0.0)
        != text_only_statistic["rate"]
        or float(evidence.get("articleIllustratedRate") or 0.0)
        != illustrated_statistic["rate"]
    ):
        raise ResearchScalePromotionError("campaign article coverage evidence drift")
    duplicate_count = _count(
        evidence.get("duplicateAssetCount"), label="campaign duplicateAssetCount"
    )
    cross_lane_count = _count(
        evidence.get("crossLaneWriteCount"), label="campaign crossLaneWriteCount"
    )
    raw_recovery_rate = fault_evidence["automaticRecoveryRate"]
    if not isinstance(raw_recovery_rate, (int, float)) or isinstance(
        raw_recovery_rate, bool
    ):
        raise ResearchScalePromotionError("automaticRecoveryRate must be numeric")
    recovery_eligible = _count(
        fault_evidence.get("recoveryEligibleCount"), label="recoveryEligibleCount"
    )
    automatic_recovered = _count(
        fault_evidence.get("automaticRecoveredCount"),
        label="automaticRecoveredCount",
    )
    recovery_statistic = _rate_statistic(
        automatic_recovered,
        recovery_eligible,
    )
    expected_recovery_status = (
        "NOT_EXERCISED" if recovery_eligible == 0 else "MEASURED"
    )
    if (
        automatic_recovered > recovery_eligible
        or float(raw_recovery_rate) != recovery_statistic["rate"]
        or fault_evidence.get("automaticRecoveryStatus") != expected_recovery_status
    ):
        raise ResearchScalePromotionError("automatic recovery statistics drift")
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
    statistics = {
        "objectPassRate": _rate_statistic(
            object_pass_numerator, object_pass_denominator
        ),
        "illustratedRate": illustrated_statistic,
        "automaticRecoveryRate": recovery_statistic,
        "firstPassRate": _rate_statistic(first_pass_lane_count, len(carriers)),
        "discardRate": _rate_statistic(
            discarded_count, object_pass_denominator
        ),
        "quotaAttainmentByCarrier": [
            {
                "carrier": carrier,
                **_rate_statistic(
                    int(row["qualifiedCount"]),
                    int(row["targetCount"]),
                ),
            }
            for carrier, row in zip(carriers, promotion_counts, strict=True)
        ],
    }
    try:
        _assert_m100_video_popularity(
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
            f"{_VIDEO_POPULARITY_BLOCKER}: release video evidence is unreadable: {exc}"
        ) from exc
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
        "targetScale": "M100",
        "carrierCounts": promotion_counts,
        "statistics": statistics,
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
        "automaticRecoveryStatus": str(
            fault_evidence["automaticRecoveryStatus"]
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
        "m1000Eligible": True,
        "recordedAt": datetime.now(timezone.utc).isoformat(),
    }
    assert_valid(
        document,
        "release",
        "research_scale_promotion",
        label="research M100 promotion",
    )
    path = (
        output_root
        / "data/release-promotions"
        / release_id
        / promotion_id
        / "research-m100.json"
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ResearchScalePromotionError(
            f"append-only promotion already exists: {path.parent}"
        ) from exc
    write_json(path, document)
    return document, path


__all__ = [
    "ResearchScalePromotionError",
    "write_research_scale_promotion",
]
