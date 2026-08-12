"""Plan and apply fail-closed repository output-layout reconciliation.

The planner consumes the canonical root/output verifier findings.  It never
guesses that a finding is deletable: only unambiguous repo-local cache/process
misplacements can become move actions.  Runtime receipts, Data output,
source-tree paths, secret material, active paths, and ambiguous destinations
remain explicit blockers in the immutable plan.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .output_layout_reconciliation_identity import (
    OutputLayoutReconciliationError,
    activity_for_path as _activity_for_path,
    canonical_bytes,
    canonical_digest,
    is_within as _is_within,
    lsof_records as _lsof_records,
    snapshot_path,
)


PLAN_SCHEMA = "stackctl-output-layout-reconciliation-plan"
PLAN_VERSION = 1
PLAN_FILENAME = "output-layout-reconciliation-plan.json"
PLAN_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ISSUE_PREFIX_RE = re.compile(r"^(?P<path>.*?)(?::(?P<line>[1-9][0-9]*))?$")
LOCAL_CACHE_HINTS = (
    "cache",
    "go-build",
    "go-mod",
    "pytest",
    "pycache",
    "python",
    "tool",
)
LOCAL_PROCESS_SUFFIXES = frozenset({".log", ".pid"})
EXCLUDED_RESOURCE_CLASSES = [
    "named_volumes",
    "environment_runtime",
    "source_truth",
    "data_release",
]


OpenFileProbe = Callable[[Sequence[Path]], tuple[dict[str, list[dict[str, Any]]], list[str]]]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _parse_issue(issue: str) -> tuple[str | None, int | None, str]:
    prefix, separator, reason = issue.partition(": ")
    if not separator:
        return None, None, issue
    match = ISSUE_PREFIX_RE.fullmatch(prefix)
    if match is None:
        return None, None, issue
    path = str(match.group("path") or "").strip()
    if not path:
        return None, None, issue
    line = match.group("line")
    return path, int(line) if line else None, reason


def canonical_issue_fingerprints(
    issues: Sequence[str],
    *,
    repository_root: Path,
) -> set[str]:
    fingerprints: set[str] = set()
    for issue in issues:
        value, line, reason = _parse_issue(str(issue))
        if value is None:
            fingerprints.add("unscoped\0" + str(issue))
            continue
        absolute = _absolute_issue_path(value, repository_root=repository_root)
        fingerprints.add(f"path\0{absolute}\0{line or 0}\0{reason}")
    return fingerprints


def plan_issue_fingerprints(payload: Mapping[str, Any]) -> set[str]:
    repository_root = Path(str(payload.get("repositoryRoot") or ""))
    fingerprints = {
        "unscoped\0" + str(issue)
        for issue in payload.get("unscopedIssues", [])
    }
    for record in payload.get("records", []):
        path = Path(str(record.get("path") or ""))
        for violation in record.get("violations", []):
            fingerprints.add(
                f"path\0{path}\0{int(violation.get('line') or 0)}\0"
                + str(violation.get("reason") or "")
            )
    if not repository_root.is_absolute():
        raise OutputLayoutReconciliationError(
            "output reconciliation plan repository root is invalid"
        )
    return fingerprints


def _absolute_issue_path(
    value: str,
    *,
    repository_root: Path,
) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = repository_root / candidate
    return candidate.absolute()


def _producer_identity(
    path: Path,
    *,
    repository_root: Path,
    output_root: Path,
) -> tuple[str, str, str]:
    if _is_within(path, output_root):
        relative = path.relative_to(output_root)
        parts = relative.parts
        if len(parts) >= 2 and parts[0] == "env":
            environment = parts[1]
            group = f"output_env_{environment}"
            if len(parts) >= 4 and parts[2] == "local":
                target = parts[3]
                return group, f"{group}:local:{target}", target
            category = parts[2] if len(parts) >= 3 else "root"
            return group, f"{group}:{category}", environment
        if parts and parts[0] == "data":
            category = parts[1] if len(parts) >= 2 else "root"
            return "output_data", f"output_data:{category}", "data"
        return "output_root", "output_root", "repo"
    try:
        relative = path.relative_to(repository_root)
    except ValueError:
        return "external", "external", "external"
    domain = relative.parts[0] if relative.parts else "repository"
    return f"source_{domain}", f"source_{domain}", "source"


def _canonical_repo_local_destination(
    path: Path,
    *,
    output_root: Path,
) -> tuple[str, Path | None]:
    try:
        relative = path.relative_to(output_root / "env" / "repo" / "local")
    except ValueError:
        return "owner_destination_required", None
    if len(relative.parts) < 2 or relative.parts[1] in {"cache", "process"}:
        return "owner_destination_required", None
    target = relative.parts[0]
    tail = Path(*relative.parts[1:])
    normalized = target.lower()
    if any(hint in normalized for hint in LOCAL_CACHE_HINTS):
        return "move_to_canonical_cache", output_root / "env/repo/local" / target / "cache" / tail
    if path.suffix.lower() in LOCAL_PROCESS_SUFFIXES or "process" in normalized:
        return "move_to_canonical_process", output_root / "env/repo/local" / target / "process" / tail
    return "owner_destination_required", None


def _classify_record(
    path: Path,
    *,
    reasons: Sequence[str],
    repository_root: Path,
    output_root: Path,
    active_process_pids: Sequence[int],
    open_fd_pids: Sequence[int],
) -> dict[str, Any]:
    joined = " ".join(reasons).lower()
    within_output = _is_within(path, output_root)
    relative_output = path.relative_to(output_root).parts if within_output else ()
    in_data = bool(relative_output and relative_output[0] == "data")
    in_environment_runtime = bool(
        len(relative_output) >= 2
        and relative_output[0] == "env"
        and relative_output[1] in {"alpha", "beta", "gamma", "prod"}
    )
    protected_receipt = bool(
        len(relative_output) >= 3
        and relative_output[0] == "env"
        and relative_output[2] == "runs"
    )
    protected_data_release = bool(
        len(relative_output) >= 2
        and relative_output[0] == "data"
        and relative_output[1] in {"tasks", "releases"}
    )
    protected_quarantine = bool(
        len(relative_output) >= 2
        and relative_output[0] == "data"
        and (
            relative_output[1] == "quarantine"
            or "quarantine" in relative_output
        )
    )
    secret_material = (
        "unredacted secret assignment" in joined
        or "deployment configuration, tls or secret material is forbidden" in joined
        or "deployment configuration, tls or secret material "
        "is forbidden" in joined
    )
    source_truth = "source truth" in joined
    source_path = not within_output
    blockers: list[str] = []
    destination: Path | None = None
    if source_path:
        disposition = "out_of_scope_source"
        blockers.append("source paths are outside output reconciliation")
    elif in_data:
        disposition = "out_of_scope_data"
        blockers.append("Data tasks/releases/quarantine are outside this operation")
    elif in_environment_runtime or protected_receipt:
        disposition = "out_of_scope_environment_runtime"
        blockers.append("environment runtime and receipts are outside this operation")
    elif secret_material:
        disposition = "security_owner_review"
        blockers.append("secret/configuration material requires security owner review")
    elif source_truth:
        disposition = "source_owner_migration_required"
        blockers.append("embedded source truth needs an owner-declared canonical source destination")
    else:
        disposition, destination = _canonical_repo_local_destination(
            path,
            output_root=output_root,
        )
        if destination is None:
            blockers.append("canonical destination cannot be inferred without the producer owner")
    if active_process_pids or open_fd_pids:
        blockers.append("path is active or has open file descriptors")
    if protected_quarantine:
        blockers.append("protected Data quarantine must not be moved or deleted")
    if protected_data_release:
        blockers.append("Data release/task truth must not be moved or deleted")
    if destination is not None and destination.exists():
        blockers.append("canonical destination already exists")
    return {
        "disposition": disposition,
        "canonicalDestination": str(destination) if destination is not None else None,
        "operation": "move" if destination is not None else "none",
        "flags": {
            "activeProcess": bool(active_process_pids),
            "openFileDescriptor": bool(open_fd_pids),
            "protectedReceipt": protected_receipt,
            "protectedDataRelease": protected_data_release,
            "protectedQuarantine": protected_quarantine,
            "secretMaterial": secret_material,
            "sourceTruth": source_truth,
            "sourcePath": source_path,
            "environmentRuntime": in_environment_runtime,
            "namedVolume": False,
        },
        "blockers": sorted(set(blockers)),
    }


def build_plan(
    *,
    repository_root: Path,
    output_root: Path,
    canonical_issues: Sequence[str],
    truth: Mapping[str, Mapping[str, str]],
    open_file_probe: OpenFileProbe = _lsof_records,
    created_at: str | None = None,
) -> dict[str, Any]:
    repository_root = repository_root.expanduser().absolute()
    output_root = output_root.expanduser().absolute()
    grouped: dict[Path, list[dict[str, Any]]] = defaultdict(list)
    unscoped: list[str] = []
    for issue in canonical_issues:
        value, line, reason = _parse_issue(str(issue))
        if value is None:
            unscoped.append(str(issue))
            continue
        path = _absolute_issue_path(value, repository_root=repository_root)
        grouped[path].append({"line": line, "reason": reason})

    roots = [output_root]
    roots.extend(path for path in grouped if not _is_within(path, output_root))
    open_files, probe_issues = open_file_probe(roots)
    records: list[dict[str, Any]] = []
    for path in sorted(grouped, key=lambda item: item.as_posix()):
        reasons = [str(item["reason"]) for item in grouped[path]]
        process_pids, open_fd_pids = _activity_for_path(path, open_files)
        group, producer, target = _producer_identity(
            path,
            repository_root=repository_root,
            output_root=output_root,
        )
        try:
            snapshot = snapshot_path(path)
            snapshot_error = ""
        except OutputLayoutReconciliationError as exc:
            snapshot = None
            snapshot_error = str(exc)
        classification = _classify_record(
            path,
            reasons=reasons,
            repository_root=repository_root,
            output_root=output_root,
            active_process_pids=process_pids,
            open_fd_pids=open_fd_pids,
        )
        blockers = list(classification["blockers"])
        if snapshot_error:
            blockers.append(snapshot_error)
        if snapshot is not None and snapshot["kind"] in {"symlink", "other"}:
            blockers.append("symlink and special-file paths cannot be reconciled")
        records.append(
            {
                "path": str(path),
                "producerGroup": group,
                "producer": producer,
                "target": target,
                "violations": sorted(
                    grouped[path],
                    key=lambda item: (int(item["line"] or 0), str(item["reason"])),
                ),
                "snapshot": snapshot,
                "activeProcessPids": process_pids,
                "openFileDescriptorPids": open_fd_pids,
                **classification,
                "blockers": sorted(set(blockers)),
                "action": not blockers and classification["operation"] == "move",
            }
        )

    blocking = [
        f"{record['path']}: {reason}"
        for record in records
        for reason in record["blockers"]
    ]
    blocking.extend(f"unscoped canonical issue: {issue}" for issue in unscoped)
    blocking.extend(probe_issues)
    payload: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "schemaVersion": PLAN_VERSION,
        "createdAt": created_at or _now(),
        "status": "blocked" if blocking else "ready",
        "repositoryRoot": str(repository_root),
        "outputRoot": str(output_root),
        "canonicalTruth": {key: dict(value) for key, value in sorted(truth.items())},
        "canonicalIssueCount": len(canonical_issues),
        "canonicalIssueDigest": canonical_digest(sorted(str(item) for item in canonical_issues)),
        "unscopedIssues": sorted(unscoped),
        "probeIssues": sorted(probe_issues),
        "excludedResourceClasses": EXCLUDED_RESOURCE_CLASSES,
        "records": records,
        "actionCount": sum(1 for record in records if record["action"]),
        "noOp": not records,
        "blockers": sorted(set(blocking)),
    }
    payload["planDigest"] = canonical_digest(payload)
    return payload


def validate_plan(payload: Mapping[str, Any]) -> None:
    required = {
        "schema",
        "schemaVersion",
        "createdAt",
        "status",
        "repositoryRoot",
        "outputRoot",
        "canonicalTruth",
        "canonicalIssueCount",
        "canonicalIssueDigest",
        "unscopedIssues",
        "probeIssues",
        "excludedResourceClasses",
        "records",
        "actionCount",
        "noOp",
        "blockers",
        "planDigest",
    }
    if set(payload) != required:
        raise OutputLayoutReconciliationError("output reconciliation plan fields mismatch")
    if payload.get("schema") != PLAN_SCHEMA or payload.get("schemaVersion") != PLAN_VERSION:
        raise OutputLayoutReconciliationError("output reconciliation plan schema mismatch")
    plan_digest = str(payload.get("planDigest") or "")
    if not PLAN_DIGEST_RE.fullmatch(plan_digest):
        raise OutputLayoutReconciliationError("output reconciliation plan digest is invalid")
    unsigned = dict(payload)
    unsigned.pop("planDigest", None)
    if canonical_digest(unsigned) != plan_digest:
        raise OutputLayoutReconciliationError("output reconciliation plan digest mismatch")
    if payload.get("status") not in {"ready", "blocked"}:
        raise OutputLayoutReconciliationError("output reconciliation plan status is invalid")
    if payload.get("excludedResourceClasses") != EXCLUDED_RESOURCE_CLASSES:
        raise OutputLayoutReconciliationError("output reconciliation excluded resource classes drifted")
    records = payload.get("records")
    if not isinstance(records, list):
        raise OutputLayoutReconciliationError("output reconciliation records must be an array")
    action_count = sum(
        1 for record in records if isinstance(record, Mapping) and record.get("action") is True
    )
    if payload.get("actionCount") != action_count:
        raise OutputLayoutReconciliationError("output reconciliation action count mismatch")
    if payload.get("status") == "ready" and payload.get("blockers"):
        raise OutputLayoutReconciliationError("ready output reconciliation plan has blockers")
    for record in records:
        if not isinstance(record, Mapping):
            raise OutputLayoutReconciliationError("output reconciliation record is invalid")
        if record.get("flags", {}).get("namedVolume") is not False:
            raise OutputLayoutReconciliationError("named volumes are outside output reconciliation")
        if record.get("operation") not in {"move", "none"}:
            raise OutputLayoutReconciliationError("output reconciliation only supports reversible moves")
        if record.get("action") is True and (
            record.get("operation") != "move"
            or record.get("blockers")
            or not record.get("canonicalDestination")
        ):
            raise OutputLayoutReconciliationError("output reconciliation action is not safe")


def write_create_once(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(canonical_bytes(payload) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)
    directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return path


def load_plan(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise OutputLayoutReconciliationError("output reconciliation plan must be a regular non-symlink file")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise OutputLayoutReconciliationError("output reconciliation plan must be an object")
    validate_plan(payload)
    return payload


def _snapshot_matches(
    expected: Mapping[str, Any],
    current: Mapping[str, Any],
    *,
    relocated: bool = False,
) -> bool:
    expected_snapshot = dict(expected)
    current_snapshot = dict(current)
    if relocated:
        expected_snapshot.pop("pathByteLength", None)
        current_snapshot.pop("pathByteLength", None)
    return expected_snapshot == current_snapshot


def apply_plan(
    payload: Mapping[str, Any],
    *,
    repository_root: Path,
    output_root: Path,
    truth: Mapping[str, Mapping[str, str]],
    open_file_probe: OpenFileProbe = _lsof_records,
    move: Callable[[str, str], Any] = shutil.move,
) -> dict[str, Any]:
    validate_plan(payload)
    if payload.get("status") != "ready":
        raise OutputLayoutReconciliationError("blocked output reconciliation plan cannot be applied")
    if str(repository_root.expanduser().absolute()) != payload.get("repositoryRoot"):
        raise OutputLayoutReconciliationError("repository root differs from immutable plan")
    if str(output_root.expanduser().absolute()) != payload.get("outputRoot"):
        raise OutputLayoutReconciliationError("output root differs from immutable plan")
    if {key: dict(value) for key, value in sorted(truth.items())} != payload.get("canonicalTruth"):
        raise OutputLayoutReconciliationError("canonical layout truth differs from immutable plan")
    planned_actions = [
        record for record in payload["records"] if record.get("action") is True
    ]
    open_files, probe_issues = open_file_probe([output_root])
    if probe_issues:
        raise OutputLayoutReconciliationError("; ".join(probe_issues))
    pending_actions: list[Mapping[str, Any]] = []
    read_back: list[Path] = []
    for record in planned_actions:
        source = Path(str(record["path"]))
        destination = Path(str(record["canonicalDestination"]))
        if not _is_within(source, output_root) or not _is_within(destination, output_root):
            raise OutputLayoutReconciliationError("apply is restricted to QWQ_OUTPUT_ROOT")
        source_exists = source.exists()
        destination_exists = destination.exists()
        if source_exists and destination_exists:
            raise OutputLayoutReconciliationError(
                f"source and canonical destination both exist: {source}"
            )
        if source_exists:
            current_path = source
            pending_actions.append(record)
        elif destination_exists:
            current_path = destination
            read_back.append(destination)
        else:
            raise OutputLayoutReconciliationError(
                f"planned source and destination are both missing: {source}"
            )
        current = snapshot_path(current_path)
        if not _snapshot_matches(
            record["snapshot"],
            current,
            relocated=current_path == destination,
        ):
            raise OutputLayoutReconciliationError(
                f"planned path identity drifted: {current_path}"
            )
        process_pids, open_fd_pids = _activity_for_path(current_path, open_files)
        if process_pids or open_fd_pids:
            raise OutputLayoutReconciliationError(
                f"planned path became active: {current_path}"
            )

    moved: list[tuple[Path, Path]] = []
    created_parents: list[Path] = []
    try:
        for record in pending_actions:
            source = Path(str(record["path"]))
            destination = Path(str(record["canonicalDestination"]))
            missing_parents: list[Path] = []
            current_parent = destination.parent
            while not current_parent.exists() and _is_within(current_parent, output_root):
                missing_parents.append(current_parent)
                current_parent = current_parent.parent
            destination.parent.mkdir(parents=True, exist_ok=True)
            created_parents.extend(reversed(missing_parents))
            move(str(source), str(destination))
            moved.append((source, destination))
            if not destination.exists() or source.exists():
                raise OutputLayoutReconciliationError(f"move readback failed: {source}")
            if not _snapshot_matches(
                record["snapshot"],
                snapshot_path(destination),
                relocated=True,
            ):
                raise OutputLayoutReconciliationError(f"destination identity mismatch: {destination}")
            read_back.append(destination)
    except Exception as exc:
        rollback_issues: list[str] = []
        for source, destination in reversed(moved):
            try:
                if source.exists() or not destination.exists():
                    raise OutputLayoutReconciliationError(
                        f"rollback path identity conflict: {source}"
                    )
                source.parent.mkdir(parents=True, exist_ok=True)
                move(str(destination), str(source))
            except Exception as rollback_exc:  # noqa: BLE001 - preserve every rollback failure
                rollback_issues.append(str(rollback_exc))
        for parent in reversed(created_parents):
            try:
                parent.rmdir()
            except OSError:
                pass
        suffix = ""
        if rollback_issues:
            suffix = "; rollback issues: " + "; ".join(rollback_issues)
        raise OutputLayoutReconciliationError(str(exc) + suffix) from exc
    return {
        "status": "passed",
        "planDigest": payload["planDigest"],
        "noOp": not pending_actions,
        "replayed": bool(planned_actions) and not pending_actions,
        "moved": [
            {"from": str(source), "to": str(destination)}
            for source, destination in moved
        ],
        "readBack": [str(path) for path in read_back],
        "rollbackAvailable": True,
    }
