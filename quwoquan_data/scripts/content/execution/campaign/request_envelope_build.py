"""Immutable campaign request-envelope construction."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json
from core.schema import assert_valid
from governance.coverage.distribution import load_content_distribution_policy

from content.execution.campaign.external_inputs import (
    content_source_revision,
    external_inputs_digest,
)
from content.execution.campaign import request_envelope as owner
from content.execution.campaign.scale import CampaignScaleError, resolve_campaign_scale
from content.execution.identity import parse_execution_id
from content.execution.model_contract import (
    CURSOR_AUTO_SEMANTIC_SELECTION_ID,
    DEFAULT_SEMANTIC_SELECTION_ID,
    normalize_semantic_selection_id,
)
from content.execution.planning.semantic_preflight_admission import (
    bind_semantic_preflight_receipt,
    validate_semantic_preflight_binding_at,
)
from content.execution.preflight.receipt import validate_semantic_preflight_receipt
from content.execution.request import resolve_candidate_pool
from content.execution.runtime_contract import file_sha256
from content.execution.campaign.source_pool_binding import bind_scale_source_pool


def _fixed_capacity_plan(
    *,
    scale: str,
    semantic_selection_id: str,
    semantic_preflight_receipt: Path | None,
) -> dict[str, Any]:
    preflight_identity: dict[str, Any] | None = None
    if semantic_selection_id == CURSOR_AUTO_SEMANTIC_SELECTION_ID:
        if semantic_preflight_receipt is None:
            raise ValueError(
                "campaign cursor_auto capacity requires a fresh semantic preflight receipt"
            )
        receipt = read_json(semantic_preflight_receipt.expanduser().resolve())
        if not isinstance(receipt, Mapping):
            raise TypeError("semantic preflight receipt must be an object")
        validate_semantic_preflight_receipt(
            receipt,
            require_execution_admission=True,
        )
        capacity = (receipt.get("evidence") or {}).get("capacitySoak")
        effective = (
            capacity.get("effectiveConcurrency")
            if isinstance(capacity, Mapping)
            else None
        )
        if isinstance(effective, bool) or not isinstance(effective, int) or effective < 4:
            raise ValueError(
                "DATA.AGENT.CAPACITY_SHORTFALL: fixed-capacity cursor_auto campaign requires "
                "effectiveConcurrency>=4"
            )
        preflight_identity = {
            "receiptId": receipt["receiptId"],
            "selectionDigest": receipt["selectionDigest"],
            "effectiveConcurrency": effective,
        }
    stable: dict[str, Any] = {
        "schema": "quwoquan_data.fixed_campaign_capacity_plan",
        "targetScale": scale,
        "semanticSelectionId": semantic_selection_id,
        "preflight": preflight_identity,
        "carrierPlans": [
            {
                "carrier": lane,
                "requiredWorkers": 1,
                "partitionCount": 16,
            }
            for lane in owner.CAMPAIGN_CARRIERS
        ],
    }
    return {**stable, "planDigest": owner._sha256(stable)}


def _capacity_plan(
    *,
    scale: str,
    policy: Any,
    semantic_selection_id: str,
    semantic_preflight_receipt: Path | None,
    promotion_receipt: Path | None,
    predecessor_counts: Mapping[str, int] | None,
) -> dict[str, Any]:
    if scale not in {"M1000", "M10000"}:
        return _fixed_capacity_plan(
            scale=scale,
            semantic_selection_id=semantic_selection_id,
            semantic_preflight_receipt=semantic_preflight_receipt,
        )
    if promotion_receipt is None or semantic_preflight_receipt is None:
        raise ValueError(
            f"{scale} capacity requires predecessor promotion and fresh preflight"
        )
    promotion = read_json(promotion_receipt.expanduser().resolve())
    receipt = read_json(semantic_preflight_receipt.expanduser().resolve())
    if not isinstance(promotion, Mapping) or not isinstance(receipt, Mapping):
        raise TypeError("capacity plan inputs must be objects")
    if predecessor_counts is None:
        raise ValueError(
            f"{scale} capacity requires canonical predecessor counts"
        )
    deltas = {
        lane: policy.scale_target(scale, lane) - int(predecessor_counts[lane])
        for lane in owner.CAMPAIGN_CARRIERS
    }
    from content.execution.scale.capacity_plan import build_governed_capacity_plan

    return build_governed_capacity_plan(
        predecessor_promotion=promotion,
        target_scale=scale,
        carrier_deltas=deltas,
        preflight_receipt=receipt,
    )


def _capacity_binding(plan: Mapping[str, Any], *, carrier: str) -> dict[str, Any]:
    rows = plan.get("carrierPlans")
    if not isinstance(rows, list):
        raise TypeError("capacity plan carrierPlans must be an array")
    matching = [row for row in rows if isinstance(row, Mapping) and row.get("carrier") == carrier]
    if len(matching) != 1:
        raise ValueError(f"capacity plan must contain exactly one {carrier} row")
    row = matching[0]
    return {
        "requiredWorkers": int(row["requiredWorkers"]),
        "partitionCount": int(row["partitionCount"]),
        "capacityPlanDigest": str(plan["planDigest"]),
    }

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
    semantic_selection_id: str = DEFAULT_SEMANTIC_SELECTION_ID,
    semantic_preflight_receipt: Path | None = None,
    semantic_preflight_output_root: Path | None = None,
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
) -> dict[str, Any]:
    if carrier not in owner._OPERATIONS:
        raise ValueError(f"unsupported carrier: {carrier}")
    resolved = resolve_campaign_scale(scale=scale, quota=quota)
    vertical_id = owner._normalize_vertical(vertical)
    source_repo = (repo_root or paths.REPO_ROOT).resolve()
    policy = load_content_distribution_policy()
    governed_target = (
        policy.scale_target(resolved.scale, carrier)
        if resolved.scale in {"M100", "M1000", "M10000"}
        else resolved.quota
    )
    source = owner.current_source_digest(repo_root=source_repo).to_document()
    owner._require_stable_source_inputs(source, repo_root=source_repo)
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
    catalog_digest = owner.entity_catalog_digest(
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
        if resolved.scale in {"M1000", "M10000"}
        else None
    )
    carried_count = 0
    if promotion_reference is not None:
        carried_count = next(
            int(row["totalUniqueFinalizedCount"])
            for row in promotion_reference["carrierCounts"]
            if row["carrier"] == carrier
        )
    governed_quota = governed_target - carried_count
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
    frozen_external_refs, handoff_binding = owner.freeze_carrier_pre_acquisition_inputs(
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
        scale=resolved.scale,
        vertical=vertical_id,
        scope=scope,
        day=stamp,
        sequence=sequence,
    )
    retry_of = str(predecessor_execution_id or "").strip() or None
    if sequence == 1 and retry_of is not None:
        raise ValueError("campaign envelope sequence=1 forbids a retry predecessor")
    if sequence > 1 and retry_of is None:
        raise ValueError("campaign envelope sequence>1 requires a retry predecessor")
    if retry_of is not None:
        current, predecessor = map(parse_execution_id, (ids[carrier], retry_of))
        comparable = ("vertical", "content_type", "intent", "scope", "phase")
        if any(getattr(current, key) != getattr(predecessor, key) for key in comparable):
            raise ValueError("campaign envelope retry predecessor must preserve execution scope")
        if predecessor.sequence >= current.sequence:
            raise ValueError("campaign envelope retry predecessor must use an earlier sequence")
    frozen_semantic_selection_id = normalize_semantic_selection_id(
        semantic_selection_id
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
    if frozen_semantic_selection_id == CURSOR_AUTO_SEMANTIC_SELECTION_ID:
        if semantic_preflight_binding is None:
            raise ValueError(
                "campaign cursor_auto selection requires a fresh semantic preflight receipt"
            )
    capacity_binding = _capacity_binding(
        _capacity_plan(
            scale=resolved.scale,
            policy=policy,
            semantic_selection_id=frozen_semantic_selection_id,
            semantic_preflight_receipt=semantic_preflight_receipt,
            promotion_receipt=promotion_receipt,
            predecessor_counts=(
                {
                    str(row["carrier"]): int(row["totalUniqueFinalizedCount"])
                    for row in promotion_reference["carrierCounts"]
                }
                if promotion_reference is not None
                else None
            ),
        ),
        carrier=carrier,
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
    names = sorted({str(item).strip() for item in (target_names or []) if str(item).strip()})
    if names and len(names) < quota_value:
        raise ValueError(
            "campaign targetNames must contain at least the governed quota "
            f"({quota_value}); got {len(names)}"
        )
    providers = sorted(
        {str(item).strip() for item in (source_providers or []) if str(item).strip()}
    )
    topic_value = str(topic).strip() if topic is not None and str(topic).strip() else None
    source_pool_binding = None
    source_pool_evidence_ref = None
    source_pool_selection = None
    if resolved.scale in {"M100", "M1000", "M10000"}:
        if scale_source_pool is None or source_pool_evidence_root is None:
            raise ValueError(
                "DATA.SOURCE.POOL_SHORTFALL: M100+ requires scale source pool and evidence root"
            )
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
        )
    elif scale_source_pool is not None or source_pool_evidence_root is not None:
        raise ValueError(
            "DATA.SOURCE.POOL_SHORTFALL: below-M100 forbids scale source pool inputs"
        )
    git_branch = owner._git_branch(source_repo)
    git_commit_sha = owner._git_commit(source_repo)
    stable: dict[str, Any] = {
        "schema": owner.ENVELOPE_SCHEMA,
        "scale": resolved.scale,
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
        **capacity_binding,
        "topic": topic_value,
        "targetNames": names,
        "sourceProviders": providers,
        "semanticSelectionId": frozen_semantic_selection_id,
        "retryOf": retry_of,
        "rootExecutionId": ids["homepage"],
        "executionId": ids[carrier],
        "gitBranch": git_branch,
        "gitCommitSha": git_commit_sha,
        "sourceRevision": source_revision,
        "sourceDigest": source,
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
    owner._require_stable_source_inputs(source, repo_root=source_repo)
    return envelope
