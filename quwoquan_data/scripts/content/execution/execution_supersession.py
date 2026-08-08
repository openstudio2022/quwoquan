"""Create-once supersession for historical execution evidence.

Supersession never rewrites a historical manifest, request, state, or object.
It only proves that the frozen execution cannot resume under the current source
identity and that its bytes remain protected for audit/retry lineage.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import socket
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json
from core.schema import assert_valid
from core.source_digest import SourceDigest, current_source_digest

from content.execution.identity import validate_execution_id
from content.execution.terminal_state_integrity import verify_terminal_state_integrity

_REASONS = frozenset({"source_drift", "legacy_contract"})
_ERROR_CODES = {
    "source_drift": "DATA.EXECUTION.SOURCE_DRIFT_SUPERSEDED",
    "legacy_contract": "DATA.EXECUTION.LEGACY_CONTRACT_SUPERSEDED",
}
_ANCHOR_REFS = {
    "executionManifest": "execution_manifest.json",
    "request": "0.plan/request.json",
    "targetSet": "0.plan/target_set.json",
    "executionState": "_shared/execution_state.json",
    "controllerLease": "_shared/controller_lease.json",
}
_PRE_CONTROLLER_REQUIRED_FILES = frozenset(
    {
        "0.plan/execution_spec.yaml",
        "0.plan/queue_backend_envelope.json",
        "0.plan/request.json",
        "0.plan/target_set.json",
        "_shared/catalog.ndjson",
        "_shared/execution_progress.json",
        "_shared/target_selection.json",
        "evidence/model_readiness.json",
        "evidence/runtime_preflight.json",
        "execution_manifest.json",
        "sources/qualification/request.json",
    }
)
_PRE_CONTROLLER_OPTIONAL_FILES = frozenset({"_shared/execution_state.lock"})
_PRE_CONTROLLER_IDENTITY_FILES = frozenset(
    {
        "0.plan/queue_backend_envelope.json",
        "0.plan/target_set.json",
        "_shared/execution_progress.json",
        "_shared/target_selection.json",
        "evidence/model_readiness.json",
        "execution_manifest.json",
        "sources/qualification/request.json",
    }
)
_SUPERSESSION_ELIGIBLE_STATE_STATUSES = {"manual_required", "stopped_at_until"}
_LIVENESS_PROBE = "pid_pgid_only_no_argv"


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _file_binding(root: Path, relative: str) -> dict[str, object]:
    path = root / relative
    if path.is_symlink():
        raise ValueError(f"execution supersession anchor cannot be a symlink: {path}")
    exists = path.is_file()
    return {
        "ref": relative,
        "exists": exists,
        "sha256": _file_digest(path) if exists else None,
    }


def _anchors(root: Path) -> dict[str, dict[str, object]]:
    return {
        name: _file_binding(root, relative)
        for name, relative in _ANCHOR_REFS.items()
    }


def _optional_pid(value: object) -> int | None:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 1 else None


def _pid_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _pgid_alive(pgid: int | None) -> bool:
    if pgid is None:
        return False
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _optional_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = read_json(path)
    if not isinstance(value, dict):
        raise TypeError(f"execution supersession evidence must be an object: {path}")
    return value


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _require_regular_file(path: Path, *, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file: {path}")


def _root_inventory(root: Path) -> tuple[tuple[dict[str, object], ...], str]:
    entries: list[dict[str, object]] = []
    candidates = sorted(
        root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
    )
    for path in candidates:
        relative = path.relative_to(root).as_posix()
        parts = Path(relative).parts
        if parts[:2] == ("_shared", "reconciliation"):
            if len(parts) == 2 and (path.is_symlink() or not path.is_dir()):
                raise ValueError(
                    "execution supersession reconciliation root is corrupt"
                )
            continue
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(
                f"execution supersession root contains a symlink: {relative}"
            )
        if stat.S_ISDIR(metadata.st_mode):
            entries.append({
                "ref": relative, "kind": "directory", "size": None, "sha256": None
            })
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(
                f"execution supersession root contains a non-regular entry: {relative}"
            )
        entries.append(
            {
                "ref": relative,
                "kind": "file",
                "size": metadata.st_size,
                "sha256": _file_digest(path),
            }
        )
    frozen = tuple(entries)
    return frozen, _digest({"entries": list(frozen)})


def _settled_execution_state(root: Path) -> dict[str, Any] | None:
    state_path = root / _ANCHOR_REFS["executionState"]
    head_path = state_path.with_name("execution_state_head.json")
    events_path = state_path.with_name("execution_state_events")
    lock_path = state_path.with_name("execution_state.lock")
    state_exists = _path_exists(state_path)
    head_exists = _path_exists(head_path)
    events_exist = _path_exists(events_path)
    if _path_exists(lock_path):
        _require_regular_file(lock_path, label="execution state lock")
        if lock_path.stat().st_size != 0:
            raise ValueError("execution state lock must be empty")
    if not state_exists:
        if head_exists or events_exist:
            raise ValueError(
                "execution state is missing but journal fragments are present"
            )
        return None
    _require_regular_file(state_path, label="execution state snapshot")
    state = _optional_object(state_path)
    assert state is not None
    assert_valid(
        state,
        "execution",
        "execution_state",
        label=f"execution supersession state:{root.name}",
    )
    if state.get("executionId") != root.name:
        raise ValueError("execution supersession state executionId drift")
    if not head_exists:
        if events_exist:
            raise ValueError(
                "execution state journal has an uncommitted events directory"
            )
    else:
        _require_regular_file(head_path, label="execution state head")
        head = _optional_object(head_path)
        assert head is not None
        if head.get("executionId") != root.name:
            raise ValueError("execution state head executionId drift")
        try:
            sequence = int(head.get("sequence"))
        except (TypeError, ValueError) as exc:
            raise ValueError("execution state head sequence is invalid") from exc
        if events_path.is_symlink() or not events_path.is_dir():
            raise ValueError("execution state journal directory is missing or invalid")
        event_entries = sorted(events_path.iterdir(), key=lambda item: item.name)
        if any(item.is_symlink() or not item.is_file() for item in event_entries):
            raise ValueError("execution state journal contains a non-regular entry")
        expected_names = [f"{item:020d}.json" for item in range(1, sequence + 1)]
        if [item.name for item in event_entries] != expected_names:
            raise ValueError(
                "execution state journal is not settled at its committed head"
            )
    # Pure verifier: pending/torn journal recovery is forbidden above.
    verify_terminal_state_integrity(state_path)
    return state


def _validate_pre_controller_closure(
    root: Path,
    inventory: tuple[dict[str, object], ...],
) -> None:
    files = {
        str(entry["ref"])
        for entry in inventory
        if entry.get("kind") == "file"
    }
    missing = sorted(_PRE_CONTROLLER_REQUIRED_FILES - files)
    unexpected = sorted(
        files - _PRE_CONTROLLER_REQUIRED_FILES - _PRE_CONTROLLER_OPTIONAL_FILES
    )
    if missing or unexpected:
        raise ValueError(
            "missing-state execution is not an exact pre-controller closure: "
            f"missing={missing} unexpected={unexpected}"
        )
    for relative in sorted(_PRE_CONTROLLER_REQUIRED_FILES):
        path = root / relative
        if relative.endswith(".json"):
            _optional_object(path)
        elif relative.endswith(".ndjson"):
            lines = path.read_text(encoding="utf-8").splitlines()
            if not lines:
                raise ValueError("pre-controller catalog must not be empty")
            for line in lines:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("pre-controller catalog rows must be objects")
        elif path.stat().st_size == 0:
            raise ValueError(f"pre-controller evidence must not be empty: {relative}")
    for relative in _PRE_CONTROLLER_IDENTITY_FILES:
        document = _optional_object(root / relative)
        if document is None or document.get("executionId") != root.name:
            raise ValueError(
                f"pre-controller evidence executionId drift: {relative}"
            )
    progress = _optional_object(root / "_shared/execution_progress.json") or {}
    counts = progress.get("counts")
    if progress.get("lastRunId") is not None or not isinstance(counts, Mapping):
        raise ValueError("pre-controller progress contains runtime evidence")
    if any(int(counts.get(name) or 0) != 0 for name in ("entities", "posts")):
        raise ValueError("pre-controller progress contains finalized objects")


def _process_evidence(
    root: Path,
    *,
    execution_id: str,
    state: Mapping[str, Any] | None,
) -> tuple[dict[str, object], str]:
    lease = _optional_object(root / _ANCHOR_REFS["controllerLease"])
    if lease is not None:
        if lease.get("executionId") != execution_id:
            raise ValueError("execution controller lease executionId drift")
        lease_status = str(lease.get("status") or "").strip()
        if lease_status == "active":
            raise ValueError("execution controller lease is active; supersession refused")
        if lease_status != "released":
            raise ValueError("execution controller lease status is invalid")
    state_status = str((state or {}).get("status") or "missing")
    if state is not None and state_status not in _SUPERSESSION_ELIGIBLE_STATE_STATUSES:
        raise ValueError(
            f"execution state is not supersession-eligible: {state_status}"
        )
    controller = state.get("controller") if state else None
    controller_row = controller if isinstance(controller, Mapping) else {}
    pid = _optional_pid((lease or {}).get("pid") or controller_row.get("pid"))
    pgid = _optional_pid((lease or {}).get("pgid") or controller_row.get("pgid"))
    observed_pid_alive = _pid_alive(pid)
    observed_group_alive = _pgid_alive(pgid)
    if observed_pid_alive or observed_group_alive:
        raise ValueError(
            "execution controller/process group is still alive; supersession refused"
        )
    return (
        {
            "hostname": socket.gethostname(),
            "pid": pid,
            "pgid": pgid,
            "observedPidAlive": observed_pid_alive,
            "observedProcessGroupAlive": observed_group_alive,
            "identityMatched": False,
            "pidAlive": False,
            "processGroupAlive": False,
            "livenessProbe": _LIVENESS_PROBE,
        },
        state_status,
    )


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
        expected_state_evidence = (
            "settled_snapshot"
            if (execution_root / _ANCHOR_REFS["executionState"]).is_file()
            else "missing_pre_controller"
        )
        if receipt["stateEvidence"] != expected_state_evidence:
            raise ValueError("execution supersession state evidence drift")
        if receipt["processEvidence"].get("livenessProbe") != _LIVENESS_PROBE:
            raise ValueError("execution supersession liveness probe drift")
    source = receipt.get("manifestSourceDigest")
    if source is not None:
        SourceDigest.from_document(source)
    SourceDigest.from_document(receipt["observedSourceDigest"])
    return receipt


def load_execution_supersession_receipt(
    execution_root: Path,
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
        raise ValueError("supersession reason must be source_drift or legacy_contract")
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
        existing = load_execution_supersession_receipt(root)
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
        if manifest is not None:
            manifest_source = SourceDigest.from_document(
                manifest.get("sourceDigest")
            ).to_document()
        observed_source = current_source_digest(repo_root=source_repo).to_document()
        if normalized_reason == "source_drift":
            if manifest_source is None or manifest_source == observed_source:
                raise ValueError("source_drift supersession requires manifest drift")
        elif all(
            bool(anchors[name]["exists"])
            for name in ("executionManifest", "request", "targetSet")
        ):
            raise ValueError(
                "legacy_contract supersession requires a missing canonical input"
            )
        process_evidence, previous_status = _process_evidence(
            root,
            execution_id=normalized,
            state=state,
        )
        inventory, inventory_digest = _root_inventory(root)
        state_evidence = "settled_snapshot"
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
            "rootInventoryDigest": inventory_digest,
            "rootInventoryEntryCount": len(inventory),
            "stateEvidence": state_evidence,
            "retryPolicy": "new_execution_with_retryOf",
            "evidenceDisposition": "protected_read_only",
        }
        receipt = {**stable, "receiptDigest": _digest(stable)}
        validate_execution_supersession_receipt(
            receipt,
            path=path,
            execution_root=root,
        )
        if current_source_digest(repo_root=source_repo).to_document() != observed_source:
            raise ValueError("source changed while writing supersession receipt")
        current_inventory, current_inventory_digest = _root_inventory(root)
        if (
            current_inventory_digest != inventory_digest
            or len(current_inventory) != len(inventory)
        ):
            raise ValueError("execution root changed while writing supersession receipt")
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
        help="以 create-once receipt 终结 source-drift/legacy execution，保留旧证据",
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
