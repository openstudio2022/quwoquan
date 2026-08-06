"""Compile Provider bindings with topology and capability-scoped secret bundles."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from .output_paths import deployment_work_root
from .provider_endpoint_contract import load_provider_endpoint_environment
from .provider_runtime_composition import (
    validate_provider_runtime_composition,
    validate_provider_runtime_scope,
)

SCHEMA = "stackctl-provider-config"
CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def project_provider_secret_bundles(
    *,
    environment: str,
    target: str,
    source: Mapping[str, str],
    runtime_composition: Mapping[str, Any],
) -> dict[str, str]:
    """Project generated local secrets into capability-owned external bundles."""

    _validate_scope(environment, target)
    bindings = _runtime_bindings(
        environment=environment,
        target=target,
        runtime_composition=runtime_composition,
    )
    deployment_root = deployment_work_root(target)
    projected: dict[str, str] = {}
    for capability_id, binding in bindings.items():
        for field in ("endpoint_envs", "secret_refs"):
            for key in _binding_keys(binding, field):
                value = str(source.get(key) or "")
                if not value:
                    continue
                path = _bundle_key_path(
                    target,
                    capability_id,
                    key,
                    deployment_root=deployment_root,
                )
                _atomic_write(
                    path,
                    value.encode("utf-8"),
                    mode=0o600,
                    deployment_root=deployment_root,
                )
                projected[f"{capability_id}:{key}"] = _value_digest(value)
    return projected


def compile_provider_config(
    *,
    action: str,
    environment: str,
    target: str,
    runtime_composition: Mapping[str, Any],
) -> dict[str, Any]:
    if action not in {"validate", "render", "diff"}:
        raise ValueError(f"unsupported provider-config action: {action}")
    _validate_scope(environment, target)
    resolved_composition = validate_provider_runtime_composition(
        runtime_composition,
        expected_environment=environment,
        expected_target=target,
    )
    bindings = packaged_runtime_bindings(resolved_composition)
    endpoint_environment = (
        load_provider_endpoint_environment()
        if environment in {"alpha", "beta", "gamma"}
        else {}
    )
    resolved: dict[str, str] = {}
    missing: list[str] = []
    invalid: list[str] = []
    capability_digests: dict[str, str] = {}
    for capability_id, binding in bindings.items():
        if str(binding.get("state") or "") != "enabled":
            continue
        adapter = str(binding.get("adapter_id") or "")
        if adapter == "ext.first_party.http_authority":
            continue
        material: dict[str, str] = {}
        for key in _binding_keys(binding, "endpoint_envs"):
            value = endpoint_environment.get(key)
            if value is None:
                value, issue = _read_bundle_key(target, capability_id, key)
                if issue:
                    (missing if issue == "missing" else invalid).append(
                        f"{capability_id}:{key}"
                    )
                    continue
            material[key] = value
            resolved[key] = value
        for key in _binding_keys(binding, "secret_refs"):
            value, issue = _read_bundle_key(target, capability_id, key)
            if issue:
                (missing if issue == "missing" else invalid).append(
                    f"{capability_id}:{key}"
                )
                continue
            material[key] = value
            resolved[key] = value
        capability_digests[capability_id] = _mapping_digest(material)

    material_digest = _mapping_digest(capability_digests)
    aggregate_digest = _mapping_digest(
        {
            "bindingDigest": resolved_composition["bindingDigest"],
            "materialDigest": material_digest,
            "runtimeCompositionDigest": resolved_composition[
                "runtimeCompositionDigest"
            ],
        }
    )
    current = {
        "schema": SCHEMA,
        "environment": environment,
        "target": target,
        "configurationDigest": aggregate_digest,
        "bindingDigest": resolved_composition["bindingDigest"],
        "runtimeCompositionDigest": resolved_composition[
            "runtimeCompositionDigest"
        ],
        "materialDigest": material_digest,
        "capabilityDigests": capability_digests,
        "runtimeWorkloads": resolved_composition["workloads"],
        "missingKeys": sorted(missing),
        "invalidKeys": sorted(invalid),
    }
    if action == "diff":
        previous = _load_active_receipt(target)
        previous_digest = str(previous.get("configurationDigest") or "")
        return {
            "exitCode": 0
            if previous_digest == aggregate_digest and not missing and not invalid
            else 2,
            "summary": (
                "stackctl provider-config diff is clean"
                if previous_digest == aggregate_digest and not missing and not invalid
                else "stackctl provider-config diff detected material drift"
            ),
            "details": [
                f"configurationDigest={aggregate_digest}",
                f"previousDigest={previous_digest or 'missing'}",
                *[f"missing={key}" for key in sorted(missing)],
                *[f"invalid={key}" for key in sorted(invalid)],
            ],
            **current,
            "changed": previous_digest != aggregate_digest,
        }
    if missing or invalid:
        return {
            "exitCode": 2,
            "summary": f"stackctl provider-config {action} is GATE_BLOCK",
            "details": [
                f"configurationDigest={aggregate_digest}",
                *[f"missing={key}" for key in sorted(missing)],
                *[f"invalid={key}" for key in sorted(invalid)],
            ],
            **current,
        }
    if action == "render":
        _render_material(target, resolved, current)
    return {
        "exitCode": 0,
        "summary": f"stackctl provider-config {action} passed",
        "details": [f"configurationDigest={aggregate_digest}"],
        **current,
    }


def packaged_runtime_bindings(
    composition: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    """Project validated package records into the compiler's binding shape."""

    bindings = composition.get("bindings")
    if not isinstance(bindings, list):
        raise TypeError("packaged Provider bindings are invalid")
    return {
        str(binding["capabilityId"]): {
            "state": binding["state"],
            "adapter_id": binding["adapterId"],
            "endpoint_ref": binding["endpointRef"],
            "endpoint_envs": dict(binding["endpointEnvironmentKeys"]),
            "secret_refs": list(binding["secretEnvironmentKeys"]),
        }
        for binding in bindings
        if isinstance(binding, Mapping)
    }


def _runtime_bindings(
    *,
    environment: str,
    target: str,
    runtime_composition: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    validated = validate_provider_runtime_composition(
        runtime_composition,
        expected_environment=environment,
        expected_target=target,
    )
    return packaged_runtime_bindings(validated)


def _binding_keys(binding: Mapping[str, Any], field: str) -> list[str]:
    value = binding.get(field) or {}
    keys = value.values() if isinstance(value, Mapping) else value
    return sorted(str(key) for key in keys if KEY_RE.fullmatch(str(key)))


def _validate_scope(environment: str, target: str) -> None:
    validate_provider_runtime_scope(environment, target)


def _bundle_key_path(
    target: str,
    capability_id: str,
    key: str,
    *,
    deployment_root: Path | None = None,
) -> Path:
    if not CAPABILITY_RE.fullmatch(capability_id):
        raise ValueError(f"invalid capability identifier: {capability_id}")
    if not KEY_RE.fullmatch(key):
        raise ValueError(f"invalid Provider material key: {key}")
    root = deployment_root or deployment_work_root(target)
    return root / "secrets" / capability_id / key


def _read_bundle_key(
    target: str,
    capability_id: str,
    key: str,
) -> tuple[str, str]:
    deployment_root = deployment_work_root(target)
    path = _bundle_key_path(
        target,
        capability_id,
        key,
        deployment_root=deployment_root,
    )
    payload, info, issue = _secure_read_regular_file(
        path,
        deployment_root=deployment_root,
    )
    if issue:
        return "", issue
    if payload is None or info is None:
        return "", "invalid"
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        return "", "invalid"
    try:
        value = payload.decode("utf-8")
    except UnicodeDecodeError:
        return "", "invalid"
    if not value:
        return "", "invalid"
    return value, ""


def _render_material(
    target: str,
    values: Mapping[str, str],
    receipt: Mapping[str, Any],
) -> None:
    deployment_root = deployment_work_root(target)
    root = deployment_root / "provider-config"
    _atomic_write(
        root / "material.json",
        json.dumps(values, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        mode=0o600,
        deployment_root=deployment_root,
    )
    _atomic_write(
        root / "active.json",
        json.dumps(receipt, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        mode=0o600,
        deployment_root=deployment_root,
    )


def _load_active_receipt(target: str) -> dict[str, Any]:
    deployment_root = deployment_work_root(target)
    path = deployment_root / "provider-config" / "active.json"
    payload, _info, issue = _secure_read_regular_file(
        path,
        deployment_root=deployment_root,
    )
    if issue or payload is None:
        return {}
    try:
        loaded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


class _UnsafeProviderPath(ValueError):
    pass


def _directory_open_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise RuntimeError("Provider secret projection requires O_NOFOLLOW/O_DIRECTORY")
    return os.O_RDONLY | nofollow | directory | getattr(os, "O_CLOEXEC", 0)


def _file_open_flags(*, write: bool) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise RuntimeError("Provider secret projection requires O_NOFOLLOW")
    access = os.O_WRONLY | os.O_CREAT | os.O_EXCL if write else os.O_RDONLY
    return access | nofollow | getattr(os, "O_CLOEXEC", 0)


def _validated_relative_path(path: Path, *, deployment_root: Path) -> Path:
    if not path.is_absolute() or not deployment_root.is_absolute():
        raise _UnsafeProviderPath("Provider deployment paths must be absolute")
    try:
        relative = path.relative_to(deployment_root)
    except ValueError as exc:
        raise _UnsafeProviderPath(
            f"Provider deployment path escapes target root: {path}"
        ) from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise _UnsafeProviderPath(f"unsafe Provider deployment path: {path}")
    return relative


def _open_directory_component(
    parent_descriptor: int,
    name: str,
    *,
    create: bool,
) -> int:
    try:
        return os.open(name, _directory_open_flags(), dir_fd=parent_descriptor)
    except FileNotFoundError:
        if not create:
            raise
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_descriptor)
        except FileExistsError:
            pass
        try:
            return os.open(name, _directory_open_flags(), dir_fd=parent_descriptor)
        except OSError as exc:
            raise _UnsafeProviderPath(
                f"Provider deployment directory is unsafe: {name}"
            ) from exc
    except OSError as exc:
        raise _UnsafeProviderPath(
            f"Provider deployment directory is a symlink or non-directory: {name}"
        ) from exc


def _open_secure_parent(
    path: Path,
    *,
    deployment_root: Path,
    create: bool,
) -> tuple[int, tuple[tuple[int, int], ...]]:
    relative = _validated_relative_path(path, deployment_root=deployment_root)
    root_parts = deployment_root.parts[1:]
    parent_parts = relative.parts[:-1]
    descriptor = os.open(deployment_root.anchor, _directory_open_flags())
    identities: list[tuple[int, int]] = []
    try:
        for index, part in enumerate((*root_parts, *parent_parts)):
            child = _open_directory_component(descriptor, part, create=create)
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            if not stat.S_ISDIR(info.st_mode):
                raise _UnsafeProviderPath(
                    f"Provider deployment component is not a directory: {part}"
                )
            if index >= len(root_parts):
                if create:
                    os.fchmod(descriptor, 0o700)
                identities.append((info.st_dev, info.st_ino))
            elif index == len(root_parts) - 1:
                identities.append((info.st_dev, info.st_ino))
        return descriptor, tuple(identities)
    except Exception:
        os.close(descriptor)
        raise


def _revalidate_secure_parent(
    path: Path,
    *,
    deployment_root: Path,
    expected_identities: tuple[tuple[int, int], ...],
) -> None:
    descriptor, identities = _open_secure_parent(
        path,
        deployment_root=deployment_root,
        create=False,
    )
    os.close(descriptor)
    if identities != expected_identities:
        raise _UnsafeProviderPath(
            f"Provider deployment parent changed during operation: {path.parent}"
        )


def _final_entry_info(parent_descriptor: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise _UnsafeProviderPath(f"Provider final path is unsafe: {name}") from exc


def _require_regular_or_missing(parent_descriptor: int, name: str) -> None:
    info = _final_entry_info(parent_descriptor, name)
    if info is not None and not stat.S_ISREG(info.st_mode):
        raise _UnsafeProviderPath(
            f"Provider final path is a symlink or non-regular file: {name}"
        )


def _secure_read_regular_file(
    path: Path,
    *,
    deployment_root: Path,
) -> tuple[bytes | None, os.stat_result | None, str]:
    try:
        parent_descriptor, identities = _open_secure_parent(
            path,
            deployment_root=deployment_root,
            create=False,
        )
    except FileNotFoundError:
        return None, None, "missing"
    except (_UnsafeProviderPath, RuntimeError):
        return None, None, "invalid"
    descriptor = -1
    try:
        before = _final_entry_info(parent_descriptor, path.name)
        if before is None:
            return None, None, "missing"
        if not stat.S_ISREG(before.st_mode):
            return None, None, "invalid"
        try:
            descriptor = os.open(
                path.name,
                _file_open_flags(write=False),
                dir_fd=parent_descriptor,
            )
        except OSError:
            return None, None, "invalid"
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino)
        ):
            return None, None, "invalid"
        try:
            _revalidate_secure_parent(
                path,
                deployment_root=deployment_root,
                expected_identities=identities,
            )
        except (FileNotFoundError, _UnsafeProviderPath):
            return None, None, "invalid"
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            return handle.read(), info, ""
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_descriptor)


def _atomic_write(
    path: Path,
    payload: bytes,
    *,
    mode: int,
    deployment_root: Path,
) -> None:
    parent_descriptor, identities = _open_secure_parent(
        path,
        deployment_root=deployment_root,
        create=True,
    )
    temporary = f".{path.name}.{uuid4().hex}.tmp"
    descriptor = -1
    temporary_exists = False
    expected_identity: tuple[int, int] | None = None
    try:
        _require_regular_or_missing(parent_descriptor, path.name)
        descriptor = os.open(
            temporary,
            _file_open_flags(write=True),
            mode,
            dir_fd=parent_descriptor,
        )
        temporary_exists = True
        os.fchmod(descriptor, mode)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("Provider temporary write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        info = os.fstat(descriptor)
        expected_identity = (info.st_dev, info.st_ino)
        os.close(descriptor)
        descriptor = -1

        _revalidate_secure_parent(
            path,
            deployment_root=deployment_root,
            expected_identities=identities,
        )
        _require_regular_or_missing(parent_descriptor, path.name)
        os.replace(
            temporary,
            path.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_exists = False
        _revalidate_secure_parent(
            path,
            deployment_root=deployment_root,
            expected_identities=identities,
        )
        final_descriptor = os.open(
            path.name,
            _file_open_flags(write=False),
            dir_fd=parent_descriptor,
        )
        try:
            final_info = os.fstat(final_descriptor)
            if (
                not stat.S_ISREG(final_info.st_mode)
                or expected_identity != (final_info.st_dev, final_info.st_ino)
            ):
                raise _UnsafeProviderPath(
                    f"Provider final file changed during atomic write: {path.name}"
                )
        finally:
            os.close(final_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_exists:
            try:
                os.unlink(temporary, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)


def _mapping_digest(values: Mapping[str, str]) -> str:
    encoded = json.dumps(
        dict(sorted(values.items())),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _value_digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
