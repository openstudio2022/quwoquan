"""Immutable campaign request-envelope construction."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import paths
from core.schema import assert_valid
from core.source_digest import (
    current_execution_bundle_identity,
    current_source_definition_snapshot,
)
from governance.coverage.distribution import load_content_distribution_policy

from content.execution.campaign import request_envelope as owner
from content.execution.campaign.external_inputs import (
    content_source_revision,
    external_inputs_digest,
)
from content.execution.campaign.lane import (
    CAMPAIGN_CARRIERS,
    normalize_active_carriers,
    normalize_workloads,
)
from content.execution.campaign.retry_submission import (
    campaign_review_retry_feedback_source,
)
from content.execution.campaign.scale import CampaignScaleError, resolve_campaign_scale
from content.execution.campaign.source_pool_binding import bind_scale_source_pool
from content.execution.controller.execute.pre_acquisition_handoff import (
    freeze_carrier_pre_acquisition_inputs,
)
from content.execution.identity import parse_execution_id
from content.execution.model_contract import (
    CURSOR_AUTO_SEMANTIC_SELECTION_ID,
    DEFAULT_SEMANTIC_SELECTION_ID,
    normalize_semantic_selection_id,
)
from content.execution.planning.semantic_failover_admission import (
    require_cursor_auto_retry_admission,
)
from content.execution.planning.semantic_preflight_admission import (
    bind_semantic_preflight_receipt,
    validate_semantic_preflight_binding_at,
)
from content.execution.planning.capacity_calibration import (
    bind_capacity_calibration_source,
    current_host_class,
    resolve_capacity_calibration_ref,
)
from content.execution.request import resolve_candidate_pool
from content.execution.workspace import entity_catalog_digest


def build_envelope(
    *,
    scale: str | None = None,
    quota: int | None = None,
    carrier: str,
    region_ref: str,
    vertical: str = "travel",
    topic: str | None = None,
    target_names: Iterable[str] | None = None,
    source_providers: Iterable[str] | None = None,
    family_ref: str | None = None,
    repo_root: Path | None = None,
    day: str | None = None,
    sequence: int = 1,
    predecessor_execution_id: str | None = None,
    allow_retry_intent_change: bool = False,
    semantic_selection_id: str = DEFAULT_SEMANTIC_SELECTION_ID,
    semantic_preflight_receipt: Path | None = None,
    semantic_preflight_output_root: Path | None = None,
    capacity_calibration_receipt: Path | None = None,
    capacity_calibration_output_root: Path | None = None,
    predecessor_reconciliation: Mapping[str, Any] | None = None,
    promotion_receipt: Path | None = None,
    promotion_output_root: Path | None = None,
    pre_acquisition_handoff: Path | None = None,
    pre_acquisition_handoff_output_root: Path | None = None,
    external_input_refs: Iterable[Mapping[str, Any]] = (),
    acquisition_root: Path | None = None,
    scale_source_pool: Path | None = None,
    source_pool_evidence_root: Path | None = None,
    source_pool_output_root: Path | None = None,
    retry_evidence_output_root: Path | None = None,
    active_carriers: Iterable[str] | None = None,
    workloads: Mapping[str, int] | None = None,
    workload_mode: str = "explicit",
) -> dict[str, Any]:
    if carrier not in owner._OPERATIONS:
        raise ValueError(f"unsupported carrier: {carrier}")
    resolved = resolve_campaign_scale(scale=scale, quota=quota)
    vertical_id = owner._normalize_vertical(vertical)
    source_repo = (repo_root or paths.REPO_ROOT).resolve()
    active = normalize_active_carriers(active_carriers or (carrier,))
    if carrier not in active:
        raise ValueError(f"campaign envelope carrier {carrier} is not active")
    if workloads is None:
        exact_workloads = {selected: resolved.quota for selected in active}
    else:
        exact_workloads = normalize_workloads(workloads, active_carriers=active)
    if workload_mode == "milestone_preset":
        if active != CAMPAIGN_CARRIERS:
            raise ValueError("milestone preset must expand all campaign carriers")
        policy = load_content_distribution_policy()
        expected = {
            selected: policy.scale_target(resolved.scale, selected)
            for selected in active
        }
        if exact_workloads != expected:
            raise ValueError("milestone preset workloads drift from governed targets")
    elif workload_mode != "explicit":
        raise ValueError(f"unsupported campaign workload mode: {workload_mode}")
    governed_target = exact_workloads[carrier]
    source = current_source_definition_snapshot(repo_root=source_repo).to_document()
    execution_bundle = current_execution_bundle_identity(
        repo_root=source_repo
    ).to_document()
    owner._require_stable_source_inputs(
        source,
        execution_bundle=execution_bundle,
        repo_root=source_repo,
    )
    discovery = (
        source_repo
        / "quwoquan_data"
        / "reference"
        / vertical_id
        / "entities"
        / region_ref
    )
    if not discovery.is_dir():
        raise ValueError(f"region reference does not exist: {region_ref}")
    catalog_digest = entity_catalog_digest(
        discovery.relative_to(source_repo).as_posix()
    )
    source_revision = content_source_revision(
        source_digest=str(source["digest"]),
        entity_catalog_digest=catalog_digest,
    )
    promotion_reference = (
        owner._research_scale_promotion_ref(
            promotion_receipt,
            next_scale=resolved.scale,
            source_digest=source,
            entity_catalog_digest=catalog_digest,
            source_revision=source_revision,
            output_root=(promotion_output_root or paths.OUTPUT_ROOT),
        )
        if promotion_receipt is not None
        else None
    )
    names = sorted(
        {str(item).strip() for item in (target_names or []) if str(item).strip()}
    )
    carried_count = 0
    if promotion_reference is not None:
        carried_count = next(
            int(row["totalUniqueFinalizedCount"])
            for row in promotion_reference["carrierCounts"]
            if row["carrier"] == carrier
        )
    remaining_quota = governed_target - carried_count
    if (
        workload_mode == "milestone_preset"
        and resolved.scale in {"M100", "M1000"}
        and not names
    ):
        raise ValueError(
            f"DATA.SOURCE.WAVE_INPUT_MISSING: {resolved.scale} requires current-wave targetNames"
        )
    governed_quota = remaining_quota
    if governed_quota < 1:
        raise CampaignScaleError(
            f"GATE_BLOCK {resolved.scale}/{carrier} predecessor already meets or exceeds target"
        )
    try:
        quota_value, count = resolve_candidate_pool(quota=governed_quota, count=None)
    except SystemExit as exc:
        raise CampaignScaleError(str(exc)) from exc
    stamp = day or datetime.now(timezone.utc).strftime("%Y%m%d")
    scope = owner.normalize_execution_scope(region_ref, topic)
    frozen_external_refs, handoff_binding = freeze_carrier_pre_acquisition_inputs(
        carrier,
        external_input_refs,
        acquisition_root=(
            acquisition_root or paths.SOURCE_ACQUISITION_ROOT
        ).resolve(),
        handoff_ref=pre_acquisition_handoff,
        scale=resolved.scale,
        vertical=vertical_id,
        scope=scope,
        region_ref=region_ref,
        topic=topic,
        run_date=stamp,
        campaign_sequence=sequence,
        source_revision=source_revision,
        source_digest=str(source["digest"]),
        entity_catalog_digest=catalog_digest,
        handoff_output_root=pre_acquisition_handoff_output_root,
    )
    ids = owner._execution_ids(
        intent=owner.workload_intent(
            scale=resolved.scale,
            workload_mode=workload_mode,
            workloads=exact_workloads,
        ),
        vertical=vertical_id,
        scope=scope,
        day=stamp,
        carriers=active,
        sequence=sequence,
    )
    retry_of = str(predecessor_execution_id or "").strip() or None
    if sequence == 1 and retry_of is not None:
        raise ValueError("campaign envelope sequence=1 forbids a retry predecessor")
    if retry_of is not None:
        current, predecessor = map(parse_execution_id, (ids[carrier], retry_of))
        comparable = (
            ("vertical", "content_type", "scope", "phase")
            if allow_retry_intent_change
            else ("vertical", "content_type", "intent", "scope", "phase")
        )
        if any(getattr(current, key) != getattr(predecessor, key) for key in comparable):
            raise ValueError("campaign envelope retry predecessor must preserve execution scope")
        if predecessor.sequence >= current.sequence:
            raise ValueError("campaign envelope retry predecessor must use an earlier sequence")
    retry_output = (retry_evidence_output_root or paths.OUTPUT_ROOT).resolve()
    review_feedback = campaign_review_retry_feedback_source(
        campaigns_dir=(
            retry_output
            / "data/local/workspace/content-campaign-submissions"
        ),
        output_root=retry_output,
        execution_id=ids[carrier],
        carrier=carrier,
        retry_of=retry_of,
    )
    if review_feedback is not None:
        failed_count = len(review_feedback.object_refs)
        if governed_quota != failed_count or tuple(names) != review_feedback.target_names:
            raise ValueError(
                "GATE_BLOCK DATA.CAMPAIGN.REVIEW_RETRY_SCOPE_DRIFT: article retry "
                "workload quota/targetNames must equal predecessor failed "
                "final-review objects"
            )
        quota_value = failed_count
        count = failed_count
    frozen_semantic_selection_id = normalize_semantic_selection_id(
        semantic_selection_id
    )
    if frozen_semantic_selection_id == CURSOR_AUTO_SEMANTIC_SELECTION_ID:
        require_cursor_auto_retry_admission(
            retry_of,
            output_root=(semantic_preflight_output_root or paths.OUTPUT_ROOT),
        )
    semantic_preflight_binding = (
        bind_semantic_preflight_receipt(
            semantic_preflight_receipt,
            semantic_selection_id=frozen_semantic_selection_id,
            output_root=(semantic_preflight_output_root or paths.OUTPUT_ROOT),
        )
        if semantic_preflight_receipt is not None
        else None
    )
    if capacity_calibration_receipt is None:
        raise ValueError(
            "GATE_BLOCK DATA.CAPACITY.CALIBRATION_REQUIRED: "
            "campaign envelope requires a governed capacity calibration receipt"
        )
    capacity_ref = capacity_calibration_receipt.as_posix()
    capacity_path = resolve_capacity_calibration_ref(capacity_ref)
    capacity_binding = bind_capacity_calibration_source(
        receipt_path=capacity_path,
        receipt_ref=capacity_ref,
        host_class=current_host_class(),
        provider_tier=frozen_semantic_selection_id,
    )
    reconciliation = (
        dict(predecessor_reconciliation)
        if predecessor_reconciliation is not None
        else None
    )
    if reconciliation is not None:
        if retry_of is None:
            raise ValueError(
                "campaign envelope predecessor reconciliation requires retryOf"
            )
        assert_valid(
            reconciliation,
            "execution",
            "campaign_submission_reconciliation_ref",
            label=f"campaign predecessor reconciliation:{carrier}",
        )
    # targetNames is a unique-entity candidate scope. It may be smaller than
    # the requested object quota when several assets map to one entity.
    providers = sorted(
        {str(item).strip() for item in (source_providers or []) if str(item).strip()}
    )
    topic_value = str(topic).strip() if topic is not None and str(topic).strip() else None
    source_pool_binding = None
    source_pool_evidence_ref = None
    source_pool_selection = None
    pool_inputs = (scale_source_pool, source_pool_evidence_root)
    if any(value is not None for value in pool_inputs) and not all(
        value is not None for value in pool_inputs
    ):
        raise ValueError(
            "DATA.SOURCE.POOL_SHORTFALL: scale source pool and evidence root must be provided together"
        )
    if (
        resolved.scale not in {"M100", "M1000", "M10000"}
        and any(value is not None for value in pool_inputs)
    ):
        raise ValueError(
            "DATA.SOURCE.POOL_SHORTFALL: below-M100 forbids scale source pool inputs"
        )
    if all(value is not None for value in pool_inputs):
        assert scale_source_pool is not None and source_pool_evidence_root is not None
        (
            source_pool_binding,
            source_pool_evidence_ref,
            source_pool_selection,
        ) = bind_scale_source_pool(
            scale_source_pool,
            evidence_root=source_pool_evidence_root,
            output_root=(source_pool_output_root or paths.OUTPUT_ROOT),
            target_scale=resolved.scale,
            carrier=carrier,
            count=count,
            source_revision=source_revision,
            source_digest=str(source["digest"]),
            entity_catalog_digest=catalog_digest,
            active_carriers=active,
            workload_targets=exact_workloads,
        )
    git_branch = owner._git_branch(source_repo)
    git_commit_sha = owner._git_commit(source_repo)
    stable: dict[str, Any] = {
        "schema": owner.ENVELOPE_SCHEMA,
        "scale": resolved.scale,
        "workloadMode": workload_mode,
        "activeCarriers": list(active),
        "workloads": {
            **exact_workloads,
            carrier: quota_value,
        },
        "carrier": carrier,
        "operation": owner._OPERATIONS[carrier],
        "vertical": vertical_id,
        "familyRef": family_ref or owner.default_family_ref(
            vertical=vertical_id,
            carrier=carrier,
        ),
        "regionRef": region_ref,
        "selector": owner._SELECTORS[carrier],
        "quota": quota_value,
        "count": count,
        "capacityCalibration": capacity_binding,
        "workerHostSetBinding": None,
        "topic": topic_value,
        "targetNames": names,
        "sourceProviders": providers,
        "semanticSelectionId": frozen_semantic_selection_id,
        "retryOf": retry_of,
        "rootExecutionId": ids[active[0]],
        "executionId": ids[carrier],
        "gitBranch": git_branch,
        "gitCommitSha": git_commit_sha,
        "sourceRevision": source_revision,
        "sourceDigest": source,
        "executionBundle": execution_bundle,
        "entityCatalogDigest": catalog_digest,
        "preAcquisitionHandoff": handoff_binding,
        "externalInputRefs": frozen_external_refs,
        "externalInputsDigest": external_inputs_digest(frozen_external_refs),
        "allowedStage": "submit-only",
        "operatorPrompt": owner._OPERATOR_PROMPTS[carrier],
    }
    if promotion_reference is not None:
        stable["researchScalePromotion"] = promotion_reference
    if semantic_preflight_binding is not None:
        stable["semanticPreflightReceipt"] = semantic_preflight_binding
    if reconciliation is not None:
        stable["predecessorReconciliation"] = reconciliation
    if source_pool_binding is not None:
        stable["scaleSourcePool"] = source_pool_binding
        stable["sourcePoolEvidenceRootRef"] = source_pool_evidence_ref
        stable["sourcePoolSelection"] = source_pool_selection
    frozen_at = owner._utc_now()
    if semantic_preflight_binding is not None:
        validate_semantic_preflight_binding_at(
            semantic_preflight_binding,
            semantic_selection_id=frozen_semantic_selection_id,
            admitted_at=frozen_at,
            output_root=(semantic_preflight_output_root or paths.OUTPUT_ROOT),
        )
    envelope = {
        **stable,
        "requestDigest": owner._sha256(stable),
        "frozenAt": frozen_at,
    }
    owner._require_stable_source_inputs(
        source,
        execution_bundle=execution_bundle,
        repo_root=source_repo,
    )
    return envelope
