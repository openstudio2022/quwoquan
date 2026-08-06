"""Canonical publish-ref and controller-fence projection for lane receipts."""

from __future__ import annotations

import fcntl
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid

from content.execution.campaign_external_inputs import payload_digest
from content.execution.campaign_lane_claim import (
    lane_claim_path,
    read_lane_claim,
)
from content.execution.campaign_runtime import (
    lane_checkpoint_path,
    read_lane_checkpoint,
    read_runtime_snapshot,
    runtime_snapshot_path,
)
from content.execution.campaign_submission import campaign_root
from content.execution.campaign_workspace import (
    CampaignRuntimePaths,
    lane_execution_root,
)
from content.execution.identity import parse_execution_id, validate_execution_id

PUBLISH_BINDING_FIELDS = (
    "executionPublishRef",
    "executionPublishSha256",
    "campaignRunId",
    "campaignGeneration",
    "campaignFencingToken",
)


class CampaignReceiptError(ValueError):
    """A campaign receipt cannot be bound to current canonical runtime truth."""

    def __init__(
        self, code: str, detail: str, *, evidence_path: Path | None = None
    ) -> None:
        suffix = f"; evidence={evidence_path}" if evidence_path is not None else ""
        super().__init__(f"GATE_BLOCK {code}: {detail}{suffix}")
        self.code = code
        self.evidence_path = evidence_path


@dataclass(frozen=True, slots=True)
class CampaignPublishProjection:
    publish_ref: dict[str, Any]
    binding: dict[str, Any]


def receipt_error(
    code: str,
    detail: str,
    *,
    evidence: Path | None = None,
) -> CampaignReceiptError:
    return CampaignReceiptError(
        f"DATA.CAMPAIGN.RECEIPT_{code}",
        detail,
        evidence_path=evidence,
    )


def _read_regular(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise receipt_error(
            "EVIDENCE_MISSING",
            f"{label} must be one regular file",
            evidence=path,
        )
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise receipt_error(
            "EVIDENCE_INVALID",
            f"{label} is unreadable",
            evidence=path,
        ) from exc
    if not isinstance(payload, dict):
        raise receipt_error(
            "EVIDENCE_INVALID",
            f"{label} must be an object",
            evidence=path,
        )
    return payload


def _runtime_identity(payload: Mapping[str, Any]) -> tuple[str, int, str]:
    run_id = str(payload.get("runId") or "")
    token = str(payload.get("fencingToken") or "")
    try:
        generation = int(payload.get("generation") or 0)
    except (TypeError, ValueError) as exc:
        raise receipt_error(
            "FENCE_INVALID",
            "campaign runtime generation is invalid",
        ) from exc
    if not run_id or generation < 1 or not token.startswith("sha256:"):
        raise receipt_error(
            "FENCE_INVALID",
            "campaign runtime identity is incomplete",
        )
    return run_id, generation, token


def _load_frozen_plan(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
) -> tuple[dict[str, Any], Path]:
    path = (
        campaign_root(root_execution_id, root=runtime.campaigns_root)
        / "campaign_plan.json"
    )
    plan = _read_regular(path, label="campaign plan")
    try:
        assert_valid(
            plan,
            "execution",
            "content_campaign_plan",
            label=f"campaign publish plan:{root_execution_id}",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise receipt_error("PLAN_INVALID", str(exc), evidence=path) from exc
    digest_input = {key: value for key, value in plan.items() if key != "planDigest"}
    if plan.get("planDigest") != payload_digest(digest_input):
        raise receipt_error(
            "PLAN_DIGEST_DRIFT",
            "campaign planDigest drift",
            evidence=path,
        )
    return plan, path


def _read_publish_ref(path: Path, execution_id: str) -> tuple[dict[str, Any], str]:
    if path.is_symlink() or not path.is_file():
        raise receipt_error(
            "PUBLISH_REF_MISSING",
            "execution publish_ref must be one regular file",
            evidence=path,
        )
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise receipt_error(
            "PUBLISH_REF_INVALID",
            "execution publish_ref is unreadable",
            evidence=path,
        ) from exc
    if not isinstance(payload, dict):
        raise receipt_error(
            "PUBLISH_REF_INVALID",
            "execution publish_ref must be an object",
            evidence=path,
        )
    try:
        assert_valid(
            payload,
            "execution",
            "publish_ref",
            label=f"publish_ref:{execution_id}",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise receipt_error("PUBLISH_REF_INVALID", str(exc), evidence=path) from exc
    if payload.get("executionId") != execution_id:
        raise receipt_error(
            "PUBLISH_REF_IDENTITY_DRIFT",
            "execution publish_ref executionId drift",
            evidence=path,
        )
    return payload, "sha256:" + hashlib.sha256(raw).hexdigest()


def _portable_publish_projection(
    *,
    runtime_paths: CampaignRuntimePaths,
    execution_id: str,
    run_id: str,
    generation: int,
    fencing_token: str,
) -> CampaignPublishProjection:
    publish_path = lane_execution_root(runtime_paths, execution_id) / "publish_ref.json"
    publish_ref, publish_sha256 = _read_publish_ref(publish_path, execution_id)
    try:
        portable_ref = (
            publish_path.resolve()
            .relative_to(runtime_paths.output_root.resolve())
            .as_posix()
        )
    except ValueError as exc:
        raise receipt_error(
            "PUBLISH_REF_PATH_DRIFT",
            "execution publish_ref is outside canonical output root",
            evidence=publish_path,
        ) from exc
    return CampaignPublishProjection(
        publish_ref=publish_ref,
        binding={
            "executionPublishRef": portable_ref,
            "executionPublishSha256": publish_sha256,
            "campaignRunId": run_id,
            "campaignGeneration": generation,
            "campaignFencingToken": fencing_token,
        },
    )


def _project_distributed_publish(
    *,
    runtime_paths: CampaignRuntimePaths,
    root_execution_id: str,
    execution_id: str,
    carrier: str,
    plan: Mapping[str, Any],
) -> CampaignPublishProjection:
    claim_path = lane_claim_path(runtime_paths, root_execution_id, carrier)
    lock_path = claim_path.parent / f".{carrier}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            raise receipt_error(
                "CLAIM_NOT_ACTIVE",
                f"{carrier} distributed lane lock is not held",
                evidence=lock_path,
            )
    claim_before = read_lane_claim(runtime_paths, root_execution_id, carrier)
    claim_after = read_lane_claim(runtime_paths, root_execution_id, carrier)
    if claim_before is None or claim_after is None:
        raise receipt_error(
            "CLAIM_MISSING",
            f"{carrier} distributed lane claim is missing",
            evidence=claim_path,
        )
    stable_claim_keys = (
        "claimId",
        "planDigest",
        "campaignRunId",
        "campaignGeneration",
        "campaignFencingToken",
        "carrier",
        "executionId",
    )
    if any(
        claim_before.get(key) != claim_after.get(key) for key in stable_claim_keys
    ):
        raise receipt_error(
            "FENCE_CHANGED",
            f"{carrier} distributed claim changed during publish projection",
            evidence=claim_path,
        )
    distributed = plan.get("distributedRun")
    expected = {
        "planDigest": plan["planDigest"],
        "campaignRunId": (distributed or {}).get("campaignRunId"),
        "campaignGeneration": (distributed or {}).get("campaignGeneration"),
        "campaignFencingToken": (distributed or {}).get("campaignFencingToken"),
        "carrier": carrier,
        "executionId": execution_id,
        "phase": "run",
        "status": "running",
        "executionRoot": str(lane_execution_root(runtime_paths, execution_id)),
    }
    if any(claim_after.get(key) != value for key, value in expected.items()):
        raise receipt_error(
            "CLAIM_DRIFT",
            f"{carrier} distributed claim does not own the current publish",
            evidence=claim_path,
        )
    return _portable_publish_projection(
        runtime_paths=runtime_paths,
        execution_id=execution_id,
        run_id=str(claim_after["campaignRunId"]),
        generation=int(claim_after["campaignGeneration"]),
        fencing_token=str(claim_after["campaignFencingToken"]),
    )


def project_publish_receipt(
    *,
    root_execution_id: str,
    execution_id: str,
    runtime_paths: CampaignRuntimePaths,
) -> CampaignPublishProjection:
    """Project one receipt binding exclusively from canonical runtime files."""

    root_id = validate_execution_id(root_execution_id)
    normalized = validate_execution_id(execution_id)
    carrier = parse_execution_id(normalized).content_type.value
    plan, plan_path = _load_frozen_plan(runtime_paths, root_id)
    execution_ids = plan.get("executionIds")
    if (
        plan.get("rootExecutionId") != root_id
        or not isinstance(execution_ids, Mapping)
        or execution_ids.get(carrier) != normalized
    ):
        raise receipt_error(
            "PLAN_IDENTITY_DRIFT",
            f"{carrier} execution is not the current frozen campaign lane",
            evidence=plan_path,
        )
    execution_mode = str(plan.get("executionMode") or "")
    if execution_mode == "distributed":
        return _project_distributed_publish(
            runtime_paths=runtime_paths,
            root_execution_id=root_id,
            execution_id=normalized,
            carrier=carrier,
            plan=plan,
        )
    if execution_mode != "central":
        raise receipt_error(
            "PLAN_MODE_INVALID",
            f"campaign executionMode is invalid: {execution_mode}",
            evidence=plan_path,
        )
    snapshot_path = runtime_snapshot_path(runtime_paths, root_id)
    checkpoint_path = lane_checkpoint_path(runtime_paths, root_id, carrier)
    snapshot_before = read_runtime_snapshot(runtime_paths, root_id)
    checkpoint = read_lane_checkpoint(runtime_paths, root_id, carrier)
    snapshot_after = read_runtime_snapshot(runtime_paths, root_id)
    if snapshot_before is None or snapshot_after is None:
        raise receipt_error(
            "RUNTIME_MISSING",
            "campaign runtime snapshot is missing",
            evidence=snapshot_path,
        )
    if checkpoint is None:
        raise receipt_error(
            "CHECKPOINT_MISSING",
            f"{carrier} runtime checkpoint is missing",
            evidence=checkpoint_path,
        )
    before_identity = _runtime_identity(snapshot_before)
    after_identity = _runtime_identity(snapshot_after)
    if before_identity != after_identity:
        raise receipt_error(
            "FENCE_CHANGED",
            "campaign generation changed while projecting publish receipt",
            evidence=snapshot_path,
        )
    run_id, generation, fencing_token = after_identity
    if (
        snapshot_after.get("rootExecutionId") != root_id
        or snapshot_after.get("status") != "active"
        or snapshot_after.get("phase") not in {"review", "publish"}
        or snapshot_after.get("planDigest") != plan["planDigest"]
    ):
        raise receipt_error(
            "RUNTIME_NOT_PUBLISHING",
            "campaign controller is not publishing the frozen plan",
            evidence=snapshot_path,
        )
    expected_checkpoint = {
        "rootExecutionId": root_id,
        "runId": run_id,
        "generation": generation,
        "fencingToken": fencing_token,
        "carrier": carrier,
        "executionId": normalized,
        "phase": "run",
        "status": "running",
        "executionRoot": str(lane_execution_root(runtime_paths, normalized)),
    }
    if any(checkpoint.get(key) != value for key, value in expected_checkpoint.items()):
        raise receipt_error(
            "CHECKPOINT_DRIFT",
            f"{carrier} checkpoint is not owned by the current publish generation",
            evidence=checkpoint_path,
        )
    snapshot_lane = (snapshot_after.get("lanes") or {}).get(carrier)
    if not isinstance(snapshot_lane, Mapping) or any(
        snapshot_lane.get(key) != value
        for key, value in {
            "executionId": normalized,
            "phase": "run",
            "status": "running",
        }.items()
    ):
        raise receipt_error(
            "CHECKPOINT_DRIFT",
            f"{carrier} snapshot lane is not the current running publish",
            evidence=snapshot_path,
        )
    return _portable_publish_projection(
        runtime_paths=runtime_paths,
        execution_id=normalized,
        run_id=run_id,
        generation=generation,
        fencing_token=fencing_token,
    )


def project_publish_receipt_binding(
    *,
    root_execution_id: str,
    execution_id: str,
    runtime_paths: CampaignRuntimePaths | None = None,
) -> dict[str, Any]:
    """Project publish/fence binding; callers cannot supply any binding value."""

    projection = project_publish_receipt(
        root_execution_id=root_execution_id,
        execution_id=execution_id,
        runtime_paths=runtime_paths or CampaignRuntimePaths.defaults(),
    )
    return dict(projection.binding)


__all__ = [
    "PUBLISH_BINDING_FIELDS",
    "CampaignPublishProjection",
    "CampaignReceiptError",
    "project_publish_receipt",
    "project_publish_receipt_binding",
    "receipt_error",
]
