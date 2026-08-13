#!/usr/bin/env python3
"""黄金指标注册表 ↔ 告警定义阈值同源门禁。

golden_metric_catalog.yaml 是业务指标阈值的唯一真相源。每条声明了 alerting 的
指标，其绑定的告警必须真实存在于对应 policy 文件中，且 catalog 登记的
threshold 数值必须逐字出现在该告警的触发条件里；任何一侧单独改动阈值都会
在此 BLOCK，修复方式是同一次变更同时更新 catalog 与告警定义。

校验范围：
- policy=prometheus：quwoquan_alerts.yaml（Prometheus alerting rules），从
  目标 alert 的 expr 中提取全部比较阈值数值。
- policy=elasticsearch_product_telemetry：product_telemetry_alerts.yaml
  （ES 告警策略），从目标告警 condition 中提取全部比较阈值数值，样本量
  门槛子句（*Count >= N）不计入阈值集合。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_METRIC_CATALOG = (
    REPO_ROOT
    / "quwoquan_service/services/product-ops-service/contracts/product_ops"
    / "event_record/golden_metric_catalog.yaml"
)

_COMPARISON_VALUE = re.compile(r"[<>]=?\s*([0-9]+(?:\.[0-9]+)?)")
_SAMPLE_GUARD_CLAUSE = re.compile(
    r"\b\w*[Cc]ount\s*>=\s*[0-9]+(?:\.[0-9]+)?"
)


def _load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"INVALID YAML ROOT: {path.relative_to(REPO_ROOT)}")
    return value


def _comparison_values(expression: str) -> set[float]:
    return {float(match) for match in _COMPARISON_VALUE.findall(expression)}


def _prometheus_alert_thresholds(policy_document: dict) -> dict[str, set[float]]:
    """alert 名 → expr 中出现的全部比较阈值。"""
    thresholds: dict[str, set[float]] = {}
    for group in policy_document.get("groups", []):
        if not isinstance(group, dict):
            continue
        for rule in group.get("rules", []):
            if not isinstance(rule, dict) or "alert" not in rule:
                continue
            expression = str(rule.get("expr", ""))
            thresholds[str(rule["alert"])] = _comparison_values(expression)
    return thresholds


def _elasticsearch_alert_thresholds(policy_document: dict) -> dict[str, set[float]]:
    """告警名 → condition 中样本门槛之外的全部比较阈值。"""
    thresholds: dict[str, set[float]] = {}
    for alert in policy_document.get("spec", {}).get("alerts", []):
        if not isinstance(alert, dict):
            continue
        condition = _SAMPLE_GUARD_CLAUSE.sub("", str(alert.get("condition", "")))
        thresholds[str(alert.get("name", ""))] = _comparison_values(condition)
    return thresholds


def main() -> int:
    errors: list[str] = []
    catalog = _load_yaml(GOLDEN_METRIC_CATALOG)
    policies = catalog.get("alerting_policies")
    if not isinstance(policies, dict) or not policies:
        print("FAIL: golden metric catalog must declare alerting_policies")
        return 1

    thresholds_by_policy: dict[str, dict[str, set[float]]] = {}
    for policy, relative_path in policies.items():
        policy_path = REPO_ROOT / str(relative_path)
        if not policy_path.is_file():
            errors.append(f"alerting policy file missing: {policy} -> {relative_path}")
            continue
        document = _load_yaml(policy_path)
        if policy == "prometheus":
            thresholds_by_policy[policy] = _prometheus_alert_thresholds(document)
        elif policy == "elasticsearch_product_telemetry":
            thresholds_by_policy[policy] = _elasticsearch_alert_thresholds(document)
        else:
            errors.append(f"unknown alerting policy kind: {policy}")

    bound_metrics = 0
    for metric in catalog.get("metrics", []):
        if not isinstance(metric, dict):
            continue
        alerting = metric.get("alerting")
        if alerting is None:
            continue
        metric_id = str(metric.get("metric_id", ""))
        if not isinstance(alerting, dict):
            errors.append(f"{metric_id}: alerting must be a mapping")
            continue
        policy = str(alerting.get("policy", ""))
        alert_name = str(alerting.get("alert_name", ""))
        threshold = alerting.get("threshold")
        if policy not in thresholds_by_policy:
            errors.append(f"{metric_id}: alerting policy is not loadable: {policy}")
            continue
        alerts = thresholds_by_policy[policy]
        if alert_name not in alerts:
            errors.append(
                f"{metric_id}: alert {alert_name} does not exist in {policy} policy"
            )
            continue
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            errors.append(f"{metric_id}: alerting threshold must be numeric")
            continue
        if float(threshold) not in alerts[alert_name]:
            observed = sorted(alerts[alert_name])
            errors.append(
                f"{metric_id}: threshold {threshold} is not among the comparison "
                f"values of alert {alert_name} ({observed}); update the catalog "
                "and the alert definition in the same change"
            )
            continue
        bound_metrics += 1

    if errors:
        print("FAIL: golden metric threshold homology")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASS: golden metric threshold homology")
    print(f"  - {bound_metrics} alert-bound golden metrics verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
