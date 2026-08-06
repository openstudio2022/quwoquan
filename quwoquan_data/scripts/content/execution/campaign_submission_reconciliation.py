"""Create-once lineage for a four-lane campaign that never created executions."""

from __future__ import annotations

import argparse
import fcntl
import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import paths
from core.io import write_json
from core.schema import assert_valid
from core.source_digest import content_source_revision, current_source_digest

from content.execution.campaign_process import CAMPAIGN_CARRIERS
from content.execution.campaign_submission_reconciliation_contract import (
    ERROR_CODES,
    REASONS,
    RECEIPT_SCHEMA,
    CampaignSubmissionReconciliationError,
    canonical_digest,
    execution_absence,
    load_reconciliation_reference,
    load_submission_reconciliation_receipt,
    load_terminal_submission_documents,
    predecessor_campaign_root_execution_id,
    reconciliation_receipt_path,
    reconciliation_reference,
    source_identity,
    submission_evidence,
    typed,
)
from content.execution.campaign_submission_reconciliation_contract import (
    blocker_evidence as freeze_blocker_evidence,
)
from content.execution.identity import parse_execution_id
from content.execution.workspace import entity_catalog_digest


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _reconciliation_lock(path: Path) -> Iterator[None]:
    lock = path.parent / ".lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load_reconciled_predecessor_submission(
    execution_id: str,
    *,
    output_root: Path | None = None,
) -> dict[str, Any] | None:
    resolved_output = (output_root or paths.OUTPUT_ROOT).resolve()
    identity = parse_execution_id(execution_id)
    root_id = predecessor_campaign_root_execution_id(execution_id)
    path = reconciliation_receipt_path(root_id, output_root=resolved_output)
    if not path.is_file():
        return None
    receipt = load_submission_reconciliation_receipt(
        path,
        output_root=resolved_output,
    )
    row = receipt["submissions"].get(identity.content_type.value)
    if row is None:
        return None
    if not isinstance(row, Mapping) or row.get("executionId") != identity.execution_id:
        raise typed(
            "REFERENCE_DRIFT",
            f"receipt does not bind predecessor {identity.execution_id}",
        )
    return dict(row)


def assert_campaign_not_reconciled(
    root_execution_id: str,
    *,
    output_root: Path | None = None,
) -> None:
    resolved_output = (output_root or paths.OUTPUT_ROOT).resolve()
    path = reconciliation_receipt_path(
        root_execution_id,
        output_root=resolved_output,
    )
    if not path.is_file():
        return
    receipt = load_submission_reconciliation_receipt(
        path,
        output_root=resolved_output,
    )
    raise typed(
        "TERMINAL",
        "campaign submissions are already abandoned; create a new four-lane "
        f"sequence with retryOf; receiptDigest={receipt['receiptDigest']}",
    )


def reconcile_submission_only_campaign(
    root_execution_id: str,
    *,
    reason: str,
    blocker_evidence: Path,
    repo_root: Path | None = None,
    output_root: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Abandon four immutable submissions only when no execution ever started."""

    normalized_reason = str(reason or "").strip()
    if normalized_reason not in REASONS:
        raise typed(
            "REASON_INVALID",
            "reason must be provider_rejected, semantic_preflight_expired, or source_drift",
        )
    source_repo = (repo_root or paths.REPO_ROOT).resolve()
    resolved_output = (output_root or paths.OUTPUT_ROOT).resolve()
    root_id = predecessor_campaign_root_execution_id(root_execution_id)
    if root_id != root_execution_id:
        raise typed("IDENTITY_DRIFT", "rootExecutionId must be the homepage lane")
    submissions = load_terminal_submission_documents(
        root_id,
        output_root=resolved_output,
        require_all=False,
    )
    submission_rows, original_identity = submission_evidence(
        submissions,
        output_root=resolved_output,
        root_execution_id=root_id,
    )
    missing_submissions = sorted(set(CAMPAIGN_CARRIERS) - set(submissions))
    absence = execution_absence(
        root_id,
        submissions,
        output_root=resolved_output,
    )
    blocker_path = blocker_evidence.expanduser()
    if not blocker_path.is_absolute():
        blocker_path = source_repo / blocker_path
    blocker = freeze_blocker_evidence(
        blocker_path.resolve(),
        reason=normalized_reason,
        output_root=resolved_output,
    )
    receipt_path = reconciliation_receipt_path(
        root_id,
        output_root=resolved_output,
    )
    with _reconciliation_lock(receipt_path):
        if receipt_path.is_file():
            existing = load_submission_reconciliation_receipt(
                receipt_path,
                output_root=resolved_output,
            )
            expected = {
                "rootExecutionId": root_id,
                "reason": normalized_reason,
                "errorCode": ERROR_CODES[normalized_reason],
                "originalSourceIdentity": original_identity,
                "submissions": submission_rows,
                "executionEvidence": absence,
                "blockerEvidence": blocker,
            }
            if missing_submissions:
                expected["missingSubmissions"] = missing_submissions
            if any(existing.get(key) != value for key, value in expected.items()):
                raise typed("CREATE_ONCE_COLLISION", "existing receipt differs")
            return existing, receipt_path

        observed_source = current_source_digest(repo_root=source_repo).to_document()
        representative = submissions.get("homepage") or next(iter(submissions.values()))
        discovery = (
            source_repo
            / "quwoquan_data/reference"
            / parse_execution_id(root_id).vertical
            / "entities"
            / str(representative["regionRef"])
        )
        catalog_digest = entity_catalog_digest(
            discovery.relative_to(source_repo).as_posix()
        )
        observed_identity = source_identity(
            observed_source,
            catalog_digest=catalog_digest,
        )
        if normalized_reason == "source_drift" and observed_identity == original_identity:
            raise typed(
                "REASON_INVALID",
                "source_drift requires identity drift between submission and observation",
            )
        stable = {
            "schema": RECEIPT_SCHEMA,
            "rootExecutionId": root_id,
            "decision": "abandoned",
            "reason": normalized_reason,
            "errorCode": ERROR_CODES[normalized_reason],
            "originalSourceIdentity": original_identity,
            "observedSourceIdentity": observed_identity,
            "submissions": submission_rows,
            "executionEvidence": absence,
            "blockerEvidence": blocker,
            "retryPolicy": "new_four_lane_execution_with_retryOf",
            "recordedAt": _now(),
        }
        if missing_submissions:
            stable["missingSubmissions"] = missing_submissions
        receipt = {**stable, "receiptDigest": canonical_digest(stable)}
        try:
            assert_valid(
                receipt,
                "execution",
                "campaign_submission_reconciliation_receipt",
                label=f"campaign submission reconciliation:{root_id}",
            )
        except (FileNotFoundError, TypeError, ValueError) as exc:
            raise typed("RECEIPT_INVALID", str(exc)) from exc
        if current_source_digest(repo_root=source_repo).to_document() != observed_source:
            raise typed("SOURCE_DRIFT", "observed source changed while writing receipt")
        write_json(receipt_path, receipt)
        return receipt, receipt_path


def _handle(args: argparse.Namespace) -> None:
    receipt, path = reconcile_submission_only_campaign(
        str(args.campaign_root_execution_id),
        reason=str(args.reason),
        blocker_evidence=Path(str(args.blocker_evidence)),
    )
    representative = receipt["submissions"].get("homepage") or next(
        iter(receipt["submissions"].values())
    )
    summary = {
        "rootExecutionId": receipt["rootExecutionId"],
        "decision": receipt["decision"],
        "reason": receipt["reason"],
        "errorCode": receipt["errorCode"],
        "originalSourceIdentity": receipt["originalSourceIdentity"],
        "observedSourceIdentity": receipt["observedSourceIdentity"],
        "predecessorExecutionIds": {
            carrier: receipt["submissions"][carrier]["executionId"]
            for carrier in CAMPAIGN_CARRIERS
            if carrier in receipt["submissions"]
        },
        "missingSubmissions": receipt.get("missingSubmissions", []),
        "targetNames": representative["targetNames"],
        "blockerEvidence": receipt["blockerEvidence"],
        "receiptRef": path.resolve().relative_to(paths.OUTPUT_ROOT.resolve()).as_posix(),
        "receiptDigest": receipt["receiptDigest"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def register_reconcile_submissions_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    parser = subparsers.add_parser(
        "reconcile-submissions",
        help="收敛从未创建 execution 的四路 submissions",
    )
    parser.add_argument("--campaign-root-execution-id", required=True)
    parser.add_argument("--reason", required=True, choices=tuple(sorted(REASONS)))
    parser.add_argument("--blocker-evidence", required=True)
    parser.set_defaults(handler=_handle)


__all__ = [
    "CampaignSubmissionReconciliationError",
    "assert_campaign_not_reconciled",
    "content_source_revision",
    "load_reconciled_predecessor_submission",
    "load_reconciliation_reference",
    "load_submission_reconciliation_receipt",
    "predecessor_campaign_root_execution_id",
    "reconcile_submission_only_campaign",
    "reconciliation_receipt_path",
    "reconciliation_reference",
    "register_reconcile_submissions_parser",
]
