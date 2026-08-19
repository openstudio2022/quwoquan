"""Canonical aggregate evidence for four-lane research scale promotion."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.identity import parse_execution_id
from content.execution.planning.semantic_preflight_admission import (
    bind_semantic_preflight_receipt,
    validate_semantic_preflight_binding,
)
from content.execution.preflight.selection import (
    CALIBRATION_SEMANTIC_SELECTION_ID,
)
from content.execution.scale.semantic_promotion import (
    ScaleSemanticPromotionError,
    build_scale_semantic_calibration,
)
from content.release.canonical import campaign_scale_object_closure as object_closure
from content.release.canonical.campaign_scale_contract import (
    CARRIERS,
    CampaignScaleEvidenceError,
    _execution_chain,
    _file_sha256,
    _load_plan,
    _resolve_ref,
    _safe_ref,
    _validated,
    _verify_evidence_digest,
    _write_create_once,
    campaign_source_revision,
)
from content.release.canonical.campaign_scale_cumulative import (
    SCALE_INTENTS,
    release_refs_by_carrier,
    scale_context,
    validate_cumulative_lanes,
    validate_recorded_scale_context,
)
from content.release.canonical.campaign_scale_diagnostics import (
    derive_runtime_diagnostic_fields,
    load_campaign_diagnostics,
)
from content.release.canonical.campaign_scale_source_pool import (
    campaign_source_pool_fields,
    validate_recorded_source_pool_fields,
)
from content.release.canonical.fault_injection_evidence import (
    write_fault_injection_evidence,
)
from content.release.canonical.release_header import validate_release_header
from content.release.canonical.resource_soak_evidence import (
    write_resource_soak_evidence,
)
from core.release_layout import payload_digest, payload_file


def write_campaign_scale_evidence(
    *,
    evidence_id: str,
    release_id: str,
    campaign_plan_path: Path,
    runtime_session_path: Path | None,
    calibration_preflight_receipt_path: Path,
    tasks_root: Path,
    release_root: Path,
    output_root: Path,
) -> tuple[dict[str, Any], Path]:
    """Derive the sole promotion evidence from frozen canonical truth sources."""

    plan = _load_plan(campaign_plan_path)
    source_revision = campaign_source_revision(plan)
    try:
        calibration_preflight = bind_semantic_preflight_receipt(
            calibration_preflight_receipt_path,
            semantic_selection_id=CALIBRATION_SEMANTIC_SELECTION_ID,
            output_root=output_root,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise CampaignScaleEvidenceError(
            f"Sol calibration preflight receipt is not promotable: {exc}"
        ) from exc
    evidence_root = (
        campaign_scale_evidence_root(output_root=output_root)
        / release_id
        / evidence_id
    )
    release = release_root / release_id
    header = _validated(
        payload_file(release, "release.json"),
        "release",
        "release_header",
        label=f"research release header:{release_id}",
    )
    validate_release_header(header, label=f"research release header:{release_id}")
    admission_path = payload_file(release, "asset_admission.json")
    admission = _validated(
        admission_path,
        "release",
        "release_asset_admission",
        label=f"research release asset admission:{release_id}",
    )
    manifest_digest = payload_digest(release)
    if (
        header.get("releaseId") != release_id
        or admission.get("releaseId") != release_id
        or header.get("releaseClass") != "research"
        or admission.get("releaseClass") != "research"
        or header.get("productLifecycleState") != "research"
        or admission.get("productLifecycleState") != "research"
    ):
        raise CampaignScaleEvidenceError("campaign evidence requires one research release")
    source_digests = header.get("sourceDigests")
    if (
        not isinstance(source_digests, list)
        or len(source_digests) != 1
        or not isinstance(source_digests[0], Mapping)
        or source_digests[0].get("digest") != plan.get("sourceDigest")
    ):
        raise CampaignScaleEvidenceError("release sourceDigest differs from campaign plan")
    current_execution_ids = [str(plan["executionIds"][carrier]) for carrier in CARRIERS]
    if set(header.get("executionIds") or []) != set(current_execution_ids):
        raise CampaignScaleEvidenceError("release executionIds differ from exact campaign lanes")
    carrier_admission = {
        str(row.get("carrier")): row
        for row in admission.get("carrierCounts") or []
        if isinstance(row, Mapping)
    }
    if set(carrier_admission) != set(CARRIERS):
        raise CampaignScaleEvidenceError("release carrierCounts are incomplete")
    lane_rows: list[dict[str, Any]] = []
    refs_by_lane: dict[str, list[str]] = {}
    for carrier in CARRIERS:
        execution_id = str(plan["executionIds"][carrier])
        identity = parse_execution_id(execution_id)
        if identity.intent != "m100" or identity.phase.value != "scale":
            raise CampaignScaleEvidenceError(f"{carrier} is not one M100 scale execution")
        chain = _execution_chain(
            execution_id=execution_id,
            carrier=carrier,
            plan=plan,
            tasks_root=tasks_root,
        )
        receipt_path = campaign_plan_path.parent / "receipts" / f"{carrier}-publish.json"
        receipt = _validated(
            receipt_path,
            "execution",
            "content_campaign_lane_receipt",
            label=f"campaign {carrier} publish receipt",
        )
        publish_path = tasks_root / execution_id / "publish_ref.json"
        publish = _validated(
            publish_path,
            "execution",
            "publish_ref",
            label=f"execution publish_ref:{execution_id}",
        )
        if (
            receipt.get("rootExecutionId") != plan.get("rootExecutionId")
            or receipt.get("executionId") != execution_id
            or receipt.get("carrier") != carrier
            or receipt.get("phase") != "publish"
            or receipt.get("status") not in {"finalized", "partial"}
            or publish.get("executionId") != execution_id
        ):
            raise CampaignScaleEvidenceError(f"{carrier} publish receipt identity drift")
        refs = object_closure.canonical_lane_refs(carrier, publish)
        if len(refs) != int(receipt["finalizedCount"]):
            raise CampaignScaleEvidenceError(f"{carrier} publish closure count drift")
        refs_by_lane[carrier] = refs
        admission_row = carrier_admission[carrier]
        if int(admission_row.get("objectCount") or 0) != len(refs):
            raise CampaignScaleEvidenceError(f"{carrier} release object count drift")
        calibration_ref = min(refs)
        try:
            semantic_calibration = build_scale_semantic_calibration(
                execution_id=execution_id,
                carrier=carrier,
                execution_manifest_path=(
                    tasks_root / execution_id / "execution_manifest.json"
                ),
                object_root=tasks_root / execution_id / calibration_ref,
                published_refs=refs,
                accepted_object_count=int(
                    admission_row.get("researchAcceptedCount") or 0
                ),
                output_root=output_root,
            )
        except ScaleSemanticPromotionError as exc:
            raise CampaignScaleEvidenceError(str(exc)) from exc
        lane_rows.append(
            {
                "carrier": carrier,
                "executionId": execution_id,
                "retryChain": chain,
                "publishReceiptRef": _safe_ref(
                    receipt_path,
                    output_root=output_root,
                    label=f"{carrier} publish receipt",
                ),
                "publishReceiptSha256": _file_sha256(receipt_path),
                "executionPublishRef": _safe_ref(
                    publish_path,
                    output_root=output_root,
                    label=f"{carrier} execution publish_ref",
                ),
                "executionPublishSha256": _file_sha256(publish_path),
                "finalizedCount": len(refs),
                "researchAcceptedCount": int(
                    admission_row.get("researchAcceptedCount") or 0
                ),
                "semanticCalibration": semantic_calibration,
            }
        )
    duplicate_publish_refs = sum(
        max(0, count - 1)
        for count in Counter(ref for refs in refs_by_lane.values() for ref in refs).values()
    )
    wrong_lane_refs = sum(
        ref.split("/", 2)[1] != carrier
        for carrier, refs in refs_by_lane.items()
        if carrier != "homepage"
        for ref in refs
    )
    cross_lane_write_count = duplicate_publish_refs + wrong_lane_refs
    duplicate_asset_count = object_closure.duplicate_asset_count(admission)
    published_closure = {
        ref for lane_refs in refs_by_lane.values() for ref in lane_refs
    }
    admission_object_refs = {
        str(row.get("objectRef") or "")
        for row in admission.get("assets") or []
        if isinstance(row, Mapping)
        and str(row.get("objectRef") or "").startswith(("entities/", "posts/"))
    }
    if not admission_object_refs.issubset(published_closure):
        raise CampaignScaleEvidenceError(
            "release asset admission references objects outside campaign publish closure"
        )
    article_coverage = admission.get("articleMediaCoverage")
    illustrated_rate = float(
        article_coverage.get("illustratedRate")
        if isinstance(article_coverage, Mapping)
        else 0.0
    )
    passed = duplicate_asset_count == 0 and cross_lane_write_count == 0
    diagnostic_fields = derive_runtime_diagnostic_fields(
        evidence_id=evidence_id,
        runtime_session_path=runtime_session_path,
        campaign_plan_path=campaign_plan_path,
        tasks_root=tasks_root,
        release=release,
        output_root=output_root,
        evidence_root=evidence_root,
        target_scale=target_scale,
        predecessor_promotion_path=predecessor_promotion_path,
    )
    stable = {
        "schema": "quwoquan_data.campaign_scale_evidence",
        "evidenceId": evidence_id,
        "rootExecutionId": plan["rootExecutionId"],
        "status": "passed" if passed else "failed",
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
        "sourceRevision": source_revision,
        "sourceDigest": plan["sourceDigest"],
        "entityCatalogDigest": plan["entityCatalogDigest"],
        "campaignPlanRef": _safe_ref(campaign_plan_path, output_root=output_root, label="campaign plan"),
        "campaignPlanDigest": plan["planDigest"],
        "calibrationPreflightReceipt": calibration_preflight,
        "releaseAssetAdmissionRef": _safe_ref(
            admission_path,
            output_root=output_root,
            label="release asset admission",
        ),
        "releaseAssetAdmissionSha256": _file_sha256(admission_path),
        "lanes": lane_rows,
        "duplicateAssetCount": duplicate_asset_count,
        "crossLaneWriteCount": cross_lane_write_count,
        "articleIllustratedRate": illustrated_rate,
        **diagnostic_fields,
    }
    return _write_create_once(
        path=evidence_root / "campaign-scale.json",
        stable=stable,
        schema_name="campaign_scale_evidence",
    )


def load_campaign_scale_evidence(
    path: Path,
    *,
    output_root: Path,
    diagnostics_required: bool = False,
) -> tuple[
    dict[str, Any], dict[str, Any] | None, dict[str, Any] | None
]:
    """Load exact promotion closure plus optional runtime diagnostics."""
    _safe_ref(path, output_root=output_root, label="canonical campaign scale evidence")
    campaign = _validated(
        path,
        "release",
        "campaign_scale_evidence",
        label="canonical campaign scale evidence",
    )
    _verify_evidence_digest(campaign, label="campaign scale")
    plan_path = _resolve_ref(
        str(campaign["campaignPlanRef"]),
        output_root=output_root,
        label="campaign plan ref",
    )
    admission_path = _resolve_ref(
        str(campaign["releaseAssetAdmissionRef"]),
        output_root=output_root,
        label="release asset admission ref",
    )
    plan = _load_plan(plan_path)
    calibration_preflight = campaign.get("calibrationPreflightReceipt")
    if not isinstance(calibration_preflight, Mapping):
        raise CampaignScaleEvidenceError(
            "campaign Sol calibration preflight receipt is missing"
        )
    try:
        validate_semantic_preflight_binding(
            calibration_preflight,
            semantic_selection_id=CALIBRATION_SEMANTIC_SELECTION_ID,
            output_root=output_root,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise CampaignScaleEvidenceError(
            f"bound Sol calibration preflight receipt is invalid: {exc}"
        ) from exc
    admission = _validated(
        admission_path,
        "release",
        "release_asset_admission",
        label="bound release asset admission",
    )
    release_id = str(campaign.get("releaseId") or "")
    if len(Path(release_id).parts) != 1 or release_id in {"", ".", ".."}:
        raise CampaignScaleEvidenceError("campaign releaseId is unsafe")
    release = output_root / "data/releases" / release_id
    if admission_path.resolve() != payload_file(release, "asset_admission.json").resolve():
        raise CampaignScaleEvidenceError("campaign admission ref is non-canonical")
    header = _validated(
        payload_file(release, "release.json"),
        "release",
        "release_header",
        label=f"bound research release header:{release_id}",
    )
    validate_release_header(header, label=f"bound research release header:{release_id}")
    if (
        campaign.get("manifestDigest") != payload_digest(release)
        or plan.get("planDigest") != campaign.get("campaignPlanDigest")
        or _file_sha256(admission_path)
        != campaign.get("releaseAssetAdmissionSha256")
    ):
        raise CampaignScaleEvidenceError("campaign immutable source digest drift")
    if (
        header.get("releaseId") != release_id
        or admission.get("releaseId") != release_id
        or header.get("releaseClass") != "research"
        or admission.get("releaseClass") != "research"
        or set(header.get("executionIds") or [])
        != set(plan.get("executionIds", {}).values())
        or not isinstance(release_source_digests, list)
        or len(release_source_digests) != 1
        or release_source_digests[0].get("digest") != plan.get("sourceDigest")
    ):
        raise CampaignScaleEvidenceError("campaign release identity drift")
    (
        target_scale,
        predecessor_counts,
        predecessor_refs,
        predecessor_path,
    ) = validate_recorded_scale_context(
        campaign=campaign,
        plan=plan,
        header=header,
        release_root=output_root / "data/releases",
        output_root=output_root,
    )
    validate_recorded_source_pool_fields(
        campaign=campaign,
        plan=plan,
        campaign_plan_path=plan_path,
        predecessor_promotion_path=predecessor_path,
        output_root=output_root,
    )
    refs_by_lane = validate_cumulative_lanes(
        campaign=campaign,
        plan=plan,
        admission=admission,
        output_root=output_root,
    )
    duplicate_publish_refs = sum(
        max(0, count - 1)
        for count in Counter(
            ref for refs in refs_by_lane.values() for ref in refs
        ).values()
    )
    wrong_lane_refs = sum(
        ref.split("/", 2)[1] != carrier
        for carrier, refs in refs_by_lane.items()
        if carrier != "homepage"
        for ref in refs
    )
    duplicate_assets = object_closure.duplicate_asset_count(admission)
    published_closure = {ref for refs in refs_by_lane.values() for ref in refs}
    admission_refs = {
        str(row.get("objectRef") or "")
        for row in admission.get("assets") or []
        if isinstance(row, Mapping)
        and str(row.get("objectRef") or "").startswith(("entities/", "posts/"))
    }
    if not admission_refs.issubset(published_closure):
        raise CampaignScaleEvidenceError("campaign admission object closure drift")
    article_coverage = admission.get("articleMediaCoverage")
    illustrated_rate = float(
        article_coverage.get("illustratedRate")
        if isinstance(article_coverage, Mapping)
        else 0.0
    )
    derived_campaign_fields = {
        "status": (
            "passed"
            if duplicate_assets == 0
            and duplicate_publish_refs + wrong_lane_refs == 0
            else "failed"
        ),
        "duplicateAssetCount": duplicate_assets,
        "crossLaneWriteCount": duplicate_publish_refs + wrong_lane_refs,
        "articleIllustratedRate": illustrated_rate,
    }
    identity_keys = (
        "rootExecutionId",
        "sourceRevision",
        "sourceDigest",
        "entityCatalogDigest",
    )
    plan_execution_ids = plan.get("executionIds")
    campaign_execution_ids = {
        str(lane.get("carrier")): str(lane.get("executionId"))
        for lane in campaign.get("lanes") or []
        if isinstance(lane, Mapping)
    }
    if (
        any(
            campaign.get(key) != value
            for key, value in derived_campaign_fields.items()
        )
        or any(plan.get(key) != campaign.get(key) for key in identity_keys)
        or campaign_execution_ids != plan_execution_ids
    ):
        raise CampaignScaleEvidenceError("campaign exact promotion closure drift")
    try:
        resource, fault = load_campaign_diagnostics(
            campaign=campaign,
            campaign_path=path,
            plan=plan,
            plan_path=plan_path,
            predecessor_path=predecessor_path,
            release=release,
            output_root=output_root,
        )
        if diagnostics_required and resource is None and fault is None:
            raise CampaignScaleEvidenceError(
                "campaign runtime diagnostics are unavailable"
            )
    except (CampaignScaleEvidenceError, OSError, TypeError, ValueError):
        if diagnostics_required:
            raise
        resource, fault = None, None
    return campaign, resource, fault


__all__ = ["CampaignScaleEvidenceError", "campaign_source_revision", "load_campaign_scale_evidence", "write_campaign_scale_evidence", "write_fault_injection_evidence", "write_resource_soak_evidence"]
