"""判定输入的现场加载：domain 归属、operation、对象契约面与真实注册 series。"""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path

import yaml

from .constants import CONTRACT_GRAPH, SERVICES_ROOT
from .models import ContractInputError, ObjectSurface, OperationContract, _number

from quwoquan_ops.cli.lib.immutable_image_composition import first_party_service_names


def load_domain_services(services_root: Path = SERVICES_ROOT) -> dict[str, str]:
    """domain -> service 目录名，唯一真相源是各服务 contracts/domain.yaml。"""
    mapping: dict[str, str] = {}
    for path in sorted(services_root.glob("*/contracts/domain.yaml")):
        service = path.parents[1].name
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            raise ContractInputError(f"{path}: 无法解析 domain.yaml: {error}") from error
        domain = str((document or {}).get("domain", "")).strip()
        if not domain:
            raise ContractInputError(f"{path}: 缺少 domain")
        if domain in mapping:
            raise ContractInputError(
                f"domain {domain!r} 同时被 {mapping[domain]} 与 {service} 声明"
            )
        mapping[domain] = service
    if not mapping:
        raise ContractInputError(f"{services_root}: 没有找到任何 contracts/domain.yaml")
    return mapping


def runtime_domain_services(
    domain_services: dict[str, str],
    services_root: Path = SERVICES_ROOT,
) -> dict[str, str]:
    """Limit observability projections to canonical runtime workloads."""

    repo_root = services_root.parent.parent
    topology = (
        repo_root
        / "quwoquan_ops"
        / "environments"
        / "compose"
        / "docker-compose.gamma-local.yaml"
    )
    if not topology.is_file():
        return dict(domain_services)
    try:
        active_services = set(first_party_service_names(repo_root))
    except ValueError as error:
        raise ContractInputError(str(error)) from error
    return {
        domain: service
        for domain, service in domain_services.items()
        if service in active_services
    }


def load_operations(
    contract_graph: Path = CONTRACT_GRAPH,
    domain_services: dict[str, str] | None = None,
) -> list[OperationContract]:
    services = domain_services if domain_services is not None else load_domain_services()
    try:
        payload = json.loads(contract_graph.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractInputError(f"{contract_graph}: 无法读取 ContractGraph: {error}") from error
    operations = payload.get("operations")
    if not isinstance(operations, list):
        raise ContractInputError("ContractGraph.operations 必须是数组")

    result: list[OperationContract] = []
    for raw in operations:
        if not isinstance(raw, dict):
            raise ContractInputError("ContractGraph.operations 元素必须是对象")
        operation_id = str(raw.get("id", "")).strip()
        if not operation_id:
            raise ContractInputError("ContractGraph operation 缺少 id")
        domain = str(raw.get("domain", "")).strip()
        if domain not in services:
            raise ContractInputError(
                f"{operation_id} 的 domain {domain!r} 没有服务 contracts/domain.yaml 归属"
            )
        object_id = str(raw.get("objectId", "")).strip()
        if not object_id.startswith(f"{domain}."):
            raise ContractInputError(f"{operation_id} 的 objectId {object_id!r} 不属于 {domain}")
        commercial = raw.get("commercial")
        if not isinstance(commercial, dict):
            raise ContractInputError(f"{operation_id} 缺少 commercial")
        telemetry = raw.get("telemetry")
        if not isinstance(telemetry, dict):
            raise ContractInputError(f"{operation_id} 缺少 telemetry")
        metric = str(telemetry.get("metric", "")).strip()
        if not metric:
            raise ContractInputError(f"{operation_id} 缺少 telemetry.metric")
        slo = raw.get("slo")
        if not isinstance(slo, dict):
            raise ContractInputError(f"{operation_id} 缺少 slo")
        path_template = str(raw.get("pathTemplate", "")).strip()
        if not path_template.startswith("/"):
            raise ContractInputError(f"{operation_id} 缺少 pathTemplate")
        method = str(raw.get("method", "")).strip().upper()
        if not method:
            raise ContractInputError(f"{operation_id} 缺少 method")
        result.append(
            OperationContract(
                operation_id=operation_id,
                domain=domain,
                service=services[domain],
                object_name=object_id[len(domain) + 1 :],
                method=method,
                path_template=path_template,
                commercial_status=str(commercial.get("status", "")).strip(),
                block_reason=str(commercial.get("gapId", "")).strip(),
                metric=metric,
                latency_p95_ms=_number(
                    slo.get("latencyP95Milliseconds"),
                    "slo.latencyP95Milliseconds",
                    operation_id,
                ),
                availability_percent=_number(
                    slo.get("availabilityPercent"),
                    "slo.availabilityPercent",
                    operation_id,
                ),
            )
        )
    return sorted(result, key=lambda item: (item.domain, item.object_name, item.operation_id))


def load_object_surfaces(
    contract_graph: Path = CONTRACT_GRAPH,
    domain_services: dict[str, str] | None = None,
) -> list[ObjectSurface]:
    """ContractGraph 全部 object 的契约面分类；对象集合只来自 ContractGraph.objects。"""
    services = domain_services if domain_services is not None else load_domain_services()
    try:
        payload = json.loads(contract_graph.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractInputError(f"{contract_graph}: 无法读取 ContractGraph: {error}") from error
    objects = payload.get("objects")
    if not isinstance(objects, list):
        raise ContractInputError("ContractGraph.objects 必须是数组")

    operations = payload.get("operations") or []
    entrypoints = payload.get("runtimeEntrypoints") or []
    total: collections.Counter[str] = collections.Counter()
    ready: collections.Counter[str] = collections.Counter()
    for raw in operations:
        if not isinstance(raw, dict):
            continue
        object_id = str(raw.get("objectId", "")).strip()
        total[object_id] += 1
        if str((raw.get("commercial") or {}).get("status", "")).strip() == "ready":
            ready[object_id] += 1
    runtime: dict[str, list[str]] = collections.defaultdict(list)
    runtime_metrics: dict[str, list[str]] = collections.defaultdict(list)
    for raw in entrypoints:
        if not isinstance(raw, dict):
            continue
        object_id = str(raw.get("objectId", "")).strip()
        runtime[object_id].append(str(raw.get("id", "")).strip())
        metric = str((raw.get("telemetry") or {}).get("metric", "")).strip()
        if metric:
            runtime_metrics[object_id].append(metric)

    known = {str(raw.get("id", "")).strip() for raw in objects if isinstance(raw, dict)}
    for object_id in sorted(set(total) | set(runtime)):
        if object_id not in known:
            raise ContractInputError(
                f"ContractGraph 引用了未声明的对象 {object_id!r}"
            )

    surfaces: list[ObjectSurface] = []
    for raw in objects:
        if not isinstance(raw, dict):
            raise ContractInputError("ContractGraph.objects 元素必须是对象")
        object_id = str(raw.get("id", "")).strip()
        domain = str(raw.get("domain", "")).strip()
        if not object_id:
            raise ContractInputError("ContractGraph object 缺少 id")
        if domain not in services:
            raise ContractInputError(
                f"对象 {object_id} 的 domain {domain!r} 没有服务 contracts/domain.yaml 归属"
            )
        surfaces.append(
            ObjectSurface(
                object_id=object_id,
                domain=domain,
                kind=str(raw.get("kind", "")).strip(),
                operations=total[object_id],
                ready_operations=ready[object_id],
                runtime_entrypoints=tuple(sorted(runtime[object_id])),
                runtime_metrics=tuple(sorted(runtime_metrics[object_id])),
            )
        )
    return sorted(surfaces, key=lambda item: item.object_id)


_GO_METRIC_OPTS = re.compile(
    r"prometheus\.(?:Counter|Gauge|Histogram|Summary)Opts\{(.*?)\n\s*\}", re.S
)
_PY_METRIC_CTOR = re.compile(
    r"\b(?:Counter|Gauge|Histogram|Summary)\(\s*\n?\s*\"([a-zA-Z_:][a-zA-Z0-9_:]*)\""
)


def _go_opts_field(block: str, key: str) -> str:
    match = re.search(rf'{key}:\s*"([^"]*)"', block)
    return match.group(1) if match else ""


def load_emitted_series(services_root: Path = SERVICES_ROOT) -> frozenset[str]:
    """现场扫描服务实现里真实注册的 Prometheus series 名（Go + Python）。

    这是「同名 series 是否存在」的唯一判据，每次运行重算，不落盘、不做 allowlist。
    """
    roots = [services_root]
    runtime_root = services_root.parent / "runtime"
    if runtime_root.is_dir():
        roots.append(runtime_root)
    emitted: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".go", ".py"}:
                continue
            if "/contracts/" in str(path):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if path.suffix == ".go":
                for block in _GO_METRIC_OPTS.findall(text):
                    name = _go_opts_field(block, "Name")
                    if not name:
                        continue
                    parts = (
                        _go_opts_field(block, "Namespace"),
                        _go_opts_field(block, "Subsystem"),
                        name,
                    )
                    emitted.add("_".join(part for part in parts if part))
            else:
                emitted.update(_PY_METRIC_CTOR.findall(text))
    return frozenset(emitted)
