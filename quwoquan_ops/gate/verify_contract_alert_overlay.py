#!/usr/bin/env python3
"""把手写 PromQL 收敛为「ContractGraph 派生 + 显式 overlay」两类，并对两类都做漂移检测。

背景：`quwoquan_ops/observability/monitoring/alerts/` 下已经有一条强派生链——
`verify_object_alert_coverage.py --write` 从 ContractGraph 生成 `<domain>_contract/*.yaml`
recording rules、`contract_object_coverage.yaml`（**只覆盖 commercial ready**）与覆盖仪表盘，
并做字节级漂移检测。断点有两处：

1. `commercial.status != ready` 的 operation 没有任何派生告警口径，只能靠手写 PromQL 兜底。
2. 手写文件（`quwoquan_alerts.yaml` 等）整体不在任何漂移检测里，新增一条手写 PromQL 不会被拦。

本门禁补齐这两处：

* `--write` 从 ContractGraph 生成 `contract_pending_commercial_coverage.yaml`，
  为待商用 operation 提供与 ready 同形状的可用性 / P95 告警。selector 用 operation id 与
  contract_metric 的**显式枚举**，不假设 `contract_metric` 以 `<domain>_` 开头。
* 默认模式对该生成物做字节级漂移检测，并要求所有**非派生**告警文件里的每一条规则都在
  `handwritten_overlay_manifest.yaml` 登记「为何不可派生」。未登记即 BLOCK。

可派生判定是机械的，没有 allowlist：一条规则可派生当且仅当

* 只消费 `http_server_requests_total` / `http_server_duration_seconds_bucket` /
  `quwoquan_<domain>_contract_operation_*`，不掺任何其它 series；
* `status` matcher 只允许缺省或 `=~"5.."`（ContractGraph 的 `slo.availabilityPercent`
  只定义 5xx 错误预算，4xx/429/503 不在契约声明的 SLO 维度里）；
* 形状是 `histogram_quantile(0.95, ...)`（对应 `slo.latencyP95Milliseconds`）或 5xx 比率
  （对应 `slo.availabilityPercent`）；
* selector 能解析到 ContractGraph 里至少一个 operation。

可派生的规则必须迁走（由上述两个派生产物承担），留在 overlay 即 BLOCK；反过来 selector
指向 ContractGraph 内服务却匹配不到任何 operation 的规则是死告警，也 BLOCK，不允许用
overlay 理由掩盖。
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

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_service.scripts.verify.observability import (  # noqa: E402
    verify_object_alert_coverage as coverage,
)

MONITORING_ROOT = REPO_ROOT / "quwoquan_ops/observability/monitoring"
ALERTS_ROOT = MONITORING_ROOT / "alerts"
# manifest 不能落在 alerts/ 下：该目录整体挂载成 Prometheus 的 /etc/prometheus/rules，
# 非 rule YAML 放进去会被 Prometheus 与 verify_object_alert_coverage.py 当成坏规则文件。
OVERLAY_MANIFEST = MONITORING_ROOT / "handwritten_overlay_manifest.yaml"
PENDING_COVERAGE_NAME = "contract_pending_commercial_coverage.yaml"
PROMETHEUS_CONFIG = MONITORING_ROOT / "prometheus.yml"
PROMETHEUS_PENDING_RULE = f"/etc/prometheus/rules/{PENDING_COVERAGE_NAME}"

SCRIPT_NAME = Path(__file__).name
GENERATED_HEADER = (
    "# Code generated from quwoquan_service/generated/contract_graph.json.\n"
    f"# Regenerate with {SCRIPT_NAME} --write.\n"
)

HTTP_SOURCE_SERIES = frozenset(
    {
        coverage.REQUEST_SOURCE_METRIC,
        coverage.DURATION_SOURCE_METRIC,
    }
)
ALLOWED_STATUS_MATCHER = ("=~", "5..")

MANIFEST_SCHEMA = "alert-overlay"

# overlay 理由是封闭枚举：每一条都描述「ContractGraph 为什么无法表达这个口径」，
# 而不是「这条规则暂时没人迁」。新增理由必须同时说明它为何不可能被契约声明覆盖。
NON_DERIVABLE_REASONS = {
    # selector 指向的服务没有 contracts/domain.yaml，不在 ContractGraph 运行分母内。
    "service_outside_contract_graph",
    # 服务级/全局金信号，不绑定任何单个 operation，无法由 per-operation SLO 派生。
    "service_level_golden_signal",
    # 用了 4xx/429/503 等状态类；ContractGraph 的 slo.availabilityPercent 只定义 5xx 错误预算。
    "status_class_not_in_contract_slo",
    # 用绝对错误数触发；契约只声明比率型 availabilityPercent。
    "absolute_count_not_ratio_slo",
    # 主机/容器/中间件 exporter series，不属于第一方契约面。
    "infrastructure_exporter_series",
    # 第一方服务自注册的运行时/业务 series，不是 HTTP operation 观测面，契约未声明其 SLO。
    "first_party_series_not_contract_operation",
    # App 端体验埋点回流的 ops_* series，属于客户端遥测而非云侧 operation。
    "app_client_telemetry_series",
}

_STRING_RE = re.compile(r'"(?:\\.|[^"])*"')
_LABEL_BLOCK_RE = re.compile(r"\{[^{}]*\}")
_IDENTIFIER_RE = re.compile(r"[a-zA-Z_:][a-zA-Z0-9_:]*")
_GROUPING_RE = re.compile(
    r"\b(?:by|without|on|ignoring|group_left|group_right)\s*\([^()]*\)"
)
_DURATION_RE = re.compile(r"\[\s*\d+(?:\.\d+)?[smhdwy]\s*\]")
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?(?:[eE][-+]?\d+)?\b")
_PATH_PARAMETER_RE = re.compile(r"\{[^{} /]+\}")
# 形似契约 record metric 但域段缺失/拼错的 series：这类 selector 永远不会有样本。
_RECORD_METRIC_SHAPED_RE = re.compile(
    r"^quwoquan_[a-z0-9_]*contract_operation_(?:requests_total|duration_seconds_bucket)$"
)

_PROMQL_FUNCTIONS = frozenset(
    """
    abs absent absent_over_time and avg avg_over_time bool bottomk ceil changes clamp
    clamp_max clamp_min count count_over_time count_values day_of_month day_of_week
    days_in_month delta deriv exp floor group histogram_quantile hour idelta increase
    irate label_join label_replace last_over_time ln log10 log2 max max_over_time min
    min_over_time minute month or predict_linear present_over_time quantile
    quantile_over_time rate resets round scalar sgn sort sort_desc sqrt stddev
    stddev_over_time stdvar sum sum_over_time time timestamp topk unless vector year
    """.split()
)


class OverlayInputError(RuntimeError):
    """告警树或 overlay manifest 无法作为判定输入。"""


@dataclass(frozen=True)
class AlertRule:
    path: Path
    group: str
    name: str
    kind: str
    expression: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (_display_path(self.path), self.group, self.name)


@dataclass(frozen=True)
class OverlayEntry:
    file: str
    group: str
    rule: str
    reason: str
    justification: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.file, self.group, self.rule)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def generated_alert_files(alerts_root: Path) -> set[Path]:
    """ContractGraph 派生告警文件集合；overlay 是它在告警树里的补集。"""
    generated = {
        alerts_root / coverage.COVERAGE_ALERTS_NAME,
        alerts_root / PENDING_COVERAGE_NAME,
    }
    for directory in sorted(
        alerts_root.glob(f"*{coverage.RECORDING_RULE_DIR_SUFFIX}")
    ):
        if directory.is_dir():
            generated.update(directory.glob("*.yaml"))
            generated.update(directory.glob("*.yml"))
    return generated


def load_alert_rules(paths: Iterable[Path]) -> list[AlertRule]:
    rules: list[AlertRule] = []
    for path in sorted(paths):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            raise OverlayInputError(f"{_display_path(path)}: 无法解析: {error}") from error
        groups = (document or {}).get("groups") if isinstance(document, dict) else None
        if not isinstance(groups, list):
            raise OverlayInputError(f"{_display_path(path)}: 缺少 Prometheus groups")
        for group in groups:
            if not isinstance(group, dict):
                continue
            group_name = str(group.get("name", ""))
            for index, rule in enumerate(group.get("rules") or []):
                if not isinstance(rule, dict) or not isinstance(rule.get("expr"), str):
                    continue
                name = str(rule.get("alert") or rule.get("record") or index)
                rules.append(
                    AlertRule(
                        path=path,
                        group=group_name,
                        name=name,
                        kind="alert" if rule.get("alert") else "record",
                        expression=rule["expr"],
                    )
                )
    return rules


def referenced_series(expression: str) -> set[str]:
    """PromQL 里出现在 series 位置的标识符；label matcher、字符串、分组子句都不算。"""
    text = _LABEL_BLOCK_RE.sub(" ", expression)
    text = _STRING_RE.sub(" ", text)
    text = _GROUPING_RE.sub(" ", text)
    text = _DURATION_RE.sub(" ", text)
    text = _NUMBER_RE.sub(" ", text)
    names: set[str] = set()
    for match in _IDENTIFIER_RE.finditer(text):
        name = match.group(0)
        if name in _PROMQL_FUNCTIONS:
            continue
        if text[match.end() :].lstrip().startswith("("):
            continue
        names.add(name)
    return names


def _selectors(expression: str) -> list[tuple[str, dict[str, tuple[str, str]]]]:
    result: list[tuple[str, dict[str, tuple[str, str]]]] = []
    for selector in coverage._PROMQL_SELECTOR_RE.finditer(expression):
        labels: dict[str, tuple[str, str]] = {}
        for matcher in coverage._PROMQL_LABEL_RE.finditer(selector.group("labels")):
            labels[matcher.group("name")] = (
                matcher.group("operator"),
                coverage._decode_promql_string(matcher.group("value")),
            )
        result.append((selector.group("metric"), labels))
    return result


def _route_instances(path_template: str) -> tuple[str, str]:
    """路由 matcher 既可能写 pathTemplate 原文，也可能写运行时具体路径的正则。"""
    return path_template, _PATH_PARAMETER_RE.sub("x", path_template)


def _operation_matches(
    operation: coverage.OperationContract, labels: dict[str, tuple[str, str]]
) -> bool | None:
    for name, (operator, expected) in labels.items():
        if name in {"status", "le", "code"}:
            continue
        if name == "service":
            actual: tuple[str, ...] = (operation.service,)
        elif name == "method":
            actual = (operation.method,)
        elif name == "route":
            actual = _route_instances(operation.path_template)
        elif name == "operation":
            actual = (operation.operation_id,)
        elif name == "contract_metric":
            actual = (operation.metric,)
        elif name == "commercial_status":
            actual = (operation.commercial_status,)
        else:
            return None
        if not any(
            coverage._matcher_accepts(operator, expected, value) for value in actual
        ):
            return False
    return True


@dataclass(frozen=True)
class Derivability:
    derivable: bool
    detail: str


def classify_rule(
    rule: AlertRule,
    operations: list[coverage.OperationContract],
    services: frozenset[str],
) -> Derivability:
    series = referenced_series(rule.expression)
    contract_series = {
        name
        for name in series
        if name in HTTP_SOURCE_SERIES or coverage._RECORD_METRIC_RE.match(name)
    }
    counterfeit = sorted(
        name
        for name in series - contract_series
        if _RECORD_METRIC_SHAPED_RE.match(name)
    )
    if counterfeit:
        return Derivability(
            False,
            f"DEAD_SELECTOR: {counterfeit} 形似契约 record metric 但不是任何域的 "
            "quwoquan_<domain>_contract_operation_* ，永远不会有样本",
        )
    foreign = series - contract_series
    if foreign:
        return Derivability(False, f"消费非契约 series {sorted(foreign)}")
    if not contract_series:
        return Derivability(False, "没有消费任何契约 series")

    selectors = [
        (metric, labels)
        for metric, labels in _selectors(rule.expression)
        if metric in contract_series
    ]
    if not selectors:
        return Derivability(False, "契约 series 没有任何 label selector（服务级金信号）")
    contract_dimensions = {"service", "route", "operation", "contract_metric"}
    if not any(contract_dimensions & set(labels) for _, labels in selectors):
        return Derivability(
            False,
            "selector 只约束 status 等运行时维度，没有落到任何 service/route/operation（服务级金信号）",
        )

    for _, labels in selectors:
        status = labels.get("status")
        if status is not None and status != ALLOWED_STATUS_MATCHER:
            return Derivability(
                False,
                f'status matcher {status[0]}"{status[1]}" 不在契约 slo.availabilityPercent 的 5xx 口径内',
            )

    for _, labels in selectors:
        service = labels.get("service")
        if service is not None and service[0] == "=" and service[1] not in services:
            return Derivability(False, f"服务 {service[1]!r} 不在 ContractGraph 运行分母内")

    for _, labels in selectors:
        resolved = [
            operation
            for operation in operations
            if _operation_matches(operation, labels) is True
        ]
        if any(_operation_matches(operation, labels) is None for operation in operations):
            return Derivability(False, "selector 使用了 ContractGraph 无法解析的 label 维度")
        if not resolved:
            return Derivability(
                False,
                "DEAD_SELECTOR: selector 落在 ContractGraph 服务内却匹配不到任何 operation",
            )

    compact = "".join(rule.expression.split())
    if "histogram_quantile(0.95" in compact:
        return Derivability(True, "P95 延迟口径，等价于 slo.latencyP95Milliseconds")
    numerator = any(
        labels.get("status") == ALLOWED_STATUS_MATCHER for _, labels in selectors
    )
    denominator = any("status" not in labels for _, labels in selectors)
    if numerator and denominator and "/" in compact:
        return Derivability(True, "5xx 比率口径，等价于 slo.availabilityPercent")
    if numerator:
        return Derivability(
            False,
            "只统计 5xx 绝对量而没有比率分母，契约只声明 availabilityPercent 错误预算比率",
        )
    return Derivability(False, "既不是 P95 延迟也不是 5xx 比率，不对应任何已声明 SLO 维度")


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _promql_literal_alternation(values: Iterable[str]) -> str:
    """把字面量集合编成 PromQL 正则；正则元字符先转义，后续 `_quoted` 再做字符串层转义。"""
    escaped = sorted(
        {
            "".join(f"\\{char}" if char in r".^$|?*+()[]{}\\" else char for char in value)
            for value in values
        }
    )
    return "(" + "|".join(escaped) + ")"


def pending_coverage_document(
    operations: Iterable[coverage.OperationContract],
) -> str:
    pending = [operation for operation in operations if not operation.ready]
    grouped: dict[tuple[str, str, str], list[coverage.OperationContract]] = {}
    for operation in pending:
        grouped.setdefault(
            (operation.domain, operation.service, operation.commercial_status), []
        ).append(operation)

    lines = [
        GENERATED_HEADER.rstrip("\n"),
        "# commercial.status != ready 的 operation 覆盖。阈值同样来自 ContractGraph 的",
        "# slo.availabilityPercent / slo.latencyP95Milliseconds；selector 显式枚举 operation 与",
        "# contract_metric，不假设 contract_metric 以 <domain>_ 开头。",
        "groups:" if grouped else "groups: []",
    ]
    for (domain, service, status), group_operations in sorted(grouped.items()):
        request_metric, duration_metric = coverage.record_metrics(domain)
        prefix = coverage._alert_name_domain(domain)
        status_suffix = "".join(part.capitalize() for part in status.split("_"))
        lines.append(
            f"  - name: quwoquan_{domain}_contract_object_pending_{status}_coverage"
        )
        lines.append("    rules:")
        by_availability: dict[float, list[coverage.OperationContract]] = {}
        by_latency: dict[float, list[coverage.OperationContract]] = {}
        for operation in group_operations:
            by_availability.setdefault(operation.availability_percent, []).append(
                operation
            )
            by_latency.setdefault(operation.latency_p95_ms, []).append(operation)

        for tier, tier_operations in sorted(by_availability.items()):
            budget = round((100.0 - tier) / 100.0, 6)
            selector = _pending_selector(service, status, tier_operations)
            lines.extend(
                [
                    f"      - alert: {prefix}Pending{status_suffix}ContractOperation"
                    f"AvailabilityBelow{coverage._threshold_label(tier)}Percent",
                    "        expr: |",
                    f'          sum(rate({request_metric}{{{selector},status=~"5.."}}[10m]))'
                    " by (operation, contract_metric)",
                    f"          / clamp_min(sum(rate({request_metric}{{{selector}}}[10m]))"
                    f" by (operation, contract_metric), 0.001) > {budget:g}",
                    "        for: 10m",
                    "        labels:",
                    "          severity: warning",
                    "          layer: l2",
                    f"          domain: {domain}",
                    f"          commercial_status: {status}",
                    "        annotations:",
                    f'          summary: "{domain} 待商用（{status}）operation 5xx 比率超出可用性 SLO'
                    f'（{coverage._number_label(tier)}%）"',
                    '          description: "{{ $labels.operation }}'
                    f"（{{{{ $labels.contract_metric }}}}）5xx 比率 "
                    '{{ $value | humanizePercentage }} 超出 ContractGraph 声明的可用性 SLO；'
                    '该 operation 尚未商用，先按 commercial.gapId 判断是否阻塞放量。"',
                ]
            )
        for tier, tier_operations in sorted(by_latency.items()):
            selector = _pending_selector(service, status, tier_operations)
            lines.extend(
                [
                    f"      - alert: {prefix}Pending{status_suffix}ContractOperation"
                    f"LatencyP95Above{coverage._threshold_label(tier)}Ms",
                    "        expr: |",
                    "          histogram_quantile(0.95,",
                    f"            sum(rate({duration_metric}{{{selector}}}[5m]))"
                    " by (le, operation, contract_metric)",
                    f"          ) > {tier / 1000:g}",
                    "        for: 5m",
                    "        labels:",
                    "          severity: info",
                    "          layer: l2",
                    f"          domain: {domain}",
                    f"          commercial_status: {status}",
                    "        annotations:",
                    f'          summary: "{domain} 待商用（{status}）operation P95 超出 SLO'
                    f'（{coverage._number_label(tier)}ms）"',
                    '          description: "{{ $labels.operation }}'
                    f"（{{{{ $labels.contract_metric }}}}）P95 = "
                    '{{ $value | humanizeDuration }} 超出 ContractGraph 声明的 '
                    f'slo.latencyP95Milliseconds={coverage._number_label(tier)}。"',
                ]
            )
    return "\n".join(lines) + "\n"


def _pending_selector(
    service: str, status: str, operations: Iterable[coverage.OperationContract]
) -> str:
    materialized = list(operations)
    return ",".join(
        [
            f'service="{service}"',
            "operation=~"
            + _quoted(
                _promql_literal_alternation(
                    operation.operation_id for operation in materialized
                )
            ),
            "contract_metric=~"
            + _quoted(
                _promql_literal_alternation(
                    operation.metric for operation in materialized
                )
            ),
            f'commercial_status="{status}"',
        ]
    )


def load_overlay_manifest(path: Path) -> list[OverlayEntry]:
    if not path.is_file():
        raise OverlayInputError(f"{_display_path(path)}: 缺少 overlay manifest")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise OverlayInputError(f"{_display_path(path)}: 无法解析: {error}") from error
    if not isinstance(document, dict):
        raise OverlayInputError(f"{_display_path(path)}: 顶层必须是映射")
    if document.get("schema") != MANIFEST_SCHEMA:
        raise OverlayInputError(
            f"{_display_path(path)}: schema 必须是 {MANIFEST_SCHEMA}"
        )
    entries: list[OverlayEntry] = []
    for raw in document.get("rules") or []:
        if not isinstance(raw, dict):
            raise OverlayInputError(f"{_display_path(path)}: rules 元素必须是映射")
        entries.append(
            OverlayEntry(
                file=str(raw.get("file", "")).strip(),
                group=str(raw.get("group", "")).strip(),
                rule=str(raw.get("rule", "")).strip(),
                reason=str(raw.get("reason", "")).strip(),
                justification=str(raw.get("justification", "")).strip(),
            )
        )
    return entries


def verify(
    alerts_root: Path = ALERTS_ROOT,
    manifest_path: Path = OVERLAY_MANIFEST,
    prometheus_config: Path | None = PROMETHEUS_CONFIG,
    check_drift: bool = True,
) -> tuple[list[str], dict[str, int]]:
    issues: list[str] = []
    domain_services = coverage.load_domain_services()
    runtime_services = coverage.runtime_domain_services(domain_services)
    operations = [
        operation
        for operation in coverage.load_operations(domain_services=domain_services)
        if operation.service in runtime_services.values()
    ]
    services = frozenset(runtime_services.values())

    generated = generated_alert_files(alerts_root)
    overlay_files = [
        path
        for path in sorted(alerts_root.rglob("*.yaml")) + sorted(alerts_root.rglob("*.yml"))
        if path not in generated and path != manifest_path
    ]
    overlay_rules = load_alert_rules(overlay_files)

    if check_drift:
        pending_path = alerts_root / PENDING_COVERAGE_NAME
        expected = pending_coverage_document(operations)
        if not pending_path.is_file():
            issues.append(
                f"{_display_path(pending_path)}: 缺少 ContractGraph 派生产物，执行 {SCRIPT_NAME} --write"
            )
        elif pending_path.read_text(encoding="utf-8") != expected:
            issues.append(
                f"{_display_path(pending_path)}: 与 ContractGraph 派生结果漂移，执行 {SCRIPT_NAME} --write"
            )

    entries = load_overlay_manifest(manifest_path)
    by_key: dict[tuple[str, str, str], OverlayEntry] = {}
    for entry in entries:
        if entry.key in by_key:
            issues.append(
                f"{_display_path(manifest_path)}: {entry.key} 重复登记"
            )
            continue
        by_key[entry.key] = entry
        if entry.reason not in NON_DERIVABLE_REASONS:
            issues.append(
                f"{_display_path(manifest_path)}: {entry.key} 的 reason {entry.reason!r} "
                f"不在封闭枚举 {sorted(NON_DERIVABLE_REASONS)} 内"
            )
        if not entry.justification:
            issues.append(
                f"{_display_path(manifest_path)}: {entry.key} 缺少 justification"
            )

    counters: collections.Counter[str] = collections.Counter()
    seen: set[tuple[str, str, str]] = set()
    for rule in overlay_rules:
        seen.add(rule.key)
        verdict = classify_rule(rule, operations, services)
        if verdict.detail.startswith("DEAD_SELECTOR"):
            counters["dead"] += 1
            issues.append(
                f"{rule.key[0]}#{rule.group}/{rule.name}: {verdict.detail}；"
                "死告警必须删除，不能用 overlay 理由保留"
            )
            continue
        if verdict.derivable:
            counters["derivable"] += 1
            issues.append(
                f"{rule.key[0]}#{rule.group}/{rule.name}: 可由 ContractGraph 派生"
                f"（{verdict.detail}），必须迁入 codegen 而不是留在 overlay"
            )
            continue
        counters["overlay"] += 1
        entry = by_key.get(rule.key)
        if entry is None:
            issues.append(
                f"{rule.key[0]}#{rule.group}/{rule.name}: 手写 PromQL 未在 "
                f"{_display_path(manifest_path)} 登记不可派生理由"
            )
            continue
        counters[f"reason:{entry.reason}"] += 1

    for key in sorted(set(by_key) - seen):
        issues.append(
            f"{_display_path(manifest_path)}: {key} 登记了不存在的规则，删除该条目"
        )

    if prometheus_config is not None:
        issues.extend(_verify_prometheus_rule_files(prometheus_config))

    counters["overlay_files"] = len(overlay_files)
    counters["overlay_rules"] = len(overlay_rules)
    return issues, dict(counters)


def _verify_prometheus_rule_files(config: Path) -> list[str]:
    if not config.is_file():
        return [f"{_display_path(config)}: 缺少 Prometheus 配置"]
    try:
        document = yaml.safe_load(config.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        return [f"{_display_path(config)}: 无法解析: {error}"]
    rule_files = (document or {}).get("rule_files")
    if not isinstance(rule_files, list):
        return [f"{_display_path(config)}: 缺少 rule_files"]
    if PROMETHEUS_PENDING_RULE not in rule_files:
        return [
            f"{_display_path(config)}: rule_files 缺少 {PROMETHEUS_PENDING_RULE}，"
            "待商用 operation 的派生告警不会被 Prometheus 加载"
        ]
    return []


def write_generated(alerts_root: Path = ALERTS_ROOT) -> Path:
    domain_services = coverage.load_domain_services()
    runtime_services = coverage.runtime_domain_services(domain_services)
    operations = [
        operation
        for operation in coverage.load_operations(domain_services=domain_services)
        if operation.service in runtime_services.values()
    ]
    path = alerts_root / PENDING_COVERAGE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pending_coverage_document(operations), encoding="utf-8")
    return path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alerts-root", type=Path, default=ALERTS_ROOT)
    parser.add_argument("--manifest", type=Path, default=OVERLAY_MANIFEST)
    parser.add_argument(
        "--write",
        action="store_true",
        help="从 ContractGraph 重建待商用 operation 覆盖告警",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="只打印每条 overlay 规则的可派生判定，不做 manifest 完备性判定",
    )
    return parser.parse_args()


def _report(alerts_root: Path, manifest_path: Path) -> int:
    domain_services = coverage.load_domain_services()
    runtime_services = coverage.runtime_domain_services(domain_services)
    operations = [
        operation
        for operation in coverage.load_operations(domain_services=domain_services)
        if operation.service in runtime_services.values()
    ]
    services = frozenset(runtime_services.values())
    generated = generated_alert_files(alerts_root)
    overlay_files = [
        path
        for path in sorted(alerts_root.rglob("*.yaml")) + sorted(alerts_root.rglob("*.yml"))
        if path not in generated and path != manifest_path
    ]
    for rule in load_alert_rules(overlay_files):
        verdict = classify_rule(rule, operations, services)
        tag = "DERIVABLE" if verdict.derivable else "OVERLAY   "
        print(f"{tag}\t{rule.key[0]}\t{rule.group}\t{rule.name}\t{verdict.detail}")
    return 0


def main() -> int:
    args = _parse_args()
    if args.write:
        try:
            path = write_generated(args.alerts_root)
        except coverage.ContractInputError as error:
            print(f"[contract-alert-overlay] BLOCK: {error}", file=sys.stderr)
            return 1
        print(f"[contract-alert-overlay] 生成 {_display_path(path)}")
        return 0
    if args.report:
        return _report(args.alerts_root, args.manifest)

    try:
        issues, counters = verify(args.alerts_root, args.manifest)
    except (OverlayInputError, coverage.ContractInputError) as error:
        print(f"[contract-alert-overlay] BLOCK: {error}", file=sys.stderr)
        return 1

    reasons = {
        key.split(":", 1)[1]: value
        for key, value in counters.items()
        if key.startswith("reason:")
    }
    print(
        f"[contract-alert-overlay] overlay 文件={counters.get('overlay_files', 0)} "
        f"规则={counters.get('overlay_rules', 0)} 已登记={sum(reasons.values())} "
        f"可派生残留={counters.get('derivable', 0)} 死告警={counters.get('dead', 0)}"
    )
    for reason, count in sorted(reasons.items()):
        print(f"  - {reason}: {count}")
    if issues:
        print(
            f"[contract-alert-overlay] FAIL: 手写 PromQL 收敛不完整（{len(issues)} 项）",
            file=sys.stderr,
        )
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    print("[contract-alert-overlay] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
