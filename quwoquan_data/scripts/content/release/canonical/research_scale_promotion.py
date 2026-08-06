"""Write the create-once research M100 promotion receipt."""
from __future__ import annotations

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
    if (
        evidence.get("status") != "passed"
        or resource_evidence.get("status") != "passed"
        or fault_evidence.get("status") != "passed"
    ):
        raise ResearchScalePromotionError(
            "canonical campaign scale/resource/fault evidence is not passed"
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
    carrier_counts = {
        str(row.get("carrier") or ""): int(row.get("researchAcceptedCount") or 0)
        for row in carrier_rows
        if isinstance(row, Mapping)
    }
    expected_carriers = {"homepage", "article", "image", "video"}
    targets = dict(policy.m100_targets)
    if set(carrier_counts) != expected_carriers or any(
        carrier_counts.get(carrier, 0) < targets[carrier]
        for carrier in expected_carriers
    ):
        raise ResearchScalePromotionError(
            "M100 requires homepage/article/image >= 100 and video >= 50"
        )
    article_coverage = admission.get("articleMediaCoverage")
    illustrated_rate = float(
        article_coverage.get("illustratedRate")
        if isinstance(article_coverage, Mapping)
        else 0
    )
    if illustrated_rate != float(evidence.get("articleIllustratedRate") or 0.0):
        raise ResearchScalePromotionError("campaign article coverage evidence drift")
    duplicate_count = evidence["duplicateAssetCount"]
    cross_lane_count = evidence["crossLaneWriteCount"]
    if (
        not isinstance(duplicate_count, int)
        or isinstance(duplicate_count, bool)
        or not isinstance(cross_lane_count, int)
        or isinstance(cross_lane_count, bool)
    ):
        raise ResearchScalePromotionError("campaign write counters must be integers")
    resource_isolation = resource_evidence.get("status") == "passed"
    raw_recovery_rate = fault_evidence["automaticRecoveryRate"]
    if not isinstance(raw_recovery_rate, (int, float)) or isinstance(
        raw_recovery_rate, bool
    ):
        raise ResearchScalePromotionError("automaticRecoveryRate must be numeric")
    recovery_rate = float(raw_recovery_rate)
    if duplicate_count or cross_lane_count:
        raise ResearchScalePromotionError(
            "M100 duplicateAssetCount and crossLaneWriteCount must both be zero"
        )
    if illustrated_rate < policy.minimum_illustrated_rate:
        raise ResearchScalePromotionError("M100 article illustrated rate is below policy")
    if not resource_isolation:
        raise ResearchScalePromotionError("M100 resource isolation evidence is missing")
    if (
        int(resource_evidence.get("fourLaneLongestContinuousOverlapSeconds") or 0)
        < MIN_SOAK_SECONDS
        or not resource_evidence.get("allSemanticJobsTerminalAt")
        or not resource_evidence.get("terminalResidualMeasuredAfterAllJobs")
    ):
        raise ResearchScalePromotionError(
            "M100 requires 60 continuous four-lane minutes and post-terminal cleanup"
        )
    if (
        fault_evidence.get("automaticRecoveryStatus") != "MEASURED"
        or int(fault_evidence.get("recoveryEligibleCount") or 0) < 20
        or int(fault_evidence.get("automaticRecoveredCount") or 0) < 19
    ):
        raise ResearchScalePromotionError(
            "M100 recovery evidence requires 20 eligible and 19 automatic cases"
        )
    if recovery_rate < policy.minimum_automatic_recovery_rate:
        raise ResearchScalePromotionError(
            "M100 automatic recovery rate is below the M1000 promotion threshold"
        )
    try:
        _assert_m100_video_popularity(
            release,
            expected_video_count=carrier_counts["video"],
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
        "carrierCounts": [
            {"carrier": carrier, "researchAcceptedCount": carrier_counts[carrier]}
            for carrier in ("homepage", "article", "image", "video")
        ],
        "duplicateAssetCount": 0,
        "crossLaneWriteCount": 0,
        "articleIllustratedRate": illustrated_rate,
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
        "recoveryEligibleCount": int(fault_evidence["recoveryEligibleCount"]),
        "automaticRecoveredCount": int(
            fault_evidence["automaticRecoveredCount"]
        ),
        "automaticRecoveryRate": recovery_rate,
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
