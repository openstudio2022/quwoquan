"""Target-scoped transactional receipt for local runtime startup."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from quwoquan_ops.cli.lib.deployment_candidate_manifest import load_candidate_manifest
from quwoquan_ops.cli.lib.immutable_image_composition import immutable_image_digest
from quwoquan_ops.cli.lib.output_paths import (
    ACTIVE_CANDIDATE_SCHEMA,
    active_candidate_manifest_path,
    deployment_candidate_dir,
    output_root,
    target_process_dir,
)

SCHEMA = "stackctl-local-startup-attempt"
STATUSES = ("prepared", "partial", "running", "stopped")
WORKLOADS = ("full", "content-release", "content-commercial")
RECEIPT_FIELDS = frozenset(
    {
        "schema",
        "attemptId",
        "env",
        "target",
        "status",
        "workload",
        "composeProject",
        "candidateDigest",
        "configurationDigest",
        "providerRuntimeDigest",
        "observabilityLogSinkDigest",
        "imageTransportTag",
        "imageComposition",
        "runRoot",
        "startedAt",
        "updatedAt",
        "failure",
        "cleanupFailure",
    }
)
_TRANSITIONS = {
    None: {"prepared"},
    "prepared": {"partial", "stopped"},
    "partial": {"partial", "running", "stopped"},
    "running": {"stopped"},
    "stopped": {"prepared"},
}
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_IMAGE_ROLE = re.compile(r"[a-z][a-z0-9-]*")
_OCI_SCHEMA = "stackctl-package-oci-images"
_OCI_FIELDS = frozenset(
    {
        "schema",
        "environment",
        "target",
        "configurationDigest",
        "buildInputDigest",
        "imageDigest",
        "images",
    }
)
_OCI_IMAGE_FIELD_SETS = (
    frozenset({"ref", "imageDigest"}),
    frozenset({"buildInputDigest", "ref", "imageDigest"}),
)
_IMAGE_COMPOSITION_FIELDS = frozenset(
    {
        "configurationDigest",
        "buildInputDigest",
        "imageDigest",
        "imageVersion",
        "images",
        "ociImages",
    }
)
_ACTIVE_CANDIDATE_FIELDS = frozenset(
    {
        "schema",
        "candidateType",
        "target",
        "baselineId",
        "candidateDir",
    }
)
_IMMUTABLE_RECEIPT_IDENTITY_FIELDS = (
    "env",
    "target",
    "workload",
    "composeProject",
    "candidateDigest",
    "configurationDigest",
    "providerRuntimeDigest",
    "observabilityLogSinkDigest",
    "imageTransportTag",
    "imageComposition",
    "runRoot",
    "startedAt",
)
_FANOUT_TRANSACTION_SCHEMA = "stackctl-startup-attempt-fanout-transaction"
_FANOUT_TRANSACTION_FIELDS = frozenset(
    {
        "schema",
        "transactionId",
        "newPayload",
        "destinations",
    }
)
_FANOUT_DESTINATION_FIELDS = frozenset({"path", "oldPayload"})


def startup_attempt_path(target: str) -> Path:
    return target_process_dir(target) / "startup_attempt.json"


def startup_attempt_path_for_workload(target: str, workload: str) -> Path:
    normalized = str(workload or "").strip()
    if normalized not in {"full", "content-release", "content-commercial"}:
        raise ValueError(f"startup attempt workload is invalid: {normalized or '<empty>'}")
    return startup_attempt_path(target).parent / "workloads" / normalized / "startup_attempt.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any] | None:
    payload = _secure_read(path)
    if payload is None:
        return None
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"startup attempt receipt is unreadable: {exc}") from exc
    return validate_startup_attempt(value)


def validate_startup_attempt(
    value: object,
    *,
    expected_env: str = "",
    expected_target: str = "",
) -> dict[str, Any]:
    """Validate the sole startup identity consumed by every runtime reader."""

    if not isinstance(value, dict) or set(value) != RECEIPT_FIELDS:
        raise ValueError("startup attempt receipt fields mismatch")
    if value.get("schema") != SCHEMA:
        raise ValueError("startup attempt receipt schema mismatch")
    env = str(value.get("env") or "").strip()
    target = str(value.get("target") or "").strip()
    if env not in {"alpha", "beta", "gamma"} or target != f"{env}-local":
        raise ValueError("startup attempt receipt target identity mismatch")
    if expected_env and env != expected_env:
        raise ValueError("startup attempt receipt environment mismatch")
    if expected_target and target != expected_target:
        raise ValueError("startup attempt receipt target mismatch")
    run_root_text = str(value.get("runRoot") or "").strip()
    canonical_run_root = _canonical_run_root(run_root_text, env=env)
    if canonical_run_root is not None and run_root_text != str(canonical_run_root):
        raise ValueError("startup attempt receipt runRoot is not canonical")
    if value.get("status") not in STATUSES:
        raise ValueError("startup attempt receipt status is invalid")
    workload = str(value.get("workload") or "").strip()
    if workload not in WORKLOADS:
        raise ValueError("startup attempt receipt workload is invalid")
    for field in ("attemptId", "composeProject"):
        if not str(value.get(field) or "").strip():
            raise ValueError(f"startup attempt receipt {field} is required")
    for field in (
        "candidateDigest",
        "configurationDigest",
        "providerRuntimeDigest",
        "imageTransportTag",
    ):
        if _DIGEST.fullmatch(str(value.get(field) or "")) is None:
            raise ValueError(f"startup attempt receipt {field} is invalid")
    observability_digest = str(value.get("observabilityLogSinkDigest") or "")
    if workload in {"full", "content-commercial"}:
        if _DIGEST.fullmatch(observability_digest) is None:
            raise ValueError(
                "startup attempt receipt observabilityLogSinkDigest is invalid"
            )
    elif observability_digest and _DIGEST.fullmatch(observability_digest) is None:
        raise ValueError(
            "startup attempt receipt observabilityLogSinkDigest is invalid"
        )

    composition = value.get("imageComposition")
    if not isinstance(composition, dict) or set(composition) != _IMAGE_COMPOSITION_FIELDS:
        raise ValueError("startup attempt receipt imageComposition fields mismatch")
    for field in ("configurationDigest", "buildInputDigest", "imageDigest"):
        if _DIGEST.fullmatch(str(composition.get(field) or "")) is None:
            raise ValueError(
                f"startup attempt receipt imageComposition {field} is invalid"
            )
    if composition["configurationDigest"] != value["configurationDigest"]:
        raise ValueError(
            "startup attempt receipt configuration differs from OCI composition"
        )
    images = composition.get("images")
    oci_images = composition.get("ociImages")
    if (
        not isinstance(images, dict)
        or not images
        or not isinstance(oci_images, dict)
        or set(images) != set(oci_images)
    ):
        raise ValueError("startup attempt receipt imageComposition has no images")
    refs: dict[str, str] = {}
    for service, descriptor in sorted(images.items()):
        if (
            _IMAGE_ROLE.fullmatch(str(service)) is None
            or not isinstance(descriptor, dict)
            or set(descriptor) != {"ref"}
            or _DIGEST.fullmatch(str(descriptor.get("ref") or "")) is None
        ):
            raise ValueError(
                f"startup attempt receipt image descriptor is invalid: {service}"
            )
        oci_descriptor = oci_images.get(service)
        if not isinstance(oci_descriptor, dict):
            raise TypeError(
                f"startup attempt receipt OCI image descriptor is invalid: {service}"
            )
        normalized_oci_descriptor = {
            str(key): str(item) for key, item in oci_descriptor.items()
        }
        if frozenset(normalized_oci_descriptor) not in _OCI_IMAGE_FIELD_SETS:
            raise ValueError(
                f"startup attempt receipt OCI image descriptor fields mismatch: {service}"
            )
        image_digest = str(normalized_oci_descriptor.get("imageDigest") or "")
        source_ref = str(normalized_oci_descriptor.get("ref") or "")
        build_input_digest = normalized_oci_descriptor.get("buildInputDigest")
        if (
            not source_ref
            or _DIGEST.fullmatch(image_digest) is None
            or (
                build_input_digest is not None
                and _DIGEST.fullmatch(build_input_digest) is None
            )
            or descriptor["ref"] != image_digest
        ):
            raise ValueError(
                f"startup attempt receipt OCI image identity is invalid: {service}"
            )
        refs[service] = image_digest
    if _sha256_json(oci_images) != composition["imageDigest"]:
        raise ValueError("startup attempt receipt OCI imageDigest mismatch")
    expected_image_version = immutable_image_digest(refs)
    if (
        composition.get("imageVersion") != expected_image_version
        or value.get("imageTransportTag") != expected_image_version
    ):
        raise ValueError("startup attempt receipt image composition mismatch")
    for field in ("startedAt", "updatedAt"):
        timestamp = str(value.get(field) or "")
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(
                f"startup attempt receipt {field} is invalid"
            ) from exc
    for field in ("failure", "cleanupFailure"):
        if value.get(field) is not None and not isinstance(value.get(field), str):
            raise ValueError(f"startup attempt receipt {field} is invalid")
    return value


def load_startup_attempt(target: str) -> dict[str, Any] | None:
    path = startup_attempt_path(target)
    _recover_fanout_transaction(
        path,
        expected_env=_environment_for_target(target),
        expected_target=target,
    )
    return _read(path)


def load_workload_startup_attempt(
    target: str,
    workload: str,
) -> dict[str, Any] | None:
    _recover_fanout_transaction(
        startup_attempt_path(target),
        expected_env=_environment_for_target(target),
        expected_target=target,
    )
    return _read(startup_attempt_path_for_workload(target, workload))


class _UnsafeStartupReceiptPath(ValueError):
    pass


def _directory_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise RuntimeError(
            "startup receipt persistence requires O_NOFOLLOW/O_DIRECTORY"
        )
    return os.O_RDONLY | nofollow | directory | getattr(os, "O_CLOEXEC", 0)


def _file_flags(*, write: bool) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise RuntimeError("startup receipt persistence requires O_NOFOLLOW")
    access = os.O_WRONLY | os.O_CREAT | os.O_EXCL if write else os.O_RDONLY
    return access | nofollow | getattr(os, "O_CLOEXEC", 0)


def _absolute_path(path: Path) -> Path:
    expanded = path.expanduser()
    candidate = expanded if expanded.is_absolute() else Path.cwd() / expanded
    normalized = Path(os.path.abspath(candidate))
    if not normalized.is_absolute() or not normalized.name:
        raise _UnsafeStartupReceiptPath("startup receipt path is unsafe")
    return normalized


def _open_parent(
    path: Path,
    *,
    create: bool,
) -> tuple[int, tuple[tuple[int, int], ...]]:
    absolute = _absolute_path(path)
    descriptor = os.open(absolute.anchor, _directory_flags())
    identities: list[tuple[int, int]] = []
    try:
        for part in absolute.parent.parts[1:]:
            try:
                child = os.open(part, _directory_flags(), dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                try:
                    child = os.open(part, _directory_flags(), dir_fd=descriptor)
                except OSError as exc:
                    raise _UnsafeStartupReceiptPath(
                        f"startup receipt parent is unsafe: {part}"
                    ) from exc
            except OSError as exc:
                raise _UnsafeStartupReceiptPath(
                    f"startup receipt parent is a symlink or non-directory: {part}"
                ) from exc
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            if not stat.S_ISDIR(info.st_mode):
                raise _UnsafeStartupReceiptPath(
                    f"startup receipt parent is not a directory: {part}"
                )
            identities.append((info.st_dev, info.st_ino))
        return descriptor, tuple(identities)
    except Exception:
        os.close(descriptor)
        raise


def _revalidate_parent(
    path: Path,
    *,
    expected: tuple[tuple[int, int], ...],
) -> None:
    descriptor, identities = _open_parent(path, create=False)
    os.close(descriptor)
    if identities != expected:
        raise _UnsafeStartupReceiptPath(
            "startup receipt parent changed during persistence"
        )


def _entry_info(parent_descriptor: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise _UnsafeStartupReceiptPath(
            f"startup receipt final path is unsafe: {name}"
        ) from exc


def _secure_read(
    path: Path,
    *,
    label: str = "startup attempt receipt",
) -> bytes | None:
    absolute = _absolute_path(path)
    try:
        parent_descriptor, identities = _open_parent(absolute, create=False)
    except FileNotFoundError:
        return None
    descriptor = -1
    try:
        before = _entry_info(parent_descriptor, absolute.name)
        if before is None:
            return None
        if not stat.S_ISREG(before.st_mode):
            raise _UnsafeStartupReceiptPath(
                f"{label} is a symlink or non-regular file"
            )
        try:
            descriptor = os.open(
                absolute.name,
                _file_flags(write=False),
                dir_fd=parent_descriptor,
            )
        except OSError as exc:
            raise _UnsafeStartupReceiptPath(
                f"{label} is a symlink or unreadable"
            ) from exc
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise _UnsafeStartupReceiptPath(
                f"{label} changed during validation"
            )
        _revalidate_parent(absolute, expected=identities)
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            return handle.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_descriptor)


@dataclass(frozen=True)
class _StagedReceiptWrite:
    path: Path
    temporary_name: str
    temporary_identity: tuple[int, int]
    parent_identities: tuple[tuple[int, int], ...]


def _encode_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _stage_receipt_bytes(path: Path, encoded: bytes) -> _StagedReceiptWrite:
    absolute = _absolute_path(path)
    parent_descriptor, identities = _open_parent(absolute, create=True)
    temporary = f".{absolute.name}.{uuid4().hex}.tmp"
    descriptor = -1
    temporary_exists = False
    try:
        current = _entry_info(parent_descriptor, absolute.name)
        if current is not None and not stat.S_ISREG(current.st_mode):
            raise _UnsafeStartupReceiptPath(
                "startup attempt receipt final path is a symlink or non-regular file"
            )
        descriptor = os.open(
            temporary,
            _file_flags(write=True),
            0o600,
            dir_fd=parent_descriptor,
        )
        temporary_exists = True
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("startup receipt temporary write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise _UnsafeStartupReceiptPath(
                "startup attempt receipt temporary path is not a regular file"
            )
        expected_identity = (info.st_dev, info.st_ino)
        os.close(descriptor)
        descriptor = -1
        _revalidate_parent(absolute, expected=identities)
        staged = _StagedReceiptWrite(
            path=absolute,
            temporary_name=temporary,
            temporary_identity=expected_identity,
            parent_identities=identities,
        )
        temporary_exists = False
        return staged
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_exists:
            try:
                os.unlink(temporary, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)


def _commit_staged_receipt(staged: _StagedReceiptWrite) -> None:
    absolute = staged.path
    parent_descriptor, identities = _open_parent(absolute, create=False)
    try:
        if identities != staged.parent_identities:
            raise _UnsafeStartupReceiptPath(
                "startup receipt parent changed before commit"
            )
        temporary = _entry_info(parent_descriptor, staged.temporary_name)
        if (
            temporary is None
            or not stat.S_ISREG(temporary.st_mode)
            or (temporary.st_dev, temporary.st_ino) != staged.temporary_identity
        ):
            raise _UnsafeStartupReceiptPath(
                "startup receipt staged entry changed before commit"
            )
        current = _entry_info(parent_descriptor, absolute.name)
        if current is not None and not stat.S_ISREG(current.st_mode):
            raise _UnsafeStartupReceiptPath(
                "startup attempt receipt final path is a symlink or non-regular file"
            )
        os.replace(
            staged.temporary_name,
            absolute.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        os.fsync(parent_descriptor)
        _revalidate_parent(absolute, expected=identities)
        final_descriptor = os.open(
            absolute.name,
            _file_flags(write=False),
            dir_fd=parent_descriptor,
        )
        try:
            final_info = os.fstat(final_descriptor)
            if (
                not stat.S_ISREG(final_info.st_mode)
                or (final_info.st_dev, final_info.st_ino)
                != staged.temporary_identity
            ):
                raise _UnsafeStartupReceiptPath(
                    "startup attempt receipt changed after atomic write"
                )
        finally:
            os.close(final_descriptor)
    finally:
        os.close(parent_descriptor)


def _discard_staged_receipt(staged: _StagedReceiptWrite) -> None:
    try:
        parent_descriptor, identities = _open_parent(staged.path, create=False)
    except FileNotFoundError:
        return
    try:
        if identities != staged.parent_identities:
            return
        temporary = _entry_info(parent_descriptor, staged.temporary_name)
        if temporary is None:
            return
        if (
            stat.S_ISREG(temporary.st_mode)
            and (temporary.st_dev, temporary.st_ino) == staged.temporary_identity
        ):
            os.unlink(staged.temporary_name, dir_fd=parent_descriptor)
            os.fsync(parent_descriptor)
    finally:
        os.close(parent_descriptor)


def _atomic_write_bytes(path: Path, encoded: bytes) -> None:
    staged = _stage_receipt_bytes(path, encoded)
    try:
        _commit_staged_receipt(staged)
    finally:
        _discard_staged_receipt(staged)


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_write_bytes(path, _encode_json(payload))


def _prevalidate_write_path(path: Path) -> None:
    absolute = _absolute_path(path)
    parent_descriptor, identities = _open_parent(absolute, create=True)
    try:
        current = _entry_info(parent_descriptor, absolute.name)
        if current is not None and not stat.S_ISREG(current.st_mode):
            raise _UnsafeStartupReceiptPath(
                "startup attempt receipt final path is a symlink or non-regular file"
            )
        _revalidate_parent(absolute, expected=identities)
    finally:
        os.close(parent_descriptor)


def _secure_unlink_if_matches(path: Path, expected: bytes) -> None:
    absolute = _absolute_path(path)
    parent_descriptor, identities = _open_parent(absolute, create=False)
    descriptor = -1
    try:
        before = _entry_info(parent_descriptor, absolute.name)
        if before is None or not stat.S_ISREG(before.st_mode):
            raise _UnsafeStartupReceiptPath(
                "startup receipt transaction entry is missing or unsafe"
            )
        descriptor = os.open(
            absolute.name,
            _file_flags(write=False),
            dir_fd=parent_descriptor,
        )
        info = os.fstat(descriptor)
        if (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino):
            raise _UnsafeStartupReceiptPath(
                "startup receipt transaction entry changed during validation"
            )
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            actual = handle.read()
        if actual != expected:
            raise _UnsafeStartupReceiptPath(
                "startup receipt transaction entry content drifted"
            )
        _revalidate_parent(absolute, expected=identities)
        current = _entry_info(parent_descriptor, absolute.name)
        if (
            current is None
            or (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise _UnsafeStartupReceiptPath(
                "startup receipt transaction entry changed before removal"
            )
        os.unlink(absolute.name, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
        _revalidate_parent(absolute, expected=identities)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_descriptor)


def _write_transaction_journal_exclusive(path: Path, encoded: bytes) -> None:
    absolute = _absolute_path(path)
    parent_descriptor, identities = _open_parent(absolute, create=True)
    descriptor = -1
    created_identity: tuple[int, int] | None = None
    completed = False
    try:
        if _entry_info(parent_descriptor, absolute.name) is not None:
            raise _UnsafeStartupReceiptPath(
                "startup fan-out transaction journal already exists"
            )
        descriptor = os.open(
            absolute.name,
            _file_flags(write=True),
            0o600,
            dir_fd=parent_descriptor,
        )
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise _UnsafeStartupReceiptPath(
                "startup fan-out transaction journal is not a regular file"
            )
        created_identity = (info.st_dev, info.st_ino)
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("startup fan-out journal write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.fsync(parent_descriptor)
        _revalidate_parent(absolute, expected=identities)
        current = _entry_info(parent_descriptor, absolute.name)
        if (
            current is None
            or not stat.S_ISREG(current.st_mode)
            or (current.st_dev, current.st_ino) != created_identity
        ):
            raise _UnsafeStartupReceiptPath(
                "startup fan-out transaction journal changed after creation"
            )
        completed = True
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if not completed and created_identity is not None:
            current = _entry_info(parent_descriptor, absolute.name)
            if (
                current is not None
                and (current.st_dev, current.st_ino) == created_identity
            ):
                os.unlink(absolute.name, dir_fd=parent_descriptor)
                os.fsync(parent_descriptor)
        os.close(parent_descriptor)


def _environment_for_target(target: str) -> str:
    normalized = str(target or "").strip()
    for environment in ("alpha", "beta", "gamma"):
        if normalized == f"{environment}-local":
            return environment
    raise ValueError("startup attempt target identity mismatch")


def _fanout_destinations(
    canonical_path: Path,
    payload: Mapping[str, Any],
) -> list[Path]:
    workload = str(payload.get("workload") or "").strip()
    target = str(payload.get("target") or "").strip()
    destinations = [startup_attempt_path_for_workload(target, workload)]
    run_root = str(payload.get("runRoot") or "").strip()
    if run_root:
        destinations.append(Path(run_root) / "startup_attempt.json")
    destinations.append(canonical_path)
    normalized = [_absolute_path(item) for item in destinations]
    if len(set(normalized)) != len(normalized):
        raise ValueError("startup attempt receipt fan-out destinations overlap")
    return normalized


def _fanout_transaction_path(canonical_path: Path) -> Path:
    absolute = _absolute_path(canonical_path)
    return absolute.with_name(f".{absolute.name}.fanout-transaction.json")


def _validate_old_receipt_text(
    value: object,
    *,
    expected_env: str,
    expected_target: str,
) -> bytes | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("startup fan-out transaction oldPayload is invalid")
    encoded = value.encode("utf-8")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"startup fan-out transaction oldPayload is unreadable: {exc}"
        ) from exc
    validate_startup_attempt(
        parsed,
        expected_env=expected_env,
        expected_target=expected_target,
    )
    if _encode_json(parsed) != encoded:
        raise ValueError("startup fan-out transaction oldPayload is not canonical")
    return encoded


def _validate_fanout_transaction(
    value: object,
    *,
    canonical_path: Path,
    expected_env: str,
    expected_target: str,
) -> tuple[dict[str, Any], list[tuple[Path, bytes | None]]]:
    if not isinstance(value, dict) or set(value) != _FANOUT_TRANSACTION_FIELDS:
        raise ValueError("startup fan-out transaction fields mismatch")
    if value.get("schema") != _FANOUT_TRANSACTION_SCHEMA:
        raise ValueError("startup fan-out transaction schema mismatch")
    if not str(value.get("transactionId") or "").strip():
        raise ValueError("startup fan-out transaction id is missing")
    new_payload = validate_startup_attempt(
        value.get("newPayload"),
        expected_env=expected_env,
        expected_target=expected_target,
    )
    expected_paths = _fanout_destinations(canonical_path, new_payload)
    raw_destinations = value.get("destinations")
    if not isinstance(raw_destinations, list) or len(raw_destinations) != len(
        expected_paths
    ):
        raise ValueError("startup fan-out transaction destinations mismatch")
    destinations: list[tuple[Path, bytes | None]] = []
    for expected_path, raw_destination in zip(
        expected_paths,
        raw_destinations,
        strict=True,
    ):
        if (
            not isinstance(raw_destination, dict)
            or set(raw_destination) != _FANOUT_DESTINATION_FIELDS
            or raw_destination.get("path") != str(expected_path)
        ):
            raise ValueError("startup fan-out transaction destination is invalid")
        old_payload = _validate_old_receipt_text(
            raw_destination.get("oldPayload"),
            expected_env=expected_env,
            expected_target=expected_target,
        )
        destinations.append((expected_path, old_payload))
    return new_payload, destinations


def _rollback_fanout_transaction(
    value: object,
    *,
    canonical_path: Path,
    expected_env: str,
    expected_target: str,
) -> None:
    new_payload, destinations = _validate_fanout_transaction(
        value,
        canonical_path=canonical_path,
        expected_env=expected_env,
        expected_target=expected_target,
    )
    new_encoded = _encode_json(new_payload)
    errors: list[str] = []
    for destination, old_encoded in reversed(destinations):
        try:
            current = _secure_read(
                destination,
                label="startup fan-out transaction destination",
            )
            if current == old_encoded:
                continue
            if current != new_encoded:
                raise _UnsafeStartupReceiptPath(
                    f"startup fan-out destination drifted: {destination}"
                )
            if old_encoded is None:
                _secure_unlink_if_matches(destination, new_encoded)
            else:
                _atomic_write_bytes(destination, old_encoded)
        except Exception as exc:  # keep restoring the other replicas
            errors.append(f"{destination}: {exc}")
    if errors:
        raise RuntimeError(
            "startup fan-out rollback could not restore every destination: "
            + "; ".join(errors)
        )


def _recover_fanout_transaction(
    canonical_path: Path,
    *,
    expected_env: str,
    expected_target: str,
) -> None:
    journal_path = _fanout_transaction_path(canonical_path)
    journal_bytes = _secure_read(
        journal_path,
        label="startup fan-out transaction journal",
    )
    if journal_bytes is None:
        return
    try:
        value = json.loads(journal_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"startup fan-out transaction journal is unreadable: {exc}"
        ) from exc
    _rollback_fanout_transaction(
        value,
        canonical_path=canonical_path,
        expected_env=expected_env,
        expected_target=expected_target,
    )
    _secure_unlink_if_matches(journal_path, journal_bytes)


def _transactional_fanout_write(
    canonical_path: Path,
    destinations: list[Path],
    payload: Mapping[str, Any],
) -> None:
    expected_env = str(payload["env"])
    expected_target = str(payload["target"])
    encoded = _encode_json(payload)
    old_payloads = [
        _secure_read(path, label="startup fan-out destination")
        for path in destinations
    ]
    old_payload_texts: list[str | None] = []
    for old in old_payloads:
        if old is None:
            old_payload_texts.append(None)
            continue
        validated_old = _validate_old_receipt_text(
            old.decode("utf-8"),
            expected_env=expected_env,
            expected_target=expected_target,
        )
        assert validated_old is not None
        old_payload_texts.append(validated_old.decode("utf-8"))
    stages: list[_StagedReceiptWrite] = []
    for destination in destinations:
        try:
            stages.append(_stage_receipt_bytes(destination, encoded))
        except Exception:
            for staged in stages:
                _discard_staged_receipt(staged)
            raise

    journal = {
        "schema": _FANOUT_TRANSACTION_SCHEMA,
        "transactionId": uuid4().hex,
        "newPayload": dict(payload),
        "destinations": [
            {
                "path": str(destination),
                "oldPayload": old_text,
            }
            for destination, old_text in zip(
                destinations,
                old_payload_texts,
                strict=True,
            )
        ],
    }
    journal_path = _fanout_transaction_path(canonical_path)
    journal_bytes = _encode_json(journal)
    journal_written = False
    try:
        _write_transaction_journal_exclusive(journal_path, journal_bytes)
        journal_written = True
        for staged in stages:
            _commit_staged_receipt(staged)
        _secure_unlink_if_matches(journal_path, journal_bytes)
        journal_written = False
    except Exception as original:
        if journal_written:
            try:
                _rollback_fanout_transaction(
                    journal,
                    canonical_path=canonical_path,
                    expected_env=expected_env,
                    expected_target=expected_target,
                )
                current_journal = _secure_read(
                    journal_path,
                    label="startup fan-out transaction journal",
                )
                if current_journal is not None:
                    _secure_unlink_if_matches(journal_path, journal_bytes)
            except Exception as rollback_error:
                raise RuntimeError(
                    "startup fan-out commit failed and rollback was incomplete"
                ) from rollback_error
        raise original
    finally:
        for staged in stages:
            _discard_staged_receipt(staged)


def _canonical_run_root(value: str, *, env: str) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = _absolute_path(Path(text))
    expected_parent = _absolute_path(output_root()) / "env" / env / "runs"
    try:
        relative = candidate.relative_to(expected_parent)
    except ValueError as exc:
        raise ValueError(
            "startup attempt runRoot must be target-environment run evidence"
        ) from exc
    if (
        len(relative.parts) != 1
        or relative.name in {"", ".", ".."}
        or "/" in relative.name
        or "\\" in relative.name
    ):
        raise ValueError(
            "startup attempt runRoot must be one canonical run directory"
        )
    return candidate


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def image_composition_from_candidate_oci(
    value: object,
    *,
    expected_environment: str = "",
    expected_target: str = "",
) -> dict[str, Any]:
    """Project the complete package OCI role closure into startup identity."""

    if not isinstance(value, dict) or set(value) != _OCI_FIELDS:
        raise ValueError("startup OCI image manifest fields mismatch")
    if value.get("schema") != _OCI_SCHEMA:
        raise ValueError("startup OCI image manifest schema mismatch")
    if expected_environment and value.get("environment") != expected_environment:
        raise ValueError("startup OCI image manifest environment mismatch")
    if expected_target and value.get("target") != expected_target:
        raise ValueError("startup OCI image manifest target mismatch")
    for field in ("configurationDigest", "buildInputDigest", "imageDigest"):
        if _DIGEST.fullmatch(str(value.get(field) or "")) is None:
            raise ValueError(f"startup OCI image manifest {field} is invalid")

    images = value.get("images")
    if not isinstance(images, dict) or not images:
        raise ValueError("startup OCI image manifest has no images")
    normalized_images: dict[str, dict[str, str]] = {}
    runtime_refs: dict[str, str] = {}
    for raw_role, raw_descriptor in sorted(images.items()):
        role = str(raw_role)
        if _IMAGE_ROLE.fullmatch(role) is None or not isinstance(
            raw_descriptor, dict
        ):
            raise ValueError(f"startup OCI image descriptor is invalid: {role}")
        descriptor = {str(key): str(item) for key, item in raw_descriptor.items()}
        if frozenset(descriptor) not in _OCI_IMAGE_FIELD_SETS:
            raise ValueError(f"startup OCI image descriptor fields mismatch: {role}")
        if not descriptor["ref"] or _DIGEST.fullmatch(
            descriptor["imageDigest"]
        ) is None:
            raise ValueError(f"startup OCI image identity is invalid: {role}")
        build_input_digest = descriptor.get("buildInputDigest")
        if build_input_digest is not None and _DIGEST.fullmatch(
            build_input_digest
        ) is None:
            raise ValueError(
                f"startup OCI Provider build input identity is invalid: {role}"
            )
        normalized_images[role] = descriptor
        runtime_refs[role] = descriptor["imageDigest"]
    if _sha256_json(normalized_images) != value["imageDigest"]:
        raise ValueError("startup OCI image manifest imageDigest mismatch")

    return {
        "configurationDigest": str(value["configurationDigest"]),
        "buildInputDigest": str(value["buildInputDigest"]),
        "imageDigest": str(value["imageDigest"]),
        "imageVersion": immutable_image_digest(runtime_refs),
        "images": {
            role: {"ref": image_digest}
            for role, image_digest in sorted(runtime_refs.items())
        },
        "ociImages": normalized_images,
    }


def load_candidate_oci_image_composition(
    path: Path,
    *,
    expected_environment: str,
    expected_target: str,
    expected_candidate_digest: str = "",
) -> dict[str, Any]:
    if not expected_target:
        raise ValueError("startup OCI image manifest requires expected target")
    if (
        expected_environment not in {"alpha", "beta", "gamma"}
        or expected_target != f"{expected_environment}-local"
    ):
        raise ValueError("startup OCI expected target identity mismatch")
    pointer_path = active_candidate_manifest_path(expected_target)
    pointer_bytes = _secure_read(
        pointer_path,
        label="active deployment candidate",
    )
    if pointer_bytes is None:
        raise ValueError("startup OCI image manifest has no active candidate")
    try:
        active = json.loads(pointer_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"active deployment candidate is unreadable: {exc}") from exc
    if not isinstance(active, dict) or set(active) != _ACTIVE_CANDIDATE_FIELDS:
        raise ValueError("active deployment candidate fields mismatch")
    baseline_id = str(active.get("baselineId") or "").strip()
    candidate_root = deployment_candidate_dir(expected_target, baseline_id)
    if (
        active.get("schema") != ACTIVE_CANDIDATE_SCHEMA
        or active.get("candidateType") != "runtime-full"
        or active.get("target") != expected_target
        or active.get("candidateDir") != str(candidate_root)
    ):
        raise ValueError("active deployment candidate identity mismatch")
    normalized_expected_candidate = str(expected_candidate_digest or "").strip()
    if (
        normalized_expected_candidate
        and normalized_expected_candidate != baseline_id
    ):
        raise ValueError("startup OCI candidate digest mismatch")
    candidate = load_candidate_manifest(
        expected_environment,
        expected_target,
        baseline_id,
        require_full=True,
    )
    expected_path = (
        candidate_root / "packages" / "runtime-shared" / "oci-images.json"
    )
    if _absolute_path(path) != _absolute_path(expected_path):
        raise ValueError(
            "startup OCI image manifest must be the active candidate fixed artifact"
        )
    payload = _secure_read(expected_path, label="startup OCI image manifest")
    if payload is None:
        raise ValueError("startup OCI image manifest is missing or unsafe")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"startup OCI image manifest is unreadable: {exc}") from exc
    composition = image_composition_from_candidate_oci(
        value,
        expected_environment=expected_environment,
        expected_target=expected_target,
    )
    if (
        candidate.get("baselineId") != baseline_id
        or candidate.get("configurationDigest")
        != composition["configurationDigest"]
        or candidate.get("buildInputDigest") != composition["buildInputDigest"]
        or candidate.get("imageDigest") != composition["imageDigest"]
    ):
        raise ValueError("startup OCI image manifest differs from active candidate")
    pointer_after = _secure_read(
        pointer_path,
        label="active deployment candidate",
    )
    if pointer_after != pointer_bytes:
        raise ValueError("active deployment candidate changed during OCI validation")
    return composition


def transition_startup_attempt(
    *,
    env: str,
    target: str,
    attempt_id: str,
    status: str,
    workload: str = "",
    compose_project: str = "",
    candidate_digest: str = "",
    configuration_digest: str = "",
    provider_runtime_digest: str = "",
    observability_log_sink_digest: str = "",
    image_transport_tag: str = "",
    image_composition: Mapping[str, Any] | None = None,
    run_root: str = "",
    failure: str = "",
    cleanup_failure: str = "",
) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"startup attempt status is invalid: {status}")
    path = startup_attempt_path(target)
    _recover_fanout_transaction(
        path,
        expected_env=env,
        expected_target=target,
    )
    previous = _read(path)
    previous_status = str(previous.get("status")) if previous else None
    if status not in _TRANSITIONS.get(previous_status, set()):
        raise ValueError(
            f"startup attempt transition is invalid: {previous_status!r} -> {status!r}"
        )
    normalized_attempt = str(attempt_id or "").strip()
    if status == "prepared":
        if not normalized_attempt:
            raise ValueError("prepared startup attempt requires attemptId")
        if previous is not None and normalized_attempt == previous.get("attemptId"):
            raise ValueError("prepared startup attempt requires a new attemptId")
        started_at = _utc_now()
        identity = {
            "env": str(env or "").strip(),
            "target": str(target or "").strip(),
            "workload": str(workload or "").strip(),
            "composeProject": str(compose_project or "").strip(),
            "candidateDigest": str(candidate_digest or "").strip(),
            "configurationDigest": str(configuration_digest or "").strip(),
            "providerRuntimeDigest": str(provider_runtime_digest or "").strip(),
            "observabilityLogSinkDigest": str(
                observability_log_sink_digest or ""
            ).strip(),
            "imageTransportTag": str(image_transport_tag or "").strip(),
            "imageComposition": dict(image_composition or {}),
            "runRoot": str(run_root or "").strip(),
        }
        if identity["workload"] not in WORKLOADS:
            raise ValueError("prepared startup attempt requires workload")
        if not identity["composeProject"]:
            raise ValueError("prepared startup attempt requires Compose project")
        if _DIGEST.fullmatch(str(identity["candidateDigest"])) is None:
            raise ValueError("prepared startup attempt requires candidate digest")
        if _DIGEST.fullmatch(str(identity["configurationDigest"])) is None:
            raise ValueError("prepared startup attempt requires configuration digest")
        if _DIGEST.fullmatch(str(identity["providerRuntimeDigest"])) is None:
            raise ValueError("prepared startup attempt requires Provider runtime digest")
        if identity["workload"] in {"full", "content-commercial"} and _DIGEST.fullmatch(
            str(identity["observabilityLogSinkDigest"])
        ) is None:
            raise ValueError(
                "prepared startup attempt requires observability log-sink digest"
            )
        if not identity["imageComposition"]:
            raise ValueError("prepared startup attempt requires image composition")
        if identity["imageTransportTag"] != identity["imageComposition"].get(
            "imageVersion"
        ):
            raise ValueError("prepared startup attempt image composition mismatch")
    else:
        if previous is None:
            raise ValueError("startup attempt transition requires an existing receipt")
        if normalized_attempt and normalized_attempt != previous.get("attemptId"):
            raise ValueError("startup attempt identity mismatch")
        normalized_attempt = str(previous["attemptId"])
        started_at = str(previous["startedAt"])
        assert previous is not None
        supplied_identity = {
            "workload": workload,
            "composeProject": compose_project,
            "candidateDigest": candidate_digest,
            "configurationDigest": configuration_digest,
            "providerRuntimeDigest": provider_runtime_digest,
            "observabilityLogSinkDigest": observability_log_sink_digest,
            "imageTransportTag": image_transport_tag,
            "runRoot": run_root,
        }
        for field, supplied in supplied_identity.items():
            normalized = str(supplied or "").strip()
            if normalized and normalized != str(previous.get(field) or "").strip():
                raise ValueError(f"startup attempt identity mismatch: {field}")
        if image_composition is not None and dict(image_composition) != previous.get(
            "imageComposition"
        ):
            raise ValueError("startup attempt identity mismatch: imageComposition")
        identity = {
            field: previous[field]
            for field in (
                "env",
                "target",
                "workload",
                "composeProject",
                "candidateDigest",
                "configurationDigest",
                "providerRuntimeDigest",
                "observabilityLogSinkDigest",
                "imageTransportTag",
                "imageComposition",
                "runRoot",
            )
        }

    payload = {
        "schema": SCHEMA,
        "attemptId": normalized_attempt,
        "env": identity["env"],
        "target": identity["target"],
        "status": status,
        "workload": identity["workload"],
        "composeProject": identity["composeProject"],
        "candidateDigest": identity["candidateDigest"],
        "configurationDigest": identity["configurationDigest"],
        "providerRuntimeDigest": identity["providerRuntimeDigest"],
        "observabilityLogSinkDigest": identity["observabilityLogSinkDigest"],
        "imageTransportTag": identity["imageTransportTag"],
        "imageComposition": identity["imageComposition"],
        "runRoot": identity["runRoot"],
        "startedAt": started_at,
        "updatedAt": _utc_now(),
        "failure": str(failure or "").strip() or None,
        "cleanupFailure": str(cleanup_failure or "").strip() or None,
    }
    if payload["env"] != env or payload["target"] != target:
        raise ValueError("startup attempt target identity mismatch")
    validate_startup_attempt(payload, expected_env=env, expected_target=target)
    run_receipt_path: Path | None = None
    run_path_text = str(payload["runRoot"] or "").strip()
    if run_path_text:
        run_receipt_path = Path(run_path_text) / "startup_attempt.json"
        existing_run_receipt = _read(run_receipt_path)
        if existing_run_receipt is not None:
            if existing_run_receipt["attemptId"] != payload["attemptId"]:
                raise ValueError(
                    "startup attempt runRoot already belongs to a different attempt"
                )
            for field in _IMMUTABLE_RECEIPT_IDENTITY_FIELDS:
                if existing_run_receipt[field] != payload[field]:
                    raise ValueError(
                        f"startup attempt runRoot identity mismatch: {field}"
                    )
    destinations = _fanout_destinations(path, payload)
    for destination in destinations:
        _prevalidate_write_path(destination)
    _transactional_fanout_write(path, destinations, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--attempt-id", default="")
    parser.add_argument("--status", choices=STATUSES, required=True)
    parser.add_argument("--workload", default="")
    parser.add_argument("--compose-project", default="")
    parser.add_argument("--candidate-digest", default="")
    parser.add_argument("--configuration-digest", default="")
    parser.add_argument("--provider-runtime-digest", default="")
    parser.add_argument("--observability-log-sink-digest", default="")
    parser.add_argument("--image-transport-tag", default="")
    parser.add_argument("--image-composition-file", default="")
    parser.add_argument("--run-root", default="")
    parser.add_argument("--failure", default="")
    parser.add_argument("--cleanup-failure", default="")
    args = parser.parse_args()
    image_composition = None
    if args.image_composition_file:
        image_composition = load_candidate_oci_image_composition(
            Path(args.image_composition_file),
            expected_environment=args.env,
            expected_target=args.target,
            expected_candidate_digest=args.candidate_digest,
        )
    transition_startup_attempt(
        env=args.env,
        target=args.target,
        attempt_id=args.attempt_id,
        status=args.status,
        workload=args.workload,
        compose_project=args.compose_project,
        candidate_digest=args.candidate_digest,
        configuration_digest=args.configuration_digest,
        provider_runtime_digest=args.provider_runtime_digest,
        observability_log_sink_digest=args.observability_log_sink_digest,
        image_transport_tag=args.image_transport_tag,
        image_composition=image_composition,
        run_root=args.run_root,
        failure=args.failure,
        cleanup_failure=args.cleanup_failure,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
