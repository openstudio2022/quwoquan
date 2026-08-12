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
from content.execution.preflight.selection import CALIBRATION_SEMANTIC_SELECTION_ID
from content.execution.scale.semantic_promotion import (
    ScaleSemanticPromotionError,
    build_scale_semantic_calibration,
)
from content.release.canonical import campaign_scale_object_closure as object_closure
from content.release.canonical import runtime_scale_evidence_binding as runtime_binding
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
    scale_timing_fields,
    validate_cumulative_lanes,
    validate_recorded_scale_context,
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
    _derive_resource_soak_stable,
    write_resource_soak_evidence,
)
from core.paths import campaign_scale_evidence_root
from core.release_layout import payload_digest, payload_file


def write_campaign_scale_evidence(
    *,
    evidence_id: str,
    release_id: str,
    campaign_plan_path: Path,
    runtime_session_path: Path,
    calibration_preflight_receipt_path: Path,
    tasks_root: Path,
    release_root: Path,
    output_root: Path,
    target_scale: str = "M100",
    predecessor_promotion_path: Path | None = None,
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
    session, raw_samples_path, raw_fault_cases_path = (
        runtime_binding.materialize_bound_runtime_inputs(
            runtime_session_path=runtime_session_path, campaign_plan_path=campaign_plan_path,
            evidence_root=evidence_root, output_root=output_root,
        )
    )
    resource, resource_path = write_resource_soak_evidence(
        evidence_id=evidence_id,
        campaign_plan_path=campaign_plan_path,
        raw_samples_path=raw_samples_path,
        tasks_root=tasks_root,
        release_root=release_root / release_id,
        output_root=output_root,
        evidence_root=evidence_root,
    )
    fault, fault_path = write_fault_injection_evidence(
        evidence_id=evidence_id,
        campaign_plan_path=campaign_plan_path,
        raw_cases_path=raw_fault_cases_path,
        tasks_root=tasks_root,
        output_root=output_root,
        evidence_root=evidence_root,
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
    (
        target_scale,
        predecessor_promotion,
        predecessor_counts,
        predecessor_execution_ids,
        release_execution_ids,
        predecessor_refs,
    ) = scale_context(
        target_scale=target_scale,
        predecessor_promotion_path=predecessor_promotion_path,
        plan=plan,
        header=header,
        release_root=release_root,
        output_root=output_root,
    )
    source_pool_fields = campaign_source_pool_fields(
        plan=plan, campaign_plan_path=campaign_plan_path, target_scale=target_scale,
        predecessor_promotion_path=predecessor_promotion_path, output_root=output_root,
    )
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
        if identity.intent != SCALE_INTENTS[target_scale] or identity.phase.value != "scale":
            raise CampaignScaleEvidenceError(
                f"{carrier} is not one {target_scale} scale execution"
            )
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
        carried_count = predecessor_counts[carrier]
        total_count = int(admission_row.get("objectCount") or 0)
        accepted_total = int(admission_row.get("researchAcceptedCount") or 0)
        if (
            set(refs) & predecessor_refs[carrier]
            or accepted_total != total_count
        ):
            raise CampaignScaleEvidenceError(
                f"{carrier} rolling-wave/release cohort closure drift"
            )
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
                accepted_object_count=len(refs),
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
                "researchAcceptedCount": len(refs),
                "predecessorCarriedCount": carried_count,
                "newFinalizedCount": len(refs),
                "totalUniqueFinalizedCount": total_count,
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
    admission_object_refs = {
        str(row.get("objectRef") or "")
        for row in admission.get("assets") or []
        if isinstance(row, Mapping)
        and str(row.get("objectRef") or "").startswith(("entities/", "posts/"))
    }
    release_object_refs = set().union(*release_refs_by_carrier(release).values())
    if not admission_object_refs.issubset(release_object_refs):
        raise CampaignScaleEvidenceError(
            "release asset admission references objects outside release closure"
        )
    article_coverage = admission.get("articleMediaCoverage")
    illustrated_rate = float(
        article_coverage.get("illustratedRate")
        if isinstance(article_coverage, Mapping)
        else 0.0
    )
    passed = duplicate_asset_count == 0 and cross_lane_write_count == 0
    timing_fields = scale_timing_fields(target_scale=target_scale, plan=plan, predecessor_promotion_path=predecessor_promotion_path, resource=resource)
    stable = {
        "schema": "quwoquan_data.campaign_scale_evidence",
        "evidenceId": evidence_id,
        "rootExecutionId": plan["rootExecutionId"],
        **runtime_binding.runtime_binding_fields(
            session, session_path=runtime_session_path, output_root=output_root
        ),
        "status": "passed" if passed else "failed",
        "targetScale": target_scale,
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
        "predecessorCarriedExecutionIds": predecessor_execution_ids,
        "releaseExecutionIds": release_execution_ids,
        **source_pool_fields,
        "lanes": lane_rows,
        "duplicateAssetCount": duplicate_asset_count,
        "crossLaneWriteCount": cross_lane_write_count,
        "articleIllustratedRate": illustrated_rate,
        "fourLaneOverlapDurationSeconds": int(
            resource["fourLaneOverlapDurationSeconds"]
        ),
        "fourLaneLongestContinuousOverlapSeconds": int(
            resource["fourLaneLongestContinuousOverlapSeconds"]
        ),
        "allSemanticJobsTerminalAt": resource["allSemanticJobsTerminalAt"],
        "terminalResidualSampleAt": resource["terminalResidualSampleAt"],
        **timing_fields,
        "resourceSoakEvidenceRef": _safe_ref(
            resource_path,
            output_root=output_root,
            label="resource soak evidence",
        ),
        "resourceSoakEvidenceDigest": resource["evidenceDigest"],
        "faultInjectionEvidenceRef": _safe_ref(
            fault_path,
            output_root=output_root,
            label="fault injection evidence",
        ),
        "faultInjectionEvidenceDigest": fault["evidenceDigest"],
    }
    if predecessor_promotion is not None:
        stable["predecessorPromotion"] = predecessor_promotion
    return _write_create_once(
        path=evidence_root / "campaign-scale.json",
        stable=stable,
        schema_name="campaign_scale_evidence",
    )
def load_campaign_scale_evidence(
    path: Path,
    *,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Load and rebind canonical aggregate/subordinate evidence for promotion."""
    _safe_ref(path, output_root=output_root, label="canonical campaign scale evidence")
    campaign = _validated(
        path,
        "release",
        "campaign_scale_evidence",
        label="canonical campaign scale evidence",
    )
    _verify_evidence_digest(campaign, label="campaign scale")
    resource_path = _resolve_ref(
        str(campaign["resourceSoakEvidenceRef"]),
        output_root=output_root,
        label="resource soak evidence ref",
    )
    fault_path = _resolve_ref(
        str(campaign["faultInjectionEvidenceRef"]),
        output_root=output_root,
        label="fault injection evidence ref",
    )
    resource = _validated(
        resource_path,
        "release",
        "resource_soak_evidence",
        label="canonical resource soak evidence",
    )
    fault = _validated(
        fault_path,
        "release",
        "fault_injection_evidence",
        label="canonical fault injection evidence",
    )
    resource_digest = _verify_evidence_digest(resource, label="resource soak")
    fault_digest = _verify_evidence_digest(fault, label="fault injection")
    raw_samples_path = _resolve_ref(
        str(resource["rawSamplesRef"]),
        output_root=output_root,
        label="resource raw samples ref",
    )
    raw_faults_path = _resolve_ref(
        str(fault["rawCasesRef"]),
        output_root=output_root,
        label="fault raw cases ref",
    )
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
            require_fresh=False,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise CampaignScaleEvidenceError(
            f"bound Sol calibration preflight receipt is invalid: {exc}"
        ) from exc
    runtime_session_path = _resolve_ref(
        str(campaign["runtimeSessionRef"]),
        output_root=output_root,
        label="runtime session ref",
    )
    session, bound_samples_path, bound_faults_path = runtime_binding.materialize_bound_runtime_inputs(
        runtime_session_path=runtime_session_path,
        campaign_plan_path=plan_path,
        evidence_root=path.parent,
        output_root=output_root,
    )
    if (
        raw_samples_path.resolve() != bound_samples_path.resolve()
        or raw_faults_path.resolve() != bound_faults_path.resolve()
    ):
        raise CampaignScaleEvidenceError("campaign runtime input projection drift")
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
    if campaign.get("manifestDigest") != payload_digest(release):
        raise CampaignScaleEvidenceError("campaign release manifest digest drift")
    if (
        header.get("releaseId") != release_id
        or admission.get("releaseId") != release_id
        or header.get("releaseClass") != "research"
        or admission.get("releaseClass") != "research"
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
        campaign=campaign, plan=plan, campaign_plan_path=plan_path,
        predecessor_promotion_path=predecessor_path, output_root=output_root,
    )
    expected_resource = _derive_resource_soak_stable(
        evidence_id=str(resource["evidenceId"]),
        campaign_plan_path=plan_path,
        raw_samples_path=raw_samples_path,
        tasks_root=output_root / "data/tasks",
        release_root=release,
        output_root=output_root,
    )
    resource_stable = {
        key: value
        for key, value in resource.items()
        if key not in {"recordedAt", "evidenceDigest"}
    }
    if resource_stable != expected_resource:
        raise CampaignScaleEvidenceError("resource soak derived evidence drift")
    if fault_path.name != "fault-injection.json":
        raise CampaignScaleEvidenceError("fault injection evidence path is non-canonical")
    write_fault_injection_evidence(
        evidence_id=str(fault["evidenceId"]),
        campaign_plan_path=plan_path,
        raw_cases_path=raw_faults_path,
        tasks_root=output_root / "data/tasks",
        output_root=output_root,
        evidence_root=fault_path.parent,
    )
    if (
        _file_sha256(raw_samples_path) != resource.get("rawSamplesSha256")
        or _file_sha256(raw_faults_path) != fault.get("rawCasesSha256")
        or plan.get("planDigest") != campaign.get("campaignPlanDigest")
        or _file_sha256(admission_path)
        != campaign.get("releaseAssetAdmissionSha256")
    ):
        raise CampaignScaleEvidenceError("campaign source evidence file digest drift")
    refs_by_lane = validate_cumulative_lanes(
        campaign=campaign,
        plan=plan,
        admission=admission,
        target_scale=target_scale,
        predecessor_counts=predecessor_counts,
        predecessor_refs=predecessor_refs,
        release_refs=release_refs_by_carrier(release),
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
    admission_refs = {
        str(row.get("objectRef") or "") for row in admission.get("assets") or []
        if isinstance(row, Mapping) and str(row.get("objectRef") or "").startswith(("entities/", "posts/"))
    }
    release_object_refs = set().union(*release_refs_by_carrier(release).values())
    if not admission_refs.issubset(release_object_refs):
        raise CampaignScaleEvidenceError("campaign admission object closure drift")
    article_coverage = admission.get("articleMediaCoverage")
    illustrated_rate = float(
        article_coverage.get("illustratedRate")
        if isinstance(article_coverage, Mapping)
        else 0.0
    )
    derived_status = (
        "passed"
        if duplicate_assets == 0
        and duplicate_publish_refs + wrong_lane_refs == 0
        else "failed"
    )
    timing_fields = scale_timing_fields(target_scale=target_scale, plan=plan, predecessor_promotion_path=predecessor_path, resource=resource)
    derived_campaign_fields = {
        "status": derived_status,
        "duplicateAssetCount": duplicate_assets,
        "crossLaneWriteCount": duplicate_publish_refs + wrong_lane_refs,
        "articleIllustratedRate": illustrated_rate,
        "fourLaneOverlapDurationSeconds": resource[
            "fourLaneOverlapDurationSeconds"
        ],
        "fourLaneLongestContinuousOverlapSeconds": resource[
            "fourLaneLongestContinuousOverlapSeconds"
        ],
        "allSemanticJobsTerminalAt": resource["allSemanticJobsTerminalAt"],
        "terminalResidualSampleAt": resource["terminalResidualSampleAt"],
        **timing_fields,
    }
    if any(campaign.get(key) != value for key, value in derived_campaign_fields.items()):
        raise CampaignScaleEvidenceError("campaign aggregate derived evidence drift")
    identity_keys = ("rootExecutionId", "sourceRevision", "sourceDigest", "entityCatalogDigest")
    plan_execution_ids = plan.get("executionIds")
    campaign_execution_ids = {
        str(lane.get("carrier")): str(lane.get("executionId"))
        for lane in campaign.get("lanes") or []
        if isinstance(lane, Mapping)
    }
    if (
        campaign.get("resourceSoakEvidenceDigest") != resource_digest
        or campaign.get("faultInjectionEvidenceDigest") != fault_digest
        or resource.get("evidenceId") != campaign.get("evidenceId")
        or fault.get("evidenceId") != campaign.get("evidenceId")
        or any(plan.get(key) != campaign.get(key) for key in identity_keys)
        or campaign_execution_ids != plan_execution_ids
        or any(resource.get(key) != campaign.get(key) for key in identity_keys)
        or any(fault.get(key) != campaign.get(key) for key in identity_keys)
        or not runtime_binding.documents_match_runtime_binding(
            (campaign, resource, fault), session,
            session_path=runtime_session_path, output_root=output_root
        )
    ):
        raise CampaignScaleEvidenceError("campaign subordinate evidence binding drift")
    return campaign, resource, fault
__all__ = ["CampaignScaleEvidenceError", "campaign_source_revision", "load_campaign_scale_evidence", "write_campaign_scale_evidence", "write_fault_injection_evidence", "write_resource_soak_evidence"]
