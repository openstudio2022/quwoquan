#!/usr/bin/env python3
"""校验 entity commercial-ready operation 的对象级告警覆盖。

业务 operation/metric/SLO 只从唯一 ContractGraph 读取；告警文件必须同时覆盖
GET 读路径与 POST/PATCH/DELETE 命令路径，防止 operation 翻 ready 后不可观测。
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_GRAPH = REPO_ROOT / "quwoquan_service/generated/contract_graph.json"
ALERTS = (
    REPO_ROOT
    / "quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml"
)
DASHBOARD = (
    REPO_ROOT
    / "quwoquan_ops/observability/monitoring/dashboards/l2_entity_objects.json"
)

REQUIRED_ALERTS = {
    "HomepageReadLatencyHigh",
    "HomepageReadAvailabilityLow",
    "HomepageCommandErrorRateHigh",
    "HomepageCommandLatencyHigh",
    "HomepageImportIssuesPresent",
    "HomepageImportStale",
}
ENTITY_ROUTE_PREFIXES = (
    "/homepages",
    "/homepage-reviews",
    "/homepage-claim-requests",
    "/homepage-status-reports",
)
ENTITY_ROUTE_SELECTOR = (
    "/homepages.*|/homepage-reviews.*|"
    "/homepage-claim-requests.*|/homepage-status-reports.*"
)


def _ready_entity_operations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    operations = payload.get("operations")
    if not isinstance(operations, list):
        raise ValueError("ContractGraph.operations 必须是数组")
    return [
        operation
        for operation in operations
        if isinstance(operation, dict)
        and operation.get("domain") == "entity"
        and (operation.get("commercial") or {}).get("status") == "ready"
    ]


def _alert_names(document: Any) -> set[str]:
    if not isinstance(document, dict):
        return set()
    names: set[str] = set()
    for group in document.get("groups") or []:
        if not isinstance(group, dict):
            continue
        for rule in group.get("rules") or []:
            if isinstance(rule, dict) and isinstance(rule.get("alert"), str):
                names.add(rule["alert"])
    return names


def main() -> int:
    issues: list[str] = []
    graph = json.loads(CONTRACT_GRAPH.read_text(encoding="utf-8"))
    operations = _ready_entity_operations(graph)
    if not operations:
        issues.append("ContractGraph 中没有 commercial-ready entity operation")

    for operation in operations:
        operation_id = str(operation.get("id", "")).strip()
        method = str(operation.get("method", "")).upper()
        path = str(operation.get("pathTemplate", "")).strip()
        telemetry = operation.get("telemetry")
        slo = operation.get("slo")
        if not isinstance(telemetry, dict) or not str(
            telemetry.get("metric", "")
        ).strip():
            issues.append(f"{operation_id} 缺少 telemetry.metric")
        if not isinstance(slo, dict):
            issues.append(f"{operation_id} 缺少 slo")
        if method not in {"GET", "POST", "PATCH", "DELETE"}:
            issues.append(f"{operation_id} HTTP method 未被 entity 告警分类: {method}")
        if not path.startswith(ENTITY_ROUTE_PREFIXES):
            issues.append(f"{operation_id} route 未被 entity 告警 selector 覆盖: {path}")

    alerts_document = yaml.safe_load(ALERTS.read_text(encoding="utf-8"))
    missing = REQUIRED_ALERTS - _alert_names(alerts_document)
    if missing:
        issues.append("缺少 entity 对象级告警: " + ", ".join(sorted(missing)))

    alerts_text = ALERTS.read_text(encoding="utf-8")
    for evidence in (
        'service="entity-service"',
        f'route=~"{ENTITY_ROUTE_SELECTOR}"',
        'method=~"POST|PATCH|DELETE"',
    ):
        if evidence not in alerts_text:
            issues.append(f"告警缺少真实 PromQL selector 证据: {evidence}")

    if "homepage_state" in alerts_text:
        issues.append("entity 告警仍引用已退役 homepage_state")

    try:
        dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        issues.append(f"entity dashboard 无法解析: {error}")
        dashboard = {}
    dashboard_text = json.dumps(dashboard, ensure_ascii=False)
    for evidence in (
        'service=\\"entity-service\\"',
        f'route=~\\"{ENTITY_ROUTE_SELECTOR}\\"',
        "quwoquan_homepage_import_objects",
        "runtime_health_check_status",
    ):
        if evidence not in dashboard_text:
            issues.append(f"entity dashboard 缺少真实 PromQL 证据: {evidence}")

    if issues:
        print("[entity-object-alert-coverage] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print(
        "[entity-object-alert-coverage] OK: "
        f"ready_operations={len(operations)} alerts={len(REQUIRED_ALERTS)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
