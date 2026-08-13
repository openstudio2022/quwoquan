"""对象级告警与仪表盘覆盖的语义判定主流程。"""

from __future__ import annotations

import collections
import re
from pathlib import Path
from typing import Iterable

import yaml

from .constants import (
    ALERTS_ROOT,
    CONTRACT_GRAPH,
    DASHBOARDS_ROOT,
    DURATION_SOURCE_METRIC,
    PROMETHEUS_CONFIG,
    PROMETHEUS_COVERAGE_RULE,
    PROMETHEUS_RULE_GLOB,
    REQUEST_SOURCE_METRIC,
    SERVICES_ROOT,
    _RECORD_METRIC_RE,
    _display_path,
    _number_label,
)
from .contract_inputs import (
    load_domain_services,
    load_emitted_series,
    load_object_surfaces,
    load_operations,
    runtime_domain_services,
)
from .generated_docs import _drift_issues, record_metrics, source_expression
from .models import (
    ContractInputError,
    DomainReport,
    ObjectSurface,
    OperationContract,
    OBJECT_SURFACE_NONE,
    RuleExpression,
    VerificationReport,
)
from .promql import (
    _LABEL_MATCHER_BLOCK,
    _load_alert_expressions,
    _load_dashboard_expressions,
    _matcher_accepts,
    _record_metric_selectors,
    _selector_labels,
)


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
