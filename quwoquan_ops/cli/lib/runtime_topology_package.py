#!/usr/bin/env python3
"""Materialize and validate the immutable local runtime Compose topology."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
from typing import Any, Mapping

import yaml

from quwoquan_ops.cli.lib.immutable_image_composition import first_party_service_names


ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "qwq.runtime_topology_package.v1"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
TOPOLOGY_RELATIVE_ROOT = PurePosixPath(
    "packages/runtime-shared/runtime-topology"
)
CONTENT_RELEASE_SERVICES = frozenset(
    {
        "api-edge",
        "recommendation-service",
        "content-service",
        "user-service",
        "entity-service",
    }
)
CONTENT_COMMERCIAL_SERVICES = frozenset(
    {*CONTENT_RELEASE_SERVICES, "product-ops-service"}
)


class RuntimeTopologyPackageError(ValueError):
    """The runtime topology package is missing, unsafe, or internally drifted."""


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _safe_source_bytes(path: Path, *, label: str) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise RuntimeTopologyPackageError(f"{label} is unavailable: {path}") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeTopologyPackageError(f"{label} must be a regular file: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RuntimeTopologyPackageError(f"{label} is unreadable: {path}") from exc


def _sealed_compose_bytes(source: Path) -> tuple[bytes, str]:
    source_bytes = _safe_source_bytes(source, label="runtime Compose source")
    try:
        compose = yaml.safe_load(source_bytes.decode("utf-8"))
    except (UnicodeError, yaml.YAMLError) as exc:
        raise RuntimeTopologyPackageError(
            f"runtime Compose source is invalid: {source}"
        ) from exc
    if not isinstance(compose, dict):
        raise RuntimeTopologyPackageError(
            f"runtime Compose source must be an object: {source}"
        )
    services = compose.get("services")
    if not isinstance(services, dict) or not services:
        raise RuntimeTopologyPackageError(
            f"runtime Compose source has no services: {source}"
        )
    for service_name, service in services.items():
        if not isinstance(service_name, str) or not isinstance(service, dict):
            raise RuntimeTopologyPackageError(
                f"runtime Compose service is invalid: {source}"
            )
        # A runtime candidate is image-only.  Keeping a live build context here
        # would let `up` read the mutable repository after candidate creation.
        service.pop("build", None)
    encoded = yaml.safe_dump(
        compose,
        allow_unicode=True,
        sort_keys=False,
    ).encode("utf-8")
    return encoded, _sha256_bytes(source_bytes)


def _validate_relative(relative: PurePosixPath, *, label: str) -> None:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise RuntimeTopologyPackageError(f"{label} path is unsafe")


def _ensure_safe_directory(root: Path, relative: PurePosixPath) -> Path:
    _validate_relative(relative, label="runtime topology directory")
    current = root
    for part in relative.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            metadata = current.lstat()
            if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
                raise RuntimeTopologyPackageError(
                    f"runtime topology directory is unsafe: {current}"
                )
        else:
            current.mkdir(mode=0o700)
    return current


def _write_exclusive(root: Path, relative: PurePosixPath, payload: bytes) -> None:
    _validate_relative(relative, label="runtime topology artifact")
    parent_relative = PurePosixPath(*relative.parts[:-1])
    parent = (
        _ensure_safe_directory(root, parent_relative)
        if parent_relative.parts
        else root
    )
    destination = parent / relative.name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(destination, flags, 0o600)
    except OSError as exc:
        raise RuntimeTopologyPackageError(
            f"runtime topology artifact cannot be created safely: {destination}"
        ) from exc
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short runtime topology write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    parent_descriptor = os.open(
        parent,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(parent_descriptor)
    finally:
        os.close(parent_descriptor)


def _entry(
    *,
    role: str,
    layer: str,
    service: str,
    reference: PurePosixPath,
    payload: bytes,
    source_digest: str,
) -> dict[str, str]:
    return {
        "role": role,
        "layer": layer,
        "service": service,
        "ref": reference.as_posix(),
        "digest": _sha256_bytes(payload),
        "sourceDigest": source_digest,
    }


def materialize_runtime_topology_package(
    environment: str,
    target: str,
    runtime_shared_root: Path,
    *,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Seal every Compose/policy byte needed by local runtime up/down."""

    if environment not in {"alpha", "beta", "gamma"}:
        raise RuntimeTopologyPackageError(
            "runtime topology package supports alpha, beta, and gamma only"
        )
    if target != f"{environment}-local":
        raise RuntimeTopologyPackageError(
            "runtime topology target does not match environment"
        )
    root = runtime_shared_root
    try:
        root_metadata = root.lstat()
    except OSError as exc:
        raise RuntimeTopologyPackageError(
            "runtime-shared package root is unavailable"
        ) from exc
    if root.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
        raise RuntimeTopologyPackageError("runtime-shared package root is unsafe")

    output_prefix = PurePosixPath("runtime-topology")
    output_root = root / output_prefix
    if output_root.exists() or output_root.is_symlink():
        raise RuntimeTopologyPackageError(
            "runtime topology package already exists"
        )
    entries: list[dict[str, str]] = []

    def add_compose(
        source: Path,
        relative: PurePosixPath,
        *,
        role: str,
        layer: str,
        service: str = "",
    ) -> None:
        encoded, source_digest = _sealed_compose_bytes(source)
        _write_exclusive(root, output_prefix / relative, encoded)
        entries.append(
            _entry(
                role=role,
                layer=layer,
                service=service,
                reference=TOPOLOGY_RELATIVE_ROOT / relative,
                payload=encoded,
                source_digest=source_digest,
            )
        )

    add_compose(
        repo_root
        / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml",
        PurePosixPath("base.compose.yaml"),
        role="ops-base",
        layer="base",
    )

    services_root = repo_root / "quwoquan_service/services"
    try:
        service_directories = sorted(services_root.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise RuntimeTopologyPackageError(
            "first-party service tree is unavailable"
        ) from exc
    active_services = set(first_party_service_names(repo_root))
    service_names: list[str] = []
    for service_root in service_directories:
        service = service_root.name
        # Retired / non-topology service roots may be local materialization
        # symlinks during workspace transitions; only active owners must be
        # physical directories under the repository tree.
        if service not in active_services:
            continue
        if service_root.is_symlink():
            raise RuntimeTopologyPackageError(
                f"first-party service directory is unsafe: {service_root}"
            )
        try:
            service_metadata = service_root.lstat()
        except OSError as exc:
            raise RuntimeTopologyPackageError(
                f"first-party service directory is unavailable: {service_root}"
            ) from exc
        if not stat.S_ISDIR(service_metadata.st_mode):
            continue
        base_source = service_root / "deploy/compose.yaml"
        if not base_source.exists():
            continue
        service_names.append(service)
        add_compose(
            base_source,
            PurePosixPath("services", service, "base.compose.yaml"),
            role="service",
            layer="base",
            service=service,
        )
        environment_source = (
            service_root
            / "environments"
            / environment
            / "deploy/compose.yaml"
        )
        if environment_source.exists() or environment_source.is_symlink():
            add_compose(
                environment_source,
                PurePosixPath("services", service, "environment.compose.yaml"),
                role="service",
                layer="environment",
                service=service,
            )

    if not service_names:
        raise RuntimeTopologyPackageError(
            "runtime topology package has no first-party services"
        )
    add_compose(
        repo_root
        / "quwoquan_service/control-plane/platform-ops/deploy/compose.yaml",
        PurePosixPath("control-plane/platform-ops.compose.yaml"),
        role="control-plane",
        layer="base",
    )

    policy_source = (
        repo_root
        / "quwoquan_service/services/content-service/resources/policies/content/post/recommendation_policy.yaml"
    )
    policy_bytes = _safe_source_bytes(
        policy_source,
        label="recommendation policy source",
    )
    policy_relative = output_prefix / PurePosixPath(
        "policies/recommendation_policy.yaml"
    )
    _write_exclusive(root, policy_relative, policy_bytes)
    policy = {
        "ref": (
            TOPOLOGY_RELATIVE_ROOT / "policies/recommendation_policy.yaml"
        ).as_posix(),
        "digest": _sha256_bytes(policy_bytes),
    }
    identity = {
        "compose": entries,
        "policy": policy,
        "serviceNames": service_names,
    }
    manifest = {
        "schema": SCHEMA,
        "environment": environment,
        "target": target,
        **identity,
        "topologyDigest": _sha256_bytes(_canonical_json(identity)),
    }
    _write_exclusive(
        root,
        output_prefix / "manifest.json",
        (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        ),
    )
    return manifest


def _open_directory(parent_descriptor: int, name: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    return os.open(name, flags, dir_fd=parent_descriptor)


def _read_candidate_bytes(
    candidate_root: Path,
    relative: PurePosixPath,
    *,
    label: str,
) -> bytes:
    _validate_relative(relative, label=label)
    root_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    root_flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate_root, root_flags)
    except OSError as exc:
        raise RuntimeTopologyPackageError(
            "runtime candidate root is unsafe"
        ) from exc
    try:
        for part in relative.parts[:-1]:
            child = _open_directory(descriptor, part)
            os.close(descriptor)
            descriptor = child
        file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        file_descriptor = os.open(
            relative.parts[-1],
            file_flags,
            dir_fd=descriptor,
        )
        try:
            metadata = os.fstat(file_descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise RuntimeTopologyPackageError(
                    f"{label} must be a regular file"
                )
            chunks: list[bytes] = []
            while True:
                chunk = os.read(file_descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(file_descriptor)
    except OSError as exc:
        raise RuntimeTopologyPackageError(f"{label} is unsafe or missing") from exc
    finally:
        os.close(descriptor)


def _artifact_relative(value: object, *, label: str) -> PurePosixPath:
    text = str(value or "").strip()
    relative = PurePosixPath(text)
    _validate_relative(relative, label=label)
    if not relative.is_relative_to(TOPOLOGY_RELATIVE_ROOT):
        raise RuntimeTopologyPackageError(f"{label} escaped runtime topology")
    return relative


def load_runtime_topology_package(
    candidate_root: Path,
    *,
    environment: str,
    target: str,
    workload: str,
) -> dict[str, Any]:
    """Validate a candidate-owned topology and select one workload closure."""

    try:
        manifest = json.loads(
            _read_candidate_bytes(
                candidate_root,
                TOPOLOGY_RELATIVE_ROOT / "manifest.json",
                label="runtime topology manifest",
            ).decode("utf-8")
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeTopologyPackageError(
            "runtime topology manifest is unreadable"
        ) from exc
    required = {
        "schema",
        "environment",
        "target",
        "compose",
        "policy",
        "serviceNames",
        "topologyDigest",
    }
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise RuntimeTopologyPackageError("runtime topology manifest fields mismatch")
    if (
        manifest.get("schema") != SCHEMA
        or manifest.get("environment") != environment
        or manifest.get("target") != target
    ):
        raise RuntimeTopologyPackageError("runtime topology identity mismatch")
    service_names = manifest.get("serviceNames")
    if (
        not isinstance(service_names, list)
        or not service_names
        or any(not isinstance(item, str) or not item for item in service_names)
        or service_names != sorted(set(service_names))
    ):
        raise RuntimeTopologyPackageError("runtime topology service closure is invalid")
    compose = manifest.get("compose")
    policy = manifest.get("policy")
    identity = {
        "compose": compose,
        "policy": policy,
        "serviceNames": service_names,
    }
    if manifest.get("topologyDigest") != _sha256_bytes(_canonical_json(identity)):
        raise RuntimeTopologyPackageError("runtime topology identity digest drifted")
    if not isinstance(compose, list) or not compose:
        raise RuntimeTopologyPackageError("runtime topology Compose closure is empty")
    if not isinstance(policy, dict) or set(policy) != {"ref", "digest"}:
        raise RuntimeTopologyPackageError("runtime topology policy fields mismatch")

    selected_services: frozenset[str] | None
    include_control_plane = False
    if workload == "full":
        selected_services = None
        include_control_plane = True
    elif workload == "content-release":
        selected_services = CONTENT_RELEASE_SERVICES
    elif workload == "content-commercial":
        selected_services = CONTENT_COMMERCIAL_SERVICES
    else:
        raise RuntimeTopologyPackageError(
            "runtime topology workload is unsupported"
        )
    if selected_services is not None and not selected_services.issubset(service_names):
        raise RuntimeTopologyPackageError(
            "runtime topology content workload service closure is incomplete"
        )

    seen_refs: set[str] = set()
    seen_base = 0
    seen_service_layers: set[tuple[str, str]] = set()
    seen_control_plane = 0
    selected_paths: list[Path] = []
    for item in compose:
        expected_fields = {
            "role",
            "layer",
            "service",
            "ref",
            "digest",
            "sourceDigest",
        }
        if not isinstance(item, dict) or set(item) != expected_fields:
            raise RuntimeTopologyPackageError(
                "runtime topology Compose entry fields mismatch"
            )
        role = str(item.get("role") or "")
        layer = str(item.get("layer") or "")
        service = str(item.get("service") or "")
        reference = _artifact_relative(
            item.get("ref"),
            label="runtime topology Compose artifact",
        )
        if reference.as_posix() in seen_refs:
            raise RuntimeTopologyPackageError(
                "runtime topology Compose artifact is duplicated"
            )
        seen_refs.add(reference.as_posix())
        if role == "ops-base":
            if layer != "base" or service:
                raise RuntimeTopologyPackageError(
                    "runtime topology base entry identity is invalid"
                )
            seen_base += 1
            selected = True
        elif role == "service":
            if service not in service_names or layer not in {"base", "environment"}:
                raise RuntimeTopologyPackageError(
                    "runtime topology service entry identity is invalid"
                )
            service_layer = (service, layer)
            if service_layer in seen_service_layers:
                raise RuntimeTopologyPackageError(
                    "runtime topology service layer is duplicated"
                )
            seen_service_layers.add(service_layer)
            selected = selected_services is None or service in selected_services
        elif role == "control-plane":
            if layer != "base" or service:
                raise RuntimeTopologyPackageError(
                    "runtime topology control-plane identity is invalid"
                )
            seen_control_plane += 1
            selected = include_control_plane
        else:
            raise RuntimeTopologyPackageError(
                "runtime topology Compose role is invalid"
            )
        encoded = _read_candidate_bytes(
            candidate_root,
            reference,
            label="runtime topology Compose artifact",
        )
        if (
            item.get("digest") != _sha256_bytes(encoded)
            or _DIGEST.fullmatch(str(item.get("sourceDigest") or "")) is None
        ):
            raise RuntimeTopologyPackageError(
                "runtime topology Compose artifact drifted"
            )
        try:
            parsed = yaml.safe_load(encoded.decode("utf-8"))
        except (UnicodeError, yaml.YAMLError) as exc:
            raise RuntimeTopologyPackageError(
                "runtime topology Compose artifact is unreadable"
            ) from exc
        services = parsed.get("services") if isinstance(parsed, dict) else None
        if not isinstance(services, dict) or not services:
            raise RuntimeTopologyPackageError(
                "runtime topology Compose artifact has no services"
            )
        if any(
            not isinstance(definition, Mapping) or "build" in definition
            for definition in services.values()
        ):
            raise RuntimeTopologyPackageError(
                "runtime topology Compose artifact retains a live build context"
            )
        workload_selector = parsed.get("x-qwq-workloads")
        if workload_selector is not None:
            allowed_workloads = {"full", "content-release", "content-commercial"}
            if (
                role != "service"
                or layer != "environment"
                or not isinstance(workload_selector, list)
                or not workload_selector
                or any(
                    not isinstance(item, str) or item not in allowed_workloads
                    for item in workload_selector
                )
                or len(workload_selector) != len(set(workload_selector))
            ):
                raise RuntimeTopologyPackageError(
                    "runtime topology workload selector is invalid"
                )
            selected = selected and workload in workload_selector
        if selected:
            selected_paths.append(candidate_root / reference.as_posix())

    seen_service_base = {
        service for service, layer in seen_service_layers if layer == "base"
    }
    if (
        seen_base != 1
        or seen_control_plane != 1
        or seen_service_base != set(service_names)
    ):
        raise RuntimeTopologyPackageError(
            "runtime topology Compose service closure is incomplete"
        )
    policy_reference = _artifact_relative(
        policy.get("ref"),
        label="runtime topology policy artifact",
    )
    policy_bytes = _read_candidate_bytes(
        candidate_root,
        policy_reference,
        label="runtime topology policy artifact",
    )
    if policy.get("digest") != _sha256_bytes(policy_bytes):
        raise RuntimeTopologyPackageError("runtime topology policy artifact drifted")

    return {
        "schema": SCHEMA,
        "environment": environment,
        "target": target,
        "workload": workload,
        "topologyDigest": manifest["topologyDigest"],
        "composeFiles": selected_paths,
        "policyFile": candidate_root / policy_reference.as_posix(),
        "serviceNames": service_names,
    }


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-root", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--workload", required=True)
    parser.add_argument("--format", choices=("json", "shell"), default="json")
    args = parser.parse_args()
    try:
        payload = load_runtime_topology_package(
            Path(args.candidate_root),
            environment=args.environment,
            target=args.target,
            workload=args.workload,
        )
    except (OSError, RuntimeTopologyPackageError) as exc:
        parser.exit(2, f"GATE_BLOCK: {exc}\n")
    serializable = {
        **payload,
        "composeFiles": [str(path) for path in payload["composeFiles"]],
        "policyFile": str(payload["policyFile"]),
    }
    if args.format == "json":
        print(json.dumps(serializable, ensure_ascii=False, sort_keys=True))
    else:
        print(
            "QWQ_RUNTIME_TOPOLOGY_COMPOSE_FILES="
            + shlex.quote("\n".join(serializable["composeFiles"]))
        )
        print(
            "QWQ_RUNTIME_TOPOLOGY_POLICY_FILE="
            + shlex.quote(serializable["policyFile"])
        )
        print(
            "QWQ_RUNTIME_TOPOLOGY_DIGEST="
            + shlex.quote(str(serializable["topologyDigest"]))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
