"""Write create-once cumulative Research scale promotion receipts."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.release.canonical.campaign_scale_evidence import (
    CampaignScaleEvidenceError,
    load_campaign_scale_evidence,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)
from content.release.canonical.research_scale_predecessor import (
    ResearchScalePredecessorError,
    load_predecessor_promotion,
)
from content.release.canonical.research_scale_promotion_acceptance import (
    ResearchScalePromotionAcceptanceError,
    acceptance_binding_fields,
    bind_m1000_alpha_acceptance,
    validate_acceptance_input_mode,
)
from content.release.canonical.research_scale_promotion_diagnostics import (
    project_promotion_diagnostics,
)
from content.release.canonical.research_scale_promotion_release import (
    CARRIERS,
    ResearchMilestoneReleaseError,
    load_research_milestone_release,
)
from content.release.canonical.research_scale_promotion_statistics import (
    article_media_statistics,
    professional_image_source_mix_statistics,
    video_popularity_statistics,
)
from content.release.canonical.research_scale_promotion_statistics import (
    rate_statistic as _rate_statistic,
)
from content.release.canonical.research_scale_video_popularity import (
    VIDEO_POPULARITY_EVIDENCE_ERROR,
    VIDEO_POPULARITY_SIGNALS,
)
from core.io import write_json
from core.paths import OUTPUT_ROOT, RELEASE_ROOT, research_scale_promotions_root
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


def _collect_m100_video_popularity(
    release: Path,
    *,
    expected_video_count: int,
) -> dict[str, Any]:
    return video_popularity_statistics(
        release, expected_video_count=expected_video_count
    )


def _diagnostic_issue(message: object) -> dict[str, list[str]]:
    return {
        "diagnosticIssues": [
            "DATA.DIAGNOSTIC.CAMPAIGN_EVIDENCE_UNAVAILABLE: " + str(message)
        ]
    }


def _merge_diagnostic_issues(
    fields: dict[str, Any], *additional: str
) -> dict[str, Any]:
    issues = [
        str(item)
        for item in fields.pop("diagnosticIssues", [])
        if str(item).strip()
    ]
    issues.extend(str(item) for item in additional if str(item).strip())
    if issues:
        fields["diagnosticIssues"] = list(dict.fromkeys(issues))
    return fields


def _optional_campaign_diagnostics(
    campaign_evidence_path: Path | None,
    *,
    release_id: str,
    manifest_digest: str,
    target_scale: str,
    output_root: Path,
    automatic_recovery_rate_target: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Best-effort projection; no campaign failure can reject a release."""

    if campaign_evidence_path is None:
        return {}, {}
    try:
        evidence, resource_evidence, fault_evidence = load_campaign_scale_evidence(
            campaign_evidence_path,
            output_root=output_root,
            diagnostics_required=False,
        )
        if (
            evidence.get("releaseId") != release_id
            or evidence.get("manifestDigest") != manifest_digest
            or evidence.get("targetScale") != target_scale
        ):
            raise CampaignScaleEvidenceError(
                "campaign diagnostic release identity drift"
            )
        document_fields, statistic_fields = project_promotion_diagnostics(
            target_scale=target_scale,
            evidence=evidence,
            resource_evidence=resource_evidence,
            fault_evidence=fault_evidence,
            automatic_recovery_rate_target=automatic_recovery_rate_target,
        )
        document_fields.update(
            {
                "campaignEvidenceRef": _evidence_ref(
                    campaign_evidence_path, output_root=output_root
                ),
                "campaignEvidenceDigest": str(evidence["evidenceDigest"]),
            }
        )
        source_pool_digest = str(evidence.get("sourcePoolDigest") or "")
        if source_pool_digest.startswith("sha256:"):
            document_fields["campaignSourcePoolDigest"] = source_pool_digest
        predecessor_pool_digests = evidence.get("predecessorSourcePoolDigests")
        if isinstance(predecessor_pool_digests, list):
            document_fields["predecessorSourcePoolDigests"] = list(
                predecessor_pool_digests
            )
        lanes = {
            str(row.get("carrier") or ""): row
            for row in evidence.get("lanes") or []
            if isinstance(row, Mapping)
        }
        if set(lanes) == set(CARRIERS) and all(
            isinstance(lanes[carrier].get("semanticCalibration"), Mapping)
            for carrier in CARRIERS
        ):
            document_fields["semanticCalibrationByLane"] = [
                dict(lanes[carrier]["semanticCalibration"])
                for carrier in CARRIERS
            ]
        failed_issue = (
            "DATA.DIAGNOSTIC.CAMPAIGN_EVIDENCE_FAILED: optional campaign "
            "diagnostic reported failed"
            if evidence.get("status") != "passed"
            else ""
        )
        return _merge_diagnostic_issues(
            document_fields, failed_issue
        ), statistic_fields
    except (
        CampaignScaleEvidenceError,
        KeyError,
        OSError,
        ResearchScalePromotionError,
        TypeError,
        ValueError,
    ) as exc:
        return _diagnostic_issue(exc), {}


def _source_identity_anchor(header: Mapping[str, Any]) -> tuple[str, str, str]:
    identities = header.get("sourceIdentities")
    if not isinstance(identities, list) or not identities:
        raise ResearchScalePromotionError(
            "milestone release source identity set is missing"
        )
    first = identities[0]
    if not isinstance(first, Mapping):
        raise ResearchScalePromotionError(
            "milestone release source identity set is invalid"
        )
    return (
        str(first.get("sourceRevision") or ""),
        str(first.get("sourceDigest") or ""),
        str(first.get("entityCatalogDigest") or ""),
    )


def write_research_scale_promotion(
    *,
    release_id: str,
    promotion_id: str,
    campaign_evidence_path: Path | None = None,
    target_scale: str = "M100",
    predecessor_promotion_path: Path | None = None,
    m100_alpha_readiness_receipt_path: Path | None = None,
    m100_alpha_app_uat_receipt_path: Path | None = None,
    m100_alpha_acceptance_binding_path: Path | None = None,
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
    try:
        validate_acceptance_input_mode(
            target_scale=target_scale,
            predecessor_promotion_path=predecessor_promotion_path,
            readiness_receipt_path=m100_alpha_readiness_receipt_path,
            app_uat_receipt_path=m100_alpha_app_uat_receipt_path,
            binding_path=m100_alpha_acceptance_binding_path,
        )
    except ResearchScalePromotionAcceptanceError as exc:
        raise ResearchScalePromotionError(str(exc)) from exc

    release = release_root / release_id
    try:
        milestone_release = load_research_milestone_release(
            release,
            release_id=release_id,
            target_scale=target_scale,
        )
    except ResearchMilestoneReleaseError as exc:
        raise ResearchScalePromotionError(str(exc)) from exc
    header = milestone_release.header
    admission = milestone_release.admission
    source_revision, source_digest, entity_catalog_digest = (
        _source_identity_anchor(header)
    )
    try:
        predecessor_reference, predecessor_counts = load_predecessor_promotion(
            predecessor_promotion_path,
            target_scale=target_scale,
            source_revision=source_revision,
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
            output_root=output_root,
        )
    except ResearchScalePredecessorError as exc:
        raise ResearchScalePromotionError(str(exc)) from exc
    if (
        predecessor_reference is not None
        and predecessor_reference.get("releaseId") == release_id
    ):
        raise ResearchScalePromotionError(
            "DATA.SCALE.PREDECESSOR_IDENTITY_DRIFT: cumulative milestone "
            "requires a new immutable release"
        )

    promotion_counts: list[dict[str, Any]] = []
    for carrier in CARRIERS:
        accepted = milestone_release.counts[carrier]
        carried = predecessor_counts[carrier]
        if accepted < carried:
            raise ResearchScalePromotionError(
                f"{carrier} cumulative release count regressed below predecessor"
            )
        promotion_counts.append(
            {
                "carrier": carrier,
                "targetCount": milestone_release.targets[carrier],
                "qualifiedCount": accepted,
                "finalizedCount": accepted,
                "predecessorCarriedCount": carried,
                "newFinalizedCount": accepted - carried,
                "totalUniqueFinalizedCount": accepted,
                "selectedCount": accepted,
                "discardedCount": 0,
                "shortfallCount": 0,
                "researchAcceptedCount": accepted,
            }
        )

    policy = load_content_distribution_policy()
    if policy.video_popularity_signals != tuple(
        signal for signal, _field in VIDEO_POPULARITY_SIGNALS
    ):
        raise ResearchScalePromotionError(
            "video popularity policy signals differ from promotion statistics"
        )
    article_count = milestone_release.counts["article"]
    try:
        illustrated_statistic, text_only_statistic = article_media_statistics(
            admission.get("articleMediaCoverage"),
            expected_article_count=article_count,
        )
    except ValueError as exc:
        raise ResearchScalePromotionError(str(exc)) from exc
    video_count = milestone_release.counts["video"]
    try:
        video_popularity = _collect_m100_video_popularity(
            release, expected_video_count=video_count
        )
    except (ObjectTransactionError, OSError, TypeError, ValueError) as exc:
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
    total_count = sum(milestone_release.counts.values())
    statistics: dict[str, Any] = {
        "objectPassRate": _rate_statistic(total_count, total_count),
        "illustratedRate": illustrated_statistic,
        "textOnlyRate": text_only_statistic,
        "videoPopularity": {
            "statistical": policy.video_popularity_statistical,
            "nonBlocking": policy.video_popularity_non_blocking,
            **video_popularity,
        },
        "quotaAttainmentByCarrier": [
            {
                "carrier": carrier,
                **_rate_statistic(
                    milestone_release.counts[carrier],
                    milestone_release.targets[carrier],
                ),
            }
            for carrier in CARRIERS
        ],
    }
    diagnostic_fields, diagnostic_statistics = _optional_campaign_diagnostics(
        campaign_evidence_path,
        release_id=release_id,
        manifest_digest=milestone_release.manifest_digest,
        target_scale=target_scale,
        output_root=output_root,
        automatic_recovery_rate_target=policy.automatic_recovery_rate_target,
    )
    statistics.update(diagnostic_statistics)

    document: dict[str, Any] = {
        "schema": "quwoquan_data.research_scale_promotion",
        "promotionId": promotion_id,
        "releaseId": release_id,
        "releaseClass": "research",
        "productLifecycleState": "research",
        "manifestDigest": milestone_release.manifest_digest,
        "sourceIdentities": list(header["sourceIdentities"]),
        "sourceIdentitySetDigest": str(header["sourceIdentitySetDigest"]),
        "targetScale": target_scale,
        "sourcePoolDigest": str(header["poolDigest"]),
        "carrierCounts": promotion_counts,
        "statistics": statistics,
        "professionalImageSourceMix": professional_image_source_mix_statistics(
            admission
        ),
        "duplicateAssetCount": 0,
        "crossLaneWriteCount": 0,
        **diagnostic_fields,
        "nextScaleEligible": {
            "M100": "M1000",
            "M1000": "M10000",
            "M10000": "COMPLETE",
        }[target_scale],
        "recordedAt": datetime.now(timezone.utc).isoformat(),
    }
    if predecessor_reference is not None:
        document["predecessorPromotion"] = predecessor_reference
    try:
        m100_alpha_acceptance, m100_alpha_acceptance_source = (
            bind_m1000_alpha_acceptance(
                target_scale=target_scale,
                predecessor_promotion_path=predecessor_promotion_path,
                predecessor_reference=predecessor_reference,
                readiness_receipt_path=m100_alpha_readiness_receipt_path,
                app_uat_receipt_path=m100_alpha_app_uat_receipt_path,
                binding_path=m100_alpha_acceptance_binding_path,
                output_root=output_root,
            )
        )
    except ResearchScalePromotionAcceptanceError as exc:
        raise ResearchScalePromotionError(str(exc)) from exc
    if m100_alpha_acceptance is not None:
        document.update(
            acceptance_binding_fields(
                m100_alpha_acceptance, m100_alpha_acceptance_source
            )
        )
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
