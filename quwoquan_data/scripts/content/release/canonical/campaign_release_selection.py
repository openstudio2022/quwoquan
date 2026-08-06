"""Validate one immutable four-lane campaign selection and retry lineage."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.campaign_external_inputs import (
    content_source_revision,
    external_inputs_digest,
)
from content.execution.campaign_process import CAMPAIGN_CARRIERS
from content.execution.campaign_submission import campaign_root, load_submissions
from content.execution.campaign_submission_reconciliation import (
    load_reconciliation_reference,
    predecessor_campaign_root_execution_id,
)
from content.execution.identity import parse_execution_id
from content.execution.reviewed_closure_adoption_campaign_contract import (
    ADOPTION_OPERATIONS,
    CAMPAIGN_ADOPTION_FIELD,
    validate_adoption_task_binding,
    validate_campaign_adoption_binding,
)
from content.release.canonical.campaign_release_contract import (
    CampaignReleaseRoots,
    canonical_digest,
    read_regular,
    typed_error,
)
from core.schema import assert_valid


def validate_plan(
    root_id: str,
    *,
    roots: CampaignReleaseRoots,
) -> tuple[dict[str, Any], Path]:
    path = campaign_root(root_id, root=roots.campaigns_root) / "campaign_plan.json"
    plan = read_regular(path, label="campaign plan")
    try:
        assert_valid(
            plan, "execution", "content_campaign_plan", label="campaign release plan"
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise typed_error("PLAN_INVALID", str(exc), evidence=path) from exc
    if plan.get("rootExecutionId") != root_id:
        raise typed_error(
            "PLAN_IDENTITY_DRIFT", "campaign plan rootExecutionId drift", evidence=path
        )
    stable = {key: value for key, value in plan.items() if key != "planDigest"}
    if plan.get("planDigest") != canonical_digest(stable):
        raise typed_error("PLAN_DIGEST_DRIFT", "campaign planDigest drift", evidence=path)
    source_revision = content_source_revision(
        source_digest=str(plan["sourceDigest"]),
        entity_catalog_digest=str(plan["entityCatalogDigest"]),
    )
    if plan.get("sourceRevision") != source_revision:
        raise typed_error(
            "SOURCE_REVISION_DRIFT", "campaign sourceRevision drift", evidence=path
        )
    execution_ids = plan.get("executionIds")
    lane_inputs = plan.get("laneExternalInputs")
    if not isinstance(execution_ids, Mapping) or set(execution_ids) != set(
        CAMPAIGN_CARRIERS
    ):
        raise typed_error(
            "PLAN_LANES_INVALID",
            "plan must own exactly four current executionIds",
            evidence=path,
        )
    if not isinstance(lane_inputs, Mapping) or set(lane_inputs) != set(
        CAMPAIGN_CARRIERS
    ):
        raise typed_error(
            "EXTERNAL_INPUT_DRIFT",
            "plan external input lanes are incomplete",
            evidence=path,
        )
    for carrier in CAMPAIGN_CARRIERS:
        row = lane_inputs[carrier]
        refs = row.get("externalInputRefs") if isinstance(row, Mapping) else None
        if (
            not isinstance(refs, list)
            or row.get("executionId") != execution_ids[carrier]
            or row.get("externalInputsDigest") != external_inputs_digest(refs)
            or any(
                not isinstance(ref, Mapping)
                or ref.get("carrier") != carrier
                or ref.get("sourceRevision") != source_revision
                or ref.get("sourceDigest") != plan["sourceDigest"]
                or ref.get("entityCatalogDigest") != plan["entityCatalogDigest"]
                for ref in refs
            )
        ):
            raise typed_error(
                "EXTERNAL_INPUT_DRIFT",
                f"{carrier} external input binding drift",
                evidence=path,
            )
    if plan.get("externalInputsDigest") != canonical_digest(
        {"schema": "quwoquan_data.campaign_external_input_lanes", "lanes": lane_inputs}
    ):
        raise typed_error(
            "EXTERNAL_INPUT_DRIFT", "campaign externalInputsDigest drift", evidence=path
        )
    if execution_ids["homepage"] != root_id or len(set(execution_ids.values())) != 4:
        raise typed_error(
            "PLAN_LANES_INVALID",
            "plan lane identities are not four unique current executions",
            evidence=path,
        )
    adoption_document = plan.get(CAMPAIGN_ADOPTION_FIELD)
    if adoption_document is not None:
        try:
            binding = validate_campaign_adoption_binding(
                adoption_document,
                output_root=roots.output_root,
            )
            if (
                binding.adoption_receipt.target_source_revision
                != plan["sourceRevision"]
                or binding.adoption_receipt.target_source_digest != plan["sourceDigest"]
            ):
                raise ValueError(
                    "adoption target source identity differs from campaign plan"
                )
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            raise typed_error(
                "ADOPTION_BINDING_INVALID",
                str(exc),
                evidence=path,
            ) from exc
    return plan, path


def validate_submissions(
    root_id: str,
    plan: Mapping[str, Any],
    *,
    roots: CampaignReleaseRoots,
) -> dict[str, dict[str, Any]]:
    try:
        submissions = load_submissions(root_id, root=roots.campaigns_root)
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise typed_error("SUBMISSION_INVALID", str(exc)) from exc
    if set(submissions) != set(CAMPAIGN_CARRIERS):
        raise typed_error(
            "SUBMISSION_INVALID",
            "campaign must contain exactly four immutable submissions",
        )
    source_documents = {
        json.dumps(row["sourceDigest"], sort_keys=True) for row in submissions.values()
    }
    if len(source_documents) != 1:
        raise typed_error(
            "SOURCE_DIGEST_DRIFT", "submission sourceDigest documents drift"
        )
    root_vertical = parse_execution_id(root_id).vertical
    for carrier in CAMPAIGN_CARRIERS:
        row = submissions[carrier]
        lane_inputs = plan["laneExternalInputs"][carrier]
        expected = {
            "rootExecutionId": root_id,
            "executionId": plan["executionIds"][carrier],
            "requestDigest": plan["submissionDigests"][carrier],
            "sourceRevision": plan["sourceRevision"],
            "entityCatalogDigest": plan["entityCatalogDigest"],
            "externalInputsDigest": lane_inputs["externalInputsDigest"],
            "externalInputRefs": lane_inputs["externalInputRefs"],
            "gitBranch": plan["gitBranch"],
            "gitCommitSha": plan["gitCommitSha"],
        }
        if any(row.get(key) != value for key, value in expected.items()):
            raise typed_error(
                "SUBMISSION_IDENTITY_DRIFT", f"{carrier} submission differs from plan"
            )
        if (row.get("sourceDigest") or {}).get("digest") != plan["sourceDigest"]:
            raise typed_error(
                "SOURCE_DIGEST_DRIFT", f"{carrier} submission sourceDigest drift"
            )
        if parse_execution_id(str(row["executionId"])).vertical != root_vertical:
            raise typed_error(
                "SUBMISSION_IDENTITY_DRIFT",
                f"{carrier} submission vertical differs from campaign root",
            )
        adoption = plan.get(CAMPAIGN_ADOPTION_FIELD)
        if adoption is not None:
            if (
                row.get(CAMPAIGN_ADOPTION_FIELD) != adoption
                or row.get("operation") != ADOPTION_OPERATIONS[carrier]
                or row.get("retryOf") is not None
            ):
                raise typed_error(
                    "ADOPTION_BINDING_INVALID",
                    f"{carrier} adoption submission differs from frozen plan",
                )
        elif CAMPAIGN_ADOPTION_FIELD in row:
            raise typed_error(
                "ADOPTION_BINDING_INVALID",
                f"{carrier} submission adds an adoption outside the plan",
            )
    return submissions


def _target_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def retry_lineage(
    carrier: str,
    current_id: str,
    submission: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    roots: CampaignReleaseRoots,
) -> list[str]:
    if plan.get(CAMPAIGN_ADOPTION_FIELD) is not None:
        if submission.get("retryOf") is not None:
            raise typed_error(
                "RETRY_IDENTITY_DRIFT",
                f"{carrier} adoption cannot carry retryOf",
            )
        binding_path = (
            roots.tasks_root / current_id / "0.plan/reviewed_closure_adoption.json"
        )
        try:
            task_binding = read_regular(
                binding_path,
                label=f"{carrier} reviewed closure task binding",
            )
            validate_adoption_task_binding(
                task_binding,
                output_root=roots.output_root,
            )
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            raise typed_error(
                "ADOPTION_TASK_INVALID",
                str(exc),
                evidence=binding_path,
            ) from exc
        if (
            task_binding.get("planDigest") != plan["planDigest"]
            or task_binding.get(CAMPAIGN_ADOPTION_FIELD)
            != plan[CAMPAIGN_ADOPTION_FIELD]
        ):
            raise typed_error(
                "ADOPTION_TASK_INVALID",
                f"{carrier} task binding differs from frozen plan",
                evidence=binding_path,
            )
        return [current_id]
    lineage: list[str] = []
    execution_id = current_id
    source_document = submission["sourceDigest"]
    expected_vertical = parse_execution_id(current_id).vertical
    reconciliation_reference = submission.get("predecessorReconciliation")
    reconciliation_consumed = False
    while execution_id:
        if execution_id in lineage:
            raise typed_error(
                "RETRY_CYCLE", f"{carrier} retryOf cycle at {execution_id}"
            )
        try:
            identity = parse_execution_id(execution_id)
        except ValueError as exc:
            raise typed_error(
                "RETRY_IDENTITY_DRIFT", f"{carrier} retry identity is invalid"
            ) from exc
        if identity.content_type.value != carrier or identity.vertical != expected_vertical:
            raise typed_error(
                "RETRY_IDENTITY_DRIFT",
                f"{carrier} retry carrier drift at {execution_id}",
            )
        execution_root = roots.tasks_root / execution_id
        manifest_path = execution_root / "execution_manifest.json"
        target_path = execution_root / "0.plan/target_set.json"
        if not manifest_path.exists() and not target_path.exists():
            if (
                not isinstance(reconciliation_reference, Mapping)
                or reconciliation_consumed
                or len(lineage) != 1
            ):
                raise typed_error(
                    "RETRY_EVIDENCE_INVALID",
                    f"{carrier} execution evidence is missing: {execution_id}",
                    evidence=manifest_path,
                )
            try:
                receipt, receipt_path = load_reconciliation_reference(
                    reconciliation_reference,
                    output_root=roots.output_root,
                )
            except (OSError, TypeError, ValueError) as exc:
                raise typed_error(
                    "RETRY_EVIDENCE_INVALID",
                    str(exc),
                    evidence=manifest_path,
                ) from exc
            row = (receipt.get("submissions") or {}).get(carrier)
            expected_observed = {
                "sourceRevision": plan["sourceRevision"],
                "sourceDigest": source_document,
                "entityCatalogDigest": plan["entityCatalogDigest"],
            }
            scope_fields = (
                "familyRef",
                "regionRef",
                "selector",
                "quota",
                "count",
                "topic",
                "targetNames",
                "sourceProviders",
            )
            if (
                not isinstance(row, Mapping)
                or row.get("executionId") != execution_id
                or row.get("retryOf") is not None
                or receipt.get("rootExecutionId")
                != predecessor_campaign_root_execution_id(execution_id)
                or receipt.get("observedSourceIdentity") != expected_observed
                or any(row.get(key) != submission.get(key) for key in scope_fields)
            ):
                raise typed_error(
                    "RETRY_IDENTITY_DRIFT",
                    f"{carrier} submission-only predecessor binding drift",
                    evidence=receipt_path,
                )
            lineage.append(execution_id)
            reconciliation_consumed = True
            break
        if manifest_path.exists() != target_path.exists():
            raise typed_error(
                "RETRY_EVIDENCE_INVALID",
                f"{carrier} execution manifest/target-set are incomplete",
                evidence=manifest_path,
            )
        manifest = read_regular(manifest_path, label=f"{carrier} execution manifest")
        target = read_regular(target_path, label=f"{carrier} target set")
        try:
            assert_valid(
                manifest,
                "execution",
                "content_execution_manifest",
                label=f"manifest:{execution_id}",
            )
            assert_valid(
                target, "execution", "target_set", label=f"target_set:{execution_id}"
            )
        except (FileNotFoundError, TypeError, ValueError) as exc:
            raise typed_error(
                "RETRY_EVIDENCE_INVALID", str(exc), evidence=manifest_path
            ) from exc
        if (
            manifest.get("executionId") != execution_id
            or manifest.get("sourceDigest") != source_document
            or target.get("executionId") != execution_id
            or target.get("entityCatalogDigest") != plan["entityCatalogDigest"]
            or manifest.get("targetSetDigest") != _target_digest(target)
        ):
            raise typed_error(
                "RETRY_IDENTITY_DRIFT",
                f"{carrier} frozen retry inputs drift at {execution_id}",
            )
        lineage.append(execution_id)
        execution_id = str(manifest.get("retryOf") or "").strip()
    expected_retry = str(submission.get("retryOf") or "").strip()
    observed_retry = lineage[1] if len(lineage) > 1 else ""
    if expected_retry != observed_retry:
        raise typed_error(
            "RETRY_IDENTITY_DRIFT", f"{carrier} submission/manifest retryOf drift"
        )
    if reconciliation_reference is not None and not reconciliation_consumed:
        raise typed_error(
            "RETRY_IDENTITY_DRIFT",
            f"{carrier} predecessor reconciliation was not consumed",
        )
    return lineage


def validate_runtime(
    root_id: str,
    plan: Mapping[str, Any],
    *,
    roots: CampaignReleaseRoots,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    runtime_root = campaign_root(root_id, root=roots.campaigns_root) / "runtime"
    snapshot_path = runtime_root / "snapshot.json"
    snapshot = read_regular(snapshot_path, label="campaign runtime snapshot")
    run_id = str(snapshot.get("runId") or "")
    try:
        generation = int(snapshot.get("generation") or 0)
    except (TypeError, ValueError) as exc:
        raise typed_error(
            "RUNTIME_NOT_FINAL",
            "campaign runtime generation is invalid",
            evidence=snapshot_path,
        ) from exc
    token = str(snapshot.get("fencingToken") or "")
    if (
        snapshot.get("rootExecutionId") != root_id
        or not run_id
        or generation < 1
        or not token.startswith("sha256:")
        or snapshot.get("status") not in {"succeeded", "succeeded_partial"}
        or snapshot.get("phase") != "completed"
        or snapshot.get("planDigest") != plan["planDigest"]
        or snapshot.get("failure") not in {None, ""}
    ):
        raise typed_error(
            "RUNTIME_NOT_FINAL",
            "campaign runtime is not one current fenced completion",
            evidence=snapshot_path,
        )
    checkpoints: dict[str, dict[str, Any]] = {}
    for carrier in CAMPAIGN_CARRIERS:
        path = runtime_root / "lanes" / f"{carrier}.json"
        row = read_regular(path, label=f"{carrier} runtime checkpoint")
        expected = {
            "rootExecutionId": root_id,
            "runId": run_id,
            "generation": generation,
            "fencingToken": token,
            "carrier": carrier,
            "executionId": plan["executionIds"][carrier],
            "phase": "run",
            "status": "succeeded",
            "returnCode": 0,
            "executionRoot": str(
                (roots.tasks_root / plan["executionIds"][carrier]).resolve()
            ),
        }
        if any(row.get(key) != value for key, value in expected.items()):
            raise typed_error(
                "FENCE_DRIFT",
                f"{carrier} checkpoint differs from current fenced run",
                evidence=path,
            )
        checkpoints[carrier] = row
    return snapshot, checkpoints


__all__ = [
    "retry_lineage",
    "validate_plan",
    "validate_runtime",
    "validate_submissions",
]
