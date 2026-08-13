#!/usr/bin/env python3
"""指标存在性对账门禁：看板/告警消费的每个 Prometheus series 必须有真实来源。

来源闭包（任一命中即合法）：
1. Go 服务代码的 prometheus Opts 注册（Namespace/Subsystem/Name 拼接）与 NewDesc；
2. Python 服务代码的 prometheus_client 注册；
3. alerts/**/*.yaml 中的 recording rule（record:）；
4. 批处理 textfile 产物（代码内以字符串常量出现的完整指标名，Go 扫描已覆盖）；
5. 第三方 exporter 白名单前缀（node_/probe_/livekit_/up 等）。

看板或告警引用了闭包外的 series 即幽灵指标（空面板/死告警），BLOCK。
监控配置面禁止超前于代码 emit 面。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MONITORING = ROOT / "quwoquan_ops/observability/monitoring"
SERVICE_ROOT = ROOT / "quwoquan_service"

# PromQL 函数/关键字/修饰词：出现在表达式里但不是 series 名。
PROMQL_NOT_SERIES = {
    "sum", "rate", "irate", "increase", "avg", "min", "max", "count", "topk",
    "bottomk", "quantile", "histogram_quantile", "clamp_min", "clamp_max",
    "by", "without", "on", "ignoring", "group_left", "group_right", "offset",
    "and", "or", "unless", "abs", "absent", "absent_over_time", "ceil",
    "changes", "delta", "deriv", "exp", "floor", "label_join",
    "label_replace", "ln", "log2", "log10", "predict_linear", "resets",
    "round", "scalar", "sort", "sort_desc", "sqrt", "time", "timestamp",
    "vector", "year", "month", "minute", "hour", "day_of_month",
    "day_of_week", "days_in_month", "avg_over_time", "min_over_time",
    "max_over_time", "sum_over_time", "count_over_time", "stddev_over_time",
    "stdvar_over_time", "last_over_time", "present_over_time", "stddev",
    "stdvar", "group", "count_values", "bool", "le", "atan2",
}

# 第三方 exporter / 内建 series：仓库内不含其 emit 代码但采集真实存在。
EXPORTER_SERIES_ALLOWLIST_PREFIXES = (
    "node_",          # node-exporter（textfile collector 采集的批处理指标另由代码扫描覆盖）
    "probe_",         # blackbox-exporter
    "livekit_",       # LiveKit SFU 自带 exporter
    "up",             # Prometheus scrape 内建
    "ALERTS",         # Prometheus 内建
    "scrape_",        # Prometheus scrape 内建
    "redis_",         # redis-exporter
    "mongodb_",       # mongodb-exporter
    "pg_",            # postgres-exporter
    "container_",     # cadvisor
    "process_",       # client_golang 默认进程指标
    "go_",            # client_golang 默认 Go 运行时指标
    "python_",        # prometheus_client 默认
    "podman_",        # prometheus-podman-exporter（compose + scrape job 已部署）
)

SERIES_TOKEN = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")
DURATION_TOKEN = re.compile(r"^\d+[smhdwy]$")

# Go prometheus Opts 块：Namespace/Subsystem/Name 三段拼接；
# 字段值允许字符串字面量或引用同文件 const 标识符。
GO_OPTS_BLOCK = re.compile(
    r"(?:CounterOpts|GaugeOpts|HistogramOpts|SummaryOpts|Opts)\s*\{([^}]*)\}",
    re.DOTALL,
)
GO_OPTS_FIELD = re.compile(
    r"(Namespace|Subsystem|Name)\s*:\s*(?:\"([^\"]+)\"|([A-Za-z][A-Za-z0-9_]*))"
)
GO_CONST_STRING = re.compile(
    r"([A-Za-z][A-Za-z0-9_]*)\s*=\s*\"([a-zA-Z_][a-zA-Z0-9_]*)\""
)
GO_NEWDESC = re.compile(r"NewDesc\(\s*\n?\s*\"([a-zA-Z_][a-zA-Z0-9_]*)\"")
# 契约 runtime_entrypoints 的统一注册 helper（runtime/observability/entrypoint_metrics.go）。
GO_ENTRYPOINT_HELPER = re.compile(
    r"NewEntrypoint(?:Outcome)?Counter\(\s*\n?\s*\"([a-zA-Z_][a-zA-Z0-9_]*)\""
)
# textfile writer 等把指标名嵌在长字符串（含 # HELP 前缀、label 拼接）里，
# 对这类文件在字符串内容中搜索候选指标名。
GO_STRING_METRIC = re.compile(r"\"[^\"]*\"")
METRIC_NAME_IN_STRING = re.compile(r"\b([a-z][a-z0-9_]{5,})\b")
PY_METRIC = re.compile(
    r"(?:Counter|Gauge|Histogram|Summary)\(\s*[\n ]*[\"']([a-zA-Z_][a-zA-Z0-9_]*)[\"']"
)
RECORD_RULE = re.compile(r"^\s*-?\s*record:\s*([a-zA-Z_:][a-zA-Z0-9_:]*)\s*$", re.MULTILINE)


def normalize_series(name: str) -> str:
    """直方图族只登记基名：xxx_bucket/_sum/_count 归一到 xxx。"""
    for suffix in ("_bucket", "_sum", "_count"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


# 剔除 PromQL 中不承载 series 名的片段：标签选择器、分组子句、时长窗口、字符串。
SELECTOR = re.compile(r"\{[^}]*\}")
GROUPING = re.compile(r"\b(?:by|without|on|ignoring|group_left|group_right)\s*\([^)]*\)")
WINDOW = re.compile(r"\[[^\]]*\]")
QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")


def series_from_expression(expr: str) -> set[str]:
    cleaned = QUOTED.sub(" ", expr)
    cleaned = SELECTOR.sub(" ", cleaned)
    cleaned = GROUPING.sub(" ", cleaned)
    cleaned = WINDOW.sub(" ", cleaned)
    names: set[str] = set()
    for match in SERIES_TOKEN.finditer(cleaned):
        token = match.group(1)
        if token in PROMQL_NOT_SERIES or DURATION_TOKEN.match(token):
            continue
        # series 命名约定必须含下划线且全小写。
        if "_" not in token or token != token.lower():
            continue
        names.add(token)
    return names


def alert_rule_expressions(payload: object) -> list[str]:
    expressions: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "expr" and isinstance(value, str):
                expressions.append(value)
            else:
                expressions.extend(alert_rule_expressions(value))
    elif isinstance(payload, list):
        for item in payload:
            expressions.extend(alert_rule_expressions(item))
    return expressions


def consumed_series() -> dict[str, list[str]]:
    """返回 series -> 消费位置列表（只解析 expr 字段，不扫全文）。"""
    out: dict[str, list[str]] = {}

    def collect(expr: str, location: str) -> None:
        for name in series_from_expression(expr):
            out.setdefault(name, []).append(location)

    for dashboard in sorted((MONITORING / "dashboards").glob("*.json")):
        payload = json.loads(dashboard.read_text(encoding="utf-8"))
        for panel in payload.get("panels", []):
            for target in panel.get("targets", []):
                expr = target.get("expr", "")
                if expr:
                    collect(expr, str(dashboard.relative_to(ROOT)))
    for rules_file in sorted((MONITORING / "alerts").rglob("*.yaml")):
        payload = yaml.safe_load(rules_file.read_text(encoding="utf-8"))
        for expr in alert_rule_expressions(payload):
            collect(expr, str(rules_file.relative_to(ROOT)))
    return out


def emitted_series() -> set[str]:
    emitted: set[str] = set()
    go_files = list(SERVICE_ROOT.rglob("*.go"))
    for path in go_files:
        if "/tests/" in str(path) or path.name.endswith("_test.go"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if (
            "prometheus" not in text
            and "# TYPE" not in text
            and "NewEntrypoint" not in text
        ):
            continue
        constants = dict(GO_CONST_STRING.findall(text))
        for block in GO_OPTS_BLOCK.finditer(text):
            fields: dict[str, str] = {}
            for key, literal, identifier in GO_OPTS_FIELD.findall(block.group(1)):
                if literal:
                    fields[key] = literal
                elif identifier in constants:
                    fields[key] = constants[identifier]
            name = fields.get("Name", "")
            if not name:
                continue
            parts = [
                fields.get("Namespace", ""),
                fields.get("Subsystem", ""),
                name,
            ]
            emitted.add("_".join(part for part in parts if part))
        for match in GO_NEWDESC.finditer(text):
            emitted.add(match.group(1))
        for match in GO_ENTRYPOINT_HELPER.finditer(text):
            emitted.add(match.group(1))
        # textfile writer 等把指标名嵌在长字符串里（# HELP/# TYPE/Sprintf 拼接）。
        if "# TYPE" in text or "textfile" in text:
            for quoted in GO_STRING_METRIC.finditer(text):
                for match in METRIC_NAME_IN_STRING.finditer(quoted.group(0)):
                    emitted.add(match.group(1))
    for path in SERVICE_ROOT.rglob("*.py"):
        if "/tests/" in str(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "prometheus" not in text:
            continue
        for match in PY_METRIC.finditer(text):
            emitted.add(match.group(1))
    for rules_file in (MONITORING / "alerts").rglob("*.yaml"):
        for match in RECORD_RULE.finditer(rules_file.read_text(encoding="utf-8")):
            emitted.add(match.group(1))
    return emitted


def main() -> int:
    consumers = consumed_series()
    emitted = {normalize_series(name) for name in emitted_series()}
    ghosts: dict[str, list[str]] = {}
    for name, locations in sorted(consumers.items()):
        base = normalize_series(name)
        if base in emitted:
            continue
        if any(
            base == prefix.rstrip("_") or base.startswith(prefix)
            for prefix in EXPORTER_SERIES_ALLOWLIST_PREFIXES
        ):
            continue
        ghosts[name] = sorted(set(locations))
    if ghosts:
        print(f"FAIL: {len(ghosts)} 个看板/告警 series 在仓库内没有任何 emitter（幽灵指标）")
        for name, locations in ghosts.items():
            print(f"  - {name}: {', '.join(locations[:3])}")
        return 1
    print(
        "PASS: metric emitter existence "
        f"({len(consumers)} consumed series closed against {len(emitted)} emitters)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
