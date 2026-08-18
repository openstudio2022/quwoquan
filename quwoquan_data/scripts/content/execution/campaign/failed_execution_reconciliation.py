"""Create-once supersession for a campaign whose four lanes failed terminally."""

from __future__ import annotations

import argparse
import fcntl
import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.execution.campaign.process import CAMPAIGN_CARRIERS
from content.execution.campaign.runtime_process import _pid_alive
from content.execution.campaign.submission_reconciliation_contract import (
    campaigns_root,
    canonical_digest,
    file_digest,
    load_terminal_submission_documents,
    predecessor_campaign_root_execution_id,
    reconciliation_receipt_path,
    resolve_ref,
    safe_regular_ref,
    source_identity,
    submission_evidence,
    typed,
)
from content.execution.identity import parse_execution_id
from content.execution.workspace import entity_catalog_digest
from core import paths
from core.io import read_json, write_json
from core.schema import assert_valid
from core.source_digest import current_source_digest

SCHEMA = "quwoquan_data.campaign_failed_execution_reconciliation_receipt"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _lock(path: Path) -> Iterator[None]:
    lock = path.parent / ".lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _file_binding(path: Path, *, output_root: Path, label: str) -> dict[str, str]:
    return {
        "ref": safe_regular_ref(
            path,
            output_root=output_root,
            label=label,
        ),
        "sha256": file_digest(path),
    }


def _failed_campaign_evidence(
    root_id: str,
    *,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    campaign = campaigns_root(output_root) / root_id
    plan_path = campaign / "campaign_plan.json"
    report_path = campaign / "campaign_report.json"
    runtime_path = campaign / "runtime/snapshot.json"
    plan = read_json(plan_path)
    report = read_json(report_path)
    runtime = read_json(runtime_path)
    if not all(isinstance(item, Mapping) for item in (plan, report, runtime)):
        raise typed("CAMPAIGN_EVIDENCE_INVALID", "campaign evidence must be objects")
    frozen_boundary = (
        runtime.get("status") == "frozen"
        and bool(runtime.get("finishedAt"))
    )
    interrupted_successor = (
        runtime.get("status") == "interrupted"
        and runtime.get("phase") == "controller"
        and bool(runtime.get("finishedAt"))
        and runtime.get("planDigest") is None
        and runtime.get("lanes") == {}
        and runtime.get("failure")
        == "ValueError: campaign plan is immutable and already differs"
        and int(runtime.get("generation") or 0)
        == int(report.get("campaignGeneration") or 0) + 1
        and runtime.get("runId") != report.get("campaignRunId")
    )
    if (
        plan.get("rootExecutionId") != root_id
        or report.get("rootExecutionId") != root_id
        or runtime.get("rootExecutionId") != root_id
        or not (frozen_boundary or interrupted_successor)
        or report.get("phase") != "capsule"
    ):
        raise typed(
            "CAMPAIGN_EVIDENCE_INVALID",
            "campaign did not stop at one frozen capsule boundary",
        )
    shared = (
        ("planDigest", "planDigest"),
        ("campaignRunId", "runId"),
        ("campaignGeneration", "generation"),
        ("campaignFencingToken", "fencingToken"),
    )
    if frozen_boundary and any(
        report.get(left) != runtime.get(right) for left, right in shared
    ):
        raise typed("CAMPAIGN_EVIDENCE_INVALID", "campaign runtime identity drifted")
    claims: dict[str, dict[str, str]] = {}
    report_lanes = report.get("lanes")
    if not isinstance(report_lanes, Mapping):
        raise typed("CAMPAIGN_EVIDENCE_INVALID", "campaign report lanes are invalid")
    for carrier in CAMPAIGN_CARRIERS:
        claim_path = campaign / "claims" / f"{carrier}.json"
        claim = read_json(claim_path)
        lane = report_lanes.get(carrier)
        terminal_failed = (
            isinstance(claim, Mapping)
            and claim.get("status") == "failed"
            and bool(claim.get("finishedAt"))
            and (
                claim.get("returnCode") != 0
                or bool(str(claim.get("error") or "").strip())
            )
        )
        stale_interrupted = (
            isinstance(claim, Mapping)
            and claim.get("status") in {"active", "starting", "running"}
            and isinstance(claim.get("returnCode"), int)
            and claim.get("returnCode") != 0
            and claim.get("terminationOwner") == "lane_process"
            and not _pid_alive(claim.get("pid"))
            and not _pid_alive(claim.get("pgid"))
        )
        if (
            not isinstance(claim, Mapping)
            or not isinstance(lane, Mapping)
            or claim.get("rootExecutionId") != root_id
            or claim.get("carrier") != carrier
            or not (terminal_failed or stale_interrupted)
            or (terminal_failed and claim.get("phase") != "completed")
            or (
                stale_interrupted
                and claim.get("phase") not in {"review-only", "run"}
            )
            or not isinstance(claim.get("returnCode"), int)
            or lane.get("status") != "capsule_ready"
            or lane.get("phase") != "capsule"
            or lane.get("reviewReturnCode") is not None
            or lane.get("publishReturnCode") is not None
            or any(
                lane.get(field) is not None
                for field in (
                    "approvedQuota",
                    "qualifiedCount",
                    "finalizedCount",
                    "selectedCount",
                    "discardedCount",
                    "shortfallCount",
                )
            )
        ):
            raise typed(
                "CAMPAIGN_NOT_TERMINAL_FAILED",
                f"{carrier} is not a terminal pre-execution failure",
            )
        claims[carrier] = _file_binding(
            claim_path,
            output_root=output_root,
            label=f"{carrier} failed claim",
        )
    return (
        {
            "plan": _file_binding(
                plan_path,
                output_root=output_root,
                label="campaign plan",
            ),
            "report": _file_binding(
                report_path,
                output_root=output_root,
                label="campaign report",
            ),
            "runtimeSnapshot": _file_binding(
                runtime_path,
                output_root=output_root,
                label="campaign runtime snapshot",
            ),
            "claims": claims,
        },
        dict(report),
    )


def _execution_absence(
    submissions: Mapping[str, Mapping[str, Any]],
    *,
    output_root: Path,
) -> dict[str, Any]:
    lanes: list[dict[str, Any]] = []
    for carrier in CAMPAIGN_CARRIERS:
        execution_id = str(submissions[carrier]["executionId"])
        execution_root = output_root / "data/tasks" / execution_id
        if execution_root.exists():
            raise typed(
                "EXECUTION_EVIDENCE_PRESENT",
                f"{carrier} execution root must be discarded first",
            )
        lanes.append(
            {
                "carrier": carrier,
                "executionId": execution_id,
                "executionRootRef": f"data/tasks/{execution_id}",
                "executionRootExists": False,
                "executionManifestExists": False,
                "targetSetExists": False,
                "publishRefExists": False,
            }
        )
    return {"lanes": lanes}


def validate_failed_campaign_reconciliation_receipt(
    path: Path,
    *,
    output_root: Path,
) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise typed("RECEIPT_INVALID", "failed campaign receipt must be an object")
    try:
        assert_valid(
            payload,
            "execution",
            "campaign_failed_execution_reconciliation_receipt",
            label=f"failed campaign reconciliation:{path}",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise typed("RECEIPT_INVALID", str(exc)) from exc
    stable = {key: value for key, value in payload.items() if key != "receiptDigest"}
    if payload.get("receiptDigest") != canonical_digest(stable):
        raise typed("DIGEST_DRIFT", "failed campaign receipt digest drifted")
    root_id = str(payload["rootExecutionId"])
    submissions = load_terminal_submission_documents(
        root_id,
        output_root=output_root,
        require_all=True,
    )
    rows, original = submission_evidence(
        submissions,
        output_root=output_root,
        root_execution_id=root_id,
    )
    campaign_evidence, report = _failed_campaign_evidence(
        root_id,
        output_root=output_root,
    )
    absence = _execution_absence(submissions, output_root=output_root)
    if (
        payload.get("submissions") != rows
        or payload.get("originalSourceIdentity") != original
        or payload.get("campaignEvidence") != campaign_evidence
        or payload.get("executionEvidence") != absence
        or report.get("sourceDigest") != original["sourceDigest"]["digest"]
        or report.get("entityCatalogDigest") != original["entityCatalogDigest"]
    ):
        raise typed("DIGEST_DRIFT", "failed campaign reconciliation evidence drifted")
    blocker = payload.get("blockerEvidence")
    blocker_path = resolve_ref(
        blocker.get("ref"),
        output_root=output_root,
        label="failed campaign blocker evidence",
    )
    if file_digest(blocker_path) != blocker.get("sha256"):
        raise typed("DIGEST_DRIFT", "failed campaign blocker evidence drifted")
    return payload


def reconcile_failed_campaign(
    root_execution_id: str,
    *,
    blocker_evidence: Path,
    repo_root: Path | None = None,
    output_root: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    source_repo = (repo_root or paths.REPO_ROOT).resolve()
    resolved_output = (output_root or paths.OUTPUT_ROOT).resolve()
    root_id = predecessor_campaign_root_execution_id(root_execution_id)
    if root_id != root_execution_id:
        raise typed("IDENTITY_DRIFT", "rootExecutionId must be the homepage lane")
    submissions = load_terminal_submission_documents(
        root_id,
        output_root=resolved_output,
        require_all=True,
    )
    rows, original = submission_evidence(
        submissions,
        output_root=resolved_output,
        root_execution_id=root_id,
    )
    campaign_evidence, report = _failed_campaign_evidence(
        root_id,
        output_root=resolved_output,
    )
    absence = _execution_absence(submissions, output_root=resolved_output)
    observed_source = current_source_digest(repo_root=source_repo).to_document()
    representative = submissions["homepage"]
    discovery = (
        source_repo
        / "quwoquan_data/reference"
        / parse_execution_id(root_id).vertical
        / "entities"
        / str(representative["regionRef"])
    )
    observed = source_identity(
        observed_source,
        catalog_digest=entity_catalog_digest(
            discovery.relative_to(source_repo).as_posix()
        ),
    )
    if observed == original:
        raise typed("REASON_INVALID", "failed campaign source identity has not drifted")
    blocker_path = blocker_evidence.expanduser()
    if not blocker_path.is_absolute():
        blocker_path = source_repo / blocker_path
    blocker = _file_binding(
        blocker_path.resolve(),
        output_root=resolved_output,
        label="failed campaign blocker evidence",
    )
    if report.get("sourceDigest") != original["sourceDigest"]["digest"]:
        raise typed("IDENTITY_DRIFT", "campaign report source digest drifted")
    receipt_path = reconciliation_receipt_path(
        root_id,
        output_root=resolved_output,
    )
    stable = {
        "schema": SCHEMA,
        "rootExecutionId": root_id,
        "decision": "superseded",
        "reason": "source_drift",
        "errorCode": "DATA.CAMPAIGN.FAILED_EXECUTION_SOURCE_DRIFT",
        "originalSourceIdentity": original,
        "observedSourceIdentity": observed,
        "submissions": rows,
        "campaignEvidence": campaign_evidence,
        "executionEvidence": absence,
        "blockerEvidence": blocker,
        "retryPolicy": "new_four_lane_execution_with_retryOf",
        "recordedAt": _now(),
    }
    receipt = {**stable, "receiptDigest": canonical_digest(stable)}
    assert_valid(
        receipt,
        "execution",
        "campaign_failed_execution_reconciliation_receipt",
        label=f"failed campaign reconciliation:{root_id}",
    )
    with _lock(receipt_path):
        if receipt_path.is_file():
            existing = validate_failed_campaign_reconciliation_receipt(
                receipt_path,
                output_root=resolved_output,
            )
            if (
                existing.get("rootExecutionId") != root_id
                or existing.get("blockerEvidence") != blocker
            ):
                raise typed("CREATE_ONCE_COLLISION", "existing failed receipt differs")
            return existing, receipt_path
        write_json(receipt_path, receipt)
    validate_failed_campaign_reconciliation_receipt(
        receipt_path,
        output_root=resolved_output,
    )
    return receipt, receipt_path


def _handle(args: argparse.Namespace) -> None:
    receipt, path = reconcile_failed_campaign(
        str(args.campaign_root_execution_id),
        blocker_evidence=Path(str(args.blocker_evidence)),
    )
    print(
        json.dumps(
            {
                "rootExecutionId": receipt["rootExecutionId"],
                "decision": receipt["decision"],
                "reason": receipt["reason"],
                "predecessorExecutionIds": {
                    carrier: receipt["submissions"][carrier]["executionId"]
                    for carrier in CAMPAIGN_CARRIERS
                },
                "receiptRef": path.relative_to(paths.OUTPUT_ROOT).as_posix(),
                "receiptDigest": receipt["receiptDigest"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def register_reconcile_failed_campaign_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    parser = subparsers.add_parser(
        "reconcile-failed-campaign",
        help="在四路 terminal failure 且 execution roots 已清理后写 source-bound supersession",
    )
    parser.add_argument("--campaign-root-execution-id", required=True)
    parser.add_argument("--blocker-evidence", required=True)
    parser.set_defaults(handler=_handle)


__all__ = [
    "reconcile_failed_campaign",
    "register_reconcile_failed_campaign_parser",
    "validate_failed_campaign_reconciliation_receipt",
]
