"""Validation primitives for submission-only campaign reconciliation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json
from core.schema import assert_valid
from core.source_digest import content_source_revision

from content.execution.campaign_process import CAMPAIGN_CARRIERS
from content.execution.campaign_submission import campaign_root
from content.execution.identity import build_execution_id, parse_execution_id

RECEIPT_SCHEMA = "quwoquan_data.campaign_submission_reconciliation_receipt"
RECEIPT_FILENAME = "submission-only-abandonment.json"
REASONS = frozenset(
    {"provider_rejected", "semantic_preflight_expired", "source_drift"}
)
ERROR_CODES = {
    "provider_rejected": "DATA.CAMPAIGN.SUBMISSION_ONLY_PROVIDER_REJECTED",
    "semantic_preflight_expired": (
        "DATA.CAMPAIGN.SUBMISSION_ONLY_SEMANTIC_PREFLIGHT_EXPIRED"
    ),
    "source_drift": "DATA.CAMPAIGN.SUBMISSION_ONLY_SOURCE_DRIFT",
}
SCOPE_FIELDS = (
    "familyRef",
    "regionRef",
    "selector",
    "quota",
    "count",
    "topic",
    "targetNames",
    "sourceProviders",
    "retryOf",
)


class CampaignSubmissionReconciliationError(ValueError):
    """Submission-only evidence is missing, mutable, or not actually abandoned."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"GATE_BLOCK {code}: {detail}")
        self.code = code


def typed(code: str, detail: str) -> CampaignSubmissionReconciliationError:
    return CampaignSubmissionReconciliationError(
        f"DATA.CAMPAIGN.SUBMISSION_RECONCILIATION_{code}", detail
    )


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def safe_regular_ref(path: Path, *, output_root: Path, label: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise typed("EVIDENCE_MISSING", f"{label} must be one regular file: {path}")
    try:
        return path.resolve().relative_to(output_root.resolve()).as_posix()
    except ValueError as exc:
        raise typed("ROOT_DRIFT", f"{label} must be below QWQ_OUTPUT_ROOT") from exc


def resolve_ref(ref: object, *, output_root: Path, label: str) -> Path:
    raw = Path(str(ref or "").strip())
    if raw.is_absolute() or not raw.parts or ".." in raw.parts:
        raise typed("ROOT_DRIFT", f"{label} is not a safe output-relative ref")
    path = output_root.resolve() / raw
    safe_regular_ref(path, output_root=output_root, label=label)
    return path


def campaigns_root(output_root: Path) -> Path:
    return output_root / "data/local/workspace/content-campaign-submissions"


def load_terminal_submission_documents(
    root_execution_id: str,
    *,
    output_root: Path,
    require_all: bool = True,
) -> dict[str, dict[str, Any]]:
    """Read immutable submission bytes solely for terminal reconciliation.

    Abandoned submissions may predate a current execution-schema hard cut.  They
    must never be normalized or returned to the active campaign loader, but the
    controller still needs a cryptographically verified lineage receipt before a
    new ``retryOf`` sequence can be created.  This reader therefore validates the
    original request digest and the closed four-carrier identity only; its result
    is consumed exclusively by the abandonment receipt path.
    """
    normalized_root = predecessor_campaign_root_execution_id(root_execution_id)
    if normalized_root != root_execution_id:
        raise typed("IDENTITY_DRIFT", "rootExecutionId must be the homepage lane")
    submissions_dir = campaigns_root(output_root) / normalized_root / "submissions"
    documents: dict[str, dict[str, Any]] = {}
    for path in (
        sorted(submissions_dir.glob("*.json")) if submissions_dir.is_dir() else ()
    ):
        safe_regular_ref(
            path,
            output_root=output_root,
            label=f"terminal submission:{path.name}",
        )
        payload = read_json(path)
        if not isinstance(payload, dict):
            raise typed("EVIDENCE_INVALID", f"submission must be an object: {path}")
        if payload.get("schema") != "quwoquan_data.content_execution_submission":
            raise typed("EVIDENCE_INVALID", f"submission schema is invalid: {path}")
        stable = {
            key: value
            for key, value in payload.items()
            if key not in {"requestDigest", "submittedAt"}
        }
        if str(payload.get("requestDigest") or "") != canonical_digest(stable):
            raise typed("DIGEST_DRIFT", f"submission requestDigest drift: {path}")
        execution_id = str(payload.get("executionId") or "")
        identity = parse_execution_id(execution_id)
        carrier = str(payload.get("carrier") or "")
        expected_path = submissions_dir / f"{execution_id}.json"
        if (
            identity.content_type.value != carrier
            or str(payload.get("rootExecutionId") or "") != normalized_root
            or path != expected_path
            or carrier in documents
        ):
            raise typed("IDENTITY_DRIFT", f"submission identity collision: {path}")
        documents[carrier] = payload
    if not documents:
        raise typed("SUBMISSIONS_INCOMPLETE", "at least one submission is required")
    if require_all and set(documents) != set(CAMPAIGN_CARRIERS):
        raise typed("SUBMISSIONS_INCOMPLETE", "exactly four submissions are required")
    return documents


def execution_roots(output_root: Path) -> Path:
    return output_root / "data/tasks"


def predecessor_campaign_root_execution_id(execution_id: str) -> str:
    identity = parse_execution_id(execution_id)
    return build_execution_id(
        run_date=identity.run_date,
        vertical=identity.vertical,
        content_type="homepage",
        intent=identity.intent,
        scope=identity.scope,
        phase=identity.phase.value,
        sequence=identity.sequence,
    )


def reconciliation_receipt_path(
    root_execution_id: str,
    *,
    output_root: Path | None = None,
) -> Path:
    resolved_output = (output_root or paths.OUTPUT_ROOT).resolve()
    return (
        campaign_root(root_execution_id, root=campaigns_root(resolved_output))
        / "reconciliation"
        / RECEIPT_FILENAME
    )


def source_identity(
    source_document: Mapping[str, Any],
    *,
    catalog_digest: str,
) -> dict[str, Any]:
    digest = str(source_document.get("digest") or "")
    return {
        "sourceRevision": content_source_revision(
            source_digest=digest,
            entity_catalog_digest=catalog_digest,
        ),
        "sourceDigest": dict(source_document),
        "entityCatalogDigest": catalog_digest,
    }


def submission_evidence(
    submissions: Mapping[str, Mapping[str, Any]],
    *,
    output_root: Path,
    root_execution_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not submissions or not set(submissions) <= set(CAMPAIGN_CARRIERS):
        raise typed("SUBMISSIONS_INCOMPLETE", "one to four submissions are required")
    representative = submissions.get("homepage") or next(iter(submissions.values()))
    root_id = str(representative.get("rootExecutionId") or "")
    if root_execution_id is not None and root_id != root_execution_id:
        raise typed("IDENTITY_DRIFT", "submission campaign root drift")
    root_identity = parse_execution_id(root_id)
    if root_identity.content_type.value != "homepage":
        raise typed("IDENTITY_DRIFT", "campaign root must be the homepage submission")
    source_documents = {
        json.dumps(row.get("sourceDigest"), sort_keys=True)
        for row in submissions.values()
    }
    source_revisions = {str(row.get("sourceRevision") or "") for row in submissions.values()}
    catalog_digests = {
        str(row.get("entityCatalogDigest") or "") for row in submissions.values()
    }
    target_sets = {
        json.dumps(row.get("targetNames"), ensure_ascii=False)
        for row in submissions.values()
    }
    if (
        len(source_documents) != 1
        or len(source_revisions) != 1
        or len(catalog_digests) != 1
        or len(target_sets) != 1
    ):
        raise typed(
            "IDENTITY_DRIFT",
            "four submissions must share source identity and exact targetNames",
        )
    original_source = representative.get("sourceDigest")
    if not isinstance(original_source, Mapping):
        raise typed("IDENTITY_DRIFT", "submission sourceDigest is invalid")
    original_identity = source_identity(
        original_source,
        catalog_digest=next(iter(catalog_digests)),
    )
    if original_identity["sourceRevision"] != next(iter(source_revisions)):
        raise typed("IDENTITY_DRIFT", "submission sourceRevision is not derived")

    evidence: dict[str, Any] = {}
    for carrier in CAMPAIGN_CARRIERS:
        if carrier not in submissions:
            continue
        row = submissions[carrier]
        execution_id = str(row.get("executionId") or "")
        identity = parse_execution_id(execution_id)
        comparable = ("run_date", "vertical", "intent", "scope", "phase", "sequence")
        if (
            identity.content_type.value != carrier
            or any(
                getattr(identity, field) != getattr(root_identity, field)
                for field in comparable
            )
            or str(row.get("rootExecutionId") or "") != root_id
        ):
            raise typed("IDENTITY_DRIFT", f"{carrier} submission scope drift")
        path = (
            campaigns_root(output_root)
            / root_id
            / "submissions"
            / f"{execution_id}.json"
        )
        evidence[carrier] = {
            "carrier": carrier,
            "executionId": execution_id,
            "submissionRef": safe_regular_ref(
                path,
                output_root=output_root,
                label=f"{carrier} submission",
            ),
            "submissionSha256": file_digest(path),
            "requestDigest": str(row["requestDigest"]),
            **{field: row.get(field) for field in SCOPE_FIELDS},
        }
    return evidence, original_identity


def execution_absence(
    root_execution_id: str,
    submissions: Mapping[str, Mapping[str, Any]],
    *,
    output_root: Path,
) -> dict[str, Any]:
    root = campaigns_root(output_root) / root_execution_id
    campaign_paths = {
        "campaignPlanExists": root / "campaign_plan.json",
        "campaignReportExists": root / "campaign_report.json",
        "runtimeDirectoryExists": root / "runtime",
        "receiptDirectoryExists": root / "receipts",
    }
    present = [name for name, path in campaign_paths.items() if path.exists()]
    if present:
        raise typed(
            "CAMPAIGN_STARTED",
            "submission-only campaign already has execution evidence: "
            + ", ".join(present),
        )
    lane_rows: list[dict[str, Any]] = []
    root_identity = parse_execution_id(root_execution_id)
    for carrier in CAMPAIGN_CARRIERS:
        row = submissions.get(carrier)
        execution_id = (
            str(row["executionId"])
            if isinstance(row, Mapping)
            else build_execution_id(
                run_date=root_identity.run_date,
                vertical=root_identity.vertical,
                content_type=carrier,
                intent=root_identity.intent,
                scope=root_identity.scope,
                phase=root_identity.phase.value,
                sequence=root_identity.sequence,
            )
        )
        execution_root = execution_roots(output_root) / execution_id
        if execution_root.exists():
            raise typed(
                "EXECUTION_EVIDENCE_PRESENT",
                f"{carrier} execution evidence exists: {execution_root}",
            )
        lane_rows.append(
            {
                "carrier": carrier,
                "executionId": execution_id,
                "executionRootRef": execution_root.relative_to(
                    output_root
                ).as_posix(),
                "executionRootExists": False,
                "executionManifestExists": False,
                "targetSetExists": False,
                "publishRefExists": False,
            }
        )
    return {**{name: False for name in campaign_paths}, "lanes": lane_rows}


def blocker_evidence(
    path: Path,
    *,
    reason: str,
    output_root: Path,
) -> dict[str, str]:
    ref = safe_regular_ref(path, output_root=output_root, label="blocker evidence")
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise typed("BLOCKER_INVALID", "blocker evidence must be valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise typed("BLOCKER_INVALID", "blocker evidence must be one JSON object")
    if reason == "provider_rejected":
        startup = payload.get("semanticAgentStartup")
        if (
            payload.get("ready") is not False
            or not isinstance(startup, Mapping)
            or startup.get("checked") is not True
            or startup.get("ready") is not False
            or not str(startup.get("provider") or "").strip()
            or not isinstance(startup.get("issues"), list)
            or not startup.get("issues")
        ):
            raise typed(
                "BLOCKER_INVALID",
                "provider rejection evidence must be one failed checked semantic startup",
            )
    if reason == "semantic_preflight_expired":
        valid_until = str(payload.get("validUntil") or "").strip()
        try:
            expiry = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
        except ValueError as exc:
            raise typed(
                "BLOCKER_INVALID",
                "expired semantic preflight evidence has invalid validUntil",
            ) from exc
        if (
            payload.get("schema") != "quwoquan_data.semantic_preflight_receipt"
            or payload.get("ready") is not True
            or expiry.tzinfo is None
            or expiry > datetime.now(timezone.utc)
        ):
            raise typed(
                "BLOCKER_INVALID",
                "expired semantic preflight evidence must be a ready receipt past validUntil",
            )
    return {"ref": ref, "sha256": file_digest(path)}


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
    if (
        not isinstance(submissions, Mapping)
        or not submissions
        or not set(submissions) <= set(CAMPAIGN_CARRIERS)
    ):
        raise typed("RECEIPT_INVALID", "reconciliation submissions are invalid")
    missing = sorted(set(CAMPAIGN_CARRIERS) - set(submissions))
    frozen_missing = receipt.get("missingSubmissions", [])
    if frozen_missing != missing:
        raise typed("RECEIPT_INVALID", "reconciliation missingSubmissions drift")
    original = receipt.get("originalSourceIdentity")
    if not isinstance(original, Mapping):
        raise typed("RECEIPT_INVALID", "original source identity is invalid")
    for carrier in CAMPAIGN_CARRIERS:
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


def load_submission_reconciliation_receipt(
    path: Path,
    *,
    output_root: Path | None = None,
) -> dict[str, Any]:
    resolved_output = (output_root or paths.OUTPUT_ROOT).resolve()
    receipt_path = path.resolve()
    safe_regular_ref(
        receipt_path,
        output_root=resolved_output,
        label="submission reconciliation receipt",
    )
    receipt = validate_receipt_document(receipt_path)
    verify_frozen_receipt_evidence(receipt, output_root=resolved_output)
    return receipt


def reconciliation_reference(
    path: Path,
    *,
    output_root: Path | None = None,
) -> dict[str, str]:
    resolved_output = (output_root or paths.OUTPUT_ROOT).resolve()
    receipt = load_submission_reconciliation_receipt(path, output_root=resolved_output)
    return {
        "predecessorRootExecutionId": str(receipt["rootExecutionId"]),
        "receiptRef": path.resolve().relative_to(resolved_output).as_posix(),
        "receiptDigest": str(receipt["receiptDigest"]),
    }


def load_reconciliation_reference(
    reference: Mapping[str, Any],
    *,
    output_root: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    resolved_output = (output_root or paths.OUTPUT_ROOT).resolve()
    try:
        assert_valid(
            dict(reference),
            "execution",
            "campaign_submission_reconciliation_ref",
            label="campaign submission reconciliation ref",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise typed("REFERENCE_INVALID", str(exc)) from exc
    path = resolve_ref(
        reference.get("receiptRef"),
        output_root=resolved_output,
        label="submission reconciliation receipt",
    )
    receipt = load_submission_reconciliation_receipt(path, output_root=resolved_output)
    if (
        reference.get("predecessorRootExecutionId") != receipt.get("rootExecutionId")
        or reference.get("receiptDigest") != receipt.get("receiptDigest")
    ):
        raise typed("REFERENCE_DRIFT", "submission reconciliation ref drift")
    return receipt, path


__all__ = [
    "ERROR_CODES",
    "REASONS",
    "RECEIPT_SCHEMA",
    "CampaignSubmissionReconciliationError",
    "blocker_evidence",
    "campaigns_root",
    "canonical_digest",
    "execution_absence",
    "load_reconciliation_reference",
    "load_submission_reconciliation_receipt",
    "load_terminal_submission_documents",
    "predecessor_campaign_root_execution_id",
    "reconciliation_receipt_path",
    "reconciliation_reference",
    "source_identity",
    "submission_evidence",
    "typed",
]
