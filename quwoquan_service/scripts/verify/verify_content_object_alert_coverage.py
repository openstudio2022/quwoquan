#!/usr/bin/env python3
"""校验 content commercial-ready operation 的对象级可观测覆盖。
唯一业务输入是 generated/contract_graph.json，不维护 route allowlist 或读取业务 YAML。
门禁核对 telemetry.metric/SLO、HTTP recording rule 以及 alert/dashboard PromQL。
注释、annotation、panel description 和 legend 文本都不计覆盖证据。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_GRAPH = REPO_ROOT / "quwoquan_service/generated/contract_graph.json"
ALERTS_ROOT = REPO_ROOT / "quwoquan_ops/observability/monitoring/alerts"
DASHBOARDS_ROOT = REPO_ROOT / "quwoquan_ops/observability/monitoring/dashboards"
MAPPING_ROOT = ALERTS_ROOT / "content_contract"

REQUEST_SOURCE_METRIC = "http_server_requests_total"
DURATION_SOURCE_METRIC = "http_server_duration_seconds_bucket"
REQUEST_RECORD_METRIC = "quwoquan_content_contract_operation_requests_total"
DURATION_RECORD_METRIC = "quwoquan_content_contract_operation_duration_seconds_bucket"

_PROMQL_SELECTOR_RE = re.compile(
    r"(?P<metric>[a-zA-Z_:][a-zA-Z0-9_:]*)\s*"
    r"\{(?P<labels>[^{}]*)\}"
)
_PROMQL_LABEL_RE = re.compile(
    r'(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\s*'
    r'(?P<operator>=~|!~|=|!=)\s*"(?P<value>(?:\\.|[^"])*)"'
)
_PATH_PARAMETER_RE = re.compile(r"\{[^{} /]+\}")

@dataclass(frozen=True)
class OperationContract:
    operation_id: str
    object_id: str
    method: str
    path_template: str
    commercial_status: str
    metric: str
    latency_p95_ms: float
    availability_percent: float

@dataclass(frozen=True)
class RuleExpression:
    source: Path
    name: str
    expression: str
    record: str = ""
    labels: dict[str, str] | None = None

@dataclass(frozen=True)
class VerificationReport:
    content_operations: int
    ready_operations: int
    issues: tuple[str, ...]

def _number(value: Any, field: str, operation_id: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{operation_id} 缺少数值 {field}")
    return float(value)

def _number_label(value: float) -> str:
    return str(int(value)) if value.is_integer() else format(value, "g")

def load_content_operations(path: Path) -> list[OperationContract]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    operations = payload.get("operations")
    if not isinstance(operations, list):
        raise ValueError("ContractGraph.operations 必须是数组")

    result: list[OperationContract] = []
    for raw in operations:
        if not isinstance(raw, dict) or raw.get("domain") != "content":
            continue
        operation_id = str(raw.get("id", "")).strip()
        commercial = raw.get("commercial")
        telemetry = raw.get("telemetry")
        slo = raw.get("slo")
        if not operation_id:
            raise ValueError("content operation 缺少 id")
        if not isinstance(commercial, dict):
            raise ValueError(f"{operation_id} 缺少 commercial")
        status = str(commercial.get("status", "")).strip()
        if not isinstance(telemetry, dict):
            raise ValueError(f"{operation_id} 缺少 telemetry")
        metric = str(telemetry.get("metric", "")).strip()
        if not metric:
            raise ValueError(f"{operation_id} 缺少 telemetry.metric")
        if not isinstance(slo, dict):
            raise ValueError(f"{operation_id} 缺少 slo")
        result.append(
            OperationContract(
                operation_id=operation_id,
                object_id=str(raw.get("objectId", "")).strip(),
                method=str(raw.get("method", "")).strip().upper(),
                path_template=str(raw.get("pathTemplate", "")).strip(),
                commercial_status=status,
                metric=metric,
                latency_p95_ms=_number(
                    slo.get("latencyP95Milliseconds"), "slo.latencyP95Milliseconds", operation_id
                ),
                availability_percent=_number(
                    slo.get("availabilityPercent"), "slo.availabilityPercent", operation_id
                ),
            )
        )
    return sorted(result, key=lambda item: item.operation_id)

def _escape_promql_regex_literal(value: str) -> str:
    meta = frozenset(r"\.^$|?*+()[]")
    return "".join(f"\\{char}" if char in meta else char for char in value)

def route_matcher(path_template: str) -> str:
    if not _PATH_PARAMETER_RE.search(path_template):
        return f'route={json.dumps(path_template)}'

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
        f'service="content-service",method="{operation.method}",'
        f"{route_matcher(operation.path_template)}"
    )
    if record == REQUEST_RECORD_METRIC:
        return f"sum by (status) ({REQUEST_SOURCE_METRIC}{{{selector}}})"
    if record == DURATION_RECORD_METRIC:
        return f"sum by (le) ({DURATION_SOURCE_METRIC}{{{selector}}})"
    raise ValueError(f"未知 recording metric: {record}")

def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)

def render_recording_rule_documents(operations: Iterable[OperationContract]) -> dict[str, str]:
    by_object: dict[str, list[OperationContract]] = {}
    for operation in operations:
        object_name = operation.object_id.removeprefix("content.") or "unknown"
        by_object.setdefault(object_name, []).append(operation)

    documents: dict[str, str] = {}
    for object_name, object_operations in sorted(by_object.items()):
        group_name = re.sub(r"[^a-zA-Z0-9_]", "_", object_name)
        lines = [
            "# Code generated from quwoquan_service/generated/contract_graph.json.",
            "# Regenerate with verify_content_object_alert_coverage.py "
            "--write-recording-rules.",
            "groups:",
            f"  - name: quwoquan_content_contract_{group_name}",
            "    rules:",
        ]
        for operation in sorted(
            object_operations, key=lambda item: item.operation_id
        ):
            labels = {
                "service": "content-service",
                "operation": operation.operation_id,
                "contract_metric": operation.metric,
                "commercial_status": operation.commercial_status,
                "slo_latency_p95_ms": _number_label(operation.latency_p95_ms),
                "slo_availability_percent": _number_label(
                    operation.availability_percent
                ),
            }
            for record in (REQUEST_RECORD_METRIC, DURATION_RECORD_METRIC):
                lines.extend(
                    [
                        f"      - record: {record}",
                        "        expr: |",
                        f"          {source_expression(operation, record)}",
                        "        labels:",
                    ]
                )
                lines.extend(
                    f"          {name}: {_quoted(value)}"
                    for name, value in labels.items()
                )
        documents[f"{group_name}.yaml"] = "\n".join(lines) + "\n"
    return documents

def write_recording_rule_files(
    operations: Iterable[OperationContract], output_root: Path
) -> int:
    documents = render_recording_rule_documents(operations)
    output_root.mkdir(parents=True, exist_ok=True)
    expected = set(documents)
    for path in tuple(output_root.glob("*.yaml")) + tuple(output_root.glob("*.yml")):
        if path.name not in expected:
            path.unlink()
    for name, content in documents.items():
        (output_root / name).write_text(content, encoding="utf-8")
    return len(documents)

def _load_alert_expressions(root: Path) -> tuple[list[RuleExpression], list[str]]:
    expressions: list[RuleExpression] = []
    issues: list[str] = []
    paths = sorted(root.rglob("*.yaml")) + sorted(root.rglob("*.yml"))
    for path in paths:
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
                        labels={
                            str(key): str(value)
                            for key, value in labels.items()
                        }
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

def _expression_covers(
    expression: str,
    metric: str,
    operation: OperationContract,
) -> bool:
    actual = {
        "service": "content-service",
        "operation": operation.operation_id,
        "contract_metric": operation.metric,
        "commercial_status": operation.commercial_status,
    }
    for labels in _selector_labels(expression, metric):
        positive = {
            name
            for name, (operator, _) in labels.items()
            if operator in {"=", "=~"}
        }
        if not {"operation", "contract_metric"}.issubset(positive):
            continue
        if all(
            name not in labels
            or _matcher_accepts(labels[name][0], labels[name][1], value)
            for name, value in actual.items()
        ):
            return True
    return False

def _verify_consumer_operation_selectors(
    operations: Iterable[OperationContract],
    expressions: Iterable[RuleExpression],
) -> list[str]:
    operation_ids = tuple(operation.operation_id for operation in operations)
    issues: list[str] = []
    for expression in expressions:
        for metric in (REQUEST_RECORD_METRIC, DURATION_RECORD_METRIC):
            for labels in _selector_labels(expression.expression, metric):
                operation_matcher = labels.get("operation")
                if operation_matcher is None:
                    continue
                operator, expected = operation_matcher
                if operator not in {"=", "=~"}:
                    continue
                if any(
                    _matcher_accepts(operator, expected, operation_id)
                    for operation_id in operation_ids
                ):
                    continue
                issues.append(
                    f"{expression.source}#{expression.name}: {metric} 的 operation "
                    f"selector {operator}{expected!r} 不匹配 ContractGraph 中任何 "
                    "content operation"
                )
    return issues

def _verify_recording_rules(
    operations: list[OperationContract],
    expressions: list[RuleExpression],
) -> tuple[dict[tuple[str, str], RuleExpression], list[str]]:
    by_id = {operation.operation_id: operation for operation in operations}
    mappings: dict[tuple[str, str], RuleExpression] = {}
    issues: list[str] = []
    expected_records = {REQUEST_RECORD_METRIC, DURATION_RECORD_METRIC}
    for rule in expressions:
        if rule.record not in expected_records:
            continue
        labels = rule.labels or {}
        operation_id = labels.get("operation", "")
        operation = by_id.get(operation_id)
        if operation is None:
            issues.append(
                f"{rule.source}#{rule.name}: 未知 content operation {operation_id!r}"
            )
            continue
        key = (operation_id, rule.record)
        if key in mappings:
            issues.append(
                f"{rule.source}#{rule.name}: {operation_id} 的 {rule.record} 重复映射"
            )
            continue
        mappings[key] = rule
        expected_labels = {
            "service": "content-service",
            "operation": operation.operation_id,
            "contract_metric": operation.metric,
            "commercial_status": operation.commercial_status,
            "slo_latency_p95_ms": _number_label(operation.latency_p95_ms),
            "slo_availability_percent": _number_label(
                operation.availability_percent
            ),
        }
        for name, expected in expected_labels.items():
            if labels.get(name) != expected:
                issues.append(
                    f"{rule.source}#{rule.name}: {operation_id} label {name}="
                    f"{labels.get(name)!r}，ContractGraph 要求 {expected!r}"
                )
        if " ".join(rule.expression.split()) != " ".join(
            source_expression(operation, rule.record).split()
        ):
            issues.append(
                f"{rule.source}#{rule.name}: {operation_id} 未按 method/pathTemplate "
                f"消费 {REQUEST_SOURCE_METRIC if rule.record == REQUEST_RECORD_METRIC else DURATION_SOURCE_METRIC}"
            )
    return mappings, issues

def verify_coverage(
    contract_graph: Path = CONTRACT_GRAPH,
    alerts_root: Path = ALERTS_ROOT,
    dashboards_root: Path = DASHBOARDS_ROOT,
) -> VerificationReport:
    issues: list[str] = []
    try:
        operations = load_content_operations(contract_graph)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        return VerificationReport(0, 0, (f"ContractGraph 无法使用: {error}",))

    alert_expressions, alert_issues = _load_alert_expressions(alerts_root)
    dashboard_expressions, dashboard_issues = _load_dashboard_expressions(
        dashboards_root
    )
    issues.extend(alert_issues)
    issues.extend(dashboard_issues)
    mappings, mapping_issues = _verify_recording_rules(
        operations, alert_expressions
    )
    issues.extend(mapping_issues)

    ready = [
        operation
        for operation in operations
        if operation.commercial_status == "ready"
    ]
    consumers = [
        expression
        for expression in alert_expressions + dashboard_expressions
        if not expression.record
    ]
    issues.extend(_verify_consumer_operation_selectors(operations, consumers))
    for operation in ready:
        for record, dimension in (
            (REQUEST_RECORD_METRIC, "availability"),
            (DURATION_RECORD_METRIC, "latency_p95"),
        ):
            if (operation.operation_id, record) not in mappings:
                issues.append(
                    f"{operation.operation_id} ({operation.metric}) 缺少 "
                    f"{dimension} recording rule"
                )
                continue
            if not any(
                _expression_covers(
                    consumer.expression,
                    record,
                    operation,
                )
                for consumer in consumers
            ):
                issues.append(
                    f"{operation.operation_id} ({operation.metric}) 的 "
                    f"{dimension} 未被 alert/dashboard PromQL 消费"
                )
    return VerificationReport(
        content_operations=len(operations),
        ready_operations=len(ready),
        issues=tuple(issues),
    )

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-graph", type=Path, default=CONTRACT_GRAPH)
    parser.add_argument("--alerts-root", type=Path, default=ALERTS_ROOT)
    parser.add_argument("--dashboards-root", type=Path, default=DASHBOARDS_ROOT)
    parser.add_argument(
        "--write-recording-rules",
        action="store_true",
        help="从 ContractGraph 重建 content operation recording rules",
    )
    parser.add_argument("--mapping-root", type=Path, default=MAPPING_ROOT)
    return parser.parse_args()

def main() -> int:
    args = _parse_args()
    if args.write_recording_rules:
        try:
            operations = load_content_operations(args.contract_graph)
            count = write_recording_rule_files(operations, args.mapping_root)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            print(
                f"verify_content_object_alert_coverage: BLOCK: {error}",
                file=sys.stderr,
            )
            return 1
        print(
            "verify_content_object_alert_coverage: "
            f"生成 {count} 份 recording rule"
        )
        return 0

    report = verify_coverage(
        contract_graph=args.contract_graph,
        alerts_root=args.alerts_root,
        dashboards_root=args.dashboards_root,
    )
    if report.issues:
        print(
            "verify_content_object_alert_coverage: BLOCK: "
            "content ready operation 可观测覆盖不完整",
            file=sys.stderr,
        )
        for issue in report.issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    print(
        "verify_content_object_alert_coverage: OK "
        f"(content={report.content_operations}, ready={report.ready_operations})"
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
