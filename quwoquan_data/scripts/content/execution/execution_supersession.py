"""Create-once supersession for historical execution evidence.

Supersession never rewrites a historical manifest, request, state, or object.
It only proves that the frozen execution cannot resume under the current source
identity and that its bytes remain protected for audit/retry lineage.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json
from core.schema import assert_valid
from core.source_digest import (
    SourceDefinitionSnapshot,
    SourceDigest,
    SourceDigestError,
    current_source_definition_snapshot,
    current_source_digest,
)

from content.execution.operational_fingerprint import operational_fingerprint

from content.execution.closure.execution_supersession_admission import (
    _RETIRED_MANAGED_STATE_SCHEMA,
    _completion_evidence_binding,
    _lease_disposition,
    _process_evidence,
    _settled_execution_state,
    _validate_pre_controller_closure,
    _workflow_drift_state_status,
)
from content.execution.closure.execution_supersession_inventory import (
    _ANCHOR_REFS,
    _LIVENESS_PROBE,
    _anchors,
    _digest,
    _optional_object,
    _path_exists,
    _root_inventory,
)
from content.execution.identity import validate_execution_id

_REASONS = frozenset(
    {
        "source_drift",
        "workflow_drift",
        "missing_canonical_input",
        "unbound_completion_evidence",
    }
)
_ERROR_CODES = {
    "source_drift": "DATA.EXECUTION.SOURCE_DRIFT_SUPERSEDED",
    "workflow_drift": "DATA.EXECUTION.WORKFLOW_DRIFT_SUPERSEDED",
    "missing_canonical_input": "DATA.EXECUTION.MISSING_CANONICAL_INPUT_SUPERSEDED",
    "unbound_completion_evidence": (
        "DATA.EXECUTION.UNBOUND_COMPLETION_EVIDENCE_SUPERSEDED"
    ),
}


@contextmanager
def _lock(root: Path) -> Iterator[None]:
    path = root / "_shared/reconciliation/.lock"
    shared = path.parent.parent
    reconciliation = path.parent
    if _path_exists(shared) and (shared.is_symlink() or not shared.is_dir()):
        raise ValueError("execution supersession _shared root is corrupt")
    if _path_exists(reconciliation) and (
        reconciliation.is_symlink() or not reconciliation.is_dir()
    ):
        raise ValueError("execution supersession reconciliation root is corrupt")
    path.parent.mkdir(parents=True, exist_ok=True)
    if _path_exists(path) and (path.is_symlink() or not path.is_file()):
        raise ValueError("execution supersession lock is corrupt")
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def validate_execution_supersession_receipt(
    document: Mapping[str, Any],
    *,
    path: Path,
    execution_root: Path,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    receipt = dict(document)
    assert_valid(
        receipt,
        "execution",
        "execution_supersession_receipt",
        label=f"execution supersession receipt:{path}",
    )
    stable = {key: value for key, value in receipt.items() if key != "receiptDigest"}
    if receipt["receiptDigest"] != _digest(stable):
        raise ValueError(f"execution supersession receipt digest drift: {path}")
    if receipt["executionId"] != execution_root.name:
        raise ValueError("execution supersession executionId drift")
    if receipt["errorCode"] != _ERROR_CODES[receipt["reason"]]:
        raise ValueError("execution supersession error code does not match its reason")
    workflow_fields = (
        "manifestOperationalFingerprint",
        "observedOperationalFingerprint",
    )
    workflow_values = tuple(receipt.get(field) for field in workflow_fields)
    if receipt["reason"] == "workflow_drift":
        manifest = _optional_object(
            execution_root / _ANCHOR_REFS["executionManifest"]
        )
        if manifest is None:
            raise ValueError("workflow_drift supersession requires an execution manifest")
        manifest_fingerprint = _operational_fingerprint(
            manifest.get("operationalFingerprint"),
            label="execution manifest operationalFingerprint",
        )
        current_fingerprint = _operational_fingerprint(
            operational_fingerprint(
                repo_root=(repo_root or paths.REPO_ROOT).resolve()
            ),
            label="current operational fingerprint",
        )
        if workflow_values != (manifest_fingerprint, current_fingerprint):
            raise ValueError("execution supersession workflow fingerprint binding drift")
        if manifest_fingerprint == current_fingerprint:
            raise ValueError("workflow_drift supersession requires operational drift")
        state = _settled_execution_state(execution_root)
        if state is None:
            raise ValueError("workflow_drift supersession requires execution state")
        previous_status = _workflow_drift_state_status(execution_root, state)
        if receipt["previousStatus"] != previous_status:
            raise ValueError("execution supersession previous status drift")
    elif any(value is not None for value in workflow_values):
        raise ValueError(
            "execution supersession carries workflow fingerprint binding without "
            "the reason that proves it"
        )
    binding = receipt.get("completionEvidenceBinding")
    if receipt["reason"] == "unbound_completion_evidence":
        if binding != _completion_evidence_binding(execution_root):
            raise ValueError("execution supersession completion evidence binding drift")
    elif binding is not None:
        raise ValueError(
            "execution supersession carries a completion evidence binding without "
            "the reason that proves it"
        )
    anchors = _anchors(execution_root)
    if receipt["evidenceAnchors"] != anchors:
        raise ValueError("execution supersession evidence anchor drift")
    expected_evidence_digest = _digest(anchors)
    if receipt["evidenceDigest"] != expected_evidence_digest:
        raise ValueError("execution supersession evidence digest drift")
    expected_name = f"supersession-{expected_evidence_digest.removeprefix('sha256:')}.json"
    if path.name != expected_name:
        raise ValueError("execution supersession receipt path drift")
    root_fields = ("rootInventoryDigest", "rootInventoryEntryCount", "stateEvidence")
    present_root_fields = tuple(field for field in root_fields if field in receipt)
    if present_root_fields and len(present_root_fields) != len(root_fields):
        raise ValueError("execution supersession root evidence is incomplete")
    if present_root_fields:
        inventory, inventory_digest = _root_inventory(execution_root)
        if receipt["rootInventoryDigest"] != inventory_digest:
            raise ValueError("execution supersession root inventory drift")
        if receipt["rootInventoryEntryCount"] != len(inventory):
            raise ValueError("execution supersession root inventory count drift")
        state_path = execution_root / _ANCHOR_REFS["executionState"]
        if not state_path.is_file():
            expected_state_evidence = {"missing_pre_controller"}
        else:
            snapshot = _optional_object(state_path)
            if (
                isinstance(snapshot, Mapping)
                and snapshot.get("schema") == _RETIRED_MANAGED_STATE_SCHEMA
            ):
                # 早于本契约区分的不可变历史收据记录的是 settled_snapshot；
                # 收据 create-once，不得追溯改写，因此两个值都合法。
                expected_state_evidence = {
                    "settled_snapshot",
                    "settled_retired_managed_snapshot",
                }
            else:
                expected_state_evidence = {"settled_snapshot"}
        if receipt["stateEvidence"] not in expected_state_evidence:
            raise ValueError("execution supersession state evidence drift")
        if receipt["processEvidence"].get("livenessProbe") != _LIVENESS_PROBE:
            raise ValueError("execution supersession liveness probe drift")
    lease = _optional_object(execution_root / _ANCHOR_REFS["controllerLease"])
    if receipt["controllerLeaseDisposition"] != _lease_disposition(lease):
        raise ValueError("execution supersession controller lease disposition drift")
    source = receipt.get("manifestSourceDigest")
    source_kind = None
    if source is not None:
        source_kind = _source_identity_kind(source)
    observed_kind = _source_identity_kind(receipt["observedSourceDigest"])
    if source_kind is not None and source_kind != observed_kind:
        raise ValueError("execution supersession source identity kind drift")
    return receipt


def _operational_fingerprint(value: object, *, label: str) -> str:
    fingerprint = str(value or "")
    if (
        len(fingerprint) != 71
        or not fingerprint.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in fingerprint[7:])
    ):
        raise ValueError(f"{label} must be sha256:<64 lowercase hex>")
    return fingerprint


def _source_identity_kind(document: object) -> str:
    """Validate one v1 or v2 source identity without weakening either shape."""

    try:
        SourceDefinitionSnapshot.from_document(document)
        return "source_definition_snapshot"
    except SourceDigestError:
        SourceDigest.from_document(document)
        return "source_digest_v1"


def load_execution_supersession_receipt(
    execution_root: Path,
    *,
    repo_root: Path | None = None,
) -> tuple[dict[str, Any], Path] | None:
    candidates = sorted(
        (execution_root / "_shared/reconciliation").glob("supersession-*.json")
    )
    if not candidates:
        return None
    if len(candidates) != 1:
        raise ValueError("execution has multiple supersession receipts")
    path = candidates[0]
    value = read_json(path)
    if not isinstance(value, dict):
        raise TypeError("execution supersession receipt must be an object")
    return (
        validate_execution_supersession_receipt(
            value,
            path=path,
            execution_root=execution_root,
            repo_root=repo_root,
        ),
        path,
    )


def supersede_execution(
    execution_id: str,
    *,
    reason: str,
    executions_root: Path | None = None,
    repo_root: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    normalized = validate_execution_id(execution_id)
    normalized_reason = str(reason or "").strip()
    if normalized_reason not in _REASONS:
        raise ValueError(
            "supersession reason must be one of: " + ", ".join(sorted(_REASONS))
        )
    output = (executions_root or paths.DATA_EXECUTIONS_ROOT).resolve()
    root = output / normalized
    if not root.is_dir():
        raise FileNotFoundError(f"execution root is missing: {root}")
    source_repo = (repo_root or paths.REPO_ROOT).resolve()
    with _lock(root):
        stale_receipts = tuple(
            (root / "_shared/reconciliation").glob("stale-*.json")
        )
        if stale_receipts:
            raise ValueError("stale-reconciled execution is already terminal")
        existing = load_execution_supersession_receipt(
            root,
            repo_root=source_repo,
        )
        if existing is not None:
            receipt, path = existing
            if receipt["reason"] != normalized_reason:
                raise ValueError("execution supersession create-once reason collision")
            return receipt, path

        state = _settled_execution_state(root)
        anchors = _anchors(root)
        manifest_path = root / _ANCHOR_REFS["executionManifest"]
        manifest = _optional_object(manifest_path)
        manifest_source = None
        source_definition_identity = False
        if manifest is not None:
            raw_manifest_source = manifest.get("sourceDigest")
            try:
                manifest_source = SourceDefinitionSnapshot.from_document(
                    raw_manifest_source
                ).to_document()
                source_definition_identity = True
                observed_source = current_source_definition_snapshot(
                    repo_root=source_repo
                ).to_document()
            except SourceDigestError:
                manifest_source = SourceDigest.from_document(
                    raw_manifest_source
                ).to_document()
                observed_source = current_source_digest(
                    repo_root=source_repo
                ).to_document()
        else:
            observed_source = current_source_digest(repo_root=source_repo).to_document()
        workflow_binding: tuple[str, str] | None = None
        if normalized_reason == "workflow_drift":
            if manifest is None:
                raise ValueError(
                    "workflow_drift supersession requires an execution manifest"
                )
            manifest_fingerprint = _operational_fingerprint(
                manifest.get("operationalFingerprint"),
                label="execution manifest operationalFingerprint",
            )
            observed_fingerprint = _operational_fingerprint(
                operational_fingerprint(repo_root=source_repo),
                label="current operational fingerprint",
            )
            if manifest_fingerprint == observed_fingerprint:
                raise ValueError(
                    "workflow_drift supersession requires operational drift"
                )
            workflow_binding = (manifest_fingerprint, observed_fingerprint)
        completion_binding: dict[str, object] | None = None
        if normalized_reason == "source_drift":
            if manifest_source is None or manifest_source == observed_source:
                raise ValueError("source_drift supersession requires manifest drift")
        elif normalized_reason == "unbound_completion_evidence":
            completion_binding = _completion_evidence_binding(root)
        elif normalized_reason == "missing_canonical_input" and all(
            bool(anchors[name]["exists"])
            for name in ("executionManifest", "request", "targetSet")
        ):
            raise ValueError(
                "missing_canonical_input supersession requires a missing canonical input"
            )
        process_evidence, previous_status, lease_disposition = _process_evidence(
            root,
            execution_id=normalized,
            state=state,
            reason=normalized_reason,
        )
        inventory, inventory_digest = _root_inventory(root)
        state_evidence = (
            "settled_retired_managed_snapshot"
            if state is not None
            and state.get("schema") == _RETIRED_MANAGED_STATE_SCHEMA
            else "settled_snapshot"
        )
        if state is None:
            if normalized_reason != "source_drift":
                raise ValueError(
                    "missing-state supersession only supports source_drift"
                )
            _validate_pre_controller_closure(root, inventory)
            state_evidence = "missing_pre_controller"
        evidence_digest = _digest(anchors)
        path = (
            root
            / "_shared/reconciliation"
            / f"supersession-{evidence_digest.removeprefix('sha256:')}.json"
        )
        stable = {
            "schema": "quwoquan_data.execution_supersession_receipt",
            "executionId": normalized,
            "decision": "superseded",
            "reason": normalized_reason,
            "errorCode": _ERROR_CODES[normalized_reason],
            "recordedAt": datetime.now(timezone.utc).isoformat(),
            "evidenceAnchors": anchors,
            "evidenceDigest": evidence_digest,
            "manifestSourceDigest": manifest_source,
            "observedSourceDigest": observed_source,
            "previousStatus": previous_status,
            "processEvidence": process_evidence,
            "controllerLeaseDisposition": lease_disposition,
            "rootInventoryDigest": inventory_digest,
            "rootInventoryEntryCount": len(inventory),
            "stateEvidence": state_evidence,
            "retryPolicy": "new_execution_with_retryOf",
            "evidenceDisposition": "protected_read_only",
        }
        if workflow_binding is not None:
            stable["manifestOperationalFingerprint"] = workflow_binding[0]
            stable["observedOperationalFingerprint"] = workflow_binding[1]
        if completion_binding is not None:
            stable["completionEvidenceBinding"] = completion_binding
        receipt = {**stable, "receiptDigest": _digest(stable)}
        assert_valid(
            receipt,
            "execution",
            "execution_supersession_receipt",
            label=f"execution supersession receipt:{path}",
        )
        observed_again = (
            current_source_definition_snapshot(repo_root=source_repo).to_document()
            if source_definition_identity
            else current_source_digest(repo_root=source_repo).to_document()
        )
        if observed_again != observed_source:
            raise ValueError("source changed while writing supersession receipt")
        if workflow_binding is not None:
            current_manifest = _optional_object(manifest_path)
            if current_manifest is None:
                raise ValueError(
                    "execution manifest changed while writing supersession receipt"
                )
            manifest_fingerprint_again = _operational_fingerprint(
                current_manifest.get("operationalFingerprint"),
                label="execution manifest operationalFingerprint",
            )
            observed_fingerprint_again = _operational_fingerprint(
                operational_fingerprint(repo_root=source_repo),
                label="current operational fingerprint",
            )
            if (
                manifest_fingerprint_again,
                observed_fingerprint_again,
            ) != workflow_binding:
                raise ValueError(
                    "workflow fingerprint changed while writing supersession receipt"
                )
        current_inventory, current_inventory_digest = _root_inventory(root)
        if (
            current_inventory_digest != inventory_digest
            or len(current_inventory) != len(inventory)
        ):
            raise ValueError("execution root changed while writing supersession receipt")
        validate_execution_supersession_receipt(
            receipt,
            path=path,
            execution_root=root,
            repo_root=source_repo,
        )
        body = json.dumps(receipt, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        return receipt, path


def _handle(args: argparse.Namespace) -> None:
    receipt, path = supersede_execution(
        str(args.execution_id),
        reason=str(args.reason),
    )
    print(
        json.dumps(
            {
                "executionId": receipt["executionId"],
                "decision": receipt["decision"],
                "reason": receipt["reason"],
                "receiptDigest": receipt["receiptDigest"],
                "receiptRef": path.relative_to(paths.OUTPUT_ROOT).as_posix(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def register_supersede_execution_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    parser = subparsers.add_parser(
        "supersede-execution",
        help=(
            "以 create-once receipt 终结 source/workflow drift、缺 canonical input "
            "或 unbound completion evidence 的 execution，保留旧证据"
        ),
    )
    parser.add_argument("execution_id")
    parser.add_argument("--reason", required=True, choices=tuple(sorted(_REASONS)))
    parser.set_defaults(handler=_handle)


__all__ = [
    "load_execution_supersession_receipt",
    "register_supersede_execution_parser",
    "supersede_execution",
    "validate_execution_supersession_receipt",
]
