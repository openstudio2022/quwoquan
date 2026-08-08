"""Immutable local deployment candidate identity and release binding."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from quwoquan_ops.cli.lib.immutable_image_composition import (
    first_party_service_names,
    immutable_image_digest,
)
from quwoquan_ops.cli.lib.output_paths import (
    app_deployment_package_dir,
    deployment_candidate_dir,
    legal_static_deployment_package_dir,
    runtime_shared_deployment_package_dir,
)
from quwoquan_ops.cli.lib.provider_runtime_composition import (
    compile_provider_runtime_composition,
    validate_provider_runtime_composition,
)

CANDIDATE_MANIFEST_SCHEMA = "stackctl-deployment-candidate"
RUNTIME_CANDIDATE_TYPE = "runtime-full"
PROVIDER_RUNTIME_PACKAGE_SCHEMA = "stackctl-provider-runtime-package"
OBSERVABILITY_LOG_SINK_PACKAGE_SCHEMA = (
    "stackctl-observability-log-sink-package"
)
SPEC_REFS = (
    "AppRoot/JNY-002/SCN-005/UAT-003",
    "runtime/runtime-config/environment-topology-and-packaging/GWT-001",
    "runtime/runtime-config/environment-topology-and-packaging/GWT-002",
    "runtime/runtime-config/environment-ops-cli-and-skill/GWT-001",
    "runtime/deliver-deploy-prod-pipeline/SIT-001",
    "runtime/system-architecture-and-engineering-guide/SIT-003",
    "runtime/runtime-data-engineering/SIT-001",
)
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
ROOT = Path(__file__).resolve().parents[3]
LOG_SINK_ADAPTER_ID = "ext.obs.elasticsearch"
_ELASTICSEARCH_IMAGE_LITERAL_RE = re.compile(
    r"^docker\.elastic\.co/elasticsearch/elasticsearch@(sha256:[0-9a-f]{64})$"
)
_ELASTICSEARCH_IMAGE_DEFAULT_RE = re.compile(
    r"^\$\{QWQ_COMPOSE_ELASTICSEARCH_IMAGE:-"
    r"docker\.elastic\.co/elasticsearch/elasticsearch@(sha256:[0-9a-f]{64})\}$"
)


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return value


class _UnsafeCandidatePath(ValueError):
    pass


def _candidate_directory_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise RuntimeError("candidate verification requires O_NOFOLLOW/O_DIRECTORY")
    return os.O_RDONLY | nofollow | directory | getattr(os, "O_CLOEXEC", 0)


def _candidate_file_flags(*, write: bool) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise RuntimeError("candidate verification requires O_NOFOLLOW")
    access = os.O_WRONLY | os.O_CREAT | os.O_EXCL if write else os.O_RDONLY
    return access | nofollow | getattr(os, "O_CLOEXEC", 0)


def _candidate_relative_path(value: str | Path, *, label: str) -> Path:
    reference = Path(value)
    if (
        reference.is_absolute()
        or not reference.parts
        or any(part in {"", ".", ".."} for part in reference.parts)
    ):
        raise _UnsafeCandidatePath(f"{label} escapes the candidate root")
    return reference


def _open_candidate_root(
    candidate_root: Path,
    *,
    label: str,
) -> tuple[int, tuple[tuple[int, int], ...]]:
    """Open every absolute candidate ancestor without following symlinks."""

    absolute = Path(candidate_root).expanduser().absolute()
    if not absolute.is_absolute() or ".." in absolute.parts:
        raise _UnsafeCandidatePath(f"{label} candidate root is unsafe")
    try:
        descriptor = os.open(Path(absolute.anchor), _candidate_directory_flags())
    except OSError as exc:
        raise _UnsafeCandidatePath(
            f"{label} candidate filesystem root is unavailable"
        ) from exc
    identities: list[tuple[int, int]] = []
    try:
        root_info = os.fstat(descriptor)
        if not stat.S_ISDIR(root_info.st_mode):
            raise _UnsafeCandidatePath(
                f"{label} candidate filesystem root is not a directory"
            )
        identities.append((root_info.st_dev, root_info.st_ino))
        for part in absolute.parts[1:]:
            try:
                child = os.open(
                    part,
                    _candidate_directory_flags(),
                    dir_fd=descriptor,
                )
            except OSError as exc:
                raise _UnsafeCandidatePath(
                    f"{label} candidate ancestor is a symlink, missing, or "
                    f"non-directory: {part}"
                ) from exc
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            if not stat.S_ISDIR(info.st_mode):
                raise _UnsafeCandidatePath(
                    f"{label} candidate ancestor is not a directory: {part}"
                )
            identities.append((info.st_dev, info.st_ino))
        return descriptor, tuple(identities)
    except Exception:
        os.close(descriptor)
        raise


def _open_candidate_parent(
    candidate_root: Path,
    relative: Path,
    *,
    label: str,
) -> tuple[int, tuple[tuple[int, int], ...]]:
    descriptor, root_identities = _open_candidate_root(
        candidate_root,
        label=label,
    )
    identities = list(root_identities)
    try:
        for part in relative.parts[:-1]:
            try:
                child = os.open(
                    part,
                    _candidate_directory_flags(),
                    dir_fd=descriptor,
                )
            except OSError as exc:
                raise _UnsafeCandidatePath(
                    f"{label} parent is missing, a symlink, or non-directory: {part}"
                ) from exc
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            if not stat.S_ISDIR(info.st_mode):
                raise _UnsafeCandidatePath(
                    f"{label} parent is not a directory: {part}"
                )
            identities.append((info.st_dev, info.st_ino))
        return descriptor, tuple(identities)
    except Exception:
        os.close(descriptor)
        raise


def _revalidate_candidate_parent(
    candidate_root: Path,
    relative: Path,
    *,
    label: str,
    expected_identities: tuple[tuple[int, int], ...],
) -> None:
    descriptor, identities = _open_candidate_parent(
        candidate_root,
        relative,
        label=label,
    )
    os.close(descriptor)
    if identities != expected_identities:
        raise _UnsafeCandidatePath(f"{label} parent changed during access")


def _open_candidate_file(
    candidate_root: Path,
    relative_value: str | Path,
    *,
    label: str,
) -> tuple[int, int, Path, tuple[tuple[int, int], ...], tuple[int, int]]:
    relative = _candidate_relative_path(relative_value, label=label)
    parent_descriptor, identities = _open_candidate_parent(
        candidate_root,
        relative,
        label=label,
    )
    try:
        try:
            before = os.stat(
                relative.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise _UnsafeCandidatePath(f"{label} is missing or unsafe") from exc
        if not stat.S_ISREG(before.st_mode):
            raise _UnsafeCandidatePath(f"{label} is a symlink or non-regular file")
        try:
            descriptor = os.open(
                relative.name,
                _candidate_file_flags(write=False),
                dir_fd=parent_descriptor,
            )
        except OSError as exc:
            raise _UnsafeCandidatePath(f"{label} is a symlink or unreadable") from exc
        info = os.fstat(descriptor)
        identity = (info.st_dev, info.st_ino)
        if not stat.S_ISREG(info.st_mode) or identity != (
            before.st_dev,
            before.st_ino,
        ):
            os.close(descriptor)
            raise _UnsafeCandidatePath(f"{label} changed during validation")
        return descriptor, parent_descriptor, relative, identities, identity
    except Exception:
        os.close(parent_descriptor)
        raise


def _revalidate_candidate_file(
    candidate_root: Path,
    relative: Path,
    *,
    label: str,
    expected_parent_identities: tuple[tuple[int, int], ...],
    expected_file_identity: tuple[int, int],
) -> None:
    descriptor, parent_descriptor, _relative, identities, identity = (
        _open_candidate_file(candidate_root, relative, label=label)
    )
    os.close(descriptor)
    os.close(parent_descriptor)
    if (
        identities != expected_parent_identities
        or identity != expected_file_identity
    ):
        raise _UnsafeCandidatePath(f"{label} changed during validation")


def _read_candidate_bytes(
    candidate_root: Path,
    relative_value: str | Path,
    *,
    label: str,
) -> bytes:
    descriptor, parent_descriptor, relative, identities, identity = (
        _open_candidate_file(candidate_root, relative_value, label=label)
    )
    try:
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            payload = handle.read()
        _revalidate_candidate_file(
            candidate_root,
            relative,
            label=label,
            expected_parent_identities=identities,
            expected_file_identity=identity,
        )
        return payload
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_descriptor)


def _read_candidate_object(
    candidate_root: Path,
    relative_value: str | Path,
    *,
    label: str,
) -> dict[str, Any]:
    try:
        value = json.loads(
            _read_candidate_bytes(
                candidate_root,
                relative_value,
                label=label,
            ).decode("utf-8")
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return value


def _sha256_candidate_file(
    candidate_root: Path,
    relative_value: str | Path,
    *,
    label: str,
) -> str:
    payload = _read_candidate_bytes(candidate_root, relative_value, label=label)
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _atomic_write_candidate_file(
    candidate_root: Path,
    relative_value: str | Path,
    payload: bytes,
    *,
    label: str,
    expected_current: bytes | None = None,
) -> Path:
    relative = _candidate_relative_path(relative_value, label=label)
    parent_descriptor, identities = _open_candidate_parent(
        candidate_root,
        relative,
        label=label,
    )
    temporary = f".{relative.name}.{uuid4().hex}.tmp"
    descriptor = -1
    temporary_exists = False
    expected_identity: tuple[int, int] | None = None
    try:
        try:
            current = os.stat(
                relative.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            current = None
        if current is not None and not stat.S_ISREG(current.st_mode):
            raise _UnsafeCandidatePath(
                f"{label} final path is a symlink or non-regular file"
            )
        if current is not None and expected_current is None:
            raise _UnsafeCandidatePath(f"{label} is immutable and already exists")
        if current is None and expected_current is not None:
            raise _UnsafeCandidatePath(f"{label} changed before update")
        current_snapshot = (
            (
                current.st_dev,
                current.st_ino,
                current.st_mode,
                current.st_size,
                current.st_mtime_ns,
                current.st_ctime_ns,
            )
            if current is not None
            else None
        )
        if expected_current is not None:
            current_descriptor = -1
            try:
                current_descriptor = os.open(
                    relative.name,
                    _candidate_file_flags(write=False),
                    dir_fd=parent_descriptor,
                )
                opened = os.fstat(current_descriptor)
                opened_snapshot = (
                    opened.st_dev,
                    opened.st_ino,
                    opened.st_mode,
                    opened.st_size,
                    opened.st_mtime_ns,
                    opened.st_ctime_ns,
                )
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or opened_snapshot != current_snapshot
                ):
                    raise _UnsafeCandidatePath(f"{label} changed before update")
                with os.fdopen(current_descriptor, "rb") as handle:
                    current_descriptor = -1
                    if handle.read() != expected_current:
                        raise _UnsafeCandidatePath(
                            f"{label} content changed before update"
                        )
            finally:
                if current_descriptor >= 0:
                    os.close(current_descriptor)
        descriptor = os.open(
            temporary,
            _candidate_file_flags(write=True),
            0o600,
            dir_fd=parent_descriptor,
        )
        temporary_exists = True
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            info = os.fstat(handle.fileno())
            expected_identity = (info.st_dev, info.st_ino)
        _revalidate_candidate_parent(
            candidate_root,
            relative,
            label=label,
            expected_identities=identities,
        )
        try:
            latest = os.stat(
                relative.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            latest = None
        if latest is not None and not stat.S_ISREG(latest.st_mode):
            raise _UnsafeCandidatePath(
                f"{label} final path is a symlink or non-regular file"
            )
        latest_snapshot = (
            (
                latest.st_dev,
                latest.st_ino,
                latest.st_mode,
                latest.st_size,
                latest.st_mtime_ns,
                latest.st_ctime_ns,
            )
            if latest is not None
            else None
        )
        if latest_snapshot != current_snapshot:
            raise _UnsafeCandidatePath(f"{label} changed before activation")
        if expected_current is not None:
            latest_descriptor = -1
            try:
                latest_descriptor = os.open(
                    relative.name,
                    _candidate_file_flags(write=False),
                    dir_fd=parent_descriptor,
                )
                latest_opened = os.fstat(latest_descriptor)
                latest_opened_snapshot = (
                    latest_opened.st_dev,
                    latest_opened.st_ino,
                    latest_opened.st_mode,
                    latest_opened.st_size,
                    latest_opened.st_mtime_ns,
                    latest_opened.st_ctime_ns,
                )
                if latest_opened_snapshot != current_snapshot:
                    raise _UnsafeCandidatePath(
                        f"{label} changed before activation"
                    )
                with os.fdopen(latest_descriptor, "rb") as handle:
                    latest_descriptor = -1
                    if handle.read() != expected_current:
                        raise _UnsafeCandidatePath(
                            f"{label} content changed before activation"
                        )
            finally:
                if latest_descriptor >= 0:
                    os.close(latest_descriptor)
        if current_snapshot is None:
            try:
                os.link(
                    temporary,
                    relative.name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise _UnsafeCandidatePath(
                    f"{label} appeared before activation"
                ) from exc
            os.unlink(temporary, dir_fd=parent_descriptor)
            temporary_exists = False
        else:
            os.replace(
                temporary,
                relative.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            temporary_exists = False
        os.fsync(parent_descriptor)
        final_descriptor, final_parent, _relative, final_identities, final_identity = (
            _open_candidate_file(candidate_root, relative, label=label)
        )
        os.close(final_descriptor)
        os.close(final_parent)
        if final_identities != identities or final_identity != expected_identity:
            raise _UnsafeCandidatePath(f"{label} changed after rename")
        return candidate_root / relative
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_exists:
            try:
                os.unlink(temporary, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)


def _validate_open_candidate_tree(descriptor: int, *, label: str) -> None:
    """Reject links and special files anywhere in one runnable payload tree."""

    try:
        entries = tuple(sorted(os.listdir(descriptor)))
    except OSError as exc:
        raise _UnsafeCandidatePath(f"{label} is unreadable") from exc
    expected_entries: dict[str, tuple[int, int, int]] = {}
    for name in entries:
        try:
            before = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except OSError as exc:
            raise _UnsafeCandidatePath(
                f"{label} changed during traversal: {name}"
            ) from exc
        expected_entries[name] = (before.st_dev, before.st_ino, before.st_mode)
        if stat.S_ISREG(before.st_mode):
            file_descriptor = -1
            try:
                file_descriptor = os.open(
                    name,
                    _candidate_file_flags(write=False),
                    dir_fd=descriptor,
                )
                opened = os.fstat(file_descriptor)
                if not stat.S_ISREG(opened.st_mode) or (
                    opened.st_dev,
                    opened.st_ino,
                ) != (before.st_dev, before.st_ino):
                    raise _UnsafeCandidatePath(
                        f"{label} changed during traversal: {name}"
                    )
            except OSError as exc:
                raise _UnsafeCandidatePath(
                    f"{label} contains a symlink or unreadable file: {name}"
                ) from exc
            finally:
                if file_descriptor >= 0:
                    os.close(file_descriptor)
            continue
        if stat.S_ISDIR(before.st_mode):
            child_descriptor = -1
            try:
                child_descriptor = os.open(
                    name,
                    _candidate_directory_flags(),
                    dir_fd=descriptor,
                )
                opened = os.fstat(child_descriptor)
                if not stat.S_ISDIR(opened.st_mode) or (
                    opened.st_dev,
                    opened.st_ino,
                ) != (before.st_dev, before.st_ino):
                    raise _UnsafeCandidatePath(
                        f"{label} changed during traversal: {name}"
                    )
                _validate_open_candidate_tree(
                    child_descriptor,
                    label=f"{label}/{name}",
                )
                after = os.fstat(child_descriptor)
                if (after.st_dev, after.st_ino) != (
                    opened.st_dev,
                    opened.st_ino,
                ):
                    raise _UnsafeCandidatePath(
                        f"{label} changed during traversal: {name}"
                    )
            except OSError as exc:
                raise _UnsafeCandidatePath(
                    f"{label} contains a symlink or unreadable directory: {name}"
                ) from exc
            finally:
                if child_descriptor >= 0:
                    os.close(child_descriptor)
            continue
        raise _UnsafeCandidatePath(
            f"{label} contains a symlink or non-regular payload: {name}"
        )
    try:
        if tuple(sorted(os.listdir(descriptor))) != entries:
            raise _UnsafeCandidatePath(f"{label} changed during traversal")
        for name, expected in expected_entries.items():
            after = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if (after.st_dev, after.st_ino, after.st_mode) != expected:
                raise _UnsafeCandidatePath(
                    f"{label} changed during traversal: {name}"
                )
    except OSError as exc:
        raise _UnsafeCandidatePath(f"{label} changed during traversal") from exc


def _validate_candidate_payload_tree(candidate_root: Path) -> None:
    relative = Path("packages/__candidate_payload_probe__")
    descriptor, identities = _open_candidate_parent(
        candidate_root,
        relative,
        label="deployment candidate payload",
    )
    try:
        _validate_open_candidate_tree(
            descriptor,
            label="deployment candidate packages",
        )
        _revalidate_candidate_parent(
            candidate_root,
            relative,
            label="deployment candidate payload",
            expected_identities=identities,
        )
    finally:
        os.close(descriptor)


def _begin_candidate_directory_materialization(
    candidate_root: Path,
    relative_value: str | Path,
    *,
    label: str,
) -> tuple[
    Path,
    int,
    tuple[tuple[int, int], ...],
    str,
    tuple[int, int],
]:
    relative = _candidate_relative_path(relative_value, label=label)
    parent_descriptor, identities = _open_candidate_parent(
        candidate_root,
        relative,
        label=label,
    )
    temporary = f".{relative.name}.{uuid4().hex}.tmp"
    try:
        try:
            os.stat(
                relative.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            raise _UnsafeCandidatePath(f"{label} already exists")
        os.mkdir(temporary, 0o700, dir_fd=parent_descriptor)
        staging_descriptor = os.open(
            temporary,
            _candidate_directory_flags(),
            dir_fd=parent_descriptor,
        )
        try:
            staging = os.fstat(staging_descriptor)
            staging_identity = (staging.st_dev, staging.st_ino)
        finally:
            os.close(staging_descriptor)
        return (
            relative,
            parent_descriptor,
            identities,
            temporary,
            staging_identity,
        )
    except Exception:
        os.close(parent_descriptor)
        raise


def _discard_candidate_staging_directory(
    parent_descriptor: int,
    temporary: str,
    *,
    expected_identity: tuple[int, int],
) -> None:
    """Best-effort cleanup that never traverses a replaced staging entry."""

    staging_descriptor = -1
    try:
        staging_descriptor = os.open(
            temporary,
            _candidate_directory_flags(),
            dir_fd=parent_descriptor,
        )
        info = os.fstat(staging_descriptor)
        if (info.st_dev, info.st_ino) != expected_identity:
            return
        for name in os.listdir(staging_descriptor):
            try:
                entry = os.stat(
                    name,
                    dir_fd=staging_descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                continue
            if stat.S_ISDIR(entry.st_mode):
                continue
            try:
                os.unlink(name, dir_fd=staging_descriptor)
            except FileNotFoundError:
                pass
    except OSError:
        return
    finally:
        if staging_descriptor >= 0:
            os.close(staging_descriptor)
    try:
        os.rmdir(temporary, dir_fd=parent_descriptor)
    except OSError:
        pass


def _publish_candidate_staging_directory(
    candidate_root: Path,
    relative: Path,
    parent_descriptor: int,
    parent_identities: tuple[tuple[int, int], ...],
    temporary: str,
    staging_identity: tuple[int, int],
    *,
    label: str,
) -> None:
    staging_descriptor = -1
    final_descriptor = -1
    final_identity: tuple[int, int] | None = None
    published: dict[str, tuple[int, int]] = {}
    try:
        _revalidate_candidate_parent(
            candidate_root,
            relative,
            label=label,
            expected_identities=parent_identities,
        )
        staging_descriptor = os.open(
            temporary,
            _candidate_directory_flags(),
            dir_fd=parent_descriptor,
        )
        temporary_info = os.fstat(staging_descriptor)
        if (temporary_info.st_dev, temporary_info.st_ino) != staging_identity:
            raise _UnsafeCandidatePath(f"{label} staging directory changed")
        names = tuple(
            sorted(
                os.listdir(staging_descriptor),
                key=lambda name: (name == "manifest.json", name),
            )
        )
        staged_identities: dict[str, tuple[int, int]] = {}
        for name in names:
            item = os.stat(
                name,
                dir_fd=staging_descriptor,
                follow_symlinks=False,
            )
            if not stat.S_ISREG(item.st_mode):
                raise _UnsafeCandidatePath(
                    f"{label} staging payload is a symlink or non-regular file: "
                    f"{name}"
                )
            staged_identities[name] = (item.st_dev, item.st_ino)
        try:
            os.mkdir(relative.name, 0o700, dir_fd=parent_descriptor)
        except FileExistsError as exc:
            raise _UnsafeCandidatePath(
                f"{label} appeared before activation"
            ) from exc
        final_descriptor = os.open(
            relative.name,
            _candidate_directory_flags(),
            dir_fd=parent_descriptor,
        )
        final_info = os.fstat(final_descriptor)
        final_identity = (final_info.st_dev, final_info.st_ino)
        _revalidate_candidate_parent(
            candidate_root,
            relative,
            label=label,
            expected_identities=parent_identities,
        )
        for name in names:
            try:
                os.link(
                    name,
                    name,
                    src_dir_fd=staging_descriptor,
                    dst_dir_fd=final_descriptor,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise _UnsafeCandidatePath(
                    f"{label} payload appeared before activation: {name}"
                ) from exc
            final_item = os.stat(
                name,
                dir_fd=final_descriptor,
                follow_symlinks=False,
            )
            identity = (final_item.st_dev, final_item.st_ino)
            if not stat.S_ISREG(final_item.st_mode) or identity != (
                staged_identities[name]
            ):
                raise _UnsafeCandidatePath(
                    f"{label} payload changed during activation: {name}"
                )
            published[name] = identity
            os.unlink(name, dir_fd=staging_descriptor)
        os.fsync(final_descriptor)
        if tuple(
            sorted(
                os.listdir(final_descriptor),
                key=lambda name: (name == "manifest.json", name),
            )
        ) != names:
            raise _UnsafeCandidatePath(f"{label} payload changed during activation")
        os.rmdir(temporary, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
        _revalidate_candidate_parent(
            candidate_root,
            relative,
            label=label,
            expected_identities=parent_identities,
        )
        after = os.stat(
            relative.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if not stat.S_ISDIR(after.st_mode) or (after.st_dev, after.st_ino) != (
            final_identity
        ):
            raise _UnsafeCandidatePath(f"{label} changed after activation")
    except Exception:
        if final_descriptor >= 0 and final_identity is not None:
            try:
                current = os.stat(
                    relative.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if stat.S_ISDIR(current.st_mode) and (
                    current.st_dev,
                    current.st_ino,
                ) == final_identity:
                    for name, expected_identity in published.items():
                        try:
                            item = os.stat(
                                name,
                                dir_fd=final_descriptor,
                                follow_symlinks=False,
                            )
                        except FileNotFoundError:
                            continue
                        if stat.S_ISREG(item.st_mode) and (
                            item.st_dev,
                            item.st_ino,
                        ) == expected_identity:
                            os.unlink(name, dir_fd=final_descriptor)
                    os.rmdir(relative.name, dir_fd=parent_descriptor)
                    os.fsync(parent_descriptor)
            except OSError:
                pass
        raise
    finally:
        if final_descriptor >= 0:
            os.close(final_descriptor)
        if staging_descriptor >= 0:
            os.close(staging_descriptor)


def _release_binding(path_value: str, *, label: str) -> dict[str, str]:
    path = Path(str(path_value or "").strip()).expanduser()
    if not str(path_value or "").strip():
        raise ValueError(f"{label} release attestation is required")
    path = path.resolve()
    value = _read_object(path, label=f"{label} release attestation")
    release_id = str(value.get("releaseId") or "").strip()
    release_digest = str(value.get("payloadSha256") or "").strip()
    if value.get("schema") != "quwoquan_data.release_attestation":
        raise ValueError(f"{label} release attestation schema mismatch")
    if not release_id or _DIGEST.fullmatch(release_digest) is None:
        raise ValueError(f"{label} release identity is invalid")
    return {
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "attestationRef": str(path),
        "attestationDigest": _sha256_file(path),
    }


def local_elasticsearch_image_digest(image_reference: str) -> str:
    """Resolve the one immutable local ES image form accepted by packaging."""

    normalized = str(image_reference or "").strip()
    for pattern in (
        _ELASTICSEARCH_IMAGE_LITERAL_RE,
        _ELASTICSEARCH_IMAGE_DEFAULT_RE,
    ):
        match = pattern.fullmatch(normalized)
        if match is not None:
            return match.group(1)
    raise ValueError(
        "canonical local Elasticsearch image must be an immutable Elastic digest "
        "or the package-owned QWQ_COMPOSE_ELASTICSEARCH_IMAGE expression with an "
        "immutable default"
    )


def _canonical_observability_log_sink_binding(
    provider_composition: object,
    *,
    env_name: str,
    target_name: str,
) -> dict[str, Any]:
    composition = validate_provider_runtime_composition(
        provider_composition,
        expected_environment=env_name,
        expected_target=target_name,
    )
    binding = next(
        (
            item
            for item in composition["bindings"]
            if item["capabilityId"] == "runtime.log.sink"
        ),
        None,
    )
    if not isinstance(binding, dict):
        raise TypeError("canonical Product Ops log-sink Binding is missing")
    if (
        binding.get("state") != "enabled"
        or binding.get("adapterId") != LOG_SINK_ADAPTER_ID
        or binding.get("endpointEnvironmentKeys")
        != {"endpoint": "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT"}
    ):
        raise ValueError("canonical Product Ops log-sink Binding is invalid")
    if env_name == "prod":
        if (
            binding.get("endpointRef")
            != "environment_binding:product_ops.elasticsearch"
            or binding.get("secretEnvironmentKeys")
            != ["PRODUCT_OPS_ELASTICSEARCH_API_KEY"]
        ):
            raise ValueError(
                "Prod Product Ops Binding must select protected managed Elasticsearch"
            )
    elif env_name in {"alpha", "beta", "gamma"}:
        if (
            binding.get("endpointRef")
            != f"local_topology:{env_name}.elasticsearch"
            or binding.get("secretEnvironmentKeys") != []
        ):
            raise ValueError(
                f"{env_name} Product Ops Binding is not target-local Elasticsearch"
            )
    else:
        raise ValueError(f"unsupported Product Ops log-sink environment: {env_name}")
    return binding


def _local_elasticsearch_runtime_selection(
    compose: object,
    *,
    machine: str | None = None,
) -> dict[str, str]:
    if not isinstance(compose, dict):
        raise TypeError("canonical local Elasticsearch workload must be an object")
    policy = compose.get("x-qwq-package-elasticsearch")
    if not isinstance(policy, dict) or set(policy) != {
        "runtimeEndpoint",
        "platforms",
    }:
        raise ValueError("canonical local Elasticsearch package policy is invalid")
    runtime_endpoint = str(policy.get("runtimeEndpoint") or "").strip()
    if runtime_endpoint != "http://elasticsearch:9200":
        raise ValueError("canonical local Elasticsearch runtime endpoint is invalid")
    platforms = policy.get("platforms")
    if not isinstance(platforms, dict) or set(platforms) != {"arm64", "amd64"}:
        raise ValueError("canonical local Elasticsearch platform policy is invalid")
    normalized_machine = (machine or platform.machine()).strip().lower()
    platform_key = (
        "arm64"
        if normalized_machine in {"arm64", "aarch64"}
        else "amd64"
        if normalized_machine in {"amd64", "x86_64"}
        else ""
    )
    if not platform_key:
        raise ValueError(
            f"unsupported local Elasticsearch package architecture: {normalized_machine}"
        )
    selected = platforms.get(platform_key)
    if not isinstance(selected, dict) or set(selected) != {
        "image",
        "cliJavaOpts",
        "esJavaOpts",
    }:
        raise ValueError("canonical local Elasticsearch platform entry is invalid")
    image = str(selected.get("image") or "").strip()
    image_digest = local_elasticsearch_image_digest(image)
    return {
        "platform": platform_key,
        "image": image,
        "imageDigest": image_digest,
        "runtimeEndpoint": runtime_endpoint,
        "cliJavaOpts": str(selected.get("cliJavaOpts") or ""),
        "esJavaOpts": str(selected.get("esJavaOpts") or ""),
    }


def materialize_observability_log_sink_package(
    env_name: str,
    target_name: str,
    provider_composition: object,
) -> dict[str, Any]:
    """Seal the selected ES Binding and exact local workload into a candidate."""

    binding = _canonical_observability_log_sink_binding(
        provider_composition,
        env_name=env_name,
        target_name=target_name,
    )
    shared_root = runtime_shared_deployment_package_dir(
        env_name,
        target=target_name,
    )
    candidate_root = shared_root.parent.parent
    artifact_relative = Path(
        "packages/runtime-shared/observability-log-sink"
    )
    common = {
        "schema": OBSERVABILITY_LOG_SINK_PACKAGE_SCHEMA,
        "adapterId": LOG_SINK_ADAPTER_ID,
        "bindingDigest": _sha256_json(binding),
        "endpointRef": str(binding["endpointRef"]),
        "endpointEnvironmentKey": str(
            binding["endpointEnvironmentKeys"]["endpoint"]
        ),
        "secretEnvironmentKeys": list(binding["secretEnvironmentKeys"]),
    }
    staged_files: dict[str, bytes] = {}
    if env_name == "prod":
        payload = {
            **common,
            "deploymentMode": "managed-external",
            "platform": "",
            "runtimeEndpoint": "",
            "imageDigest": "",
            "sourceComposeDigest": "",
            "composeRef": "",
            "composeDigest": "",
            "clusterRef": "environment-binding:product_ops.elasticsearch",
        }
    else:
        source_path = (
            ROOT
            / "quwoquan_service"
            / "services"
            / "product-ops-service"
            / "deploy"
            / "local-elasticsearch.compose.yaml"
        )
        try:
            compose = yaml.safe_load(source_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ValueError(
                f"canonical local Elasticsearch workload is unreadable: {exc}"
            ) from exc
        selection = _local_elasticsearch_runtime_selection(compose)
        services = compose.get("services") if isinstance(compose, dict) else None
        elasticsearch = (
            services.get("elasticsearch") if isinstance(services, dict) else None
        )
        if not isinstance(elasticsearch, dict):
            raise TypeError(
                "canonical Product Ops Elasticsearch workload is missing"
            )
        compose.pop("x-qwq-package-elasticsearch", None)
        elasticsearch["image"] = selection["image"]
        environment = elasticsearch.get("environment")
        if not isinstance(environment, dict):
            raise TypeError(
                "canonical Product Ops Elasticsearch environment is missing"
            )
        environment["CLI_JAVA_OPTS"] = selection["cliJavaOpts"]
        environment["ES_JAVA_OPTS"] = selection["esJavaOpts"]
        compose_bytes = yaml.safe_dump(
            compose,
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8")
        staged_files["elasticsearch.compose.yaml"] = compose_bytes
        deployment_ref = (
            artifact_relative / "elasticsearch.compose.yaml"
        ).as_posix()
        payload = {
            **common,
            "deploymentMode": "package-bound-local",
            "platform": selection["platform"],
            "runtimeEndpoint": selection["runtimeEndpoint"],
            "imageDigest": selection["imageDigest"],
            "sourceComposeDigest": _sha256_file(source_path),
            "composeRef": deployment_ref,
            "composeDigest": (
                "sha256:" + hashlib.sha256(compose_bytes).hexdigest()
            ),
            "clusterRef": f"target:{target_name}/product-ops/elasticsearch",
        }
    validate_observability_log_sink_package(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
    )
    staged_files["manifest.json"] = (
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    (
        artifact_relative,
        parent_descriptor,
        parent_identities,
        temporary,
        staging_identity,
    ) = _begin_candidate_directory_materialization(
        candidate_root,
        artifact_relative,
        label="observability log-sink package",
    )
    staging_exists = True
    try:
        for name, encoded in staged_files.items():
            _atomic_write_candidate_file(
                candidate_root,
                artifact_relative.parent / temporary / name,
                encoded,
                label=f"observability log-sink package {name}",
            )
        _publish_candidate_staging_directory(
            candidate_root,
            artifact_relative,
            parent_descriptor,
            parent_identities,
            temporary,
            staging_identity,
            label="observability log-sink package",
        )
        staging_exists = False
    finally:
        if staging_exists:
            _discard_candidate_staging_directory(
                parent_descriptor,
                temporary,
                expected_identity=staging_identity,
            )
        os.close(parent_descriptor)
    return validate_observability_log_sink_package(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
        candidate_root=candidate_root,
    )


def load_observability_log_sink_package(
    env_name: str,
    target_name: str,
    candidate_root: Path,
) -> dict[str, Any]:
    payload = _read_candidate_object(
        candidate_root,
        "packages/runtime-shared/observability-log-sink/manifest.json",
        label="observability log-sink package manifest",
    )
    return validate_observability_log_sink_package(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
        candidate_root=candidate_root,
    )


def validate_observability_log_sink_package(
    payload: object,
    *,
    expected_environment: str,
    expected_target: str,
    candidate_root: Path | None = None,
) -> dict[str, Any]:
    required = {
        "schema",
        "adapterId",
        "bindingDigest",
        "endpointRef",
        "endpointEnvironmentKey",
        "secretEnvironmentKeys",
        "deploymentMode",
        "platform",
        "runtimeEndpoint",
        "imageDigest",
        "sourceComposeDigest",
        "composeRef",
        "composeDigest",
        "clusterRef",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("observability log-sink package fields mismatch")
    if (
        payload.get("schema") != OBSERVABILITY_LOG_SINK_PACKAGE_SCHEMA
        or payload.get("adapterId") != LOG_SINK_ADAPTER_ID
        or _DIGEST.fullmatch(str(payload.get("bindingDigest") or "")) is None
        or payload.get("endpointEnvironmentKey")
        != "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT"
    ):
        raise ValueError("observability log-sink package identity is invalid")
    if expected_environment == "prod":
        if (
            expected_target != "prod-hosted"
            or payload.get("deploymentMode") != "managed-external"
            or payload.get("endpointRef")
            != "environment_binding:product_ops.elasticsearch"
            or payload.get("secretEnvironmentKeys")
            != ["PRODUCT_OPS_ELASTICSEARCH_API_KEY"]
            or payload.get("clusterRef")
            != "environment-binding:product_ops.elasticsearch"
            or any(
                payload.get(field) != ""
                for field in (
                    "platform",
                    "runtimeEndpoint",
                    "imageDigest",
                    "sourceComposeDigest",
                    "composeRef",
                    "composeDigest",
                )
            )
        ):
            raise ValueError(
                "Prod observability log sink must bind managed Elasticsearch"
            )
        return payload
    if (
        expected_environment not in {"alpha", "beta", "gamma"}
        or expected_target != f"{expected_environment}-local"
        or payload.get("deploymentMode") != "package-bound-local"
        or payload.get("endpointRef")
        != f"local_topology:{expected_environment}.elasticsearch"
        or payload.get("secretEnvironmentKeys") != []
        or payload.get("platform") not in {"arm64", "amd64"}
        or payload.get("runtimeEndpoint") != "http://elasticsearch:9200"
        or payload.get("clusterRef")
        != f"target:{expected_target}/product-ops/elasticsearch"
    ):
        raise ValueError("local observability log-sink package identity is invalid")
    for field in (
        "imageDigest",
        "sourceComposeDigest",
        "composeDigest",
    ):
        if _DIGEST.fullmatch(str(payload.get(field) or "")) is None:
            raise ValueError(f"observability log-sink {field} is invalid")
    deployment_ref = _validate_candidate_artifact_ref(
        payload.get("composeRef"),
        prefix="packages/runtime-shared/observability-log-sink/",
        label="observability log-sink deployment",
    )
    if candidate_root is not None:
        try:
            deployment_bytes = _read_candidate_bytes(
                candidate_root,
                deployment_ref,
                label="packaged observability log-sink artifact",
            )
        except _UnsafeCandidatePath as exc:
            raise ValueError(
                "packaged observability log-sink artifact is unsafe"
            ) from exc
        if (
            "sha256:" + hashlib.sha256(deployment_bytes).hexdigest()
            != payload["composeDigest"]
        ):
            raise ValueError("packaged observability log-sink artifact drifted")
        try:
            compose = yaml.safe_load(deployment_bytes.decode("utf-8"))
        except (UnicodeError, yaml.YAMLError) as exc:
            raise ValueError(
                "packaged observability log-sink artifact is unreadable"
            ) from exc
        if (
            not isinstance(compose, dict)
            or "x-qwq-package-elasticsearch" in compose
        ):
            raise ValueError(
                "packaged observability log-sink retains a runtime selector"
            )
        services = compose.get("services")
        elasticsearch = (
            services.get("elasticsearch")
            if isinstance(services, dict)
            else None
        )
        if (
            not isinstance(elasticsearch, dict)
            or local_elasticsearch_image_digest(
                str(elasticsearch.get("image") or "")
            )
            != payload["imageDigest"]
        ):
            raise ValueError(
                "packaged observability log-sink image identity drifted"
            )
    return payload


def materialize_provider_runtime_package(
    env_name: str,
    target_name: str,
) -> dict[str, Any]:
    """Atomically seal Provider composition and Compose overlays before fingerprinting."""

    composition = compile_provider_runtime_composition(
        environment=env_name,
        target=target_name,
    )
    validate_provider_runtime_composition(
        composition,
        expected_environment=env_name,
        expected_target=target_name,
    )
    shared_root = runtime_shared_deployment_package_dir(
        env_name,
        target=target_name,
    )
    candidate_root = shared_root.parent.parent
    artifact_relative = Path("packages/runtime-shared/provider-runtime")
    workload_artifacts: list[dict[str, str]] = []
    staged_files: dict[str, bytes] = {}
    for workload in composition["workloads"]:
        role = str(workload.get("role") or "")
        source_ref = str(workload.get("composeRef") or "")
        source_digest = str(workload.get("composeDigest") or "")
        if not source_ref or not source_digest:
            raise ValueError(
                f"package-bound Provider workload has no Compose artifact: {role}"
            )
        source_path = (ROOT / source_ref).resolve()
        if not source_path.is_relative_to(ROOT) or not source_path.is_file():
            raise ValueError(
                f"Provider workload Compose source is outside the repository: {role}"
            )
        if _sha256_file(source_path) != source_digest:
            raise ValueError(f"Provider workload Compose digest drifted: {role}")
        try:
            compose = yaml.safe_load(source_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ValueError(
                f"Provider workload Compose is unreadable: {role}: {exc}"
            ) from exc
        services = compose.get("services") if isinstance(compose, dict) else None
        service = services.get(role) if isinstance(services, dict) else None
        if not isinstance(service, dict) or not service.get("image"):
            raise ValueError(f"Provider workload Compose has no owned image: {role}")
        service.pop("build", None)
        service["image"] = (
            "${"
            + provider_runtime_image_environment_key(role)
            + ":?package-bound Provider image is required}"
        )
        name = f"{role}.compose.yaml"
        compose_bytes = yaml.safe_dump(
            compose,
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8")
        staged_files[name] = compose_bytes
        workload_artifacts.append(
            {
                "role": role,
                "sourceComposeDigest": source_digest,
                "composeRef": (artifact_relative / name).as_posix(),
                "composeDigest": (
                    "sha256:" + hashlib.sha256(compose_bytes).hexdigest()
                ),
            }
        )

    composition_bytes = (
        json.dumps(composition, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    staged_files["composition.json"] = composition_bytes
    payload = {
        "schema": PROVIDER_RUNTIME_PACKAGE_SCHEMA,
        "composition": composition,
        "compositionRef": (artifact_relative / "composition.json").as_posix(),
        "compositionDigest": (
            "sha256:" + hashlib.sha256(composition_bytes).hexdigest()
        ),
        "workloads": workload_artifacts,
        "images": {},
    }
    staged_files["manifest.json"] = (
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    (
        artifact_relative,
        parent_descriptor,
        parent_identities,
        temporary,
        staging_identity,
    ) = _begin_candidate_directory_materialization(
        candidate_root,
        artifact_relative,
        label="Provider runtime package",
    )
    staging_exists = True
    try:
        for name, encoded in staged_files.items():
            _atomic_write_candidate_file(
                candidate_root,
                artifact_relative.parent / temporary / name,
                encoded,
                label=f"Provider runtime package {name}",
            )
        _publish_candidate_staging_directory(
            candidate_root,
            artifact_relative,
            parent_descriptor,
            parent_identities,
            temporary,
            staging_identity,
            label="Provider runtime package",
        )
        staging_exists = False
    finally:
        if staging_exists:
            _discard_candidate_staging_directory(
                parent_descriptor,
                temporary,
                expected_identity=staging_identity,
            )
        os.close(parent_descriptor)
    return validate_packaged_provider_runtime(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
        candidate_root=candidate_root,
        require_images=False,
    )


def provider_runtime_image_environment_key(role: str) -> str:
    normalized = str(role or "").strip()
    if re.fullmatch(r"[a-z][a-z0-9-]{0,62}", normalized) is None:
        raise ValueError("Provider runtime role is invalid")
    return (
        "QWQ_PROVIDER_RUNTIME_"
        + normalized.replace("-", "_").upper()
        + "_IMAGE"
    )


def seal_provider_runtime_package_images(
    env_name: str,
    target_name: str,
    candidate_root: Path,
    images: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """Finalize exact Provider image IDs before package fingerprinting."""

    package_ref = "packages/runtime-shared/provider-runtime/manifest.json"
    payload = _read_candidate_object(
        candidate_root,
        package_ref,
        label="Provider runtime package manifest",
    )
    validate_packaged_provider_runtime(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
        candidate_root=candidate_root,
        require_images=False,
    )
    finalized = {**payload, "images": images}
    validate_packaged_provider_runtime(
        finalized,
        expected_environment=env_name,
        expected_target=target_name,
        candidate_root=candidate_root,
        require_images=True,
        verify_package_manifest=False,
    )
    _atomic_write_candidate_file(
        candidate_root,
        package_ref,
        (json.dumps(finalized, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        ),
        label="Provider runtime package manifest",
        expected_current=(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8"),
    )
    return validate_packaged_provider_runtime(
        finalized,
        expected_environment=env_name,
        expected_target=target_name,
        candidate_root=candidate_root,
        require_images=True,
    )


def load_provider_runtime_package(
    env_name: str,
    target_name: str,
    candidate_root: Path,
) -> dict[str, Any]:
    """Load and validate the already-fingerprinted Provider runtime package."""

    payload = _read_candidate_object(
        candidate_root,
        "packages/runtime-shared/provider-runtime/manifest.json",
        label="Provider runtime package manifest",
    )
    return validate_packaged_provider_runtime(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
        candidate_root=candidate_root,
        require_images=True,
    )


def validate_release_attestations(
    release_attestation: str,
    rollback_release_attestation: str,
) -> dict[str, dict[str, str]]:
    """Fail before package/build work when immutable release inputs are absent."""

    candidate = _release_binding(release_attestation, label="candidate")
    rollback = _release_binding(
        rollback_release_attestation,
        label="rollback",
    )
    if (
        candidate["releaseId"] == rollback["releaseId"]
        or candidate["releaseDigest"] == rollback["releaseDigest"]
    ):
        raise ValueError(
            "candidate and rollback release attestations must have distinct "
            "releaseId and releaseDigest"
        )
    return {
        "candidate": candidate,
        "rollback": rollback,
    }


def write_candidate_manifest(
    env_name: str,
    target_name: str,
    *,
    package_snapshot: dict[str, object],
    candidate_type: str = RUNTIME_CANDIDATE_TYPE,
    release_attestation: str = "",
    rollback_release_attestation: str = "",
) -> Path:
    """Write the only candidate manifest after every package digest is sealed."""

    app_dir = app_deployment_package_dir(env_name, target=target_name)
    candidate_root = app_dir.parent.parent
    fingerprint = _read_candidate_object(
        candidate_root,
        "packages/app/package-fingerprint.json",
        label="package fingerprint",
    )
    app_report = _read_candidate_object(
        candidate_root,
        "packages/app/report.json",
        label="App package report",
    )
    environment_runtime_ref = "packages/app/environment_runtime.yaml"
    environment_runtime = _read_candidate_object(
        candidate_root,
        environment_runtime_ref,
        label="packaged environment runtime",
    )
    runtime_schema_version = str(environment_runtime.get("schema") or "").strip()
    if (
        not runtime_schema_version
        or re.fullmatch(r"[a-z][a-z0-9-]*", runtime_schema_version) is None
        or environment_runtime.get("environment") != env_name
        or environment_runtime.get("target") != target_name
    ):
        raise ValueError("packaged environment runtime identity mismatch")
    package_content = fingerprint.get("packageContent")
    deployment_inputs = fingerprint.get("deploymentInputs")
    if not isinstance(package_content, dict) or not isinstance(deployment_inputs, dict):
        raise TypeError("package fingerprint digest bindings are missing")

    shared_dir = runtime_shared_deployment_package_dir(
        env_name,
        target=target_name,
    )
    if shared_dir != candidate_root / "packages/runtime-shared":
        raise ValueError("runtime-shared package root escaped the candidate")
    try:
        oci = _read_candidate_object(
            candidate_root,
            "packages/runtime-shared/oci-images.json",
            label="package OCI image manifest",
        )
    except _UnsafeCandidatePath as exc:
        raise ValueError("full candidate has no safe package-bound OCI manifest") from exc
    include_services = bool(fingerprint.get("includeServices"))
    if (
        candidate_type != RUNTIME_CANDIDATE_TYPE
        or fingerprint.get("candidateType") != RUNTIME_CANDIDATE_TYPE
        or not include_services
    ):
        raise ValueError("runtime candidate must be a full service package")
    legal_static_root = legal_static_deployment_package_dir(
        env_name,
        target=target_name,
    )
    if legal_static_root != candidate_root / "packages/legal-static":
        raise ValueError("legal-static package root escaped the candidate")
    for relative in (
        "packages/legal-static/current/release_metadata.json",
        "packages/legal-static/current/checksums.json",
        "packages/legal-static/current/public/legal/manifest.json",
    ):
        try:
            _read_candidate_bytes(
                candidate_root,
                relative,
                label="deployment candidate legal-static package",
            )
        except _UnsafeCandidatePath as exc:
            raise ValueError(
                "deployment candidate has no complete safe legal-static package"
            ) from exc
    release = validate_release_attestations(
        release_attestation,
        rollback_release_attestation,
    )

    payload = {
        "schema": CANDIDATE_MANIFEST_SCHEMA,
        "candidateType": candidate_type,
        "environment": env_name,
        "target": target_name,
        "baselineId": package_snapshot["baselineId"],
        "sourceRevision": package_snapshot["sourceRevision"],
        "workspaceDigest": deployment_inputs.get("digest"),
        "workspaceStatusDigest": package_snapshot["workspaceStatusDigest"],
        "packageDigest": package_content.get("digest"),
        "buildInputDigest": oci.get("buildInputDigest") if oci else None,
        "imageDigest": oci.get("imageDigest") if oci else None,
        "configurationDigest": oci.get("configurationDigest") if oci else None,
        "runtimeSchemaVersion": runtime_schema_version,
        "runtimeConfigDigest": app_report.get("runtimeConfigDigest"),
        "environmentRuntimeDigest": _sha256_candidate_file(
            candidate_root,
            environment_runtime_ref,
            label="packaged environment runtime",
        ),
        "observabilityLogSink": load_observability_log_sink_package(
            env_name,
            target_name,
            candidate_root,
        ),
        "providerRuntime": load_provider_runtime_package(
            env_name,
            target_name,
            candidate_root,
        ),
        "release": release,
        "specRefs": list(SPEC_REFS),
    }
    validate_candidate_manifest(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
        require_full=True,
        candidate_root=candidate_root,
    )
    path = _atomic_write_candidate_file(
        candidate_root,
        "manifest.json",
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        ),
        label="deployment candidate manifest",
    )
    return path


def validate_candidate_manifest(
    payload: object,
    *,
    expected_environment: str,
    expected_target: str,
    require_full: bool,
    candidate_root: Path | None = None,
) -> dict[str, Any]:
    if candidate_root is None:
        raise ValueError(
            "runnable deployment candidate validation requires candidate_root"
        )
    try:
        _validate_candidate_payload_tree(candidate_root)
    except _UnsafeCandidatePath as exc:
        raise ValueError("deployment candidate payload tree is unsafe") from exc
    required = {
        "schema",
        "candidateType",
        "environment",
        "target",
        "baselineId",
        "sourceRevision",
        "workspaceDigest",
        "workspaceStatusDigest",
        "packageDigest",
        "buildInputDigest",
        "imageDigest",
        "configurationDigest",
        "runtimeSchemaVersion",
        "runtimeConfigDigest",
        "environmentRuntimeDigest",
        "observabilityLogSink",
        "providerRuntime",
        "release",
        "specRefs",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("deployment candidate manifest fields mismatch")
    if payload.get("schema") != CANDIDATE_MANIFEST_SCHEMA:
        raise ValueError("deployment candidate manifest schema mismatch")
    if payload.get("candidateType") != RUNTIME_CANDIDATE_TYPE:
        raise ValueError("deployment candidate type mismatch")
    if (
        payload.get("environment") != expected_environment
        or payload.get("target") != expected_target
    ):
        raise ValueError("deployment candidate manifest target identity mismatch")
    if re.fullmatch(r"[0-9a-f]{40}", str(payload.get("sourceRevision") or "")) is None:
        raise ValueError("deployment candidate sourceRevision is invalid")
    if (
        re.fullmatch(
            r"[a-z][a-z0-9-]*",
            str(payload.get("runtimeSchemaVersion") or ""),
        )
        is None
    ):
        raise ValueError("deployment candidate runtimeSchemaVersion is invalid")
    for field in (
        "baselineId",
        "workspaceDigest",
        "workspaceStatusDigest",
        "packageDigest",
        "configurationDigest",
        "runtimeConfigDigest",
        "environmentRuntimeDigest",
    ):
        if _DIGEST.fullmatch(str(payload.get(field) or "")) is None:
            raise ValueError(f"deployment candidate {field} is invalid")
    if payload.get("specRefs") != list(SPEC_REFS):
        raise ValueError("deployment candidate specRefs mismatch")
    if not require_full:
        raise ValueError("runtime deployment candidate cannot be loaded as App-only")
    for field in ("buildInputDigest", "imageDigest"):
        if _DIGEST.fullmatch(str(payload.get(field) or "")) is None:
            raise ValueError(f"full deployment candidate {field} is invalid")
    validate_observability_log_sink_package(
        payload.get("observabilityLogSink"),
        expected_environment=expected_environment,
        expected_target=expected_target,
        candidate_root=candidate_root,
    )
    validate_packaged_provider_runtime(
        payload.get("providerRuntime"),
        expected_environment=expected_environment,
        expected_target=expected_target,
        candidate_root=candidate_root,
    )
    _validate_candidate_app_runtime_binding(
        payload,
        candidate_root=candidate_root,
    )
    _validate_candidate_provider_oci_binding(
        payload,
        candidate_root=candidate_root,
    )
    release = payload.get("release")
    if not isinstance(release, dict) or set(release) != {"candidate", "rollback"}:
        raise ValueError("full deployment candidate release binding mismatch")
    for label in ("candidate", "rollback"):
        binding = release.get(label)
        if not isinstance(binding, dict) or set(binding) != {
            "releaseId",
            "releaseDigest",
            "attestationRef",
            "attestationDigest",
        }:
            raise ValueError(f"deployment candidate {label} release fields mismatch")
        if not str(binding.get("releaseId") or ""):
            raise ValueError(f"deployment candidate {label} releaseId is invalid")
        for field in ("releaseDigest", "attestationDigest"):
            if _DIGEST.fullmatch(str(binding.get(field) or "")) is None:
                raise ValueError(f"deployment candidate {label} {field} is invalid")
    return payload


def _validate_candidate_app_runtime_binding(
    candidate: Mapping[str, Any],
    *,
    candidate_root: Path,
) -> None:
    """Cross-bind the App runtime config without conflating service config."""

    try:
        app_report = _read_candidate_object(
            candidate_root,
            "packages/app/report.json",
            label="App package report",
        )
    except _UnsafeCandidatePath as exc:
        raise ValueError("deployment candidate App package report is unsafe") from exc
    if (
        _DIGEST.fullmatch(str(app_report.get("runtimeConfigDigest") or "")) is None
        or app_report.get("runtimeConfigDigest")
        != candidate.get("runtimeConfigDigest")
    ):
        raise ValueError("deployment candidate App runtime identity drifted")


def validate_packaged_provider_runtime(
    payload: object,
    *,
    expected_environment: str,
    expected_target: str,
    candidate_root: Path | None,
    require_images: bool = True,
    verify_package_manifest: bool = True,
) -> dict[str, Any]:
    if candidate_root is None:
        raise ValueError(
            "packaged Provider runtime validation requires candidate_root"
        )
    if not isinstance(payload, dict) or set(payload) != {
        "schema",
        "composition",
        "compositionRef",
        "compositionDigest",
        "workloads",
        "images",
    }:
        raise ValueError("deployment candidate Provider runtime fields mismatch")
    if payload.get("schema") != PROVIDER_RUNTIME_PACKAGE_SCHEMA:
        raise ValueError("deployment candidate Provider runtime schema mismatch")
    composition = validate_provider_runtime_composition(
        payload.get("composition"),
        expected_environment=expected_environment,
        expected_target=expected_target,
    )
    composition_ref = _validate_candidate_artifact_ref(
        payload.get("compositionRef"),
        prefix="packages/runtime-shared/provider-runtime/",
        label="Provider runtime composition",
    )
    composition_digest = str(payload.get("compositionDigest") or "")
    if _DIGEST.fullmatch(composition_digest) is None:
        raise ValueError("deployment candidate Provider compositionDigest is invalid")

    workloads = payload.get("workloads")
    if not isinstance(workloads, list):
        raise TypeError("deployment candidate Provider workloads must be a list")
    expected_workloads = {
        str(workload["role"]): str(workload["composeDigest"])
        for workload in composition["workloads"]
    }
    seen_roles: set[str] = set()
    normalized_artifacts: list[tuple[str, str, str]] = []
    for artifact in workloads:
        if not isinstance(artifact, dict) or set(artifact) != {
            "role",
            "sourceComposeDigest",
            "composeRef",
            "composeDigest",
        }:
            raise ValueError(
                "deployment candidate Provider workload artifact fields mismatch"
            )
        role = str(artifact.get("role") or "")
        if not role or role in seen_roles or role not in expected_workloads:
            raise ValueError(
                "deployment candidate Provider workload artifact role mismatch"
            )
        seen_roles.add(role)
        compose_ref = _validate_candidate_artifact_ref(
            artifact.get("composeRef"),
            prefix="packages/runtime-shared/provider-runtime/",
            label=f"Provider workload {role}",
        )
        compose_digest = str(artifact.get("composeDigest") or "")
        source_compose_digest = str(artifact.get("sourceComposeDigest") or "")
        if (
            _DIGEST.fullmatch(compose_digest) is None
            or source_compose_digest != expected_workloads[role]
        ):
            raise ValueError(
                f"deployment candidate Provider workload digest mismatch: {role}"
            )
        normalized_artifacts.append((role, compose_ref, compose_digest))
    if seen_roles != set(expected_workloads):
        raise ValueError("deployment candidate Provider workload closure mismatch")

    images = payload.get("images")
    if not isinstance(images, dict):
        raise TypeError("deployment candidate Provider images must be an object")
    if require_images and set(images) != set(expected_workloads):
        raise ValueError("deployment candidate Provider image closure mismatch")
    if not require_images and images:
        raise ValueError("unsealed Provider runtime package cannot contain images")
    for role, descriptor in images.items():
        if not isinstance(descriptor, dict) or set(descriptor) != {
            "buildInputDigest",
            "ref",
            "imageDigest",
        }:
            raise ValueError("deployment candidate Provider image fields mismatch")
        build_input_digest = str(descriptor.get("buildInputDigest") or "")
        expected_ref = (
            f"quwoquan/provider-runtime-{role}:"
            f"{build_input_digest.removeprefix('sha256:')}"
        )
        if (
            role not in expected_workloads
            or _DIGEST.fullmatch(build_input_digest) is None
            or descriptor.get("ref") != expected_ref
            or _DIGEST.fullmatch(str(descriptor.get("imageDigest") or "")) is None
        ):
            raise ValueError("deployment candidate Provider image identity is invalid")

    if verify_package_manifest:
        try:
            packaged_manifest = _read_candidate_object(
                candidate_root,
                "packages/runtime-shared/provider-runtime/manifest.json",
                label="Provider runtime package manifest",
            )
        except _UnsafeCandidatePath as exc:
            raise ValueError(
                "deployment candidate Provider package manifest is unsafe"
            ) from exc
        if packaged_manifest != payload:
            raise ValueError(
                "deployment candidate Provider package manifest drifted"
            )
    try:
        composition_bytes = _read_candidate_bytes(
            candidate_root,
            composition_ref,
            label="packaged Provider runtime composition",
        )
    except _UnsafeCandidatePath as exc:
        raise ValueError(
            "packaged Provider runtime composition artifact is unsafe"
        ) from exc
    if (
        "sha256:" + hashlib.sha256(composition_bytes).hexdigest()
        != composition_digest
    ):
        raise ValueError("packaged Provider runtime composition artifact drifted")
    try:
        packaged_composition = json.loads(composition_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "packaged Provider runtime composition is unreadable"
        ) from exc
    if packaged_composition != composition:
        raise ValueError("packaged Provider runtime composition bytes mismatch")
    for role, compose_ref, compose_digest in normalized_artifacts:
        try:
            compose_bytes = _read_candidate_bytes(
                candidate_root,
                compose_ref,
                label=f"packaged Provider workload artifact: {role}",
            )
        except _UnsafeCandidatePath as exc:
            raise ValueError(
                f"packaged Provider workload artifact is unsafe: {role}"
            ) from exc
        if (
            "sha256:" + hashlib.sha256(compose_bytes).hexdigest()
            != compose_digest
        ):
            raise ValueError(f"packaged Provider workload artifact drifted: {role}")
        try:
            compose = yaml.safe_load(compose_bytes.decode("utf-8"))
        except (UnicodeError, yaml.YAMLError) as exc:
            raise ValueError(
                f"packaged Provider workload is unreadable: {role}: {exc}"
            ) from exc
        services = compose.get("services") if isinstance(compose, dict) else None
        service = services.get(role) if isinstance(services, dict) else None
        expected_image = (
            "${"
            + provider_runtime_image_environment_key(role)
            + ":?package-bound Provider image is required}"
        )
        if (
            not isinstance(service, dict)
            or service.get("image") != expected_image
            or "build" in service
        ):
            raise ValueError(
                f"packaged Provider workload image selector drifted: {role}"
            )
    return payload


def _validate_candidate_provider_oci_binding(
    candidate: Mapping[str, Any],
    *,
    candidate_root: Path,
) -> None:
    """Cross-bind Provider images to the one package-owned OCI manifest."""

    try:
        oci = _read_candidate_object(
            candidate_root,
            "packages/runtime-shared/oci-images.json",
            label="package OCI image manifest",
        )
    except _UnsafeCandidatePath as exc:
        raise ValueError("deployment candidate OCI image manifest is unsafe") from exc
    if set(oci) != {
        "schema",
        "environment",
        "target",
        "configurationDigest",
        "buildInputDigest",
        "imageDigest",
        "images",
    } or oci.get("schema") != "stackctl-package-oci-images":
        raise ValueError("package OCI image manifest fields mismatch")
    if (
        oci.get("environment") != candidate.get("environment")
        or oci.get("target") != candidate.get("target")
        or oci.get("buildInputDigest") != candidate.get("buildInputDigest")
        or oci.get("imageDigest") != candidate.get("imageDigest")
        or oci.get("configurationDigest") != candidate.get("configurationDigest")
    ):
        raise ValueError("deployment candidate OCI identity drifted")
    images = oci.get("images")
    provider_runtime = candidate.get("providerRuntime")
    provider_images = (
        provider_runtime.get("images")
        if isinstance(provider_runtime, Mapping)
        else None
    )
    if not isinstance(images, dict) or not isinstance(provider_images, dict):
        raise TypeError("deployment candidate OCI image closure is invalid")
    provider_roles = set(provider_images)
    first_party_roles = set(first_party_service_names())
    if set(images) != first_party_roles | provider_roles:
        raise ValueError("deployment candidate OCI image role closure mismatch")
    if {role: images.get(role) for role in provider_roles} != provider_images:
        raise ValueError("deployment candidate Provider images differ from canonical OCI")
    if _sha256_json(images) != oci.get("imageDigest"):
        raise ValueError("deployment candidate OCI imageDigest mismatch")

    if provider_roles:
        first_party_refs: dict[str, str] = {}
        for role in sorted(first_party_roles):
            descriptor = images.get(role)
            if not isinstance(descriptor, Mapping) or set(descriptor) != {
                "ref",
                "imageDigest",
            }:
                raise ValueError(
                    f"deployment candidate first-party image is invalid: {role}"
                )
            first_party_refs[role] = str(descriptor["ref"])
        provider_refs = {
            role: {
                "buildInputDigest": descriptor["buildInputDigest"],
                "ref": descriptor["ref"],
            }
            for role, descriptor in sorted(provider_images.items())
        }
        expected_build_input = _sha256_json(
            {
                "firstPartyImageVersion": immutable_image_digest(first_party_refs),
                "providerRuntimeDigest": provider_runtime["composition"][
                    "runtimeCompositionDigest"
                ],
                "providerImageRefs": provider_refs,
            }
        )
        if oci.get("buildInputDigest") != expected_build_input:
            raise ValueError(
                "deployment candidate Provider buildInputDigest closure mismatch"
            )


def _validate_candidate_artifact_ref(
    value: object,
    *,
    prefix: str,
    label: str,
) -> str:
    reference = str(value or "").strip()
    path = Path(reference)
    if (
        not reference.startswith(prefix)
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != reference
    ):
        raise ValueError(f"{label} artifactRef is invalid")
    return reference


def load_candidate_manifest(
    env_name: str,
    target_name: str,
    baseline_id: str,
    *,
    require_full: bool,
) -> dict[str, Any]:
    candidate_root = deployment_candidate_dir(target_name, baseline_id)
    payload = _read_candidate_object(
        candidate_root,
        "manifest.json",
        label="deployment candidate manifest",
    )
    return validate_candidate_manifest(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
        require_full=require_full,
        candidate_root=candidate_root,
    )
