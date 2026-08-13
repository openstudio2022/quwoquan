"""ContractGraph 派生产物：recording rules、覆盖告警、覆盖仪表盘与漂移检测。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from .constants import (
    ALERTS_ROOT,
    COVERAGE_ALERTS_NAME,
    COVERAGE_DASHBOARD_NAME,
    COVERAGE_DASHBOARD_UID,
    DASHBOARDS_ROOT,
    DURATION_SOURCE_METRIC,
    GENERATED_HEADER,
    RECORDING_RULE_DIR_SUFFIX,
    REQUEST_SOURCE_METRIC,
    SCRIPT_NAME,
    _PATH_PARAMETER_RE,
    _display_path,
    _number_label,
    _quoted,
)
from .models import ContractInputError, OperationContract


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
    # Grafana file provisioning 直接消费 dashboard model（bare 顶层），
    # 不使用 API 响应形状的 {"dashboard": ...} 包装。
    dashboard = {
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
