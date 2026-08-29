"""Project autonomous core-service Compose fragments into one service-core PID."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

class ServiceCoreCompositionError(ValueError):
    """The core module closure cannot be projected without semantic drift."""


_ROOT = Path(__file__).resolve().parents[3]
_MANIFEST_PATH = (
    _ROOT / "quwoquan_service/cmd/service-core/composition.yaml"
)
SERVICE_CORE_WORKLOAD = "service-core"
SERVICE_CORE_IMAGE_ENV = "QWQ_COMPOSE_SERVICE_CORE_IMAGE"
SERVICE_CORE_SCHEMA = "qwq.service_core_projection.v1"


def _service_core_module_target_ports(modules: Sequence[object]) -> dict[str, int]:
    """模块在容器内对外可转发的监听口只有 `port`，不是 `internalAddress`。

    `internalAddress`（`127.0.0.1:2808x`）是虚拟路由器在容器内的回环上游，Docker
    转发不到只绑 loopback 的 socket；把它当发布 target 会让 canonical 主机端口运行期
    不可服务。共用容器口（user/chat 同 18081，assistant/notification 同 18087）合法，
    由 publisher 四元组身份（含 hostPort）区分归属，不在此处要求 target 互异。
    """
    target_ports: dict[str, int] = {}
    for module in modules:
        if not isinstance(module, Mapping):
            raise TypeError("service-core composition module is invalid")
        module_name = str(module.get("name") or "").strip()
        public_port = module.get("port")
        if (
            not module_name
            or module_name in target_ports
            or isinstance(public_port, bool)
            or not isinstance(public_port, int)
            or not 0 < public_port < 65536
        ):
            raise RuntimeError("service-core composition module port is invalid")
        internal_address = str(module.get("internalAddress") or "").strip()
        if internal_address:
            internal_host, separator, internal_port_text = internal_address.rpartition(":")
            if (
                not separator
                or not internal_host
                or not internal_port_text.isdigit()
                or not 0 < int(internal_port_text) < 65536
            ):
                raise RuntimeError("service-core composition internal address is invalid")
        target_ports[module_name] = public_port
    return target_ports


_COMPOSITION_CACHE: tuple[tuple[str, ...], dict[str, int]] | None = None


def _load_composition() -> tuple[tuple[str, ...], dict[str, int]]:
    """惰性装载并缓存 composition 声明，失败一律是 `ServiceCoreCompositionError`。

    这层惰性只为门禁通道服务：`service_core_composition_issues()` 与
    `port_manifest.validate_port_manifest` 能把装载失败转成结构化 issue，而不是一段
    发生在模块加载期、看不出是哪个门禁在检查的裸 traceback。

    它**不覆盖任意 import 链**：`SERVICE_CORE_MODULES` / `SERVICE_CORE_MODULE_SET` 仍被
    `cli/stackctl.py`、`runtime_topology_package`、`service_core_cutover`、
    `immutable_image_composition`、`ci/plan_service_release_images` 五处在模块级绑定，
    `__getattr__` 会在那些模块 import 期就触发本函数，装载失败照样是 import 期异常。
    其中 `stackctl.py` 那条影响最大：composition 声明损坏时**任何** stackctl 子命令
    （含 `down` / `repair`）都在 import 期抛裸异常，而不是走门禁的结构化 issue 通道。
    要覆盖那几条链需要把它们改成函数内取值，属独立工作项。
    """
    global _COMPOSITION_CACHE
    if _COMPOSITION_CACHE is not None:
        return _COMPOSITION_CACHE
    try:
        manifest = yaml.safe_load(_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ServiceCoreCompositionError(
            f"service-core composition manifest is unreadable: {exc}"
        ) from exc
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("schema") != "quwoquan.service_core_manifest.v1"
        or not isinstance(manifest.get("modules"), Sequence)
    ):
        raise ServiceCoreCompositionError(
            "service-core composition manifest is invalid"
        )
    names = tuple(
        str(module.get("name") or "").strip()
        for module in manifest["modules"]
        if isinstance(module, Mapping)
    )
    if not names or any(not name for name in names):
        raise ServiceCoreCompositionError(
            "service-core composition manifest module closure is invalid"
        )
    try:
        target_ports = _service_core_module_target_ports(manifest["modules"])
    except (RuntimeError, TypeError) as exc:
        raise ServiceCoreCompositionError(str(exc)) from exc
    _COMPOSITION_CACHE = (names, target_ports)
    return _COMPOSITION_CACHE


def _module_names() -> tuple[str, ...]:
    return _load_composition()[0]


def _module_set() -> frozenset[str]:
    return frozenset(_load_composition()[0])


def __getattr__(name: str) -> Any:
    """把两个模块常量做成惰性属性，保持既有 `from ... import` 写法不变。"""
    if name == "SERVICE_CORE_MODULES":
        return _module_names()
    if name == "SERVICE_CORE_MODULE_SET":
        return _module_set()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def service_core_composition_issues() -> list[str]:
    """把装载失败转成结构化 issue，供门禁在不抛异常的前提下判否。"""
    try:
        _load_composition()
    except ServiceCoreCompositionError as exc:
        return [str(exc)]
    return []


def service_core_module_target_ports() -> dict[str, int]:
    return dict(_load_composition()[1])


def _token(service: str) -> str:
    return service.upper().replace("-", "_")


def module_config_environment_key(service: str) -> str:
    if service not in _module_set():
        raise ServiceCoreCompositionError(f"unknown service-core module: {service}")
    return f"SERVICE_CORE_{_token(service)}_CONFIG_VERSION"


def module_instance_environment_key(service: str) -> str:
    if service not in _module_set():
        raise ServiceCoreCompositionError(f"unknown service-core module: {service}")
    return f"SERVICE_CORE_{_token(service)}_SERVICE_INSTANCE_ID"


def _verified_published_port(service: str, raw: Any) -> Any:
    """校验发布口的容器侧 target 与 composition 声明同源后原样透传。

    这里只判否不改写：容器侧 target 必须等于模块声明的 `port`，让 composition.yaml
    与 Compose 片段互为单一真相；改写 target 会把发布目标指向不可转发的回环口。
    """
    declared_port = _load_composition()[1].get(service)
    if declared_port is None:
        # 调用方今天只会传 composition 声明过的模块，但静默透传会成为本函数唯一绕过
        # target drift 判否的出口；调用面一旦变宽，未声明模块的发布口就会不经校验进投影。
        raise ServiceCoreCompositionError(
            f"unknown service-core module published port: {service}"
        )
    if isinstance(raw, Mapping):
        verified = copy.deepcopy(dict(raw))
        raw_target = verified.get("target")
        if (
            isinstance(raw_target, bool)
            or not isinstance(raw_target, (int, str))
            or not str(raw_target).isdigit()
            or int(raw_target) != declared_port
        ):
            raise ServiceCoreCompositionError(
                f"service-core published port target drift: {service}"
            )
        return verified
    if not isinstance(raw, str) or not raw.strip():
        raise ServiceCoreCompositionError(
            f"service-core published port syntax is invalid: {service}"
        )
    endpoint, separator, protocol = raw.strip().partition("/")
    if separator and protocol not in {"tcp", "udp"}:
        raise ServiceCoreCompositionError(
            f"service-core published port protocol is invalid: {service}"
        )
    prefix, colon, target_text = endpoint.rpartition(":")
    if (
        not colon
        or not prefix
        or not target_text.isdigit()
        or int(target_text) != declared_port
    ):
        raise ServiceCoreCompositionError(
            f"service-core published port target drift: {service}"
        )
    return copy.deepcopy(raw)


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
            for module in _module_names()
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
        f"QWQ_COMPOSE_{_token(module)}_IMAGE" for module in _module_names()
    }
    companions: list[str] = []
    for name, definition in service_map.items():
        if name in _module_set() or not isinstance(definition, Mapping):
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
        service for service in _module_names() if service in service_map
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
                if dependency in _module_set() or dependency in removed_jobs:
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
                projected_value = (
                    _verified_published_port(service, value)
                    if field == "ports"
                    else copy.deepcopy(value)
                )
                if projected_value not in target:
                    target.append(projected_value)
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
        "modules": list(_module_names()),
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
    if set(module_source_digests) != _module_set():
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
