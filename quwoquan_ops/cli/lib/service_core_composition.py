"""Project autonomous core-service Compose fragments into one service-core PID."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml


_ROOT = Path(__file__).resolve().parents[3]
_MANIFEST_PATH = (
    _ROOT / "quwoquan_service/cmd/service-core/composition.yaml"
)
_MANIFEST = yaml.safe_load(_MANIFEST_PATH.read_text(encoding="utf-8"))
if (
    not isinstance(_MANIFEST, Mapping)
    or _MANIFEST.get("schema") != "quwoquan.service_core_manifest.v1"
    or not isinstance(_MANIFEST.get("modules"), Sequence)
):
    raise RuntimeError("service-core composition manifest is invalid")
SERVICE_CORE_MODULES: tuple[str, ...] = tuple(
    str(module.get("name") or "").strip()
    for module in _MANIFEST["modules"]
    if isinstance(module, Mapping)
)
if not SERVICE_CORE_MODULES or any(not module for module in SERVICE_CORE_MODULES):
    raise RuntimeError("service-core composition manifest module closure is invalid")
SERVICE_CORE_MODULE_SET = frozenset(SERVICE_CORE_MODULES)
SERVICE_CORE_WORKLOAD = "service-core"
SERVICE_CORE_IMAGE_ENV = "QWQ_COMPOSE_SERVICE_CORE_IMAGE"
SERVICE_CORE_SCHEMA = "qwq.service_core_projection.v1"


class ServiceCoreCompositionError(ValueError):
    """The core module closure cannot be projected without semantic drift."""


def _token(service: str) -> str:
    return service.upper().replace("-", "_")


def module_config_environment_key(service: str) -> str:
    if service not in SERVICE_CORE_MODULE_SET:
        raise ServiceCoreCompositionError(f"unknown service-core module: {service}")
    return f"SERVICE_CORE_{_token(service)}_CONFIG_VERSION"


def module_instance_environment_key(service: str) -> str:
    if service not in SERVICE_CORE_MODULE_SET:
        raise ServiceCoreCompositionError(f"unknown service-core module: {service}")
    return f"SERVICE_CORE_{_token(service)}_SERVICE_INSTANCE_ID"


def _project_environment(service: str, raw: object) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ServiceCoreCompositionError(
            f"service-core environment must be an object: {service}"
        )
    projected = copy.deepcopy(dict(raw))
    projected.pop("SERVICE_NAME", None)
    config_version = projected.pop("CONFIG_VERSION", None)
    if config_version is not None:
        projected[module_config_environment_key(service)] = config_version
    instance_id = projected.pop("SERVICE_INSTANCE_ID", None)
    if instance_id is not None:
        projected[module_instance_environment_key(service)] = instance_id
    return projected


def _rewrite_core_dependencies(service_map: dict[str, Any]) -> None:
    for workload, raw_definition in tuple(service_map.items()):
        if not isinstance(raw_definition, Mapping):
            continue
        definition = copy.deepcopy(dict(raw_definition))
        raw_dependencies = definition.get("depends_on")
        if not isinstance(raw_dependencies, Mapping):
            continue
        dependencies = dict(raw_dependencies)
        core_conditions = [
            dependencies.pop(module)
            for module in SERVICE_CORE_MODULES
            if module in dependencies
        ]
        if not core_conditions:
            continue
        first = core_conditions[0]
        if any(condition != first for condition in core_conditions[1:]):
            raise ServiceCoreCompositionError(
                f"service-core dependency condition drift: {workload}"
            )
        dependencies[SERVICE_CORE_WORKLOAD] = first
        definition["depends_on"] = dependencies
        service_map[workload] = definition


def _core_companion_jobs(service_map: Mapping[str, Any]) -> list[str]:
    """One-shot jobs that run a core module's per-service image and binary.

    service-core 是单二进制镜像,不再携带各模块的独立迁移/回填命令;
    这些伴生 job 的数据变更由模块在 servicehost 启动阶段自行承担。
    """
    module_image_keys = {
        f"QWQ_COMPOSE_{_token(module)}_IMAGE" for module in SERVICE_CORE_MODULES
    }
    companions: list[str] = []
    for name, definition in service_map.items():
        if name in SERVICE_CORE_MODULE_SET or not isinstance(definition, Mapping):
            continue
        image = str(definition.get("image") or "")
        if any(key in image for key in module_image_keys):
            companions.append(str(name))
    return companions


def project_compose_document(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Replace core workloads in one Compose layer with one mergeable core layer."""

    projected = copy.deepcopy(dict(payload))
    services = projected.get("services")
    if not isinstance(services, Mapping):
        raise ServiceCoreCompositionError("Compose services must be an object")
    service_map = dict(services)
    present = [
        service for service in SERVICE_CORE_MODULES if service in service_map
    ]
    if not present:
        _rewrite_core_dependencies(service_map)
        projected["services"] = service_map
        return projected

    removed_jobs = _core_companion_jobs(service_map)
    for job in removed_jobs:
        service_map.pop(job, None)
    if removed_jobs:
        for raw_definition in service_map.values():
            if not isinstance(raw_definition, Mapping):
                continue
            raw_dependencies = raw_definition.get("depends_on")
            if isinstance(raw_dependencies, dict):
                for job in removed_jobs:
                    raw_dependencies.pop(job, None)

    core_networks: dict[str, Any] = {
        "default": {"aliases": list(present)},
    }
    core: dict[str, Any] = {
        "image": (
            "${"
            + SERVICE_CORE_IMAGE_ENV
            + ":?fixed service-core source image reference is required}"
        ),
        "networks": core_networks,
    }
    environments: dict[str, Any] = {}
    dependencies: dict[str, Any] = {}
    ports: list[Any] = []
    volumes: list[Any] = []
    for service in present:
        definition = service_map.pop(service)
        if not isinstance(definition, Mapping):
            raise ServiceCoreCompositionError(
                f"core service definition must be an object: {service}"
            )
        definition = dict(definition)
        environments.update(_project_environment(service, definition.get("environment")))
        raw_dependencies = definition.get("depends_on")
        if raw_dependencies is not None:
            if not isinstance(raw_dependencies, Mapping):
                raise ServiceCoreCompositionError(
                    f"core service dependencies must be an object: {service}"
                )
            for dependency, condition in raw_dependencies.items():
                if dependency in SERVICE_CORE_MODULE_SET or dependency in removed_jobs:
                    continue
                previous = dependencies.get(str(dependency))
                if previous is not None and previous != condition:
                    raise ServiceCoreCompositionError(
                        f"service-core dependency drift: {dependency}"
                    )
                dependencies[str(dependency)] = copy.deepcopy(condition)
        for field, target in (("ports", ports), ("volumes", volumes)):
            values = definition.get(field)
            if values is None:
                continue
            if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
                raise ServiceCoreCompositionError(
                    f"core service {field} must be a list: {service}"
                )
            for value in values:
                if value not in target:
                    target.append(copy.deepcopy(value))
        raw_networks = definition.get("networks")
        if raw_networks is not None:
            if isinstance(raw_networks, Mapping):
                network_items = raw_networks.items()
            elif isinstance(raw_networks, Sequence) and not isinstance(
                raw_networks, (str, bytes)
            ):
                network_items = ((str(name), {}) for name in raw_networks)
            else:
                raise ServiceCoreCompositionError(
                    f"core service networks must be a list or object: {service}"
                )
            for network, configuration in network_items:
                network_name = str(network)
                if network_name == "default":
                    continue
                previous = core_networks.get(network_name)
                normalized = copy.deepcopy(configuration or {})
                if previous is not None and previous != normalized:
                    raise ServiceCoreCompositionError(
                        f"service-core network drift: {network_name}"
                    )
                core_networks[network_name] = normalized
        if "build" in definition:
            raw_build = definition["build"]
            if isinstance(raw_build, str):
                build = {"context": raw_build}
            elif isinstance(raw_build, Mapping):
                build = copy.deepcopy(dict(raw_build))
            else:
                raise ServiceCoreCompositionError(
                    f"core service build must be a string or object: {service}"
                )
            existing_build = core.get("build")
            candidate_build = {
                **build,
                "dockerfile": "cmd/service-core/Dockerfile",
            }
            if existing_build is not None and (
                existing_build.get("context") != candidate_build.get("context")
                or existing_build.get("args") != candidate_build.get("args")
            ):
                raise ServiceCoreCompositionError(
                    f"service-core build input drift: {service}"
                )
            core["build"] = candidate_build
        if service == "api-edge" and "healthcheck" in definition:
            core["healthcheck"] = copy.deepcopy(definition["healthcheck"])

    if environments:
        core["environment"] = environments
    if dependencies:
        core["depends_on"] = dependencies
    if ports:
        core["ports"] = ports
    if volumes:
        core["volumes"] = volumes
    _rewrite_core_dependencies(service_map)
    service_map[SERVICE_CORE_WORKLOAD] = core
    projected["services"] = service_map
    projected["x-qwq-service-core"] = {
        "schema": SERVICE_CORE_SCHEMA,
        "modules": list(SERVICE_CORE_MODULES),
        "removedCompanionJobs": sorted(removed_jobs),
    }
    return projected


def project_compose_file(source: Path, destination: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ServiceCoreCompositionError(
            f"service-core Compose source is unreadable: {source}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ServiceCoreCompositionError(
            f"service-core Compose source must be an object: {source}"
        )
    projected = project_compose_document(payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        yaml.safe_dump(projected, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return projected


def service_core_source_digest(module_source_digests: Mapping[str, str]) -> str:
    if set(module_source_digests) != SERVICE_CORE_MODULE_SET:
        raise ServiceCoreCompositionError(
            "service-core source digest requires every module exactly once"
        )
    canonical = json.dumps(
        dict(sorted(module_source_digests.items())),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()
