"""Campaign plan freeze, report IO, and lane status aggregation helpers."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.io import read_json, write_json
from core.schema import assert_valid

from content.execution.campaign.external_inputs import (
    external_inputs_digest,
    payload_digest,
)
from content.execution.campaign.lane import (
    normalize_active_carriers,
    normalize_workloads,
)
from content.execution.campaign.plan_lane_status import (
    aggregate_status,
    apply_receipt_fields,
    load_publish_for_lane,
    load_review_for_lane,
)
from content.execution.campaign.plan_identity import (
    campaign_path,
    plan_path,
    report_path,
    sha256_payload,
    utc_now,
)
from content.execution.campaign.plan_source_pool import aggregate_plan_source_pool
from content.execution.campaign.submission import load_submissions
from content.execution.campaign.workspace import (
    CampaignRuntimePaths,
    assert_frozen_main_tree,
)
from content.execution.closure.adoption_campaign_contract import (
    CAMPAIGN_ADOPTION_FIELD,
    validate_adoption_target_identity,
    validate_campaign_adoption_binding,
)
from content.execution.planning.capacity_calibration import (
    assert_capacity_source_binding,
)
from content.execution.planning.semantic_preflight_admission import (
    bind_semantic_preflight_receipt,
    validate_semantic_preflight_binding_at,
)

if TYPE_CHECKING:
    from content.execution.campaign.runtime import CampaignRunSession


CAMPAIGN_SUBMISSION_POLL_SECONDS = 2


def require_frozen_campaign_preflight_admission(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    *,
    execution_id: str,
    semantic_selection_id: str,
    requested_receipt_ref: str,
    expected_plan_digest: str,
) -> dict[str, Any] | None:
    """Resolve a lane receipt through the already-admitted immutable plan."""

    path = plan_path(runtime, root_execution_id)
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise TypeError("campaign plan must be an object")
    assert_valid(
        payload,
        "execution",
        "content_campaign_plan",
        label=f"campaign plan:{root_execution_id}",
    )
    stable = {key: value for key, value in payload.items() if key != "planDigest"}
    if (
        payload.get("planDigest") != sha256_payload(stable)
        or payload.get("planDigest") != expected_plan_digest
    ):
        raise ValueError("campaign planDigest drift")
    if (
        payload.get("rootExecutionId") != root_execution_id
        or execution_id not in set((payload.get("executionIds") or {}).values())
        or payload.get("semanticSelectionId") != semantic_selection_id
    ):
        raise ValueError("campaign semantic preflight admission identity drift")
    binding = payload.get("semanticPreflightReceipt")
    if binding is None:
        if not requested_receipt_ref:
            return None
        raise ValueError("campaign plan has no matching semantic preflight observation")
    validate_semantic_preflight_binding_at(
        binding,
        semantic_selection_id=semantic_selection_id,
        admitted_at=str(payload["frozenAt"]),
        output_root=runtime.output_root,
    )
    if not requested_receipt_ref:
        return dict(binding)
    requested_path = Path(requested_receipt_ref).expanduser()
    if not requested_path.is_absolute():
        requested_path = runtime.output_root / requested_path
    requested = bind_semantic_preflight_receipt(
        requested_path,
        semantic_selection_id=semantic_selection_id,
        output_root=runtime.output_root,
    )
    if requested != binding:
        raise ValueError(
            "lane semantic preflight differs from frozen campaign admission"
        )
    return dict(binding)


def empty_lane(execution_id: str = "pending") -> dict[str, Any]:
    return {
        "executionId": execution_id,
        "status": "pending",
        "phase": "submission",
        "reviewReturnCode": None,
        "publishReturnCode": None,
        "sourceCapsuleRef": None,
        "sourceCapsuleDigest": None,
        "sourceCapsuleCommitSha": None,
        "sourceCapsuleSourceDigest": None,
        "sourceCapsuleReadOnly": None,
        "executionRootRef": None,
        "cleanupStatus": "not_created",
        "approvedQuota": None,
        "qualifiedCount": None,
        "finalizedCount": None,
        "selectedCount": None,
        "discardedCount": None,
        "shortfallCount": None,
        "deliveryPendingCount": 0,
        "deliveryIntentRefs": [],
        "error": None,
    }


def write_report(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    *,
    status: str,
    phase: str,
    plan_digest: str | None,
    git_branch: str | None,
    git_commit_sha: str | None,
    source_digest: str | None,
    entity_catalog_digest: str | None,
    lanes: dict[str, dict[str, Any]],
    started_at: str,
    failure: str | None,
    active_carriers: tuple[str, ...],
    workloads: Mapping[str, int],
) -> Path:
    from content.execution.campaign.runtime import read_runtime_snapshot

    runtime_snapshot = read_runtime_snapshot(runtime, root_execution_id) or {}
    payload = {
        "schema": "quwoquan_data.content_campaign_report",
        "rootExecutionId": root_execution_id,
        "activeCarriers": list(normalize_active_carriers(active_carriers)),
        "workloads": normalize_workloads(
            workloads, active_carriers=active_carriers
        ),
        "campaignRunId": runtime_snapshot.get("runId"),
        "campaignGeneration": runtime_snapshot.get("generation"),
        "campaignFencingToken": runtime_snapshot.get("fencingToken"),
        "status": status,
        "phase": phase,
        "planDigest": plan_digest,
        "gitBranch": git_branch,
        "gitCommitSha": git_commit_sha,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "lanes": lanes,
        "failure": failure,
        "startedAt": started_at,
        "updatedAt": utc_now(),
    }
    assert_valid(
        payload,
        "execution",
        "content_campaign_report",
        label=f"campaign report:{root_execution_id}",
    )
    path = report_path(runtime, root_execution_id)
    write_json(path, payload)
    return path


def wait_for_submissions(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    *,
    timeout_seconds: int,
    lanes: dict[str, dict[str, Any]],
    started_at: str,
    run_session: CampaignRunSession | None = None,
) -> dict[str, dict[str, Any]]:
    if timeout_seconds < 1:
        raise ValueError("campaign submission timeout must be positive")
    deadline = time.monotonic() + timeout_seconds
    while True:
        if run_session is not None:
            run_session.campaign_checkpoint(phase="submission")
        submissions = load_submissions(
            root_execution_id,
            root=runtime.campaigns_root,
        )
        if not submissions:
            if time.monotonic() >= deadline:
                raise TimeoutError("campaign submissions timed out; no active request")
            time.sleep(
                min(
                    CAMPAIGN_SUBMISSION_POLL_SECONDS,
                    max(0.0, deadline - time.monotonic()),
                )
            )
            continue
        first = next(iter(submissions.values()))
        active = normalize_active_carriers(first["activeCarriers"])
        workloads = normalize_workloads(first["workloads"], active_carriers=active)
        unexpected = set(submissions) - set(active)
        if unexpected:
            raise ValueError(
                "campaign has submissions outside active workloads: "
                + ", ".join(sorted(unexpected))
            )
        lanes.clear()
        lanes.update(
            {
                carrier: empty_lane(
                    str(submissions.get(carrier, {}).get("executionId") or "pending")
                )
                for carrier in active
            }
        )
        missing = set(active) - set(submissions)
        if not missing:
            return submissions
        write_report(
            runtime,
            root_execution_id,
            status="awaiting_submissions",
            phase="submission",
            plan_digest=None,
            git_branch=None,
            git_commit_sha=None,
            source_digest=None,
            entity_catalog_digest=None,
            lanes=lanes,
            started_at=started_at,
            failure=None,
            active_carriers=active,
            workloads=workloads,
        )
        if time.monotonic() >= deadline:
            failure = (
                "campaign submissions timed out; missing "
                + ", ".join(sorted(missing))
            )
            write_report(
                runtime,
                root_execution_id,
                status="blocked",
                phase="submission",
                plan_digest=None,
                git_branch=None,
                git_commit_sha=None,
                source_digest=None,
                entity_catalog_digest=None,
                lanes=lanes,
                started_at=started_at,
                failure=failure,
                active_carriers=active,
                workloads=workloads,
            )
            raise TimeoutError(
                failure
            )
        time.sleep(
            min(
                CAMPAIGN_SUBMISSION_POLL_SECONDS,
                max(0.0, deadline - time.monotonic()),
            )
        )


def freeze_plan(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    submissions: dict[str, dict[str, Any]],
    *,
    execution_mode: str = "central",
    distributed_run: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    if execution_mode not in {"central", "distributed"}:
        raise ValueError(f"campaign execution mode is invalid: {execution_mode}")
    if execution_mode == "central" and distributed_run is not None:
        raise ValueError("central campaign plan forbids distributedRun")
    if execution_mode == "distributed":
        if not isinstance(distributed_run, Mapping):
            raise ValueError("distributed campaign plan requires distributedRun")
        if (
            not str(distributed_run.get("campaignRunId") or "").strip()
            or int(distributed_run.get("campaignGeneration") or 0) < 1
            or not str(distributed_run.get("campaignFencingToken") or "").startswith(
                "sha256:"
            )
        ):
            raise ValueError("distributed campaign run identity is incomplete")
    if not submissions:
        raise ValueError("campaign plan requires active submissions")
    first_submission = next(iter(submissions.values()))
    active = normalize_active_carriers(first_submission["activeCarriers"])
    workloads = normalize_workloads(
        first_submission["workloads"], active_carriers=active
    )
    if set(submissions) != set(active):
        raise ValueError("campaign submissions do not match active workloads")
    if any(
        row.get("activeCarriers") != list(active)
        or row.get("workloads") != workloads
        or int(row.get("quota") or 0) != workloads[carrier]
        for carrier, row in submissions.items()
    ):
        raise ValueError("campaign submission active workload drift")
    branches = {str(row.get("gitBranch") or "") for row in submissions.values()}
    commits = {str(row.get("gitCommitSha") or "") for row in submissions.values()}
    source_digests = {
        str((row.get("sourceDigest") or {}).get("digest") or "")
        for row in submissions.values()
    }
    catalog_digests = {
        str(row.get("entityCatalogDigest") or "") for row in submissions.values()
    }
    source_revisions = {
        str(row.get("sourceRevision") or "") for row in submissions.values()
    }
    execution_bundles = {
        json.dumps(
            row.get("executionBundle"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for row in submissions.values()
    }
    capacity_calibrations = {
        json.dumps(
            row.get("capacityCalibration"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for row in submissions.values()
    }
    if len(capacity_calibrations) != 1:
        raise ValueError("campaign lanes disagree on the capacity calibration")
    capacity_calibration = dict(first_submission["capacityCalibration"])
    assert_capacity_source_binding(capacity_calibration)
    scales = {str(row.get("scale") or "") for row in submissions.values()}
    regions = {str(row.get("regionRef") or "") for row in submissions.values()}
    semantic_selections = {
        str(row.get("semanticSelectionId") or "") for row in submissions.values()
    }
    semantic_preflights = {
        json.dumps(
            row.get("semanticPreflightReceipt"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for row in submissions.values()
    }
    if (
        len(branches) != 1
        or not next(iter(branches))
        or len(commits) != 1
        or len(source_digests) != 1
        or len(catalog_digests) != 1
        or len(source_revisions) != 1
        or not next(iter(source_revisions))
        or len(execution_bundles) != 1
        or execution_bundles == {"null"}
        or len(scales) != 1
        or not next(iter(scales))
        or len(semantic_selections) != 1
        or not next(iter(semantic_selections))
        or len(semantic_preflights) != 1
    ):
        raise ValueError(
            "campaign lanes must share one branch, commit, sourceRevision, "
            "sourceDigest, executionBundle, entityCatalogDigest, and scale"
        )
    if len(regions) != 1:
        raise ValueError("campaign lanes must share one regionRef")
    if str(submissions[active[0]].get("executionId") or "") != root_execution_id:
        raise ValueError("first active submission executionId must equal campaign root")
    (
        source_pool_binding,
        source_pool_evidence_ref,
        lane_source_pool_selections,
    ) = aggregate_plan_source_pool(submissions)
    adoption_values = [
        submissions[carrier].get(CAMPAIGN_ADOPTION_FIELD)
        for carrier in active
    ]
    reviewed_closure_adoption: dict[str, Any] | None = None
    if any(value is not None for value in adoption_values):
        if any(value is None for value in adoption_values):
            raise ValueError(
                "campaign cannot mix generate and reviewed-closure adoption lanes"
            )
        serialized = {
            json.dumps(value, ensure_ascii=False, sort_keys=True)
            for value in adoption_values
        }
        if len(serialized) != 1:
            raise ValueError("campaign adoption bindings must be byte-identical")
        reviewed_closure_adoption = dict(adoption_values[0])
        binding = validate_campaign_adoption_binding(
            reviewed_closure_adoption,
            output_root=runtime.output_root,
        )
        validate_adoption_target_identity(
            {
                "sourceRevision": next(iter(source_revisions)),
                "sourceDigest": submissions[active[0]]["sourceDigest"],
                "entityCatalogDigest": next(iter(catalog_digests)),
            },
            binding=binding,
        )
        if any(
            submissions[carrier].get("externalInputRefs")
            for carrier in active
        ):
            raise ValueError(
                "reviewed closure adoption cannot masquerade as acquisition inputs"
            )
    frozen_commit = next(iter(commits))
    frozen_source = next(iter(source_digests))
    lane_external_inputs: dict[str, dict[str, Any]] = {}
    for carrier in active:
        refs = list(submissions[carrier].get("externalInputRefs") or [])
        digest = external_inputs_digest(refs)
        if submissions[carrier].get("externalInputsDigest") != digest:
            raise ValueError(
                "GATE_BLOCK DATA.CAMPAIGN.EXTERNAL_INPUT_DIGEST_DRIFT: "
                f"{carrier} submission externalInputsDigest drift"
            )
        lane_external_inputs[carrier] = {
            "executionId": str(submissions[carrier]["executionId"]),
            "externalInputRefs": refs,
            "externalInputsDigest": digest,
        }
    aggregate_external_digest = payload_digest(
        {
            "schema": "quwoquan_data.campaign_external_input_lanes",
            "lanes": lane_external_inputs,
        }
    )
    assert_frozen_main_tree(
        runtime.repo_root,
        git_branch=next(iter(branches)),
        commit_sha=frozen_commit,
        source_digest=frozen_source,
        execution_bundle_digest=str(
            submissions[active[0]]["executionBundle"]["digest"]
        ),
    )
    stable = {
        "schema": "quwoquan_data.content_campaign_plan",
        "rootExecutionId": root_execution_id,
        "workloadMode": str(first_submission["workloadMode"]),
        "activeCarriers": list(active),
        "workloads": workloads,
        "executionMode": execution_mode,
        "scale": next(iter(scales)),
        "gitBranch": next(iter(branches)),
        "gitCommitSha": frozen_commit,
        "sourceRevision": next(iter(source_revisions)),
        "sourceDigest": frozen_source,
        "executionBundle": dict(submissions[active[0]]["executionBundle"]),
        "entityCatalogDigest": next(iter(catalog_digests)),
        "semanticSelectionId": next(iter(semantic_selections)),
        "capacityCalibration": capacity_calibration,
        "laneExternalInputs": lane_external_inputs,
        "externalInputsDigest": aggregate_external_digest,
        "submissionDigests": {
            carrier: str(submissions[carrier]["requestDigest"])
            for carrier in active
        },
        "laneRetryUnfinishedRefs": {
            carrier: list(submissions[carrier]["retryUnfinishedRefs"])
            for carrier in active
        },
        "executionIds": {
            carrier: str(submissions[carrier]["executionId"])
            for carrier in active
        },
        "frozenAt": utc_now(),
    }
    if distributed_run is not None:
        stable["distributedRun"] = {
            "campaignRunId": str(distributed_run["campaignRunId"]),
            "campaignGeneration": int(distributed_run["campaignGeneration"]),
            "campaignFencingToken": str(distributed_run["campaignFencingToken"]),
        }
    semantic_preflight = submissions[active[0]].get("semanticPreflightReceipt")
    if semantic_preflight is not None:
        stable["semanticPreflightReceipt"] = dict(semantic_preflight)
    if reviewed_closure_adoption is not None:
        stable[CAMPAIGN_ADOPTION_FIELD] = reviewed_closure_adoption
    if source_pool_binding is not None:
        stable["scaleSourcePool"] = source_pool_binding
        stable["sourcePoolEvidenceRootRef"] = source_pool_evidence_ref
        stable["laneSourcePoolSelections"] = lane_source_pool_selections
    path = plan_path(runtime, root_execution_id)
    if path.is_file():
        existing = read_json(path)
        digest = str(existing.get("planDigest") or "")
        digest_input = {
            key: value for key, value in existing.items() if key != "planDigest"
        }
        if digest != sha256_payload(digest_input):
            raise ValueError("campaign planDigest drift")
        stable_keys = set(stable) - {"frozenAt"}
        if any(existing.get(key) != stable[key] for key in stable_keys):
            raise ValueError("campaign plan is immutable and already differs")
        assert_valid(
            existing,
            "execution",
            "content_campaign_plan",
            label=f"campaign plan:{root_execution_id}",
        )
        existing_preflight = existing.get("semanticPreflightReceipt")
        if existing_preflight is not None:
            validate_semantic_preflight_binding_at(
                existing_preflight,
                semantic_selection_id=str(existing["semanticSelectionId"]),
                admitted_at=str(existing["frozenAt"]),
                output_root=runtime.output_root,
            )
        return existing, digest
    if semantic_preflight is not None:
        validate_semantic_preflight_binding_at(
            semantic_preflight,
            semantic_selection_id=next(iter(semantic_selections)),
            admitted_at=str(stable["frozenAt"]),
            output_root=runtime.output_root,
        )
    digest = sha256_payload(stable)
    plan = {**stable, "planDigest": digest}
    assert_valid(
        plan,
        "execution",
        "content_campaign_plan",
        label=f"campaign plan:{root_execution_id}",
    )
    write_json(path, plan)
    return plan, digest


__all__ = [
    "CAMPAIGN_SUBMISSION_POLL_SECONDS",
    "aggregate_status",
    "apply_receipt_fields",
    "campaign_path",
    "empty_lane",
    "freeze_plan",
    "load_publish_for_lane",
    "load_review_for_lane",
    "plan_path",
    "report_path",
    "sha256_payload",
    "utc_now",
    "wait_for_submissions",
    "write_report",
]
