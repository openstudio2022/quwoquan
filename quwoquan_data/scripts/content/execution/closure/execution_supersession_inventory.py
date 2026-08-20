"""Immutable anchor inventory and process probes for execution supersession."""

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
from core.source_digest import (
    SourceDefinitionSnapshot,
    SourceDigest,
    SourceDigestError,
    current_source_definition_snapshot,
    current_source_digest,
)

from content.execution.identity import validate_execution_id
from content.execution.terminal_state_integrity import verify_terminal_state_integrity

_REASONS = frozenset({"source_drift", "missing_canonical_input"})
_ERROR_CODES = {
    "source_drift": "DATA.EXECUTION.SOURCE_DRIFT_SUPERSEDED",
    "missing_canonical_input": "DATA.EXECUTION.MISSING_CANONICAL_INPUT_SUPERSEDED",
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
