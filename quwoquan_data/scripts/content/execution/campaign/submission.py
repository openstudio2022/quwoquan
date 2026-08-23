"""Immutable carrier submissions for one coordinated four-lane execution."""

from __future__ import annotations

import fcntl
import hashlib
import json
import subprocess
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

from core import paths
from core.io import read_json, write_json
from core.schema import assert_valid
from core.source_digest import (
    current_execution_bundle_identity,
    current_source_definition_snapshot,
)

from content.execution.campaign.external_inputs import (
    content_source_revision,
    external_inputs_digest,
    verify_external_input_refs,
)
from content.execution.campaign.carrier_execution_policy import carrier_operation
from content.execution.campaign.lane import (
    CAMPAIGN_CARRIERS,
    normalize_active_carriers,
    normalize_workloads,
)
from content.execution.campaign.scale import execution_campaign_scale
from content.execution.closure.adoption_campaign_contract import (
    ADOPTION_OPERATIONS,
    CAMPAIGN_ADOPTION_FIELD,
)
from content.execution.identity import parse_execution_id, validate_execution_id
from content.execution.model_contract import (
    CURSOR_AUTO_SEMANTIC_SELECTION_ID,
    DEFAULT_SEMANTIC_SELECTION_ID,
    normalize_semantic_selection_id,
)
from content.execution.planning.semantic_preflight_admission import (
    bind_semantic_preflight_receipt,
    validate_semantic_preflight_binding_at,
)
from content.execution.planning.semantic_failover_admission import (
    require_cursor_auto_retry_admission,
)
from content.execution.request import RuntimeExecutionRequest
from content.execution.workspace import entity_catalog_digest

SUBMISSION_SCHEMA = "quwoquan_data.content_execution_submission"


from content.execution.campaign.submission_identity import (
    _assert_no_cross_campaign_collision,
    _git_branch,
    _git_commit,
    _require_stable_source_inputs,
    _sha256,
    _submission_lock,
    _utc_now,
    campaign_root,
    campaigns_root,
    submission_path,
)


from content.execution.campaign.submission_workload import (
    _FrozenWorkload,
    _frozen_workload,
)


def write_submission(
    *,
    root_execution_id: str,
    execution_id: str,
    request: RuntimeExecutionRequest,
    retry_of: str | None,
    repo_root: Path | None = None,
    root: Path | None = None,
    campaign_envelope: Mapping[str, Any] | None = None,
    acquisition_root: Path | None = None,
    semantic_selection_id: str | None = None,
    semantic_preflight_receipt: Path | None = None,
    semantic_preflight_output_root: Path | None = None,
    active_carriers: Iterable[str] | None = None,
    workloads: Mapping[str, int] | None = None,
    workload_mode: str = "explicit",
    retry_unfinished_refs: Iterable[str] = (),
) -> Path:
    source_repo = (repo_root or paths.REPO_ROOT).resolve()
    campaigns_dir = root or campaigns_root()
    root_identity = parse_execution_id(root_execution_id)
    identity = parse_execution_id(execution_id)
    if identity.vertical != root_identity.vertical:
        raise ValueError("campaign lanes must use the same vertical")
    frozen_workload = _frozen_workload(
        campaign_envelope,
        carrier=identity.content_type.value,
        quota=request.quota,
        active_carriers=active_carriers,
        workloads=workloads,
        workload_mode=workload_mode,
    )
    if root_identity.content_type.value != frozen_workload.active_carriers[0]:
        raise ValueError(
            "campaign root must use the first active carrier execution identity"
        )
    if frozen_workload.workloads[identity.content_type.value] != request.quota:
        raise ValueError(
            "campaign lane quota must equal its frozen active workload quota"
        )
    unfinished_refs = [str(ref).strip() for ref in retry_unfinished_refs]
    if any(not ref for ref in unfinished_refs) or len(set(unfinished_refs)) != len(
        unfinished_refs
    ):
        raise ValueError(
            "campaign retryUnfinishedRefs must be unique non-empty object refs"
        )
    if unfinished_refs and not retry_of:
        raise ValueError("campaign retryUnfinishedRefs require a retryOf predecessor")
    scale = execution_campaign_scale(identity.execution_id, quota=request.quota)
    root_scale = execution_campaign_scale(
        root_identity.execution_id,
        quota=request.quota,
    )
    if scale != root_scale:
        raise ValueError("campaign lanes must use the same immutable scale intent")
    if retry_of:
        predecessor = parse_execution_id(retry_of)
        if predecessor.execution_id == identity.execution_id:
            raise ValueError(
                "GATE_BLOCK DATA.CAMPAIGN.EXTERNAL_INPUT_RETRY_INVALID: "
                "retryOf must reference a different execution sequence"
            )
        if (
            predecessor.vertical != identity.vertical
            or predecessor.content_type is not identity.content_type
        ):
            raise ValueError(
                "GATE_BLOCK DATA.CAMPAIGN.EXTERNAL_INPUT_RETRY_INVALID: "
                "retryOf must preserve vertical and carrier"
            )
    source = current_source_definition_snapshot(repo_root=source_repo).to_document()
    execution_bundle = current_execution_bundle_identity(
        repo_root=source_repo
    ).to_document()
    _require_stable_source_inputs(
        source,
        execution_bundle=execution_bundle,
        repo_root=source_repo,
    )
    discovery = (
        source_repo
        / "quwoquan_data"
        / "reference"
        / identity.vertical
        / "entities"
        / request.region_ref
    )
    catalog_digest = entity_catalog_digest(
        discovery.relative_to(source_repo).as_posix()
    )
    source_revision = content_source_revision(
        source_digest=str(source["digest"]),
        entity_catalog_digest=catalog_digest,
    )
    requested_semantic_selection_id = (
        normalize_semantic_selection_id(semantic_selection_id)
        if semantic_selection_id is not None
        else None
    )
    if campaign_envelope is not None:
        envelope = dict(campaign_envelope)
        assert_valid(
            envelope,
            "execution",
            "content_campaign_request_envelope",
            label=f"campaign envelope:{identity.execution_id}",
        )
        expected_envelope = {
            "scale": scale,
            "workloadMode": frozen_workload.workload_mode,
            "activeCarriers": list(frozen_workload.active_carriers),
            "workloads": frozen_workload.workloads,
            "rootExecutionId": root_identity.execution_id,
            "executionId": identity.execution_id,
            "operation": carrier_operation(identity.content_type.value),
            "carrier": identity.content_type.value,
            "familyRef": request.family_ref,
            "regionRef": request.region_ref,
            "selector": request.selector.value,
            "quota": request.quota,
            "count": request.count,
            "executionAuthority": dict(request.execution_authority),
            "workerHostSetBinding": (
                dict(request.worker_host_set_binding)
                if request.worker_host_set_binding is not None
                else None
            ),
            "scaleSourcePool": (
                dict(request.scale_source_pool)
                if request.scale_source_pool is not None
                else None
            ),
            "sourcePoolEvidenceRootRef": request.source_pool_evidence_root_ref,
            "sourcePoolSelection": (
                dict(request.source_pool_selection)
                if request.source_pool_selection is not None
                else None
            ),
            "topic": request.topic,
            "targetNames": list(request.target_names),
            "sourceProviders": list(request.source_providers),
            "semanticSelectionId": envelope.get("semanticSelectionId"),
            "semanticPreflightReceipt": envelope.get("semanticPreflightReceipt"),
            "retryOf": retry_of,
            "gitBranch": _git_branch(source_repo),
            "gitCommitSha": _git_commit(source_repo),
            "sourceRevision": source_revision,
            "sourceDigest": source,
            "executionBundle": execution_bundle,
            "entityCatalogDigest": catalog_digest,
            "predecessorReconciliation": envelope.get("predecessorReconciliation"),
        }
        drift = [
            key
            for key, value in expected_envelope.items()
            if envelope.get(key) != value
        ]
        if drift:
            raise ValueError(
                "GATE_BLOCK DATA.CAMPAIGN.EXTERNAL_INPUT_IDENTITY_DRIFT: "
                "campaign envelope drift: " + ", ".join(drift)
            )
        frozen_semantic_selection_id = normalize_semantic_selection_id(
            envelope.get("semanticSelectionId")
        )
        if (
            requested_semantic_selection_id is not None
            and requested_semantic_selection_id != frozen_semantic_selection_id
        ):
            raise ValueError(
                "GATE_BLOCK DATA.CAMPAIGN.SEMANTIC_SELECTION_DRIFT: "
                "CLI semantic selection differs from the immutable campaign envelope"
            )
        semantic_preflight_binding = envelope.get("semanticPreflightReceipt")
        if semantic_preflight_binding is not None:
            validate_semantic_preflight_binding_at(
                semantic_preflight_binding,
                semantic_selection_id=frozen_semantic_selection_id,
                admitted_at=str(envelope["frozenAt"]),
                output_root=(semantic_preflight_output_root or paths.OUTPUT_ROOT),
            )
        if semantic_preflight_receipt is not None:
            requested_preflight_binding = bind_semantic_preflight_receipt(
                semantic_preflight_receipt,
                semantic_selection_id=frozen_semantic_selection_id,
                output_root=(semantic_preflight_output_root or paths.OUTPUT_ROOT),
            )
            if requested_preflight_binding != semantic_preflight_binding:
                raise ValueError(
                    "GATE_BLOCK DATA.CAMPAIGN.SEMANTIC_PREFLIGHT_DRIFT: "
                    "CLI semantic preflight differs from immutable campaign envelope"
                )
        external_refs = verify_external_input_refs(
            identity.content_type.value,
            envelope.get("externalInputRefs") or [],
            acquisition_root=(
                acquisition_root or paths.SOURCE_ACQUISITION_ROOT
            ).resolve(),
            source_revision=source_revision,
            source_digest=str(source["digest"]),
            entity_catalog_digest=catalog_digest,
        )
        if envelope.get("externalInputsDigest") != external_inputs_digest(
            external_refs
        ):
            raise ValueError(
                "GATE_BLOCK DATA.CAMPAIGN.EXTERNAL_INPUT_DIGEST_DRIFT: "
                "campaign envelope externalInputsDigest drift"
            )
        predecessor_reconciliation = envelope.get("predecessorReconciliation")
        if predecessor_reconciliation is not None:
            from content.execution.campaign.submission_reconciliation import (
                load_reconciliation_reference,
            )

            receipt, _receipt_path = load_reconciliation_reference(
                predecessor_reconciliation,
                output_root=paths.OUTPUT_ROOT,
            )
            predecessor_row = (receipt.get("submissions") or {}).get(
                identity.content_type.value
            )
            current_source_identity = {
                "sourceRevision": source_revision,
                "sourceDigest": source,
                "executionBundle": execution_bundle,
                "entityCatalogDigest": catalog_digest,
            }
            expected_predecessor_scope = {
                "executionId": retry_of,
                "familyRef": request.family_ref,
                "regionRef": request.region_ref,
                "selector": request.selector.value,
                "quota": request.quota,
                "count": request.count,
                "topic": request.topic,
                "targetNames": list(request.target_names),
                "sourceProviders": list(request.source_providers),
            }
            if (
                not isinstance(predecessor_row, Mapping)
                or (
                    receipt.get("reason") == "source_drift"
                    and receipt.get("originalSourceIdentity")
                    == current_source_identity
                )
                or any(
                    predecessor_row.get(key) != value
                    for key, value in expected_predecessor_scope.items()
                )
            ):
                raise ValueError(
                    "GATE_BLOCK DATA.CAMPAIGN.SUBMISSION_RECONCILIATION_DRIFT: "
                    "predecessor receipt lineage/target/scope binding drift"
                )
    else:
        external_refs = []
        frozen_semantic_selection_id = (
            requested_semantic_selection_id or DEFAULT_SEMANTIC_SELECTION_ID
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
        require_cursor_auto_retry_admission(
            retry_of,
            output_root=(semantic_preflight_output_root or paths.OUTPUT_ROOT),
        )
    if (
        semantic_preflight_binding is None
        and frozen_semantic_selection_id != "not_applicable"
    ):
        raise ValueError(
            "GATE_BLOCK DATA.CAMPAIGN.SEMANTIC_PREFLIGHT_REQUIRED: "
            "every selected semantic Provider requires a fresh preflight/soak "
            "execution-admission receipt"
        )
    if (
        frozen_semantic_selection_id == CURSOR_AUTO_SEMANTIC_SELECTION_ID
        and semantic_preflight_binding is None
    ):
        raise ValueError(
            "GATE_BLOCK DATA.CAMPAIGN.SEMANTIC_PREFLIGHT_REQUIRED: "
            "cursor_auto requires a fresh execution-admission receipt"
        )
    stable: dict[str, Any] = {
        "schema": SUBMISSION_SCHEMA,
        "scale": scale,
        "workloadMode": frozen_workload.workload_mode,
        "activeCarriers": list(frozen_workload.active_carriers),
        "workloads": frozen_workload.workloads,
        "rootExecutionId": root_identity.execution_id,
        "executionId": identity.execution_id,
        "operation": carrier_operation(identity.content_type.value),
        "carrier": identity.content_type.value,
        "familyRef": request.family_ref,
        "regionRef": request.region_ref,
        "selector": request.selector.value,
        "quota": request.quota,
        "count": request.count,
        "executionAuthority": dict(request.execution_authority),
        "workerHostSetBinding": (
            dict(request.worker_host_set_binding)
            if request.worker_host_set_binding is not None
            else None
        ),
        "topic": request.topic,
        "targetNames": list(request.target_names),
        "sourceProviders": list(request.source_providers),
        "semanticSelectionId": frozen_semantic_selection_id,
        "retryOf": retry_of,
        "retryUnfinishedRefs": unfinished_refs,
        "gitBranch": _git_branch(source_repo),
        "gitCommitSha": _git_commit(source_repo),
        "sourceRevision": source_revision,
        "sourceDigest": source,
        "executionBundle": execution_bundle,
        "entityCatalogDigest": catalog_digest,
        "externalInputRefs": external_refs,
        "externalInputsDigest": external_inputs_digest(external_refs),
    }
    if request.scale_source_pool is not None:
        stable["scaleSourcePool"] = dict(request.scale_source_pool)
        stable["sourcePoolEvidenceRootRef"] = request.source_pool_evidence_root_ref
        stable["sourcePoolSelection"] = dict(request.source_pool_selection or {})
    if semantic_preflight_binding is not None:
        stable["semanticPreflightReceipt"] = dict(semantic_preflight_binding)
    if (
        campaign_envelope is not None
        and campaign_envelope.get("predecessorReconciliation") is not None
    ):
        stable["predecessorReconciliation"] = dict(
            campaign_envelope["predecessorReconciliation"]
        )
    request_digest = _sha256(stable)
    path = submission_path(
        root_identity.execution_id,
        identity.execution_id,
        root=campaigns_dir,
    )
    with _submission_lock(campaigns_dir):
        _require_stable_source_inputs(
            source,
            execution_bundle=execution_bundle,
            repo_root=source_repo,
        )
        _assert_no_cross_campaign_collision(
            campaigns_dir=campaigns_dir,
            root_execution_id=root_identity.execution_id,
            execution_id=identity.execution_id,
        )
        if path.is_file():
            existing = read_json(path)
            assert_valid(
                existing,
                "execution",
                "content_execution_submission",
                label=f"campaign submission:{identity.execution_id}",
            )
            if str(existing.get("requestDigest") or "") != request_digest or any(
                existing.get(key) != value for key, value in stable.items()
            ):
                raise ValueError(
                    "GATE_BLOCK DATA.CAMPAIGN.EXTERNAL_INPUT_IMMUTABLE: "
                    f"execution {identity.execution_id} already differs; create a "
                    "new execution sequence with retryOf"
                )
            return path
        payload = {
            **stable,
            "requestDigest": request_digest,
            "submittedAt": _utc_now(),
        }
        assert_valid(
            payload,
            "execution",
            "content_execution_submission",
            label=f"campaign submission:{identity.execution_id}",
        )
        write_json(path, payload)
    return path


def write_adoption_submission(
    *,
    root_execution_id: str,
    execution_id: str,
    region_ref: str,
    reviewed_closure_adoption: Mapping[str, Any],
    repo_root: Path | None = None,
    output_root: Path | None = None,
    root: Path | None = None,
    frozen_source_identity: Mapping[str, Any] | None = None,
    git_branch: str | None = None,
    git_commit_sha: str | None = None,
) -> Path:
    from content.execution.campaign.adoption_submission import (
        write_adoption_submission as write_adoption,
    )

    return write_adoption(
        root_execution_id=root_execution_id,
        execution_id=execution_id,
        region_ref=region_ref,
        reviewed_closure_adoption=reviewed_closure_adoption,
        repo_root=repo_root,
        output_root=output_root,
        root=root,
        frozen_source_identity=frozen_source_identity,
        git_branch=git_branch,
        git_commit_sha=git_commit_sha,
    )


def load_submissions(
    root_execution_id: str,
    *,
    root: Path | None = None,
) -> dict[str, dict[str, Any]]:
    normalized_root = validate_execution_id(root_execution_id)
    submissions_dir = campaign_root(normalized_root, root=root) / "submissions"
    submissions: dict[str, dict[str, Any]] = {}
    for path in (
        sorted(submissions_dir.glob("*.json")) if submissions_dir.is_dir() else ()
    ):
        payload = read_json(path)
        assert_valid(
            payload,
            "execution",
            "content_execution_submission",
            label=f"campaign submission:{path.name}",
        )
        execution_id = validate_execution_id(str(payload.get("executionId") or ""))
        identity = parse_execution_id(execution_id)
        carrier = str(payload.get("carrier") or "")
        if (
            str(payload.get("rootExecutionId") or "") != normalized_root
            or path.stem != execution_id
            or carrier != identity.content_type.value
            or str(payload.get("operation") or "")
            != (
                ADOPTION_OPERATIONS.get(carrier)
                if CAMPAIGN_ADOPTION_FIELD in payload
                else carrier_operation(carrier)
            )
        ):
            raise ValueError(f"campaign submission identity collision: {path}")
        stable = {
            key: value
            for key, value in payload.items()
            if key not in {"requestDigest", "submittedAt"}
        }
        if str(payload.get("requestDigest") or "") != _sha256(stable):
            raise ValueError(f"campaign submission digest drift: {path}")
        if carrier in submissions:
            raise ValueError(f"campaign has duplicate {carrier} submissions")
        submissions[carrier] = payload
    return submissions


__all__ = [
    "campaign_root",
    "campaigns_root",
    "load_submissions",
    "submission_path",
    "write_adoption_submission",
    "write_submission",
]
