"""Fail-closed Python consumer for the canonical Go storage contract view."""

from __future__ import annotations

import hashlib
import json
import stat
import subprocess
import tempfile
from collections.abc import Callable, Collection
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROOT = ROOT / "quwoquan_service"
STORAGE_VIEW_COMMAND = ("go", "run", "./tools/storage_contract_view")
STORAGE_DOCUMENT_KEYS = frozenset(
    {
        "backend",
        "description",
        "role",
        "tables",
        "collections",
        "streams",
        "transaction",
        "redis_cache",
        "environment_backends",
        "fallback",
        "logstores",
        "codegen",
    }
)
STORAGE_DOCUMENT_REQUIRED_OUTPUT_KEYS = frozenset({"backend", "role"})


class StorageContractViewError(RuntimeError):
    """The typed storage view could not be obtained without ambiguity."""


def _file_identity(path: Path) -> tuple[int, int, int, int, int]:
    file_stat = path.lstat()
    if not stat.S_ISREG(file_stat.st_mode):
        raise StorageContractViewError(f"{path} must be a regular file")
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_mode,
        file_stat.st_size,
        file_stat.st_mtime_ns,
    )


def _read_stable_source(path: Path) -> tuple[bytes, tuple[int, int, int, int, int]]:
    try:
        identity_before = _file_identity(path)
        payload = path.read_bytes()
        identity_after = _file_identity(path)
    except OSError as exc:
        raise StorageContractViewError(f"{path} cannot be read: {exc}") from exc
    if identity_before != identity_after:
        raise StorageContractViewError(f"{path} changed while being read")
    return payload, identity_before


def load_storage_contract_view(
    path: Path,
    *,
    expected_keys: Collection[str] | None = None,
    timeout_seconds: float = 30.0,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, object]:
    """Return the strict Go-decoded storage document for one immutable input.

    The Go CLI reads a byte snapshot, while the original path is checked before
    and after the invocation.  A writer therefore cannot make this consumer
    accept a typed view from one revision and source bytes from another.
    """

    source_path = path.absolute()
    source_bytes, source_identity = _read_stable_source(source_path)
    source_digest = hashlib.sha256(source_bytes).hexdigest()

    try:
        with tempfile.TemporaryDirectory(prefix="qwq-storage-contract-view-") as tmp:
            snapshot_path = Path(tmp) / "storage.yaml"
            snapshot_path.write_bytes(source_bytes)
            completed = runner(
                (*STORAGE_VIEW_COMMAND, "--input", str(snapshot_path)),
                cwd=SERVICE_ROOT,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
    except subprocess.TimeoutExpired as exc:
        raise StorageContractViewError(
            f"{path} canonical storage view timed out after {timeout_seconds:g}s"
        ) from exc
    except OSError as exc:
        raise StorageContractViewError(
            f"{path} canonical storage view could not start: {exc}"
        ) from exc

    try:
        current_bytes, current_identity = _read_stable_source(source_path)
    except StorageContractViewError as exc:
        raise StorageContractViewError(
            f"{path} changed while canonical storage view was running: {exc}"
        ) from exc
    if (
        current_identity != source_identity
        or hashlib.sha256(current_bytes).hexdigest() != source_digest
    ):
        raise StorageContractViewError(
            f"{path} changed while canonical storage view was running"
        )

    if completed.returncode != 0:
        detail = completed.stderr.strip() or "no diagnostic"
        raise StorageContractViewError(
            f"{path} canonical storage view exited {completed.returncode}: {detail}"
        )
    if completed.stderr.strip():
        raise StorageContractViewError(
            f"{path} canonical storage view emitted stderr: {completed.stderr.strip()}"
        )
    if not completed.stdout.strip():
        raise StorageContractViewError(
            f"{path} canonical storage view returned empty stdout"
        )
    try:
        payload: Any = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise StorageContractViewError(
            f"{path} canonical storage view returned invalid JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise StorageContractViewError(
            f"{path} canonical storage view must return a JSON object"
        )

    actual_keys = frozenset(payload)
    unexpected_keys = sorted(actual_keys - STORAGE_DOCUMENT_KEYS)
    if unexpected_keys:
        raise StorageContractViewError(
            f"{path} canonical storage view returned unknown keys {unexpected_keys}"
        )
    missing_required = sorted(STORAGE_DOCUMENT_REQUIRED_OUTPUT_KEYS - actual_keys)
    if missing_required:
        raise StorageContractViewError(
            f"{path} canonical storage view omitted required keys {missing_required}"
        )
    if expected_keys is not None and actual_keys != frozenset(expected_keys):
        raise StorageContractViewError(
            f"{path} canonical storage view keyset drifted: "
            f"expected {sorted(expected_keys)}, got {sorted(actual_keys)}"
        )
    return payload
