"""Post-freeze validation for campaign submission reconciliation receipts."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json
from core.schema import assert_valid

from content.execution.campaign.lane import (
    normalize_active_carriers,
    normalize_workloads,
)

from content.execution.campaign.submission_reconciliation_contract import (
    SCOPE_FIELDS,
    campaigns_root,
    canonical_digest,
    execution_roots,
    file_digest,
    resolve_ref,
    typed,
)

def validate_receipt_document(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise typed("EVIDENCE_MISSING", f"reconciliation receipt is missing: {path}")
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise typed("RECEIPT_INVALID", "reconciliation receipt must be an object")
    try:
        assert_valid(
            payload,
            "execution",
            "campaign_submission_reconciliation_receipt",
            label=f"campaign submission reconciliation:{path}",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise typed("RECEIPT_INVALID", str(exc)) from exc
    stable = {key: value for key, value in payload.items() if key != "receiptDigest"}
    if payload.get("receiptDigest") != canonical_digest(stable):
        raise typed("DIGEST_DRIFT", f"reconciliation receipt digest drift: {path}")
    return payload


def verify_frozen_receipt_evidence(
    receipt: Mapping[str, Any],
    *,
    output_root: Path,
) -> None:
    root_id = str(receipt.get("rootExecutionId") or "")
    campaign = campaigns_root(output_root) / root_id
    forbidden = (
        campaign / "campaign_plan.json",
        campaign / "campaign_report.json",
        campaign / "runtime",
        campaign / "receipts",
    )
    if any(path.exists() for path in forbidden):
        raise typed(
            "CAMPAIGN_STARTED",
            "execution evidence appeared after submission-only reconciliation",
        )
    submissions = receipt.get("submissions")
    if not isinstance(submissions, Mapping) or not submissions:
        raise typed("RECEIPT_INVALID", "reconciliation submissions are invalid")
    try:
        active = normalize_active_carriers(receipt.get("activeCarriers") or ())
        workloads = normalize_workloads(
            receipt.get("workloads") or {},
            active_carriers=active,
        )
    except ValueError as exc:
        raise typed("RECEIPT_INVALID", str(exc)) from exc
    if receipt.get("activeCarriers") != list(active):
        raise typed("RECEIPT_INVALID", "reconciliation active workload drift")
    missing = [carrier for carrier in active if carrier not in submissions]
    frozen_missing = receipt.get("missingSubmissions", [])
    if frozen_missing != missing:
        raise typed("RECEIPT_INVALID", "reconciliation missingSubmissions drift")
    original = receipt.get("originalSourceIdentity")
    if not isinstance(original, Mapping):
        raise typed("RECEIPT_INVALID", "original source identity is invalid")
    for carrier in active:
        if carrier not in submissions:
            expected_id = next(
                row["executionId"]
                for row in receipt["executionEvidence"]["lanes"]
                if row["carrier"] == carrier
            )
            if (
                campaigns_root(output_root)
                / root_id
                / "submissions"
                / f"{expected_id}.json"
            ).exists():
                raise typed(
                    "DIGEST_DRIFT",
                    f"{carrier} missing submission appeared after reconciliation",
                )
            continue
        row = submissions[carrier]
        if not isinstance(row, Mapping) or row.get("carrier") != carrier:
            raise typed("RECEIPT_INVALID", f"{carrier} reconciliation row is invalid")
        path = resolve_ref(
            row.get("submissionRef"),
            output_root=output_root,
            label=f"{carrier} submission",
        )
        payload = read_json(path)
        if (
            file_digest(path) != row.get("submissionSha256")
            or not isinstance(payload, Mapping)
            or payload.get("rootExecutionId") != root_id
            or payload.get("executionId") != row.get("executionId")
            or payload.get("carrier") != carrier
            or (
                payload.get("activeCarriers") is not None
                and payload.get("activeCarriers") != list(active)
            )
            or (
                payload.get("workloads") is not None
                and payload.get("workloads") != workloads
            )
            or payload.get("requestDigest") != row.get("requestDigest")
            or any(payload.get(field) != row.get(field) for field in SCOPE_FIELDS)
            or payload.get("sourceRevision") != original.get("sourceRevision")
            or payload.get("sourceDigest") != original.get("sourceDigest")
            or payload.get("entityCatalogDigest") != original.get("entityCatalogDigest")
        ):
            raise typed("DIGEST_DRIFT", f"{carrier} reconciled submission drift")
        if (
            execution_roots(output_root) / str(row.get("executionId") or "")
        ).exists():
            raise typed(
                "EXECUTION_EVIDENCE_PRESENT",
                f"{carrier} execution evidence appeared after reconciliation",
            )
    blocker = receipt.get("blockerEvidence")
    if not isinstance(blocker, Mapping):
        raise typed("RECEIPT_INVALID", "blocker evidence binding is invalid")
    blocker_path = resolve_ref(
        blocker.get("ref"), output_root=output_root, label="blocker evidence"
    )
    if file_digest(blocker_path) != blocker.get("sha256"):
        raise typed("DIGEST_DRIFT", "blocker evidence digest drift")
