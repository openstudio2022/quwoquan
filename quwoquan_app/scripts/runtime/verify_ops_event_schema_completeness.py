#!/usr/bin/env python3
"""验证产品遥测九字段、目录、单出口与 SLS cutover 契约。"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


APP_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = APP_ROOT.parent
METADATA = REPO_ROOT / "quwoquan_service/contracts/metadata"
EVENT_CATALOG = METADATA / "ops/event_record/event_catalog.yaml"
APP_PAGES = METADATA / "_shared/app_pages.yaml"
SLS_RESOURCES = (
    REPO_ROOT
    / "quwoquan_ops/environments/cloud-providers/aliyun/sls/product_telemetry.yaml"
)

EXPECTED_COMMON_FIELDS = [
    "logType",
    "eventType",
    "sessionId",
    "pageName",
    "occurredAt",
    "deviceManufacturer",
    "deviceModel",
    "appVersion",
    "networkClass",
]
FORBIDDEN_LEGACY_FIELDS = {
    "eventVersion",
    "eventId",
    "eventName",
    "priority",
    "producer",
    "payload",
    "metrics",
    "surfaceId",
    "userIdHash",
}
EXPECTED_LOGSTORES = {
    "app-product-telemetry-raw": 3,
    "app-startup-diagnostic-raw": 3,
    "app-product-telemetry-hourly": 90,
}


def load_yaml(path: Path) -> dict:
    if not path.exists():
        raise ValueError(f"MISSING: {path.relative_to(REPO_ROOT)}")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"INVALID YAML ROOT: {path.relative_to(REPO_ROOT)}")
    return value


def mapping_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {str(key) for key in value} | {
            nested
            for child in value.values()
            for nested in mapping_keys(child)
        }
    if isinstance(value, list):
        return {nested for child in value for nested in mapping_keys(child)}
    return set()


def verify_catalog(errors: list[str]) -> None:
    catalog = load_yaml(EVENT_CATALOG)
    common_fields = catalog.get("common_fields")
    if common_fields != EXPECTED_COMMON_FIELDS:
        errors.append(
            f"event_catalog common_fields must be exactly {EXPECTED_COMMON_FIELDS}"
        )
    if catalog.get("log_types") != ["event", "error"]:
        errors.append("event_catalog log_types must be [event, error]")
    if catalog.get("network_classes") != [
        "wifi",
        "ethernet",
        "5g",
        "4g",
        "mobile",
        "other",
        "none",
    ]:
        errors.append("event_catalog network_classes drifted")
    events = catalog.get("events")
    if not isinstance(events, list) or not events:
        errors.append("event_catalog events must be a non-empty list")
        return
    event_types = {
        row.get("event_type") for row in events if isinstance(row, dict)
    }
    if "runtime_exception" not in event_types or "app_startup" not in event_types:
        errors.append("runtime_exception and app_startup must remain catalogued")
    startup = next(
        (
            row
            for row in events
            if isinstance(row, dict) and row.get("event_type") == "app_startup"
        ),
        None,
    )
    if not isinstance(startup, dict) or startup.get("normal_sample_rate") != 1.0:
        errors.append("app_startup must be reported at 100% without client sampling")
    catalog_keys = mapping_keys(catalog)
    for field in FORBIDDEN_LEGACY_FIELDS:
        if field in catalog_keys:
            errors.append(f"legacy public field remains in event_catalog: {field}")


def verify_pages(errors: list[str]) -> None:
    pages = load_yaml(APP_PAGES)
    fallback = pages.get("fallback_contexts")
    if fallback != ["app_bootstrap", "app_background"]:
        errors.append("app_pages fallback_contexts must be bootstrap/background")
    route_rows = pages.get("pages")
    if not isinstance(route_rows, list) or not route_rows:
        errors.append("app_pages pages must be non-empty")
        return
    names = [row.get("page_name") for row in route_rows if isinstance(row, dict)]
    if any(not isinstance(name, str) or not name.strip() for name in names):
        errors.append("app_pages contains empty pageName")


def require_source(path: str, markers: list[str], errors: list[str]) -> None:
    source_path = REPO_ROOT / path
    if not source_path.exists():
        errors.append(f"MISSING: {path}")
        return
    content = source_path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in content:
            errors.append(f"{path} missing contract marker: {marker}")


def verify_app_single_egress(errors: list[str]) -> None:
    require_source(
        "quwoquan_app/lib/core/telemetry/app_telemetry_reporter.dart",
        [
            "AppTelemetryCatalog.validate(payload)",
            "Duration(hours: 72)",
            "Duration(seconds: 10)",
            "Duration(seconds: 1)",
            "normalSampleRate",
        ],
        errors,
    )
    require_source(
        "quwoquan_app/lib/core/telemetry/app_telemetry_outbox.dart",
        [
            "maxRecords = 1000",
            "maxBytes = 2 * 1024 * 1024",
            "maxBatchRecords = 50",
            "maxBatchBytes = 128 * 1024",
            "idempotencyKey",
            "identityBlocked",
            "deadLettered",
        ],
        errors,
    )
    require_source(
        "quwoquan_app/lib/core/telemetry/app_telemetry_session_store.dart",
        ["base64Url", "AppLifecycleState.inactive", "foreground_resume"],
        errors,
    )
    require_source(
        "quwoquan_app/lib/cloud/services/behavior/behavior_repository.dart",
        ["implements BehaviorReporter"],
        errors,
    )
    forbidden_paths = [
        "quwoquan_app/lib/cloud/services/ops/ops_event_repository.dart",
        "quwoquan_app/lib/assistant/observability/logging/app_log_uploader.dart",
    ]
    for path in forbidden_paths:
        if (REPO_ROOT / path).exists():
            errors.append(f"legacy automatic upload path still exists: {path}")
    for path in (APP_ROOT / "lib").rglob("*.dart"):
        content = path.read_text(encoding="utf-8")
        if "AppLogUploader" in content or "OpsEventRepository" in content:
            errors.append(
                f"legacy automatic Ops upload symbol remains: {path.relative_to(REPO_ROOT)}"
            )


def verify_sls_cutover(errors: list[str]) -> None:
    resource = load_yaml(SLS_RESOURCES)
    spec = resource.get("spec", {})
    rows = spec.get("logstores", [])
    actual = {
        row.get("name"): row.get("retentionDays")
        for row in rows
        if isinstance(row, dict)
    }
    if actual != EXPECTED_LOGSTORES:
        errors.append(f"SLS logstore retention must be {EXPECTED_LOGSTORES}, got {actual}")
    credentials = spec.get("credentials", {})
    if credentials.get("source") != "deploymentSecret" or not credentials.get(
        "forbiddenInConfig"
    ):
        errors.append("SLS credentials must be deploymentSecret-only")
    scheduled = spec.get("scheduledSql", {})
    common = scheduled.get("common", {})
    if common.get("delaySeconds") != 120 or common.get("exactlyOnce") is not True:
        errors.append("Scheduled SQL must use 120s delay and Exactly-Once")
    jobs = scheduled.get("jobs", [])
    names = {row.get("rowKind") for row in jobs if isinstance(row, dict)}
    if names != {"event_dimensions", "performance", "error_dimensions", "video_qoe"}:
        errors.append("Scheduled SQL must define event/performance/error/video_qoe jobs")
    if not any("approx_set(sessionId)" in str(row.get("sql")) for row in jobs):
        errors.append("hourly aggregate must emit mergeable sessionHll")
    if any("AS __time__" not in str(row.get("sql")) for row in jobs):
        errors.append("Scheduled SQL destination __time__ must be businessHour")
    raw = next(
        (row for row in rows if row.get("name") == "app-product-telemetry-raw"),
        {},
    )
    indexes = raw.get("indexes", {}).get("fields", [])
    if "_batchKey" not in indexes:
        errors.append("_batchKey exact index is required for timeout confirmation")
    if "callStack" not in raw.get("indexes", {}).get("forbidden", []):
        errors.append("callStack must remain unindexed")


def main() -> int:
    errors: list[str] = []
    try:
        verify_catalog(errors)
        verify_pages(errors)
        verify_app_single_egress(errors)
        verify_sls_cutover(errors)
    except (OSError, ValueError, yaml.YAMLError) as error:
        errors.append(str(error))
    if errors:
        print("FAIL: product telemetry single-track contract")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASS: product telemetry single-track contract")
    print("  - strict 9-field catalog and generated page source")
    print("  - encrypted actor outbox and no AppLog auto-upload")
    print("  - SLS 3/3/90 retention, HLL late merge and Exactly-Once jobs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
