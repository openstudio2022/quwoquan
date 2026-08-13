"""告警/仪表盘 PromQL 的加载、selector 解析与 matcher 判定。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

import yaml

from .constants import _PROMQL_LABEL_RE, _PROMQL_SELECTOR_RE, _RECORD_METRIC_RE
from .models import RuleExpression

_LABEL_MATCHER_BLOCK = re.compile(r"\{[^{}]*\}")


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
