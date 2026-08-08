"""Cumulative identity and count proof for campaign scale evidence."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.identity import parse_execution_id
from content.release.canonical.campaign_scale_contract import (
    CARRIERS,
    CampaignScaleEvidenceError,
    _resolve_ref,
    _timestamp,
    _validated,
    campaign_source_revision,
)
from content.release.canonical.campaign_scale_lane_evidence import (
    validate_campaign_lane_evidence,
)
from content.release.canonical.object_transaction_contract import _read_json
from content.release.canonical.release_header import validate_release_header
from content.release.canonical.research_scale_predecessor import (
    ResearchScalePredecessorError,
    load_predecessor_promotion,
)
from core.release_layout import payload_digest, payload_file

SCALE_INTENTS = {"M100": "m100", "M1000": "m1000", "M10000": "m10000"}
WALL_CLOCK_BUDGET_SECONDS = {"M100": None, "M1000": 259200, "M10000": 604800}


def release_refs_by_carrier(release: Path) -> dict[str, set[str]]:
    desired = _validated(
        payload_file(release, "desired_state.json"),
        "release",
        "release_desired_state",
        label=f"research release desired state:{release.name}",
    )
    refs = desired.get("desiredRefs")
    if not isinstance(refs, Mapping):
        raise CampaignScaleEvidenceError("release desiredRefs are invalid")
    result = {carrier: set() for carrier in CARRIERS}
    result["homepage"] = {f"entities/{str(ref).strip('/')}" for ref in refs["entities"]}
    for raw_ref in refs["posts"]:
        normalized = str(raw_ref).strip("/")
        carrier = normalized.split("/", 1)[0]
        if carrier not in {"article", "image", "video"}:
            raise CampaignScaleEvidenceError(
                f"release post ref has unsupported scale carrier: {raw_ref}"
            )
        result[carrier].add(f"posts/{normalized}")
    return result


def scale_context(
    *,
    target_scale: str,
    predecessor_promotion_path: Path | None,
    plan: Mapping[str, Any],
    header: Mapping[str, Any],
    release_root: Path,
    output_root: Path,
) -> tuple[str, dict[str, Any] | None, dict[str, int], list[str], list[str], dict[str, set[str]]]:
    scale = str(target_scale or "").strip().upper()
    if scale not in SCALE_INTENTS:
        raise CampaignScaleEvidenceError(f"unsupported campaign scale: {scale}")
    source_revision = campaign_source_revision(plan)
    if (
        header.get("sourceRevision") != source_revision
        or header.get("sourceDigest") != plan.get("sourceDigest")
        or header.get("entityCatalogDigest") != plan.get("entityCatalogDigest")
    ):
        raise CampaignScaleEvidenceError("release source identity differs from campaign plan")
    try:
        predecessor, carried_counts = load_predecessor_promotion(
            predecessor_promotion_path,
            target_scale=scale,
            source_revision=source_revision,
            source_digest=str(plan["sourceDigest"]),
            entity_catalog_digest=str(plan["entityCatalogDigest"]),
            output_root=output_root,
        )
    except ResearchScalePredecessorError as exc:
        raise CampaignScaleEvidenceError(str(exc)) from exc
    current_ids = {str(plan["executionIds"][carrier]) for carrier in CARRIERS}
    predecessor_ids: set[str] = set()
    predecessor_refs = {carrier: set() for carrier in CARRIERS}
    if predecessor is not None:
        if predecessor["releaseId"] == header.get("releaseId"):
            raise CampaignScaleEvidenceError("cumulative scale requires a new releaseId")
        predecessor_release = release_root / str(predecessor["releaseId"])
        predecessor_header = _validated(
            payload_file(predecessor_release, "release.json"),
            "release",
            "release_header",
            label=f"predecessor research release:{predecessor['releaseId']}",
        )
        validate_release_header(predecessor_header, label="predecessor research release")
        predecessor_source_digests = predecessor_header.get("sourceDigests")
        if (
            payload_digest(predecessor_release) != predecessor["manifestDigest"]
            or predecessor_header.get("sourceRevision") != source_revision
            or predecessor_header.get("sourceDigest") != plan.get("sourceDigest")
            or predecessor_header.get("entityCatalogDigest")
            != plan.get("entityCatalogDigest")
            or not isinstance(predecessor_source_digests, list)
            or len(predecessor_source_digests) != 1
            or predecessor_source_digests[0].get("digest")
            != plan.get("sourceDigest")
        ):
            raise CampaignScaleEvidenceError("predecessor release identity drift")
        predecessor_ids = {str(value) for value in predecessor_header["executionIds"]}
        predecessor_refs = release_refs_by_carrier(predecessor_release)
        if any(
            len(predecessor_refs[carrier]) != carried_counts[carrier]
            for carrier in CARRIERS
        ):
            raise CampaignScaleEvidenceError("predecessor unique object count drift")
    release_ids = {str(value) for value in header.get("executionIds") or []}
    if current_ids & predecessor_ids or release_ids != current_ids | predecessor_ids:
        raise CampaignScaleEvidenceError(
            "release executionIds must equal predecessor carried plus current four lanes"
        )
    return (
        scale,
        predecessor,
        carried_counts,
        sorted(predecessor_ids),
        sorted(release_ids),
        predecessor_refs,
    )


def validate_cumulative_lanes(
    *,
    campaign: Mapping[str, Any],
    plan: Mapping[str, Any],
    admission: Mapping[str, Any],
    target_scale: str,
    predecessor_counts: Mapping[str, int],
    predecessor_refs: Mapping[str, set[str]],
    output_root: Path,
) -> dict[str, list[str]]:
    carrier_admission = {
        str(row.get("carrier")): row
        for row in admission.get("carrierCounts") or []
        if isinstance(row, Mapping)
    }
    lanes = {
        str(row.get("carrier")): row
        for row in campaign.get("lanes") or []
        if isinstance(row, Mapping)
    }
    if set(carrier_admission) != set(CARRIERS) or set(lanes) != set(CARRIERS):
        raise CampaignScaleEvidenceError("campaign cumulative carrier evidence is incomplete")
    projected_admission = {
        "carrierCounts": [
            {
                **dict(carrier_admission[carrier]),
                "objectCount": int(lanes[carrier]["newFinalizedCount"]),
                "researchAcceptedCount": int(lanes[carrier]["researchAcceptedCount"]),
            }
            for carrier in CARRIERS
        ]
    }
    refs_by_lane = validate_campaign_lane_evidence(
        campaign=campaign,
        plan=plan,
        admission=projected_admission,
        output_root=output_root,
    )
    for carrier in CARRIERS:
        lane = lanes[carrier]
        row = carrier_admission[carrier]
        refs = refs_by_lane[carrier]
        carried_count = predecessor_counts[carrier]
        if (
            parse_execution_id(str(lane["executionId"])).intent
            != SCALE_INTENTS[target_scale]
            or set(refs) & predecessor_refs[carrier]
            or int(lane["researchAcceptedCount"]) != len(refs)
            or int(lane["predecessorCarriedCount"]) != carried_count
            or int(lane["newFinalizedCount"]) != len(refs)
            or int(lane["totalUniqueFinalizedCount"])
            != carried_count + len(refs)
            or int(row.get("objectCount") or 0) != carried_count + len(refs)
            or int(row.get("researchAcceptedCount") or 0)
            != carried_count + len(refs)
        ):
            raise CampaignScaleEvidenceError(
                f"{carrier} campaign cumulative count/identity drift"
            )
    return refs_by_lane


def scale_timing_fields(
    *,
    target_scale: str,
    plan: Mapping[str, Any],
    predecessor_promotion_path: Path | None,
    resource: Mapping[str, Any],
) -> dict[str, Any]:
    if target_scale not in WALL_CLOCK_BUDGET_SECONDS:
        raise CampaignScaleEvidenceError(f"unsupported campaign scale: {target_scale}")
    if target_scale == "M100":
        started_raw = plan.get("frozenAt")
    else:
        if predecessor_promotion_path is None:
            raise CampaignScaleEvidenceError(
                "DATA.SCALE.ATTAINMENT_TIMING_BLOCKED: predecessor promotion is missing"
            )
        started_raw = _read_json(predecessor_promotion_path).get("recordedAt")
    completed_raw = resource.get("terminalResidualSampleAt")
    started = _timestamp(started_raw, label=f"{target_scale} scaleStartedAt")
    completed = _timestamp(completed_raw, label=f"{target_scale} scaleCompletedAt")
    wall_clock_seconds = int((completed - started).total_seconds())
    if wall_clock_seconds < 0:
        raise CampaignScaleEvidenceError(
            "DATA.SCALE.ATTAINMENT_TIMING_BLOCKED: scale completed before it started"
        )
    budget = WALL_CLOCK_BUDGET_SECONDS[target_scale]
    if budget is not None and wall_clock_seconds > budget:
        code = (
            "DATA.SCALE.M10000_WALL_CLOCK_BUDGET_EXCEEDED"
            if target_scale == "M10000"
            else "DATA.SCALE.ATTAINMENT_SHORTFALL"
        )
        raise CampaignScaleEvidenceError(
            f"{code}: {target_scale} wall-clock {wall_clock_seconds}s exceeds {budget}s"
        )
    return {
        "scaleStartedAt": started.isoformat(),
        "scaleCompletedAt": completed.isoformat(),
        "wallClockBudgetSeconds": budget,
        "wallClockSeconds": wall_clock_seconds,
    }


def validate_recorded_scale_context(
    *,
    campaign: Mapping[str, Any],
    plan: Mapping[str, Any],
    header: Mapping[str, Any],
    release_root: Path,
    output_root: Path,
) -> tuple[str, dict[str, int], dict[str, set[str]], Path | None]:
    predecessor_document = campaign.get("predecessorPromotion")
    predecessor_path = (
        _resolve_ref(
            str(predecessor_document["receiptRef"]),
            output_root=output_root,
            label="predecessor promotion ref",
        )
        if isinstance(predecessor_document, Mapping)
        else None
    )
    (
        target_scale,
        expected_predecessor,
        predecessor_counts,
        predecessor_execution_ids,
        release_execution_ids,
        predecessor_refs,
    ) = scale_context(
        target_scale=str(campaign.get("targetScale") or ""),
        predecessor_promotion_path=predecessor_path,
        plan=plan,
        header=header,
        release_root=release_root,
        output_root=output_root,
    )
    if (
        predecessor_document != expected_predecessor
        or campaign.get("predecessorCarriedExecutionIds")
        != predecessor_execution_ids
        or campaign.get("releaseExecutionIds") != release_execution_ids
    ):
        raise CampaignScaleEvidenceError("campaign predecessor/release identity drift")
    return target_scale, predecessor_counts, predecessor_refs, predecessor_path


__all__ = [
    "SCALE_INTENTS",
    "release_refs_by_carrier",
    "scale_context",
    "scale_timing_fields",
    "validate_cumulative_lanes",
    "validate_recorded_scale_context",
]
