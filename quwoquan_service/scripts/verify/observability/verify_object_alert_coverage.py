#!/usr/bin/env python3
"""校验全域 commercial-ready operation 的对象级告警与仪表盘覆盖。

判定口径（domain-agnostic，没有域分支、没有对象清单文件）：

* 业务真相源只有 `quwoquan_service/generated/contract_graph.json`；
  domain -> service 标签只从 `services/<service>/contracts/domain.yaml` 推导，运行分母再与
  canonical `docker-compose.gamma-local.yaml` 活跃 workload 求交。
* 每个 operation 必须声明 `telemetry.metric` 与数值化 `slo`。
* 每个 operation 必须有 `quwoquan_<domain>_contract_operation_requests_total` /
  `..._duration_seconds_bucket` 两条 recording rule，label 与 expr 由 ContractGraph
  的 method / pathTemplate / metric / commercial.status / slo 派生。
* 每个 `commercial.status == ready` 的 operation 的两个 record metric 都必须被
  真实 alerting rule 与 dashboard target 的 PromQL selector 消费（`operation` +
  `contract_metric` 正向匹配）。注释、annotation、panel description、legend 不计证据。
* 任何消费 `quwoquan_<domain>_contract_operation_*` 的 selector 都必须能匹配
  ContractGraph 中该域至少一个 operation，防止对象改名后留下死告警。
* `commercial.status != ready` 的 operation 按域输出「待商用」分类统计，不阻断。

对象分母是 ContractGraph 中活跃 workload 的全部 object，按契约面自动分类（不是
allowlist，新对象自动纳入）：

* `ready`：拥有 >=1 个 ready operation，必须满足上述全部 operation 级覆盖。
* `pending_commercial`：拥有 operation 但全部待商用，recording rule 仍然生成，翻 ready 即自动纳入告警。
* `runtime_surface_only`：不拥有任何 operation，但拥有 runtimeEntrypoint（projector /
  internal_port / subscription / middleware / external_port）。这类对象没有 HTTP
  operation，ContractGraph 也没有为 runtimeEntrypoint 声明 telemetry/slo，因此不存在
  可派生的 operation 级 SLO 告警口径；一旦 runtimeEntrypoint 声明 telemetry.metric，
  本门禁立即要求同等覆盖。
* 既无 operation 又无 runtimeEntrypoint 的对象没有任何契约面，直接 BLOCK。

`/internal/` 路径与 `principal: service` 的服务间 operation 不豁免，与面向 App 的
operation 使用同一套判定。

`telemetry.metric` 的语义在本仓已由既有事实裁定为**契约层逻辑标识（join key）**，不是
series 发射承诺：

* 唯一具备 SLO 形状的运行时指标是共享中间件注册的 `http_server_requests_total`
  `{service,route,method,status}` 与 `http_server_duration_seconds{service,route,method}`，
  既没有 per-operation series 名，也没有 `contract_metric` label。
* 声明名不遵守 Prometheus 指标类型后缀约定（`_total`/`_seconds`/...），而真实注册的
  series 绝大多数遵守；声明名在 PromQL 里只以 `contract_metric` label 值出现。

因此本门禁断言：声明名只能以 label 形式被消费。任何 PromQL（alerting expr / dashboard
target）把声明名放在 **series 位置**即 BLOCK，除非确实有服务注册了同名 series——同名
series 集合由 `load_emitted_series()` 每次运行从 Go `prometheus.*Opts` 与 Python
`Counter/Gauge/Histogram/Summary` 现场扫描得出，不是 allowlist。`summary` / `description`
等人类注解文本不是 PromQL，既不计覆盖证据也不触发 BLOCK。

recording rules、覆盖告警与覆盖仪表盘都由本脚本从 ContractGraph 生成（`--write`），
默认模式同时校验语义覆盖与生成产物漂移。
"""

from __future__ import annotations

import argparse
import collections
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable

import yaml

_BOOTSTRAP = next(
    path
    for path in Path(__file__).resolve().parents
    if (path / "repository_root.py").is_file()
)
sys.path.insert(0, str(_BOOTSTRAP))

from repository_root import repository_root  # noqa: E402

REPO_ROOT = repository_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.cli.lib.immutable_image_composition import first_party_service_names

CONTRACT_GRAPH = REPO_ROOT / "quwoquan_service/generated/contract_graph.json"
SERVICES_ROOT = REPO_ROOT / "quwoquan_service/services"
MONITORING_ROOT = REPO_ROOT / "quwoquan_ops/observability/monitoring"
ALERTS_ROOT = MONITORING_ROOT / "alerts"
DASHBOARDS_ROOT = MONITORING_ROOT / "dashboards"
PROMETHEUS_CONFIG = MONITORING_ROOT / "prometheus.yml"

SCRIPT_NAME = Path(__file__).name
RECORDING_RULE_DIR_SUFFIX = "_contract"
COVERAGE_ALERTS_NAME = "contract_object_coverage.yaml"
COVERAGE_DASHBOARD_NAME = "l2_contract_object_coverage.json"
COVERAGE_DASHBOARD_UID = "qwq-l2-contract-object-coverage"
PROMETHEUS_RULE_GLOB = "/etc/prometheus/rules/*_contract/*.yaml"
PROMETHEUS_COVERAGE_RULE = f"/etc/prometheus/rules/{COVERAGE_ALERTS_NAME}"

REQUEST_SOURCE_METRIC = "http_server_requests_total"
DURATION_SOURCE_METRIC = "http_server_duration_seconds_bucket"

GENERATED_HEADER = (
    "# Code generated from quwoquan_service/generated/contract_graph.json.\n"
    f"# Regenerate with {SCRIPT_NAME} --write.\n"
)

_PROMQL_SELECTOR_RE = re.compile(
    r"(?P<metric>[a-zA-Z_:][a-zA-Z0-9_:]*)\s*\{(?P<labels>[^{}]*)\}"
)
_PROMQL_LABEL_RE = re.compile(
    r'(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\s*'
    r'(?P<operator>=~|!~|=|!=)\s*"(?P<value>(?:\\.|[^"])*)"'
)
_PATH_PARAMETER_RE = re.compile(r"\{[^{} /]+\}")
_RECORD_METRIC_RE = re.compile(
    r"^quwoquan_(?P<domain>[a-z0-9_]+)_contract_operation_"
    r"(?P<dimension>requests_total|duration_seconds_bucket)$"
)


class ContractInputError(RuntimeError):
    """ContractGraph 或 domain.yaml 无法作为唯一真相源使用。"""


@dataclass(frozen=True)
class OperationContract:
    operation_id: str
    domain: str
    service: str
    object_name: str
    method: str
    path_template: str
    commercial_status: str
    block_reason: str
    metric: str
    latency_p95_ms: float
    availability_percent: float

    @property
    def ready(self) -> bool:
        return self.commercial_status == "ready"

    def record_labels(self) -> dict[str, str]:
        return {
            "service": self.service,
            "operation": self.operation_id,
            "contract_metric": self.metric,
            "commercial_status": self.commercial_status,
            "slo_latency_p95_ms": _number_label(self.latency_p95_ms),
            "slo_availability_percent": _number_label(self.availability_percent),
        }


@dataclass(frozen=True)
class RuleExpression:
    source: Path
    name: str
    expression: str
    record: str = ""
    alert: str = ""
    labels: dict[str, str] | None = None


OBJECT_SURFACE_READY = "ready"
OBJECT_SURFACE_PENDING = "pending_commercial"
OBJECT_SURFACE_RUNTIME_ONLY = "runtime_surface_only"
OBJECT_SURFACE_NONE = "no_contract_surface"


@dataclass(frozen=True)
class ObjectSurface:
    object_id: str
    domain: str
    kind: str
    operations: int
    ready_operations: int
    runtime_entrypoints: tuple[str, ...]
    runtime_metrics: tuple[str, ...]

    @property
    def classification(self) -> str:
        if self.ready_operations:
            return OBJECT_SURFACE_READY
        if self.operations:
            return OBJECT_SURFACE_PENDING
        if self.runtime_entrypoints:
            return OBJECT_SURFACE_RUNTIME_ONLY
        return OBJECT_SURFACE_NONE


@dataclass(frozen=True)
class DomainReport:
    domain: str
    service: str
    operations: int
    ready: int
    blocked_by_gap: tuple[tuple[str, int], ...]
    objects: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class VerificationReport:
    operations: int
    ready_operations: int
    domains: tuple[DomainReport, ...]
    object_surfaces: tuple[ObjectSurface, ...]
    issues: tuple[str, ...]
    declared_metrics: int = 0
    emitted_metrics: tuple[str, ...] = ()


def _number(value: Any, field: str, operation_id: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractInputError(f"{operation_id} 缺少数值 {field}")
    return float(value)


def _number_label(value: float) -> str:
    return str(int(value)) if value.is_integer() else format(value, "g")


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


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


def _verify_object_surfaces(
    surfaces: Iterable[ObjectSurface],
    consumers: Iterable[RuleExpression],
) -> list[str]:
    """对象级分母判定：没有任何契约面的对象直接阻断，runtime 声明 telemetry 即要求覆盖。"""
    materialized = list(consumers)
    issues: list[str] = []
    for surface in surfaces:
        if surface.classification == OBJECT_SURFACE_NONE:
            issues.append(
                f"{surface.domain}: 对象 {surface.object_id}（kind={surface.kind}）"
                "既没有 operation 也没有 runtimeEntrypoint，无法判定可观测覆盖；"
                "先在对象 operations.yaml 声明契约面"
            )
            continue
        # runtimeEntrypoint 一旦声明 telemetry.metric，就存在可判定的观测口径，
        # 必须被真实 PromQL 消费，不因为它不是 HTTP operation 而豁免。
        for metric in surface.runtime_metrics:
            if not any(
                re.search(rf"\b{re.escape(metric)}\b", consumer.expression)
                for consumer in materialized
            ):
                issues.append(
                    f"{surface.domain}: 对象 {surface.object_id} 的 runtimeEntrypoint "
                    f"telemetry.metric {metric!r} 未被 alert/dashboard PromQL 消费"
                )
    return issues


_GO_METRIC_OPTS = re.compile(
    r"prometheus\.(?:Counter|Gauge|Histogram|Summary)Opts\{(.*?)\n\s*\}", re.S
)
_PY_METRIC_CTOR = re.compile(
    r"\b(?:Counter|Gauge|Histogram|Summary)\(\s*\n?\s*\"([a-zA-Z_:][a-zA-Z0-9_:]*)\""
)
_LABEL_MATCHER_BLOCK = re.compile(r"\{[^{}]*\}")


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


def _verify_metric_identifier_semantics(
    operations: Iterable[OperationContract],
    consumers: Iterable[RuleExpression],
    emitted_series: frozenset[str],
) -> list[str]:
    """`telemetry.metric` 只允许作为 label 值被消费；放在 series 位置即 BLOCK。

    例外只有一条可判定规则：确实有服务注册了同名 series。没有 allowlist。
    """
    declared = {operation.metric: operation for operation in operations}
    if not declared:
        return []
    pattern = re.compile(
        r"(?<![A-Za-z0-9_])(" + "|".join(sorted(map(re.escape, declared), key=len, reverse=True)) + r")(?![A-Za-z0-9_])"
    )
    issues: list[str] = []
    for consumer in consumers:
        # 去掉 label matcher 块后剩下的就是 series / 函数位置。
        series_space = _LABEL_MATCHER_BLOCK.sub(" ", consumer.expression)
        for name in sorted(set(pattern.findall(series_space))):
            if name in emitted_series:
                continue
            operation = declared[name]
            issues.append(
                f"{consumer.source}: PromQL 把契约标识 {name!r} 当作 series 名消费，"
                f"但没有任何服务注册同名 series；{operation.operation_id} 的 telemetry.metric "
                "只能作为 contract_metric label 值使用"
            )
    return issues


def record_metric(domain: str, dimension: str) -> str:
    return f"quwoquan_{domain}_contract_operation_{dimension}"


def record_metrics(domain: str) -> tuple[str, str]:
    return (
        record_metric(domain, "requests_total"),
        record_metric(domain, "duration_seconds_bucket"),
    )


def _escape_promql_regex_literal(value: str) -> str:
    meta = frozenset(r"\.^$|?*+()[]")
    return "".join(f"\\{char}" if char in meta else char for char in value)


def route_matcher(path_template: str) -> str:
    if not _PATH_PARAMETER_RE.search(path_template):
        return f"route={json.dumps(path_template)}"

    parts: list[str] = ["^"]
    cursor = 0
    for match in _PATH_PARAMETER_RE.finditer(path_template):
        parts.append(_escape_promql_regex_literal(path_template[cursor : match.start()]))
        parts.append("[^/]+")
        cursor = match.end()
    parts.append(_escape_promql_regex_literal(path_template[cursor:]))
    parts.append("$")
    pattern = "".join(parts).replace("\\", "\\\\")
    return f'route=~"{pattern}"'


def source_expression(operation: OperationContract, record: str) -> str:
    selector = (
        f'service="{operation.service}",method="{operation.method}",'
        f"{route_matcher(operation.path_template)}"
    )
    request_metric, duration_metric = record_metrics(operation.domain)
    if record == request_metric:
        return f"sum by (status) ({REQUEST_SOURCE_METRIC}{{{selector}}})"
    if record == duration_metric:
        return f"sum by (le) ({DURATION_SOURCE_METRIC}{{{selector}}})"
    raise ContractInputError(f"未知 recording metric: {record}")


def domain_ready_selector(domain: str, service: str, extra: str = "") -> str:
    """域内 ready operation 的共享 selector；operation/contract_metric 正向匹配。"""
    parts = [
        f'service="{service}"',
        f'operation=~"{domain}\\\\..+"',
        f'contract_metric=~"{domain}_.+"',
        'commercial_status="ready"',
    ]
    if extra:
        parts.append(extra)
    return ",".join(parts)


def _group_name(operation: OperationContract) -> str:
    return re.sub(
        r"[^a-zA-Z0-9_]",
        "_",
        f"{operation.domain}{RECORDING_RULE_DIR_SUFFIX}_{operation.object_name}",
    )


def recording_rule_documents(
    operations: Iterable[OperationContract],
) -> dict[str, str]:
    """相对 alerts root 的 `<domain>_contract/<object>.yaml` -> 文件内容。"""
    by_object: dict[tuple[str, str], list[OperationContract]] = {}
    for operation in operations:
        by_object.setdefault((operation.domain, operation.object_name), []).append(operation)

    documents: dict[str, str] = {}
    for (domain, object_name), object_operations in sorted(by_object.items()):
        group = _group_name(object_operations[0])
        file_stem = re.sub(r"[^a-zA-Z0-9_]", "_", object_name)
        lines = [
            GENERATED_HEADER.rstrip("\n"),
            "groups:",
            f"  - name: quwoquan_{group}",
            "    rules:",
        ]
        for operation in sorted(object_operations, key=lambda item: item.operation_id):
            labels = operation.record_labels()
            for record in record_metrics(domain):
                lines.extend(
                    [
                        f"      - record: {record}",
                        "        expr: |",
                        f"          {source_expression(operation, record)}",
                        "        labels:",
                    ]
                )
                lines.extend(
                    f"          {name}: {_quoted(value)}" for name, value in labels.items()
                )
        documents[f"{domain}{RECORDING_RULE_DIR_SUFFIX}/{file_stem}.yaml"] = (
            "\n".join(lines) + "\n"
        )
    return documents


def _alert_name_domain(domain: str) -> str:
    return "".join(part.capitalize() for part in domain.split("_"))


def _threshold_label(value: float) -> str:
    return _number_label(value).replace(".", "p")


def coverage_alert_document(operations: Iterable[OperationContract]) -> str:
    """按 域 × SLO 档位 生成 ready operation 的可用性与延迟告警。"""
    ready = [operation for operation in operations if operation.ready]
    by_domain: dict[tuple[str, str], list[OperationContract]] = {}
    for operation in ready:
        by_domain.setdefault((operation.domain, operation.service), []).append(operation)

    lines = [
        GENERATED_HEADER.rstrip("\n"),
        "# 阈值来自 ContractGraph 的 slo.availabilityPercent / slo.latencyP95Milliseconds，",
        "# 每个域按 SLO 档位分组，selector 只消费 recording rule 的 operation/contract_metric label。",
        "groups:" if by_domain else "groups: []",
    ]
    for (domain, service), domain_operations in sorted(by_domain.items()):
        request_metric, duration_metric = record_metrics(domain)
        name_prefix = _alert_name_domain(domain)
        lines.append(f"  - name: quwoquan_{domain}_contract_object_coverage")
        lines.append("    rules:")
        availability_tiers = sorted(
            {operation.availability_percent for operation in domain_operations}
        )
        for tier in availability_tiers:
            budget = round((100.0 - tier) / 100.0, 6)
            selector = domain_ready_selector(
                domain, service, f'slo_availability_percent="{_number_label(tier)}"'
            )
            lines.extend(
                [
                    f"      - alert: {name_prefix}ContractOperationAvailabilityBelow"
                    f"{_threshold_label(tier)}Percent",
                    "        expr: |",
                    f'          sum(rate({request_metric}{{{selector},status=~"5.."}}[10m]))'
                    " by (operation, contract_metric)",
                    f"          / clamp_min(sum(rate({request_metric}{{{selector}}}[10m]))"
                    f" by (operation, contract_metric), 0.001) > {budget:g}",
                    "        for: 10m",
                    "        labels:",
                    "          severity: critical",
                    "          layer: l2",
                    f"          domain: {domain}",
                    "        annotations:",
                    f'          summary: "{domain} ready operation 5xx 比率超出可用性 SLO'
                    f'（{_number_label(tier)}%）"',
                    '          description: "{{ $labels.operation }}'
                    f"（{{{{ $labels.contract_metric }}}}）5xx 比率 "
                    '{{ $value | humanizePercentage }} 超出 ContractGraph 声明的可用性 SLO；'
                    '按对象 owner 检查依赖、鉴权与存储链路。"',
                ]
            )
        latency_tiers = sorted({operation.latency_p95_ms for operation in domain_operations})
        for tier in latency_tiers:
            selector = domain_ready_selector(
                domain, service, f'slo_latency_p95_ms="{_number_label(tier)}"'
            )
            lines.extend(
                [
                    f"      - alert: {name_prefix}ContractOperationLatencyP95Above"
                    f"{_threshold_label(tier)}Ms",
                    "        expr: |",
                    "          histogram_quantile(0.95,",
                    f"            sum(rate({duration_metric}{{{selector}}}[5m]))"
                    " by (le, operation, contract_metric)",
                    f"          ) > {tier / 1000:g}",
                    "        for: 5m",
                    "        labels:",
                    "          severity: warning",
                    "          layer: l2",
                    f"          domain: {domain}",
                    "        annotations:",
                    f'          summary: "{domain} ready operation P95 超出 SLO'
                    f'（{_number_label(tier)}ms）"',
                    '          description: "{{ $labels.operation }}'
                    f"（{{{{ $labels.contract_metric }}}}）P95 = "
                    '{{ $value | humanizeDuration }} 超出 ContractGraph 声明的 '
                    f'slo.latencyP95Milliseconds={_number_label(tier)}。"',
                ]
            )
    return "\n".join(lines) + "\n"


def coverage_dashboard_document(operations: Iterable[OperationContract]) -> str:
    ready = [operation for operation in operations if operation.ready]
    domains = sorted({(operation.domain, operation.service) for operation in ready})
    panels: list[dict[str, Any]] = []
    for index, (domain, service) in enumerate(domains):
        request_metric, duration_metric = record_metrics(domain)
        selector = domain_ready_selector(domain, service)
        panels.append(
            {
                "title": f"{domain} ready operation 5xx 错误率",
                "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": index * 8},
                "targets": [
                    {
                        "expr": (
                            f'sum(rate({request_metric}{{{selector},status=~"5.."}}[5m]))'
                            " by (operation, contract_metric)"
                            f" / clamp_min(sum(rate({request_metric}{{{selector}}}[5m]))"
                            " by (operation, contract_metric), 0.001)"
                        ),
                        "legendFormat": "{{ operation }}",
                    }
                ],
            }
        )
        panels.append(
            {
                "title": f"{domain} ready operation P95 延迟",
                "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": index * 8},
                "targets": [
                    {
                        "expr": (
                            "histogram_quantile(0.95, sum(rate("
                            f"{duration_metric}{{{selector}}}[5m]))"
                            " by (le, operation, contract_metric, slo_latency_p95_ms))"
                        ),
                        "legendFormat": "{{ operation }}",
                    }
                ],
            }
        )
    dashboard = {
        "dashboard": {
            "title": "L2 — 契约对象 ready operation 覆盖",
            "uid": COVERAGE_DASHBOARD_UID,
            "tags": ["quwoquan", "l2", "contract-graph", "generated"],
            "timezone": "browser",
            "refresh": "30s",
            "description": (
                "Code generated from quwoquan_service/generated/contract_graph.json；"
                f"regenerate with {SCRIPT_NAME} --write。"
                "每域 ready operation 的可用性与 P95 由对象级 recording rule 派生。"
            ),
            "panels": panels,
        }
    }
    return json.dumps(dashboard, ensure_ascii=False, indent=2) + "\n"


def generated_documents(
    operations: Iterable[OperationContract],
    alerts_root: Path = ALERTS_ROOT,
    dashboards_root: Path = DASHBOARDS_ROOT,
) -> dict[Path, str]:
    materialized = list(operations)
    documents: dict[Path, str] = {
        alerts_root / relative: content
        for relative, content in recording_rule_documents(materialized).items()
    }
    documents[alerts_root / COVERAGE_ALERTS_NAME] = coverage_alert_document(materialized)
    documents[dashboards_root / COVERAGE_DASHBOARD_NAME] = coverage_dashboard_document(
        materialized
    )
    return documents


def _recording_rule_files(alerts_root: Path) -> list[Path]:
    files: list[Path] = []
    for directory in sorted(alerts_root.glob(f"*{RECORDING_RULE_DIR_SUFFIX}")):
        if not directory.is_dir():
            continue
        files.extend(sorted(directory.glob("*.yaml")))
        files.extend(sorted(directory.glob("*.yml")))
    return files


def write_generated_documents(
    operations: Iterable[OperationContract],
    alerts_root: Path = ALERTS_ROOT,
    dashboards_root: Path = DASHBOARDS_ROOT,
) -> int:
    documents = generated_documents(operations, alerts_root, dashboards_root)
    expected = set(documents)
    for path in documents:
        path.parent.mkdir(parents=True, exist_ok=True)
    for stale in _recording_rule_files(alerts_root):
        if stale not in expected:
            stale.unlink()
    for path, content in sorted(documents.items()):
        path.write_text(content, encoding="utf-8")
    return len(documents)


def _drift_issues(
    operations: Iterable[OperationContract],
    alerts_root: Path,
    dashboards_root: Path,
) -> list[str]:
    documents = generated_documents(operations, alerts_root, dashboards_root)
    issues: list[str] = []
    for path, content in sorted(documents.items()):
        relative = _display_path(path)
        if not path.exists():
            issues.append(f"{relative}: 缺少 ContractGraph 派生产物，执行 {SCRIPT_NAME} --write")
            continue
        if path.read_text(encoding="utf-8") != content:
            issues.append(f"{relative}: 与 ContractGraph 派生结果漂移，执行 {SCRIPT_NAME} --write")
    expected = set(documents)
    for existing in _recording_rule_files(alerts_root):
        if existing not in expected:
            issues.append(
                f"{_display_path(existing)}: 不属于任何 ContractGraph 对象，"
                f"执行 {SCRIPT_NAME} --write"
            )
    return issues


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load_alert_expressions(root: Path) -> tuple[list[RuleExpression], list[str]]:
    expressions: list[RuleExpression] = []
    issues: list[str] = []
    for path in sorted(root.rglob("*.yaml")) + sorted(root.rglob("*.yml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            issues.append(f"{path}: YAML 无法解析: {error}")
            continue
        groups = document.get("groups") if isinstance(document, dict) else None
        if not isinstance(groups, list):
            issues.append(f"{path}: 缺少 Prometheus groups")
            continue
        for group in groups:
            rules = group.get("rules") if isinstance(group, dict) else None
            if not isinstance(rules, list):
                issues.append(f"{path}: group.rules 必须是数组")
                continue
            for index, rule in enumerate(rules):
                if not isinstance(rule, dict) or not isinstance(rule.get("expr"), str):
                    continue
                labels = rule.get("labels")
                expressions.append(
                    RuleExpression(
                        source=path,
                        name=str(rule.get("alert") or rule.get("record") or index),
                        expression=rule["expr"],
                        record=str(rule.get("record", "")),
                        alert=str(rule.get("alert", "")),
                        labels={str(key): str(value) for key, value in labels.items()}
                        if isinstance(labels, dict)
                        else {},
                    )
                )
    return expressions, issues


def _walk_dashboard_expressions(value: Any) -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        title = str(value.get("title", "dashboard"))
        targets = value.get("targets")
        if isinstance(targets, list):
            for index, target in enumerate(targets):
                if isinstance(target, dict) and isinstance(target.get("expr"), str):
                    yield f"{title}[{index}]", target["expr"]
        for child in value.values():
            yield from _walk_dashboard_expressions(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dashboard_expressions(child)


def _load_dashboard_expressions(root: Path) -> tuple[list[RuleExpression], list[str]]:
    expressions: list[RuleExpression] = []
    issues: list[str] = []
    for path in sorted(root.rglob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            issues.append(f"{path}: dashboard JSON 无法解析: {error}")
            continue
        expressions.extend(
            RuleExpression(source=path, name=name, expression=expression)
            for name, expression in _walk_dashboard_expressions(document)
        )
    return expressions, issues


def _decode_promql_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value.replace(r"\\", "\\").replace(r"\"", '"')


def _selector_labels(expression: str, metric: str) -> Iterable[dict[str, tuple[str, str]]]:
    for selector in _PROMQL_SELECTOR_RE.finditer(expression):
        if selector.group("metric") != metric:
            continue
        labels: dict[str, tuple[str, str]] = {}
        for matcher in _PROMQL_LABEL_RE.finditer(selector.group("labels")):
            labels[matcher.group("name")] = (
                matcher.group("operator"),
                _decode_promql_string(matcher.group("value")),
            )
        yield labels


def _record_metric_selectors(expression: str) -> Iterable[tuple[str, str, dict[str, tuple[str, str]]]]:
    """产出 (domain, metric, labels)，只覆盖契约 operation record metric family。"""
    for selector in _PROMQL_SELECTOR_RE.finditer(expression):
        metric = selector.group("metric")
        match = _RECORD_METRIC_RE.match(metric)
        if match is None:
            continue
        labels: dict[str, tuple[str, str]] = {}
        for matcher in _PROMQL_LABEL_RE.finditer(selector.group("labels")):
            labels[matcher.group("name")] = (
                matcher.group("operator"),
                _decode_promql_string(matcher.group("value")),
            )
        yield match.group("domain"), metric, labels


def _matcher_accepts(operator: str, expected: str, actual: str) -> bool:
    if operator == "=":
        return actual == expected
    if operator == "!=":
        return actual != expected
    try:
        matches = re.fullmatch(expected, actual) is not None
    except re.error:
        return False
    return matches if operator == "=~" else not matches


def _expression_covers(expression: str, metric: str, operation: OperationContract) -> bool:
    actual = {
        "service": operation.service,
        "operation": operation.operation_id,
        "contract_metric": operation.metric,
        "commercial_status": operation.commercial_status,
        "slo_latency_p95_ms": _number_label(operation.latency_p95_ms),
        "slo_availability_percent": _number_label(operation.availability_percent),
    }
    for labels in _selector_labels(expression, metric):
        positive = {name for name, (operator, _) in labels.items() if operator in {"=", "=~"}}
        if not {"operation", "contract_metric"}.issubset(positive):
            continue
        if all(
            name not in labels or _matcher_accepts(labels[name][0], labels[name][1], value)
            for name, value in actual.items()
        ):
            return True
    return False


def _verify_consumer_selectors(
    operations: Iterable[OperationContract],
    expressions: Iterable[RuleExpression],
    domain_services: dict[str, str],
) -> list[str]:
    by_domain: dict[str, list[str]] = collections.defaultdict(list)
    for operation in operations:
        by_domain[operation.domain].append(operation.operation_id)

    issues: list[str] = []
    for expression in expressions:
        for domain, metric, labels in _record_metric_selectors(expression.expression):
            source = f"{_display_path(expression.source)}#{expression.name}"
            if domain not in domain_services:
                issues.append(
                    f"{source}: {metric} 的 domain {domain!r} 没有服务 contracts/domain.yaml 归属"
                )
                continue
            operation_matcher = labels.get("operation")
            if operation_matcher is None:
                continue
            operator, expected = operation_matcher
            if operator not in {"=", "=~"}:
                continue
            if any(
                _matcher_accepts(operator, expected, operation_id)
                for operation_id in by_domain[domain]
            ):
                continue
            issues.append(
                f"{source}: {metric} 的 operation selector {operator}{expected!r} "
                f"不匹配 ContractGraph 中任何 {domain} operation"
            )
    return issues


def _verify_recording_rules(
    operations: Iterable[OperationContract],
    expressions: Iterable[RuleExpression],
) -> tuple[set[tuple[str, str]], list[str]]:
    by_id = {operation.operation_id: operation for operation in operations}
    mapped: set[tuple[str, str]] = set()
    issues: list[str] = []
    for rule in expressions:
        if _RECORD_METRIC_RE.match(rule.record) is None:
            continue
        source = f"{_display_path(rule.source)}#{rule.name}"
        labels = rule.labels or {}
        operation_id = labels.get("operation", "")
        operation = by_id.get(operation_id)
        if operation is None:
            issues.append(f"{source}: 未知 ContractGraph operation {operation_id!r}")
            continue
        if rule.record not in record_metrics(operation.domain):
            issues.append(
                f"{source}: {operation_id} 属于 {operation.domain} 域，"
                f"不应记录到 {rule.record}"
            )
            continue
        key = (operation_id, rule.record)
        if key in mapped:
            issues.append(f"{source}: {operation_id} 的 {rule.record} 重复映射")
            continue
        mapped.add(key)
        for name, expected in operation.record_labels().items():
            if labels.get(name) != expected:
                issues.append(
                    f"{source}: {operation_id} label {name}={labels.get(name)!r}，"
                    f"ContractGraph 要求 {expected!r}"
                )
        if " ".join(rule.expression.split()) != " ".join(
            source_expression(operation, rule.record).split()
        ):
            issues.append(
                f"{source}: {operation_id} 未按 method/pathTemplate 消费 "
                f"{REQUEST_SOURCE_METRIC if rule.record.endswith('requests_total') else DURATION_SOURCE_METRIC}"
            )
    return mapped, issues


def _verify_prometheus_rule_files(config: Path) -> list[str]:
    if not config.exists():
        return [f"{_display_path(config)}: 缺少 Prometheus 配置"]
    try:
        document = yaml.safe_load(config.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        return [f"{_display_path(config)}: 无法解析: {error}"]
    rule_files = (document or {}).get("rule_files")
    if not isinstance(rule_files, list):
        return [f"{_display_path(config)}: 缺少 rule_files"]
    issues: list[str] = []
    for required in (PROMETHEUS_RULE_GLOB, PROMETHEUS_COVERAGE_RULE):
        if required not in rule_files:
            issues.append(
                f"{_display_path(config)}: rule_files 缺少 {required}，"
                "生成的对象级规则不会被 Prometheus 加载"
            )
    return issues


def _domain_reports(
    operations: Iterable[OperationContract],
    surfaces: Iterable[ObjectSurface],
    domain_services: dict[str, str],
) -> tuple[DomainReport, ...]:
    grouped: dict[str, list[OperationContract]] = collections.defaultdict(list)
    for operation in operations:
        grouped[operation.domain].append(operation)
    by_domain_objects: dict[str, collections.Counter[str]] = collections.defaultdict(
        collections.Counter
    )
    for surface in surfaces:
        by_domain_objects[surface.domain][surface.classification] += 1

    reports: list[DomainReport] = []
    for domain in sorted(set(grouped) | set(by_domain_objects)):
        domain_operations = grouped[domain]
        blocked = collections.Counter(
            operation.block_reason or "UNCLASSIFIED"
            for operation in domain_operations
            if not operation.ready
        )
        reports.append(
            DomainReport(
                domain=domain,
                service=domain_services.get(domain, "-"),
                operations=len(domain_operations),
                ready=sum(1 for operation in domain_operations if operation.ready),
                blocked_by_gap=tuple(sorted(blocked.items())),
                objects=tuple(sorted(by_domain_objects[domain].items())),
            )
        )
    return tuple(reports)


def verify_coverage(
    contract_graph: Path = CONTRACT_GRAPH,
    alerts_root: Path = ALERTS_ROOT,
    dashboards_root: Path = DASHBOARDS_ROOT,
    services_root: Path = SERVICES_ROOT,
    prometheus_config: Path | None = PROMETHEUS_CONFIG,
    check_drift: bool = True,
) -> VerificationReport:
    try:
        domain_services = load_domain_services(services_root)
        operations = load_operations(contract_graph, domain_services)
        surfaces = load_object_surfaces(contract_graph, domain_services)
        runtime_services = runtime_domain_services(domain_services, services_root)
        operations = [
            operation
            for operation in operations
            if operation.service in runtime_services.values()
        ]
        surfaces = [
            surface for surface in surfaces if surface.domain in runtime_services
        ]
    except ContractInputError as error:
        return VerificationReport(0, 0, (), (), (f"ContractGraph 无法使用: {error}",))

    issues: list[str] = []
    alert_expressions, alert_issues = _load_alert_expressions(alerts_root)
    dashboard_expressions, dashboard_issues = _load_dashboard_expressions(dashboards_root)
    issues.extend(alert_issues)
    issues.extend(dashboard_issues)

    mapped, mapping_issues = _verify_recording_rules(operations, alert_expressions)
    issues.extend(mapping_issues)

    consumers = [
        expression
        for expression in alert_expressions + dashboard_expressions
        if not expression.record
    ]
    issues.extend(_verify_consumer_selectors(operations, consumers, runtime_services))
    issues.extend(_verify_object_surfaces(surfaces, consumers))
    emitted_series = load_emitted_series(services_root)
    declared_metrics = {operation.metric for operation in operations}
    issues.extend(
        _verify_metric_identifier_semantics(operations, consumers, emitted_series)
    )

    alerting = [expression for expression in alert_expressions if expression.alert]
    dashboards = list(dashboard_expressions)
    ready = [operation for operation in operations if operation.ready]
    for operation in ready:
        request_metric, duration_metric = record_metrics(operation.domain)
        for record, dimension in (
            (request_metric, "availability"),
            (duration_metric, "latency_p95"),
        ):
            if (operation.operation_id, record) not in mapped:
                issues.append(
                    f"{operation.domain}: {operation.operation_id} ({operation.metric}) "
                    f"缺少 {dimension} recording rule"
                )
                continue
            if not any(
                _expression_covers(consumer.expression, record, operation)
                for consumer in alerting
            ):
                issues.append(
                    f"{operation.domain}: {operation.operation_id} ({operation.metric}) 的 "
                    f"{dimension} 未被 alerting rule PromQL 消费"
                )
            if not any(
                _expression_covers(consumer.expression, record, operation)
                for consumer in dashboards
            ):
                issues.append(
                    f"{operation.domain}: {operation.operation_id} ({operation.metric}) 的 "
                    f"{dimension} 未被 dashboard PromQL 消费"
                )

    if check_drift:
        issues.extend(_drift_issues(operations, alerts_root, dashboards_root))
    if prometheus_config is not None:
        issues.extend(_verify_prometheus_rule_files(prometheus_config))

    return VerificationReport(
        operations=len(operations),
        ready_operations=len(ready),
        domains=_domain_reports(operations, surfaces, runtime_services),
        object_surfaces=tuple(surfaces),
        issues=tuple(issues),
        declared_metrics=len(declared_metrics),
        emitted_metrics=tuple(sorted(declared_metrics & emitted_series)),
    )


def _print_report(report: VerificationReport) -> None:
    surfaces = collections.Counter(surface.classification for surface in report.object_surfaces)
    print(
        f"[object-alert-coverage] objects={len(report.object_surfaces)} "
        f"operations={report.operations} ready={report.ready_operations} "
        f"domains={len(report.domains)}"
    )
    orphans = report.declared_metrics - len(report.emitted_metrics)
    print(
        f"  telemetry.metric 语义=契约层逻辑标识（只作 contract_metric label 消费）: "
        f"declared={report.declared_metrics} 同名 series 实际存在="
        f"{len(report.emitted_metrics)} 仅逻辑标识={orphans}"
    )
    if report.emitted_metrics:
        print("    同名 series: " + ", ".join(report.emitted_metrics))
    print(
        "  对象契约面: "
        + ", ".join(
            f"{name}={surfaces[name]}"
            for name in (
                OBJECT_SURFACE_READY,
                OBJECT_SURFACE_PENDING,
                OBJECT_SURFACE_RUNTIME_ONLY,
                OBJECT_SURFACE_NONE,
            )
        )
    )
    for domain in report.domains:
        pending = sum(count for _, count in domain.blocked_by_gap)
        objects = ", ".join(f"{name}:{count}" for name, count in domain.objects)
        detail = (
            " 待商用=" + ", ".join(f"{gap}:{count}" for gap, count in domain.blocked_by_gap)
            if domain.blocked_by_gap
            else ""
        )
        print(
            f"  - {domain.domain} ({domain.service}): objects[{objects}] "
            f"operations={domain.operations} ready={domain.ready} pending={pending}{detail}"
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-graph", type=Path, default=CONTRACT_GRAPH)
    parser.add_argument("--alerts-root", type=Path, default=ALERTS_ROOT)
    parser.add_argument("--dashboards-root", type=Path, default=DASHBOARDS_ROOT)
    parser.add_argument("--services-root", type=Path, default=SERVICES_ROOT)
    parser.add_argument(
        "--write",
        action="store_true",
        help="从 ContractGraph 重建对象级 recording rules、覆盖告警与覆盖仪表盘",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.write:
        try:
            domain_services = load_domain_services(args.services_root)
            operations = load_operations(args.contract_graph, domain_services)
            runtime_services = runtime_domain_services(
                domain_services, args.services_root
            )
            operations = [
                operation
                for operation in operations
                if operation.service in runtime_services.values()
            ]
            count = write_generated_documents(
                operations, args.alerts_root, args.dashboards_root
            )
        except ContractInputError as error:
            print(f"[object-alert-coverage] BLOCK: {error}", file=sys.stderr)
            return 1
        print(f"[object-alert-coverage] 生成 {count} 份 ContractGraph 派生产物")
        return 0

    report = verify_coverage(
        contract_graph=args.contract_graph,
        alerts_root=args.alerts_root,
        dashboards_root=args.dashboards_root,
        services_root=args.services_root,
    )
    _print_report(report)
    if report.issues:
        print(
            "[object-alert-coverage] FAIL: ready operation 对象级告警覆盖不完整 "
            f"({len(report.issues)} 项)",
            file=sys.stderr,
        )
        for issue in report.issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    print("[object-alert-coverage] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
