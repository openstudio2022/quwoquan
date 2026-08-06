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
import subprocess
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json
from core.schema import assert_valid
from core.source_digest import SourceDigest, current_source_digest

from content.execution.execution_state_journal import verify_execution_state_journal
from content.execution.identity import validate_execution_id

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


def _process_command(pid: int | None) -> str:
    if pid is None:
        return ""
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        check=False,
        capture_output=True,
        text=True,
    )
    return str(result.stdout or "").strip() if result.returncode == 0 else ""


def _group_commands(pgid: int | None) -> tuple[str, ...]:
    if pgid is None:
        return ()
    result = subprocess.run(
        ["ps", "-axo", "pgid=,command="],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ()
    commands: list[str] = []
    for line in str(result.stdout or "").splitlines():
        raw_group, _, command = line.strip().partition(" ")
        try:
            observed = int(raw_group)
        except ValueError:
            continue
        if observed == pgid and command.strip():
            commands.append(command.strip())
    return tuple(commands)


def _owned_command(command: str, *, execution_id: str) -> bool:
    normalized = command.replace("\\", "/")
    return execution_id in normalized and (
        "quwoquan_data/scripts/cli.py" in normalized
        or "content.execution" in normalized
    )


def _process_evidence(
    root: Path,
    *,
    execution_id: str,
) -> tuple[dict[str, object], str]:
    state = _optional_object(root / _ANCHOR_REFS["executionState"])
    lease = _optional_object(root / _ANCHOR_REFS["controllerLease"])
    controller = state.get("controller") if state else None
    controller_row = controller if isinstance(controller, Mapping) else {}
    pid = _optional_pid((lease or {}).get("pid") or controller_row.get("pid"))
    pgid = _optional_pid((lease or {}).get("pgid"))
    observed_pid_alive = _pid_alive(pid)
    observed_group_alive = _pgid_alive(pgid)
    identity_matched = (
        observed_pid_alive
        and _owned_command(_process_command(pid), execution_id=execution_id)
    ) or any(
        _owned_command(command, execution_id=execution_id)
        for command in _group_commands(pgid)
    )
    if identity_matched:
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
        },
        str((state or {}).get("status") or "missing"),
    )


@contextmanager
def _lock(root: Path) -> Iterator[None]:
    path = root / "_shared/reconciliation/.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
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
        verify_execution_state_journal(
            root / "_shared" / "execution_state.json"
        )
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
        )
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
