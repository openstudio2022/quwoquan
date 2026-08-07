#!/usr/bin/env python3
"""验证产品遥测九字段、目录、单出口与四环境 Elasticsearch 契约。"""

from __future__ import annotations


import sys
from pathlib import Path

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

import re

import yaml


METADATA = REPO_ROOT / "quwoquan_service/contracts/metadata"
PRODUCT_OPS_CONTRACT = (
    REPO_ROOT
    / "quwoquan_service/services/product-ops-service/contracts/product_ops/event_record"
)
EVENT_CATALOG = PRODUCT_OPS_CONTRACT / "event_catalog.yaml"
GOLDEN_METRIC_CATALOG = (
    PRODUCT_OPS_CONTRACT / "golden_metric_catalog.yaml"
)
EVENT_STORAGE = PRODUCT_OPS_CONTRACT / "storage.yaml"
APP_PAGES = METADATA / "_shared/app_pages.yaml"
EVENT_ROLLUPS = PRODUCT_OPS_CONTRACT / "rollups.yaml"
ELASTICSEARCH_ALERTS = (
    REPO_ROOT
    / "quwoquan_ops/observability/elasticsearch/product_telemetry_alerts.yaml"
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
EXPECTED_CONTEXT_EXTENSIONS = ["devicePlatform"]
FORBIDDEN_LEGACY_FIELDS = {
    "eventVersion",
    "eventId",
    "eventName",
    "priority",
    "producer",
    "payload",
    "metrics",
    "userIdHash",
}
EVENT_STORAGE_LOGSTORE_ROLES = (
    "raw",
    "startup_diagnostic",
    "runtime_diagnostic",
    "aggregate",
)
REQUIRED_EXPERIENCE_EVENTS = {
    "app_anr_outcome": {
        "required_extensions": {"detectionSource", "result"},
        "optional_extensions": {"durationMs"},
    },
    "app_frame_jank_outcome": {
        "required_extensions": {
            "sampledFrames",
            "jankyFrames",
            "worstFrameMs",
            "worstBuildFrameMs",
            "worstRasterFrameMs",
            "jankThresholdMs",
            "result",
        },
        "optional_extensions": {"surfaceId", "channelId"},
    },
    "page_first_usable": {
        "required_extensions": {"durationMs", "terminalState"},
        "optional_extensions": {"surfaceId", "failReasonCode"},
    },
    "page_error_outcome": {
        "required_extensions": {
            "surfaceId",
            "errorCode",
            "recoveryAction",
            "result",
        },
        "optional_extensions": {"action", "durationMs"},
    },
}
REQUIRED_APP_EXPERIENCE_METRIC_IDS = {
    "app_anr_rate",
    "app_jank_frame_rate",
    "page_first_usable_p95_ms",
    "page_error_recovery_rate",
}
ALLOWED_GOLDEN_AGGREGATIONS = {
    "event_ratio",
    "unique_session_ratio",
    "percentile_p50",
    "percentile_p95",
    "percentile_p99",
    "sum",
    "sum_ratio",
    "count",
}
ALLOWED_TARGET_OPERATORS = {
    "less_than",
    "less_than_or_equal",
    "greater_than",
    "greater_than_or_equal",
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


def event_storage_logstore_retentions() -> dict[str, int]:
    """读取 EventRecord 对象拥有的物理保留合同，禁止在 App gate 复制 TTL。"""
    storage = load_yaml(EVENT_STORAGE)
    logstores = storage.get("logstores")
    if not isinstance(logstores, dict):
        raise ValueError("EventRecord storage.logstores must be a mapping")
    expected: dict[str, int] = {}
    for role in EVENT_STORAGE_LOGSTORE_ROLES:
        row = logstores.get(role)
        if not isinstance(row, dict):
            raise ValueError(f"EventRecord storage.logstores.{role} is required")
        name = row.get("default_name")
        ttl_days = row.get("ttl_days")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                f"EventRecord storage.logstores.{role}.default_name is required"
            )
        if not isinstance(ttl_days, int) or ttl_days <= 0:
            raise ValueError(
                f"EventRecord storage.logstores.{role}.ttl_days must be positive"
            )
        if name in expected:
            raise ValueError(f"EventRecord logstore name must be unique: {name}")
        expected[name] = ttl_days
    return expected


def verify_catalog(errors: list[str]) -> None:
    catalog = load_yaml(EVENT_CATALOG)
    common_fields = catalog.get("common_fields")
    if common_fields != EXPECTED_COMMON_FIELDS:
        errors.append(
            f"event_catalog common_fields must be exactly {EXPECTED_COMMON_FIELDS}"
        )
    if catalog.get("context_extensions") != EXPECTED_CONTEXT_EXTENSIONS:
        errors.append(
            "event_catalog context_extensions must be exactly "
            f"{EXPECTED_CONTEXT_EXTENSIONS}"
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
    events_by_type = {
        str(row.get("event_type")): row for row in events if isinstance(row, dict)
    }
    for event_type, expected in REQUIRED_EXPERIENCE_EVENTS.items():
        row = events_by_type.get(event_type)
        if not isinstance(row, dict):
            errors.append(f"experience event missing from event_catalog: {event_type}")
            continue
        for key, fields in expected.items():
            if set(row.get(key, [])) != fields:
                errors.append(
                    f"{event_type} {key} must be exactly {sorted(fields)}"
                )
        if row.get("normal_sample_rate") != 1.0:
            errors.append(f"{event_type} must be reported at 100%")
        if row.get("internal_priority") != "critical":
            errors.append(f"{event_type} must remain critical")


def verify_golden_metrics(errors: list[str]) -> None:
    catalog = load_yaml(EVENT_CATALOG)
    golden = load_yaml(GOLDEN_METRIC_CATALOG)
    rules = golden.get("registration_rules")
    metrics = golden.get("metrics")
    if not isinstance(rules, dict) or not isinstance(metrics, list):
        errors.append("golden metric catalog needs registration_rules and metrics")
        return
    if not metrics:
        errors.append("golden metric catalog must register at least one metric")
        return
    maximum = rules.get("max_primary_metrics_per_business")
    if not isinstance(maximum, int) or maximum <= 0 or maximum > 3:
        errors.append("golden metrics max primary count must be an integer <= 3")
        return
    required_dimensions = set(rules.get("required_drilldown_dimensions", []))
    forbidden_dimensions = set(rules.get("forbidden_dimensions", []))
    if not required_dimensions:
        errors.append("golden metrics must declare required drilldown dimensions")
    if required_dimensions & forbidden_dimensions:
        errors.append("golden metric required and forbidden dimensions overlap")
    common_fields = set(catalog.get("common_fields", []))
    context_extensions = set(catalog.get("context_extensions", []))
    extension_fields = set((catalog.get("extension_fields") or {}).keys())
    allowed_fields = common_fields | context_extensions | extension_fields
    events = {
        str(row.get("event_type")): row
        for row in catalog.get("events", [])
        if isinstance(row, dict)
    }
    counts: dict[str, int] = {}
    metric_ids: set[str] = set()
    for metric in metrics:
        if not isinstance(metric, dict):
            errors.append("golden metric row must be a mapping")
            continue
        metric_id = str(metric.get("metric_id", "")).strip()
        business = str(metric.get("business", "")).strip()
        if not metric_id or metric_id in metric_ids:
            errors.append(f"golden metric_id must be non-empty and unique: {metric_id}")
            continue
        if re.fullmatch(r"[a-z][a-z0-9_]*", metric_id) is None:
            errors.append(f"golden metric_id must be snake_case: {metric_id}")
        metric_ids.add(metric_id)
        tier = metric.get("tier")
        if tier not in {"primary", "secondary"}:
            errors.append(f"{metric_id} tier must be primary or secondary")
        if not business:
            errors.append(f"{metric_id} business must be non-empty")
        if not str(metric.get("owner", "")).strip():
            errors.append(f"{metric_id} owner must be non-empty")
        if tier == "primary":
            counts[business] = counts.get(business, 0) + 1
        source = metric.get("source")
        if not isinstance(source, dict):
            errors.append(f"{metric_id} source must be a mapping")
            continue
        if source.get("track") != rules.get("required_source_track"):
            errors.append(f"{metric_id} must use the registered source track")
        aggregation = source.get("aggregation")
        if aggregation not in ALLOWED_GOLDEN_AGGREGATIONS:
            errors.append(
                f"{metric_id} uses unsupported aggregation {aggregation}"
            )
        is_ratio = (
            "numerator_event_type" in source
            or "denominator_event_type" in source
        )
        is_single_event = "event_type" in source
        if is_ratio == is_single_event:
            errors.append(
                f"{metric_id} source must use exactly one event or ratio shape"
            )
        if is_ratio and (
            not source.get("numerator_event_type")
            or not source.get("denominator_event_type")
        ):
            errors.append(
                f"{metric_id} ratio source needs numerator and denominator events"
            )
        if aggregation == "sum_ratio" and (
            not source.get("numerator_value_field")
            or not source.get("denominator_value_field")
        ):
            errors.append(
                f"{metric_id} sum_ratio needs numerator and denominator value fields"
            )
        referenced_events = {
            str(value)
            for key, value in source.items()
            if key.endswith("event_type")
        }
        for event_type in referenced_events:
            if event_type not in events:
                errors.append(f"{metric_id} references unknown event {event_type}")
        value_field = source.get("value_field")
        if value_field is not None and value_field not in allowed_fields:
            errors.append(f"{metric_id} references unknown value_field {value_field}")
        single_event = events.get(str(source.get("event_type")))
        if value_field is not None and isinstance(single_event, dict):
            event_fields = set(single_event.get("required_extensions", [])) | set(
                single_event.get("optional_extensions", [])
            )
            if value_field not in event_fields and value_field not in common_fields:
                errors.append(
                    f"{metric_id} value_field {value_field} is not emitted by "
                    f"{source.get('event_type')}"
                )
        for prefix in ("numerator", "denominator"):
            ratio_value_field = source.get(f"{prefix}_value_field")
            if ratio_value_field is None:
                continue
            if aggregation != "sum_ratio":
                errors.append(
                    f"{metric_id} {prefix}_value_field requires sum_ratio"
                )
            if ratio_value_field not in allowed_fields:
                errors.append(
                    f"{metric_id} references unknown {prefix}_value_field "
                    f"{ratio_value_field}"
                )
                continue
            event_type = str(source.get(f"{prefix}_event_type", ""))
            event = events.get(event_type)
            if isinstance(event, dict):
                event_fields = set(event.get("required_extensions", [])) | set(
                    event.get("optional_extensions", [])
                )
                if ratio_value_field not in event_fields:
                    errors.append(
                        f"{metric_id} {prefix}_value_field {ratio_value_field} "
                        f"is not emitted by {event_type}"
                    )
        for prefix in ("numerator", "denominator"):
            result_filter = source.get(f"{prefix}_result")
            event_type = str(source.get(f"{prefix}_event_type", ""))
            event = events.get(event_type)
            if result_filter is None or not isinstance(event, dict):
                continue
            event_fields = set(event.get("required_extensions", [])) | set(
                event.get("optional_extensions", [])
            )
            if "result" not in event_fields:
                errors.append(
                    f"{metric_id} filters {event_type} by result, but the event "
                    "does not emit result"
                )
            if not str(result_filter).strip():
                errors.append(f"{metric_id} {prefix}_result must be non-empty")
        raw_dimensions = metric.get("dimensions", [])
        if not isinstance(raw_dimensions, list) or any(
            not isinstance(value, str) or not value.strip()
            for value in raw_dimensions
        ):
            errors.append(f"{metric_id} dimensions must be non-empty strings")
            raw_dimensions = []
        dimensions = set(raw_dimensions)
        if len(dimensions) != len(raw_dimensions):
            errors.append(f"{metric_id} dimensions must be unique")
        if not required_dimensions.issubset(dimensions):
            errors.append(
                f"{metric_id} lacks drilldowns {sorted(required_dimensions - dimensions)}"
            )
        unknown = dimensions - allowed_fields
        if unknown:
            errors.append(f"{metric_id} has unknown dimensions {sorted(unknown)}")
        forbidden = dimensions & forbidden_dimensions
        if forbidden:
            errors.append(
                f"{metric_id} uses high-cardinality dimensions {sorted(forbidden)}"
            )
        target = metric.get("target")
        if not isinstance(target, dict) or "operator" not in target or "value" not in target:
            errors.append(f"{metric_id} must declare an operator/value target")
        elif target.get("operator") not in ALLOWED_TARGET_OPERATORS:
            errors.append(f"{metric_id} target operator is unsupported")
        elif isinstance(target.get("value"), bool) or not isinstance(
            target.get("value"), (int, float)
        ):
            errors.append(f"{metric_id} target value must be numeric")
        freshness = metric.get("freshness_seconds")
        if not isinstance(freshness, int) or freshness <= 0:
            errors.append(f"{metric_id} must declare positive freshness_seconds")
    for business, count in counts.items():
        if count > maximum:
            errors.append(
                f"{business} registers {count} primary metrics, maximum is {maximum}"
            )
    missing_required = REQUIRED_APP_EXPERIENCE_METRIC_IDS - metric_ids
    if missing_required:
        errors.append(
            "app experience golden metrics are incomplete: "
            + ", ".join(sorted(missing_required))
        )


def verify_experience_collection_wiring(errors: list[str]) -> None:
    require_source(
        "quwoquan_app/lib/runtime/observability/telemetry/"
        "app_page_experience_tracker.dart",
        [
            "AppTelemetryPayload.appAnrOutcome",
            "AppTelemetryPayload.appFrameJankOutcome",
            "AppTelemetryPayload.pageFirstUsable",
            "AppTelemetryPayload.pageErrorOutcome",
            "recordLifecycleTerminal",
        ],
        errors,
    )
    require_source(
        "quwoquan_app/lib/runtime/observability/runtime_diagnostics.dart",
        [
            "dart_event_loop_watchdog",
            "recordPreviousNativeAnr",
            "recordAnrOutcome",
            "acknowledgePreviousAnr",
        ],
        errors,
    )
    require_source(
        "quwoquan_app/lib/runtime/shell/navigation/page_access_log_util.dart",
        ["beginPageVisit", "page_first_usable"],
        errors,
    )
    require_source(
        "quwoquan_app/lib/design_system/feedback/error_states/app_error_states.dart",
        [
            "recordFirstUsable",
            "recordPageErrorOutcome",
            "recovery_unexpected_failure",
        ],
        errors,
    )
    require_source(
        "quwoquan_service/services/product-ops-service/internal/product_ops/"
        "event_record/domain/fact.go",
        [
            'generated.EventExtensionFields["devicePlatform"]',
            "generated.EventContextExtensions[name]",
            "type EventRecordInput = generated.EventRecordInput",
        ],
        errors,
    )
    require_source(
        "quwoquan_service/services/product-ops-service/internal/product_ops/"
        "event_record/application/telemetry_service.go",
        ["type EventRecordInput = eventdomain.Input"],
        errors,
    )
    require_source(
        "quwoquan_service/services/product-ops-service/generated/product_ops/event_record/event_catalog.go",
        [
            'out["recoveryAction"]',
            'out["detectionSource"]',
            'out["terminalState"]',
        ],
        errors,
    )
    require_source(
        "quwoquan_app/android/app/src/main/java/com/quwoquan/quwoquan_app/MainActivity.java",
        [
            "ApplicationExitInfo.REASON_ANR",
            "getHistoricalProcessExitReasons",
            "readPreviousNativeAnrMarker",
            "acknowledgePreviousNativeAnrMarker",
        ],
        errors,
    )
    require_source(
        "quwoquan_app/ios/Runner/AppDelegate.swift",
        [
            "MXMetricManagerSubscriber",
            "hangDiagnostics",
            "NativeHangMetricStore.shared.read",
            "NativeHangMetricStore.shared.acknowledge",
        ],
        errors,
    )


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
        "quwoquan_app/lib/runtime/observability/telemetry/"
        "app_telemetry_reporter.dart",
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
        "quwoquan_app/lib/runtime/observability/telemetry/"
        "app_telemetry_outbox.dart",
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
        "quwoquan_app/lib/runtime/observability/telemetry/"
        "app_telemetry_session_store.dart",
        ["base64Url", "AppLifecycleState.inactive", "foreground_resume"],
        errors,
    )
    require_source(
        "quwoquan_app/lib/service/content_service/content/content_behavior_fact/application/"
        "public/content_behavior_repository.dart",
        ["implements BehaviorReporter"],
        errors,
    )
    for path in (APP_ROOT / "lib").rglob("*.dart"):
        content = path.read_text(encoding="utf-8")
        if "AppLogUploader" in content or "OpsEventRepository" in content:
            errors.append(
                f"legacy automatic Ops upload symbol remains: {path.relative_to(REPO_ROOT)}"
            )


def verify_elasticsearch_single_track(errors: list[str]) -> None:
    storage = load_yaml(EVENT_STORAGE)
    backends = storage.get("environment_backends", {})
    if set(backends) != {"alpha", "beta", "gamma", "prod"}:
        errors.append("Elasticsearch bindings must cover alpha/beta/gamma/prod")
    for environment, binding in backends.items():
        if not isinstance(binding, dict) or binding.get("adapter") != "ext.obs.elasticsearch":
            errors.append(f"{environment} must bind ext.obs.elasticsearch")
    if storage.get("fallback") != "forbidden":
        errors.append("Elasticsearch log sink fallback must be forbidden")

    rollups = load_yaml(EVENT_ROLLUPS)
    jobs = rollups.get("jobs", [])
    names = {row.get("row_kind") for row in jobs if isinstance(row, dict)}
    required_names = {
        "event_dimensions",
        "performance",
        "error_dimensions",
        "product_action_funnel",
        "video_qoe",
        "rtc_qoe",
        "runtime_diagnostics",
    }
    missing_names = required_names - names
    if missing_names:
        errors.append(
            "Elasticsearch rollups must define event/product-action/performance/error/"
            "video_qoe/rtc_qoe/runtime jobs; missing "
            + ", ".join(sorted(missing_names))
        )
    if not any(
        any(
            isinstance(measure, dict) and measure.get("name") == "sessionHll"
            for measure in row.get("measures", [])
        )
        for row in jobs
        if isinstance(row, dict)
    ):
        errors.append("hourly aggregate must emit mergeable sessionHll")
    for row in jobs:
        if not isinstance(row, dict) or not row.get("row_kind"):
            errors.append("Elasticsearch rollup row_kind discriminator missing")
    common = rollups.get("common", {})
    row_identity = common.get("row_identity", {})
    if row_identity.get("fields") != ["_batchKey", "_batchIndex"]:
        errors.append("Elasticsearch rollups must deduplicate canonical batch rows")
    output = common.get("output", {})
    for field in ("freshness_field", "generated_through_field", "lag_seconds_field"):
        if not output.get(field):
            errors.append(f"Elasticsearch rollup waterline field missing: {field}")
    raw = storage.get("logstores", {}).get("raw", {})
    indexes = raw.get("indexed_fields", [])
    if "_batchKey" not in indexes:
        errors.append("_batchKey exact index is required for timeout confirmation")
    if "callStack" not in raw.get("non_indexed_fields", []):
        errors.append("callStack must remain unindexed")
    alert_policy = load_yaml(ELASTICSEARCH_ALERTS).get("spec", {})
    if alert_policy.get("adapter") != "ext.obs.elasticsearch":
        errors.append("product telemetry alert policy must use Elasticsearch")


def main() -> int:
    errors: list[str] = []
    try:
        verify_catalog(errors)
        verify_golden_metrics(errors)
        verify_experience_collection_wiring(errors)
        verify_pages(errors)
        verify_app_single_egress(errors)
        verify_elasticsearch_single_track(errors)
    except (OSError, ValueError, yaml.YAMLError) as error:
        errors.append(str(error))
    if errors:
        print("FAIL: product telemetry single-track contract")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASS: product telemetry single-track contract")
    print("  - strict 9-field catalog and generated page source")
    print("  - ANR/first-usable/error outcome and golden metric coverage")
    print("  - encrypted actor outbox and no AppLog auto-upload")
    print(
        "  - four-environment Elasticsearch storage, HLL late merge and "
        "canonical row deduplication"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
