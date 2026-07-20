#!/usr/bin/env python3
"""校验 content 页面 product_action 漏斗的 metadata→App→SLS→Dashboard 闭环。"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = REPO_ROOT / "quwoquan_app"
PAGE_CONTRACT = (
    REPO_ROOT
    / "quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml"
)
EVENT_CATALOG = (
    REPO_ROOT
    / "quwoquan_service/contracts/metadata/ops/event_record/event_catalog.yaml"
)
SLS_CONTRACT = (
    REPO_ROOT
    / "quwoquan_ops/environments/cloud-providers/aliyun/sls/product_telemetry.yaml"
)
DASHBOARD = (
    REPO_ROOT
    / "quwoquan_ops/observability/monitoring/dashboards/l2_content_objects.json"
)
TRACKER = APP_ROOT / "lib/core/trackers/journey_event_tracker.dart"
TRACKER_TEST = (
    APP_ROOT
    / "test/local_contract/core/trackers/"
    "journey_event_tracker__observability__local_contract_test.dart"
)

REQUIRED_FAILURE_DIMENSIONS = frozenset(
    {
        "result",
        "durationMs",
        "failReasonCode",
        "recoveryAction",
        "requestId",
        "traceId",
    }
)
AGGREGATED_FAILURE_DIMENSIONS = frozenset(
    {"result", "durationMs", "failReasonCode", "recoveryAction"}
)


@dataclass(frozen=True)
class ProductActionFunnel:
    journey: str
    telemetry_page_name: str
    object_ids: tuple[str, ...]
    actions: tuple[str, ...]
    evidence_paths: tuple[str, ...]
    required_dimensions: tuple[str, ...]
    aggregate_row_kind: str
    alerts: tuple[str, ...]

    @property
    def identity(self) -> tuple[str, str]:
        return self.journey, self.telemetry_page_name


def _mapping(value: Any, label: str, issues: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        issues.append(f"{label} 必须是 mapping")
        return {}
    return value


def _strings(value: Any, label: str, issues: list[str]) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        issues.append(f"{label} 必须是非空字符串列表")
        return ()
    values = tuple(str(item).strip() for item in value)
    if any(not item for item in values):
        issues.append(f"{label} 不得包含空值")
    if len(values) != len(set(values)):
        issues.append(f"{label} 不得重复")
    return values


def load_product_action_funnels(
    contract_path: Path,
) -> tuple[list[ProductActionFunnel], list[str]]:
    issues: list[str] = []
    document = _mapping(
        yaml.safe_load(contract_path.read_text(encoding="utf-8")),
        str(contract_path),
        issues,
    )
    pages = document.get("pages")
    if not isinstance(pages, list):
        return [], [*issues, "page_object_contract.pages 必须是列表"]

    unique: dict[tuple[str, str], ProductActionFunnel] = {}
    for page_index, raw_page in enumerate(pages):
        page = _mapping(raw_page, f"pages[{page_index}]", issues)
        page_id = str(page.get("page_id", page_index))
        telemetry = _mapping(
            page.get("telemetry_descriptor"),
            f"{page_id}.telemetry_descriptor",
            issues,
        )
        raw_actions = telemetry.get("product_actions", [])
        if raw_actions == []:
            continue
        if not isinstance(raw_actions, list):
            issues.append(
                f"{page_id}.telemetry_descriptor.product_actions 必须是列表"
            )
            continue
        page_object_ids = set(
            _strings(page.get("object_ids"), f"{page_id}.object_ids", issues)
        )
        for action_index, raw_action in enumerate(raw_actions):
            label = f"{page_id}.product_actions[{action_index}]"
            action = _mapping(raw_action, label, issues)
            journey = str(action.get("journey", "")).strip()
            page_name = str(action.get("telemetry_page_name", "")).strip()
            if not journey or not page_name:
                issues.append(f"{label} 缺少 journey/telemetry_page_name")
                continue
            funnel = ProductActionFunnel(
                journey=journey,
                telemetry_page_name=page_name,
                object_ids=_strings(
                    action.get("object_ids"), f"{label}.object_ids", issues
                ),
                actions=_strings(action.get("actions"), f"{label}.actions", issues),
                evidence_paths=_strings(
                    action.get("instrumentation_evidence"),
                    f"{label}.instrumentation_evidence",
                    issues,
                ),
                required_dimensions=_strings(
                    action.get("required_dimensions"),
                    f"{label}.required_dimensions",
                    issues,
                ),
                aggregate_row_kind=str(
                    action.get("aggregate_row_kind", "")
                ).strip(),
                alerts=_strings(action.get("alerts"), f"{label}.alerts", issues),
            )
            missing_objects = set(funnel.object_ids) - page_object_ids
            if missing_objects:
                issues.append(
                    f"{label} object_ids 未绑定到页面对象: "
                    f"{sorted(missing_objects)}"
                )
            previous = unique.get(funnel.identity)
            if previous is not None and previous != funnel:
                issues.append(
                    f"{label} 与同 journey/page 的既有漏斗契约不一致"
                )
            unique[funnel.identity] = funnel

    if not unique:
        issues.append("page_object_contract 未声明任何 product_actions 漏斗")
    return sorted(unique.values(), key=lambda item: item.identity), issues


def _product_action_extensions(
    event_catalog_path: Path, issues: list[str]
) -> set[str]:
    document = _mapping(
        yaml.safe_load(event_catalog_path.read_text(encoding="utf-8")),
        str(event_catalog_path),
        issues,
    )
    events = document.get("events")
    if not isinstance(events, list):
        issues.append("event_catalog.events 必须是列表")
        return set()
    for event in events:
        if isinstance(event, dict) and event.get("event_type") == "product_action":
            required = event.get("required_extensions", [])
            optional = event.get("optional_extensions", [])
            if not isinstance(required, list) or not isinstance(optional, list):
                issues.append("product_action extensions 必须是列表")
                return set()
            return {str(value) for value in [*required, *optional]}
    issues.append("event_catalog 缺少 product_action")
    return set()


def _sls_parts(
    sls_path: Path, issues: list[str]
) -> tuple[set[str], dict[str, str], dict[str, str]]:
    document = _mapping(
        yaml.safe_load(sls_path.read_text(encoding="utf-8")),
        str(sls_path),
        issues,
    )
    spec = _mapping(document.get("spec"), "product_telemetry.spec", issues)
    raw_fields: set[str] = set()
    for logstore in spec.get("logstores", []):
        if (
            isinstance(logstore, dict)
            and logstore.get("name") == "app-product-telemetry-raw"
        ):
            indexes = _mapping(
                logstore.get("indexes"), "raw logstore.indexes", issues
            )
            fields = indexes.get("fields", [])
            if isinstance(fields, list):
                raw_fields = {str(field) for field in fields}
            break
    if not raw_fields:
        issues.append("SLS 缺少 app-product-telemetry-raw 字段索引")

    scheduled = _mapping(
        spec.get("scheduledSql"), "product_telemetry.scheduledSql", issues
    )
    jobs = {
        str(job.get("rowKind", "")).strip(): str(job.get("sql", ""))
        for job in scheduled.get("jobs", [])
        if isinstance(job, dict)
    }
    alerts = {
        str(alert.get("name", "")).strip(): str(alert.get("query", ""))
        for alert in spec.get("alerts", [])
        if isinstance(alert, dict)
    }
    return raw_fields, jobs, alerts


def verify_content_page_funnels(
    *,
    page_contract: Path = PAGE_CONTRACT,
    event_catalog: Path = EVENT_CATALOG,
    sls_contract: Path = SLS_CONTRACT,
    dashboard: Path = DASHBOARD,
    app_root: Path = APP_ROOT,
    tracker: Path = TRACKER,
    tracker_test: Path = TRACKER_TEST,
) -> tuple[ProductActionFunnel, ...]:
    funnels, issues = load_product_action_funnels(page_contract)
    allowed_extensions = _product_action_extensions(event_catalog, issues)
    missing_catalog_dimensions = REQUIRED_FAILURE_DIMENSIONS - allowed_extensions
    if missing_catalog_dimensions:
        issues.append(
            "event_catalog.product_action 缺少失败关联维度: "
            f"{sorted(missing_catalog_dimensions)}"
        )

    raw_fields, jobs, configured_alerts = _sls_parts(sls_contract, issues)
    required_raw_fields = REQUIRED_FAILURE_DIMENSIONS | {
        "journey",
        "action",
        "pageName",
    }
    missing_raw_fields = required_raw_fields - raw_fields
    if missing_raw_fields:
        issues.append(f"SLS raw index 缺字段: {sorted(missing_raw_fields)}")

    tracker_text = (
        tracker.read_text(encoding="utf-8", errors="ignore")
        if tracker.is_file()
        else ""
    )
    for token in (
        "RuntimeFailureTelemetryDimensions.from(error)",
        "failReasonCode:",
        "recoveryAction:",
        "requestId:",
        "traceId:",
    ):
        if token not in tracker_text:
            issues.append(f"JourneyEventTracker 缺少结构化失败投影: {token}")

    dashboard_text = (
        dashboard.read_text(encoding="utf-8", errors="ignore")
        if dashboard.is_file()
        else ""
    )
    test_text = (
        tracker_test.read_text(encoding="utf-8", errors="ignore")
        if tracker_test.is_file()
        else ""
    )
    for token in (
        "failReasonCode",
        "recoveryAction",
        "requestId",
        "traceId",
    ):
        if token not in test_text:
            issues.append(f"JourneyEventTracker local_contract 缺断言维度: {token}")

    for funnel in funnels:
        required_dimensions = set(funnel.required_dimensions)
        if required_dimensions != REQUIRED_FAILURE_DIMENSIONS:
            issues.append(
                f"{funnel.identity} required_dimensions 必须完整等于 "
                f"{sorted(REQUIRED_FAILURE_DIMENSIONS)}"
            )
        combined_evidence = ""
        for relative in funnel.evidence_paths:
            evidence = app_root / relative
            if not evidence.is_file():
                issues.append(f"{funnel.identity} evidence 不存在: {relative}")
                continue
            combined_evidence += evidence.read_text(
                encoding="utf-8", errors="ignore"
            )
        for literal in (funnel.journey, funnel.telemetry_page_name, *funnel.actions):
            if not re.search(rf"['\"]{re.escape(literal)}['\"]", combined_evidence):
                issues.append(
                    f"{funnel.identity} instrumentation 缺字面量: {literal}"
                )
        for token in ("'result'", "'durationMs'", "error:"):
            if token not in combined_evidence:
                issues.append(
                    f"{funnel.identity} instrumentation 缺失败漏斗证据: {token}"
                )

        aggregate_sql = jobs.get(funnel.aggregate_row_kind, "")
        if not aggregate_sql:
            issues.append(
                f"{funnel.identity} SLS 缺 rowKind={funnel.aggregate_row_kind}"
            )
        else:
            for dimension in AGGREGATED_FAILURE_DIMENSIONS:
                if dimension not in aggregate_sql:
                    issues.append(
                        f"{funnel.identity} SLS 聚合缺维度: {dimension}"
                    )
            if funnel.journey not in dashboard_text:
                issues.append(
                    f"{funnel.identity} dashboard 未声明 journey={funnel.journey}"
                )
            if funnel.aggregate_row_kind not in dashboard_text:
                issues.append(
                    f"{funnel.identity} dashboard 未声明 "
                    f"rowKind={funnel.aggregate_row_kind}"
                )

        for alert_name in funnel.alerts:
            query = configured_alerts.get(alert_name)
            if not query:
                issues.append(f"{funnel.identity} SLS 告警不存在: {alert_name}")
                continue
            if funnel.journey not in query:
                issues.append(
                    f"{funnel.identity} 告警 {alert_name} 未筛选该 journey"
                )
            if alert_name not in dashboard_text:
                issues.append(
                    f"{funnel.identity} dashboard 未关联告警 {alert_name}"
                )

    if issues:
        raise ValueError("\n".join(f"- {issue}" for issue in issues))
    return tuple(funnels)


def main() -> int:
    try:
        funnels = verify_content_page_funnels()
    except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError) as error:
        print(f"verify_content_page_funnel_coverage: FAIL\n{error}", file=sys.stderr)
        return 1
    print(
        "verify_content_page_funnel_coverage: OK "
        f"({len(funnels)} product-action funnels)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
