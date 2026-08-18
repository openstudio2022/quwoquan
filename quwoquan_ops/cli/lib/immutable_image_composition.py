"""Canonical first-party image composition derived from service-owned packages."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, MutableMapping, Sequence
from pathlib import Path

import yaml

from quwoquan_ops.cli.lib.output_paths import service_deployment_package_dir
from quwoquan_ops.cli.lib.service_core_composition import (
    SERVICE_CORE_MODULE_SET,
    SERVICE_CORE_WORKLOAD,
    service_core_source_digest,
)


ROOT = Path(__file__).resolve().parents[3]
SHA256_PATTERN = re.compile(r"sha256:([0-9a-f]{64})")
LOCAL_SOURCE_IMAGE_REF_PATTERN = re.compile(
    r"localhost/quwoquan_service_[a-z0-9_-]+:[0-9a-f]{64}"
)
OCI_DIGEST_IMAGE_REF_PATTERN = re.compile(
    r"[^\s@]+@sha256:[0-9a-f]{64}"
)
LOCAL_IMAGE_ID_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
IMMUTABLE_IMAGE_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


def first_party_service_names(repo_root: Path = ROOT) -> tuple[str, ...]:
    """Discover active image owners from autonomous roots and runtime topology."""

    services_root = repo_root / "quwoquan_service" / "services"
    owners = {
        path.parents[1].name
        for path in services_root.glob("*/config/schema.yaml")
        if (path.parents[1] / "deploy" / "compose.yaml").is_file()
    }
    topology_path = (
        repo_root
        / "quwoquan_ops"
        / "environments"
        / "compose"
        / "docker-compose.gamma-local.yaml"
    )
    try:
        topology = yaml.safe_load(topology_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(
            f"canonical runtime topology is unavailable: {topology_path}"
        ) from exc
    topology_services = topology.get("services") if isinstance(topology, dict) else None
    if not isinstance(topology_services, dict) or not topology_services:
        raise ValueError(
            f"canonical runtime topology has no workloads: {topology_path}"
        )
    active_workloads = set(topology_services)
    owners.intersection_update(active_workloads)
    platform_ops = (
        repo_root
        / "quwoquan_service"
        / "control-plane"
        / "platform-ops"
    )
    if (
        (platform_ops / "config" / "schema.yaml").is_file()
        and (platform_ops / "deploy" / "compose.yaml").is_file()
        and "platform-ops-service" in active_workloads
    ):
        owners.add("platform-ops-service")
    return tuple(sorted(owners))


def compose_image_environment_key(service: str) -> str:
    token = service.upper().replace("-", "_")
    return f"QWQ_COMPOSE_{token}_IMAGE"


def local_release_image_environment_key(service: str) -> str:
    token = service.upper().replace("-", "_")
    return f"LOCAL_GAMMA_{token}_IMAGE"


def _load_package_provenance(
    environment: str,
    service: str,
) -> tuple[Path, dict[str, object]]:
    path = service_deployment_package_dir(environment, service) / "provenance.json"
    if not path.is_file():
        raise FileNotFoundError(f"service package provenance missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"service package provenance must be an object: {path}")
    if payload.get("service") != service or payload.get("environment") != environment:
        raise ValueError(f"service package provenance identity mismatch: {path}")
    return path, payload


def packaged_service_source_digest(environment: str, service: str) -> str:
    path, payload = _load_package_provenance(environment, service)
    digests = payload.get("digests")
    if not isinstance(digests, dict):
        raise ValueError(f"service source provenance missing: {path}")
    source_digest = str(digests.get("sourceTree") or "")
    if SHA256_PATTERN.fullmatch(source_digest) is None:
        raise ValueError(f"invalid service source digest: {path}")
    return source_digest


def packaged_service_environment_build_digest(environment: str, service: str) -> str:
    """Bind one local image identity to its packaged environment configuration."""

    path, payload = _load_package_provenance(environment, service)
    source_digest = packaged_service_source_digest(environment, service)
    config_version = str(payload.get("configVersion") or "").strip()
    if SHA256_PATTERN.fullmatch(config_version) is None:
        raise ValueError(f"invalid service config version: {path}")
    encoded = json.dumps(
        {
            "environment": environment,
            "service": service,
            "sourceDigest": source_digest,
            "configVersion": config_version,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def packaged_service_source_image_ref(environment: str, service: str) -> str:
    """Return an environment-bound local build tag, never a cross-env source tag."""

    build_digest = packaged_service_environment_build_digest(environment, service)
    repository = service.replace("-", "_")
    return f"localhost/quwoquan_service_{repository}:{build_digest[7:]}"


def runtime_image_owner_names(repo_root: Path = ROOT) -> tuple[str, ...]:
    """Return deployed image owners after the core modules become one PID."""

    logical = set(first_party_service_names(repo_root))
    if not SERVICE_CORE_MODULE_SET.issubset(logical):
        missing = sorted(SERVICE_CORE_MODULE_SET - logical)
        raise ValueError(
            "service-core logical module closure is incomplete: " + ", ".join(missing)
        )
    return tuple(
        sorted((logical - SERVICE_CORE_MODULE_SET) | {SERVICE_CORE_WORKLOAD})
    )


def packaged_runtime_source_image_ref(environment: str, service: str) -> str:
    if service != SERVICE_CORE_WORKLOAD:
        return packaged_service_source_image_ref(environment, service)
    module_digests = {
        module: packaged_service_environment_build_digest(environment, module)
        for module in SERVICE_CORE_MODULE_SET
    }
    digest = service_core_source_digest(module_digests)
    return f"localhost/quwoquan_service_core:{digest[7:]}"


def validate_immutable_image_ref(service: str, ref: str) -> str:
    """Return one exact local-source or OCI-digest ref, never a mutable tag."""

    service_name = str(service).strip()
    image_ref = str(ref).strip()
    if not service_name or not image_ref:
        raise ValueError("immutable image composition contains an empty binding")
    if LOCAL_SOURCE_IMAGE_REF_PATTERN.fullmatch(image_ref) is not None:
        expected_repository = (
            "localhost/quwoquan_service_core:"
            if service_name == SERVICE_CORE_WORKLOAD
            else "localhost/quwoquan_service_"
            + service_name.replace("-", "_")
            + ":"
        )
        if not image_ref.startswith(expected_repository):
            raise ValueError(
                f"immutable local image owner mismatch: {service_name}"
            )
        return image_ref
    if OCI_DIGEST_IMAGE_REF_PATTERN.fullmatch(image_ref) is None:
        if LOCAL_IMAGE_ID_PATTERN.fullmatch(image_ref) is not None:
            return image_ref
        raise ValueError(f"mutable or non-canonical image ref is forbidden: {service_name}")
    return image_ref


def immutable_image_digest(refs: Mapping[str, str]) -> str:
    """Derive the one full SHA-256 identity of an exact image composition."""

    if not refs:
        raise ValueError("immutable image composition must not be empty")
    canonical_refs: dict[str, str] = {}
    for service, ref in sorted(refs.items()):
        service_name = str(service).strip()
        image_ref = validate_immutable_image_ref(service_name, ref)
        canonical_refs[service_name] = image_ref
    encoded = json.dumps(
        canonical_refs,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    digest = f"sha256:{hashlib.sha256(encoded).hexdigest()}"
    if IMMUTABLE_IMAGE_DIGEST_PATTERN.fullmatch(digest) is None:
        raise AssertionError("derived immutable image digest is not canonical")
    return digest


def bind_packaged_image_composition(
    environment: str,
    target: MutableMapping[str, str],
    *,
    services: Sequence[str] | None = None,
    include_local_release_aliases: bool = False,
) -> dict[str, object]:
    owners = tuple(services or runtime_image_owner_names())
    refs = {
        service: packaged_runtime_source_image_ref(environment, service)
        for service in owners
    }
    digest = immutable_image_digest(refs)
    for service, ref in refs.items():
        target[compose_image_environment_key(service)] = ref
        if include_local_release_aliases:
            target[local_release_image_environment_key(service)] = ref
    target["QWQ_COMPOSE_IMAGE_VERSION"] = digest
    # Compose image tags cannot embed a second colon; keep the full digest for
    # in-container IMAGE_VERSION metadata and expose a tag-safe hex form.
    target["QWQ_COMPOSE_IMAGE_TAG"] = digest.removeprefix("sha256:")
    if include_local_release_aliases:
        target["LOCAL_GAMMA_IMAGE_VERSION"] = digest
    return {"digest": digest, "images": refs}
