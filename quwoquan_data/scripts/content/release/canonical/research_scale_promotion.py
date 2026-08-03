"""Write the create-once research M100 promotion receipt."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from content.release.canonical.object_transaction_contract import _read_json
from core.io import write_json
from core.paths import OUTPUT_ROOT, RELEASE_ROOT
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
    evidence = _read_json(campaign_evidence_path)
    if (
        evidence.get("releaseId") != release_id
        or evidence.get("manifestDigest") != manifest_digest
    ):
        raise ResearchScalePromotionError("campaign evidence release identity drift")
    required_evidence = {
        "duplicateAssetCount",
        "crossLaneWriteCount",
        "resourceIsolationPassed",
        "automaticRecoveryRate",
        "sourceRevision",
        "sourceDigest",
        "entityCatalogDigest",
    }
    if not required_evidence.issubset(evidence):
        raise ResearchScalePromotionError("campaign evidence fields are incomplete")
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
    if set(carrier_counts) != expected_carriers or any(
        count < policy.m100_per_carrier for count in carrier_counts.values()
    ):
        raise ResearchScalePromotionError(
            "M100 requires researchAcceptedCount >= 100 for all four carriers"
        )
    article_coverage = admission.get("articleMediaCoverage")
    illustrated_rate = float(
        article_coverage.get("illustratedRate")
        if isinstance(article_coverage, Mapping)
        else 0
    )
    duplicate_count = evidence["duplicateAssetCount"]
    cross_lane_count = evidence["crossLaneWriteCount"]
    if (
        not isinstance(duplicate_count, int)
        or isinstance(duplicate_count, bool)
        or not isinstance(cross_lane_count, int)
        or isinstance(cross_lane_count, bool)
    ):
        raise ResearchScalePromotionError("campaign write counters must be integers")
    resource_isolation = evidence.get("resourceIsolationPassed") is True
    raw_recovery_rate = evidence["automaticRecoveryRate"]
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
    if recovery_rate < policy.minimum_automatic_recovery_rate:
        raise ResearchScalePromotionError(
            "M100 automatic recovery rate is below the M1000 promotion threshold"
        )
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
        "automaticRecoveryRate": recovery_rate,
        "campaignEvidenceRef": _evidence_ref(
            campaign_evidence_path, output_root=output_root
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
