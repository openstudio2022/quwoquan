"""Exact lane binding checks for canonical campaign scale evidence."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.scale_semantic_promotion import (
    ScaleSemanticPromotionError,
    validate_scale_semantic_calibration,
)
from content.release.canonical import campaign_scale_object_closure as object_closure
from content.release.canonical.campaign_scale_contract import (
    CampaignScaleEvidenceError,
    _execution_chain,
    _file_sha256,
    _resolve_ref,
    _validated,
)


def validate_campaign_lane_evidence(
    *,
    campaign: Mapping[str, Any],
    plan: Mapping[str, Any],
    admission: Mapping[str, Any],
    output_root: Path,
) -> dict[str, list[str]]:
    """Rebind every lane to its exact publish receipt and release admission."""

    carrier_admission = {
        str(row.get("carrier")): row
        for row in admission.get("carrierCounts") or []
        if isinstance(row, Mapping)
    }
    refs_by_lane: dict[str, list[str]] = {}
    for lane in campaign.get("lanes") or []:
        if not isinstance(lane, Mapping):
            raise CampaignScaleEvidenceError("campaign lane evidence is invalid")
        receipt_path = _resolve_ref(
            str(lane["publishReceiptRef"]),
            output_root=output_root,
            label=f"{lane['carrier']} publish receipt ref",
        )
        publish_path = _resolve_ref(
            str(lane["executionPublishRef"]),
            output_root=output_root,
            label=f"{lane['carrier']} execution publish ref",
        )
        publish = _validated(
            publish_path,
            "execution",
            "publish_ref",
            label=f"{lane['carrier']} bound execution publish ref",
        )
        receipt = _validated(
            receipt_path,
            "execution",
            "content_campaign_lane_receipt",
            label=f"{lane['carrier']} bound publish receipt",
        )
        if (
            _file_sha256(receipt_path) != lane.get("publishReceiptSha256")
            or _file_sha256(publish_path) != lane.get("executionPublishSha256")
        ):
            raise CampaignScaleEvidenceError(
                f"{lane['carrier']} campaign lane evidence file digest drift"
            )
        try:
            carrier = str(lane.get("carrier") or "")
            execution_id = str(lane.get("executionId") or "")
            admission_row = carrier_admission.get(carrier)
            if not isinstance(admission_row, Mapping):
                raise CampaignScaleEvidenceError(
                    f"{carrier} release carrier admission is missing"
                )
            refs = object_closure.canonical_lane_refs(carrier, publish)
            refs_by_lane[carrier] = refs
            retry_chain = _execution_chain(
                execution_id=execution_id,
                carrier=carrier,
                plan=plan,
                tasks_root=output_root / "data/tasks",
            )
            if (
                receipt.get("rootExecutionId") != plan.get("rootExecutionId")
                or receipt.get("executionId") != execution_id
                or receipt.get("carrier") != carrier
                or receipt.get("phase") != "publish"
                or receipt.get("status") not in {"finalized", "partial"}
                or publish.get("executionId") != execution_id
                or len(refs) != int(receipt.get("finalizedCount") or 0)
                or len(refs) != int(admission_row.get("objectCount") or 0)
                or lane.get("retryChain") != retry_chain
                or int(lane.get("finalizedCount") or 0) != len(refs)
                or int(lane.get("researchAcceptedCount") or 0)
                != int(admission_row.get("researchAcceptedCount") or 0)
            ):
                raise CampaignScaleEvidenceError(
                    f"{carrier} campaign lane derived evidence drift"
                )
            validate_scale_semantic_calibration(
                lane.get("semanticCalibration"),
                execution_id=execution_id,
                carrier=carrier,
                published_refs=refs,
                accepted_object_count=int(
                    admission_row.get("researchAcceptedCount") or 0
                ),
                output_root=output_root,
            )
        except ScaleSemanticPromotionError as exc:
            raise CampaignScaleEvidenceError(str(exc)) from exc
    return refs_by_lane


__all__ = ["validate_campaign_lane_evidence"]
